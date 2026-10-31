"""Packets: bounded work packets per job and period, with code-filled refs, result schema and budget.

build(job) -> {id, type, items, schema, budget[, context]}. While a packet of the job is issued, every caller
gets that same packet; an empty intake/nightly/feed packet is not stored (id None) and the caller stays silent.
Patrol always gets a packet: only the model can read its sources.
A batch holds the job's fixed item count, fewer when its excerpts would pass EXCERPT_TOTAL chars.
Drain jobs (intake, nightly, feed) work their whole queue within one period in batches `<job>:<period>[:<batch>]`
(lease min(period, 2h)); a ref offered in a submitted batch is not offered again that period, the refs of an
expired batch are, and so are the unanswered refs of a batch whose run failed (close); runs.relay wakes the job
again while work remains. Work arriving after the last batch waits for the next wake or period.
read/observe/submit accept only refs that belong to the packet (trust boundary).
"""
import hashlib
import json

from . import goals, intake, notifier, records, review, sources, upkeep
from .common import D, H, clip, one, patch, preferences
from .store import keys, notice_key

EXCERPT_TOTAL = 24000
READ_MAX, READ_TOTAL = 12000, 24000
OBSERVE_MAX = 50
SOURCES_DUE = 20  # per patrol packet, least recently checked first, so a longer list rotates
JOBS = {  # cron period, packet lease, fixed items per packet (a batch when draining)
    "intake": {"type": "intake", "period": H, "lease": H, "items": 15, "drain": True},
    "patrol": {"type": "patrol", "period": 30 * 60, "lease": 30 * 60, "items": 8},
    "nightly": {"type": "nightly", "period": D, "lease": 2 * H, "items": 10, "drain": True},
    "feed": {"type": "feed", "period": D, "lease": 2 * H, "items": 3, "drain": True},
}
PROPOSE_WITHIN = 7 * D
CHECK_GAP = 20 * H  # an interest is researched at most once a day
FEED_NOTICES, FEED_PRIORITIES = 1, ("ordinary", "time_sensitive")


def obj(required, **properties):
    return {"type": "object", "required": list(required), "properties": properties, "additionalProperties": False}


def enum(*values):
    return {"type": "string", "enum": list(values)}


S, REF = {"type": "string"}, {"type": "string", "description": "a ref from this packet"}
SCHEMAS = {  # design 2.6: one result shape per item kind group
    "intake": obj(["ref", "disposition"], ref=REF, disposition=enum(*intake.DISPOSITIONS),
                  facts={"type": "array", "items": S, "maxItems": 20},
                  goal_hint={"type": "string", "description": "an open goal id, or 'new' to propose a goal"}),
    "patrol": obj(["candidate_ref", "verdict"], candidate_ref=REF, verdict=enum(*notifier.VERDICTS),
                  text={"type": "string", "maxLength": notifier.TEXT_MAX}, priority=enum(*notifier.PRIORITIES),
                  topic={"type": "string", "maxLength": 100,
                         "description": "short topic label; the exact context.blocked_topics entry when the item is about one"},
                  about={"type": "string", "description": "a context.notified ref: the notified event this item is about"}),
    "goals": obj([], goal_id=REF, assessment=enum(*goals.ASSESSMENTS), progress_note=S,
                 create=obj(["signal_ref", "title", "criteria"], signal_ref=REF, title=S, criteria=S),
                 decline=obj(["signal_ref", "reason"], signal_ref=REF, reason={"type": "string", "maxLength": 500})),
    "review": obj(["candidate_ref", "verdict", "reason"], candidate_ref=REF, verdict=enum(*review.VERDICTS),
                  reason={"type": "string", "maxLength": 500}),
    "feed": obj(["interest_ref"], interest_ref=REF,
                article=obj(["title", "body", "source_refs"], title=S, body=S, source_refs={"type": "array", "items": S, "minItems": 1}),
                notice=obj(["text", "source_ref"], text={"type": "string", "maxLength": notifier.TEXT_MAX},
                           source_ref={"type": "string", "description": "one of this result's article.source_refs"},
                           priority=enum(*FEED_PRIORITIES), topic={"type": "string", "maxLength": 100})),
}
KIND_SCHEMA = {"intake": "intake", "observed": "patrol", "notice": "patrol", "goal": "goals", "signal": "goals",
               "review": "review", "interest": "feed"}
TYPE_SCHEMAS = {"intake": ("intake",), "patrol": ("patrol",), "nightly": ("goals", "review"), "feed": ("feed",)}


# -- builders: (items, context) ----------------------------------------------------------------------
def intake_items(k, n, now, offered):
    """New signals not offered this period, oldest first."""
    rows = sorted((e for e in k.store.query("signal", state="new") if e["natural_key"] not in offered),
                  key=lambda e: (e["payload"].get("created") or 0, e["id"]))
    return [intake.item(e) for e in rows], {}


def patrol_items(k, n, now, offered):
    recent = [{"at": t["at"], "text": clip(t["text"], 500)} for t in k.adapter.sessions.user_turns(now - 6 * H)][-5:]
    return notifier.due_items(k, now), {
        "sources_due": sources.due(k.store, now, k.settings().get("source_intervals"))[:SOURCES_DUE],
        "notified": notifier.recent(k.store, now),
        "recent_user_messages": recent, "send_limit": n, "blocked_topics": blocked_topics(k)}


def blocked_topics(k):
    try:
        return preferences(k.home)["blocked_topics"]
    except ValueError:  # invalid preferences hold every notice anyway (notifier); the patrol still runs
        return []


def nightly_items(k, n, now, offered):
    """The whole queue, obligations first: due goals (earliest first), goal proposals (no more than cron may still
    create today; the rest wait for the next period), then review candidates."""
    due = [goals.item(k, e) for e in k.store.due(now, kind="goal") if e["natural_key"] not in offered]
    proposals = [{**intake.item(e), "kind": "signal", "facts": e["payload"].get("facts", [])}
                 for e in reversed(k.store.query("signal", state="disposed", since=now - PROPOSE_WITHIN))
                 if e["payload"].get("goal_hint") == "new" and not e["payload"].get("proposed_at")
                 and not goals.read(k.home, goals.slug_for(e["natural_key"]))][:goals.cron_creates_left(k, now)]
    return due + proposals + review.candidates(k, now, skip=offered), {"memory_changes": upkeep.unreported(k, now)}


def feed_items(k, n, now, offered):
    """Active interests not researched for CHECK_GAP, longest unchecked first."""
    rows = sorted((e for e in k.store.query("interest", state="active")
                   if e["id"] not in offered and (e["payload"].get("checked_at") or 0) <= now - CHECK_GAP),
                  key=lambda e: (e["payload"].get("checked_at") or 0, e["state_since"]))
    return [{"kind": "interest", "ref": e["id"], "title": e["payload"].get("title"), "rationale": e["payload"].get("rationale")}
            for e in rows], {"blocked_topics": blocked_topics(k), "notice_limit": FEED_NOTICES}


BUILDERS = {"intake": intake_items, "patrol": patrol_items, "nightly": nightly_items, "feed": feed_items}


def empty(items, context):
    return not items and not (context or {}).get("memory_changes")


def view(e, spec):
    p = e["payload"]
    out = {"id": e["id"], "type": spec["type"], "items": p["items"],
           "schema": {name: SCHEMAS[name] for name in TYPE_SCHEMAS[spec["type"]]}, "budget": p["budget"]}
    return {**out, "context": p["context"]} if p.get("context") else out


def take(queue, n):
    """The first n items whose excerpts fit EXCERPT_TOTAL chars (at least one)."""
    items, chars = [], 0
    for i in queue:
        chars += len(i.get("excerpt", ""))
        if items and (len(items) >= n or chars > EXCERPT_TOTAL):
            break
        items.append(i)
    return items


def batches(k, job, now):
    """(base key, this period's packets of a drain job)."""
    spec = JOBS[job]
    period = int(now // spec["period"])
    return f"{job}:{period}", [p for p in k.store.query("packet", since=period * spec["period"])
                               if p["natural_key"].split(":")[:2] == [job, str(period)]]


def plan(k, job, now):
    """(issued packet or None, key, batch size, items, context) of the job's next packet."""
    spec = JOBS[job]
    if not spec.get("drain"):
        key = f"{job}:{int(now // spec['period'])}"
        issued = k.store.query("packet", state="issued", natural_key=key, limit=1)
        if issued:
            return issued[0], key, None, None, None
        n = spec["items"]
        return None, key, n, *BUILDERS[job](k, n, now, frozenset())
    key, batch = batches(k, job, now)
    issued = next((p for p in batch if p["state"] == "issued"), None)
    if issued:
        return issued, key, None, None, None
    offered = frozenset(ref for p in batch if p["state"] == "submitted" for ref in (
        p["payload"]["handled"] if p["payload"].get("released") else [i["ref"] for i in p["payload"]["items"]]))
    n = spec["items"]
    queue, context = BUILDERS[job](k, n, now, offered)
    items = take(queue, n)
    return None, f"{key}:{len(batch)}" if batch else key, n, items, {**context, "remaining": len(queue) - len(items)}


def pending(k, job, now):
    """True when a drain job has work left this period and no batch is out."""
    issued, _, _, items, context = plan(k, job, now)
    return not issued and not empty(items, context)


def stalls(k, job, now):
    """This period's batches in a row, latest first, that handled no item."""
    _, batch = batches(k, job, now)
    n = 0
    for p in sorted(batch, key=lambda p: p["payload"]["issued_at"], reverse=True):
        if p["payload"].get("handled"):
            break
        n += 1
    return n


def close(k, packet_id, outcome, now):
    """The run of a drain batch closed. ok/degraded consumes the batch: its handled (created or declined) proposals
    count as made and, on the last batch, its memory changes as reported. failed/abandoned releases its unanswered
    refs. A batch still issued expires."""
    e = k.store.get(packet_id)
    p, done = e["payload"], outcome in ("ok", "degraded")
    context = p.get("context") or {}  # a packet issued by 0.4.0 may have none
    if done and (e["state"] == "submitted" or not p["items"]):
        for i in p["items"]:  # an unanswered proposal comes back next period
            if i["kind"] == "signal" and i["ref"] in p["handled"]:
                patch(k.store, one(k.store, "signal", i["ref"])["id"], reason="nightly:proposed",
                      payload=lambda s: {"proposed_at": s["payload"].get("proposed_at") or now}, now=now)
        if not context.get("remaining"):
            upkeep.reported(k, context.get("memory_changes"))
    elif e["state"] == "submitted":
        patch(k.store, packet_id, expect=("submitted",), reason=f"run:{outcome}", payload={"released": True}, now=now)
    patch(k.store, packet_id, "expired", expect=("issued",), reason=f"run:{outcome}", now=now)


def build(k, job, now):
    if job not in JOBS:
        raise ValueError(f"job must be one of {', '.join(JOBS)}")
    spec, store = JOBS[job], k.store
    issued, key, n, items, context = plan(k, job, now)
    if issued:
        return view(issued, spec)
    budget = {"items": n, "excerpt_chars": EXCERPT_TOTAL,
              "read_chars": READ_MAX, "read_total_per_item": READ_TOTAL, "lease_until": now + spec["lease"]}
    if empty(items, context) and job != "patrol":
        return {"id": None, "type": spec["type"], "items": [], "schema": {}, "budget": budget}
    if job == "intake" and (full := upkeep.full(k, now)):  # counts an ask, so only for a packet being issued
        context = {**context, "memory_full": full}
    with store.atomic():
        e = store.create("packet", key, {"job": job, "type": spec["type"], "items": items, "context": context,
                                         "budget": budget, "observed": [], "reads": {}, "handled": [], "issued_at": now},
                         deadline=now + spec["lease"], now=now, dedupe=(frozenset({"issued"}), None))
        if not e["existing"]:
            store.attempt([store.query("signal", natural_key=i["ref"], limit=1)[0]["id"] for i in items if i["kind"] == "intake"], now)
    return view(e, spec)


def packet_of(k, packet_id):
    e = k.store.get(packet_id) if packet_id else None
    if not e or e["kind"] != "packet":
        raise KeyError(f"unknown packet {packet_id!r}")
    return e


def read(k, packet_id, ref, offset=0, now=None):
    """At most 12k redacted chars per call and 24k per item per packet of one item's original text."""
    packet = packet_of(k, packet_id)
    item = next((i for i in packet["payload"]["items"] if i["ref"] == ref), None)
    if item is None or not item.get("pointer"):
        raise KeyError(f"{ref!r} has no original text in this packet")
    allowed = min(READ_MAX, READ_TOTAL - packet["payload"]["reads"].get(ref, 0))
    if allowed <= 0:
        return {"ref": ref, "available": False, "reason": "read budget for this item is spent; dispose it from its excerpt"}
    page = k.adapter.sessions.read(item["pointer"], offset, allowed)
    used = len(page.get("text") or "")
    patch(k.store, packet["id"], reason="read", now=now,
          payload=lambda e: {"reads": {**e["payload"]["reads"], ref: e["payload"]["reads"].get(ref, 0) + used}})
    return {**page, "ref": ref}


def observe(k, packet_id, source_id, items, limitation_code=None, error=None, now=None):
    """Record a source check and its items (upstream IDs from the model) under packet refs o1, o2, …"""
    packet = packet_of(k, packet_id)
    if packet["payload"]["type"] != "patrol":
        raise ValueError("observe belongs to a patrol packet")
    if not isinstance(items, list) or len(items) > OBSERVE_MAX:
        raise ValueError(f"items must be a list of at most {OBSERVE_MAX}")
    source_id = sources.check_id(source_id)
    clean = []
    for raw in items:
        title = str((raw or {}).get("title") or "").strip()[:300]
        if not title:
            raise ValueError("every item needs a title")
        ts = raw.get("ts")
        clean.append({"kind": "observed", "source_id": source_id, "title": title,
                      "upstream_id": str(raw["upstream_id"])[:500] if raw.get("upstream_id") else None,
                      "url": str(raw["url"])[:1000] if raw.get("url") else None,
                      "ts": float(ts) if type(ts) in (int, float) else None})
    state = sources.record(k.store, source_id, limitation_code=limitation_code, error=error, now=now)
    out = []
    with k.store.atomic():
        observed = list(k.store.get(packet["id"])["payload"]["observed"])
        for item in clean:
            item["ref"] = f"o{len(observed) + 1}"
            key, _ = notice_key(item["upstream_id"], [item["url"]] if item["url"] else [], item["title"], item["ts"] or now)
            known = notifier.known(k.store, key, now)
            observed.append(item)
            out.append({"ref": item["ref"], "notified": known and {"ref": known["id"], "state": known["state"]}})
        patch(k.store, packet["id"], reason="observe", payload={"observed": observed}, now=now)
    return {"source": {"id": source_id, "state": state["state"], "gap": state["payload"].get("gap")}, "items": out}


# -- submit ------------------------------------------------------------------------------------------
def feed_result(k, item, r, now):
    """Every answered interest counts as checked; an article becomes a FeedItem, and its one optional notice
    goes through the Notifier with the article as evidence."""
    article, notice = r.get("article"), r.get("notice")
    if not article:
        if notice:
            raise ValueError("a notice needs the article it comes from")
        patch(k.store, item["ref"], reason="feed:checked", payload={"checked_at": now}, now=now)
        return {"result": "no_article"}
    title, body = str(article.get("title") or "").strip()[:200], str(article.get("body") or "").strip()
    refs = sorted({str(s)[:1000] for s in article.get("source_refs") or [] if s})
    if not title or not body or not refs:
        raise ValueError("article needs title, body and source_refs")
    if notice and notice.get("source_ref") not in refs:
        raise ValueError("notice.source_ref must be one of article.source_refs")
    if notice and (notice.get("priority") or "ordinary") not in FEED_PRIORITIES:
        raise ValueError(f"notice.priority must be one of {', '.join(FEED_PRIORITIES)}")
    if notice and notice.get("topic") == notifier.FADE_TOPIC:
        raise ValueError(f"topic {notifier.FADE_TOPIC!r} is reserved for Muse's dormancy questions")
    patch(k.store, item["ref"], reason="feed:checked", payload={"checked_at": now}, now=now)
    key = hashlib.sha256(json.dumps(refs, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:24]
    e = k.store.create("feed", key, {"title": title, "interest_id": item["ref"], "sources": refs, "created": now}, now=now)
    path = records.feed_path(e) if e["existing"] else records.write_feed(k, e, {"title": title, "body": body, "source_refs": refs})
    out = {"result": "existing" if e["existing"] else "recorded", "feed": e["id"], "path": path}
    if notice:
        # patrol may have notified about the same page already: any source of the article counts
        known = next(filter(None, (notifier.known(k.store, keys.notice_key(s)[0], now) for s in refs)), None)
        n = known and {**known, "existing": True} or notifier.draft(
            k, text=notice.get("text"), priority=notice.get("priority") or "ordinary", title=title,
            upstream_id=notice["source_ref"], sources=refs, topic=str(notice.get("topic") or "").strip()[:100],
            evidence=[e["id"]], interest_id=item["ref"], now=now)
        out["notice"] = {"result": "existing" if n["existing"] else "drafted", "id": n["id"], "state": n["state"]}
    return out


HANDLERS = {
    "intake": lambda k, i, r, now: {"state": intake.dispose(k, i["ref"], r.get("disposition"), r.get("facts"), r.get("goal_hint"), now)["state"]},
    "observed": lambda k, i, r, now: notifier.decide(k, i, r.get("verdict"), text=r.get("text"), priority=r.get("priority"),
                                                     topic=r.get("topic"), about=r.get("about"), now=now),
    "notice": lambda k, i, r, now: notifier.decide(k, i, r.get("verdict"), text=r.get("text"), priority=r.get("priority"), now=now),
    "goal": lambda k, i, r, now: goals.assess(k, i["ref"], r.get("assessment"), r.get("progress_note"), now),
    "signal": lambda k, i, r, now: {"result": "declined"} if r.get("decline") and not r.get("create") else goals.create(k, title=(r.get("create") or {}).get("title"),
                                                criteria=(r.get("create") or {}).get("criteria"), signal_ref=i["ref"], now=now),
    "review": lambda k, i, r, now: review.record(k, i["ref"], r.get("verdict"), r.get("reason"), now, i.get("rules", ())),
    "interest": feed_result,
}
REF_FIELDS = ("ref", "candidate_ref", "goal_id", "interest_ref")


def submit(k, packet_id, results, now):
    """Apply results item by item (idempotent); unhandled items stay in their queues with the attempt counted."""
    packet = packet_of(k, packet_id)
    if not isinstance(results, list) or len(results) > 100:
        raise ValueError("results must be a list of at most 100")
    p = packet["payload"]
    items = {i["ref"]: i for i in [*p["items"], *k.store.get(packet["id"])["payload"]["observed"]]}
    out, handled, sends, notices = [], [], 0, 0
    for r in results:
        r = r if isinstance(r, dict) else {}
        ref = next((r[f] for f in REF_FIELDS if r.get(f)), None) or (r.get("create") or r.get("decline") or {}).get("signal_ref")
        try:
            item = items.get(ref)
            if item is None:
                raise KeyError(f"{ref!r} is not in this packet")
            if r.get("about") and r["about"] not in {e["ref"] for e in (p.get("context") or {}).get("notified", ())}:
                raise KeyError(f"about {r['about']!r} is not a context.notified ref of this packet")
            if item["kind"] == "observed" and r.get("verdict") in ("send", "supersede"):
                sends += 1
                if sends > p["budget"]["items"]:
                    raise ValueError(f"at most {p['budget']['items']} notices per patrol packet")
            if item["kind"] == "interest" and r.get("notice"):
                notices += 1
                if notices > FEED_NOTICES:
                    raise ValueError(f"at most {FEED_NOTICES} notice per feed packet")
            out.append({"ref": ref, **HANDLERS[item["kind"]](k, item, r, now)})
            handled.append(ref)
        except (ValueError, KeyError, PermissionError) as exc:
            out.append({"ref": ref, "error": str(exc.args[0] if exc.args else exc)})

    def done(e):
        total = sorted(set(e["payload"]["handled"]) | set(handled))
        return {"handled": total, "submitted_at": e["payload"].get("submitted_at", now)}
    if not patch(k.store, packet["id"], "submitted", expect=("issued",), reason="submit", payload=done, now=now):
        patch(k.store, packet["id"], reason="submit", payload=done, now=now)  # a late or repeated submit on an expired/submitted packet
    return out
