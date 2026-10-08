"""Companion lifecycle rules. No model/provider or messaging dependency."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime

from .store import DAY, Store, bounded, digest, epoch, identifier, stamp

DEFAULT_PREFERENCES = {"start_hour": 9, "end_hour": 22, "ordinary_per_day": 1,
                       "time_sensitive_per_day": 3, "blocked_topics": [], "feed_brief": ""}


class Companion:
    def __init__(self, store, host, clock=time.time):
        self.store, self.host, self.clock = store, host, clock

    def preferences(self):
        text = self.store.path("PROACTIVE_PREFERENCES.md").read_text(encoding="utf-8")
        line = text.splitlines()[0]
        prefix = "<!-- hermes-muse "
        if not line.startswith(prefix) or not line.endswith(" -->"):
            raise ValueError("Preferences metadata is invalid; delivery is blocked until repaired")
        prefs = {**DEFAULT_PREFERENCES, **json.loads(line[len(prefix):-4])}
        for key, high in (("start_hour", 23), ("end_hour", 24), ("ordinary_per_day", 20), ("time_sensitive_per_day", 20)):
            if type(prefs[key]) is not int or not 0 <= prefs[key] <= high:
                raise ValueError(f"Invalid preference: {key}")
        if not isinstance(prefs["blocked_topics"], list) or any(not isinstance(x, str) for x in prefs["blocked_topics"]):
            raise ValueError("blocked_topics must be a list of topic IDs")
        return prefs

    def preference_update(self, data):
        unknown = set(data) - set(DEFAULT_PREFERENCES)
        if unknown:
            raise ValueError(f"Unknown preference fields: {sorted(unknown)}")
        with self.store.transaction() as db:
            prefs = self.preferences()
            prefs.update(data)
            # Validate before changing the file.
            for key, high in (("start_hour", 23), ("end_hour", 24), ("ordinary_per_day", 20), ("time_sensitive_per_day", 20)):
                if type(prefs[key]) is not int or not 0 <= prefs[key] <= high:
                    raise ValueError(f"Invalid preference: {key}")
            if not isinstance(prefs["blocked_topics"], list) or any(not isinstance(x, str) for x in prefs["blocked_topics"]):
                raise ValueError("blocked_topics must be a list of strings")
            if not isinstance(prefs["feed_brief"], str) or len(prefs["feed_brief"]) > 12000:
                raise ValueError("Feed brief must be text up to 12000 characters")
            path = self.store.path("PROACTIVE_PREFERENCES.md")
            body = path.read_text(encoding="utf-8").partition("\n")[2]
            self.store.write_text("PROACTIVE_PREFERENCES.md", "<!-- hermes-muse " + json.dumps(prefs, ensure_ascii=False) + " -->\n" + body)
            if "feed_brief" in data:
                self.store.put(db, "meta", "feed_requested", self.clock())
        if "feed_brief" in data:
            self.host.wake("feed-pulse")
        return prefs

    def signal(self, turn_id, session_id, text, route=None):
        now = self.clock()
        with self.store.transaction() as db:
            if self.store.get(db, "signal", turn_id):
                return
            self.store.put(db, "signal", turn_id, {"id": turn_id, "session_id": session_id,
                           "text": str(text)[:8000], "created": now})
            previous = self.store.get(db, "session", session_id, {})
            self.store.put(db, "session", session_id, {**previous, "id": session_id,
                           "last_signal": now, "active": True, "route": route or previous.get("route"), "turn_id": turn_id})
            # Signals are a bounded processing inbox. Durable facts belong in native memory.
            old = sorted(self.store.rows(db, "signal"), key=lambda x: x["created"])
            processed = min(self.store.get(db, "cursor", "memory-upkeep", 0), self.store.get(db, "cursor", "nightly-review", 0))
            for row in old[:-500]:
                if row["created"] <= processed:
                    self.store.delete(db, "signal", row["id"])

    def require_signal(self, db, signal_id):
        row = self.store.get(db, "signal", bounded(signal_id, 160))
        if not row or row["created"] < self.clock() - DAY:
            raise ValueError("A real user signal from the last 24 hours is required")
        return row

    def goal_create(self, data):
        now = self.clock()
        key = identifier(data.get("id") or uuid.uuid4().hex[:12])
        with self.store.transaction() as db:
            signal = self.require_signal(db, data.get("signal_id"))
            if self.store.path(f"workspace/goals/{key}/GOAL.md").exists():
                raise ValueError("Goal already exists; use goal_update")
            parent_id = data.get("parent_id")
            if parent_id:
                parent, _ = self.store.goal(parent_id)
                if parent.get("parent_id") or parent["status"] != "active":
                    raise ValueError("Subgoals require an active top-level parent")
            deadline = epoch(data["deadline"]) if data.get("deadline") else None
            if deadline and deadline <= now:
                raise ValueError("A new goal deadline must be in the future")
            record = {"id": key, "title": bounded(data.get("title"), 200), "status": "active",
                      "parent_id": parent_id, "created": now, "updated": now,
                      "research_review_at": min(deadline or now + 30 * DAY, now + 30 * DAY),
                      "deadline": deadline, "external_ref": data.get("external_ref"),
                      "source_signal": signal["id"], "session_id": signal["session_id"], "progress": []}
            body = f"# {record['title']}\n\n{bounded(data.get('description'))}\n\n## Completion criteria\n{bounded(data.get('completion_criteria'))}\n"
            self.store.save_goal(record, body)
            for folder in ("files", "hidden_files"):
                self.store.path(f"workspace/goals/{key}/{folder}").mkdir(exist_ok=True)
        return record

    def goal_update(self, data):
        key, now = identifier(data["id"]), self.clock()
        closing = []
        with self.store.transaction() as db:
            record, body = self.store.goal(key)
            status = data.get("status", record["status"])
            if status not in {"active", "completed", "cancelled"}:
                raise ValueError("Goal status must be active, completed or cancelled")
            if status != record["status"] or "research_review_at" in data:
                self.require_signal(db, data.get("signal_id"))
            if status != "active" and record.get("external_ref") and not data.get("external_status_verified"):
                raise ValueError("Read/update the external authoritative goal first and confirm its status")
            if data.get("progress"):
                record["progress"] = (record.get("progress", []) + [{"at": now, "text": bounded(data["progress"], 2000)}])[-50:]
            record.update(status=status, updated=now)
            if "research_review_at" in data:
                review = epoch(data["research_review_at"])
                if not now < review <= now + 30 * DAY:
                    raise ValueError("Research review must be within the next 30 days")
                record["research_review_at"] = review
            self.store.save_goal(record, body)
            if status != "active":
                closing.append(key)
                for child in self.store.goals():
                    if child.get("parent_id") == key and child["status"] == "active":
                        _, child_body = self.store.goal(child["id"])
                        child.update(status="cancelled", updated=now)
                        self.store.save_goal(child, child_body)
                        closing.append(child["id"])
                for row in self.store.rows(db, "notification"):
                    if row.get("goal_id") in closing and row["status"] in {"candidate", "pending", "queued"} and not row.get("final_result"):
                        row["status"] = "cancelled"
                        self.store.put(db, "notification", row["id"], row)
        for owner in closing:
            self.host.pause_owner(owner)
        return record

    def interest_record(self, data, *, idea=False):
        now = self.clock()
        key = identifier(data.get("id") or uuid.uuid4().hex[:12])
        with self.store.transaction() as db:
            signal = self.require_signal(db, data.get("signal_id"))
            previous = self.store.get(db, "interest", key)
            if previous and signal["created"] <= previous["last_signal"]:
                raise ValueError("Only a newer real user signal can renew this interest")
            deleted_at = self.store.get(db, "forgotten", "interest:" + key, 0)
            if signal["created"] <= deleted_at:
                raise ValueError("This interest was forgotten; old evidence cannot recreate it")
            expires = min(epoch(data["expires"]), now + 14 * DAY) if data.get("expires") else signal["created"] + 14 * DAY
            if expires <= now:
                raise ValueError("Interest already expired")
            record = {"id": key, "kind": "idea" if idea else "interest", "title": bounded(data.get("title"), 300),
                      "source_signal": signal["id"], "session_id": signal["session_id"], "last_signal": signal["created"],
                      "expires": expires, "status": "candidate" if idea else "active", "rationale": str(data.get("rationale", ""))[:2000]}
            self.store.put(db, "interest", key, record)
        return record

    def idea_add(self, data):
        # Research may propose an Idea without inventing a new user signal or starting execution.
        goal, _ = self.store.goal(data["goal_id"])
        if goal["status"] != "active" or goal["research_review_at"] <= self.clock():
            raise ValueError("Goal is inactive or needs review")
        key = digest(data["goal_id"] + bounded(data["title"], 300))
        with self.store.transaction() as db:
            existing = self.store.get(db, "interest", key)
            if existing or self.store.get(db, "forgotten", "interest:" + key):
                return existing or {"id": key, "status": "forgotten"}
            row = {"id": key, "kind": "idea", "title": data["title"], "goal_id": goal["id"],
                   "session_id": goal["session_id"], "last_signal": 0, "expires": self.clock() + 14 * DAY,
                   "status": "candidate", "rationale": bounded(data["rationale"], 2000)}
            self.store.put(db, "interest", key, row)
        return row

    def owner_valid(self, row):
        now = self.clock()
        if row.get("goal_id"):
            goal, _ = self.store.goal(row["goal_id"])
            if goal["status"] != "active" and not row.get("final_result"):
                return False
        if row.get("interest_id"):
            # Caller can be in a transaction; use its snapshot when supplied.
            interest = row.get("_interest")
            if interest is None:
                interest = self.store.read("interest", row["interest_id"])
            if not interest or interest["status"] not in {"active", "accepted"} or interest["expires"] <= now:
                return False
        return row.get("expires", now + 1) > now

    def context(self):
        now = self.clock()
        goals = self.store.goals()
        interests = [r for r in self.store.all("interest") if r["expires"] > now and r["status"] in {"active", "candidate", "accepted"}]
        signals = sorted(self.store.all("signal"), key=lambda r: r["created"])
        cursor = self.store.read("cursor", "memory-upkeep", 0)
        return {"now": stamp(now), "workspace": str(self.store.root), "preferences": self.preferences(),
                "goals": [g for g in goals if g["status"] == "active" and g["research_review_at"] > now],
                "goals_needing_review": [g for g in goals if g["status"] == "active" and g["research_review_at"] <= now],
                "interests_and_ideas": interests,
                "new_user_signals": [r for r in signals if r["created"] > cursor][:25],
                "notifications": [r for r in self.store.all("notification") if r["status"] not in {"cancelled", "dismissed", "done", "expired"}][-30:],
                "feed": self.feed_list({})[:15]}

    def review_complete(self, data):
        job = data.get("job")
        if job not in {"memory-upkeep", "nightly-review", "feed-pulse", "proactive-watch"}:
            raise ValueError("Unknown review job")
        up_to = epoch(data["up_to"])
        now = self.clock()
        if up_to > now:
            raise ValueError("Cannot advance a cursor into the future")
        with self.store.transaction() as db:
            old = self.store.get(db, "cursor", job, 0)
            if job == "memory-upkeep":
                pending = sorted((s for s in self.store.rows(db, "signal") if s["created"] > old), key=lambda s: s["created"])
                if len(pending) > 25 and up_to > pending[24]["created"]:
                    raise ValueError("Cursor skips unseen signals; process the returned batch first")
            self.store.put(db, "cursor", job, max(old, up_to))
            self.store.put(db, "meta", "last_review:" + job, {"at": now, "summary": bounded(data["summary"], 2000)})
        return {"job": job, "processed_through": stamp(max(old, up_to))}

    def notification_add(self, data):
        now = self.clock()
        event_key = bounded(data.get("event_key"), 500)
        key = digest(event_key)
        if data.get("priority", "ordinary") not in {"ordinary", "time_sensitive", "urgent", "promised"}:
            raise ValueError("Invalid priority")
        sources = data.get("sources")
        if not isinstance(sources, list) or not sources or any(not isinstance(s, str) or len(s) > 2000 for s in sources):
            raise ValueError("Supply original evidence source references")
        expires = epoch(data["expires"])
        verified_at = epoch(data["verified_at"])
        if not now < expires or not now - DAY <= verified_at <= now + 60:
            raise ValueError("Evidence verification must be recent and expiry in the future")
        row = {"id": key, "event_key": event_key, "message": bounded(data.get("message"), 6000),
               "rationale": bounded(data.get("rationale"), 2000), "sources": sources,
               "verified_at": verified_at, "expires": expires, "created": now,
               "priority": data.get("priority", "ordinary"), "topic": str(data.get("topic", ""))[:100],
               "goal_id": data.get("goal_id"), "interest_id": data.get("interest_id"),
               "final_result": bool(data.get("final_result")), "status": "candidate", "not_before": now,
               "session_id": data.get("session_id"), "job_id": None}
        if not self.owner_valid(row):
            raise ValueError("Notification owner is inactive or expired")
        with self.store.transaction() as db:
            if row["priority"] == "promised":
                self.require_signal(db, data.get("signal_id"))
            if self.store.get(db, "forgotten", "notification:" + key):
                return {"id": key, "status": "forgotten"}
            existing = self.store.get(db, "notification", key)
            if existing:
                return existing
            self.store.put(db, "notification", key, row)
        return row

    def notification_refresh(self, data):
        key = identifier(data["id"])
        verified = epoch(data["verified_at"])
        if not self.clock() - DAY <= verified <= self.clock() + 60:
            raise ValueError("Verification time must be recent")
        sources = data.get("sources")
        if not isinstance(sources, list) or not sources or any(not isinstance(s, str) or len(s) > 2000 for s in sources):
            raise ValueError("Supply rechecked original source references")
        with self.store.transaction() as db:
            row = self.store.get(db, "notification", key)
            if not row or row["status"] not in {"candidate", "pending"}:
                raise ValueError("Only a pending, not-yet-dispatched candidate can be reverified")
            row.update(verified_at=verified, sources=sources)
            if "message" in data:
                row["message"] = bounded(data["message"], 6000)
            self.store.put(db, "notification", key, row)
        return row

    def notification_queue(self, data):
        key = identifier(data["id"])
        snapshot = self.store.read("notification", key, {})
        route = self.host.route(snapshot.get("session_id"))
        with self.store.transaction() as db:
            row = self.store.get(db, "notification", key)
            if not row:
                raise ValueError("Unknown notification")
            if row["status"] not in {"candidate", "pending"}:
                return row
            if not route:
                row["status"] = "pending"
            else:
                # Local host mutation under the state lock serializes competing queue requests.
                job = self.host.delivery_job(row, route)
                row.update(status="queued", job_id=job["id"], route=route)
            self.store.put(db, "notification", key, row)
        return row

    def delivery_text(self, key):
        now = self.clock()
        with self.store.transaction() as db:
            row = self.store.get(db, "notification", key)
            if not row or row["status"] != "queued":
                return ""
            if row.get("interest_id"):
                row["_interest"] = self.store.get(db, "interest", row["interest_id"], {})
            if not self.owner_valid(row):
                row.pop("_interest", None)
                row["status"] = "expired"
                self.store.put(db, "notification", key, row)
                return ""
            row.pop("_interest", None)
            if row["verified_at"] < now - DAY:
                row.update(status="candidate", job_id=None, needs_reverification=True)
                self.store.put(db, "notification", key, row)
                return ""
            prefs = self.preferences()
            if row["topic"] in prefs["blocked_topics"]:
                row["status"] = "dismissed"
                self.store.put(db, "notification", key, row)
                return ""
            local = self.host.local_now(now)
            allowed = row["not_before"] <= now
            if row["priority"] in {"ordinary", "time_sensitive"}:
                start, end = prefs["start_hour"], prefs["end_hour"]
                waking = start <= local.hour < end if start < end else local.hour >= start or local.hour < end
                allowed &= waking
                if row["priority"] == "ordinary":
                    sessions = self.store.rows(db, "session")
                    allowed &= not any(s.get("active") and s.get("last_signal", 0) > now - 15 * 60 for s in sessions)
                budget_key = local.date().isoformat() + ":" + row["priority"]
                used = self.store.get(db, "budget", budget_key, 0)
                allowed &= used < prefs[row["priority"] + "_per_day"]
            if not allowed:
                row.update(status="pending", job_id=None)
                self.store.put(db, "notification", key, row)
                return ""
            if row["priority"] in {"ordinary", "time_sensitive"}:
                self.store.put(db, "budget", budget_key, used + 1)
            row.update(status="dispatching", dispatched_at=now)
            self.store.put(db, "notification", key, row)
            return row["message"]

    def feedback(self, data):
        kind, key, action = data["kind"], identifier(data["id"]), data["action"]
        if kind not in {"notification", "interest"}:
            raise ValueError("Feedback kind must be notification or interest")
        with self.store.transaction() as db:
            self.require_signal(db, data.get("signal_id"))
            row = self.store.get(db, kind, key)
            if not row:
                raise ValueError("Unknown feedback item")
            if action == "snooze":
                until = epoch(data["until"])
                if not self.clock() < until < row["expires"]:
                    raise ValueError("Snooze must be before expiry")
                row.update(status="pending", not_before=until, job_id=None)
            elif action in {"done", "dismiss", "stop", "accept"}:
                row["status"] = {"done": "done", "dismiss": "dismissed", "stop": "stopped", "accept": "accepted"}[action]
            else:
                raise ValueError("Unknown feedback action")
            row["feedback"] = {"action": action, "at": self.clock(), "signal_id": data["signal_id"]}
            self.store.put(db, kind, key, row)
        if action == "stop":
            prefs = self.preferences()
            topic = row.get("topic") or key
            self.preference_update({"blocked_topics": list(dict.fromkeys(prefs["blocked_topics"] + [topic]))})
        return row

    def feed_add(self, data):
        key = digest(bounded(data["event_key"], 500))
        now = self.clock()
        if data.get("interest_id") and not self.owner_valid({"interest_id": data["interest_id"]}):
            raise ValueError("Feed interest is expired or inactive")
        if data.get("goal_id"):
            goal, _ = self.store.goal(data["goal_id"])
            if goal["status"] != "active" or goal["research_review_at"] <= now:
                raise ValueError("Feed goal is inactive or needs review")
        with self.store.transaction() as db:
            old = self.store.get(db, "feed", key)
            if old or self.store.get(db, "forgotten", "feed:" + key):
                return old or {"id": key, "status": "deleted"}
            sources = data.get("sources")
            if not isinstance(sources, list) or not sources or any(not isinstance(x, str) for x in sources):
                raise ValueError("Feed needs original source references")
            relative = f"workspace/your_files/feed/{key}.md"
            title = bounded(data["title"], 300)
            self.store.write_text(relative, f"# {title}\n\n{bounded(data['content'], 60000)}\n\n## Sources\n" + "\n".join(f"- {s}" for s in sources) + "\n")
            row = {"id": key, "title": title, "path": relative, "created": now, "position": now,
                   "sources": sources, "why": bounded(data["why"], 2000), "feedback": None,
                   "goal_id": data.get("goal_id"), "interest_id": data.get("interest_id")}
            self.store.put(db, "feed", key, row)
        return row

    def feed_list(self, data):
        query = str(data.get("query", "")).casefold()
        rows = self.store.all("feed")
        if query:
            rows = [r for r in rows if query in (r["title"] + " " + self.store.path(r["path"]).read_text(encoding="utf-8")).casefold()]
        return sorted(rows, key=lambda r: r["position"], reverse=True)[:100]

    def feed_update(self, data):
        key = identifier(data["id"])
        with self.store.transaction() as db:
            signal = self.require_signal(db, data.get("signal_id"))
            row = self.store.get(db, "feed", key)
            if not row:
                raise ValueError("Unknown Feed article")
            if data.get("delete"):
                self.store.path(row["path"]).unlink(missing_ok=True)
                self.store.delete(db, "feed", key)
                self.store.put(db, "forgotten", "feed:" + key, self.clock())
                return {"id": key, "deleted": True}
            if "feedback" in data:
                row["feedback"] = {"text": bounded(data["feedback"], 2000), "signal_id": signal["id"], "at": self.clock()}
            if "position" in data:
                row["position"] = float(data["position"])
            self.store.put(db, "feed", key, row)
        return row

    def forget(self, data):
        kind, key = data["kind"], identifier(data["id"])
        if kind not in {"interest", "notification", "feed", "goal"}:
            raise ValueError("Unsupported owned record kind")
        with self.store.transaction() as db:
            self.require_signal(db, data.get("signal_id"))
        if kind == "goal":
            self.goal_update({"id": key, "status": "cancelled", "signal_id": data["signal_id"], "external_status_verified": data.get("external_status_verified", False)})
        with self.store.transaction() as db:
            row = self.store.get(db, kind, key)
            for item in self.store.rows(db, "notification"):
                if (kind == "goal" and item.get("goal_id") == key) or (kind == "interest" and item.get("interest_id") == key):
                    self.store.delete(db, "notification", item["id"])
                    self.store.put(db, "forgotten", "notification:" + item["id"], self.clock())
            for item in self.store.rows(db, "feed"):
                if (kind == "goal" and item.get("goal_id") == key) or (kind == "interest" and item.get("interest_id") == key) or (kind == "feed" and item["id"] == key):
                    self.store.path(item["path"]).unlink(missing_ok=True)
                    self.store.delete(db, "feed", item["id"])
                    self.store.put(db, "forgotten", "feed:" + item["id"], self.clock())
            if kind == "goal":
                # Only managed goal documents; user artifacts are enumerated for explicit cleanup.
                self.store.path(f"workspace/goals/{key}/GOAL.md").unlink(missing_ok=True)
            if row and row.get("source_signal"):
                self.store.delete(db, "signal", row["source_signal"])
            self.store.delete(db, kind, key)
            self.store.put(db, "forgotten", kind + ":" + key, self.clock())
        return {"owned_record_removed": True, "remaining_review": ["native/external memory", "dated notes and alignment", "goal files and evidence", "native session history and backups"],
                "instruction": "Use the forget procedure to inspect and clean these remaining copies; do not claim complete erasure yet."}
