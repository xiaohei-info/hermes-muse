"""WP5 acceptance: the model surface (design 2.6, 7.1; 7.3 A9/A11 contract side) on synthetic homes.

S1-S4 are static: action counts, schemas rendered from the one table and packets.SCHEMAS, the generated
reference is fresh, prompts and skill carry no hand-written field list or removed action. S5-S9 drive both
tools through Surface on a recording fake host. S10 (when Hermes is importable) runs the schemas through
Hermes' own provider sanitizers and the job entry and caller() against the real HostAdapter in a temporary home.
No real user data, no live channel. Usage: PYTHONPATH=<hermes-agent> <hermes venv python> tests/surface_acceptance.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from kernel_acceptance import D, T0, FakeHost, make_home  # noqa: E402
from hermes_muse import entry, install, surface as s  # noqa: E402
from hermes_muse.kernel import Kernel, packets, records  # noqa: E402

FAILED = []
MAIN_CALL = {"kind": "user", "session_id": "chat"}
CRON_CALL = {"kind": "cron", "session_id": "cronrun"}
REMOVED = re.compile(r"\b(notification_(?:add|refresh|review|resolve|prepare|queue|handoff)|source_check|review_complete|"
                     r"run_complete|operations_\w+|finding_record|research_(?:start|status)|content_read|feed_add|feed_list|"
                     r"calendar_window|conversation_read|memory_feedback_review|request_id|signal_id|context\(section)")


def check(name, ok, detail=""):
    print(f"{name} {'PASS' if ok else 'FAIL'} {json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str)[:600]}")
    if not ok:
        FAILED.append(name)


def static():
    kinds = [kind for kind, _, _ in s.MAIN.values()]
    check("S1 counts: muse_manage 14 (11 write + 3 read), muse_job read/observe/submit",
          len(s.MAIN) == 14 and kinds.count("write") == 11 and kinds.count("read") == 3 and list(s.JOB_ACTIONS) == ["read", "observe", "submit"],
          {"main": len(s.MAIN), "writes": kinds.count("write"), "reads": kinds.count("read"), "job": list(s.JOB_ACTIONS)})
    schemas = {t: s.tool_schema(t) for t in s.TOOLS}
    branches = {t: [b["title"] for b in schemas[t]["parameters"]["properties"]["data"]["anyOf"]] for t in s.TOOLS}
    results = s.JOB_ACTIONS["submit"][2]["properties"]["results"]["items"]["anyOf"]
    check("S2 tool schemas generated from the table; submit results are packets.SCHEMAS verbatim",
          all(branches[t] == list(s.TOOLS[t]) == schemas[t]["parameters"]["properties"]["action"]["enum"] for t in s.TOOLS)
          and [{k: v for k, v in r.items() if k != "title"} for r in results] == list(packets.SCHEMAS.values())
          and all(not set(sc["parameters"]) & {"anyOf", "oneOf", "allOf"} for sc in schemas.values()),
          {t: len(json.dumps(sc)) for t, sc in schemas.items()})
    check("S3 skill reference regenerated from code (single contract source)",
          s.REFERENCE.read_text(encoding="utf-8") == s.reference(), str(s.REFERENCE.relative_to(ROOT)))
    jobs = sorted(p.stem for p in (ROOT / "prompts/jobs").glob("*.md"))
    long = {p.name: n for p in (ROOT / "prompts/jobs").glob("*.md") if (n := len(p.read_text(encoding="utf-8").strip().splitlines())) > 15}
    docs = [ROOT / "prompts/system.md", *(ROOT / "prompts/jobs").glob("*.md"), *(ROOT / "skills/companion").rglob("*.md")]
    stale = {str(p.relative_to(ROOT)): sorted(set(REMOVED.findall(p.read_text(encoding="utf-8")))) for p in docs if REMOVED.search(p.read_text(encoding="utf-8"))}
    tables = [str(p.relative_to(ROOT)) for p in docs if p != s.REFERENCE and re.search(r"^\|\s*`?field`?\s*\|", p.read_text(encoding="utf-8"), re.M)]
    check("S4 five job prompts <=15 lines (the no-agent deliver job has none); no removed action, request_id or hand-written field table in prompts/skill",
          jobs == sorted(j for j, _, _ in install.JOBS.values() if j not in install.NO_AGENT) == sorted([*packets.JOBS, "weekly"]) and not long and not stale and not tables,
          {"jobs": jobs, "long": long, "stale": stale, "tables": tables})


class Host(FakeHost):
    def __init__(self, clock):
        super().__init__(clock)
        self.jobs, self.ensured = {"j-intake": {"name": "muse-intake", "enabled": True}}, []
        self.cron = SimpleNamespace(pause=self.pause, outcome=lambda job_id, execution_id=None: None,
                                    jobs=lambda: dict(self.jobs), ensure=self.ensure, wake=lambda job_id: True,
                                    job=lambda key: None)

    def pause(self, job_id, reason):
        self.paused.append(job_id)
        return job_id in self.jobs

    def ensure(self, key, **kwargs):
        self.ensured.append((key, kwargs))
        self.jobs["j-" + key] = {"name": "muse-" + key, "enabled": True}
        return {"id": "j-" + key}


def job_output(k, key):
    """Script Output of one launcher run (cron_entry -> entry.output): the packet JSON, '' when silent."""
    out = entry.output(k, key)
    return "" if not out["wakeAgent"] else json.dumps(out.get("packet") or out, ensure_ascii=False)


def writes_only_in_kernel():
    hits = {f: n for f in ("surface.py", "hooks.py", "entry.py", "install.py", "views.py")
            if (n := len(re.findall(r"store\.(?:create|transition|attempt)\(|\bpatch\(", (ROOT / "hermes_muse" / f).read_text(encoding="utf-8"))))}
    check("S11 entity state is written only in kernel/: surface, hooks, entry, install and views call kernel functions",
          not hits, hits)


def dynamic(base):
    clock = [T0]
    host = Host(lambda: clock[0])
    home = make_home(base, {"goal_dormant_days": 7, "goal_fade_days": 7})
    k = Kernel(home, adapter=host, clock=lambda: clock[0])
    host.home = k.home
    ui = s.Surface(k)

    def call(tool, action, data, caller=MAIN_CALL):
        return ui.handle(tool, {"action": action, "data": data}, caller)

    # S5 validation names the field; nothing is coerced
    errors = [call("muse_manage", "goal_create", {"title": "x"}), call("muse_manage", "preferences", {"start_hour": "9"}),
              call("muse_manage", "goal_update", {"goal_id": "g", "colour": "red"}),
              call("muse_manage", "feedback", {"kind": "notice", "id": "n", "value": "meh"}), call("muse_manage", "nope", {})]
    check("S5 argument errors are field-level and actionable",
          [e.get("field") for e in errors] == ["data.criteria", "data.start_hour", "data.colour", "data.value", "action"]
          and all(not e["ok"] and e["code"] == "invalid_argument" for e in errors), [e["error"] for e in errors])

    # S6 main-session writes and reads
    g = call("muse_manage", "goal_create", {"title": "Renew passport", "criteria": "New passport in hand",
                                            "deadline": "2026-12-01T00:00:00+00:00"})
    again = call("muse_manage", "goal_create", {"title": "renew  PASSPORT", "criteria": "dup"})
    call("muse_manage", "goal_create", {"title": "Learn piano", "criteria": "Play one piece"})  # left idle: goes dormant
    slug = g["result"]["goal_id"]
    up = call("muse_manage", "goal_update", {"goal_id": slug, "progress_note": "Photos taken", "waiting_user": True})
    goal_state = k.store.get(f"goal:{slug}")
    interest = call("muse_manage", "interest_record", {"title": "Local jazz", "rationale": "mentioned twice"})
    renewed = call("muse_manage", "interest_record", {"title": "local jazz"})
    idea = call("muse_manage", "idea_add", {"title": "Try the new bakery", "goal_id": slug})
    prefs = call("muse_manage", "preferences", {"ordinary_per_day": 2, "fade_question": "「{title}」已 {days} 天没有进展，还要继续吗？{date} 后自动关闭。",
                                                "notes": "## Coverage scope\nMail and calendar only."})
    note = call("muse_manage", "content_write", {"kind": "note", "id": "person:alice", "body": "# Alice\n", "expected_revision": "absent"})
    read_note = call("muse_manage", "read", {"kind": "note", "id": "person:alice"})
    conflict = call("muse_manage", "content_write", {"kind": "note", "id": "person:alice", "body": "x", "expected_revision": "absent"})
    listed = call("muse_manage", "read", {"kind": "goal"})
    status = call("muse_manage", "read", {"kind": "status"})
    pref_read = call("muse_manage", "read", {"kind": "preferences"})
    check("S6 main writes: user goal without signal (deduped by title), goals.update(by=user), interest/idea, preferences keep body, content CAS, reads",
          g["ok"] and again["result"] == {"result": "existing", "goal_id": slug} and up["ok"] and goal_state["state"] == "waiting"
          and interest["result"]["result"] == "recorded" and renewed["result"]["result"] == "renewed" and idea["ok"] and prefs["ok"]
          and note["result"]["result"] == "written" and read_note["result"]["revision"] == note["result"]["revision"]
          and conflict["code"] == "revision_conflict" and listed["result"]["total"] == 2 and "open" in status["result"]
          and "Mail and calendar only." in pref_read["result"]["body"] and '"ordinary_per_day": 2' in pref_read["result"]["body"],
          {"goal": g, "update": up, "conflict": conflict.get("code"), "status": status["result"]["open"]["goal"]})

    # S7 dormancy question in the user's language (WP4 hook), watch create/stop, feedback, forget
    clock[0] = T0 + 9 * D
    k.tick()
    ask = next((n for n in k.store.query("notice") if n["payload"].get("topic") == "goal-fade"), None)
    watch = call("muse_manage", "watch_create", {"goal_id": slug, "schedule": "every 6h", "prompt": "Check the appointment page",
                                                 "stop_condition": "an appointment is booked"})
    stop = call("muse_manage", "watch_stop", {"watch_id": watch["result"]["watch_id"]})
    fb = call("muse_manage", "feedback", {"kind": "interest", "id": interest["result"]["id"], "value": "stop"})
    gone = call("muse_manage", "forget", {"kind": "note", "id": "person:alice", "expected_revision": read_note["result"]["revision"]})
    prep = call("muse_manage", "installation_prepare", {"operation": "disable"})
    paused = call("muse_manage", "preferences", {"pause_jobs": True})
    ensured = host.ensured[0] if host.ensured else (None, {})
    check("S7 fade question uses the user's template; watch job via host cron and stop pauses it; feedback stops; forget deletes; disable plan + pause",
          ask is not None and ask["payload"]["text"].startswith("「Learn piano」已 7 天") and watch["ok"]
          and ensured[1].get("entry") == s.ROOT / "cron_entry.py" and stop["result"]["job_paused"]
          and fb["result"]["state"] == "stopped" and gone["result"]["result"] == "deleted"
          and prep["result"]["read_only"] and paused["result"]["paused_jobs"] == list(host.jobs),
          {"ask": ask and ask["payload"]["text"], "watch": watch, "fb": fb, "paused": paused})

    # S8 job runs: entry output, read/observe/submit, feed file written by the content writer
    host.add("chat", "user", "I decided: dentist on Friday at 3pm", clock[0] + 10)
    clock[0] += 60
    out = job_output(k, "memory-upkeep")
    packet = json.loads(out)
    item = packet["items"][0]
    read = call("muse_job", "read", {"packet_id": packet["id"], "ref": item["ref"]}, CRON_CALL)
    sub = call("muse_job", "submit", {"packet_id": packet["id"], "results": [
        {"ref": item["ref"], "disposition": "saved", "facts": ["Dentist Friday 3pm"], "goal_hint": "new"}]}, CRON_CALL)
    patrol = json.loads(job_output(k, "proactive-watch"))
    obs = call("muse_job", "observe", {"packet_id": patrol["id"], "source_id": "mail:work",
                                       "items": [{"upstream_id": "<m1@example.com>", "title": "Invoice due today", "ts": clock[0]}]}, CRON_CALL)
    verdict = call("muse_job", "submit", {"packet_id": patrol["id"], "results": [
        {"candidate_ref": obs["result"]["items"][0]["ref"], "verdict": "send", "text": "Invoice due today", "priority": "time_sensitive"}]}, CRON_CALL)
    # interest stopped above: record a fresh one for the feed packet
    call("muse_manage", "interest_record", {"title": "Rust async"})
    feed = json.loads(job_output(k, "feed-pulse"))
    fsub = call("muse_job", "submit", {"packet_id": feed["id"], "results": [{"interest_ref": feed["items"][0]["ref"], "article": {
        "title": "Async drop", "body": "What changed and why it matters.", "source_refs": ["https://example.com/a"]}}]}, CRON_CALL)
    path = fsub["result"][0].get("path", "")
    feed_file = home / "muse" / path
    listed_feed = call("muse_manage", "read", {"kind": "feed"})
    deleted = call("muse_manage", "feed_update", {"id": listed_feed["result"]["items"][0]["id"], "change": "delete"})
    empty_nightly = job_output(k, "feed-pulse")
    weekly = json.loads(job_output(k, "weekly-governance-review"))
    check("S8 job runs: packet as Script Output, read/submit/observe through muse_job, article file written then deleted, empty packet silent",
          read["ok"] and sub["result"][0].get("state") == "disposed" and obs["ok"] and verdict["result"][0].get("result") == "drafted"
          and fsub["ok"] and "article" not in fsub["result"][0] and not feed_file.exists() and deleted["ok"]
          and path.startswith(records.FEED_DIR) and empty_nightly == "" and weekly["job"] == "weekly" and "signal" in weekly["last_7_days"],
          {"submit": sub, "verdict": verdict, "feed": fsub, "weekly": weekly["last_7_days"]})

    # S9 authorization by caller: cron/delegated/group/main boundaries
    denied = {
        "cron_goal_create": call("muse_manage", "goal_create", {"title": "t", "criteria": "c"}, CRON_CALL),
        "cron_preferences": call("muse_manage", "preferences", {"start_hour": 8}, CRON_CALL),
        "cron_tools_note": call("muse_manage", "content_write", {"kind": "tools_note", "id": "current", "body": "x", "expected_revision": "absent"}, CRON_CALL),
        "child_write": call("muse_manage", "idea_add", {"title": "x"}, {**MAIN_CALL, "kind": "child"}),
        "group": call("muse_manage", "read", {"kind": "goal"}, {**MAIN_CALL, "kind": "group"}),
        "machine_goal_create": call("muse_manage", "goal_create", {"title": "t", "criteria": "c"}, {**MAIN_CALL, "kind": "other"}),
        "main_submit": call("muse_job", "submit", {"packet_id": "p", "results": []}),
    }
    allowed = [call("muse_manage", "content_write", {"kind": "dream", "id": "2026-11-07", "body": "# Dream\n", "expected_revision": "absent"}, CRON_CALL),
               call("muse_manage", "read", {"kind": "goal"}, {**MAIN_CALL, "kind": "child"}),
               call("muse_manage", "read", {"kind": "goal"}, CRON_CALL)]  # any cron run, also the user's own jobs
    check("S9 authorization: only the private main session changes state; any cron reads and writes notes/dreams/alignment, "
          "Muse jobs submit; children read; group and machine callers are refused",
          all(r["code"] == "permission_denied" for r in denied.values()) and all(r["ok"] for r in allowed),
          {n: r.get("code") for n, r in denied.items()})

    # One gate to the model: every result redacted; every read pages at READ_MAX; no tool runs while install migrates.
    body = "password: hunter22-synthetic\n" + "x" * 30000
    call("muse_manage", "content_write", {"kind": "note", "id": "person:long", "body": body, "expected_revision": "absent"})
    first = call("muse_manage", "read", {"kind": "note", "id": "person:long"})["result"]
    rest = call("muse_manage", "read", {"kind": "note", "id": "person:long", "offset": first["next_offset"]})["result"]
    for i in range(80):
        call("muse_manage", "idea_add", {"title": f"synthetic idea {i} " + "y" * 150})
    listed = call("muse_manage", "read", {"kind": "idea", "limit": 100})["result"]
    marker = k.home / "muse" / "migrating.json"
    marker.write_text(json.dumps({"at": clock[0], "pid": 1}))
    busy = call("muse_manage", "read", {"kind": "goal"})
    marker.unlink()
    check("S12 model gate: results redacted, reads paged at 12k with next_offset, tools refused while an install runs",
          "hunter22" not in json.dumps(first) and len(first["body"]) <= s.READ_MAX and first["next_offset"] == s.READ_MAX
          and "next_offset" in rest and len(json.dumps(listed)) < 2 * s.READ_MAX and listed["next_offset"] == len(listed["items"])
          and busy["code"] == "host_unavailable",
          {"page": len(first["body"]), "listed": len(listed["items"]), "busy": busy})


def native(base):
    try:
        from tools.schema_sanitizer import sanitize_tool_schemas
        from agent.anthropic_message_convert import _normalize_tool_input_schema
        from agent.gemini_schema import sanitize_gemini_schema
    except ImportError as exc:
        print(f"S10 SKIP Hermes not importable: {exc}")
        return
    import os
    schemas = [s.tool_schema(t) for t in s.TOOLS]
    sanitized = sanitize_tool_schemas([{"type": "function", "function": sc} for sc in schemas])
    kept = all(len(f["function"]["parameters"]["properties"]["data"]["anyOf"]) == len(s.TOOLS[f["function"]["name"]]) for f in sanitized)
    anthropic = [_normalize_tool_input_schema(sc["parameters"]) for sc in schemas]
    gemini = [sanitize_gemini_schema(sc["parameters"]) for sc in schemas]
    home = base / "native-home"
    (home / "muse").mkdir(parents=True)
    os.environ["HERMES_HOME"] = str(home)
    from hermes_muse.host import HostAdapter
    from hermes_state import SessionDB
    SessionDB(db_path=home / "state.db").close()
    import sqlite3
    with sqlite3.connect(home / "state.db") as db:  # what Hermes writes before the first tool call of a turn
        db.executemany("INSERT INTO sessions (id, source, started_at) VALUES (?, ?, 0)",
                       [("native", "cli"), ("phone", "ios"), ("hook", "webhook"), ("q", "oneshot")])
    adapter = HostAdapter(home)
    # Isolated from the shell that runs the test: no inherited session env, only this temporary home's state.db.
    for name in [n for n in os.environ if n.startswith("HERMES_SESSION_") or n in ("HERMES_CRON_SESSION", "HERMES_PLATFORM")]:
        del os.environ[name]
    # Tool handlers get no platform: the stored sessions.source decides (same USER_SOURCES list as Signals).
    caller = {**{sid: adapter.caller(session_id=sid) for sid in ("native", "phone", "hook", "q", "missing")},
              **{p: adapter.caller(session_id="x", platform=p) for p in ("cli", "ios", "webhook", "api_server", "kanban", "local")}}
    # An inherited env naming a user surface never widens a stored machine source and never stands in for a missing row.
    os.environ["HERMES_SESSION_SOURCE"] = "cli"
    inherited = {sid: adapter.caller(session_id=sid) for sid in ("native", "hook", "q", "missing")}
    del os.environ["HERMES_SESSION_SOURCE"]
    k = Kernel(home, adapter=adapter)
    out = {job: job_output(k, key) for key, (job, _, _) in install.JOBS.items() if job in ("intake", "nightly", "feed")}
    registered = []
    s.register(SimpleNamespace(register_tool=lambda **kw: registered.append(kw)), k)
    reply = json.loads(registered[0]["handler"]({"action": "read", "data": {"kind": "goal"}}, session_id="native"))
    check("S10 native: Hermes sanitizers keep every branch; caller() allows only USER_SOURCES (CLI via its stored source, ios) "
          "and refuses machine/unknown callers; job entry runs on the real adapter; registered handler answers",
          kept and all(a.get("type") == "object" for a in anthropic) and all(g.get("properties") for g in gemini)
          and caller == {"native": "user", "phone": "user", "hook": "other", "q": "other", "missing": "other", "cli": "user",
                         "ios": "user", "webhook": "other", "api_server": "other", "kanban": "other", "local": "other"}
          and inherited == {"native": "user", "hook": "other", "q": "other", "missing": "other"}
          and out == {"intake": "", "nightly": "", "feed": ""}
          and [r["name"] for r in registered] == list(s.TOOLS) and reply["ok"],
          {"caller": caller, "inherited_env_cli": inherited, "faults": list(adapter.faults)[:3], "reply": reply})


def main():
    static()
    writes_only_in_kernel()
    with tempfile.TemporaryDirectory() as tmp:
        dynamic(Path(tmp) / "a")
        native(Path(tmp) / "b")
    print("RESULT", "FAIL " + ",".join(FAILED) if FAILED else "PASS")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
