"""WP3 Health acceptance and contract check on synthetic temporary homes (design 2.8, 7.3 A3/A4/A7–A10).

Reproduces the audited failures on a native Hermes + Store v2 home, re-checks a migrated 0.3.16 store,
and verifies health.json, the four alert exits, read-only Store access and the no_agent entrypoint.
Run with a Hermes interpreter: PYTHONPATH=/path/to/hermes-agent python tests/health_acceptance.py
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))
H, D = 3600, 86400
FAILED = []


def check(name, ok, detail):
    print(f"{name} {'PASS' if ok else 'FAIL'} {json.dumps(detail, ensure_ascii=False, sort_keys=True)}")
    if not ok:
        FAILED.append(name)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_store(home, now, host):
    """Store v2 holding today's failure patterns (synthetic ids only). Fields Health reads come from the kernel
    writers; raw creates only reproduce states the kernel prevents (oneshot captured, duplicate sends, stuck rows)."""
    from hermes_muse.kernel import Kernel, goals, notifier, review, sources
    from hermes_muse.kernel.store import Store
    s = Store.for_home(home, clock=lambda: now)
    k = Kernel(home, adapter=host, store=s, clock=lambda: now)
    s.create("signal", "chat:long", {"source": "cli"}, now=now - 80 * H)          # watermark stuck, tick not run
    s.create("signal", "once:1", {"source": "oneshot"}, now=now - H)               # E16 oneshot captured
    for i in range(2):  # urgent sent twice by v2, before the local day of the draft below (not its urgent_per_day)
        s.create("notice", "src:msgaaa", {"priority": "urgent", "strong_key": True,
                 "delivery_key": notifier.delivery_key("src:msgaaa", i)}, state="sent", now=now - (3 - i) * D, dedupe=False)
    for i in range(2):                                                             # migrated 0.3.x history: not counted
        s.create("notice", "src:msgold", {"priority": "urgent", "strong_key": True, "v1_id": f"old{i}"}, state="sent",
                 now=now - (2 - i) * D, dedupe=False)
    notifier.draft(k, text="Thread bbb", priority="urgent", upstream_id="thr-bbb", now=now - 10 * H)  # eligible, unsent
    s.create("notice", "src:ccc", {"delivery_key": notifier.delivery_key("src:ccc")}, state="unknown",
             now=now - 3 * H)                                                      # a v2 send went unknown
    s.create("notice", "src:oldq", {"v1_id": "oldq"}, state="unknown", now=now - 3 * H)  # migrated 0.3.x: not counted
    s.create("goal", "stale-goal", {}, deadline=now - 12 * D, now=now - 20 * D)  # next_check 12 days old
    goals.create(k, title="Learn piano", criteria="Play one piece", by="user", session_id="chat", now=now - 20 * D)
    goals.fade(k, now)                                                             # dormant: fade_at 6 days ago
    s.create("run", "exec-stuck", {}, now=now - 3 * H)
    s.create("run", "exec-ok", {}, state="ok", now=now - 2 * H)
    s.create("run", "exec-bad", {}, state="degraded", now=now - H)
    s.create("packet", "intake:1", {}, state="expired", now=now - 6 * H)
    s.create("packet", "intake:2", {}, state="submitted", now=now - 5 * H)
    for _ in range(3):
        sources.record(s, "calendar:home", error="timeout", now=now - H)           # 3 in a row: Health
    sources.record(s, "mail:work", error="timeout", now=now - H)                   # 1: not yet
    review.record(k, "review:chat:8", "agent_gap", "claimed sent without a send", now - H, rules=["claim_without_write"])
    s.create("finding", "review:chat:9", {}, now=now - H)                          # migrated 0.3.x finding, no evidence
    return s


def main():
    from native_host_contract import finish, seed_state
    from hermes_muse import health
    from hermes_muse.health import invariants
    from hermes_muse.host import HostAdapter, profile_scope
    from hermes_muse.kernel.store import Store

    from contextlib import ExitStack, closing

    with tempfile.TemporaryDirectory(prefix="muse-health-") as temporary, ExitStack() as cleanup:
        base = Path(temporary).resolve()
        home = base / "profile"
        (home / "workspace").mkdir(parents=True)
        (home / "config.yaml").write_text("timezone: UTC\nplugins:\n  enabled: [hermes-muse]\n  entries:\n"
                                          "    hermes-muse:\n      settings: {health_deliver: telegram}\n")
        os.environ.update(HERMES_HOME=str(home), HERMES_IGNORE_USER_CONFIG="1")
        gone = base / "gone"
        gone.mkdir()
        cleanup.callback(os.chdir, os.getcwd())
        os.chdir(gone)
        if os.name != "nt":
            gone.rmdir()  # Health must never need the process cwd
        # Windows keeps an unrelated cwd: ntpath.realpath requires getcwd even for absolute paths.

        # -- today's failures on the current Hermes ------------------------------------------------
        host = HostAdapter(home)
        entry = base / "entry.py"
        entry.write_text("print('')\n")
        job = host.cron.ensure("patrol", schedule="every 30m", entry=entry, prompt="Patrol.", deliver="bot-chat")
        seed_state(home, job["id"])  # Bot Chat cwd=/workspace, local-* cron session, oneshot, unknown 'local' source
        with closing(sqlite3.connect(home / "state.db")) as db, db:
            for content in ('{"ok": true}', '{"error": "missing request_id"}', "x" * 25000,
                            "token sk-" + "a1b2c3d4" * 3, '{"success": true}'):
                db.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES ('local-run','tool',?,?)",
                           (content, time.time()))
        with profile_scope(home):
            finish(job["id"], "failed")
            from cron.jobs import update_job
            update_job(job["id"], {"last_delivery_error": "bot_relay.deliver refused: invalid_params field=cwd"})
        now = time.time()
        store = seed_store(home, now, host)
        db_file = store.path
        before = digest(db_file)

        text = health.run(home, now=now)
        report = health.load(home)
        levels = {f["id"]: f["level"] for f in report["invariants"]}
        expected = {
            "store": "ok", "deadlines": "ok", "tick_stalled": "high", "signal_watermark": "high", "signal_parked": "ok",
            "packet_expiry": "medium", "packets_idle": "high", "notice_duplicates": "high", "notice_hanging": "medium",
            "notice_unknown": "ok", "runs_ok": "medium", "runs_unclosed": "low", "goals_missed": "high",
            "goal_fade": "medium", "sources_failing": "medium", "review_findings": "low", "drain_stopped": "ok",
            "interests_unchecked": "ok", "memory_capacity": "ok",
            "probe.symbols": "ok", "probe.cron_sessions": "ok", "probe.delivery_semantics": "medium",
            "probe.delivery_target": "high", "probe.signal_purity": "high", "probe.config_location": "ok",
            "probe.home": "ok", "delivery": "high", "executions": "ok", "tool_errors": "medium",
            "model_input": "medium", "jobs_late": "ok", "jobs_paused": "ok", "deliver_stalled": "high", "host_faults": "ok"}
        by = {f["id"]: f for f in report["invariants"]}
        check("H1 delivery failure is high within one run", levels["delivery"] == "high"
              and "invalid_params field=cwd" in by["delivery"]["detail"],
              {"delivery": levels["delivery"]})
        check("only v2 deliveries count: migrated 0.3.x duplicate sends and unknowns are not reported",
              by["notice_duplicates"]["value"] == 1 and "1 failed/unknown notices" in by["delivery"]["detail"],
              {k: [by[k]["value"], by[k]["detail"]] for k in ("notice_duplicates", "delivery")})
        check("A4 probe->level mapping (missing=high, degraded=medium)",
              all(levels[k] == expected[k] for k in expected if k.startswith("probe.")),
              {k: levels[k] for k in levels if k.startswith("probe.")})
        check("kernel-written fields: fade_at from goals.fade, fail_streak/health from sources.record (3 in a row only), "
              "evidence from review.record (only the migrated finding is bare)",
              by["goal_fade"]["value"] == 1 and by["goal_fade"]["evidence"][0].startswith("goal:g")
              and by["sources_failing"]["value"] == 1
              and "1 open without evidence" in by["review_findings"]["detail"],
              {k: [by[k]["value"], by[k]["evidence"], by[k]["detail"]] for k in ("goal_fade", "sources_failing", "review_findings")})
        purity = by["probe.signal_purity"]["detail"]
        check("signal_purity gets 24h captured sources from Store; unknown 'local' reported unclassified",
              "['oneshot']" in purity and "'local'" in purity, {"detail": purity})
        check("A7/A8/A9/A10 and kernel watchdogs reproduce today's issues", levels == expected,
              {k: [levels.get(k), v] for k, v in expected.items() if levels.get(k) != v} or {"invariants": len(levels)})
        shape = set(report) >= {"schema", "profile", "generated_at", "generated_ts", "level", "alert_fingerprint",
                                "invariants", "faults"} and all(
            set(f) == {"id", "level", "value", "threshold", "detail", "evidence", "fix", "first_seen"}
            and (f["level"] == "ok") == (f["first_seen"] is None) for f in report["invariants"])
        check("health.json schema", shape and report["level"] == "high", {"keys": sorted(report), "level": report["level"]})
        check("Store opened read-only (state-v2.db bytes unchanged)", digest(db_file) == before, {})
        check("stdout exit: alert text on first change", text.startswith("Muse health (profile): high") and "delivery" in text,
              {"first_line": text.splitlines()[0]})
        stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        ran = {"enabled": True, "last_run_at": stamp(now - 600), "next_run_at": stamp(now)}  # a 10-minute period
        stalled = {name: invariants.deliver_stalled(store, job, now, readable)["level"] for name, job, readable in (
            ("ran", ran, True), ("four_hourly", {**ran, "last_run_at": stamp(now - 4 * H)}, True),
            ("never_ran", {"enabled": True, "next_run_at": stamp(now)}, True), ("paused", {**ran, "enabled": False}, True),
            ("unreadable", None, False))}
        check("deliver_stalled: a notice due for 10h is high with no muse-deliver job or past 3 of its periods (next_run_at - "
              "last_run_at); ok within them, before its first run or when host jobs are unreadable; low while paused",
              "missing" in by["deliver_stalled"]["detail"] and by["deliver_stalled"]["value"] == 1
              and stalled == {"ran": "high", "four_hourly": "ok", "never_ran": "ok", "paused": "low", "unreadable": "ok"},
              {"detail": by["deliver_stalled"]["detail"], "levels": stalled})

        again = health.run(home, now=now + 60)
        report2 = health.load(home)
        first = {f["id"]: f["first_seen"] for f in report["invariants"]}
        check("stdout exit silent when nothing changed; first_seen kept",
              again == "" and all(f["first_seen"] == first[f["id"]] for f in report2["invariants"]),
              {"stdout": again})
        line = health.injection(home, now=now + 60)
        check("injection exit: one line naming high findings", bool(line) and "\n" not in line and "delivery" in line,
              {"line": (line or "")[:120]})
        stale = health.injection(home, now=now + 3 * H)
        check("injection exit: stale health.json is itself an alert", "has not run since" in (stale or ""), {"line": stale})

        import importlib.util
        spec = importlib.util.spec_from_file_location("muse_dashboard_api", PROJECT / "dashboard" / "plugin_api.py")
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        api.home = lambda selected_profile=None: home  # skip the host install lookup
        served = api.health()
        check("dashboard exit: /health serves health.json", served == health.load(home)
              and any(r.path.endswith("/health") for r in api.router.routes), {"level": served.get("level")})

        # -- the no_agent cron entrypoint ----------------------------------------------------------
        cron_job = health.ensure_cron(host, "bot-chat")
        launcher = home / "scripts" / "hermes-muse-health.py"
        ran = subprocess.run([sys.executable, str(launcher)], cwd=base, capture_output=True, text=True,
                             env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)})
        report3 = health.load(home)
        check("no_agent entry runs the check and rewrites health.json",
              cron_job["no_agent"] and cron_job["schedule_display"] == "every 30m" and ran.returncode == 0
              and report3["generated_ts"] > now + 60 - 120 and report3["generated_ts"] != report2["generated_ts"],
              {"rc": ran.returncode, "stderr": ran.stderr[-300:]})
        again = health.ensure_cron(host, "bot-chat")
        check("backup exit: health_deliver is a second route of the health job (Hermes delivers its stdout to both); "
              "no job per alert", cron_job["deliver"] == again["deliver"] == "bot-chat,telegram"
              and not [j for j in host.cron.jobs().values() if "-deliver-" in j["script"]],
              {"deliver": [cron_job["deliver"], again["deliver"]]})

        # -- a healthy profile is silent; recovery is announced --------------------------------------
        clean = base / "clean"
        (clean / "muse").mkdir(parents=True)
        (clean / "config.yaml").write_text("plugins:\n  enabled: [hermes-muse]\n")
        Store.for_home(clean)
        quiet = health.run(clean)
        check("healthy profile: level ok and silent", quiet == "" and health.load(clean)["level"] == "ok",
              {f["id"]: f["level"] for f in health.load(clean)["invariants"] if f["level"] != "ok"})
        cs = Store.for_home(clean)
        sig = cs.create("signal", "chat:2", {"source": "cli"}, now=time.time() - 3 * H)
        alert = health.run(clean)
        cs.transition(sig["id"], "disposed", state="new", version=sig["version"], reason="test")
        recovered = health.run(clean)
        check("alert then recovery message", "signal_watermark" in alert and "recovered" in recovered,
              {"alert": alert.splitlines()[-1:], "recovered": recovered})
        none = base / "none"
        none.mkdir()
        check("missing Store v2 is high, never a crash", invariants.worst(
            *(f["level"] for f in health.check(HostAdapter(none)) if f["id"] == "store")) == "high", {})

        # -- an old 0.3.16 store, migrated, reproduces its stuck watermark and duplicate sends -----
        from store_v2_acceptance import NOW, sample
        from hermes_muse.kernel.store.migrate import migrate
        old = base / "old"
        sample(old, "0.3.16")
        migrate(old, now=NOW)
        found = {f["id"]: f for f in health.check(HostAdapter(old), now=NOW)}
        check("migrated 0.3.16 store: stuck watermark found; its 0.3.x duplicate sends are history, not a v2 failure",
              found["signal_watermark"]["level"] == "high" and found["notice_duplicates"]["level"] == "ok",
              {k: [found[k]["level"], found[k]["value"]] for k in ("signal_watermark", "notice_duplicates")})

    print("FAIL " + ", ".join(FAILED) if FAILED else "PASS health_acceptance")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
