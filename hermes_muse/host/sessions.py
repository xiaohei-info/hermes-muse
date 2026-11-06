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
    "cli", "tui", "gui", "desktop", "ios", "acp", "photon",
    "telegram", "discord", "whatsapp", "whatsapp_cloud", "slack", "signal", "mattermost", "matrix",
    "email", "sms", "dingtalk", "feishu", "wecom", "weixin", "bluebubbles", "qqbot", "yuanbao",
})
MACHINE_SOURCES = frozenset({
    "cron", "oneshot", "kanban", "subagent", "delegate", "tool", "batch", "api", "api_server",
    "webhook", "msgraph_webhook", "wecom_callback", "relay", "bot_room", "bot_peer_dm",
})
GROUP_CHATS = ("group", "supergroup", "channel", "guild", "room")
# Hermes' canonical main conversation: this exact title is its identity, and it is born hidden from the sidebar.
BOT_CHAT = "Bot Chat"
HIDDEN_KINDS = ("hidden", "process_complete", "async_delegation_complete")
# Producer prefixes of injected user-role turns that Hermes stored before it stamped them with a machinery display kind.
BACKGROUND = ('[Cronjob "', "[ASYNC DELEGATION ", "[IMPORTANT:", "[Hermes Muse ")
# A refused `other` caller; Health's main_session finds it among the main session's tool results.
UNRECOGNIZED = "Muse could not confirm this turn as the user's own private conversation"
LIVE_TURN = (f"COALESCE(m.display_kind,'') NOT IN ({','.join('?' * len(HIDDEN_KINDS))}) "
             "AND (m.active = 1 OR m.compacted = 1) AND m.content IS NOT NULL AND m.content != ''")
COLUMNS = {
    "sessions": {"id", "source", "chat_type", "title", "cwd", "started_at", "last_activity_at", "archived"},
    "session_admissions": {"target_session_id", "principal_id", "request_id"},
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


def surface():
    """The client or platform Hermes names for the running turn: `session_surface()` resolves a LOCAL turn to its
    launch policy's client (cli/tui/desktop/acp; cron for a scheduled run) and a chat turn to its platform. The
    in-process TUI binds no platform, only the session source."""
    from gateway.session_context import get_session_env
    from hermes_cli.plugin_session import session_surface
    return session_surface() or get_session_env("HERMES_SESSION_SOURCE", "")


def local_surfaces():
    """Hermes' LOCAL creation labels (those a peer refresh stores as `local`) and the client each one is."""
    from gateway.session_policy import STORED_AS_LOCAL, SURFACES
    return {label: SURFACES[label] for label in sorted(STORED_AS_LOCAL)}


def machinery(display_kind, content) -> bool:
    """A user-role turn Hermes injected (cron output, a finished background process, a delegation result), not words
    the user wrote: Hermes stamps its row with a machinery display kind; rows from before that stamp keep the
    producer's prefix."""
    from gateway.response_filters import is_machinery_display_kind
    return is_machinery_display_kind(display_kind) or (
        not display_kind and str(content or "").lstrip().startswith(BACKGROUND))


def turn_message(history):
    """The running turn's user message as Hermes hands it to an LLM hook (the last user entry), else None."""
    return next((m for m in reversed(history or ()) if isinstance(m, dict) and m.get("role") == "user"), None)


def caller(platform="", task_id="", parent_session_id="", conversation_history=None,
           stored_source=None, stored_transport=None, latest_turn=None, **_):
    """Who runs the current hook or tool call: user | cron | child | automation | group | other.

    Each fact comes from the host and is judged on its own:
    - automation: a delegated child (`child`), a cron run (`cron`), or a turn Hermes injected into a user conversation
      (`automation`: its user message carries a machinery display kind, see `machinery`). The turn's message is the
      one an LLM hook receives in `conversation_history`; a tool call reads the session's latest user row
      (`latest_turn()`), which Hermes persists before the turn's first model call;
    - group: the turn's chat type;
    - the user's private conversation: `stored_source()`, the resolved private producer and Hermes' final
      classification of the row (e.g. `oneshot` for `hermes -q` although the env says cli), and the turn's surface
      (the host's `platform` kwarg, else `surface()`) must both be user surfaces. The row decides; the surface, which a
      child process may simply inherit, can only narrow it. A transport name such as `local` is never a surface.
    Without a row only the host's own `platform` kwarg of this call counts (hooks get it; tool calls never run before
    Hermes writes the row); an env value alone is not evidence. Otherwise: missing, refused.
    Only `user` carries authority or gets injections.
    """
    from agent.delegation_context import is_delegated_child_context
    from gateway.session_context import get_session_env
    if parent_session_id or is_delegated_child_context():
        return "child"
    stored = str((stored_source() if stored_source else "") or "").lower()
    named = str(platform or surface()).lower()
    transport = str((stored_transport() if stored_transport else "") or "").lower()
    if (get_session_env("HERMES_CRON_SESSION", "") == "1" or "cron" in (named, stored, transport)
            or str(task_id or "").startswith("cron:")):
        return "cron"
    if get_session_env("HERMES_SESSION_CHAT_TYPE", "").lower() in GROUP_CHATS:
        return "group"
    if not (classify(stored) == "user" and classify(named or stored) == "user"
            or not stored and classify(platform) == "user"):
        return "other"
    message = turn_message(conversation_history) or (latest_turn() if stored and latest_turn else None)
    return "automation" if message and machinery(message.get("display_kind"), message.get("content")) else "user"


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


def memory_result(text: str, tool: str = "memory") -> dict | None:
    """A native memory or skill write that did not save, as {state, reason[, pending_id, command, usage]}; None for
    anything else. state staged: Hermes' write approval holds it, `command` is the slash command that reviews it.
    state failed: reason is capacity (the store's char limit), invalid (the call's own arguments or a text that
    matched nothing), disabled (config) or other. Hermes' failure class is not in the result, so this reads its shape."""
    try:
        value = json.loads(text or "null")
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("staged") or value.get("proposal_staged"):
        command = {"memory": "/memory", "skill_manage": "/skills"}.get(tool)
        return {"state": "staged", "reason": "approval", "pending_id": value.get("pending_id"), "command": command}
    if not failed_result(text):
        return None
    error = str(value.get("error") or "").casefold()
    if "usage" in value and any(word in error for word in ("limit", "exceed", "would put")):
        reason = "capacity"
    elif "disabled" in error:
        reason = "disabled"
    elif any(word in error for word in ("required", "needs ", "invalid", "no entry matched", "cannot be empty", "target")):
        reason = "invalid"
    else:
        reason = "other"
    return {"state": "failed", "reason": reason, **({"usage": value["usage"]} if isinstance(value.get("usage"), str) else {})}


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


def local_surface(raw, session_id, route, chat_id, user_id, surfaces):
    """Project only a matching native immutable creation receipt, never its config/prompt.
    `surfaces` is `local_surfaces()`.

    commit_local_session reserves sessions.source without created_source. A later
    placeholder writer can stamp `unknown`; the native receipt still proves who
    created this exact root/private route. An absent receipt permits the older
    created_source path; a present malformed or machine receipt fails closed.
    """
    if raw is None:
        return ""
    try:
        receipt = json.loads(raw)
        policy, entry = receipt["policy"], receipt["entry"]
        origin = entry["origin"]
        source = policy["source"]
        platform = surfaces.get(source)
        if (not platform or not route or not user_id or chat_id != session_id
                or receipt["session_id"] != session_id or receipt["route"] != route
                or receipt["principal_id"] != user_id
                or entry["session_id"] != session_id or entry["session_key"] != route
                or entry["platform"] != "local" or origin["platform"] != "local"
                or origin["chat_id"] != chat_id or origin["user_id"] != user_id
                or policy["platform"] != platform
                or json.loads(policy["request_json"])["source"] != source):
            return "other"
        return source
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return "other"


def private_user(db):
    """Shared authority/intake/read predicate; native provenance, never a caller override.

    Older schemas have no LOCAL provenance and retain their legacy source rules.
    Machine creation labels cannot gain authority through a later surface flip.
    Hidden rows are room plumbing or sessions put out of use; the canonical Bot Chat is hidden and is the user's.
    The leading s.source IN is what lets the query use sessions(source): the resolved source sits inside a CASE.
    """
    columns = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
    source, guards, native = "s.source", [], "''"
    surfaces = local_surfaces()
    labels = ",".join(f"'{s}'" for s in surfaces)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "state_meta" in tables and {"session_key", "chat_id", "user_id"} <= columns:
        from hermes_state_local import POLICY_PREFIX
        db.create_function("muse_local_surface", 5, lambda *row: local_surface(*row, surfaces=surfaces), deterministic=True)
        native = ("(SELECT muse_local_surface(value,s.id,s.session_key,s.chat_id,s.user_id) "
                  f"FROM state_meta WHERE key = '{POLICY_PREFIX}' || s.id)")
    if "created_source" in columns:
        source = f"CASE WHEN s.source = 'local' AND s.created_source IN ({labels}) THEN s.created_source ELSE s.source END"
        guards.append("(s.created_source IS NULL OR s.created_source = '' OR s.created_source IN ("
                      + ",".join("?" * len(USER_SOURCES))
                      + f") OR (s.created_source = 'unknown' AND {native} IN ({labels})))")
    source = (f"CASE WHEN s.source IN ('local',{labels}) THEN "
              f"COALESCE(NULLIF({native},''),({source})) ELSE s.source END")
    if "hidden" in columns:
        guards.append(f"(COALESCE(s.hidden,0) = 0 OR s.title = '{BOT_CHAT}')")
    predicate = f"s.source IN ('local',{','.join('?' * len(USER_SOURCES))}) AND " + PRIVATE_USER.replace("s.source", f"({source})")
    args = (*sorted(USER_SOURCES), *PRIVATE_USER_ARGS)
    if guards:
        predicate += " AND " + " AND ".join(guards)
    if "created_source" in columns:
        args += tuple(sorted(USER_SOURCES))
    return source, predicate, args


def turns_query(db, since, roles, limit):
    """(sql, args) of `user_turns`; the native contract asserts its query plan."""
    source, private, args = private_user(db)
    return (f"SELECT m.id, m.session_id, m.role, m.content, m.timestamp, m.tool_name, m.message_uid, m.display_kind, "
            f"({source}) AS source "
            "FROM messages m JOIN sessions s ON s.id = m.session_id "
            f"WHERE m.timestamp > ? AND m.role IN ({','.join('?' * len(roles))}) AND {private} AND {LIVE_TURN} "
            "ORDER BY m.timestamp, m.id LIMIT ?",
            (since, *roles, *args, *HIDDEN_KINDS, limit))


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
            rows = db.execute(*turns_query(db, since, roles, limit)).fetchall()
        turns, seen = [], set()
        for row in rows:
            try:
                text = as_text(row["content"])
                if row["message_uid"] in seen or text.strip() == "[SILENT]":
                    continue  # compression copies share the original's uid
                if row["role"] == "user" and machinery(row["display_kind"], text):
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
            _, private, args = private_user(db)
            row = db.execute(
                f"SELECT m.content FROM messages m JOIN sessions s ON s.id = m.session_id "
                f"WHERE m.session_id = ? AND m.id = ? AND {private}",
                (session_id, message_id, *args)).fetchone()
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

    @tolerant(str)
    def user_source_of(self, session_id):
        """Resolved private producer; present but excluded rows return `other`.

        Do not return empty for an excluded row: caller's pre-row hook fallback
        must never override stored child/group/machine provenance.
        """
        if not session_id or not self.path.exists():
            return ""
        with reader(self.path) as db:
            source, private, args = private_user(db)
            row = db.execute(f"SELECT CASE WHEN {private} THEN ({source}) ELSE 'other' END AS source "
                             "FROM sessions s WHERE s.id = ?", (*args, str(session_id))).fetchone()
        return row["source"] if row else ""

    def latest_turn(self, session_id):
        """{display_kind, content} of the session's latest live user row, else None. Raises when unreadable: the caller
        fails closed."""
        if not session_id or not self.path.exists():
            return None
        with reader(self.path) as db:
            row = db.execute("SELECT display_kind, content FROM messages WHERE session_id = ? AND role = 'user' "
                             "AND active = 1 ORDER BY id DESC LIMIT 1", (str(session_id),)).fetchone()
        return dict(row) if row else None

    @tolerant(lambda: None)
    def job_of(self, session_id):
        """Owned cron job id that ran this session, else None."""
        with reader(self.path) as db:
            row = db.execute("SELECT id, source, title, started_at FROM sessions WHERE id = ?", (session_id,)).fetchone()
            row = cron_admissions(db, [dict(row)])[0] if row else None
        if not row:
            return None
        cron = self.adapter.cron
        return match_job(row, cron.jobs(), cron.executions(row["started_at"] - 86400))

    @tolerant(list)
    def cron_sessions(self, since):
        """Cron-run sessions started after `since`, each with its owned `job_id` or None."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            rows = [dict(r) for r in db.execute(
                "SELECT id, source, title, started_at FROM sessions "
                "WHERE started_at > ? AND (source = 'cron' OR id LIKE 'cron\\_%' ESCAPE '\\')", (since,))]
            rows = cron_admissions(db, rows)
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
        """Session count per producer source with activity after `since`; unresolved LOCAL stays visible."""
        if not self.path.exists():
            return Counter()
        with reader(self.path) as db:
            source, _, _ = private_user(db)
            return Counter({r[0]: r[1] for r in db.execute(
                f"SELECT ({source}), COUNT(*) FROM sessions s "
                f"WHERE COALESCE(last_activity_at, started_at) > ? GROUP BY ({source})",
                (since,))})

    @tolerant(list)
    def bot_chats(self):
        """The profile's Bot Chat rows (delivery targets) with their host cwd."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            return [dict(r) for r in db.execute(
                "SELECT id, cwd FROM sessions WHERE title = ? AND COALESCE(archived, 0) = 0", (BOT_CHAT,))]

    @tolerant(list)
    def main_sessions(self, since, tools=("muse_manage", "muse_job")):
        """Bot Chats with user turns after `since`, as {id, source (`other` when excluded), turns: [timestamp],
        refused: Muse tool calls since then refused as an unrecognized caller (`UNRECOGNIZED`)}.

        Read past `private_user` and the caller, so Health can see either lose the main session. A title held by a
        machine conversation (Hermes moves those aside) is not the main session.
        """
        if not self.path.exists():
            return []
        chats, refused = {}, Counter()
        with reader(self.path) as db:
            for row in db.execute(
                    "SELECT s.id, s.source, m.content, m.display_kind, m.timestamp FROM sessions s JOIN messages m ON m.session_id = s.id "
                    f"WHERE s.title = ? AND COALESCE(s.archived, 0) = 0 AND m.role = 'user' AND m.timestamp > ? AND {LIVE_TURN}",
                    (BOT_CHAT, since, *HIDDEN_KINDS)):
                if classify(row["source"]) != "machine" and not machinery(row["display_kind"], row["content"]):
                    chats.setdefault(row["id"], []).append(row["timestamp"])
            for sid in chats:
                for (content,) in db.execute(
                        f"SELECT content FROM messages WHERE session_id = ? AND role = 'tool' AND timestamp > ? AND tool_name IN "
                        f"({','.join('?' * len(tools))})", (sid, since, *tools)):
                    refused[sid] += UNRECOGNIZED in as_text(content or "")
        return [{"id": sid, "source": self.user_source_of(sid), "turns": turns, "refused": refused[sid]}
                for sid, turns in chats.items()]

    def schema_gaps(self):
        """Columns this adapter reads that the native state.db lacks (none before the first session)."""
        if not self.path.exists():
            return []
        with reader(self.path) as db:
            return [f"state.db {table}.{column}" for table, columns in COLUMNS.items()
                    if table != "session_admissions" or db.execute("SELECT 1 FROM sqlite_master WHERE name='session_admissions'").fetchone()
                    for column in sorted(columns - {c[1] for c in db.execute(f"PRAGMA table_info({table})")})]


def cron_admissions(db, rows):
    """Annotate scheduler-owned LOCAL runs from the host's durable admission ledger.

    Older Hermes has no ledger: retain its id/title/window fallback. Never read
    admission payloads or treat a non-scheduler principal as provenance.
    """
    if not rows or not db.execute("SELECT 1 FROM sqlite_master WHERE name='session_admissions'").fetchone():
        return rows
    for row in rows:
        if row["source"] == "cron":
            admissions = list(db.execute(
                "SELECT principal_id, request_id FROM session_admissions WHERE target_session_id=?",
                (row["id"],)))
            if admissions:
                row["cron_requests"] = [r[1] for r in admissions if r[0] == "cron-owner"]
    return rows


def match_job(session, jobs, executions):
    """Scheduler admission first; legacy id/title/window only without that provenance."""
    if session["source"] == "cron" and "cron_requests" in session:
        hits = set()
        for request in session["cron_requests"]:
            named = {jid for jid in jobs if isinstance(request, str) and request.startswith(f"cron:{jid}:")
                     and request[len(f"cron:{jid}:"):]
                     and ":" not in request[len(f"cron:{jid}:"):]}
            if len(named) != 1:
                return None  # authoritative but malformed/unowned; never guess from the title
            hits.update(named)
        return hits.pop() if len(hits) == 1 else None
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
