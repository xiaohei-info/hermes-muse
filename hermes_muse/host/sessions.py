"""Hermes conversations: private user-surface turns, bounded redacted reads, cron session -> owned job."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from . import Part, tolerant

# Allowlist, fail closed: an unlisted source is never user authority; probe `signal_purity` reports it.
USER_SOURCES = frozenset({
    "cli", "tui", "gui", "desktop", "ios", "acp",
    "telegram", "discord", "whatsapp", "whatsapp_cloud", "slack", "signal", "mattermost", "matrix",
    "email", "sms", "dingtalk", "feishu", "wecom", "weixin", "bluebubbles", "qqbot", "yuanbao",
})
MACHINE_SOURCES = frozenset({
    "cron", "oneshot", "kanban", "subagent", "delegate", "tool", "batch", "api", "api_server",
    "webhook", "msgraph_webhook", "wecom_callback", "relay", "bot_room", "bot_peer_dm",
})
GROUP_CHATS = ("group", "supergroup", "channel", "guild", "room")
HIDDEN_KINDS = ("hidden", "process_complete", "async_delegation_complete")
# Cron/Muse/delegation results arrive as user-role turns in a user session; they are not the user.
BACKGROUND = ('[Cronjob "', "[ASYNC DELEGATION ", "[IMPORTANT:", "[Hermes Muse ")
COLUMNS = {
    "sessions": {"id", "source", "chat_type", "title", "cwd", "started_at", "last_activity_at", "archived"},
    "messages": {"id", "session_id", "role", "content", "timestamp", "tool_name",
                 "display_kind", "active", "compacted", "message_uid"},
}
EXCERPT = 8000
READ_MAX = 12000
SECRETS = [
    # a labelled value only when it looks like one (6+ chars with a digit): not prose ("page token: when") or code
    (re.compile(r"(?i)((?:password|passwd|pwd|passcode|secret|token|api[_-]?key|密码|口令)[\"']?\s*[:：=]\s*[\"']?)"
                r"(?=[^\s\"'<>,;()]*\d)[^\s\"'<>,;()]{6,}"), r"\1[REDACTED]"),
    (re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}"), "[REDACTED]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"), "[REDACTED]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1[REDACTED]@"),
]


def classify(source):
    """user | machine | unclassified for a session source or platform; only `user` is signal and authority."""
    source = str(source or "").lower()
    return "user" if source in USER_SOURCES else "machine" if source in MACHINE_SOURCES else "unclassified"


def caller(platform="", task_id="", parent_session_id="", stored_source=None, **_):
    """Who runs the current hook or tool call: user | cron | child | group | other.

    Only `user` (a private turn on a user-surface platform) carries authority or gets injections.
    `stored_source()` is the session's `sessions.source`, Hermes' final classification of the session
    (e.g. `oneshot` for `hermes -q` although the env says cli): when the row exists it decides; the call's
    platform or the session env (which a child process may simply inherit) can only narrow it, never widen it.
    Without a row only the host's own `platform` kwarg of this call counts (hooks get it; tool calls never
    run before Hermes writes the row); an env value alone is not evidence. Otherwise: missing, refused.
    """
    from agent.delegation_context import is_delegated_child_context
    from gateway.session_context import get_session_env
    if parent_session_id or is_delegated_child_context():
        return "child"
    stored = str((stored_source() if stored_source else "") or "").lower()
    # The gateway binds the session platform, CLI/TUI/desktop bind the session source.
    named = str(platform or get_session_env("HERMES_SESSION_PLATFORM", "")
                or get_session_env("HERMES_SESSION_SOURCE", "")).lower()
    if (get_session_env("HERMES_CRON_SESSION", "") == "1" or "cron" in (named, stored)
            or str(task_id or "").startswith("cron:")):
        return "cron"
    if get_session_env("HERMES_SESSION_CHAT_TYPE", "").lower() in GROUP_CHATS:
        return "group"
    if not stored:
        return "user" if classify(platform) == "user" else "other"
    return "user" if classify(stored) == "user" and classify(named or stored) == "user" else "other"


def run_of(task_id, job_id) -> bool:
    """True when a hook's task_id belongs to a run of cron job `job_id` (Hermes: `cron:<job_id>:<execution_id>`)."""
    return bool(job_id) and str(task_id or "").startswith(f"cron:{job_id}:")


def failed_result(text: str) -> bool:
    """A native tool result whose JSON root reports failure (never words quoted in its body)."""
    try:
        value = json.loads(text or "null")
    except (ValueError, TypeError, RecursionError):
        return False
    return isinstance(value, dict) and (
        value.get("ok") is False or value.get("success") is False or value.get("isError") is True
        or bool(value.get("error")) or value.get("status") in ("error", "failed"))


def redact(text: str) -> str:
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def clean(value):
    """The one gate for what Muse hands the model (tool results, Script Output): every string redacted."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def excerpt(text: str) -> str:
    if len(text) <= EXCERPT:
        return text
    half = EXCERPT // 2
    return f"{text[:half]}\n…[{len(text) - EXCERPT} chars omitted; read(ref, offset) for more]…\n{text[-half:]}"


def as_text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


@contextmanager
def reader(path: Path):
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


PRIVATE_USER = (f"s.source IN ({','.join('?' * len(USER_SOURCES))}) "
                f"AND LOWER(COALESCE(s.chat_type,'')) NOT IN ({','.join('?' * len(GROUP_CHATS))})")
PRIVATE_USER_ARGS = (*sorted(USER_SOURCES), *GROUP_CHATS)


class Sessions(Part):
    @property
    def path(self):
        return self.home / "state.db"

    @tolerant(list)
    def user_turns(self, since, roles=("user",), limit=500):
        """Turns after `since` in private user-surface sessions, oldest first, redacted, excerpted above 8k.

        Natural key is `ref` = `<session>:<message>`; `chars` is the full redacted length for `read`.
        """
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            rows = db.execute(
                "SELECT m.id, m.session_id, m.role, m.content, m.timestamp, m.tool_name, m.message_uid, s.source "
                "FROM messages m JOIN sessions s ON s.id = m.session_id "
                f"WHERE m.timestamp > ? AND m.role IN ({','.join('?' * len(roles))}) AND {PRIVATE_USER} "
                f"AND COALESCE(m.display_kind,'') NOT IN ({','.join('?' * len(HIDDEN_KINDS))}) "
                "AND (m.active = 1 OR m.compacted = 1) AND m.content IS NOT NULL AND m.content != '' "
                "ORDER BY m.timestamp, m.id LIMIT ?",
                (since, *roles, *PRIVATE_USER_ARGS, *HIDDEN_KINDS, limit)).fetchall()
        turns, seen = [], set()
        for row in rows:
            try:
                text = as_text(row["content"])
                if row["message_uid"] in seen or text.strip() == "[SILENT]":
                    continue  # compression copies share the original's uid
                if row["role"] == "user" and text.lstrip().startswith(BACKGROUND):
                    continue
                if row["message_uid"]:
                    seen.add(row["message_uid"])
                clean = redact(text)
                turns.append({"ref": f"{row['session_id']}:{row['id']}", "session_id": row["session_id"],
                              "role": row["role"], "at": row["timestamp"], "source": row["source"],
                              "tool_name": row["tool_name"], "chars": len(clean),
                              "attachment": len(clean) > EXCERPT, "text": excerpt(clean)})
            except Exception as exc:
                self.adapter.fault("sessions.user_turns.row", exc)
        return turns

    @tolerant(lambda: {"available": False})
    def read(self, ref, offset=0, length=READ_MAX):
        """At most 12k redacted chars of one message in a private user-surface session."""
        session_id, _, message_id = str(ref).rpartition(":")
        if not self.path.exists():
            return {"ref": ref, "available": False}
        with reader(self.path) as db:
            row = db.execute(
                f"SELECT m.content FROM messages m JOIN sessions s ON s.id = m.session_id "
                f"WHERE m.session_id = ? AND m.id = ? AND {PRIVATE_USER}",
                (session_id, message_id, *PRIVATE_USER_ARGS)).fetchone()
        if not row:
            return {"ref": ref, "available": False}
        text = redact(as_text(row["content"]))
        offset, length = max(0, int(offset)), max(0, min(int(length), READ_MAX))
        part = text[offset:offset + length]
        return {"ref": ref, "available": True, "offset": offset, "total": len(text),
                "text": part, "more": offset + len(part) < len(text)}

    @tolerant(str)
    def source_of(self, session_id):
        """`sessions.source` of one session, '' when unknown."""
        if not session_id or not self.path.exists():
            return ""
        with reader(self.path) as db:
            row = db.execute("SELECT source FROM sessions WHERE id = ?", (str(session_id),)).fetchone()
        return (row["source"] or "") if row else ""

    @tolerant(lambda: None)
    def job_of(self, session_id):
        """Owned cron job id that ran this session, else None."""
        with reader(self.path) as db:
            row = db.execute("SELECT id, source, title, started_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        cron = self.adapter.cron
        return match_job(dict(row), cron.jobs(), cron.executions(row["started_at"] - 86400))

    @tolerant(list)
    def cron_sessions(self, since):
        """Cron-run sessions started after `since`, each with its owned `job_id` or None."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            rows = [dict(r) for r in db.execute(
                "SELECT id, source, title, started_at FROM sessions "
                "WHERE started_at > ? AND (source = 'cron' OR id LIKE 'cron\\_%' ESCAPE '\\')", (since,))]
        jobs, executions = self.adapter.cron.jobs(), self.adapter.cron.executions(since - 86400)
        return [{**row, "job_id": match_job(row, jobs, executions)} for row in rows]

    @tolerant(list)
    def tool_results(self, since, oversized=20000, tools=("muse_manage", "muse_job")):
        """Per owned-cron session after `since`: results of Muse's own `tools`, failures, results over `oversized`
        chars, and results still matching a credential pattern (what Muse handed the model unredacted). Other
        tools' output belongs to the host and the user's tools, not to a Muse read path."""
        runs = [s for s in self.cron_sessions(since) if s["job_id"]]
        out = []
        if not runs:
            return out
        with reader(self.path) as db:
            for run in runs:
                stats = {"session_id": run["id"], "job_id": run["job_id"], "tools": 0, "failed": 0, "oversized": 0, "secrets": 0}
                for (content,) in db.execute(
                        f"SELECT content FROM messages WHERE session_id = ? AND role = 'tool' AND tool_name IN "
                        f"({','.join('?' * len(tools))})", (run["id"], *tools)):
                    text = as_text(content or "")
                    stats["tools"] += 1
                    stats["failed"] += failed_result(text)
                    stats["oversized"] += len(text) > oversized
                    stats["secrets"] += redact(text) != text
                out.append(stats)
        return out

    @tolerant(Counter)
    def sources(self, since):
        """Session count per `sessions.source` with activity after `since`."""
        if not self.path.exists():
            return Counter()
        with reader(self.path) as db:
            return Counter({r[0]: r[1] for r in db.execute(
                "SELECT source, COUNT(*) FROM sessions WHERE COALESCE(last_activity_at, started_at) > ? GROUP BY source",
                (since,))})

    @tolerant(list)
    def bot_chats(self):
        """The profile's Bot Chat rows (delivery targets) with their host cwd."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            return [dict(r) for r in db.execute(
                "SELECT id, cwd FROM sessions WHERE title = 'Bot Chat' AND COALESCE(archived, 0) = 0")]

    def schema_gaps(self):
        """Columns this adapter reads that the native state.db lacks (none before the first session)."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            return [f"state.db {table}.{column}" for table, columns in COLUMNS.items()
                    for column in sorted(columns - {c[1] for c in db.execute(f"PRAGMA table_info({table})")})]


def match_job(session, jobs, executions):
    """`cron_<jid>_` id, else a cron session titled `<job name> · …` (or untitled) inside exactly one run window."""
    sid = session["id"]
    for jid in jobs:
        if sid.startswith(f"cron_{jid}_"):
            return jid
    if session["source"] != "cron":
        return None
    title = session.get("title") or ""
    named = {jid for jid, job in jobs.items()
             if title and (title == job.get("name") or title.startswith(f"{job.get('name')} · "))}
    if title and not named:
        return None
    hits = {e["job_id"] for e in executions
            if (not title or e["job_id"] in named) and e["start"] - 5 <= session["started_at"] <= e["end"] + 5}
    return hits.pop() if len(hits) == 1 else None
