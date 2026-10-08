"""Catalog-review regressions against real Hermes APIs, in a temporary profile."""
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
    from cron.scheduler_delivery import BOT_CHAT_PLATFORM
    from gateway.session_context import set_session_vars, clear_session_vars
    from hermes_muse.host import profile_scope, enabled
    from hermes_muse.runtime import Runtime
    from hermes_muse.store import stamp

    runtime = Runtime(object(), home)
    with profile_scope(home):
        runtime.host.initialize()
        runtime.service.signal("user-choice", "review-session", "Track bicycle options until I choose one.")
        goal = {"id": "bicycle", "title": "Choose a bicycle", "description": "Compare options",
                "completion_criteria": "User confirms a purchase", "signal_id": "user-choice"}
        runtime.service.goal_create(goal)
        watch = {"goal_id": "bicycle", "signal_id": "user-choice", "schedule": "every 30m",
                 "prompt": "Check bicycle availability", "stop_condition": "User chooses a bicycle"}
        owned = runtime.host.watch(watch)
        runtime.service.interest_record({"id": "cycling", "title": "Cycling", "signal_id": "user-choice"})
        article = runtime.service.feed_add({"event_key": "review-article", "title": "Bicycle notes", "content": "Evidence",
                                           "sources": ["https://example.org/source"], "why": "Matches the goal"})

        tokens = set_session_vars(session_id="review-session", chat_type="private", cron_session="1")
        try:
            attempts = [
                ("goal_create", dict(goal, id="unrequested")),
                ("watch_create", watch),
                ("goal_update", {"id": "bicycle", "status": "completed", "signal_id": "user-choice"}),
                ("goal_update", {"id": "bicycle", "research_review_at": stamp(time.time() + 86400), "signal_id": "user-choice"}),
                ("interest_record", {"title": "New topic", "signal_id": "user-choice"}),
                ("feedback", {"kind": "interest", "id": "cycling", "action": "stop", "signal_id": "user-choice"}),
                ("forget", {"kind": "goal", "id": "bicycle", "signal_id": "user-choice"}),
                ("preferences", {"ordinary_per_day": 2}),
                ("feed_update", {"id": article["id"], "delete": True, "signal_id": "user-choice"}),
            ]
            for action, data in attempts:
                before = len(list_jobs(True))
                result = json.loads(runtime.handle({"action": action, "data": data}))
                assert not result["ok"] and "real user" in result["error"], (action, result)
                assert len(list_jobs(True)) == before, action
            assert runtime.store.goal("bicycle")[0]["status"] == "active"
            assert len(runtime.store.goals()) == 1
            assert runtime.store.read("interest", "cycling")["status"] == "active"
            assert runtime.service.preferences()["ordinary_per_day"] == 1
            assert runtime.store.path(article["path"]).exists()
            for action, data in [
                ("goal_update", {"id": "bicycle", "progress": "Saved research evidence."}),
                ("idea_add", {"goal_id": "bicycle", "title": "Compare nearby shops", "rationale": "Relevant to the goal"}),
                ("watch_stop", {"job_id": owned["id"]}),
                ("context", {}),
            ]:
                result = json.loads(runtime.handle({"action": action, "data": data}))
                assert result["ok"], (action, result)
            assert not get_job(owned["id"])["enabled"]
        finally:
            clear_session_vars(tokens)

        tokens = set_session_vars(session_id="review-session", chat_type="private", cron_session="true")
        try:
            result = json.loads(runtime.handle({"action": "preferences", "data": {"ordinary_per_day": 2}}))
            assert not result["ok"] and "real user" in result["error"], result
        finally:
            clear_session_vars(tokens)

        def reject(data, text):
            before = len(list_jobs(True))
            try:
                runtime.host.watch(data)
            except ValueError as exc:
                assert text in str(exc), str(exc)
            else:
                raise AssertionError(f"Unsafe watch accepted: {data['schedule']}")
            assert len(list_jobs(True)) == before

        reject(dict(watch, prompt="x" * 4001), "4000")
        for schedule in ("every 1m", "29m", "* * * * *", "*/20 * * * *", "*/31 * * * *",
                         "0,10,40 9 * * MON", "0,40 * * * *", "0 * * * * *", "R * * * *",
                         "10,50 0,23 * * MON"):
            reject(dict(watch, schedule=schedule), "30 minutes")
        for schedule in ("every 30m", "2h", "0,30 * * * *", "0,40 9 * * *", "0 9 * * MON",
                         "0 * * * * 15", "in 1m", stamp(time.time() + 3600)):
            job = runtime.host.watch(dict(watch, schedule=schedule, prompt="x" * 4000))
            assert get_job(job["id"]), schedule
            remove_job(job["id"])

        bot = {"id": BOT_CHAT_PLATFORM + ":other-profile", "home_target_set": True}
        telegram = {"id": "telegram", "home_target_set": True}
        for targets in ([bot], [bot, telegram], [], [telegram]):
            with patch("cron.scheduler_delivery.cron_delivery_targets", return_value=targets):
                assert runtime.host.route() == {"deliver": BOT_CHAT_PLATFORM}
        source = runtime.store.read("session", "review-session")
        source["route"] = {"platform": "telegram", "chat_id": "123", "session_key": "source"}
        runtime.store.write("session", "review-session", source)
        assert runtime.host.route("review-session") == {"deliver": BOT_CHAT_PLATFORM}
        notice = runtime.service.notification_add({
            "event_key": "review-notice", "message": "A bicycle is available.", "rationale": "Matches the goal",
            "sources": ["https://example.org/source"], "verified_at": time.time(),
            "expires": time.time() + 3600, "priority": "urgent", "goal_id": "bicycle"})
        queued = runtime.handoff(notice["id"])
        assert queued["route"] == {"deliver": "bot-chat"}
        job = get_job(queued["job_id"])
        assert job["deliver"] == "bot-chat" and job["no_agent"], job
        from hermes_muse.host import cron_run
        payload = cron_run(home, "deliver-" + notice["id"])
        assert payload.startswith("[Hermes Muse notification ") and "A bicycle is available." in payload
        tokens = set_session_vars(session_id="bot-session", chat_type="private", cron_session="")
        try:
            before = len(runtime.store.all("signal"))
            context = runtime.pre_turn(session_id="bot-session", turn_id="delivery-turn",
                                       user_message='[Cronjob "muse-delivery-test" output]\n\n' + payload)
            assert "one concise reply" in context["context"]
            assert len(runtime.store.all("signal")) == before
            result = json.loads(runtime.handle({"action": "notification_handoff", "data": {"id": notice["id"]}}))
            assert not result["ok"] and "background data" in result["error"], result
            runtime.pre_turn(session_id="bot-session", turn_id="human-turn", user_message="I am interested in hiking.")
            result = json.loads(runtime.handle({"action": "interest_record", "data": {
                "title": "Hiking", "signal_id": "human-turn"}}))
            assert result["ok"], result
        finally:
            clear_session_vars(tokens)

        tokens = set_session_vars(session_id="review-session", chat_type="private", cron_session="")
        try:
            result = json.loads(runtime.handle({"action": "goal_update", "data": {
                "id": "bicycle", "status": "completed", "signal_id": "user-choice"}}))
            assert result["ok"], result
        finally:
            clear_session_vars(tokens)
            runtime.close()
        original = (home / "config.yaml").read_bytes()
        assert enabled(home)
        assert (home / "config.yaml").read_bytes() == original
    print("PASS: Cron user-decision guard, allowed upkeep, bounded watch prompts/cadence, current-profile Bot Chat routing, no self-triggered user signals and interactive completion")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="muse-review-") as temporary:
        os.environ["HERMES_HOME"] = temporary
        run(Path(temporary))
