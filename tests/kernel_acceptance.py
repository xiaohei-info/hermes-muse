"""WP4 acceptance: kernel business on synthetic homes (design 2.1, 2.4, 2.5, 2.7, 2.9; 7.3 A3, A5, A10).

Part 1 drives the kernel through a recording fake host (no Hermes needed); `run_deliver` stands in for one
muse-deliver run. Part 2, when Hermes is importable, runs Intake and Notifier through the real HostAdapter on a
temporary Hermes home; it creates jobs in that home only and never runs them. No real user data, no live channel.
Usage: PYTHONPATH=<hermes-agent> <hermes venv python> tests/kernel_acceptance.py
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse.host.sessions import SECRETS, excerpt, redact  # noqa: E402
from hermes_muse.health import invariants  # noqa: E402
from hermes_muse.kernel import Kernel, goals, intake, notifier, packets, records, review, sources, upkeep  # noqa: E402
from hermes_muse.kernel.common import render  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC).timestamp()
H, D = 3600, 86400
KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
FAILED = []
SEEN_TEXT = []  # every packet / read handed to the model, for A10


def check(name, ok, detail=""):
    print(f"{name} {'PASS' if ok else 'FAIL'} {json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str)}")
    if not ok:
        FAILED.append(name)


class FakeHost:
    """The HostAdapter surface the kernel uses, over in-memory rows; filters like hermes_muse/host does."""

    def __init__(self, clock):
        self.clock, self.rows, self.delivered, self.receipts = clock, [], {}, {}  # by execution id
        self.paused, self.outcomes, self.owner, self.removed = [], {}, {}, []
        self.legacy, self.legacy_receipts = {}, {}  # 0.4.1 one-shot delivery jobs by key, their receipts
        self.sessions = SimpleNamespace(user_turns=self.user_turns, read=self.read)
        self.deliver = SimpleNamespace(receipt=self.receipt, legacy_jobs=lambda: dict(self.legacy),
                                       legacy_receipt=lambda key: self.legacy_receipts.get(key, {"status": "unknown", "reason": "no_delivery_job"}))
        self.woken, self.stores = [], {}
        self.cron = SimpleNamespace(pause=lambda job_id, reason: self.paused.append(job_id) or True,
                                    outcome=lambda job_id, execution_id=None: self.outcomes.get(execution_id),
                                    wake=lambda job_id: self.woken.append(job_id) or True, remove=self.remove,
                                    job=lambda key: {"id": "job-deliver", "deliver": "bot-chat", "enabled": True} if key == "deliver" else None)
        self.memory = SimpleNamespace(stores=lambda: self.stores)
        self.owners = SimpleNamespace(status=lambda handle: {"state": self.owner.get(handle, "unknown")})
        self.config = SimpleNamespace(get=lambda: {})

    def now(self):
        return datetime.fromtimestamp(self.clock(), UTC)

    def add(self, session, role, text, at, source="cli", tool=None):
        self.rows.append({"id": len(self.rows) + 1, "session_id": session, "role": role, "text": text, "at": at,
                          "source": source, "tool": tool})
        return f"{session}:{len(self.rows)}"

    def user_turns(self, since, roles=("user",), limit=500):
        out = []
        for r in self.rows:
            if r["at"] > since and r["role"] in roles and sources.classify(r["source"]) == "user":
                clean = redact(r["text"])
                out.append({"ref": f"{r['session_id']}:{r['id']}", "session_id": r["session_id"], "role": r["role"],
                            "at": r["at"], "source": r["source"], "tool_name": r["tool"], "chars": len(clean),
                            "attachment": len(clean) > 8000, "text": excerpt(clean)})
        return out[:limit]

    def read(self, ref, offset=0, length=12000):
        row = next(r for r in self.rows if f"{r['session_id']}:{r['id']}" == ref)
        text = redact(row["text"])
        part = text[offset:offset + min(length, 12000)]
        return {"ref": ref, "available": True, "offset": offset, "total": len(text), "text": part, "more": offset + len(part) < len(text)}

    def receipt(self, job_id, execution_id=None):
        return {"job_id": job_id, **self.receipts.get(execution_id, {"status": "sending"})}

    def remove(self, job_id):
        key = next(key for key, job in self.legacy.items() if job["id"] == job_id)
        self.removed.append(self.legacy.pop(key)["id"])
        return True


def make_home(base, prefs=None):
    home = base / "profile"
    (home / "muse").mkdir(parents=True)
    defaults = {"start_hour": 9, "end_hour": 22, "ordinary_per_day": 1, "time_sensitive_per_day": 3, "blocked_topics": []}
    (home / "muse" / "PROACTIVE_PREFERENCES.md").write_text(
        "<!-- hermes-muse " + json.dumps({**defaults, **(prefs or {})}) + " -->\n# Preferences\n", encoding="utf-8")
    return home


def seen(value):
    SEEN_TEXT.append(json.dumps(value, ensure_ascii=False))
    return value


def run_deliver(k, host):
    """One muse-deliver run as entry.deliver makes it: tick, claim for a new execution, record the printed message."""
    k.tick()
    execution = f"exec-{len(host.delivered) + 1}"
    text = notifier.message(notifier.claim(k, host.cron.job("deliver"), execution, k.clock()))
    if text:
        host.delivered[execution] = text
    return text


def deliver_all(k, host):
    run_deliver(k, host)
    for execution in host.delivered:
        host.receipts.setdefault(execution, {"status": "sent", "outcome": "delivered"})
    k.tick()


def part_intake(base):
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    home = make_home(base)
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    host.add("chat", "user", "Remind me Friday; password: hunter2xyz", T0 - 50)
    host.add("chat", "assistant", "Noted.", T0 - 49)
    long_ref = host.add("chat", "user", "Pasted data:\n" + "row,1,2\n" * 4000 + "key sk-" + "a" * 30 + " end", T0 - 40)
    host.add("cronrun", "user", "cron prompt", T0 - 30, source="cron")
    host.add("odd", "user", "legacy source", T0 - 30, source="local")
    host.add("tg", "user", "telegram note", T0 - 20, source="telegram")
    forgotten = host.add("chat", "user", "forget me", T0 - 10)
    k.store.create("tombstone", forgotten, {}, now=T0 - 5)
    first = k.tick()
    again = k.tick()
    signals = k.store.query("signal")
    check("K1 intake: user surfaces only, machine/unclassified/forgotten skipped, idempotent",
          first.get("signals_captured") == 3 and again.get("signals_captured") == 0
          and sorted(s["payload"]["source"] for s in signals) == ["cli", "cli", "telegram"],
          {"first": first.get("signals_captured"), "again": again.get("signals_captured"),
           "sources": intake.captured_sources(k.store, T0 - D), "classify": {s: sources.classify(s) for s in ("cli", "cron", "local")}})

    packet = seen(k.build_packet("intake"))
    same = k.build_packet("intake")
    sizes = [len(i["excerpt"]) for i in packet["items"]]
    long_item = next(i for i in packet["items"] if i["ref"] == long_ref)
    check("K2 intake packet: one issued at a time, head/tail excerpts, <=15 items and <=24k chars, schema+budget",
          same["id"] == packet["id"] and len(packet["items"]) <= 15 and sum(sizes) <= 24000 and max(sizes) <= 8200
          and long_item["attachment"] and set(packet) >= {"id", "type", "items", "schema", "budget"},
          {"items": len(packet["items"]), "excerpt_chars": sizes, "budget": packet["budget"]})

    reads = [seen(k.read(packet["id"], long_ref, offset)) for offset in (0, 12000, 24000)]
    check("K3 read: <=12k per call, <=24k per item per packet",
          [len(r.get("text", "")) for r in reads] == [12000, 12000, 0] and reads[2]["available"] is False,
          [{"len": len(r.get("text", "")), "available": r["available"]} for r in reads])

    results = [{"ref": i["ref"], "disposition": "saved", "facts": ["prefers Friday reminders"],
                **({"goal_hint": "new"} if "Remind" in i["excerpt"] else {})} for i in packet["items"]]
    out = k.submit(packet["id"], results + [{"ref": "chat:999", "disposition": "saved"}])
    after = k.build_packet("intake")
    check("K4 submit: idempotent per item, foreign refs refused, empty packet stays silent",
          [o.get("state") for o in out[:-1]] == ["disposed"] * 3 and "not in this packet" in out[-1]["error"]
          and k.submit(packet["id"], results)[0]["state"] == "disposed" and after["id"] is None
          and k.store.get(packet["id"])["state"] == "submitted",
          {"out": out, "after": after["id"]})

    # A signal handed out 3 times without a disposition parks and stops blocking the queue.
    host.add("chat", "user", "something ambiguous", T0 + 10)
    for hour in range(3):
        clock[0] = T0 + 60 + hour * H
        k.tick()
        k.build_packet("intake")
    clock[0] += H
    k.tick()
    parked = [s for s in k.store.query("signal") if s["payload"]["excerpt"] == "something ambiguous"][0]
    check("K5 signal: 3 hand-outs -> parked", parked["state"] == "parked" and parked["attempts"] == 3,
          {"state": parked["state"], "attempts": parked["attempts"]})

    # Silence-triggered intake wake: 5 min of silence, waiting signals, at most 3 per day.
    host.add("chat", "user", "new thought", clock[0] - 1)
    k.tick()
    wakes = [intake.quiet_wake(k, clock[0] - 400, clock[0]) for _ in range(4)]
    check("K6 quiet wake: after 5 min silence, <=3 per day", wakes == [True, True, True, False]
          and not intake.quiet_wake(k, clock[0] - 60, clock[0]), wakes)
    return k, host, clock


def patrol(k, items, verdict="send", priority="urgent", source="mail:work", text="Security alert", topic=None):
    packet = seen(k.build_packet("patrol"))
    observed = k.observe(packet["id"], source, items)
    results = [{"candidate_ref": o["ref"], "verdict": verdict, "text": text, "priority": priority,
                **({"topic": topic} if topic else {})} for o in observed["items"]]
    return packet, observed, k.submit(packet["id"], results)


def part_notifier(base):
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    k = Kernel(make_home(base, {"blocked_topics": ["crypto"]}), adapter=host, clock=lambda: clock[0])
    alert = {"upstream_id": "gmail:message:synthetic-alert-1", "title": "Vendor alert: environment variable disclosure"}
    outcomes = []
    for day, hour in ((0, 0), (2, 1), (2, 3), (2, 5)):  # the audited pattern: once, then three times two days later
        clock[0] = T0 + day * D + hour * H
        _, observed, out = patrol(k, [alert])
        outcomes.append((observed["items"][0]["notified"], out[0]["result"]))
        k.tick()
        deliver_all(k, host)
    renewal = {"upstream_id": "synthetic-renewal-1", "title": "Domain renewal"}
    for i in range(7):
        clock[0] = T0 + 3 * D + i * 600
        patrol(k, [{**renewal, "title": renewal["title"] + ("" if i % 2 else " (reminder)")}], priority="time_sensitive")
        k.tick()
        deliver_all(k, host)
    by_key = {}
    for e in k.store.query("notice"):
        by_key.setdefault(e["natural_key"], []).append(e["state"])
    rail, plat = by_key.get("src:synthetic-alert-1", []), by_key.get("src:synthetic-renewal-1", [])
    check("A5 dedupe replay: vendor alert x4 and domain renewal x7 -> one notice, one delivery each",
          rail == ["sent"] and plat == ["sent"] and len(host.delivered) == 2,
          {"alert": rail, "renewal": plat, "delivered": len(host.delivered), "alert_rounds": outcomes})

    clock[0] += H
    _, _, out = patrol(k, [alert], verdict="supersede", text="Vendor alert: rotation completed, new details")
    run_deliver(k, host)
    rail = [e for e in k.store.query("notice") if e["natural_key"] == "src:synthetic-alert-1"]
    check("N1 supersede: explicit, new evidence, new generation and delivery key",
          out[0]["result"] == "superseded" and len(rail) == 2 and len(host.delivered) == 3
          and len({e["payload"]["delivery_key"] for e in rail}) == 2, [(e["state"], e["payload"].get("generation")) for e in rail])

    clock[0] = datetime(2026, 11, 5, 9, 30, tzinfo=UTC).timestamp()
    weak = {"title": "Weekly digest ready"}
    patrol(k, [weak], priority="ordinary", source="web:news")
    k.tick()
    deliver_all(k, host)
    clock[0] += 600
    patrol(k, [weak], priority="ordinary", source="web:news")
    k.tick()
    weak_rows = [e for e in k.store.query("notice") if e["natural_key"].startswith("weak:")]
    check("N2 weak key: dedupes unsent candidates only, never blocks on sent history; budget 1/day defers the second",
          sorted(e["state"] for e in weak_rows) == ["scheduled", "sent"]
          and datetime.fromtimestamp(next(e for e in weak_rows if e["state"] == "scheduled")["payload"]["next_eligible"], UTC)
          == datetime(2026, 11, 6, 9, 0, tzinfo=UTC), [(e["state"], e["payload"].get("next_eligible")) for e in weak_rows])

    clock[0] = datetime(2026, 11, 5, 23, 0, tzinfo=UTC).timestamp()
    patrol(k, [{"upstream_id": "cal:evt-1", "title": "Meeting moved"}], priority="time_sensitive", source="calendar:home")
    host.woken.clear()
    patrol(k, [{"upstream_id": "mail:<outage@example.org>", "title": "Outage"}], priority="urgent")
    woken = list(host.woken)
    run_deliver(k, host)
    quiet = {e["natural_key"]: e for e in k.store.query("notice")}
    held, urgent = quiet["src:cal:evt-1"], quiet["src:outage@example.org"]
    check("N3 quiet hours: time_sensitive waits for 09:00, urgent wakes muse-deliver and goes at once",
          held["state"] == "scheduled" and datetime.fromtimestamp(held["payload"]["next_eligible"], UTC).hour == 9
          and urgent["state"] == "sending" and woken == ["job-deliver"], {"held": held["state"], "urgent": urgent["state"], "woken": woken})

    awake_at = datetime(2026, 11, 6, 12, 0, 0, 123456, tzinfo=UTC).timestamp() + 4e-7  # not a whole microsecond
    check("N3 gate: inside waking hours an ordinary notice is eligible at exactly the time asked, not a rounded copy",
          notifier.gate("ordinary", notifier.preferences(k.home), awake_at, UTC) == awake_at,
          {})

    for n in (2, 3):  # urgent_per_day (default 2): the third urgent of the night is gated as time_sensitive
        patrol(k, [{"upstream_id": f"mail:<urgent{n}@example.org>", "title": f"Urgent {n}"}], priority="urgent")
        run_deliver(k, host)
    crypto = patrol(k, [{"upstream_id": "mail:<coin@example.org>", "title": "Token sale"}], priority="urgent", topic="crypto")
    k.tick()
    fade = patrol(k, [{"upstream_id": "mail:<f@example.org>", "title": "x"}], priority="urgent", topic="goal-fade")
    quiet = {e["natural_key"]: e for e in k.store.query("notice")}
    second, third = quiet["src:urgent2@example.org"], quiet["src:urgent3@example.org"]
    check("N3b urgent_per_day caps quiet-hour urgent sends (the rest wait as time_sensitive); a patrol topic in "
          "blocked_topics is withdrawn; the dormancy topic is reserved",
          notifier.spent_today(k.store, "urgent", clock[0], UTC) == 2  # the superseded vendor alert and Outage today
          and all(n["state"] == "scheduled" and n["payload"]["priority"] == "time_sensitive"
                  and n["payload"]["requested_priority"] == "urgent"
                  and datetime.fromtimestamp(n["payload"]["next_eligible"], UTC).hour == 9 for n in (second, third))
          and quiet["src:coin@example.org"]["state"] == "withdrawn" and "reserved" in fade[2][0].get("error", ""),
          {"urgent_spent": notifier.spent_today(k.store, "urgent", clock[0], UTC),
           "held": [[n["state"], n["payload"]["priority"]] for n in (second, third)],
           "crypto": quiet["src:coin@example.org"]["state"], "fade": fade[2][0]})

    # One run, one message: every notice due now in it (up to PER_MESSAGE), each tied to the run's execution;
    # an unreadable receipt waits, a failed one is recorded and nothing is ever claimed or sent again.
    clock[0] = datetime(2026, 11, 6, 10, 0, tzinfo=UTC).timestamp()
    held = run_deliver(k, host)  # the three notices held overnight (the stale digest waits for patrol)
    clock[0] += D  # a fresh urgent allowance
    patrol(k, [{"upstream_id": "https://status.example.org/incidents/42?utm_source=x", "title": "Incident 42"},
               {"upstream_id": "https://status.example.org/incidents/43", "title": "Incident 43"}], text="Incident")
    text = run_deliver(k, host)
    execution = list(host.delivered)[-1]
    pending = [e for e in k.store.query("notice", state="sending") if e["payload"].get("execution_id") == execution]
    host.receipts[execution] = {"status": "unknown", "reason": "host_error"}
    k.tick()
    kept = [k.store.get(e["id"])["state"] for e in pending]
    host.receipts[execution] = {"status": "failed", "reason": "host_config", "detail": "invalid_params field=cwd"}
    again = run_deliver(k, host)
    failed = [k.store.get(e["id"]) for e in pending]
    check("N4 deliver run: due notices in one message with a separator, tied to the run's execution; host_error keeps them "
          "sending, failed(host_config) recorded, never claimed again",
          held.count(notifier.SEPARATOR) == 2 and len(pending) == 2 and text.count(notifier.SEPARATOR) == 1 and text.count("Incident") == 2 and kept == ["sending"] * 2
          and all(e["state"] == "failed" and e["payload"]["receipt"]["reason"] == "host_config" for e in failed) and again == "",
          {"states": [e["state"] for e in failed], "receipt": failed[0]["payload"].get("receipt"), "again": again,
           "held": held.count(notifier.SEPARATOR), "kept": kept})

    # 0.4.1 one-shot deliveries: a sending notice is read from its old job by key and never resent; finished one-shots
    # are removed only once no notice waits for them (a Health backup one-shot has none).
    old = k.store.create("notice", "src:legacy-1", {"text": "Legacy", "priority": "ordinary", "generation": 0,
                                                   "delivery_key": notifier.delivery_key("src:legacy-1"), "job_id": "job-old"},
                         state="sending", now=clock[0])
    old_key = old["payload"]["delivery_key"]
    host.legacy = {old_key: {"id": "job-old", "state": "completed"}, "health-ab-1": {"id": "job-health", "state": "completed"}}
    before = len(host.delivered)
    swept = notifier.sweep(k)
    host.legacy_receipts[old_key] = {"status": "sent", "job_id": "job-old", "outcome": "delivered"}
    run_deliver(k, host)
    swept += notifier.sweep(k)
    check("N4b legacy: one-shot receipt read by delivery key, nothing resent; settled one-shots removed, a waiting one kept until then",
          k.store.get(old["id"])["state"] == "sent" and len(host.delivered) == before and host.removed == ["job-health", "job-old"]
          and swept == 2 and notifier.sweep(k) == 0, {"state": k.store.get(old["id"])["state"], "removed": host.removed})

    # Stale scheduled notice goes back to patrol; only send/skip/withdraw apply to it.
    clock[0] += 2 * D
    packet = seen(k.build_packet("patrol"))
    due = [i for i in packet["items"] if i["kind"] == "notice"]
    out = k.submit(packet["id"], [{"candidate_ref": due[0]["ref"], "verdict": "withdraw"}]) if due else []
    check("N5 patrol packet: stale notices re-verified (<=5), sources due listed, withdraw by verdict",
          due and due[0]["why"] == "stale" and out[0]["result"] == "withdrawn" and len(due) <= 5
          and any(s["source_id"] == "mail:work" for s in packet["context"]["sources_due"]),
          {"due": [(i["ref"], i["why"]) for i in due], "sources_due": [s["source_id"] for s in packet["context"]["sources_due"]]})

    keys = [e["payload"]["delivery_key"] for e in k.store.query("notice") if e["payload"].get("delivery_key")]
    check("N6 delivery keys: digest of the notice key, all match [a-z0-9][a-z0-9_-]{0,63}",
          keys and all(KEY.fullmatch(x) for x in keys), {"count": len(keys), "sample": keys[:2]})

    # Concurrency: two kernels (processes) claim the same notice and build the same packet.
    clock[0] += H
    patrol(k, [{"upstream_id": "gmail:message:race", "title": "Race"}])
    other = Kernel(k.home, adapter=host, clock=lambda: clock[0])
    claimed, ids = [], []
    threads = [threading.Thread(target=lambda kk=kk, n=n: (claimed.extend(notifier.claim(kk, host.cron.job("deliver"), f"race-{n}", clock[0])),
                                                           ids.append(kk.build_packet("patrol", clock[0] + 1800)["id"])))
               for n, kk in enumerate((k, other))]
    [t.start() for t in threads]
    [t.join() for t in threads]
    check("N7 concurrency: one claim, one issued packet per job and period",
          len(claimed) == 1 and len(set(ids)) == 1, {"claimed": len(claimed), "packets": ids})

    # Source registry.
    for _ in range(4):
        four = sources.record(k.store, "calendar:apple", limitation_code="no_attendees", now=clock[0])
    five = sources.record(k.store, "calendar:apple", limitation_code="no_attendees", now=clock[0])
    for _ in range(3):
        failing = sources.record(k.store, "mail:old", error="auth expired", now=clock[0])
    check("S1 sources: same limitation 5x -> limited (no gap); 3 errors -> failing + health; intervals per kind",
          four["state"] == "ok" and four["payload"]["gap"] and five["state"] == "limited" and not five["payload"]["gap"]
          and failing["state"] == "failing" and failing["payload"]["health"]
          and sources.interval("mail:work") == 1800 and sources.interval("calendar:x", {"calendar": 30}) == 1800,
          {"four": four["state"], "five": five["state"], "failing": failing["payload"].get("fail_streak")})
    return k


def write_goal(home, slug, **fields):
    record = {"id": slug, "title": fields.pop("title", slug), "status": "active", "revision": 1, "parent_id": None,
              "created": T0 - 10 * D, "updated": T0 - 10 * D, "deadline": None, "session_id": "chat", "progress": [],
              "owner": None, "next_check_at": T0 - 9 * D, "waiting_user": False, **fields}
    path = home / "muse" / "workspace" / "goals" / slug / "GOAL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(record, f"# {record['title']}\n\nBody.\n"))


def part_goals(base):
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    home = make_home(base, {"ordinary_per_day": None})
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    write_goal(home, "old-goal", title="Old goal")
    write_goal(home, "revive-goal", title="Revive goal")
    write_goal(home, "kept-goal", title="Kept goal", no_fade=True)
    write_goal(home, "fresh", title="Fresh goal", created=T0 - D, updated=T0 - D, next_check_at=T0 + H)
    k.store.create("watch", "goal:old-goal:watch:1", {"job_id": "job-watch-old", "goal_id": "old-goal", "expires": None},
                   deadline=T0 + 30 * D, now=T0)
    k.store.create("watch", "goal:fresh:watch:1", {"job_id": "job-watch-fresh", "goal_id": "fresh", "expires": None},
                   deadline=T0 - 1, now=T0 - 30 * D)
    k.store.create("watch", "goal:fresh:watch:2", {"job_id": "job-watch-user", "goal_id": "fresh", "expires": T0 - 1},
                   deadline=T0 - 1, now=T0 - 30 * D)
    report = k.tick()
    asks = {e["natural_key"]: e for e in k.store.query("notice") if e["payload"].get("topic") == notifier.FADE_TOPIC}
    renewed = k.store.query("watch", natural_key="goal:fresh:watch:1")[0]
    check("G1 sync + watches: mirror from GOAL.md; open goal's watch renewed, user-expired watch expired and paused",
          report["goals_synced"] == 4 and renewed["state"] == "active" and renewed["deadline"] == T0 + goals.WATCH_RENEW
          and k.store.query("watch", natural_key="goal:fresh:watch:2")[0]["state"] == "expired" and "job-watch-user" in host.paused,
          {"report": report, "paused": host.paused})
    check("G2 dormancy: one question per dormant goal (watch, no_fade exempt), code-keyed",
          sorted(asks) == ["goal:revive-goal:fade:20261026:1"], sorted(asks))

    ask = asks["goal:revive-goal:fade:20261026:1"]
    try:
        notifier.withdraw(k, ask["id"], reason="patrol:withdraw", now=clock[0])
        refused = False
    except PermissionError:
        refused = True
    run_deliver(k, host)
    host.receipts[k.store.get(ask["id"])["payload"]["execution_id"]] = {"status": "failed", "reason": "transport"}
    clock[0] = T0 + 13 * H  # 23:00: the re-ask waits for waking hours
    k.tick()  # the first question never arrived
    second = k.store.query("notice", natural_key="goal:revive-goal:fade:20261026:2")
    check("G3 fade question: model cannot withdraw it; a failed delivery is asked again (attempt 2)",
          refused and second and second[0]["state"] in ("scheduled", "sending"), {"refused": refused, "second": [s["state"] for s in second]})

    # The user answers (main session goal_update): the goal revives and the open question is withdrawn by code.
    goals.update(k, "revive-goal", {"progress_note": "user: still on it"}, by="user", now=clock[0])
    k.tick()
    second = k.store.get(second[0]["id"])
    check("G4 revival withdraws the open question", second["state"] == "withdrawn", second["state"])

    clock[0] = T0 + D

    # A dormant goal whose question was delivered a day earlier is cancelled by code at fade_at.
    write_goal(home, "fade-me", title="Fade me", created=T0 - 15 * D, updated=T0 - 15 * D)
    k.store.create("watch", "goal:fade-me:watch:1", {"job_id": "job-watch-fade", "goal_id": "fade-me", "expires": T0 + 9 * D},
                   deadline=T0 + 9 * D, now=T0)
    k.tick()
    w = k.store.query("watch", natural_key="goal:fade-me:watch:1")[0]
    k.store.transition(w["id"], "stopped", state="active", version=w["version"], reason="test:user_stop")
    k.tick()
    ask = [e for e in k.store.query("notice") if e["natural_key"].startswith("goal:fade-me:fade:")][0]
    deliver_all(k, host)
    clock[0] += D + 60
    k.tick()
    record = goals.read(home, "fade-me")[0]
    mirror = k.store.get("goal:fade-me")
    check("G5 fade: question delivered >= 1 day and fade_at reached -> code cancels GOAL.md and the mirror",
          k.store.get(ask["id"])["state"] == "sent" and record["status"] == "cancelled" and mirror["state"] == "cancelled"
          and "Closed by Muse" in record["progress"][-1]["note"], {"status": record["status"], "mirror": mirror["state"]})

    # Old goal: watch keeps it exempt; once the goal closes, its watch stops and its host job is paused.
    goals.update(k, "old-goal", {"status": "done"}, by="user", now=clock[0])
    k.tick()
    check("G6 closed goal stops its watch and pauses the host job",
          k.store.query("watch", natural_key="goal:old-goal:watch:1")[0]["state"] == "stopped" and "job-watch-old" in host.paused,
          host.paused)

    # next_check: any touch moves it; cron may only append; external edits are picked up by sync.
    clock[0] += H
    before = goals.read(home, "fresh")[0]["next_check_at"]
    goals.assess(k, "fresh", "on_track", "made progress", now=clock[0])
    rec = goals.read(home, "fresh")[0]
    try:
        goals.update(k, "fresh", {"status": "done"}, by="cron", now=clock[0])
        cron_status = True
    except PermissionError:
        cron_status = False
    write_goal(home, "fresh", title="Fresh goal (renamed by user)", created=T0 - D, updated=clock[0], next_check_at=clock[0] + 5 * H)
    k.tick()
    check("G7 next_check: nightly assessment -> now+1d-6h (due again next night), cron cannot change status, mirror follows GOAL.md edits",
          rec["next_check_at"] == clock[0] + D - goals.NIGHT_SLACK and before != rec["next_check_at"] and not cron_status
          and rec["progress"][-1]["by"] == "cron" and k.store.get("goal:fresh")["payload"]["title"] == "Fresh goal (renamed by user)"
          and k.store.get("goal:fresh")["deadline"] == clock[0] + 5 * H, {"next_check_at": rec["next_check_at"]})

    # Nightly: due goals, review candidates and goal proposals in one packet; cron goal creation needs a user signal.
    host.add("chat", "user", "fix the deploy script", clock[0] - 5 * H)
    host.add("chat", "assistant", "Done, fixed.", clock[0] - 5 * H + 5)
    host.add("chat", "user", "run the tests", clock[0] - 4 * H)
    host.add("chat", "tool", '{"success": false, "error": "exit 1"}', clock[0] - 4 * H + 5, tool="terminal")
    host.add("chat", "assistant", "The tests fail.", clock[0] - 4 * H + 6)
    host.add("chat", "user", "不是这个，我说的是另一个仓库", clock[0] - 3 * H)
    need = host.add("chat", "user", "remind me to renew the passport next month", clock[0] - 2 * H)
    host.add("chat", "user", "thanks", clock[0] - H)
    for i in range(12):
        host.add("burst", "user", f"ship build {i}", clock[0] - 50 * 60 + i)
        host.add("burst", "assistant", f"Deployed build {i}.", clock[0] - 50 * 60 + i + 0.5)
    k.tick()
    every_rule = {r for i in review.candidates(k, clock[0]) for r in i["rules"]}
    signal = k.store.query("signal", natural_key=need)[0]
    intake.dispose(k, signal["natural_key"], "saved", ["passport renewal next month"], "new", clock[0])
    packet = seen(k.build_packet("nightly"))
    kinds = [i["kind"] for i in packet["items"]]
    reviews = [i for i in packet["items"] if i["kind"] == "review"]
    check("R1 nightly batch: goals, then proposals, then review candidates oldest first; rules claim/tool failure/correction/need",
          kinds == sorted(kinds, key=["goal", "signal", "review"].index) and reviews and reviews[0]["at"] <= reviews[-1]["at"]
          and packet["context"]["remaining"] > 0
          and every_rule == {"claim_without_write", "tool_failure_unretried", "user_correction", "unrecorded_need"},
          {"kinds": kinds, "rules_all_candidates": sorted(every_rule)})
    results = [{"candidate_ref": i["ref"], "verdict": "agent_gap" if n == 0 else "fine", "reason": "claimed without evidence"}
               for n, i in enumerate(reviews)]
    results += [{"goal_id": "revive-goal", "assessment": "stalled"}] if "goal" in kinds else []
    proposal = next(i for i in packet["items"] if i["kind"] == "signal")
    results.append({"create": {"signal_ref": proposal["ref"], "title": "Renew passport", "criteria": "Passport renewed"}})
    out = k.submit(packet["id"], results)
    created = out[-1]
    again = k.submit(packet["id"], results[-1:])
    older_reviews = review.candidates(k, clock[0])
    check("R2 review/goals submit: one finding per turn, goal from a user signal once, picked turns never re-picked",
          created.get("result") == "created" and again[0]["result"] == "existing"
          and len(k.store.query("finding", state="open")) == 1
          and not {i["ref"] for i in older_reviews} & {i["ref"] for i in reviews},
          {"created": created, "open_findings": len(k.store.query("finding", state="open")), "next_reviews": len(older_reviews)})

    # Runs: closed from host status and packet dispositions; abandoned when the host never heard of it.
    k.start_run("nightly", job_id="job-n", execution_id="e-ok", packet_id=packet["id"])
    k.start_run("nightly", job_id="job-n", execution_id="e-fail")
    k.start_run("nightly", job_id="job-n", execution_id="e-lost")
    k.start_run("nightly", job_id="job-n", execution_id="e-flaky")
    k.start_run("nightly", job_id="job-n", execution_id="e-lostproc")
    host.outcomes.update({"e-ok": {"status": "completed"}, "e-fail": {"status": "failed"}, "e-lostproc": {"status": "unknown"},
                          "e-flaky": {"execution_id": None, "status": "host_error"}})  # what Cron.outcome gives on a fault
    k.tick()
    clock[0] += 3 * H
    k.tick()
    states = {r["natural_key"]: r["state"] for r in k.store.query("run")}
    check("R3 runs: degraded/failed from host + packet (a process the host lost is failed), abandoned when the host has "
          "no record, kept when the host read failed",
          states == {"e-ok": "degraded", "e-fail": "failed", "e-lostproc": "failed", "e-lost": "abandoned", "e-flaky": "running"}, states)
    return k


def batch_size(job, n):
    """Shrink the fixed batch size of a job (a short drain in the test)."""
    spec = packets.JOBS[job]
    packets.JOBS[job] = {**spec, "items": n}
    return lambda: packets.JOBS.__setitem__(job, spec)


def part_drain(base):
    """Nightly drains every due goal in batches: relay wakes, failed batch re-offered, skipped goal reported;
    only batches in a row that handle nothing end the relay."""
    clock = [T0 + 17 * H + 20 * 60]  # 03:20 next day
    night = clock[0]
    host = FakeHost(lambda: clock[0])
    home = make_home(base)
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    for i in range(23):
        write_goal(home, f"g{i:02d}", no_fade=True, next_check_at=T0 - H - i)
    k.tick()
    restore = batch_size("nightly", 2)
    try:
        names, offered, most_issued, same, n, released, between = [], [], 0, True, 0, None, None
        while n < 40:
            packet = k.build_packet("nightly")
            if packet["id"] is None:
                break
            n += 1
            same &= k.build_packet("nightly")["id"] == packet["id"]
            most_issued = max(most_issued, len(k.store.query("packet", state="issued")))
            names.append(k.store.get(packet["id"])["natural_key"])
            refs = [i["ref"] for i in packet["items"]]
            offered += refs
            k.start_run("nightly", job_id="job-n", execution_id=f"e{n}", packet_id=packet["id"])
            if n == 2:  # this run dies before submitting
                host.outcomes["e2"] = {"status": "failed"}
            elif n == 4:  # this run submits one goal, then dies: the other comes back
                k.submit(packet["id"], [{"goal_id": refs[0], "assessment": "on_track"}])
                host.outcomes["e4"], released = {"status": "failed"}, refs[1]
            else:
                k.submit(packet["id"], [{"goal_id": r, "assessment": "on_track"} for r in refs if r != "g03"])
                host.outcomes[f"e{n}"] = {"status": "completed"}
            clock[0] += 60
            k.tick()
            if n == 1:  # between two batches: the night is still in progress
                between = invariants.goals(k.store, clock[0])[0]["level"]
        drained = len(host.woken)
        stuck = []
        for i in range(5):  # a goal no run gets to: every batch handles nothing
            write_goal(home, "g99", no_fade=True, next_check_at=clock[0] - 1)
            k.tick()
            k.start_run("nightly", job_id="job-n", execution_id=f"e-stuck{i}", packet_id=k.build_packet("nightly")["id"])
            host.outcomes[f"e-stuck{i}"] = {"status": "failed"}
            clock[0] += 60
            woken = len(host.woken)
            k.tick()
            stuck.append(len(host.woken) - woken)
    finally:
        restore()
    period = int(night // D)
    checked = [i for i in range(23) if goals.read(home, f"g{i:02d}")[0]["next_check_at"] > night]
    missed = invariants.goals(k.store, clock[0] + 3 * H)[0]
    expired = [p for p in k.store.query("packet", state="expired")]
    check("N1 drain: every due goal checked tonight in batches nightly:P, nightly:P:1…; one issued at a time; "
          "a failed batch expires and its goals come back; a skipped goal is not offered again",
          len(checked) == 22 and 3 not in checked and names[:3] == [f"nightly:{period}", f"nightly:{period}:1", f"nightly:{period}:2"]
          and most_issued == 1 and same and offered.count("g03") == 1 and offered.count(offered[2]) == 2
          and offered.count(released) == 2 and offered.count(offered[6]) == 1 and offered[0] == "g22",
          {"batches": n, "checked": len(checked), "names": names[:3], "expired": len(expired)})
    check("N2 relay: every batch with work left wakes the job; three batches in a row that handle nothing end it",
          drained == n - 1 and stuck == [1, 1, 0, 0, 0] and set(host.woken) == {"job-n"},
          {"drained": drained, "batches": n, "stuck_wakes": stuck})
    check("N3 Health goals_missed: quiet between two batches; then names only the goals left unchecked; "
          "assessed goals are due the next night",
          between == "ok" and missed["id"] == "goals_missed" and missed["level"] == "medium"
          and missed["evidence"] == ["goal:g03"]
          and len([g for g in k.store.due(night + D, kind="goal") if g["natural_key"] != "g99"]) == 23,
          {"missed": [missed["level"], missed["evidence"]]})
    return k


def part_intake_drain(base):
    """Intake drains a backlog larger than one batch within one period, a message arriving meanwhile included;
    failed batches between progressing ones never end the relay (more than the 12 wakes 0.4.2 allowed); three
    batches in a row that handle nothing do, Health reports it, and the next period goes on."""
    clock = [T0]  # the start of an hourly period
    period = int(T0 // H)
    host = FakeHost(lambda: clock[0])
    k = Kernel(make_home(base), adapter=host, clock=lambda: clock[0])
    for i in range(30):
        host.add("chat", "user", f"note {i}", T0 - 300 + i)
    k.tick()
    restore = batch_size("intake", 2)
    try:
        names, n, failed, late = [], 0, 0, None
        while n < 80:
            packet = k.build_packet("intake")
            if packet["id"] is None:
                break
            n += 1
            names.append(k.store.get(packet["id"])["natural_key"])
            k.start_run("intake", job_id="job-i", execution_id=f"i{n}", packet_id=packet["id"])
            if n % 2 == 0:  # every other run dies before submitting: its signals come back in the next batch
                host.outcomes[f"i{n}"], failed = {"status": "failed"}, failed + 1
            else:
                k.submit(packet["id"], [{"ref": i["ref"], "disposition": "context"} for i in packet["items"]])
                host.outcomes[f"i{n}"] = {"status": "completed"}
            if n == 5:
                late = host.add("chat", "user", "a message during the drain", clock[0])
            clock[0] += 60
            k.tick()
        drained, signals = len(host.woken), k.store.query("signal")
        stuck = [host.add("chat", "user", f"stuck {i}", clock[0] - 10 + i) for i in range(3)]
        k.tick()
        wakes = []
        for i in range(3):  # runs that die before submitting
            k.start_run("intake", job_id="job-i", execution_id=f"s{i}", packet_id=k.build_packet("intake")["id"])
            host.outcomes[f"s{i}"] = {"status": "failed"}
            clock[0] += 60
            woken = len(host.woken)
            k.tick()
            wakes.append(len(host.woken) - woken)
        quiet = invariants.drains(k.store, clock[0])["level"]
        stopped = invariants.drains(k.store, clock[0] + invariants.DRAIN_GRACE + 60)
        clock[0] = (period + 1) * H + 60
        k.tick()
        following = k.build_packet("intake")
    finally:
        restore()
    check("K7 intake drain: 31 signals in batches intake:P, intake:P:1… within one period, the late message included; "
          f"{failed} failed batches between progressing ones still relay (> 12)",
          all(s["state"] == "disposed" for s in signals) and len(signals) == 31 and late in {s["natural_key"] for s in signals}
          and names[:2] == [f"intake:{period}", f"intake:{period}:1"] and all(x.startswith(f"intake:{period}") for x in names)
          and drained == n - 1 and failed > 12 and max(s["attempts"] for s in signals) == 2,
          {"batches": n, "failed": failed, "wakes": drained})
    check("K8 intake relay: three batches in a row that handle nothing stop it; Health drain_stopped after the grace; "
          "the next period offers what is left",
          wakes == [1, 1, 0] and quiet == "ok" and stopped["level"] == "medium" and "intake: 1 left" in stopped["detail"]
          and [i["ref"] for i in following["items"]] == stuck[2:]
          and k.store.get(following["id"])["natural_key"] == f"intake:{period + 1}",
          {"wakes": wakes, "stopped": stopped["detail"], "following": [i["ref"] for i in following["items"]]})
    return k


def part_reviews(base):
    """Every flagged turn is judged the same night in batches; proposals are made once and look back 7 days."""
    clock = [T0 - 2 * D]
    host = FakeHost(lambda: clock[0])
    home = make_home(base)
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    old = host.add("chat", "user", "Let us repaint the shed this weekend", clock[0])
    k.tick()
    intake.dispose(k, old, "saved", ["repaint the shed"], "new", clock[0])
    clock[0] = T0
    for i in range(40):
        host.add(f"s{i}", "user", f"deploy service {i}", T0 - 40 * H + i * H)
        host.add(f"s{i}", "assistant", f"Done, deployed service {i}.", T0 - 40 * H + i * H + 1)
    judged, kinds, sizes = 0, [], []
    for n in range(30):
        packet = seen(k.build_packet("nightly"))
        if packet["id"] is None:
            break
        kinds += [i["kind"] for i in packet["items"]]
        sizes.append(len(packet["items"]))
        k.start_run("nightly", job_id="job-n", execution_id=f"r{n}", packet_id=packet["id"])
        out = k.submit(packet["id"], [{"candidate_ref": i["ref"], "verdict": "fine", "reason": "verified the deploy"}
                                      if i["kind"] == "review" else {"decline": {"signal_ref": i["ref"], "reason": "a chore"}}
                                      for i in packet["items"]])
        judged += sum("error" not in r and r.get("result") != "declined" for r in out)
        host.outcomes[f"r{n}"] = {"status": "completed"}
        k.tick()
        clock[0] += 60
    proposed = k.store.query("signal", natural_key=old)[0]["payload"].get("proposed_at")
    clock[0] = T0 + D
    second = k.build_packet("nightly")
    check("N4 no review cap: all 40 flagged turns judged tonight in fixed batches of JOBS.nightly.items, none left for the "
          "next night; a proposal disposed two days ago is offered once; Health's drain jobs are the kernel's",
          sizes[:4] == [packets.JOBS["nightly"]["items"]] * 4 and
          invariants.DRAINS == tuple(j for j, spec in packets.JOBS.items() if spec.get("drain"))
          and judged == 40 and kinds.count("review") == 40 and kinds.count("signal") == 1 and proposed == T0 and second["id"] is None,
          {"judged": judged, "kinds": len(kinds), "second": second["id"], "sizes": sizes})
    return k


def part_proposals(base):
    """A declined proposal is progress; proposals past the cron daily goal cap wait, unproposed, for the next period."""
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    k = Kernel(make_home(base), adapter=host, clock=lambda: clock[0])
    refs = [host.add(f"p{i}", "user", f"please plan errand {i}", T0 - H + i) for i in range(11)]
    k.tick()
    for ref in refs:
        intake.dispose(k, ref, "saved", ["an errand"], "new", T0)
    restore = batch_size("nightly", 1)
    try:
        wakes = []
        for i in range(4):  # one proposal per batch, each declined
            packet = k.build_packet("nightly")
            k.start_run("nightly", job_id="job-n", execution_id=f"d{i}", packet_id=packet["id"])
            k.submit(packet["id"], [{"decline": {"signal_ref": packet["items"][0]["ref"], "reason": "not concrete work"}}])
            host.outcomes[f"d{i}"] = {"status": "completed"}
            woken = len(host.woken)
            k.tick()
            wakes.append(len(host.woken) - woken)
    finally:
        restore()
    declined = [r for r in refs if k.store.query("signal", natural_key=r)[0]["payload"].get("proposed_at")]
    check("N5 a declined proposal is handled: batches of declines keep the relay going and are not offered again",
          wakes == [1, 1, 1, 1] and len(declined) == 4, {"wakes": wakes, "declined": len(declined)})

    offered = []
    for day in (0, 1):
        clock[0] = T0 + day * D + 60
        for i in range(3):
            packet = k.build_packet("nightly")
            if packet["id"] is None:
                break
            k.start_run("nightly", job_id="job-n", execution_id=f"c{day}{i}", packet_id=packet["id"])
            props = [p["ref"] for p in packet["items"] if p["kind"] == "signal"]
            k.submit(packet["id"], [{"create": {"signal_ref": r, "title": f"Errand {r}", "criteria": "done"}} for r in props])
            offered += [props] if props else []
            host.outcomes[f"c{day}{i}"] = {"status": "completed"}
            k.tick()
    left = [r for r in refs if r not in declined and not k.store.query("signal", natural_key=r)[0]["payload"].get("proposed_at")]
    check("N6 the cron goal cap: 5 proposals offered and created today, the other 2 not marked proposed and offered "
          "the next period",
          [len(o) for o in offered] == [5, 2] and not left and goals.cron_creates_left(k, clock[0]) == 3,
          {"offered": [len(o) for o in offered], "left": len(left)})
    return k


def part_feed(base):
    """Interests are researched once a day without starving; one Feed notice goes through the Notifier."""
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    home = make_home(base, {"blocked_topics": ["crypto"]})
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    ids = [records.remember(k, "interest", t, now=T0)["id"] for t in ("Rust releases", "Moon mission", "Coins", "Jazz")]
    restore = batch_size("feed", 1)
    try:
        seen_refs = []
        for _ in range(6):
            packet = k.build_packet("feed")
            if packet["id"] is None:
                break
            seen_refs += [i["ref"] for i in packet["items"]]
            k.submit(packet["id"], [{"interest_ref": i["ref"]} for i in packet["items"]])
        check("F1 feed: every active interest checked once today though no article was written",
              sorted(seen_refs) == sorted(ids) and all(k.store.get(i)["payload"].get("checked_at") == T0 for i in ids)
              and k.build_packet("feed")["id"] is None, {"seen": len(seen_refs)})

        url = "https://example.org/rust/1.99"
        notifier.draft(k, text="Rust 1.99 is out", upstream_id=url, title="Rust 1.99", now=T0)
        k.tick()
        deliver_all(k, host)
        clock[0] = T0 + D + 13 * H  # 23:00 next day: quiet hours
        out = {}
        for _ in range(4):
            packet = seen(k.build_packet("feed"))
            item = packet["items"][0]
            title = k.store.get(item["ref"])["payload"]["title"]
            source = {"Rust releases": url, "Moon mission": "https://example.org/moon", "Coins": "https://example.org/coin",
                      "Jazz": "https://example.org/jazz"}[title]
            result = {"interest_ref": item["ref"], "article": {"title": title, "body": "What happened and why.", "source_refs": [source]},
                      "notice": {"text": f"{title}: news", "source_ref": source, "topic": "crypto" if title == "Coins" else "space"}}
            if title == "Jazz":
                bad = [{**result, "notice": {**result["notice"], "source_ref": "https://elsewhere"}},
                       {"interest_ref": item["ref"], "notice": result["notice"]},
                       {**result, "notice": {**result["notice"], "priority": "urgent"}}]
                out["errors"] = [k.submit(packet["id"], [r])[0].get("error", "") for r in bad]
                result = {**result, "notice": {**result["notice"], "topic": "music"}}
                out["Jazz"] = k.submit(packet["id"], [result, result])
            else:
                out[title] = k.submit(packet["id"], [result])[0]
    finally:
        restore()
    moon = k.store.get(out["Moon mission"]["notice"]["id"])
    coin = k.store.get(out["Coins"]["notice"]["id"])
    morning = datetime.fromtimestamp(clock[0], UTC).replace(hour=9) .timestamp() + D
    check("F2 feed notice: src: strong key shared with patrol (existing), blocked topic withdrawn, quiet hours wait for 09:00, "
          "interest_id kept; one notice per packet; notice needs its article and one of its sources; urgent refused",
          out["Rust releases"]["notice"]["result"] == "existing" and moon["natural_key"] == "src:https://example.org/moon"
          and moon["state"] == "scheduled" and moon["payload"]["next_eligible"] == morning and moon["payload"]["interest_id"]
          and coin["state"] == "withdrawn" and "at most 1 notice" in out["Jazz"][1].get("error", "")
          and all(out["errors"]), {"moon": [moon["state"], moon["payload"].get("next_eligible")], "coin": coin["state"],
                                   "errors": out["errors"], "jazz": out["Jazz"]})
    interest = k.store.get(moon["payload"]["interest_id"])
    records.feedback(k, interest, "stop", now=clock[0])
    run_deliver(k, host)
    moon = k.store.get(moon["id"])
    check("F3 a Feed notice is withdrawn by code when its interest stops",
          moon["state"] == "withdrawn" and k.store.events(moon["id"])[-1]["reason"] == "interest_closed", moon["state"])
    return k


def part_upkeep(base):
    clock = [T0]
    host = FakeHost(lambda: clock[0])
    home = make_home(base)
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    host.stores = {"user": {"entries": ["x"], "chars": 1789, "limit": 1800}, "memory": {"entries": [], "chars": 10, "limit": 3600}}
    host.add("chat", "user", "I moved to Lisbon", T0 - 60)
    k.tick()
    packet = k.build_packet("intake")
    asks = [bool(upkeep.full(k, T0)) for _ in range(3)]
    host.stores["user"]["chars"] = 1000
    low = upkeep.full(k, T0 + D)
    host.stores = {"status": "host_error"}
    failed = upkeep.full(k, T0 + D)
    check("U1 memory_full: a store >= 90% is named while intake has items, at most 3 packets a day; not below 90% or on a host error",
          packet["context"]["memory_full"] == [{"target": "user", "usage": "99% 1789/1800"}] and asks == [True, True, False]
          and low == [] and failed == [], {"context": packet.get("context"), "asks": asks})
    remove = {"action": "remove", "target": "user", "old_text": "tea"}
    merge = {"action": "patch", "old_text": "a", "content": "b"}
    check("U2 guard: each remove needs its own patch in the same batch (merge); empty operations is the single action; add/patch pass",
          upkeep.guard(remove) and upkeep.guard({"operations": [remove, remove]}) and upkeep.guard({**remove, "operations": []})
          and upkeep.guard({"operations": [merge, remove, remove]})
          and upkeep.guard({"operations": [merge, remove]}) is None
          and upkeep.guard({"action": "add", "content": "x"}) is None, "")
    before = {"user": {"entries": ["Likes tea", "Likes green tea; password: hunter2xyz", "Lives in Porto"], "chars": 0, "limit": 1800}}
    after = {"user": {"entries": ["Likes green tea", "Lives in Porto", "Moved to Lisbon"], "chars": 0, "limit": 1800}}
    clock[0] = T0 + 2 * H
    added = upkeep.record(k, after, {"user": {**after["user"], "entries": [*after["user"]["entries"], "Has a cat"]}}, clock[0])
    changes = upkeep.record(k, before, after, clock[0])
    note = (home / "muse" / "memory" / "2026-10-29.md").read_text(encoding="utf-8")
    clock[0] = T0 + 17 * H
    nightly = seen(k.build_packet("nightly"))
    listed = nightly["context"]["memory_changes"]
    k.start_run("nightly", job_id="job-n", execution_id="u3", packet_id=nightly["id"])
    host.outcomes["u3"] = {"status": "completed"}  # the run wrote the dream without a submit (no items)
    k.tick()
    check("U3 every merge/shorten is recorded in the day's note (redacted) and handed to the nightly dream once; "
          "the closed run reports it, no relay wake",
          added == [] and changes[0]["old"] == before["user"]["entries"][:2] and "Likes tea" in note and "Moved to Lisbon" in note
          and "hunter2xyz" not in note and nightly["items"] == [] and len(listed) == 1 and "hunter2xyz" not in json.dumps(listed)
          and host.woken == [] and k.build_packet("nightly")["id"] is None, {"note": note[:300], "listed": listed})
    return k


def a3_a10(kernels):
    missing = []
    for k in kernels:
        db = sqlite3.connect(k.store.path)
        from hermes_muse.kernel.store import MACHINES
        for kind, m in MACHINES.items():
            for state in m.ttl:
                missing += db.execute("SELECT id FROM entity WHERE kind=? AND state=? AND deadline IS NULL", (kind, state)).fetchall()
        db.close()
    check("A3 every non-terminal entity has a deadline", not missing, {"missing": missing})
    hits = sum(len(p.findall(text)) for text in SEEN_TEXT for p, _ in SECRETS[1:])
    hits += sum(len(re.findall(r"(?:hunter2xyz)", text)) for text in SEEN_TEXT)
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, (list, dict)):
            for v in value.values() if isinstance(value, dict) else value:
                yield from strings(v)
    biggest = max(len(x) for text in SEEN_TEXT for x in strings(json.loads(text)))
    check("A10 nothing handed to the model holds a credential pattern; no single text field > 12k chars",
          hits == 0 and biggest <= 12000, {"credential_hits": hits, "largest_item_chars": biggest, "payloads": len(SEEN_TEXT)})


def part_native(base):
    try:
        from hermes_state import SessionDB
    except ImportError:
        print("NATIVE SKIP hermes-agent not importable (set PYTHONPATH to hermes-agent)")
        return
    home = base / "native"
    (home / "workspace").mkdir(parents=True)
    (home / "config.yaml").write_text("timezone: UTC\nplugins:\n  enabled: [hermes-muse]\n")
    os.environ.update(HERMES_HOME=str(home), HERMES_IGNORE_USER_CONFIG="1")
    SessionDB(db_path=home / "state.db").close()
    import time
    now = time.time()
    db = sqlite3.connect(home / "state.db")
    for sid, source in (("chat", "cli"), ("once", "oneshot"), ("odd", "local")):
        db.execute("INSERT INTO sessions (id, source, chat_type, title, started_at) VALUES (?,?,?,?,?)", (sid, source, "dm", None, now - 60))
    for i, (sid, text) in enumerate((("chat", "Plan the trip; token: zq81kd0"), ("once", "Reply only OK"), ("odd", "legacy"))):
        db.execute("INSERT INTO messages (session_id, role, content, timestamp, message_uid) VALUES (?,?,?,?,?)",
                   (sid, "user", text, now - 30 + i, f"u{i}"))
    db.commit()
    db.close()
    k = Kernel(home)
    k.tick()
    signals = k.store.query("signal")
    packet = k.build_packet("intake")
    page = k.read(packet["id"], packet["items"][0]["ref"]) if packet["items"] else {}
    probe = {p["name"]: p for p in k.adapter.probe(captured_sources=intake.captured_sources(k.store, now - D))}
    check("NATIVE intake via HostAdapter: only the cli turn, redacted; unclassified 'local' reported by probe",
          [s["payload"]["source"] for s in signals] == ["cli"] and "zq81kd0" not in json.dumps(packet) + json.dumps(page)
          and page.get("available") and probe["signal_purity"]["status"] == "degraded" and "local" in probe["signal_purity"]["detail"],
          {"signals": len(signals), "purity": probe["signal_purity"]["detail"]})
    notice = notifier.draft(k, text="Native delivery check", priority="urgent", upstream_id="gmail:message:native1",
                            title="Native", now=now)
    job = k.adapter.cron.ensure("deliver", schedule="*/10 * * * *", entry=ROOT / "cron_entry.py", deliver="bot-chat", no_agent=True)
    claimed = notifier.claim(k, job, "native-run", now)
    sent = k.store.get(notice["id"])
    check("NATIVE delivery: claimed for the muse-deliver run; its receipt is read from that job (not run: sending)",
          [e["id"] for e in claimed] == [notice["id"]] and sent["state"] == "sending" and sent["payload"]["job_id"] == job["id"]
          and k.adapter.deliver.receipt(job["id"], "native-run")["status"] == "sending",
          {"state": sent["state"], "faults": list(k.adapter.faults)[-2:]})


def main():
    with tempfile.TemporaryDirectory(prefix="muse-kernel-") as temporary:
        base = Path(temporary).resolve()
        kernels = []
        for name, part in (("intake", part_intake), ("notifier", part_notifier), ("goals", part_goals), ("drain", part_drain),
                           ("intake_drain", part_intake_drain), ("reviews", part_reviews), ("proposals", part_proposals), ("feed", part_feed), ("upkeep", part_upkeep)):
            (base / name).mkdir()
            result = part(base / name)
            kernels.append(result[0] if isinstance(result, tuple) else result)
        a3_a10(kernels)
        part_native(base)
    print(f"RESULT {'FAIL ' + ','.join(FAILED) if FAILED else 'PASS'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
