"""Natural keys derived by code. Notifier (WP4) and the v1 migration must share these."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# A source is `<kind>:<account>` (mail:work). 0.3.x per-resource check ids (source-<hex>, migrated as history)
# and their `source:` copies are not sources: they are never due and never counted.
SOURCE_ID = re.compile(r"(?=.{3,64}\Z)(?!source:)[a-z0-9][a-z0-9_.@-]*:[a-z0-9_.:@-]+")
REFS = (re.compile(r"^gmail:(?:message|thread):([\w-]+)$", re.I), re.compile(r"^mail:<?([^<>\s]+)>?$", re.I))


def upstream(value):
    """Normalized upstream item ID (message-id, provider ID, URL) or None."""
    value = str(value or "").strip()
    if not value:
        return None
    for pattern in REFS:
        match = pattern.match(value)
        if match:
            return match.group(1).lower()
    if re.match(r"^https?://", value, re.I):
        parts = urlsplit(value)
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))
    return value.strip("<>").lower()


def notice_key(item_id=None, sources=(), title="", ts=None):
    """(notice key, strong). Strong keys are upstream IDs and dedupe against 7-day sent history;
    weak keys (title + day) only dedupe unsent candidates.

    The key holds the upstream ID without a source prefix: 0.3.x notices never recorded a source_id,
    and v2 notices must still match migrated history for the same item.
    """
    found = upstream(item_id) if item_id else None
    for ref in sources or ():
        if found:
            break
        if any(p.match(str(ref).strip()) for p in REFS) or re.match(r"^https?://", str(ref).strip(), re.I):
            found = upstream(ref)
    if found:
        return "src:" + found, True
    words = re.sub(r"[\W_]+", " ", str(title).lower()).split()
    day = datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts is not None else ""
    return "weak:" + hashlib.sha256(f"{' '.join(words)}|{day}".encode()).hexdigest()[:24], False


def signal_key(session_id, turn_id):
    return turn_id if str(turn_id).startswith(f"{session_id}:") else f"{session_id}:{turn_id}"


def title_key(title):
    """Interest/idea natural key: the casefolded, whitespace-normalized title."""
    return hashlib.sha256(" ".join(str(title).casefold().split()).encode()).hexdigest()[:16]
