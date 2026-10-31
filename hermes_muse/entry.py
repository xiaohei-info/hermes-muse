"""Pre-run script of every Muse cron job (cron_entry.py): decides whether the model wakes and with what.

Prints one JSON line. `{"wakeAgent": false, ...}` keeps the run silent (Hermes wakes the model on empty
stdout): plugin disabled, migration marker present, Muse not loaded in the Hermes process running the job
(its agent would have no Muse tools or skill), empty packet, unknown key or a watch whose goal is no
longer open. Otherwise the line carries the job's packet from build_packet (ids, refs, schema and budget
filled in by code), which Hermes hands to the model as Script Output, and the run is registered with
start_run so its outcome is computed later.
The no-agent `deliver` key prints plain text instead: the notices it claimed, or nothing (silent).
"""
from . import health
from .host import HostAdapter
from .host.sessions import clean
from .install import JOBS, migrating, owned
from .kernel import Kernel, goals, notifier
from .kernel.common import D, preferences

WEEK = 7 * D
WEEKLY_KINDS = ("signal", "notice", "goal", "feed", "finding", "interest", "idea", "run")


def silent(reason):
    return {"wakeAgent": False, "reason": reason}


def weekly(k, now):
    """Inputs of the weekly digest: the failing Health checks and 7-day counts by kind and state."""
    week = {}
    for kind in WEEKLY_KINDS:
        for e in k.store.query(kind, since=now - WEEK):
            week.setdefault(kind, {}).setdefault(e["state"], 0)
            week[kind][e["state"]] += 1
    return {"health": health.summary(k.home), "last_7_days": week}


def watch(k, key):
    job = owned(k.adapter, key)
    w = next((w for w in k.store.query("watch", state="active")
              if w["payload"].get("key") == key or job and w["payload"].get("job_id") == job["id"]), None)
    goal = w and k.store.get(f"goal:{w['payload'].get('goal_id')}")
    if not goal or goal["state"] not in goals.OPEN:
        return silent("no active watch for an open goal")
    return {"wakeAgent": True, "job": "watch", "goal": goals.item(k, goal),
            "watch": {"id": w["id"], "stop_condition": w["payload"].get("stop_condition"), "expires": w["deadline"]}}


def deliver(k, now):
    """The muse-deliver run (no model): settled 0.4.1 one-shots removed, then the notices due now are claimed for
    this execution and returned as one message, which Hermes delivers to the job's route. A `deliver` preference
    becomes that route first; this run then stays silent, since Hermes delivers it on the route it started with."""
    notifier.sweep(k)
    job = owned(k.adapter, notifier.DELIVER)
    want = job and preferences(k.home).get("deliver")
    if want and want != job.get("deliver") and k.adapter.cron.set_route(job["id"], want):
        return ""
    execution = k.adapter.cron.outcome(job["id"]) if job else None
    if not execution or execution["status"] not in ("claimed", "running"):
        return ""  # a claim must name this run's execution, or its receipt could never be read
    return notifier.message(notifier.claim(k, job, execution["execution_id"], now))


def run(home, key, now=None):
    adapter = HostAdapter(home)
    if not adapter.config.enabled():
        return silent("plugin absent or disabled")
    if migrating(adapter.home):
        return silent("migration in progress")
    if key != notifier.DELIVER and adapter.load_failed():  # muse-deliver needs no model and no Muse tool
        return silent("Hermes abandoned Muse's plugin load in this process; restart the gateway (Health: plugin_load)")
    return clean(output(Kernel(adapter.home, adapter=adapter), key, now))  # Script Output or the delivered message


def output(k, key, now=None):
    now = k.clock() if now is None else now
    k.tick(now)
    if key not in JOBS:
        return watch(k, key) if key.startswith("watch-") else silent(f"no Muse job {key!r}")
    job = JOBS[key][0]
    if job == "deliver":
        return deliver(k, now)
    if job == "weekly":
        return {"wakeAgent": True, "job": job, **weekly(k, now)}
    packet = k.build_packet(job, now)
    if packet["id"] is None:
        return silent("nothing to do")
    cron_job = owned(k.adapter, key)
    execution = k.adapter.cron.outcome(cron_job["id"]) if cron_job else None
    if execution and execution["status"] in ("claimed", "running"):
        k.start_run(job, job_id=cron_job["id"], execution_id=execution["execution_id"], packet_id=packet["id"], now=now)
    return {"wakeAgent": True, "job": job, "packet": packet}
