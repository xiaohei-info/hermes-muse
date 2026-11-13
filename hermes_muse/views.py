"""Read-only dashboard views of one profile: Feed, ideas, goals, recent runs and open review findings from Store v2
and the content files.

Opens state-v2.db read-only and never repairs or writes. Lists page by a plain offset cursor; an article
or goal body pages by offset and is pinned to the revision of its first page.
"""
import time
from collections import Counter
from pathlib import Path

from .content_io import Files, revision
from .kernel import goals
from .kernel.common import D, clip
from .kernel.records import FEED_DIR
from .kernel.store import Store

BODY_MAX = 24000
RUN_DAYS = 7  # runs listed: those that started or ended in this window
FOUND = 5  # observed source items named per run
SUMMARY = ("title", "status", "created", "updated", "goal_id", "interest_id", "why", "rationale", "deadline",
           "next_check_at", "waiting_user", "blocked", "no_fade")


class NotFound(LookupError):
    pass


def summary(entity_id, record):
    out = {"id": entity_id, **{k: record[k] for k in SUMMARY if record.get(k) is not None}}
    if isinstance(record.get("sources"), list):
        out["source_count"] = len(record["sources"])
    if record.get("progress"):
        out["latest_progress"] = dict(record["progress"][-1])
    return {k: v[:512] if isinstance(v, str) else v for k, v in out.items()}


def run_summary(store, e):
    """What one run was given and did, from its packet: item kinds, items handled, source items observed."""
    p, events = e["payload"], store.events(e["id"])
    out = {"id": e["id"], "job": p.get("job"), "state": e["state"], "started": events[0]["at"] if events else None,
           "ended": None if e["state"] == "running" else e["state_since"]}
    packet = store.get(p["packet_id"]) if p.get("packet_id") else None
    if packet:
        pp = packet["payload"]
        observed = pp.get("observed") or []
        out.update(items=len(pp.get("items") or []), item_kinds=dict(Counter(i.get("kind") for i in pp.get("items") or [])),
                   handled=len(pp.get("handled") or []), observed=len(observed),
                   found=[clip(str(o.get("title") or ""), 160) for o in observed[:FOUND] if o.get("title")])
    return out


def page(items, cursor, limit):
    offset = int(cursor) if str(cursor or "").isdigit() else 0
    end = offset + max(1, min(int(limit), 100))
    return {"items": items[offset:end], "next_cursor": str(end) if end < len(items) else None,
            "complete": end >= len(items), "total": len(items)}


class Views:
    def __init__(self, home):
        self.home = Path(home)
        self.files = Files(self.home)

    def store(self):
        path = self.home / "muse" / "state-v2.db"
        return Store(path, readonly=True) if path.is_file() else None

    def entities(self, kind, state):
        store = self.store()
        return store.query(kind, state=state) if store else []

    def feed_path(self, e):
        return e["payload"].get("path") or f"{FEED_DIR}/{e['natural_key']}.md"

    def feed_body(self, e):
        try:
            return self.files.read(self.feed_path(e))
        except FileNotFoundError:
            return b""

    def goal_records(self):
        found = (goals.read(self.home, slug) for slug in self.files.names(goals.ROOT))
        return [f for f in found if f]

    # -- lists ---------------------------------------------------------------------------------------
    def feed(self, query=None, topic=None, cursor=None, limit=25):
        items = []
        for e in self.entities("feed", "published"):
            p = e["payload"]
            if topic and topic not in (p.get("goal_id"), p.get("interest_id")):
                continue
            if query and query.casefold() not in (str(p.get("title")) + " " + self.feed_body(e).decode("utf-8", "replace")).casefold():
                continue
            items.append(summary(e["id"], p))
        items.sort(key=lambda r: (-(r.get("created") or 0), r["id"]))
        return page(items, cursor, limit)

    def ideas(self, cursor=None, limit=25):
        items = sorted((summary(e["id"], e["payload"]) for e in self.entities("idea", "active")),
                       key=lambda r: (-(r.get("created") or 0), r["id"]))
        return page(items, cursor, limit)

    def goals(self, status=None, cursor=None, limit=25):
        rows = []
        for record, _, _ in self.goal_records():
            if status and (record.get("status") == "active") != (status == "open"):
                continue
            rows.append(summary(record["id"], record))

        def order(r):  # needs you, blocked, in progress; closed last, newest first
            if r.get("status") != "active":
                return (3, -(r.get("updated") or 0), r["id"])
            return (0 if r.get("waiting_user") else 1 if r.get("blocked") else 2, r.get("next_check_at") or 0, r["id"])
        return page(sorted(rows, key=order), cursor, limit)

    def runs(self, cursor=None, limit=25, now=None):
        """Job runs of the last RUN_DAYS, newest first. A run is recorded only when its job had work (a packet); the
        outcome is computed by code from the host's execution status and the packet's dispositions."""
        store = self.store()
        if store is None:
            return {**page([], cursor, limit), "days": RUN_DAYS}
        now = time.time() if now is None else now
        listed = page(store.query("run", since=now - RUN_DAYS * D), cursor, limit)
        return {**listed, "days": RUN_DAYS, "items": [run_summary(store, e) for e in listed["items"]]}

    def findings(self, cursor=None, limit=25):
        """Open conversation-review findings, newest first; the user resolves or dismisses one in chat (feedback)."""
        items = []
        for e in self.entities("finding", "open"):
            p = e["payload"]
            items.append({"id": e["id"], "kind": "finding", "title": clip(p.get("reason") or "", 512),
                          "verdict": p.get("verdict"), "tag": p.get("tag"), "turn": p.get("turn"),
                          "rules": [r[5:] for r in p.get("evidence", ()) if str(r).startswith("rule:")],
                          "created": e["state_since"], "expires": e["deadline"]})
        items.sort(key=lambda r: (-(r["created"] or 0), r["id"]))
        return page(items, cursor, limit)

    # -- one object ----------------------------------------------------------------------------------
    def article(self, kind, object_id, offset=0, length=12000, pinned=None):
        if kind == "feed":
            e = next((e for e in self.entities("feed", "published") if e["id"] == object_id), None)
            if e is None:
                raise NotFound(f"no Feed article {object_id!r}")
            raw, metadata = self.feed_body(e), e["payload"]
        elif kind == "goal":
            found = goals.read(self.home, object_id) if "/" not in str(object_id) else None
            if not found:
                raise NotFound(f"no goal {object_id!r}")
            metadata, raw = found[0], found[1].encode()
        else:
            raise NotFound(f"no {kind} view")
        current = revision(raw)
        if offset and pinned != current:
            raise ValueError("content changed since the first page; reopen it")
        body = raw.decode("utf-8", "replace")
        end = offset + max(1, min(int(length), BODY_MAX))
        return {"kind": kind, "id": object_id, "revision": current, "metadata": metadata, "body": body[offset:end],
                "total_chars": len(body), "next_offset": end if end < len(body) else None, "complete": end >= len(body)}
