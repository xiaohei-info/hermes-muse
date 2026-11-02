"""Conversation review: code picks every turn of the last 72h of private user sessions that fixed rules flag,
oldest first; the model only judges each (agent_gap / latent_need / friction / fine). One entity per turn, ever.

Rules: a completion claim with no successful write-type tool result in the same turn; a failed tool not
retried successfully; a user correction or near-repeat of the previous request; a stated need that matches
no goal, interest or idea title.
"""
import re
from difflib import SequenceMatcher

from .common import D, clip, one

PAGE = 2000  # host rows per read; the window is read page by page
WINDOW = 3 * D
VERDICTS = ("agent_gap", "latent_need", "friction", "fine")
CLAIM = re.compile(r"已完成|已发送|已修复|已部署|已提交|搞定|\b(?:done|fixed|completed|sent|deployed|resolved)\b", re.I)
CORRECTION = re.compile(r"不是|还是没|又|我说的是|不对|\b(?:not what I|still (?:not|doesn'?t|broken)|again|I said|that'?s wrong)\b", re.I)
NEED = re.compile(r"帮我|记得|提醒我|以后|我想|打算|计划|\b(?:remind me|I want to|I'd like to|plan to|don'?t forget|todo)\b", re.I)
WRITE_TOOL = re.compile(r"write|edit|patch|send|create|update|delete|commit|deploy|memory|terminal|manage|cron|todo", re.I)
FAILED = re.compile(r'"(?:success|ok)"\s*:\s*false|"error"\s*:\s*"[^"]|"status"\s*:\s*"(?:error|failed)"'
                    r'|^\s*(?:error|failed|traceback)\b', re.I | re.M)


def turns(rows):
    """Group time-ordered user/assistant/tool rows into turns per session."""
    out, current = [], {}
    for row in rows:
        sid = row["session_id"]
        if row["role"] == "user":
            previous = current.get(sid)
            turn = {"ref": row["ref"], "at": row["at"], "user": row["text"], "replies": [], "tools": [],
                    "previous": previous["user"] if previous else None,
                    "previous_reply": previous["replies"][-1] if previous and previous["replies"] else None}
            current[sid] = turn
            out.append(turn)
        elif sid in current:
            if row["role"] == "assistant":
                current[sid]["replies"].append(row["text"])
            else:
                current[sid]["tools"].append((row.get("tool_name") or "", not FAILED.search(row["text"][:2000])))
    return out


def rules(turn, titles):
    found, tools, user = [], turn["tools"], turn["user"]
    if CLAIM.search("\n".join(turn["replies"])) and not any(ok and WRITE_TOOL.search(name) for name, ok in tools):
        found.append("claim_without_write")
    if any(not ok and not any(ok2 and name2 == name for name2, ok2 in tools[i + 1:]) for i, (name, ok) in enumerate(tools)):
        found.append("tool_failure_unretried")
    previous = turn["previous"]
    if CORRECTION.search(user) or previous and len(user) >= 8 and SequenceMatcher(None, previous[:500], user[:500]).ratio() >= 0.8:
        found.append("user_correction")
    if NEED.search(user) and not any(len(t) >= 3 and t in user.lower() for t in titles):
        found.append("unrecorded_need")
    return found


def window(k, since):
    """Every user/assistant/tool row after `since`; a page restarts at its last timestamp, refs dedupe the overlap."""
    rows, refs = [], set()
    while True:
        page = [r for r in k.adapter.sessions.user_turns(since, roles=("user", "assistant", "tool"), limit=PAGE)
                if r["ref"] not in refs]
        if not page:
            return rows
        rows += page
        refs.update(r["ref"] for r in page)
        since = page[-1]["at"] - 1e-6


def candidates(k, now, skip=()):
    """Every matching turn, oldest first; turns already judged or in `skip` (offered tonight) are left out."""
    rows = window(k, now - WINDOW)
    titles = [str(e["payload"].get("title") or "").lower() for kind in ("goal", "interest", "idea") for e in k.store.query(kind)]
    picked = []
    for turn in turns(rows):
        ref = "review:" + turn["ref"]
        if ref in skip or one(k.store, "finding", ref) or one(k.store, "idea", ref):
            continue
        found = rules(turn, titles)
        if not found:
            continue
        picked.append({"kind": "review", "ref": ref, "at": turn["at"], "rules": found, "user": clip(turn["user"], 1500),
                       "reply": clip(turn["replies"][-1] if turn["replies"] else "", 1500),
                       **({"previous_reply": clip(turn["previous_reply"], 800)} if "user_correction" in found and turn["previous_reply"] else {}),
                       "tools": [{"name": n, "ok": ok} for n, ok in turn["tools"][:10]], "pointer": turn["ref"]})
    return picked


def record(k, ref, verdict, reason, now, rules=()):
    """agent_gap -> open Finding (14 days); friction (the user corrected or redid something a skill or rule could have
    settled) -> open Finding tagged friction, a suggestion only; latent_need -> Idea candidate; fine -> dismissed Finding.
    `evidence` is the reviewed turn (a pointer for read) plus the pick rules that matched it."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    reason = str(reason or "").strip()[:500]
    if not reason:
        raise ValueError("reason is required")
    turn = ref.removeprefix("review:")
    payload = {"reason": reason, "verdict": verdict, "turn": turn, "evidence": [turn, *(f"rule:{r}" for r in rules)]}
    with k.store.atomic():
        found = one(k.store, "finding", ref) or one(k.store, "idea", ref)
        if found:
            return {"result": "existing", "entity": found["id"]}
        if verdict == "latent_need":
            e = k.store.create("idea", ref, {"title": reason[:200], "origin": "review", **payload}, now=now)
        else:
            tag = {"tag": "friction"} if verdict == "friction" else {}
            e = k.store.create("finding", ref, {**payload, **tag}, state="dismissed" if verdict == "fine" else "open", now=now)
    return {"result": "recorded", "entity": e["id"], "state": e["state"]}
