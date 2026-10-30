"""rollback-bridge: write v2 facts back into the v1 state.db before reinstalling 0.3.1 / 0.3.16 (design 7.4).

- v2 notices: the v1 row of a migrated notice takes the v2 outcome; a notice sent under v2 becomes a
  v1 `sent` row whose event_key and sources carry the notice key.
- cursor(memory-upkeep) moves to the end of the continuous prefix that v2 disposed or parked; settled
  signals beyond it move to kind `v2_settled_signal`, which neither 0.3.1 (cursor only) nor 0.3.16 reads,
  so no version processes them twice. Signals still new in v2 are handed back to v1 unprocessed.
- cursor(proactive-watch) = now; source_check.last_success takes the newer v2 watermark.
Goals need nothing: GOAL.md is shared. Idempotent; --dry-run works on a scratch copy.
"""
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from itertools import groupby
from pathlib import Path

from .migrate import background
from .store import Store

V1_STATUS = {"sent": "sent", "sending": "unknown", "unknown": "unknown", "closed_unknown": "unknown", "failed": "failed",
             "withdrawn": "cancelled", "superseded": "cancelled", "expired": "expired"}  # drafted/scheduled: leave as is
SETTLED = ("disposed", "parked")


@contextmanager
def v1_lock(muse):
    from ...locks import file_lock

    with file_lock(muse / "mutations.lock"):
        yield


def bridge(home, *, dry_run=False, now=None):
    # Canonicalize the profile root like HostAdapter (macOS /var is an alias).
    home = Path(home).resolve()
    if dry_run:
        with tempfile.TemporaryDirectory(prefix="muse-bridge-dry-") as scratch:
            (Path(scratch) / "muse").mkdir()
            for name in ("state.db", "state-v2.db"):
                shutil.copy2(home / "muse" / name, Path(scratch) / "muse" / name)
            (Path(scratch) / "muse" / "state.db").chmod(0o600)
            return {**bridge(scratch, now=now), "dry_run": True}
    v2 = Store.for_home(home, readonly=True)
    if not v2.meta("migration"):
        raise ValueError("state-v2.db has no migration record; nothing to bridge")
    now = time.time() if now is None else float(now)
    v1_path = home / "muse" / "state.db"
    v1_path.chmod(0o600)
    changes = Counter()
    with v1_lock(home / "muse"):
        db = sqlite3.connect(v1_path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("BEGIN IMMEDIATE")
            _notices(db, v2, now, changes)
            _signals(db, v2, changes)
            put(db, "cursor", "proactive-watch", now)
            _sources(db, v2, changes)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    return {"bridged": dict(sorted(changes.items())), "at": now}


def get(db, kind, key):
    row = db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
    return json.loads(row[0]) if row else None


def put(db, kind, key, value, *, revise=False):
    if revise:  # 0.3.x Store.put bumps _revision for these kinds so notice/source cursors see the change
        value["_revision"] = (get(db, kind, key) or {}).get("_revision", 0) + 1
        value.pop("_request_id", None)
    db.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
               (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False)))


def _notices(db, v2, now, changes):
    for notice in v2.query("notice"):
        status, p = V1_STATUS.get(notice["state"]), notice["payload"]
        if not status:
            continue
        row = get(db, "notification", p["v1_id"]) if p.get("v1_id") else None
        if row:
            if row["status"] != status and row["status"] != "sent":
                row["status"] = status
                put(db, "notification", row["id"], row, revise=True)
                changes[f"notice_v1_{status}"] += 1
            continue
        if status != "sent":
            continue  # v2-only notices that never reached the user need no v1 history
        event_key = f"{notice['natural_key']}|{p.get('event_key') or notice['id']}"[:500]
        key = hashlib.sha256(event_key.encode()).hexdigest()[:24]
        if get(db, "notification", key):
            continue
        sent_at = p.get("dispatched_at") or notice["state_since"]
        put(db, "notification", key, {
            "id": key, "event_key": event_key, "issue_key": notice["natural_key"],
            "message": p.get("message") or p.get("text") or "", "rationale": p.get("rationale") or "Sent by Muse v2",
            "sources": list(dict.fromkeys([*(p.get("sources") or []), notice["natural_key"]])),
            "verified_at": p.get("verified_at") or sent_at, "expires": p.get("expires") or sent_at, "created": p.get("created") or sent_at,
            "priority": p.get("priority") or "ordinary", "topic": p.get("topic") or "", "goal_id": p.get("goal_id"),
            "interest_id": p.get("interest_id"), "final_result": False, "status": "sent", "not_before": sent_at,
            "session_id": p.get("session_id"), "job_id": None, "dispatched_at": sent_at,
            "delivery_note": "Written back by the v2 rollback bridge."}, revise=True)
        changes["notice_v1_sent_added"] += 1


def _signals(db, v2, changes):
    rows = {key: json.loads(data) for key, data in db.execute("SELECT id, data FROM records WHERE kind='signal'")}
    settled = set()
    for signal in v2.query("signal"):
        p = signal["payload"]
        # v2 intake signals point by {"ref"}; their natural key is a unique v1 id (v1 only orders by created).
        key = p.get("pointer", {}).get("turn_id") or p.get("v1_id") or signal["natural_key"]
        if signal["state"] in SETTLED:
            settled.add(key)
        elif key not in rows:  # captured under v2 and not yet handled: give it back to v1 rather than lose it
            rows[key] = {"id": key, "session_id": p["session_id"], "text": p.get("excerpt", ""),
                         "created": p["created"], "truncated": bool(p.get("truncated"))}
            put(db, "signal", key, rows[key])
            changes["signal_v1_added_unprocessed"] += 1
    old = get(db, "cursor", "memory-upkeep") or 0
    cursor = old
    live = sorted((r for r in rows.values() if not background(r.get("text"))), key=lambda r: (r["created"], r["id"]))
    for at, group in groupby((r for r in live if r["created"] > old), key=lambda r: r["created"]):
        if any(r["id"] not in settled for r in group):
            break
        cursor = at
    if cursor != old:
        put(db, "cursor", "memory-upkeep", cursor)
        changes["cursor_memory_upkeep_advanced"] += 1
    for key in settled:
        row = rows.get(key)
        if row and row["created"] > cursor:
            db.execute("DELETE FROM records WHERE kind='signal' AND id=?", (key,))
            put(db, "v2_settled_signal", key, row)
            changes["signal_set_aside"] += 1


def _sources(db, v2, changes):
    for source in v2.query("source"):
        row, mark = get(db, "source_check", source["natural_key"]), source["payload"].get("last_success")
        if row and mark and mark > row.get("last_success", 0):
            row.update(last_success=mark, cursor=source["payload"].get("cursor"))
            put(db, "source_check", row["id"], row, revise=True)
            changes["source_watermark_advanced"] += 1
