"""Goals: GOAL.md (managed header + body) is the source of truth; Store v2 keeps an index mirror holding
the file revision. Every write is a file CAS under mutations.lock and refreshes the mirror.

Code owns the clock: any touch moves next_check to now + 1 day (a nightly assessment to now + 1 day - 6h, so
the goal is due again the next night). Activity (`activity`) is a move by the user or an executor; Muse's own writes
(nightly assessments, fade, forwarding an event) are not, so a goal assessed every night still goes dormant. Dormancy
(no activity for goal_dormant_days) asks one question per episode under `goal:<id>:fade:<episode>:<attempt>`; a
withdrawn, expired or failed question is asked again (attempt + 1, at most 3); goal_fade_days after the question was
really delivered, code cancels the goal, and goal_update(status=active) revives it. Status changes otherwise come only
from the user (main session) and, for a goal a rule made, its assignments; cron appends progress and assessments.
A `done_suggested` assessment needs evidence and becomes a question to the user, not just a record.
"""
import hashlib
import time
from datetime import datetime

from ..content_io import Files, revision
from ..locks import file_lock
from . import notifier
from .common import D, count_today, header, local_day, one, patch, preferences, render
from .sources import classify
from .store import machine

ROOT = "workspace/goals"
CHECK_EVERY = D
NIGHT_SLACK = 6 * 3600
MAX_ASKS = 3
CRON_CREATES_PER_DAY = 5
WATCH_RENEW = 30 * D
OPEN = ("active", "waiting")
CLOSED_ASK = ("withdrawn", "expired", "failed", "closed_unknown", "superseded")
ASSESSMENTS = ("on_track", "stalled", "blocked", "done_suggested")
USER_FIELDS = {"title", "status", "waiting_user", "deadline", "no_fade", "owner", "next_check_at", "progress_note", "evidence"}
CRON_FIELDS = {"progress_note", "assessment"}
# by -> (fields, statuses it may set); anyone else appends progress and assessments only
WRITERS = {"user": (USER_FIELDS, ("active", "done", "cancelled")), "fade": (CRON_FIELDS | {"status"}, ("cancelled",)),
           "executor": ({"status", "evidence", "progress_note"}, ("active", "done"))}
ACTIVITY = ("user", "kernel", "executor")  # kernel: a user message about this goal (intake's goal_hint)
FADE_ASKS_PER_DAY = 3  # so an upgrade that finds many dormant goals asks gradually; the cancel clock starts on delivery
DONE_TOPIC = "goal-done"
ASK = "The goal “{title}” has had no progress for {days} days. Do you still want it?"
CLOSES = " If I don't hear from you, I'll close it after {date}."


def state_of(record):
    status = record.get("status")
    if status == "active":
        return "waiting" if record.get("waiting_user") else "active"
    return status if status in ("done", "cancelled") else None


def read(home, slug):
    """(record, body, file revision) or None for a missing or unmanaged goal."""
    try:
        raw = Files(home).read(f"{ROOT}/{slug}/GOAL.md")
    except FileNotFoundError:
        return None
    text = raw.decode("utf-8").replace("\r\n", "\n")
    record = header(text)
    if not record or record.get("id") != slug:
        return None
    return record, text.partition("\n")[2], revision(raw)


def mirror(k, slug, record, file_revision, now, reason):
    state = state_of(record)
    if state is None:
        return None
    payload = {"revision": file_revision, **{f: record.get(f) for f in (
        "title", "session_id", "parent_id", "deadline", "no_fade", "owner", "created", "updated", "next_check_at",
        "thread_key", "rule", "evidence")}}
    deadline = (record.get("next_check_at") or now) if state in OPEN else None
    store = k.store
    with store.atomic():
        e = store.create("goal", slug, payload, state=state, deadline=deadline, id=f"goal:{slug}", now=now, reason=reason)
        if e["existing"] and (e["payload"].get("revision") != file_revision or e["state"] != state):
            if e["state"] != state and (e["state"], state) not in machine("goal").edges:  # e.g. done -> waiting
                e = store.transition(e["id"], "active", state=e["state"], version=e["version"], reason=reason,
                                     deadline=deadline or now, now=now)
            e = store.transition(e["id"], state, state=e["state"], version=e["version"], reason=reason,
                                 payload=payload, deadline=deadline, now=now)
    return e


def write(k, slug, mutate, *, reason, now, create=False):
    """mutate(record, body) -> (record, body) under the file CAS; returns the written record."""
    with file_lock(k.home / "muse" / "mutations.lock"):
        current = read(k.home, slug)
        if create == bool(current):
            raise (ValueError(f"goal {slug} already exists") if current else KeyError(f"unknown goal {slug!r}"))
        record, body = mutate(dict(current[0]) if current else {}, current[1] if current else "")
        record.update(updated=now, revision=int(record.get("revision") or 0) + 1)
        raw = render(record, body)
        Files(k.home).replace(f"{ROOT}/{slug}/GOAL.md", raw, current[2] if current else "absent")
        mirror(k, slug, record, revision(raw), now, reason)
    return record


def sync(k, now):
    """Refresh the mirror from GOAL.md files (edits by the user, another version or a rollback)."""
    seen, changed = set(), 0
    for slug in Files(k.home).names(ROOT):
        try:
            found = read(k.home, slug)
        except (ValueError, OSError):
            continue  # unsafe or unreadable entry; left alone
        if not found:
            continue
        seen.add(slug)
        e = k.store.get(f"goal:{slug}")
        if not e or e["payload"].get("revision") != found[2]:
            changed += bool(mirror(k, slug, found[0], found[2], now, "sync"))
    for e in k.store.query("goal", state=OPEN):
        if e["natural_key"] not in seen:
            patch(k.store, e["id"], "cancelled", reason="goal_file_removed", now=now)
            changed += 1
    return changed


def update(k, slug, changes, *, by="user", now, check_in=CHECK_EVERY):
    """goal_update. Only the user changes status and settings; cron appends progress/assessment; Muse's fade
    may only cancel; an assignment closes or reopens the goal its rule made. Done always carries evidence.
    next_check moves to now + 1 day unless the user sets it."""
    allowed, statuses = WRITERS.get(by, (CRON_FIELDS, ()))
    if set(changes) - allowed:
        raise PermissionError(f"{by} may not change {', '.join(sorted(set(changes) - allowed))}")
    if "status" in changes and changes["status"] not in statuses:
        raise ValueError(f"status must be one of {', '.join(statuses)}")
    if changes.get("status") == "done" and not str(changes.get("evidence") or "").strip():
        raise ValueError("status=done needs evidence: a link, commit, file path or one checkable observation")
    if "assessment" in changes and changes["assessment"] not in ASSESSMENTS:
        raise ValueError(f"assessment must be one of {', '.join(ASSESSMENTS)}")

    def mutate(record, body):
        for field in allowed - {"progress_note", "assessment"}:
            if field in changes:
                record[field] = changes[field]
        if "next_check_at" not in changes:
            record["next_check_at"] = now + check_in
        if by in ACTIVITY:
            record["activity_at"] = now
        if "status" in changes:
            record["cancelled_by"] = by if changes["status"] == "cancelled" else None
        if changes.get("assessment"):
            record["assessment"] = {"at": now, "value": changes["assessment"]}
        if changes.get("progress_note"):
            record["progress"] = [*(record.get("progress") or []),
                                  {"at": now, "note": str(changes["progress_note"]).strip()[:1000], "by": by}]
        return record, body
    return write(k, slug, mutate, reason=f"update:{by}", now=now)


def touch_if_open(k, slug, now, note=None):
    """A user message moved this goal forward: activity, and what it said goes in the progress; no notice."""
    e = k.store.get(f"goal:{slug}")
    return update(k, slug, {"progress_note": note} if note else {}, by="kernel", now=now) if e and e["state"] in OPEN else None


def activity(record):
    """When the user or an executor last moved this goal. Goals older than `activity_at` keep their history in the
    progress notes: `updated` cannot tell, since every nightly assessment wrote it."""
    if record.get("activity_at"):
        return record["activity_at"]
    return max([record.get("created") or 0, *(p.get("at") or 0 for p in record.get("progress") or []
                                              if p.get("by") not in ("cron", "fade"))])


def assess(k, slug, assessment=None, progress_note=None, evidence=None, text=None, now=None):
    """Nightly result for a due goal: append-only note and assessment; moves next_check. A done_suggested turns into a
    question to the user (they close the goal), once per stretch of activity; it never closes anything."""
    suggested = assessment == "done_suggested"
    if suggested and not (str(evidence or "").strip() and str(text or "").strip()):
        raise ValueError("done_suggested needs evidence and text (your question to the user); without evidence use on_track")
    changes = {key: v for key, v in (("assessment", assessment), ("progress_note", progress_note)) if v}
    record = update(k, slug, changes, by="cron", now=now, check_in=CHECK_EVERY - NIGHT_SLACK)
    out = {"result": "assessed", "next_check_at": record["next_check_at"]}
    if suggested:
        e = notifier.draft(k, text=text, title=record.get("title") or slug, topic=DONE_TOPIC, goal_id=slug, kind="ask",
                           sources=[evidence], evidence=[f"goal:{slug}"], now=now,
                           notice_key=f"goal:{slug}:done:{int(activity(record))}")
        out["notice"] = {"result": "existing" if e["existing"] else "drafted", "id": e["id"], "state": e["state"]}
    return out


def slug_for(signal_ref):
    return "g" + hashlib.sha256(str(signal_ref).encode()).hexdigest()[:11]


def create(k, *, title, criteria, signal_ref=None, now, by="nightly", session_id=None, extra=None, rule=None, thread=None):
    """A goal authorized by a user signal (cron: one per signal, at most 5 per day), with by='user' by the private main
    session itself (the same session and title give the same goal), or with by='rule' by a rule the user wrote in
    RULES.md (one per rule and event thread)."""
    signal = one(k.store, "signal", signal_ref) if signal_ref else None
    source = (signal or {}).get("payload", {}).get("source")
    if by not in ("user", "rule") and not signal or source and classify(source) != "user":
        raise PermissionError("a goal needs a user signal as authority")
    title, criteria = str(title or "").strip()[:200], str(criteria or "").strip()[:4000]
    if not title or not criteria:
        raise ValueError("title and criteria are required")
    slug = rule_slug(rule, thread) if by == "rule" else slug_for(signal_ref or f"{session_id}:{' '.join(title.casefold().split())}")
    found = read(k.home, slug)
    if found:
        return {"result": "existing", "goal_id": slug}
    if by not in ("user", "rule") and not count_today(k.store, "cron_goal_creates", now, k.tz(), CRON_CREATES_PER_DAY):
        raise PermissionError(f"cron already created {CRON_CREATES_PER_DAY} goals today")

    def mutate(_, __):
        record = {"id": slug, "title": title, "status": "active", "revision": 0, "parent_id": None, "created": now,
                  "deadline": None, "external_ref": None, "research_review_at": now + 30 * D, "source_signal": signal_ref,
                  "session_id": signal["payload"].get("session_id") if signal else session_id, "progress": [], "owner": None,
                  "next_check_at": now + CHECK_EVERY, "waiting_user": False, "blocked": None, "created_by": by,
                  "no_fade": False, "activity_at": now, "rule": rule, "thread_key": thread, **{f: v for f, v in (extra or {}).items() if f in ("deadline", "parent_id", "no_fade")}}
        return record, f"# {title}\n\n## Completion criteria\n{criteria}\n"
    write(k, slug, mutate, reason=f"create:{by}", now=now, create=True)
    return {"result": "created", "goal_id": slug}


def rule_slug(rule, thread):
    return slug_for(f"rule:{rule}:{thread}")


def open_for_thread(k, thread):
    """The open goal of an event thread, whichever rule made it."""
    return next((e for e in k.store.query("goal", state=OPEN) if e["payload"].get("thread_key") == thread), None)


def dropped(k, rule, thread):
    """True when the user cancelled this rule's goal for this thread: later events do not start it again."""
    found = read(k.home, rule_slug(rule, thread))
    return bool(found) and found[0].get("cancelled_by") == "user"


def for_thread(k, *, rule, thread, title, criteria, now):
    """The goal slug for an event thread under a rule: the open one, or a new one, or the rule's finished one reopened
    (a new event on a thread the user gave up on is refused)."""
    goal = open_for_thread(k, thread)
    if goal:
        return goal["natural_key"]
    if dropped(k, rule, thread):
        raise PermissionError("the user cancelled this thread's goal; skip this item")
    slug = create(k, title=title, criteria=criteria, now=now, by="rule", rule=rule, thread=thread)["goal_id"]
    if read(k.home, slug)[0].get("status") != "active":
        update(k, slug, {"status": "active", "progress_note": "Reopened by a new event on this thread."}, by="executor", now=now)
    return slug


def cron_creates_left(k, now):
    return max(0, CRON_CREATES_PER_DAY - k.store.meta("cron_goal_creates", {}).get(local_day(now, k.tz()), 0))


def item(k, e):
    found = read(k.home, e["natural_key"])
    record, body = (found[0], found[1]) if found else ({}, "")
    return {"kind": "goal", "ref": e["natural_key"], "title": record.get("title"), "state": e["state"],
            "next_check_at": record.get("next_check_at"), "progress": (record.get("progress") or [])[-3:],
            "body": body[:1500]}


# -- dormancy and fade -------------------------------------------------------------------------------
def question(prefs, title, days, date):
    """The dormancy question: the user's `fade_question` template (their language) or the English default."""
    template = prefs.get("fade_question")
    if template:
        return template.format(title=title, days=days, date=date or "-")
    return ASK.format(title=title, days=days) + (CLOSES.format(date=date) if date else ".")


def owner_handle(owner):
    return (owner.get("handle") or owner.get("id")) if isinstance(owner, dict) else owner


def exempt(k, record, now, held):
    """A future deadline, an active watch, a live assignment, a running native owner or `no_fade` hold a goal; each of
    those has its own clock (a waiting assignment stalls in 3 days and stops holding it)."""
    if record.get("no_fade") or (record.get("deadline") or 0) > now or record["id"] in held:
        return True
    handle = owner_handle(record.get("owner"))
    # An owner whose status could not be read is treated as running: a host fault must not fade a goal.
    return bool(handle) and k.adapter.owners.status(handle).get("state") in ("running", "host_error")


def fade(k, now):
    """Ask, re-ask and cancel per dormancy episode; withdraw questions whose goal revived or closed."""
    prefs, tz = preferences(k.home), k.tz()
    days, fade_days = prefs.get("goal_dormant_days"), prefs.get("goal_fade_days")
    asked = cancelled = blocked = 0
    keep = set()
    # A goal waiting on the user fades like any other: nobody else will end the wait.
    goals = [(g, read(k.home, g["natural_key"])) for g in k.store.query("goal", state=OPEN)]
    held = {w["payload"].get("goal_id") for w in k.store.query("watch", state="active")}
    held |= {a["payload"].get("goal_id") for a in k.store.query("assignment", state=("running", "waiting"))}
    child_activity = {}
    for g, found in goals:
        parent = g["payload"].get("parent_id")
        if parent and found:
            child_activity[parent] = max(child_activity.get(parent, 0), activity(found[0]))
    for g, found in goals:
        slug = g["natural_key"]
        fade_at = stuck = None
        if days and found and found[0].get("status") == "active":
            record = found[0]
            last = max(activity(record), child_activity.get(slug, 0))
            since = last + days * D
            if last and now >= since and not exempt(k, record, now, held):
                episode = time.strftime("%Y%m%d", time.gmtime(since))
                for attempt in range(1, MAX_ASKS + 1):
                    key = f"goal:{slug}:fade:{episode}:{attempt}"
                    ask = one(k.store, "notice", key)
                    if ask and ask["state"] in CLOSED_ASK:
                        continue
                    keep.add(key)
                    if ask is None:
                        if not count_today(k.store, "fade_asks", now, tz, FADE_ASKS_PER_DAY):
                            break  # tomorrow; nothing has started counting towards a cancel
                        # The cancel clock starts on delivery, so a date counted from now is never too early.
                        date = fade_days and datetime.fromtimestamp(now + fade_days * D, tz).date().isoformat()
                        notifier.draft(k, text=question(prefs, record.get("title") or slug, days, date), topic=notifier.FADE_TOPIC,
                                       goal_id=slug, notice_key=key, kind="ask", title=record.get("title") or slug,
                                       evidence=[f"goal:{slug}"], expires=now + 3 * D, now=now)
                        asked += 1
                    elif ask["state"] == "sent" and fade_days:
                        fade_at = (ask["payload"].get("dispatched_at") or ask["payload"].get("sent_at") or now) + fade_days * D
                        if now >= fade_at:
                            update(k, slug, {"status": "cancelled", "progress_note":
                                             f"Closed by Muse: dormant since {episode}, question delivered, no reply."},
                                   by="fade", now=now)
                            cancelled += 1
                            fade_at = None
                    break
                else:
                    blocked += 1  # every attempt was withdrawn; Health reports the goal instead of looping
                    stuck = episode
        # Health reads both: when code will cancel this goal, and an episode whose every question was withdrawn.
        if (g["payload"].get("fade_at"), g["payload"].get("fade_blocked")) != (fade_at, stuck):
            patch(k.store, g["id"], reason="fade_state", payload={"fade_at": fade_at, "fade_blocked": stuck}, now=now)
    for e in k.store.query("notice", state=notifier.UNSENT):
        if e["payload"].get("topic") == notifier.FADE_TOPIC and e["natural_key"] not in keep:
            notifier.withdraw(k, e["id"], reason="goal_revived_or_closed", now=now, by_code=True)
    return {"asked": asked, "cancelled": cancelled, "blocked": blocked}


def watch_slot(k, slug):
    """(n, job key) for the next watch of an open goal; KeyError when the goal is not open."""
    goal = k.store.get(f"goal:{slug}")
    if not goal or goal["state"] not in OPEN:
        raise KeyError(f"no open goal {slug!r}")
    n = sum(w["payload"].get("goal_id") == slug for w in k.store.query("watch")) + 1
    return n, "watch-" + hashlib.sha256(f"{slug}:{n}".encode()).hexdigest()[:12]


def add_watch(k, slug, n, *, job_id, key, schedule, check, stop_condition, expires=None, now):
    """Record the watch whose owned job the caller already created (install.ensure_watch)."""
    return k.store.create("watch", f"goal:{slug}:watch:{n}", {
        "goal_id": slug, "job_id": job_id, "key": key, "schedule": schedule, "check": check,
        "stop_condition": stop_condition, "expires": expires}, deadline=expires or now + WATCH_RENEW, now=now)


def stop_watch(k, e, *, reason, now):
    """(stopped now, job paused) for a user stop; the job is paused even when the watch already ended."""
    moved = patch(k.store, e["id"], "stopped", expect=("active",), reason=reason, now=now)
    job_id = e["payload"].get("job_id")
    return bool(moved), bool(job_id) and bool(k.adapter.cron.pause(job_id, "watch stopped by the user"))


def watches(k, now):
    """Stop watches of closed goals; renew an open goal's watch that has no user-set expiry."""
    out = {"renewed": 0, "stopped": []}
    for w in k.store.query("watch", state="active"):
        goal = k.store.get(f"goal:{w['payload'].get('goal_id')}")
        if goal and goal["state"] not in OPEN:
            if patch(k.store, w["id"], "stopped", expect=("active",), reason="goal_closed", now=now):
                out["stopped"].append(w)
        elif goal and w["deadline"] <= now and not w["payload"].get("expires"):
            patch(k.store, w["id"], reason="renew", deadline=now + WATCH_RENEW, now=now)
            out["renewed"] += 1
    return out

