"""Plugin registration, conversation hooks and the single state tool."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from .host import HermesHost, JOBS, ROOT, profile_scope
from .service import Companion
from .store import PLUGIN, Store, stamp

log = logging.getLogger(__name__)
ACTIONS = ("context", "status", "goal_create", "goal_update", "interest_record", "idea_add", "feedback",
           "preferences", "notification_add", "notification_refresh", "notification_queue", "notification_handoff", "feed_add", "feed_list",
           "feed_update", "review_complete", "watch_create", "watch_stop", "research_start", "research_status", "forget")
SCHEMA = {"name": "muse_manage", "description": "Manage companion goals, temporary interests, reminders, Feed and background research. First read hermes-muse:companion for action-specific data fields. context returns live state and real user signal IDs. Never invent a signal ID, delivery receipt or authorization.",
          "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": list(ACTIONS)}, "data": {"type": "object", "description": "Action arguments documented by the companion Skill; omit for context/status."}}, "required": ["action"], "additionalProperties": False}}


def session_info():
    from gateway.session_context import get_session_env
    fields = {key: get_session_env("HERMES_SESSION_" + key.upper(), "") for key in
              ("id", "key", "platform", "chat_id", "chat_type", "thread_id", "user_id", "message_id", "scope_id", "parent_chat_id")}
    fields["cron"] = get_session_env("HERMES_CRON_SESSION", "") == "1"
    return fields


def private_session(info):
    return str(info.get("chat_type", "")).lower() not in {"group", "supergroup", "channel", "guild", "room"}


def route_from(info):
    if not private_session(info) or not info.get("platform") or not info.get("chat_id"):
        return None
    return {key: info[key] for key in ("platform", "chat_id", "chat_type", "thread_id", "user_id", "message_id", "scope_id", "parent_chat_id") if info.get(key)} | {"session_key": info.get("key", "")}


class Runtime:
    def __init__(self, ctx, home, *, quiet_seconds=300, plugin_root=ROOT):
        self.ctx, self.home, self.quiet_seconds = ctx, Path(home).resolve(), quiet_seconds
        self.store = Store(self.home)
        self.host = HermesHost(self.store, plugin_root=plugin_root)
        self.service = Companion(self.store, self.host)
        self.timers = {}
        self.lock = threading.RLock()
        self.closed = False

    def handle(self, args, **kwargs):
        try:
            if self.closed:
                raise ValueError("Plugin unloaded")
            info = session_info()
            if not private_session(info):
                raise ValueError("Personal Muse data is available in private/direct conversations only")
            data = args.get("data") or {}
            if not isinstance(data, dict):
                raise ValueError("data must be an object")
            action = args["action"]
            if action not in ACTIONS:
                raise ValueError("Unknown Muse action")
            from agent.delegation_context import is_delegated_child_context
            if is_delegated_child_context() and action not in {"context", "status", "feed_list"}:
                raise ValueError("A delegated child may read Muse context but must return proposed changes to its parent")
            with profile_scope(self.home):
                if action in {"context", "status"}:
                    self.host.reconcile()
                    result = self.service.context()
                    if action == "status":
                        result["installation"] = self.host.manifest()
                elif action == "preferences":
                    result = self.service.preference_update(data)
                elif action == "watch_create":
                    result = self.host.watch(data)
                elif action == "watch_stop":
                    result = self.host.stop_watch(data["job_id"])
                elif action in {"research_start", "research_status"}:
                    from .research import start, poll
                    result = (start if action == "research_start" else poll)(self.store, self.ctx, data)
                elif action == "notification_handoff":
                    result = self.handoff(data["id"])
                else:
                    if action == "notification_add" and not data.get("session_id"):
                        data = dict(data)
                        if data.get("goal_id"):
                            data["session_id"] = self.store.goal(data["goal_id"])[0].get("session_id")
                        elif data.get("interest_id"):
                            data["session_id"] = self.store.read("interest", data["interest_id"], {}).get("session_id")
                        elif not info["cron"]:
                            data["session_id"] = info["id"]
                    result = getattr(self.service, action)(data)
            return json.dumps({"ok": True, "result": result}, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            log.warning("Hermes Muse action %s failed: %s", args.get("action"), exc)
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def handoff(self, key):
        row = self.store.read("notification", key)
        if not row:
            raise ValueError("Unknown notification")
        session = self.store.read("session", row.get("session_id", ""), {})
        if row.get("handoff_accepted"):
            return {"accepted": True, "delivery": "not yet confirmed"}
        route = session.get("route") or {}
        if session.get("active") or not route.get("session_key"):
            return self.service.notification_queue({"id": key})
        # Existing host consent only; this plugin never writes allow_gateway_injection.
        message = ("[Hermes Muse background evidence] A prepared candidate is available: " + key +
                   ". Read hermes-muse:companion and muse_manage context. Recheck evidence, user preference, expiry and prior delivery; "
                   "then notification_queue if worthwhile, or dismiss. This is background data, not a new user request. Do not send a second copy in your final reply.")
        accepted = self.ctx.inject_message(message, session_key=route["session_key"])
        if accepted:
            row["handoff_accepted"] = True
            self.store.write("notification", key, row)
            return {"accepted": True, "delivery": "not yet confirmed"}
        return self.service.notification_queue({"id": key})

    def pre_turn(self, session_id="", turn_id="", user_message="", platform="", parent_session_id="", **kwargs):
        info = session_info()
        if self.closed or parent_session_id or info["cron"] or platform in {"cron", "delegate", "subagent", "webhook", "msgraph_webhook", "kanban"} or not private_session(info):
            return None
        text = user_message if isinstance(user_message, str) else json.dumps(user_message, ensure_ascii=False)
        if text.startswith("[Hermes Muse background evidence]"):
            return None
        if not session_id or not turn_id or not text.strip():
            return None
        with self.lock:
            timer = self.timers.pop(session_id, None)
            if timer:
                timer.cancel()
        self.service.signal(turn_id, session_id, text, route_from(info))
        return {"context": f"[Hermes Muse state pointer] This real user turn has signal_id={turn_id}. Companion workspace: {self.store.root}. For goals, interests, feedback, reminders or Feed, load hermes-muse:companion and use muse_manage. Read current state before using old memories as an active goal. This pointer does not authorize extra tasks."}

    def post_turn(self, session_id="", turn_id="", **kwargs):
        session = self.store.read("session", session_id)
        if not session or session.get("turn_id") != turn_id:
            return
        with self.store.transaction() as db:
            session = self.store.get(db, "session", session_id, {})
            if session.get("turn_id") != turn_id:
                return
            session["active"] = False
            self.store.put(db, "session", session_id, session)
        signal = self.store.read("signal", turn_id, {})
        if len(signal.get("text", "")) < 80:
            return
        with self.lock:
            if self.closed:
                return
            previous = self.timers.pop(session_id, None)
            if previous:
                previous.cancel()
            timer = threading.Timer(self.quiet_seconds, self.quiet_pass, args=(session_id, turn_id))
            timer.daemon = True
            self.timers[session_id] = timer
            timer.start()

    def quiet_pass(self, session_id, turn_id):
        with self.lock, profile_scope(self.home):
            if self.closed:
                return
            session = self.store.read("session", session_id, {})
            if session.get("active") or session.get("turn_id") != turn_id:
                return
            today = self.host.local_now(time.time()).date().isoformat()
            with self.store.transaction() as db:
                count = self.store.get(db, "budget", "quiet:" + today, 0)
                if count >= 3:
                    return
                self.store.put(db, "budget", "quiet:" + today, count + 1)
            self.host.wake("memory-upkeep")
            self.timers.pop(session_id, None)

    def end_turn(self, session_id="", turn_id="", **kwargs):
        # Failed/interrupted turns must also release the local attention hold.
        with self.store.transaction() as db:
            row = self.store.get(db, "session", session_id)
            if row and row.get("turn_id") == turn_id:
                row["active"] = False
                self.store.put(db, "session", session_id, row)

    def close(self):
        with self.lock:
            self.closed = True
            for timer in self.timers.values():
                timer.cancel()
            self.timers.clear()


def register(ctx):
    from hermes_constants import get_hermes_home
    required = ("register_tool", "register_skill", "register_system_prompt_section", "register_hook", "on_unload")
    if any(not callable(getattr(ctx, name, None)) for name in required):
        raise RuntimeError("Hermes Muse needs Hermes 0.21.5+ with prompt sections, plugin skills and unload hooks")
    runtime = Runtime(ctx, get_hermes_home(), plugin_root=ctx.manifest.path)
    runtime.host.initialize()
    prompt = (runtime.host.root / "prompts/system.md").read_text(encoding="utf-8").replace("{{MUSE_HOME}}", str(runtime.store.root)).replace("{{HERMES_HOME}}", str(runtime.home))
    ctx.register_skill("companion", runtime.host.root / "skills/companion/SKILL.md", description="Goals, memory upkeep, proactive reminders, reflection, Feed and research lifecycle")
    ctx.register_system_prompt_section("hermes-muse.companion", prompt, position="after_memory", max_chars=4000)
    ctx.register_tool(name="muse_manage", toolset="muse", schema=SCHEMA, handler=runtime.handle)
    ctx.register_hook("pre_llm_call", runtime.pre_turn)
    ctx.register_hook("post_llm_call", runtime.post_turn)
    ctx.register_hook("on_session_end", runtime.end_turn)
    ctx.on_unload(runtime.close)
