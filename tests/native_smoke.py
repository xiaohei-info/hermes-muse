"""Real Hermes integration, isolated profiles; no models or live channels used.

Run with a Hermes interpreter: python tests/native_smoke.py
Set HERMES_SOURCE to a public checkout to test that source with the same interpreter.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
if os.environ.get("HERMES_SOURCE"):
    sys.path.insert(0, os.environ["HERMES_SOURCE"])
    os.environ["PYTHONPATH"] = os.environ["HERMES_SOURCE"] + os.pathsep + os.environ.get("PYTHONPATH", "")


def main():
    with tempfile.TemporaryDirectory(prefix="hermes-muse-integration-") as temporary:
        base = Path(temporary).resolve()
        homes = [base / "a", base / "b"]
        for home in homes:
            home.mkdir()
            (home / "config.yaml").write_text("plugins:\n  enabled: [hermes-muse]\ntimezone: UTC\n")
            (home / "SOUL.md").write_text("Keep this identity exactly.\n")
            (home / "memories").mkdir()
            for name in ("USER.md", "MEMORY.md"):
                (home / "memories" / name).write_text("Existing private information.\n")
            shutil.copytree(PROJECT, home / "plugins/hermes-muse", ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".hermes-core"))
        # Bind a scratch home before importing any Hermes module.
        os.environ["HERMES_HOME"] = str(homes[0])
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import discover_plugins, get_plugin_manager, render_system_prompt_sections
        from tools.skills_tool import skill_view
        from tools.registry import registry
        from cron.jobs import list_jobs, pause_job, get_job
        from cron.scheduler_script import _run_job_script
        from cron.scheduler_prompt import _parse_wake_gate
        from hermes_muse.host import HermesHost, profile_scope
        from hermes_muse.store import Store
        first_ids = None
        for index in (0, 1, 0):
            home = homes[index]
            token = set_hermes_home_override(home)
            try:
                discover_plugins(force=True)
                manager = get_plugin_manager()
                loaded = manager._plugins.get("hermes-muse")
                assert loaded and loaded.enabled, repr(loaded)
                jobs = list_jobs(include_disabled=True)
                assert len(jobs) == 6, [(j["name"], j["id"]) for j in jobs]
                for key, schedule in (("weekly-governance-review", "15 21 * * 0"),
                                      ("monthly-system-audit", "40 10 1 * *")):
                    job = next(j for j in jobs if j["name"] == "muse-" + key)
                    assert job["deliver"] == "bot-chat", job
                    assert schedule in str(job["schedule"]), job
                    assert "hermes-muse:companion" in str(job), job
                    ok, gate = _run_job_script("hermes-muse-" + key + ".py", workdir=str(home / "muse"))
                    assert ok and _parse_wake_gate(gate), (ok, gate)
                # Empty local state is not evidence that connections or native memory have no changes.
                for key in ("proactive-watch", "memory-upkeep", "nightly-review", "feed-pulse"):
                    ok, gate = _run_job_script("hermes-muse-" + key + ".py", workdir=str(home / "muse"))
                    assert ok and _parse_wake_gate(gate), (key, ok, gate)
                assert not any("skill-audit" in j["name"] for j in jobs)
                ids = {j["id"] for j in jobs}
                if index == 0 and first_ids is not None:
                    assert first_ids == ids, "Reload duplicated jobs"
                    assert not get_job(next(iter(first_ids)))["enabled"], "Reload silently resumed a paused job"
                if index == 0 and first_ids is None:
                    first_ids = ids
                    pause_job(next(iter(ids)), reason="user paused")
                prompt = render_system_prompt_sections({"session_id": "integration"})
                rendered = str(prompt)
                assert str(home / "muse") in rendered, rendered
                assert str(homes[1 - index] / "muse") not in rendered
                skill = skill_view("hermes-muse:companion")
                assert "Goal" in str(skill) or "goal" in str(skill), str(skill)
                entry = registry.get_entry("muse_manage")
                assert entry, "Plugin tool absent"
                status = json.loads(entry.handler({"action": "context"}))
                assert status["ok"], status
                assert status["result"]["workspace"] == str(home / "muse")
                # Exercise the actual native finalizer with the registered plugin hook.
                from types import SimpleNamespace
                import time, uuid
                from cron.executions import create_execution, mark_execution_running, finish_execution
                from agent.turn_finalizer import apply_llm_output_transform
                runtime = entry.handler.__self__
                from agent.subagent_lifecycle import bind_subagent_parent
                from unittest.mock import patch
                from hermes_muse.research import start as start_research
                parent = SimpleNamespace(valid_tool_names={"delegate_task"})
                with bind_subagent_parent(parent), patch("tools.delegate_tool.delegate_task", return_value=json.dumps({"status": "dispatched", "delegation_id": "isolated-native"})) as dispatch:
                    batch = start_research(runtime.store, runtime.ctx, {"items": ["Check fixture A", "Check fixture B"]})
                    assert batch["total"] == 2
                    assert dispatch.call_args.kwargs["parent_agent"] is parent
                    assert dispatch.call_args.kwargs["background"] is True
                notice = runtime.service.notification_add({"event_key": uuid.uuid4().hex, "message": "Verified test body.",
                    "rationale": "Isolated native test", "sources": ["test fixture"], "verified_at": time.time(),
                    "expires": time.time() + 3600, "priority": "urgent"})
                patrol = runtime.host.manifest()["fixed"]["proactive-watch"]
                attempt = create_execution(patrol, source="test")
                mark_execution_running(attempt["id"])
                prepared = json.loads(entry.handler({"action": "notification_prepare", "data": {"id": notice["id"]}},
                    task_id="cron:" + patrol + ":" + attempt["id"], session_id="native-patrol"))["result"]
                agent = SimpleNamespace(session_id="native-patrol", model="test", platform="cron")
                final, changed, _ = apply_llm_output_transform(agent, "Status: dispatching", turn_id="native-turn")
                assert changed and final == prepared["final_response"] and "Verified test body." in final
                # Compare our read-only receipt lookup with the actual host producer key.
                from cron.scheduler_delivery import _deliver_to_bot_chat
                from hermes_muse.host import bot_receipt_key
                with patch("tools.bot_live_delivery.read_delivery_result", return_value=None), \
                     patch("cron.bot_chat_delivery.read_pending", return_value=None), \
                     patch("tools.bot_live_delivery.find_canonical_live_owner", return_value={"test": True}), \
                     patch("tools.bot_live_delivery.deliver_to_live_owner", side_effect=lambda home, owner, message, **kw: {"status": "queued", "message": message}) as deliver:
                    _deliver_to_bot_chat({"id": patrol, "name": "muse-proactive-watch", "execution_id": attempt["id"]}, final, "")
                    assert deliver.call_args.kwargs["delivery_id"] == bot_receipt_key(home, patrol, attempt["id"])
                context = json.loads(entry.handler({"action": "context"}, task_id="cron:" + patrol + ":" + attempt["id"]))["result"]
                assert context["nightly_user_signals"] == []
                finish_execution(attempt["id"], success=True, delivery_outcome="delivered")
                runtime.host.reconcile()
                assert runtime.store.read("notification", notice["id"])["status"] == "sent"
                ok, gate = _run_job_script("hermes-muse-memory-upkeep.py", workdir=str(home / "muse"))
                assert ok and _parse_wake_gate(gate), (ok, gate)
                assert (home / "SOUL.md").read_text() == "Keep this identity exactly.\n"
                assert (home / "memories/USER.md").read_text() == "Existing private information.\n"
                assert (home / "memories/MEMORY.md").read_text() == "Existing private information.\n"
                # A genuine host-owned governance run receives the same Bot contract,
                # while its recommendations remain evidence rather than user intent.
                weekly = runtime.host.manifest()["fixed"]["weekly-governance-review"]
                review_attempt = create_execution(weekly, source="test")
                mark_execution_running(review_attempt["id"])
                review_context = json.loads(entry.handler({"action": "context"},
                    task_id="cron:" + weekly + ":" + review_attempt["id"], session_id="native-review"))
                assert review_context["ok"]
                staged = runtime.service.notification_add({"event_key": uuid.uuid4().hex, "message": "A future patrol candidate.",
                    "rationale": "Isolated test", "sources": ["fixture"], "verified_at": time.time(),
                    "expires": time.time() + 3600, "priority": "urgent"})
                report_candidate = json.loads(entry.handler({"action": "notification_prepare", "data": {"id": staged["id"]}},
                    task_id="cron:" + weekly + ":" + review_attempt["id"], session_id="native-review"))["result"]
                assert report_candidate["status"] == "pending" and report_candidate["final_response"] == "[SILENT]"
                assert not runtime.store.read("notification", staged["id"]).get("execution_id")
                review_agent = SimpleNamespace(session_id="native-review", model="test", platform="cron")
                report, changed, _ = apply_llm_output_transform(review_agent, "A verified review; proposed changes are not applied.", turn_id="review-turn")
                assert changed and report.startswith("[Hermes Muse internal delivery]")
                assert report.endswith("A verified review; proposed changes are not applied.")
                assert "The user is the audience" in report
                finish_execution(review_attempt["id"], success=True, delivery_outcome="delivered")
                if index == 1:
                    # Native read-only history must include completed answers, not just requests.
                    from hermes_state import SessionDB
                    from hermes_muse.conversation import read_conversation
                    native_db = SessionDB(db_path=home / "state.db")
                    native_db.create_session("native-history", source="cli", chat_type="private")
                    native_db.append_message("native-history", "user", "Please diagnose this screenshot.")
                    native_db.append_message("native-history", "assistant", "The database diagnosis is finished; no new screenshot is needed.")
                    native_db.create_session("group-history", source="telegram", chat_type="group")
                    native_db.append_message("group-history", "user", "Group-only private context")
                    native_db.append_message("native-history", "assistant", tool_calls=[{"id": "native-write", "function": {"name": "write_file", "arguments": '{"path":"goal.md"}'}}])
                    native_db.append_message("native-history", "tool", "Saved goal.md", tool_name="write_file", tool_call_id="native-write")
                    native_db.create_session("audit-child", source="delegate", parent_session_id="native-history", chat_type="private")
                    native_db.append_message("audit-child", "tool", "Child result", tool_name="inspect", tool_call_id="child-call")
                    native_db.close()
                    runtime.store.write("session", "native-history", {"id": "native-history", "last_signal": time.time()})
                    audit_response = json.loads(entry.handler({"action": "operations_read"}))
                    assert audit_response["ok"], audit_response
                    audit = audit_response["result"]
                    assert audit["available"] and not audit["gaps"], audit
                    assert {"native-history", "audit-child"} <= {e["session_id"] for e in audit["events"]}, audit
                    assert any(e.get("related_call", {}).get("call", {}).get("id") == "native-write" for e in audit["events"])
                    assert all(e["session_id"] != "group-history" for e in audit["events"])
                    runtime.service.operations.complete({"token": audit["token"], "summary": "Native read-only operation evidence verified"})
                    history = read_conversation(home, "native-history", time.time() - 86400)
                    assert history["available"], history
                    assert any("diagnosis is finished" in m["text"] for m in history["messages"]), history
                    assert not read_conversation(home, "group-history", 0)["available"]
                    runtime.service.signal("history-user", "native-history", "Please diagnose this screenshot.")
                    stale = runtime.service.notification_add({"event_key": "screenshot-stale", "message": "Please send another screenshot.",
                        "rationale": "Regression fixture", "sources": ["fixture"], "verified_at": time.time(), "expires": time.time()+3600})
                    review = runtime.service.notification_review({"id": stale["id"], "conversation_revisions": {"native-history": history["revision"]},
                        "verdict": "resolved", "reason": "Native history confirms the completed diagnosis was already delivered"})
                    assert review["notification"]["status"] == "cancelled"
                    # Migrate only pristine old defaults; preserve explicit edits.
                    preference_path = home / "muse/PROACTIVE_PREFERENCES.md"
                    template = (PROJECT / "templates/PROACTIVE_PREFERENCES.md").read_text()
                    old_template = template.replace('"ordinary_per_day": null', '"ordinary_per_day": 1')
                    preference_path.write_text(old_template)
                    runtime.host.initialize()
                    assert runtime.service.preferences()["ordinary_per_day"] is None
                    preference_path.write_text(old_template + "\nMy explicit limit must remain.\n")
                    runtime.host.initialize()
                    assert runtime.service.preferences()["ordinary_per_day"] == 1
                # User edits to workspace templates survive a second initialization.
                prefs = home / "muse/TOOLS.md"
                prefs.write_text("User maintained source list.\n")
                HermesHost(Store(home), plugin_root=home / "plugins/hermes-muse").initialize()
                assert prefs.read_text() == "User maintained source list.\n"
                assert len(list_jobs(include_disabled=True)) == 6
            finally:
                reset_hermes_home_override(token)
        for home in homes:
            with profile_scope(home):
                assert get_plugin_manager().unload("hermes-muse")
                shutil.rmtree(home / "plugins/hermes-muse")
                ok, output = _run_job_script("hermes-muse-memory-upkeep.py", workdir=str(home / "muse"))
                assert ok and not _parse_wake_gate(output), (ok, output)
                assert (home / "muse/install.json").exists()
                # Host remove intentionally leaves native tasks for the documented cleanup flow.
                assert len(list_jobs(include_disabled=True)) == 6
        from native_companion_smoke import run as companion_checks
        companion_checks(base / "companion")
        print("PASS: native registration, Skill, prompt, tools, six Cron jobs, real script gates, A->B->A isolation, idempotent reload, preserved native files and harmless removed-plugin launchers")


if __name__ == "__main__":
    main()
