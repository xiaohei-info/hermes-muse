"""0.1.2 behavior plus Bot Chat delivery, exercised against real Hermes APIs."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def run(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("plugins:\n  enabled: [hermes-muse]\ntimezone: UTC\n")
    from cron.jobs import get_job, list_jobs, remove_job
    from gateway.session_context import set_session_vars, clear_session_vars
    from hermes_muse.host import profile_scope, enabled, cron_run
    from hermes_muse.runtime import Runtime
    from hermes_muse.store import stamp

    runtime = Runtime(object(), home)
    now = time.time()

    def call(operation, **data):
        result = json.loads(runtime.handle({"action": operation, "data": data}))
        assert result["ok"], (operation, result)
        return result["result"]

    with profile_scope(home):
        runtime.host.initialize()
        # Reviews persist summaries without manufacturing user activity or notices.
        for review in ("weekly-governance-review", "monthly-system-audit"):
            call("review_complete", job=review, up_to=now, summary="Evidence limited; simplify only after discussion.")
            assert call("status")["reviews"][review]["summary"].startswith("Evidence limited")
        assert not runtime.store.all("signal") and not runtime.store.all("notification")
        runtime.service.signal("user-choice", "source-session", "Track bicycles until I choose one.")
        tokens = set_session_vars(session_id="cron-session", chat_type="private", cron_session="1")
        try:
            call("goal_create", id="bicycle", title="Choose a bicycle", description="Compare options",
                 completion_criteria="User confirms a purchase", signal_id="user-choice")
            interest = call("interest_record", id="cycling", title="Cycling", signal_id="user-choice")
            runtime.service.signal("new-user-choice", "source-session", "I am still interested in cycling.")
            renewed = call("interest_record", id="cycling", title="Cycling", signal_id="new-user-choice")
            assert renewed["expires"] > interest["expires"]
            invalid = json.loads(runtime.handle({"action": "interest_record", "data": {
                "id": "cycling", "title": "Cycling", "signal_id": "fabricated"}}))
            assert not invalid["ok"], "Restoring background work must not manufacture user evidence"
            repeated = json.loads(runtime.handle({"action": "interest_record", "data": {
                "id": "cycling", "title": "Cycling", "signal_id": "new-user-choice"}}))
            assert not repeated["ok"], "Rereading a signal must not renew an interest"
            call("preferences", ordinary_per_day=2)
            assert runtime.service.preferences()["ordinary_per_day"] == 2
            call("goal_update", id="bicycle", progress="Saved research evidence.",
                 research_review_at=stamp(now + 10 * 86400), signal_id="new-user-choice")
            idea = call("idea_add", goal_id="bicycle", title="Compare nearby shops", rationale="Relevant")
            call("feedback", kind="interest", id=idea["id"], action="dismiss", signal_id="new-user-choice")
            article = call("feed_add", event_key="article", title="Bicycles", content="Evidence",
                           sources=["https://example.org/source"], why="Matches the goal")
            call("feed_update", id=article["id"], feedback="Useful", signal_id="new-user-choice")
            call("feed_update", id=article["id"], delete=True, signal_id="new-user-choice")
            assert not runtime.store.path(article["path"]).exists()
            runtime.service.signal("discard-choice", "source-session", "This separate topic can be forgotten.")
            call("interest_record", id="discard", title="Discard this", signal_id="discard-choice")
            call("forget", kind="interest", id="discard", signal_id="discard-choice")
            assert runtime.store.read("interest", "discard") is None
            owned = None
            for schedule in ("every 5m", "* * * * *", "*/31 * * * *", "10,50 0,23 * * MON", "in 1m"):
                watch = call("watch_create", goal_id="bicycle", signal_id="new-user-choice", schedule=schedule,
                             prompt="x" * 5000, stop_condition="User chooses a bicycle")
                assert get_job(watch["id"]), schedule
                if owned is None:
                    owned = watch
                else:
                    remove_job(watch["id"])
        finally:
            clear_session_vars(tokens)

        source = runtime.store.read("session", "source-session")
        source["route"] = {"platform": "telegram", "chat_id": "123", "session_key": "source"}
        runtime.store.write("session", "source-session", source)
        for targets in ([], [{"id": "bot-chat:other-profile", "home_target_set": True}],
                        [{"id": "telegram", "home_target_set": True}]):
            with patch("cron.scheduler_delivery.cron_delivery_targets", return_value=targets):
                assert runtime.host.route("source-session") == {"deliver": "bot-chat"}
        notice = runtime.service.notification_add({
            "event_key": "delivery", "message": "A bicycle is available.", "rationale": "Matches the goal",
            "sources": ["https://example.org/source"], "verified_at": now,
            "expires": now + 3600, "priority": "urgent", "goal_id": "bicycle"})
        from cron.executions import create_execution, mark_execution_running, finish_execution
        from cron.jobs import update_job
        patrol_id = runtime.host.manifest()["fixed"]["proactive-watch"]
        assert get_job(patrol_id)["deliver"] == "bot-chat"
        # Upgrade a pre-direct installation once, without resuming paused jobs.
        record = runtime.host.manifest()
        record.pop("direct_patrol_delivery")
        runtime.host.save_manifest(record)
        update_job(patrol_id, {"deliver": "local"})
        watch_before = get_job(owned["id"])
        new_header = ("Check its status and your stop condition first. Prepare evidence with notification_add. "
                      "Stop and call watch_stop when the promised condition is satisfied. "
                      "As your last step call notification_prepare and return its final_response exactly; "
                      "this job delivers that response. With nothing approved return [SILENT].\n")
        old_header = ("Check its status and your stop condition first. Never send directly; prepare evidence with notification_add and notification_queue. "
                      "Stop and call watch_stop when the promised condition is satisfied. Return [SILENT].\n")
        assert new_header in watch_before["prompt"]
        update_job(owned["id"], {"prompt": watch_before["prompt"].replace(new_header, old_header),
                                "deliver": "local", "enabled": False})
        runtime.host.initialize()
        migrated = get_job(owned["id"])
        assert new_header in migrated["prompt"] and migrated["deliver"] == "bot-chat"
        assert not migrated["enabled"] and migrated["schedule"] == watch_before["schedule"]
        assert get_job(patrol_id)["deliver"] == "bot-chat"
        before = len(list_jobs(True))
        staged = runtime.handoff(notice["id"])
        assert staged["status"] == "pending" and staged["job_id"] is None
        assert cron_run(home, "proactive-watch")["wakeAgent"]
        execution = create_execution(patrol_id, source="test")
        mark_execution_running(execution["id"])
        task_id = "cron:" + patrol_id + ":" + execution["id"]
        prepared = json.loads(runtime.handle({"action": "notification_prepare", "data": {"id": notice["id"]}},
                                             task_id=task_id))["result"]
        assert len(list_jobs(True)) == before, "Preparing a notice must not create a delivery Cron"
        assert prepared["execution_id"] == execution["id"] and prepared["job_id"] == patrol_id
        payload = prepared["final_response"]
        assert payload.startswith("[Hermes Muse notification ") and "A bicycle is available." in payload
        finish_execution(execution["id"], success=True, delivery_outcome="delivered")
        runtime.host.reconcile()
        assert runtime.store.read("notification", notice["id"])["status"] == "sent"
        assert runtime.host.current_delivery(task_id) is None, "A finished run cannot prepare another notice"
        tokens = set_session_vars(session_id="bot-session", chat_type="private", cron_session="")
        try:
            count = len(runtime.store.all("signal"))
            context = runtime.pre_turn(session_id="bot-session", turn_id="delivery-turn",
                                       user_message='[Cronjob "muse-proactive-watch" output]\n\n' + payload)
            assert context and "Bot Chat" in context["context"]
            assert len(runtime.store.all("signal")) == count
            for review in ("weekly-governance-review", "monthly-system-audit"):
                review_context = runtime.pre_turn(session_id="bot-session", turn_id=review,
                    user_message='[Cronjob "muse-' + review + '" output]\n\nConsider simplifying a job.')
                assert "proposals" in review_context["context"]
                assert len(runtime.store.all("signal")) == count
            call("goal_update", id="bicycle", progress="Bot reviewed the result.")
            call("preferences", ordinary_per_day=3)
            before = len(list_jobs(True))
            call("notification_handoff", id=notice["id"])
            assert len(list_jobs(True)) == before, "The same reminder must not queue twice"
            runtime.pre_turn(session_id="bot-session", turn_id="human-turn", user_message="I am interested in hiking.")
            call("interest_record", title="Hiking", signal_id="human-turn")
        finally:
            clear_session_vars(tokens)

        tokens = set_session_vars(session_id="cron-session", chat_type="private", cron_session="1")
        try:
            call("goal_update", id="bicycle", status="completed", signal_id="new-user-choice")
            assert not get_job(owned["id"])["enabled"]
        finally:
            clear_session_vars(tokens)
            runtime.close()
        config = (home / "config.yaml").read_bytes()
        assert enabled(home)
        assert (home / "config.yaml").read_bytes() == config
    print("PASS: 0.1.2 background actions and evidence rules, native schedules/long prompts, writable Bot Chat handling, profile-local delivery and no duplicate queue")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="muse-baseline-") as temporary:
        os.environ["HERMES_HOME"] = temporary
        run(Path(temporary))
