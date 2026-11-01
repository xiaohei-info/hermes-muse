"""Source registry.

Session sources classify as user / machine / unclassified. Only `user` is signal and authority; an
unclassified source is ignored here and reported by the host probe `signal_purity`.
External sources (`<kind>:<account>`, e.g. `mail:work`) have a minimum check interval and a SourceState
that observe() moves: the same limitation code 5 times in a row becomes `limited` (no longer a gap),
an error is `failing` and flagged for Health after 3 in a row, a clean check is `ok`.
"""
from ..host.sessions import classify  # noqa: F401 - one classification for intake, goals and the probe
from .common import H, patch
from .store.keys import SOURCE_ID, source_key


def bootstrap(store, now):
    """Register complete historical identities once; retain original rows and every successful watermark.

    This is bookkeeping, not a read or a successful check. Existing registry rows always win.
    """
    created = 0
    with store.atomic():
        rows = store.query("source")
        registered = {e["natural_key"] for e in rows if SOURCE_ID.fullmatch(e["natural_key"])}
        for old in sorted(rows, key=lambda e: e["updated"], reverse=True):
            if SOURCE_ID.fullmatch(old["natural_key"]):
                continue
            data = old["payload"]
            key = source_key(data.get("source"))
            if not key or key in registered:
                continue
            store.create("source", key, {**data, "legacy_id": old["id"],
                         "last_checked": data.get("last_checked") or data.get("finished_at")},
                         state=old["state"], now=now, reason="source:bootstrap")
            registered.add(key)
            created += 1
    return created

# Seconds between checks per kind; plugin setting `source_intervals` ({id or kind: minutes}) overrides.
INTERVALS = {"calendar": 2 * H, "mail": 30 * 60, "reminders": H, "web": 6 * H, "rss": 6 * H}
DEFAULT_INTERVAL = H
LIMITED_AFTER, FAILING_ALERT = 5, 3


def check_id(source_id):
    source_id = str(source_id or "").strip().lower()
    if not SOURCE_ID.fullmatch(source_id):
        raise ValueError("source_id must be <kind>:<account> in [a-z0-9_.:@-], at most 64 characters, for example mail:work")
    return source_id


def interval(source_id, overrides=None):
    kind = source_id.partition(":")[0]
    for key in (source_id, kind):
        minutes = (overrides or {}).get(key)
        if type(minutes) in (int, float) and minutes > 0:
            return minutes * 60
    return INTERVALS.get(kind, DEFAULT_INTERVAL)


def due(store, now, overrides=None):
    """Known (observed or configured) sources whose minimum interval has passed, least recently checked first."""
    states = {e["natural_key"]: e for e in store.query("source") if SOURCE_ID.fullmatch(e["natural_key"])}
    configured = {str(k) for k in (overrides or {}) if SOURCE_ID.fullmatch(str(k))}
    out = []
    for source_id in set(states) | configured:
        e = states.get(source_id)
        last = (e["payload"].get("last_checked") if e else None) or 0
        every = interval(source_id, overrides)
        if last + every <= now:
            out.append({"source_id": source_id, "state": e["state"] if e else "new",
                        "last_checked": last or None, "every_minutes": int(every // 60),
                        **({key: e["payload"].get(key) for key in ("source", "last_success", "cursor")}
                           if e and e["payload"].get("source") else {})})
    return sorted(out, key=lambda s: (s["last_checked"] or 0, s["source_id"]))


def record(store, source_id, *, limitation_code=None, error=None, now):
    """Update one SourceState after a check."""
    source_id = check_id(source_id)
    with store.atomic():
        e = store.create("source", source_id, {}, now=now)
        previous = e["payload"]
        if error:
            fails = previous.get("fail_streak", 0) + 1
            state, data = "failing", {"fail_streak": fails, "health": fails >= FAILING_ALERT, "error": str(error)[:300]}
        elif limitation_code:
            code = str(limitation_code)[:64]
            streak = previous.get("limit_streak", 0) + 1 if previous.get("limitation_code") == code else 1
            state = "limited" if streak >= LIMITED_AFTER else "ok"
            data = {"limitation_code": code, "limit_streak": streak, "gap": streak < LIMITED_AFTER, "fail_streak": 0, "health": False}
        else:
            state, data = "ok", {"limitation_code": None, "limit_streak": 0, "gap": False, "fail_streak": 0,
                                 "health": False, "error": None, "last_success": now}
        return patch(store, e["id"], state, reason=f"observe:{state}", payload={**data, "last_checked": now}, now=now)
