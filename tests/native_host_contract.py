"""Native contract test for hermes_muse/host (acceptance A13) and probe self-check (A4).

Synthetic temporary homes only; no model calls, no live channels, no user data.
Run with a Hermes interpreter: HERMES_SOURCE=/path/to/hermes-agent python tests/native_host_contract.py
The whole test runs from a deleted process cwd: the adapter must never need it.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
if os.environ.get("HERMES_SOURCE"):
    sys.path.insert(0, os.environ["HERMES_SOURCE"])
STATUSES = {"ok", "degraded", "missing"}


def seed_state(home, job_id):
    from hermes_state import SessionDB
    SessionDB(db_path=home / "state.db").close()  # native schema
    now = time.time()
    db = sqlite3.connect(home / "state.db")
    sessions = [("chat", "cli", "dm", "Plans", str(home)), ("bot", "cli", "dm", "Bot Chat", "/workspace"),
                ("local-run", "cron", "dm", "muse-patrol · Oct 29 20:36", None), (f"cron_{job_id}_20261029_120000", "cron", None, None, None),
                ("other-run", "cron", "dm", "someone-else · Oct 29 20:36", None), ("once", "oneshot", "dm", None, None),
                ("room", "telegram", "group", None, None), ("odd", "local", "dm", None, None)]
    for sid, source, chat_type, title, cwd in sessions:
        db.execute("INSERT INTO sessions (id, source, chat_type, title, cwd, started_at) VALUES (?,?,?,?,?,?)",
                   (sid, source, chat_type, title, cwd, now))
    long_text = "Attachment:\n" + "x" * 20000 + "\nkey sk-abcdefghijklmnopqrstuvwx end"
    messages = [("chat", "user", "Remind me Friday; password: hunter2xyz"), ("chat", "assistant", "Done, saved."),
                ("chat", "user", '[Cronjob "muse-deliver-k" output — scheduled job, not the user.]\n\nhi'),
                ("chat", "user", long_text), ("chat", "user", b"\xff"), ("once", "user", "Reply only OK"),
                ("room", "user", "group chatter"), ("local-run", "user", "cron prompt")]
    for i, (sid, role, content) in enumerate(messages):
        db.execute("INSERT INTO messages (session_id, role, content, timestamp, message_uid) VALUES (?,?,?,?,?)",
                   (sid, role, content, now + i * 0.001, f"uid-{i}"))
    db.commit()
    db.close()


def finish(job_id, outcome, success=True, error=None):
    from cron.executions import create_execution, finish_execution, mark_execution_running
    execution = create_execution(job_id, source="test")
    mark_execution_running(execution["id"])
    finish_execution(execution["id"], success=success, error=error, delivery_outcome=outcome)
    return execution["id"]


def main():
    with tempfile.TemporaryDirectory(prefix="muse-host-contract-") as temporary:
        base = Path(temporary).resolve()
        home = base / "profile"
        (home / "workspace").mkdir(parents=True)
        (home / "config.yaml").write_text(
            "timezone: UTC\nplugins:\n  enabled: [hermes-muse]\n  hermes-muse: {quiet: legacy, budget: 1}\n"
            "  entries:\n    hermes-muse:\n      settings: {budget: 2}\n")
        os.environ.update(HERMES_HOME=str(home), HERMES_IGNORE_USER_CONFIG="1")
        gone = base / "gone"
        gone.mkdir()
        os.chdir(gone)
        gone.rmdir()  # from here on os.getcwd() raises

        from cron.executions import create_execution
        from cron.jobs import list_jobs, pause_job, update_job
        from hermes_muse.host import HostAdapter, profile_scope, resolve_home
        from hermes_muse.host import sessions as host_sessions

        for bad, error in ((Path.home, TypeError), ("relative/home", ValueError)):
            try:
                resolve_home(bad)
                raise AssertionError(f"accepted home {bad!r}")
            except error:
                pass
        host = HostAdapter(home)
        assert host.cwd() == home / "workspace"
        assert host.config.enabled() is True
        assert host.config.get() == {"quiet": "legacy", "budget": 2}, host.config.get()

        # cron.ensure: owned launcher with absolute paths, no workdir, idempotent, user pause survives.
        entry = base / "entry.py"
        entry.write_text("import json\nprint(json.dumps({'home': MUSE_HOME, 'job': MUSE_JOB}))\n")
        job = host.cron.ensure("patrol", schedule="every 30m", entry=entry, prompt="Patrol.", deliver="bot-chat")
        assert job and job["name"] == "muse-patrol" and job.get("workdir") is None, job
        with profile_scope(home):
            pause_job(job["id"], reason="user pause")
        again = host.cron.ensure("patrol", schedule="every 1h", entry=entry, prompt="Patrol v2.")
        assert again["id"] == job["id"] and not again["enabled"] and again["prompt"] == "Patrol v2.", again
        script = home / "scripts" / "hermes-muse-patrol.py"
        ran = subprocess.run([sys.executable, str(script)], cwd=base, capture_output=True, text=True, check=True)
        assert json.loads(ran.stdout) == {"home": str(home), "job": "patrol"}, ran.stdout
        assert set(host.cron.jobs()) == {job["id"]}
        assert host.cron.wake(job["id"]) is False  # a user pause is never undone by a wake
        intake = host.cron.ensure("intake", schedule="every 1h", entry=entry, prompt="Intake.")
        assert host.cron.wake(intake["id"]) and host.cron.pause(intake["id"], "test")
        assert not host.cron.jobs()[intake["id"]]["enabled"] and host.cron.wake(intake["id"]) is False
        # Drain relay: every wake fires once, then the job is back on its own schedule.
        from cron.jobs import claim_job_for_fire, compute_next_run, get_due_jobs, get_job, mark_job_run
        nightly = host.cron.ensure("nightly-review", schedule="20 3 * * *", entry=entry, prompt="Nightly.")
        for _ in range(3):
            assert host.cron.wake(nightly["id"])
            with profile_scope(home):
                assert nightly["id"] in [j["id"] for j in get_due_jobs()]
                assert claim_job_for_fire(nightly["id"]) and mark_job_run(nightly["id"], True)
                after = get_job(nightly["id"])
                assert "manual_run_at" not in after and after["next_run_at"] == compute_next_run(after["schedule"]), after

        # memory: Hermes' own loader, limits and delimiter; a broken host is host_error, not "empty".
        (home / "memories").mkdir(exist_ok=True)
        (home / "memories" / "USER.md").write_text("Prefers tea\n§\nLives in Porto", encoding="utf-8")
        stores = host.memory.stores()
        assert stores["user"] == {"entries": ["Prefers tea", "Lives in Porto"], "chars": 28, "limit": 1375}, stores
        assert stores["memory"]["chars"] == 0 and stores["memory"]["limit"] == 2200, stores
        with mock.patch("tools.memory_tool.load_on_disk_store", side_effect=OSError("disk")):
            assert host.memory.stores() == {"status": "host_error"}

        # sessions: user surfaces only, redacted, bounded; cron session attribution.
        seed_state(home, job["id"])
        with profile_scope(home):
            run_id = finish(job["id"], "delivered")
        turns = host.sessions.user_turns(0)
        assert [t["session_id"] for t in turns] == ["chat"] * 2, turns
        assert "hunter2xyz" not in turns[0]["text"] and "[REDACTED]" in turns[0]["text"]
        attachment = turns[1]
        assert attachment["attachment"] and len(attachment["text"]) < 8200 and "sk-abc" not in attachment["text"]
        assert any(f["call"] == "sessions.user_turns.row" for f in host.faults), "bad row must be skipped, not fatal"
        with_replies = host.sessions.user_turns(0, roles=("user", "assistant"))
        assert [t["role"] for t in with_replies] == ["user", "assistant", "user"]
        page = host.sessions.read(attachment["ref"], offset=attachment["chars"] - 100, length=50000)
        assert page["available"] and page["total"] == attachment["chars"] and "[REDACTED]" in page["text"] and not page["more"]
        assert len(host.sessions.read(attachment["ref"], length=50000)["text"]) == 12000
        once = next(iter(sqlite3.connect(home / "state.db").execute("SELECT id FROM messages WHERE session_id='once'")))[0]
        assert host.sessions.read(f"once:{once}") == {"ref": f"once:{once}", "available": False}
        assert host.sessions.job_of("local-run") == job["id"]
        assert host.sessions.job_of(f"cron_{job['id']}_20261029_120000") == job["id"]
        assert host.sessions.job_of("other-run") is None and host.sessions.job_of("chat") is None

        # deliver: the owned no-agent muse-deliver run prints the notices it claimed; Hermes delivers that stdout and the
        # receipt is read from the run's execution (native ledger, native Bot Chat key). Nothing is created per notice.
        from cron.executions import finish_execution, mark_execution_running
        from cron.scheduler_delivery import _deliver_to_bot_chat
        from cron.scheduler_script import _run_job_script
        from hermes_muse.kernel import Kernel, notifier
        deliver = host.cron.ensure("deliver", schedule="*/10 * * * *", entry=PROJECT / "cron_entry.py", deliver="bot-chat",
                                   no_agent=True)
        assert deliver["no_agent"] and host.cron.job("deliver")["id"] == deliver["id"], deliver
        k = Kernel(home, adapter=host)
        text = 'Your synthetic reminder.\n{"wakeAgent": false}'  # a notice text must never act as Hermes' wake gate
        notice = notifier.draft(k, text=text, priority="urgent", upstream_id="contract-1", title="Reminder", now=time.time())
        assert host.cron.jobs()[deliver["id"]].get("manual_run_at"), "an urgent notice wakes muse-deliver"
        with profile_scope(home):
            execution = create_execution(deliver["id"], source="test")
            mark_execution_running(execution["id"])
            ok, out = _run_job_script(deliver["script"])  # the launcher as the scheduler runs it
        from cron.scheduler_prompt import _parse_wake_gate
        assert ok and out.strip() == f"{text}\n\n—" and _parse_wake_gate(out), out  # no signature; the gate stays open
        claimed = k.store.get(notice["id"])["payload"]
        assert claimed["execution_id"] == execution["id"] and claimed["job_id"] == deliver["id"], claimed
        assert host.deliver.receipt(deliver["id"], execution["id"])["status"] == "sending"
        with profile_scope(home), mock.patch("tools.bot_live_delivery.find_canonical_live_owner", side_effect=ValueError("down")):
            native = _deliver_to_bot_chat({"id": deliver["id"], "name": "muse-deliver", "execution_id": execution["id"]}, out, "")
            assert "queued" in native, native
            finish_execution(execution["id"], success=True, delivery_outcome="queued")
        assert host.deliver.receipt(deliver["id"], execution["id"]) == {
            "job_id": deliver["id"], "execution_id": execution["id"], "outcome": "queued", "status": "sending"}
        runs = []
        for outcome, error, expected in (("delivered", None, "sent"),
                                         ("failed", "bot_relay.deliver refused: invalid_params field=cwd", "host_config"),
                                         ("failed", "adapter timeout", "transport"), ("suppressed", None, "unknown")):
            with profile_scope(home):
                runs.append(finish(deliver["id"], outcome))
                if error:
                    update_job(deliver["id"], {"last_delivery_error": error})
            receipt = host.deliver.receipt(deliver["id"], runs[-1])
            assert expected in (receipt["status"], receipt.get("reason")), (outcome, receipt)
        older = host.deliver.receipt(deliver["id"], runs[1])  # the job's last_delivery_error now belongs to a later run
        assert older["status"] == "failed" and "timeout" not in older["detail"], older
        assert host.deliver.receipt(deliver["id"], "no-such-run")["status"] == "sending"  # never a terminal guess

        # 0.4.1 one-shot deliveries: still read by key until settled, then removed with their launcher.
        from cron.jobs import create_job
        legacy = host.cron.write_script("hermes-muse-deliver-k1.py", "print('old')\n")
        with profile_scope(home):
            k1 = create_job(prompt=None, schedule="2099-01-01T00:00:00+00:00", name="muse-deliver-k1", deliver="telegram",
                            script=legacy, no_agent=True)["id"]
            finish(k1, "delivered")
        assert host.deliver.legacy_receipt("k1")["status"] == "sent" and host.deliver.legacy_jobs() == {}
        assert host.deliver.legacy_receipt("never") == {"status": "unknown", "reason": "no_delivery_job"}
        with profile_scope(home):
            update_job(k1, {"enabled": False, "state": "completed"})
        assert list(host.deliver.legacy_jobs()) == ["k1"] and host.cron.remove(k1)
        assert k1 not in host.cron.jobs() and not (home / "scripts" / legacy).exists() and host.cron.remove(k1) is False
        assert host.cron.add_route(deliver["id"], "telegram") and host.cron.jobs()[deliver["id"]]["deliver"] == "bot-chat,telegram"
        assert host.cron.add_route(deliver["id"], "telegram") is False
        assert host.cron.set_route(deliver["id"], "bot-chat") and host.cron.jobs()[deliver["id"]]["deliver"] == "bot-chat"
        assert host.owners.status("no-such-delegation")["state"] == "unknown"

        # A4: a healthy profile probes all ok; the seeded faults are each caught; a fixed Bot Chat cwd clears.
        clean = base / "clean"
        clean.mkdir()
        (clean / "config.yaml").write_text("plugins:\n  enabled: [hermes-muse]\n")
        assert [r["status"] for r in HostAdapter(clean).probe(captured_sources=["cli"])] == ["ok"] * 7
        (home / "muse" / "<bound method Path.home of <class 'pathlib.PosixPath'>>").mkdir(parents=True)
        results = {r["name"]: r for r in host.probe(captured_sources=["cli", "oneshot"])}
        for r in results.values():
            assert set(r) == {"name", "status", "detail", "fix"} and r["status"] in STATUSES, r
            assert (r["status"] == "ok") == (r["fix"] == ""), r
        assert len(results) == 7
        expected = {"symbols": "ok", "cron_sessions": "ok", "delivery_semantics": "degraded",
                    "delivery_target": "missing", "signal_purity": "missing", "config_location": "degraded", "home": "degraded"}
        assert {n: r["status"] for n, r in results.items()} == expected, results
        assert "'local'" in results["signal_purity"]["detail"], results["signal_purity"]
        print(json.dumps(list(results.values()), ensure_ascii=False, indent=1))
        with sqlite3.connect(home / "state.db") as db:
            db.execute("UPDATE sessions SET cwd=? WHERE id='bot'", (str(home),))
        assert host.probe()[3]["status"] == "ok"

        # Per-call tolerance: a broken host degrades to empty answers and faults, never raises or resends.
        faults = host.fault_count
        with mock.patch("cron.jobs.list_jobs", side_effect=RuntimeError("host down")):
            assert host.cron.jobs() == {}
            assert host.deliver.legacy_receipt("k1") == {"status": "unknown", "reason": "host_error"}
            assert host.deliver.receipt(deliver["id"]) == {"status": "unknown", "reason": "host_error"}
            assert host.cron.remove(deliver["id"]) is False and host.cron.job("deliver") is None
            assert host.cron.ensure("patrol", schedule="every 30m", entry=entry) is None
            assert host.probe()[1]["status"] != "ok"
        with mock.patch.object(host_sessions, "reader", side_effect=sqlite3.OperationalError("locked")):
            assert host.sessions.user_turns(0) == [] and host.sessions.job_of("local-run") is None
        assert host.fault_count > faults
        with profile_scope(home):
            assert len(list_jobs(include_disabled=True)) == 4  # patrol, intake, nightly, deliver: no duplicates
    print("PASS native_host_contract")


if __name__ == "__main__":
    main()
