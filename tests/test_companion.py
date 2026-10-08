import concurrent.futures
import contextlib
import json
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from hermes_muse.service import Companion
from hermes_muse.store import DAY, Store, stamp

ROOT = Path(__file__).resolve().parents[1]


class Host:
    def __init__(self):
        self.jobs = []
        self.paused = []
        self.woken = []
        self.destination = {"platform": "test", "chat_id": "private"}

    def route(self, session_id=None):
        return self.destination

    def delivery_job(self, row, route):
        job = {"id": uuid.uuid4().hex[:12]}
        self.jobs.append(job)
        return job

    def pause_owner(self, owner):
        self.paused.append(owner)

    def wake(self, key):
        self.woken.append(key)
        return True

    def local_now(self, timestamp):
        return datetime.fromtimestamp(timestamp, timezone.utc)


def prepare(home):
    store = Store(home)
    for file in (ROOT / "templates").rglob("*.md"):
        store.write_text(file.relative_to(ROOT / "templates").as_posix(), file.read_text(), create_only=True)
    store.path("workspace/goals").mkdir(parents=True, exist_ok=True)
    return store


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = prepare(self.temp.name)
        self.host = Host()
        self.now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc).timestamp()
        self.service = Companion(self.store, self.host, lambda: self.now)
        self.signal = self.user("I want to compare available bicycles and finish choosing one this month.")

    def user(self, message):
        key = uuid.uuid4().hex
        self.service.signal(key, "session-a", message)
        row = self.store.read("session", "session-a")
        row["active"] = False
        self.store.write("session", "session-a", row)
        return key

    def goal(self, key="bicycle", **kw):
        return self.service.goal_create({"id": key, "title": "Choose a bicycle", "description": "Compare candidates within budget", "completion_criteria": "User confirms a purchase", "signal_id": self.signal, **kw})

    def notice(self, key="event-a", **kw):
        return self.service.notification_add({"event_key": key, "message": "A relevant fact changed.", "rationale": "Matches the active goal", "sources": ["https://example.org/announcement"], "verified_at": self.now, "expires": self.now + DAY, **kw})

    def test_concurrent_dedup_and_queue_create_one_native_job(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda _: self.notice(), range(12)))
            queued = list(pool.map(lambda _: self.service.notification_queue({"id": rows[0]["id"]}), range(12)))
        self.assertEqual(len(self.store.all("notification")), 1)
        self.assertEqual(len(self.host.jobs), 1)
        self.assertEqual(len({r["job_id"] for r in queued}), 1)

    def test_concurrent_daily_budget_and_no_second_dispatch(self):
        rows = [self.notice("event-" + str(i)) for i in range(8)]
        for row in rows:
            self.service.notification_queue({"id": row["id"]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            messages = list(pool.map(lambda r: self.service.delivery_text(r["id"]), rows))
        self.assertEqual(sum(bool(s) for s in messages), 1)
        self.assertEqual(sum(bool(self.service.delivery_text(r["id"])) for r in rows), 0)
        self.assertTrue(all(r["status"] != "sent" for r in self.store.all("notification")))

    def test_closed_goal_stops_watches_but_keeps_final_result(self):
        self.goal()
        old = self.notice("old", goal_id="bicycle")
        final = self.notice("final", goal_id="bicycle", final_result=True, priority="urgent")
        for row in (old, final):
            self.service.notification_queue({"id": row["id"]})
        self.service.goal_update({"id": "bicycle", "status": "completed", "signal_id": self.signal})
        self.assertEqual(self.host.paused, ["bicycle"])
        self.assertEqual(self.service.delivery_text(old["id"]), "")
        self.assertEqual(self.service.delivery_text(final["id"]), final["message"])

    def test_interest_expiry_is_not_renewed_by_background(self):
        row = self.service.interest_record({"id": "cycling", "title": "Cycling", "signal_id": self.signal})
        self.now += 13 * DAY
        with self.assertRaises(ValueError):
            self.service.interest_record({"id": "cycling", "title": "Cycling", "signal_id": self.signal})
        self.now += 2 * DAY
        self.assertEqual(self.service.context()["interests_and_ideas"], [])
        self.assertEqual(self.store.read("interest", "cycling")["expires"], row["expires"])
        new = self.user("I am interested in cycling again")
        renewed = self.service.interest_record({"id": "cycling", "title": "Cycling", "signal_id": new})
        self.assertGreater(renewed["expires"], row["expires"])

    def test_interest_expiry_rechecked_after_queue(self):
        self.service.interest_record({"id": "topic", "title": "A passing topic", "signal_id": self.signal, "expires": self.now + 30})
        row = self.notice(interest_id="topic")
        self.service.notification_queue({"id": row["id"]})
        self.now += 31
        self.assertEqual(self.service.delivery_text(row["id"]), "")

    def test_late_cancel_and_feedback_no_repeat(self):
        row = self.notice(topic="cycling")
        self.service.notification_queue({"id": row["id"]})
        self.service.feedback({"kind": "notification", "id": row["id"], "action": "dismiss", "signal_id": self.signal})
        self.assertEqual(self.service.delivery_text(row["id"]), "")
        self.assertEqual(self.notice()["status"], "dismissed")
        next_row = self.notice("event-next", topic="cycling")
        self.service.feedback({"kind": "notification", "id": next_row["id"], "action": "stop", "signal_id": self.signal})
        future = self.notice("event-future", topic="cycling")
        self.service.notification_queue({"id": future["id"]})
        self.assertEqual(self.service.delivery_text(future["id"]), "")

    def test_no_route_keeps_pending_and_no_fake_receipt(self):
        self.host.destination = None
        row = self.notice()
        result = self.service.notification_queue({"id": row["id"]})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.host.jobs, [])

    def test_quiet_hours_and_urgency(self):
        self.now = datetime(2026, 10, 8, 2, tzinfo=timezone.utc).timestamp()
        ordinary = self.notice()
        urgent = self.notice("urgent", priority="urgent")
        for row in (ordinary, urgent):
            self.service.notification_queue({"id": row["id"]})
        self.assertFalse(self.service.delivery_text(ordinary["id"]))
        self.assertTrue(self.service.delivery_text(urgent["id"]))

    def test_goal_review_boundary_does_not_complete_or_stop_subscription(self):
        self.goal()
        self.now += 31 * DAY
        context = self.service.context()
        self.assertEqual(context["goals"], [])
        self.assertEqual(context["goals_needing_review"][0]["status"], "active")
        self.assertEqual(self.host.paused, [])

    def test_goal_closure_retires_unaccepted_ideas(self):
        self.goal()
        idea = self.service.idea_add({"goal_id": "bicycle", "title": "Compare gearing", "rationale": "Useful for this goal"})
        self.assertEqual(self.service.context()["interests_and_ideas"][0]["id"], idea["id"])
        self.service.goal_update({"id": "bicycle", "status": "completed", "signal_id": self.signal})
        self.assertEqual(self.service.context()["interests_and_ideas"], [])
        self.assertEqual(self.store.read("interest", idea["id"])["status"], "cancelled")

    def test_subgoals_one_level_and_parent_cancellation(self):
        self.goal()
        self.goal("child", parent_id="bicycle")
        with self.assertRaises(ValueError):
            self.goal("grandchild", parent_id="child")
        self.service.goal_update({"id": "bicycle", "status": "cancelled", "signal_id": self.signal})
        self.assertEqual(self.store.goal("child")[0]["status"], "cancelled")

    def test_external_goal_requires_source_verification(self):
        self.goal(external_ref="external/task/12")
        with self.assertRaises(ValueError):
            self.service.goal_update({"id": "bicycle", "status": "completed", "signal_id": self.signal})
        self.assertEqual(self.store.goal("bicycle")[0]["status"], "active")

    def test_feed_search_feedback_delete_and_no_recreation(self):
        args = {"event_key": "article-one", "title": "A bike comparison", "content": "Durable wheel bearings matter.", "sources": ["https://example.org/spec"], "why": "An explicit user interest"}
        article = self.service.feed_add(args)
        self.assertEqual(self.service.feed_list({"query": "bearings"})[0]["id"], article["id"])
        updated = self.service.feed_update({"id": article["id"], "signal_id": self.signal, "feedback": "More technical detail", "position": 9999999999})
        self.assertEqual(updated["feedback"]["text"], "More technical detail")
        self.service.feed_update({"id": article["id"], "signal_id": self.signal, "delete": True})
        self.assertFalse(self.store.path(article["path"]).exists())
        self.assertEqual(self.service.feed_add(args)["status"], "deleted")

    def test_failed_work_leaves_cursor_and_future_cursor_refused(self):
        self.assertEqual(self.store.read("cursor", "memory-upkeep", 0), 0)
        with self.assertRaises(ValueError):
            self.service.review_complete({"job": "memory-upkeep", "up_to": self.now + 1, "summary": "invalid"})
        self.assertEqual(self.store.read("cursor", "memory-upkeep", 0), 0)
        self.service.review_complete({"job": "memory-upkeep", "up_to": self.now, "summary": "processed"})
        self.assertEqual(self.service.context()["new_user_signals"], [])

    def test_forget_removes_indexed_derivatives_without_erasure_claim(self):
        self.service.interest_record({"id": "topic", "title": "Topic", "signal_id": self.signal})
        row = self.notice(interest_id="topic")
        article = self.service.feed_add({"event_key": "topic-article", "title": "Topic", "content": "A report", "sources": ["source"], "why": "Interest", "interest_id": "topic"})
        result = self.service.forget({"kind": "interest", "id": "topic", "signal_id": self.signal})
        self.assertIsNone(self.store.read("notification", row["id"]))
        self.assertFalse(self.store.path(article["path"]).exists())
        self.assertTrue(result["remaining_review"])
        with self.assertRaises(ValueError):
            self.service.interest_record({"id": "topic", "title": "Topic", "signal_id": self.signal})

    def test_path_traversal_and_symlink_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.store.write_text("../../outside", "bad")
        with self.assertRaises(ValueError):
            self.goal("../../outside")
        target = Path(self.temp.name) / "external"
        target.mkdir()
        link = self.store.root / "escape"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("No symlink privilege")
        with self.assertRaises(ValueError):
            self.store.write_text("escape/file", "bad")

    def test_profile_data_does_not_cross_between_instances(self):
        self.goal()
        other = prepare(Path(self.temp.name) / "other-profile")
        self.assertEqual(Companion(other, Host()).context()["goals"], [])
        self.assertEqual(self.store.goal("bicycle")[0]["id"], "bicycle")

    def test_snoozed_notice_requires_fresh_evidence_before_dispatch(self):
        row = self.notice(expires=self.now + 5 * DAY, priority="urgent")
        self.service.notification_queue({"id": row["id"]})
        self.now += 2 * DAY
        self.assertFalse(self.service.delivery_text(row["id"]))
        self.assertEqual(self.store.read("notification", row["id"])["status"], "candidate")
        self.service.notification_refresh({"id": row["id"], "verified_at": self.now, "sources": ["rechecked original"]})
        self.service.notification_queue({"id": row["id"]})
        self.assertTrue(self.service.delivery_text(row["id"]))

    def test_cursor_cannot_skip_unseen_batch(self):
        for i in range(30):
            self.now += 1
            self.user("Real user signal " + str(i))
        with self.assertRaises(ValueError):
            self.service.review_complete({"job": "memory-upkeep", "up_to": self.now, "summary": "Skipped batch"})
        batch = self.service.context()["new_user_signals"]
        self.assertEqual(len(batch), 25)
        self.service.review_complete({"job": "memory-upkeep", "up_to": batch[-1]["created"], "summary": "First batch complete"})
        self.assertEqual(len(self.service.context()["new_user_signals"]), 6)

    def test_native_receipt_unknown_is_never_assumed_sent(self):
        import sys
        import types
        from hermes_muse.host import HermesHost
        row = self.notice(priority="urgent")
        self.service.notification_queue({"id": row["id"]})
        self.service.delivery_text(row["id"])
        ledger = types.ModuleType("cron.executions")
        ledger.latest_execution = lambda job: {"id": "attempt-one", "status": "unknown", "delivery_outcome": None}
        with patch.dict(sys.modules, {"cron.executions": ledger}), patch("hermes_muse.host.profile_scope", lambda home: contextlib.nullcontext()):
            HermesHost(self.store).reconcile()
        current = self.store.read("notification", row["id"])
        self.assertEqual(current["status"], "unknown")
        self.service.notification_queue({"id": row["id"]})
        self.assertEqual(len(self.host.jobs), 1)

    def test_native_queue_ack_is_not_final_delivery(self):
        import sys
        import types
        from hermes_muse.host import HermesHost
        row = self.notice(priority="urgent")
        self.service.notification_queue({"id": row["id"]})
        self.service.delivery_text(row["id"])
        ledger = types.ModuleType("cron.executions")
        ledger.latest_execution = lambda job: {"id": "attempt-one", "status": "completed", "delivery_outcome": "queued"}
        queue = types.ModuleType("cron.delivery_queue")
        queue.get_status = lambda execution_id: {"status": "pending"}
        with patch.dict(sys.modules, {"cron.executions": ledger, "cron.delivery_queue": queue}), patch("hermes_muse.host.profile_scope", lambda home: contextlib.nullcontext()):
            HermesHost(self.store).reconcile()
            self.assertEqual(self.store.read("notification", row["id"])["status"], "transport_queued")
            queue.get_status = lambda execution_id: {"status": "delivered"}
            HermesHost(self.store).reconcile()
        self.assertEqual(self.store.read("notification", row["id"])["status"], "sent")

    def test_preference_failure_preserves_file(self):
        before = self.store.path("PROACTIVE_PREFERENCES.md").read_bytes()
        with self.assertRaises(ValueError):
            self.service.preference_update({"start_hour": 500})
        self.assertEqual(before, self.store.path("PROACTIVE_PREFERENCES.md").read_bytes())


class HookTests(unittest.TestCase):
    def test_new_turn_cancels_quiet_pass_and_unload_releases_timers(self):
        from hermes_muse.runtime import Runtime
        with tempfile.TemporaryDirectory() as home:
            prepare(home)
            runtime = Runtime(object(), home, quiet_seconds=100)
            info = {"cron": False, "chat_type": "", "platform": "", "chat_id": ""}
            with patch("hermes_muse.runtime.session_info", return_value=info):
                runtime.pre_turn(session_id="a", turn_id="one", user_message="A" * 100)
                runtime.post_turn(session_id="a", turn_id="one")
                old = runtime.timers["a"]
                runtime.pre_turn(session_id="a", turn_id="two", user_message="A new message")
                self.assertTrue(old.finished.is_set())
                runtime.post_turn(session_id="a", turn_id="two")
                runtime.close()
                self.assertFalse(runtime.timers)

    def test_background_group_and_child_turns_do_not_renew_interest(self):
        from hermes_muse.runtime import Runtime
        with tempfile.TemporaryDirectory() as home:
            prepare(home)
            runtime = Runtime(object(), home)
            self.addCleanup(runtime.close)
            with patch("hermes_muse.runtime.session_info", return_value={"cron": False, "chat_type": "group"}):
                self.assertIsNone(runtime.pre_turn(session_id="g", turn_id="one", user_message="topic"))
            with patch("hermes_muse.runtime.session_info", return_value={"cron": True, "chat_type": ""}):
                self.assertIsNone(runtime.pre_turn(session_id="c", turn_id="two", user_message="topic"))
            self.assertEqual(runtime.store.all("signal"), [])


if __name__ == "__main__":
    unittest.main()
