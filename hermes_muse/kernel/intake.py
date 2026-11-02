"""Intake: private user turns become Signal entities; packets carry redacted head/tail excerpts only.

The host already selects user-surface sessions and redacts; excerpts are redacted again when handed
out because migrated v1 signals hold raw text. Disposing never requires reading the whole original.
"""
from ..host.sessions import EXCERPT, excerpt, redact
from .common import D, count_today, one, patch
from .sources import classify
from .store import signal_key

DISPOSITIONS = ("saved", "ignored", "context")
QUIET_WAKE_AFTER, QUIET_WAKES_PER_DAY = 300, 3


def capture(k, now):
    """Store new user turns since the intake watermark; returns how many were new."""
    store = k.store
    since = store.meta("intake_since")
    if since is None:
        migration = store.meta("migration")
        since = migration["at"] if migration else now - D
    turns = k.adapter.sessions.user_turns(since)
    new = 0
    for turn in turns:
        if classify(turn.get("source")) != "user":
            continue
        key = signal_key(turn["session_id"], turn["ref"])
        if one(store, "tombstone", key) or one(store, "tombstone", "signal:" + key):
            continue  # forgotten by the user
        e = store.create("signal", key, {
            "session_id": turn["session_id"], "source": turn.get("source"), "created": turn["at"],
            "excerpt": turn["text"], "chars": turn["chars"], "attachment": turn["attachment"],
            "pointer": {"ref": turn["ref"]}}, now=now)
        new += not e["existing"]
    if turns:  # equal timestamps cut by the host page limit are read again; create() dedupes them
        store.set_meta("intake_since", turns[-1]["at"] - 1e-6)
    return new


def item(e):
    p = e["payload"]
    pointer = p.get("pointer") or {}
    return {"kind": "intake", "ref": e["natural_key"], "at": p.get("created"), "source": p.get("source"),
            "chars": p.get("chars") or len(p.get("excerpt", "")),
            "attachment": bool(p.get("attachment") or p.get("truncated") or (p.get("chars") or 0) > EXCERPT),
            "attempt": e["attempts"] + 1, "excerpt": excerpt(redact(p.get("excerpt", ""))),
            "pointer": pointer.get("ref") or pointer.get("turn_id")}


def dispose(k, ref, disposition, facts=(), goal_hint=None, now=None):
    """saved / ignored / context; idempotent. A goal_hint naming an open goal records it as progress (activity, next
    check) and notifies nobody; assignments are started only by the patrol."""
    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {', '.join(DISPOSITIONS)}")
    e = one(k.store, "signal", ref)
    if e is None:
        raise KeyError(f"unknown signal {ref!r}")
    if e["state"] == "disposed":
        return e
    facts = [str(f).strip()[:1000] for f in facts or () if str(f).strip()][:20]
    moved = patch(k.store, e["id"], "disposed", expect=("new", "parked"), reason=f"intake:{disposition}",
                  payload={"disposition": disposition, "facts": facts, "goal_hint": goal_hint}, now=now)
    if goal_hint and goal_hint != "new":
        from . import goals
        goals.touch_if_open(k, goal_hint, now, "; ".join(facts)[:1000] or None)
    return moved or one(k.store, "signal", ref)


def captured_sources(store, since):
    """Session sources of signals stored since `since` (for the host probe signal_purity)."""
    return sorted({e["payload"].get("source") for e in store.query("signal", since=since) if e["payload"].get("source")})


def quiet_wake(k, last_turn_at, now):
    """True (and counted) when the user went quiet 5 min after a turn, signals wait, and < 3 such wakes today."""
    if now - last_turn_at < QUIET_WAKE_AFTER or not k.store.query("signal", state="new", limit=1):
        return False
    return count_today(k.store, "quiet_wakes", now, k.tz(), QUIET_WAKES_PER_DAY)
