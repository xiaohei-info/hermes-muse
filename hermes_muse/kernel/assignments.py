"""Assignments: the ledger of work handed to an executor. Muse keeps the books (who, since when, expected when, what
came back) and never starts, stops or talks to an executor: the patrol's model or the main session does that with the
user's tools and templates from RULES.md, and reports here.

Nobody waits on a process: an assignment comes due, the patrol checks it with the `status` template and submits what it
found. Hermes' own delegation (executor `native`) closes by code through HostAdapter.owners. `failed` ends one
assignment; its goal stays open and the user is asked to retry (a new assignment, n + 1) or give up (cancel the goal).

An executor cannot be called back once started, so whether an item may start one is decided before observe hands out
its template (`blocker`), not when the ledger hears about it afterwards.
"""
from datetime import datetime

from .. import rules
from . import goals, notifier
from .common import D, H, patch
from .store import keys, machine

CHECK_EVERY = 2 * H
MAX_UNANSWERED = 3  # patrol packets in a row that left a due assignment unanswered
MAX_EXPECT = 30 * D
LIVE = ("running", "waiting")
ENDED = ("done", "failed", "stopped")
HOLDS = ("failed", "stalled")  # the latest assignment of a thread ended this way: the user decides what comes next
REPORTS = ("running", "waiting", "done", "failed", "stalled")
TOPIC = "assignment"
STALLED = "The work on “{title}” ({executor}) has passed its expected end with no progress. Should it continue, or stop?"
LOST = "I can no longer see how the work on “{title}” ({executor}) is going: its status checks keep coming back empty."


def next_check(expected_end, now):
    return min(expected_end, now + CHECK_EVERY) if expected_end > now else now + CHECK_EVERY


def of_goal(k, slug):
    """A goal's assignments, latest first."""
    return sorted((e for e in k.store.query("assignment") if e["payload"].get("goal_id") == slug),
                  key=lambda e: e["payload"].get("opened_at") or 0, reverse=True)


def live_of(k, slug):
    return next((e for e in of_goal(k, slug) if e["state"] in LIVE), None)


def end_time(k, value, default, now):
    """An expected end (ISO 8601; the profile's zone when it has none) kept within MAX_EXPECT, or the default."""
    if not value:
        return default
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"expected_end {value!r} is not an ISO 8601 time") from None
    return min((at if at.tzinfo else at.replace(tzinfo=k.tz())).timestamp(), now + MAX_EXPECT)


def open(k, *, goal_id, executor, handle, expected_end, rule=None, thread=None, tell="needed", authority=None, by, now):
    """Record one assignment; the same handle on the same goal returns the live one (submit is idempotent)."""
    goal = k.store.get(f"goal:{goal_id}")
    if not goal or goal["state"] not in goals.OPEN:
        raise KeyError(f"no open goal {goal_id!r}")
    with k.store.atomic():
        rows = of_goal(k, goal_id)
        same = next((e for e in rows if e["state"] in LIVE and e["payload"].get("handle") == handle), None)
        if same:
            return {**same, "existing": True}
        e = k.store.create("assignment", keys.assignment_key(goal_id, len(rows) + 1), {
            "goal_id": goal_id, "executor": executor, "handle": handle, "rule": rule, "thread_key": thread, "tell": tell,
            "authority": authority, "by": by, "opened_at": now, "expected_end": expected_end, "unanswered": 0, "forwards": 0},
            deadline=next_check(expected_end, now), now=now)
    goals.update(k, goal_id, {"progress_note": f"Assigned to {executor} ({handle})."}, by="executor", now=now)
    return e


def record(k, goal_id, *, executor, handle, expected_end=None, note=None, now):
    """assignment_record: the main session says which executor it started for an open goal."""
    known = (rules.NATIVE, *rules.load(k.home)["executors"])
    if executor not in known:
        raise ValueError(f"executor must be one of {', '.join(known)} (add it to RULES.md); got {executor!r}")
    goal = k.store.get(f"goal:{goal_id}")
    e = open(k, goal_id=goal_id, executor=executor, handle=handle, by="user", now=now,
             expected_end=end_time(k, expected_end, now + CHECK_EVERY, now), thread=goal and goal["payload"].get("thread_key"))
    if note and not e["existing"]:
        goals.update(k, goal_id, {"progress_note": note}, by="executor", now=now)
    return e


def current(k, rule, thread):
    """(the open goal this rule and thread belong to, its live assignment); each None when there is none."""
    auto = rule.get("goal") in (None, "auto")
    goal = (goals.open_for_thread(k, thread) if thread else None) if auto else k.store.get(f"goal:{rule['goal']}")
    goal = goal if goal and goal["state"] in goals.OPEN else None
    return goal, goal and live_of(k, goal["natural_key"]) or None


def blocker(k, rule, item, thread, goal):
    """Why this item may not start its rule's executor, or None. Writes nothing. Observe gives no run template when there
    is a reason, and dispatch refuses on the same one."""
    if not rules.link(item):
        return "the item has no clean http(s) link to give the executor"
    auto = rule.get("goal") in (None, "auto")
    if not auto and not goal:
        return f"goal {rule['goal']!r} is not open"
    if auto and not goal and goals.dropped(k, thread):
        return "the user cancelled this thread's goal"
    rows = of_goal(k, rule["goal"]) if not auto else sorted(
        (e for e in k.store.query("assignment") if e["payload"].get("thread_key") == thread),
        key=lambda e: e["payload"].get("opened_at") or 0, reverse=True)
    latest = next(iter(rows), None)
    if latest and (latest["state"] in HOLDS or (goal and latest["state"] == "stopped" and latest["payload"].get("stopped_by"))):
        return f"{latest['id']} {latest['state']}: the user decides what happens next"
    return None


def dispatch(k, item, r, now):
    """Patrol verdict `dispatch`: the model started the rule's executor with its template and reports the handle."""
    rule = item.get("rule") or {}
    if rule.get("do") != "dispatch":
        raise ValueError("an executor has this thread; answer `forwarded`" if rule.get("do") == "forward" else
                         f"{item.get('held') or 'observe did not mark this item do=dispatch'}; judge it with send or skip")
    handle = str(r.get("handle") or "").strip()[:200]
    if not handle:
        raise ValueError("dispatch needs handle: what the executor's run template returned")
    if r.get("executor") not in (None, rule["executor"]):
        raise ValueError(f"this rule's executor is {rule['executor']!r}")
    thread = item.get("thread")
    goal, live = current(k, rule, thread)
    if live and live["payload"].get("handle") != handle:
        raise ValueError(f"{live['id']} is already working on this; answer `forwarded` instead")
    why = None if live else blocker(k, rule, item, thread, goal)
    if why:
        raise ValueError(f"{why}; skip this item")
    slug = goal["natural_key"] if goal else rule["goal"] if rule["goal"] != "auto" else goals.for_thread(
        k, rule=rule["name"], thread=thread, title=item["title"], criteria=rule["ask"], now=now)
    default = now + rules.seconds(rule.get("expect") or rules.EXPECT)
    try:
        end = end_time(k, r.get("expected_end"), default, now)
    except ValueError:  # the executor is running: a bad estimate must not lose its record
        end = default
    e = open(k, goal_id=slug, executor=rule["executor"], handle=handle, rule=rule["name"], thread=thread, expected_end=end,
             tell=rule.get("tell") or "needed", authority=rule.get("authority"), by="patrol", now=now)
    return {"result": "existing" if e["existing"] else "dispatched", "assignment": e["id"], "goal": slug}


def forward(k, item, now):
    """Patrol verdict `forwarded`: a new item of a thread went to the executor with its `send` template. Looked up now,
    since the executor may have been started by an earlier item of this very packet."""
    _, e = current(k, item.get("rule") or {}, item.get("thread"))
    if not e:
        raise ValueError("forwarded needs a live assignment on this item's thread; dispatch the thread's first item, or skip")
    moved = patch(k.store, e["id"], expect=LIVE, reason="forward", now=now,
                  payload=lambda c: {"forwards": c["payload"].get("forwards", 0) + 1, "forwarded_at": now})
    # Not activity (by=patrol): an event arriving is not anyone moving the work forward.
    goals.update(k, e["payload"]["goal_id"], {"progress_note": f"New on this thread, passed on: {item['title']}"}, by="patrol", now=now)
    return {"result": "forwarded", "assignment": e["id"], "forwards": moved["payload"]["forwards"]}


def tell(k, e, event, text, *, kind="tell", priority="ordinary", sources=(), now):
    """A notice about this state change of the assignment; same gates, budgets and delivery as any other."""
    title = (goals.read(k.home, e["payload"]["goal_id"]) or [{}])[0].get("title") or e["payload"]["goal_id"]
    return notifier.draft(k, text=text, priority=priority, title=title, topic=TOPIC, goal_id=e["payload"]["goal_id"],
                          sources=sources, evidence=[e["id"]], kind=kind, assignment_id=e["id"], now=now,
                          notice_key=keys.assignment_notice_key(e["natural_key"], event, e["version"]))


def told_text(k, e, template):
    title = (goals.read(k.home, e["payload"]["goal_id"]) or [{}])[0].get("title") or e["payload"]["goal_id"]
    return template.format(title=title, executor=e["payload"].get("executor"))


def close_goal(k, e, conclusion, evidence, now):
    """(a goal a rule made is closed by code on evidence; the user's goal stays theirs to close). True when closed."""
    slug = e["payload"]["goal_id"]
    found = goals.read(k.home, slug)
    if found and found[0].get("created_by") == "rule" and found[0].get("status") == "active":
        goals.update(k, slug, {"status": "done", "evidence": evidence, "progress_note": conclusion}, by="executor", now=now)
        return True
    goals.update(k, slug, {"progress_note": f"{conclusion} Evidence: {evidence}"}, by="executor", now=now)
    return False


def report(k, assignment_id, state, *, conclusion=None, evidence=None, question=None, expected_end=None, by="patrol", now):
    """What an executor's status showed (patrol), or the user's say (main session, by=user: they already know, so no
    notice; by=native likewise: Hermes returns a delegation's result to the main session). Past its expected end with nothing new, `running` is `stalled`. A question or failure always reaches the
    user; the rule's `tell` decides only about finished work."""
    if state not in (*REPORTS, *(("stopped",) if by == "user" else ())):
        raise ValueError(f"state must be one of {', '.join(REPORTS)}")
    e = k.store.get(assignment_id)
    if not e or e["kind"] != "assignment":
        raise KeyError(f"unknown assignment {assignment_id!r}")
    conclusion, evidence = str(conclusion or "").strip(), str(evidence or "").strip()
    question = str(question or "").strip()
    if state == "done" and not (conclusion and evidence):
        raise ValueError("state=done needs conclusion and evidence (a link, commit, file path or checkable observation)")
    if state == "failed" and not conclusion:
        raise ValueError("state=failed needs conclusion: what went wrong")
    if state == "waiting" and not question and by != "user":
        raise ValueError("state=waiting needs question: the decision, your recommendation, why, and the options")
    if e["state"] in ENDED:
        return {"result": "closed", "assignment": e["id"], "state": e["state"]}
    p = e["payload"]
    end = end_time(k, expected_end, p["expected_end"], now)
    if state == "running" and not conclusion and now >= end and by != "user":
        state = "stalled"
    if state == e["state"] and state != "running":
        return {"result": "unchanged", "assignment": e["id"], "state": state}
    if state != e["state"] and (e["state"], state) not in machine("assignment").edges:
        legal = sorted(to for at, to in machine("assignment").edges if at == e["state"])
        raise ValueError(f"state: this assignment is {e['state']}; it can only become {', '.join(legal)}")
    data = {"unanswered": 0, "checked_at": now, "expected_end": end, "stalled_told": state == "stalled",
            **({"stopped_by": by} if state == "stopped" else {}),
            **{f: v for f, v in (("conclusion", conclusion), ("evidence", evidence), ("question", question)) if v}}
    moved = patch(k.store, e["id"], state, expect=(e["state"],), reason=f"report:{by}:{state}", payload=data, now=now,
                  deadline=next_check(end, now) if state == "running" else None)
    if moved is None:
        return {"result": "unchanged", "assignment": e["id"], "state": k.store.get(e["id"])["state"]}
    out = {"result": "reported", "assignment": e["id"], "state": state}
    closed = False
    if state == "done":
        closed = out["goal_closed"] = close_goal(k, moved, conclusion, evidence, now)
    elif conclusion or state != "running":
        note = conclusion or question or f"{p.get('executor')}: {state}."
        goals.update(k, p["goal_id"], {"progress_note": note}, by="executor", now=now)
    if by not in ("user", "native"):
        notice = {
            "waiting": lambda: tell(k, moved, "ask", question, kind="ask", now=now),
            "failed": lambda: tell(k, moved, "failed", question or conclusion, kind="ask", priority="time_sensitive", now=now),
            "stalled": lambda: tell(k, moved, "stalled", conclusion or told_text(k, moved, STALLED), priority="time_sensitive", now=now),
            "done": lambda: (p.get("tell") == "always" or (p.get("tell") != "never" and not closed)) and tell(
                k, moved, "done", conclusion, sources=[evidence], now=now),
        }.get(state, lambda: None)()
        if notice:
            out["notice"] = notice["id"]
    return out


def sweep(k, now):
    """Tick step: end what lost its goal, close native delegations from the host, give up on a patrol that stopped
    answering, tell the user about a question left waiting into `stalled`, and withdraw questions about closed goals."""
    counts = {"stopped": 0, "closed": 0, "lost": 0, "told": 0, "withdrawn": 0}
    store = k.store
    for e in store.query("assignment", state=LIVE):
        p = e["payload"]
        goal = store.get(f"goal:{p.get('goal_id')}")
        if goal and goal["state"] not in goals.OPEN:
            counts["stopped"] += bool(patch(store, e["id"], "stopped", expect=LIVE, reason="goal_closed", now=now))
        elif e["state"] != "running" or e["deadline"] > now:
            continue
        elif p.get("executor") == rules.NATIVE:
            counts["closed"] += close_native(k, e, now)
        elif p.get("unanswered", 0) >= MAX_UNANSWERED:
            moved = patch(store, e["id"], "lost", expect=("running",), reason="patrol_unanswered", now=now)
            if moved:
                counts["lost"] += 1
                tell(k, moved, "lost", told_text(k, moved, LOST), priority="time_sensitive", now=now)
    for e in store.query("assignment", state="stalled"):
        if not e["payload"].get("stalled_told"):
            moved = patch(store, e["id"], expect=("stalled",), reason="stalled_told", payload={"stalled_told": True}, now=now)
            if moved:
                counts["told"] += 1
                tell(k, moved, "stalled", told_text(k, moved, STALLED), priority="time_sensitive", now=now)
    for e in store.query("notice", state=notifier.UNSENT):  # goals.fade withdraws its own
        p = e["payload"]
        if p.get("kind") == "ask" and p.get("goal_id") and p.get("topic") != notifier.FADE_TOPIC:
            goal = store.get(f"goal:{p['goal_id']}")
            if goal and goal["state"] not in goals.OPEN:
                counts["withdrawn"] += bool(notifier.withdraw(k, e["id"], reason="goal_closed", now=now, by_code=True))
    return counts


def close_native(k, e, now):
    """Hermes returns a delegation's result to the main session itself; the ledger only needs its outcome."""
    handle = e["payload"].get("handle")
    state = k.adapter.owners.status(handle).get("state")
    if state == "done":
        report(k, e["id"], "done", conclusion=f"Delegation {handle} finished.", evidence=f"delegation:{handle}", by="native", now=now)
    elif state == "failed":
        report(k, e["id"], "failed", conclusion=f"Delegation {handle} failed.", by="native", now=now)
    elif state == "unknown":
        patch(k.store, e["id"], "lost", expect=("running",), reason="no_host_record", now=now)
    else:  # still running, or the host could not be read: ask again later
        patch(k.store, e["id"], expect=("running",), reason="native_running", deadline=now + CHECK_EVERY, now=now)
        return 0
    return 1


def due(k, now, limit):
    """Running assignments past their check time, the longest waiting first; patrol checks them with `status`."""
    rows = [e for e in k.store.query("assignment", state="running")
            if e["deadline"] <= now and e["payload"].get("executor") != rules.NATIVE]
    return [{"kind": "assignment", "ref": e["id"], "goal": e["payload"].get("goal_id"), "executor": e["payload"].get("executor"),
             "handle": e["payload"].get("handle"), "opened_at": e["payload"].get("opened_at"),
             "expected_end": e["payload"].get("expected_end"), "conclusion": e["payload"].get("conclusion"),
             "overdue": now >= e["payload"].get("expected_end", now)}
            for e in sorted(rows, key=lambda e: e["deadline"])[:limit]]


def offered(k, items, now):
    """Count one more patrol packet holding these due assignments; a report resets the count."""
    for item in items:
        if item["kind"] == "assignment":
            patch(k.store, item["ref"], expect=("running",), reason="offered", now=now,
                  payload=lambda e: {"unanswered": e["payload"].get("unanswered", 0) + 1})


def annotate(k, item, table, earlier=()):
    """What the rules say about one observed item, stored on it and answered by observe; {} when no rule matches. `earlier`
    are this packet's previous items: one of them may be about to start the executor this item's thread needs.
    `do` is final: dispatch (run and brief given), forward (an executor has the thread), ask, tell, ignore. A dispatch rule
    that may not start anything now is `tell` with `held` saying why."""
    rule = rules.match(table["rules"], item)
    if not rule:
        return {}
    thread = rules.thread(rule, item)
    auto = rule["goal"] == "auto"
    goal, live = current(k, rule, thread)
    opener = next((o for o in earlier if (o.get("rule") or {}).get("do") == "dispatch"
                   and (o["thread"] == thread if auto else o["rule"].get("goal") == rule["goal"])), None)
    do, held = rule["do"], None
    if auto and thread and not goal and goals.dropped(k, thread):
        do = "ignore"
    elif do != "ignore" and (live or opener):
        do = "forward"
    elif do == "dispatch":
        held = blocker(k, rule, item, thread, goal)
        do = "tell" if held else do
    kept = {f: rule.get(f) for f in ("name", "executor", "ask", "tell", "authority", "expect", "goal")}
    item.update(rule={**kept, "do": do}, thread=thread, goal=goal and goal["natural_key"], assignment=live and live["id"], held=held)
    out = {"rule": rule["name"], "do": do, "thread": thread, "goal": item["goal"], "assignment": item["assignment"]}
    executor = (live and live["payload"].get("executor")) or (opener and opener["rule"].get("executor")) or rule.get("executor")
    templates = table["executors"].get(executor or "", {})
    if do == "forward":
        note = rules.forward_note(item)
        if note and templates.get("send"):
            out.update(forward_with=templates["send"], message=note, **({"handle": live["payload"].get("handle")} if live else {"handle_from": opener["ref"]}))
        else:
            held = "nothing can be passed on: no clean link, or the executor has no send template; skip it"
    elif do == "dispatch":
        out.update(run=templates.get("run"), brief=rules.brief(rule, item))
    elif do == "ask" and rule.get("ask"):
        out["ask"] = rule["ask"]
    return {**out, **({"held": held} if held else {})}


def rule_context(k, items):
    """patrol's context.rules: the templates of the executors its due assignments need, or why the file is unusable."""
    try:
        executors = rules.load(k.home)["executors"]
    except ValueError as exc:
        return {"error": str(exc)}
    needed = {i["executor"] for i in items if i["kind"] == "assignment"}
    return {"executors": {name: executors[name] for name in needed if name in executors}}


def links(k, e):
    """Next-hop ids of a goal or assignment, so a page leads to the rest of the story."""
    slug = e["natural_key"] if e["kind"] == "goal" else e["payload"].get("goal_id")
    notices = [{"id": n["id"], "state": n["state"], "kind": n["payload"].get("kind", "tell"), "title": n["payload"].get("title")}
               for n in k.store.query("notice") if n["payload"].get("goal_id") == slug][:20]
    if e["kind"] == "goal":
        return {"assignments": [{"id": a["id"], "state": a["state"], "executor": a["payload"].get("executor"),
                                 "handle": a["payload"].get("handle"), "expected_end": a["payload"].get("expected_end")}
                                for a in of_goal(k, slug)][:20],
                "notices": notices, "thread": e["payload"].get("thread_key")}
    return {"goal": f"goal:{slug}", "notices": [n for n in notices if k.store.get(n["id"])["payload"].get("assignment_id") == e["id"]]}


def week(store, since):
    """Weekly digest counts: assignments per rule and executor (by state), questions asked, frictions found."""
    by_rule, by_executor = {}, {}
    for e in store.query("assignment", since=since):
        p = e["payload"]
        for table, name in ((by_rule, p.get("rule") or "(main session)"), (by_executor, p.get("executor"))):
            table.setdefault(name, {}).setdefault(e["state"], 0)
            table[name][e["state"]] += 1
    return {"by_rule": by_rule, "by_executor": by_executor,
            "questions_asked": sum(n["payload"].get("kind") == "ask" for n in store.query("notice", state=notifier.SPENT, since=since)),
            "notices_from_assignments": sum(bool(n["payload"].get("assignment_id")) for n in store.query("notice", state=notifier.SPENT, since=since)),
            "frictions": sum(f["payload"].get("tag") == "friction" for f in store.query("finding", since=since))}
