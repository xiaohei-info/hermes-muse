"""Helpers shared by the kernel business modules: CAS patch, managed-file headers, preferences, clipping."""
import json
from datetime import datetime
from pathlib import Path

from .store import machine

H, D = 3600, 86400
PREFIX = "<!-- hermes-muse "
DEFAULT_PREFERENCES = {"start_hour": 9, "end_hour": 22, "ordinary_per_day": None, "time_sensitive_per_day": 3, "urgent_per_day": 2,
                       "blocked_topics": [], "deliver": None, "goal_dormant_days": 3, "goal_fade_days": 3,
                       "fade_question": None}


def header(text):
    """JSON metadata on the first line of a managed Muse file, or None."""
    first = text.partition("\n")[0].strip()
    if not (first.startswith(PREFIX) and first.endswith(" -->")):
        return None
    try:
        value = json.loads(first[len(PREFIX):-4])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def render(record, body):
    return (PREFIX + json.dumps(record, ensure_ascii=False, allow_nan=False) + " -->\n" + body).encode()


def preferences(home):
    """PROACTIVE_PREFERENCES.md header over defaults; invalid metadata blocks delivery rather than guessing."""
    try:
        stored = header((Path(home) / "muse" / "PROACTIVE_PREFERENCES.md").read_text(encoding="utf-8"))
    except FileNotFoundError:
        stored = {}
    prefs = {**DEFAULT_PREFERENCES, **(stored or {})}
    valid = (stored is not None
             and all(type(prefs[k]) is int and 0 <= prefs[k] <= high
                     for k, high in (("start_hour", 23), ("end_hour", 24), ("urgent_per_day", 50)))
             and all(prefs[k] is None or type(prefs[k]) is int and prefs[k] >= 0 for k in ("ordinary_per_day", "time_sensitive_per_day"))
             and isinstance(prefs["blocked_topics"], list))
    if not valid:
        raise ValueError("PROACTIVE_PREFERENCES.md metadata is invalid; notices wait until it is repaired")
    return prefs


def patch(store, entity_id, to_state=None, *, reason, payload=None, deadline=None, expect=None, now=None):
    """One CAS step inside a write transaction, so it cannot lose a race; None when the entity left `expect`.

    `payload` may be a function of the current entity (read-modify-write); a caller-owned deadline carries over.
    """
    with store.atomic():
        current = store.get(entity_id)
        if current is None or (expect and current["state"] not in expect):
            return None
        to_state = to_state or current["state"]
        ttl = machine(current["kind"]).ttl
        if deadline is None and to_state in ttl and ttl[to_state][0] is None:
            deadline = current["deadline"]
        data = payload(current) if callable(payload) else payload
        return store.transition(entity_id, to_state, state=current["state"], version=current["version"],
                                reason=reason, payload=data, deadline=deadline, now=now)


def one(store, kind, natural_key):
    """Latest entity with this natural key."""
    rows = store.query(kind, natural_key=natural_key, limit=1)
    return rows[0] if rows else None


def clip(text, limit):
    """Head and tail of `text` within `limit` characters."""
    text = str(text or "")
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n…[{len(text) - limit} chars omitted]…\n{text[-half:]}"


def local_midnight(now, tz):
    return datetime.fromtimestamp(now, tz).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def local_day(now, tz):
    return datetime.fromtimestamp(now, tz).date().isoformat()


def count_today(store, name, now, tz, limit):
    """Increment the per-day counter `name` unless it reached `limit`; True when incremented."""
    day = local_day(now, tz)
    with store.atomic():
        counts = store.meta(name, {})
        if counts.get(day, 0) >= limit:
            return False
        store.set_meta(name, {day: counts.get(day, 0) + 1})
    return True
