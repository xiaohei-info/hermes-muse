"""Health invariants over a read-only Store v2 and the HostAdapter (design 2.8, 7.3).

Each check returns one or more health items `item(id, level, value, threshold, detail, evidence)`; level is
ok | low | medium | high. Checks only read; they never repair, so a kernel bug stays visible.
Payload fields read here are the kernel's contract: signal.source, notice.next_eligible/priority/strong_key,
goal.fade_at/fade_blocked (goals.fade), finding.evidence (review.record), source.health (sources.record),
packet.job/issued_at/context.remaining/handled (packets.build/submit), run.job (runs.start), interest.checked_at
(packets.feed_result), notice.verified_at/topic (notifier.draft).
Tests seed these through the kernel writers, never with hand-written payloads.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from ..kernel.store import MACHINES
from ..kernel.store.keys import SOURCE_ID

H, D = 3600, 86400
LEVELS = ("ok", "low", "medium", "high")
PROBE_LEVEL = {"ok": "ok", "degraded": "medium", "missing": "high"}
MINOR_PROBES = {"config_location", "home"}  # degraded here never stops a feature
EVIDENCE = 10
DRAINS = ("intake", "nightly", "feed")  # kernel.packets drain jobs (kernel_acceptance N4 asserts they match)
DRAIN_GRACE = 3 * H  # a drain between two batches is still in progress
MEMORY_NEAR_FULL = 0.98


def item(id, level, value, threshold, detail="", evidence=(), fix=""):
    return {"id": id, "level": level, "value": value, "threshold": threshold, "detail": detail,
            "evidence": [str(e) for e in list(evidence)[:EVIDENCE]], "fix": fix if level != "ok" else ""}


def worst(*levels):
    return max(levels, key=LEVELS.index, default="ok")


def ids(rows):
    return [r["id"] for r in rows]


def probes(results):
    out = []
    for p in results:
        level = PROBE_LEVEL.get(p["status"], "high")
        if p["name"] in MINOR_PROBES and level == "medium":
            level = "low"
        out.append(item(f"probe.{p['name']}", level, p["status"], "ok", p["detail"], fix=p["fix"]))
    return out


def host_faults(faults):
    calls = Counter(f["call"] for f in faults)
    return item("host_faults", "medium" if faults else "ok", len(faults), 0,
                   "; ".join(f"{c} x{n}" for c, n in calls.most_common()) or "no host call failed",
                   [f["error"][:200] for f in faults],
                   "A Hermes API or database changed shape; run tests/native_host_contract.py")


def plugin_load(failed):
    """B: Hermes abandoned Muse's load (deadline passed) in the process running its jobs; they stay silent."""
    return item("plugin_load", "high" if failed else "ok", failed, False,
                "Hermes abandoned Muse's plugin load in the process running its jobs: no Muse tools, skill or hooks "
                "there, so the jobs that need the model stay silent" if failed else "loaded where Muse's jobs run",
                fix="Restart the gateway; errors.log names the load error")


# -- Store v2 ---------------------------------------------------------------------------------------
def deadlines(store, now):
    """A3 and the kernel watchdog: every non-terminal entity has a deadline, and tick() applies due exits."""
    missing, stalled = [], []
    for kind, m in MACHINES.items():
        for state, (_, exit_state) in m.ttl.items():
            for e in store.query(kind, state=state):
                if e["deadline"] is None:
                    missing.append(e)
                elif exit_state and e["deadline"] < now - H:
                    stalled.append(e)
    return [item("deadlines", "high" if missing else "ok", len(missing), 0,
                    f"{len(missing)} non-terminal entities without a deadline", ids(missing),
                    "Kernel created a live entity without a deadline; fix the caller (A3)"),
            item("tick_stalled", "high" if stalled else "ok", len(stalled), 0,
                    f"{len(stalled)} entities over 1h past a deadline with a code exit", ids(stalled),
                    "Store.tick() is not running; check the kernel pre-run and its errors")]


def signals(store, now):
    """A7 watermark age (oldest undisposed signal), parked count in 7 days."""
    live = sorted(store.query("signal", state="new"), key=lambda e: e["state_since"])
    age = (now - live[0]["state_since"]) / H if live else 0
    parked = store.query("signal", state="parked", since=now - 7 * D)
    return [item("signal_watermark", "high" if age > 6 else "medium" if age > 2 else "ok", round(age, 2), "<2h",
                    f"{len(live)} signals waiting; oldest {age:.1f}h", ids(live[:1]),
                    "Intake packets are not disposing signals; check packets_idle and intake runs"),
            item("signal_parked", "medium" if len(parked) >= 5 else "ok", len(parked), "<5",
                    f"{len(parked)} signals parked in 7 days (excerpt not disposed in 3 tries/72h)", ids(parked),
                    "Read the parked signals; long pastes may need a smaller intake packet")]


def packets(store, now):
    """A8 expiry rate, and the watchdog: work is queued but the kernel issued no packet for 2 hours."""
    recent = store.query("packet", since=now - 7 * D)
    done = [p for p in recent if p["state"] in ("submitted", "expired")]
    expired = [p for p in done if p["state"] == "expired"]
    rate = len(expired) / len(done) if done else 0.0
    queued = store.query("signal", state="new", limit=1) + store.query("notice", state=("drafted", "scheduled"), limit=1)
    latest = max((p["state_since"] for p in store.query("packet", limit=1)), default=None)
    idle = bool(queued) and (latest is None or latest < now - 2 * H)
    return [item("packet_expiry", "medium" if rate >= 0.1 else "ok", round(rate, 3), "<0.1",
                    f"{len(expired)}/{len(done)} packets expired in 7 days", ids(expired),
                    "Packets are too large for the job's time budget; check the per-item timing"),
            item("packets_idle", "high" if idle else "ok", int(idle), 0,
                    "work is queued but no packet was issued for 2h" if idle else "packets flowing",
                    ids(queued), "Kernel packet builder is stuck or the Muse cron jobs are not running")]


def notices(store, now):
    """7-day duplicate sends per strong notice key; hanging drafted/scheduled notices; closed unknowns."""
    groups = defaultdict(list)
    for n in store.query("notice", state="sent", since=now - 7 * D):
        if n["payload"].get("strong_key", n["natural_key"].startswith("src:")):
            groups[n["natural_key"]].append(n)
    # only v2 deliveries (delivery_key) make a duplicate: migrated 0.3.x sends alone are history, not a dedupe failure
    dups = {k: g for k, g in groups.items() if len(g) > 1 and any(n["payload"].get("delivery_key") for n in g)}
    urgent = any(n["payload"].get("priority") == "urgent" and n["payload"].get("delivery_key") for g in dups.values() for n in g)
    hanging = [n for n in store.query("notice", state=("drafted", "scheduled"))
               if n["payload"].get("next_eligible", n["state_since"]) < now - 6 * H]
    closed = store.query("notice", state="closed_unknown", since=now - 7 * D)
    return [item("notice_duplicates", ("high" if urgent else "medium") if dups else "ok", len(dups), 0,
                    f"{len(dups)} source keys sent again by v2 within 7 days",
                    [n["id"] for g in dups.values() for n in g], "Notifier dedupe against sent history failed (A5)"),
            item("notice_hanging", "medium" if hanging else "ok", len(hanging), 0,
                    f"{len(hanging)} notices eligible for over 6h but not decided", ids(hanging),
                    "Patrol packets must carry due notices; check packet building"),
            item("notice_unknown", "medium" if closed else "ok", len(closed), 0,
                    f"{len(closed)} notices closed after 48h unknown in 7 days", ids(closed),
                    "Delivery receipts are unreadable; see probe.delivery_semantics")]


def deliveries(store, executions, jobs, now):
    """Delivery failure within one cycle: host executions of Muse jobs, and v2 notices that failed or went unknown."""
    failed = [e for e in executions if e["delivery_outcome"] in ("failed", "not_configured")]
    broken = [e for e in executions if e["status"] in ("failed", "unknown")]
    lost = [n for n in store.query("notice", state=("failed", "unknown"), since=now - D)
            if n["payload"].get("delivery_key")] if store else []  # migrated 0.3.x deliveries have no delivery_key
    errors = sorted({str(e["error"] or jobs.get(e["job_id"], {}).get("last_delivery_error") or e["delivery_outcome"])[:160]
                     for e in failed})
    return [item("delivery", "high" if failed or lost else "ok", len(failed) + len(lost), 0,
                    f"{len(failed)} failed deliveries, {len(lost)} failed/unknown notices in 24h; {errors}",
                    [e["execution_id"] for e in failed] + ids(lost),
                    "Check probe.delivery_target and the job's last_delivery_error; configure health_deliver"),
            item("executions", "medium" if broken else "ok", len(broken), 0,
                    f"{len(broken)} Muse cron executions failed or unknown in 24h",
                    [f"{e['execution_id']}: {str(e['error'])[:120]}" for e in broken],
                    "Read the execution error; a gateway restart explains one isolated failure")]


def runs(store, now):
    """Run results in 24h (ok >= 90%) and runs left running past their deadline."""
    finished = [r for r in store.query("run", since=now - D) if r["state"] != "running"]
    ok = sum(r["state"] == "ok" for r in finished)
    rate = ok / len(finished) if finished else 1.0
    stuck = [r for r in store.query("run", state="running") if r["deadline"] is not None and r["deadline"] < now]
    return [item("runs_ok", "medium" if rate < 0.9 else "ok", round(rate, 3), ">=0.9",
                    f"{ok}/{len(finished)} runs ok in 24h", ids(r for r in finished if r["state"] != "ok"),
                    "Read the degraded/failed runs' reasons; limited sources must not degrade a run"),
            item("runs_unclosed", "low" if stuck else "ok", len(stuck), 0,
                    f"{len(stuck)} runs running past 2h", ids(stuck),
                    "Run closing reads the host execution; check host_faults")]


def last_night(store, now):
    """(start, packets) of the latest finished nightly period: no batch issued, no nightly run running, and not
    between two batches (the latest left work and was issued within DRAIN_GRACE)."""
    nightly = [p for p in store.query("packet", since=now - 3 * D) if p["payload"].get("job") == "nightly"]
    if any(p["state"] == "issued" for p in nightly) or any(r["payload"].get("job") == "nightly" for r in store.query("run", state="running")):
        return None, []
    if not nightly:
        return now - 3 * D, []  # no nightly packet for 3 days: every goal due since then was missed
    latest = max(nightly, key=lambda p: p["payload"]["issued_at"])
    if (latest["payload"].get("context") or {}).get("remaining") and latest["payload"]["issued_at"] > now - DRAIN_GRACE:
        return None, []
    period = latest["natural_key"].split(":")[:2]
    night = [p for p in nightly if p["natural_key"].split(":")[:2] == period]
    return min(p["payload"]["issued_at"] for p in night), night


def goals(store, now):
    """Every active goal due before last night's first batch was checked (two nights missed: high); fade executed
    within 2 days of fade_at."""
    live = store.query("goal", state=("active", "waiting"))
    active = [g for g in live if g["state"] == "active"]
    start, _ = last_night(store, now)
    missed = [] if start is None else [g for g in active if g["deadline"] is not None and g["deadline"] < start]
    twice = [g for g in missed if g["deadline"] < start - D]
    faded = [g for g in active if (g["payload"].get("fade_at") or now) < now - 2 * D]
    stuck = [g for g in active if g["payload"].get("fade_blocked")]
    return [item("goals_missed", "high" if twice else "medium" if missed else "ok", len(missed), 0,
                    f"{len(missed)} active goals due before the last nightly run and still unchecked; {len(twice)} missed two nights",
                    ids(twice + [g for g in missed if g not in twice]),
                    "Read the nightly runs and packets: a result error, a failed batch or a stopped relay leave goals unchecked"),
            item("goal_fade", "medium" if faded or stuck else "ok", len(faded) + len(stuck), 0,
                    f"{len(faded)} goals over 2 days past fade_at and still open; "
                    f"{len(stuck)} whose dormancy question was withdrawn every time", ids(faded + stuck),
                    "Fade ask was not delivered, the code cancel did not run, or the question keeps being withdrawn")]


def sources(store, now):
    failing = [s for s in store.query("source", state="failing")
               if s["payload"].get("health") and SOURCE_ID.fullmatch(s["natural_key"])]
    return item("sources_failing", "medium" if failing else "ok", len(failing), 0,
                   f"{len(failing)} sources failing 3+ times in a row", ids(failing),
                   "Check the source's tool or credentials")


def findings(store, now):
    recent = store.query("finding", since=now - D)
    bare = [f for f in store.query("finding", state="open") if not f["payload"].get("evidence")]
    return item("review_findings", "low" if bare else "ok", len(recent), "all with evidence",
                f"{len(recent)} findings in 24h; {len(bare)} open without evidence", ids(bare),
                "Review findings must cite evidence")


def drains(store, now):
    """A drain job whose latest batch left work, with no batch issued or run running for DRAIN_GRACE: its relay
    stopped (batches in a row that handled nothing, or a lost wake) and the rest waits for the next period."""
    recent = store.query("packet", since=now - 3 * D)
    running = {r["payload"].get("job") for r in store.query("run", state="running")}
    stopped = []
    for job in DRAINS:
        latest = max((p for p in recent if p["payload"].get("job") == job), key=lambda p: p["payload"]["issued_at"], default=None)
        if (latest and latest["state"] != "issued" and job not in running and latest["payload"]["issued_at"] < now - DRAIN_GRACE
                and (latest["payload"].get("context") or {}).get("remaining")):
            stopped.append(latest)
    return item("drain_stopped", "medium" if stopped else "ok", len(stopped), 0,
                "; ".join(f"{p['payload']['job']}: {p['payload']['context']['remaining']} left after the last batch"
                          for p in stopped) or "no drain stopped with work left", ids(stopped),
                "Read the job's last runs: three batches in a row that handled nothing stop the relay until the next period")


def interests(store, now):
    unchecked = [i for i in store.query("interest", state="active")
                 if (i["payload"].get("checked_at") or i["state_since"]) < now - 2 * D]
    return item("interests_unchecked", "medium" if unchecked else "ok", len(unchecked), 0,
                f"{len(unchecked)} active interests not researched by the Feed for 2 days", ids(unchecked),
                "Check the feed-pulse job and its runs")


STORE_CHECKS = (deadlines, signals, packets, notices, runs, goals, sources, findings, drains, interests)


# -- Host --------------------------------------------------------------------------------------------
def tools(results):
    """A9 tool error rate per job (<3%) and A10 oversized results / credential patterns sent to the model."""
    by_job = defaultdict(Counter)
    for s in results:
        by_job[s["job_id"]].update({k: s[k] for k in ("tools", "failed", "oversized", "secrets")})
    noisy = {j: c["failed"] / c["tools"] for j, c in by_job.items() if c["tools"] and c["failed"] / c["tools"] >= 0.03}
    exposed = [s["session_id"] for s in results if s["oversized"] or s["secrets"]]
    return [item("tool_errors", "medium" if noisy else "ok", round(max(noisy.values(), default=0), 3), "<0.03 per job",
                    "; ".join(f"{j} {r:.0%}" for j, r in noisy.items()) or f"{len(results)} Muse cron sessions in 24h",
                    [s["session_id"] for s in results if s["job_id"] in noisy and s["failed"]],
                    "Repeated tool errors are a schema/prompt contract gap; read the failing calls"),
            item("model_input", "medium" if exposed else "ok", len(exposed), 0,
                    f"oversized (>20k) {sum(s['oversized'] for s in results)}, credential patterns "
                    f"{sum(s['secrets'] for s in results)} in Muse cron tool results", exposed,
                    "A Muse read path skipped redaction or its page limit")]


def memory(stores):
    """Native memory stores near their limit: intake can save new facts only by compacting entries."""
    if "status" in stores:
        return item("memory_capacity", "ok", None, f"<{MEMORY_NEAR_FULL:.0%}", "memory usage unreadable; see host_faults")
    near = {t: s for t, s in stores.items() if s["chars"] >= MEMORY_NEAR_FULL * s["limit"]}
    return item("memory_capacity", "medium" if near else "ok", len(near), f"<{MEMORY_NEAR_FULL:.0%}",
                "; ".join(f"{t} {s['chars']}/{s['limit']}" for t, s in stores.items()), list(near),
                "Intake merges or shortens entries when it has new facts; ask the assistant to tidy memory in the "
                "main session, or raise memory.memory_char_limit / memory.user_char_limit")


def jobs(owned, now):
    """Scheduled Muse jobs fire on time; a pause carries a reason."""
    scheduled = {j: job for j, job in owned.items() if "-deliver-" not in str(job.get("script"))}
    late = [j for j, job in scheduled.items() if job.get("enabled") and job.get("state") == "scheduled"
            and job.get("next_run_at") and _epoch(job["next_run_at"]) < now - H]
    silent = [j for j, job in scheduled.items() if (job.get("paused_at") or job.get("state") == "paused")
              and not job.get("paused_reason")]
    return [item("jobs_late", "high" if late else "ok", len(late), 0,
                    f"{len(late)} Muse jobs over 1h past next_run_at", late,
                    "The Hermes scheduler is not ticking; check the gateway"),
            item("jobs_paused", "low" if silent else "ok", len(silent), 0,
                    f"{len(silent)} Muse jobs paused without a reason", silent,
                    "Confirm the pause was intended; resume it otherwise")]


def deliver_stalled(store, job, now, readable=True):
    """Notices left unclaimed for three muse-deliver periods (its next_run_at - last_run_at; up to 5 go per run, a
    stale one waits for patrol, see notifier.stale): the job is missing, paused or its runs claim nothing. A job
    that never ran is jobs_late's case; unreadable host jobs are host_faults'."""
    period = job and job.get("enabled") and job.get("last_run_at") and job.get("next_run_at") and \
        _epoch(job["next_run_at"]) - _epoch(job["last_run_at"])
    grace = 3 * period if period and period > 0 else None
    due = [n for n in store.query("notice", state="scheduled") if (n["payload"].get("next_eligible") or now) < now - (grace or 0)
           and (n["payload"].get("topic") == "goal-fade" or (n["payload"].get("verified_at") or 0) >= now - D)] if store else []
    state = "unreadable" if not readable else "missing" if not job else "enabled" if job.get("enabled") else "paused"
    quiet = not due or state == "unreadable" or state == "enabled" and not grace
    level = "ok" if quiet else "low" if state == "paused" else "high"
    return item("deliver_stalled", level, len(due), 0,
                f"{len(due)} notices due and not sent" + (f" for over {grace / 60:.0f} min" if grace else "")
                + f"; muse-deliver {state}", ids(due),
                "Resume the muse-deliver job, or reinstall Muse if it is missing; check its last execution error")


def _epoch(stamp):
    from datetime import datetime
    return datetime.fromisoformat(stamp).timestamp()
