"""Model surface (design 2.6): one action table from which the tool schemas, argument validation, dispatch
and the skill's interface reference are all generated; there is no second, hand-written field list.

muse_manage: the main session's 14 user-semantic actions (11 writes, 3 reads). A cron run may use only
read, calendar_view and content_write of notes/dreams/alignment; a delegated child only reads.
muse_job: a Muse job run's read / observe / submit against the packet in its Script Output; the submit
result shapes are kernel.packets.SCHEMAS. Code fills every ID, key, next_check and managed revision;
only content files take an expected_revision.
Every result passes one gate on its way to the model (`host.sessions.clean`: all text redacted), and every read
pages at READ_MAX characters (offset/next_offset), so no Muse read hands the model unbounded or raw text.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from . import health, install
from .content_io import DomainError, Files, revision
from .host.sessions import READ_MAX, clean
from .kernel import goals, packets, records
from .kernel.common import header, one, render
from .kernel.packets import enum, obj
from .locks import file_lock

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/companion/references/interface.md"


def text(limit, description=None):
    return {"type": "string", "maxLength": limit, **({"description": description} if description else {})}


def nullable(schema):
    return {**schema, "type": [schema["type"], "null"]}


ID = {"type": "string", "maxLength": 200, "description": "an id returned by Muse"}
TIME = {"type": "string", "maxLength": 40, "description": "ISO 8601, e.g. 2026-11-02T18:00:00+08:00 (no offset: profile time)"}
BOOL = {"type": "boolean"}


def count(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


ENTITY_KINDS = ("goal", "notice", "finding", "feed", "interest", "idea", "watch", "source", "signal")
CONTENT = {  # kind -> id description; paths under <home>/muse
    "note": "daily:YYYY-MM-DD, person:<name> or group:<name>",
    "dream": "YYYY-MM-DD",
    "alignment": "current",
    "tools_note": "current (TOOLS.md)",
    "working_lessons": "current (AGENTS.md)",
    "preferences": "current (read only; change it with preferences)",
    "goal_file": "<goal id>/<name>.md",
}
CRON_CONTENT = ("note", "dream", "alignment")
WRITABLE = tuple(k for k in CONTENT if k != "preferences")
FORGETTABLE = ("signal", "interest", "idea", "feed", "note", "dream", "goal_file")

MAIN = {  # action: (kind, summary, data schema)
    "goal_create": ("write", "Create a goal the user accepted in this conversation; same title twice returns the existing goal.",
                    obj(["title", "criteria"], title=text(200), criteria=text(4000, "what done looks like"),
                        deadline=TIME, parent_id=ID, no_fade={**BOOL, "description": "only on the user's explicit request"})),
    "goal_update": ("write", "Change a goal for the user: status, waiting, deadline, owner or a progress note. Any update moves the next check to tomorrow unless next_check_at is given.",
                    obj(["goal_id"], goal_id=ID, title=text(200), status=enum("active", "done", "cancelled"),
                        waiting_user=BOOL, deadline=nullable(TIME), no_fade=BOOL,
                        owner=nullable(text(200, "native delegation handle now working on it")),
                        next_check_at=TIME, progress_note=text(1000))),
    "interest_record": ("write", "Remember a temporary interest (Feed and patrol use it); 14 days unless expires.",
                        obj(["title"], title=text(200), rationale=text(2000), expires=TIME)),
    "idea_add": ("write", "Keep an idea for later; 14 days unless expires.",
                 obj(["title"], title=text(200), rationale=text(2000), goal_id=ID, expires=TIME,
                     sources={"type": "array", "items": text(1000), "maxItems": 20})),
    "preferences": ("write", "Change proactive preferences; pause_jobs=true pauses every Muse job (after installation_prepare and the user's confirmation).",
                    obj([], start_hour=count(0, 23), end_hour=count(0, 24), ordinary_per_day=nullable(count(0, 50)),
                        time_sensitive_per_day=nullable(count(0, 50)),
                        urgent_per_day={**count(0, 50), "description": "urgent notices that may skip quiet hours per day; more are sent as time_sensitive"},
                        blocked_topics={"type": "array", "items": text(100), "maxItems": 50},
                        deliver=nullable(text(200, "route of the muse-deliver job (notices), e.g. bot-chat or telegram; applied from its next run, null keeps the job's route")),
                        goal_dormant_days=nullable(count(1, 365)), goal_fade_days=nullable(count(1, 365)),
                        fade_question=nullable(text(500, "dormancy question in the user's language with {title}, {days}, {date}")),
                        weather_context={**BOOL, "description": "allow weather checks for known plans (uses the user's location)"},
                        notes=text(8000, "free-text body of PROACTIVE_PREFERENCES.md: coverage scope, topics to avoid, Feed brief"),
                        pause_jobs=BOOL)),
    "feedback": ("write", "The user's reaction to a notice, interest, idea or review finding; stop ends an interest/idea and withdraws an unsent notice.",
                 obj(["kind", "id", "value"], kind=enum("notice", "interest", "idea", "finding"), id=ID,
                     value=enum("useful", "not_useful", "stop"), note=text(500))),
    "forget": ("write", "Delete what the user asked Muse to forget; content kinds need expected_revision.",
               obj(["kind", "id"], kind=enum(*FORGETTABLE), id=ID, expected_revision=text(80))),
    "watch_create": ("write", "Watch something for an open goal on a schedule; the run reports only when the stop condition is met or something changed.",
                     obj(["goal_id", "schedule", "prompt", "stop_condition"], goal_id=ID,
                         schedule=text(100, "Hermes cron schedule, e.g. every 2h or 0 9 * * *"),
                         prompt=text(4000, "what to check and how"), stop_condition=text(1000), expires=TIME)),
    "watch_stop": ("write", "Stop a watch.", obj(["watch_id"], watch_id=ID)),
    "feed_update": ("write", "Feedback on, pin, unpin or delete a Feed article.",
                    obj(["id", "change"], id=ID, change=enum("feedback", "pin", "unpin", "delete"), feedback=text(1000))),
    "content_write": ("write", "Write a note, person/group page, dream, alignment, TOOLS.md, AGENTS.md or goal file; read it first for its revision ('absent' when new).",
                      obj(["kind", "id", "body", "expected_revision"], kind=enum(*WRITABLE), id=text(200),
                          body=text(60000), expected_revision=text(80))),
    "read": ("read", "Read Muse state: one entity or file by id, or a list (query filters, newest first). Text pages at 12k characters: pass next_offset as offset. kind=status gives health and counts.",
             obj(["kind"], kind=enum("status", *ENTITY_KINDS, *CONTENT), id=text(200), query=text(200),
                 limit=count(1, 100), offset=count(0, 10 ** 7))),
    "calendar_view": ("read", "Without window: the window for mode. With that window unchanged plus sources: the merged schedule.",
                      obj([], mode=enum("rolling", "month"), window={"type": "object", "description": "returned by calendar_view"},
                          sources={"type": "array", "items": {"type": "object"}, "description": "see the calendar reference"},
                          discovery_complete=BOOL)),
    "installation_prepare": ("read", "Read-only plan for disabling or removing Muse: owned jobs and the confirmed steps.",
                             obj(["operation"], operation=enum("disable", "remove"))),
}
JOB_ACTIONS = {
    "read": ("read", "Original text of a packet item beyond its excerpt (12k per call, 24k per item).",
             obj(["packet_id", "ref"], packet_id=ID, ref=text(200), offset=count(0, 10 ** 7))),
    "observe": ("write", "Record one source check of a patrol packet with the items seen (upstream IDs as the source gives them).",
                obj(["packet_id", "source_id", "items"], packet_id=ID,
                    source_id=text(64, "<kind>:<account>, e.g. mail:work, calendar:home"),
                    items={"type": "array", "maxItems": packets.OBSERVE_MAX, "items": obj(
                        ["title"], upstream_id=text(500, "message-id, event id+revision, reminder id or URL"),
                        title=text(300), ts={"type": "number", "description": "epoch seconds"}, url=text(1000))},
                    limitation_code=text(64, "a stable code when the source could only be read partly"),
                    error=text(300, "the source could not be read"))),
    "submit": ("write", "Results for packet items, one per item; the packet's schema lists the shapes. Idempotent per item.",
               obj(["packet_id", "results"], packet_id=ID,
                   results={"type": "array", "maxItems": 100,
                            "items": {"anyOf": [{**s, "title": name} for name, s in packets.SCHEMAS.items()]}})),
}
TOOLS = {"muse_manage": MAIN, "muse_job": JOB_ACTIONS}
DESCRIPTIONS = {
    "muse_manage": "Hermes Muse: goals, interests, ideas, preferences, watches, Feed, notes and calendar for the user "
                   "of this private conversation. Arguments go inside data. Muse fills IDs, keys and next checks; only "
                   "content_write and content forget take an expected_revision (from read).",
    "muse_job": "Hermes Muse job runs only: read, observe and submit against the packet in this run's Script Output. "
                "Arguments go inside data; refs come from the packet.",
}


def tool_schema(tool):
    actions = TOOLS[tool]
    lines = [f"{name}: {summary}" for name, (_, summary, _) in actions.items()]
    return {"name": tool, "description": DESCRIPTIONS[tool] + "\n" + "\n".join(lines), "parameters": {
        "type": "object", "required": ["action", "data"], "properties": {
            "action": {"type": "string", "enum": list(actions)},
            "data": {"anyOf": [{**schema, "title": name} for name, (_, _, schema) in actions.items()]}}}}


# -- validation: the subset of JSON Schema the table uses ------------------------------------------
def fits(kind, value):
    return {"integer": type(value) is int, "number": type(value) in (int, float), "boolean": type(value) is bool,
            "string": isinstance(value, str), "array": isinstance(value, list), "object": isinstance(value, dict),
            "null": value is None}[kind]


def check(schema, value, path):
    """Raise DomainError naming the field and what it must be; nothing else is coerced or guessed."""
    if "anyOf" in schema:  # the branch whose required fields are present reports its error
        branches = sorted(schema["anyOf"], key=lambda b: -sum(f in value for f in b.get("required", ()))
                          if isinstance(value, dict) else 0)
        errors = []
        for branch in branches:
            try:
                return check(branch, value, path)
            except DomainError as exc:
                errors.append(exc)
        raise errors[0]
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []
    if kinds and not any(fits(k, value) for k in kinds):
        raise bad(path, f"must be {' or '.join(kinds)}, got {type(value).__name__}")
    if value is None:
        return
    if "enum" in schema and value not in schema["enum"]:
        raise bad(path, f"must be one of {', '.join(schema['enum'])}, got {json.dumps(value, ensure_ascii=False)[:80]}")
    if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
        raise bad(path, f"is {len(value)} characters; at most {schema['maxLength']}")
    if type(value) in (int, float) and not schema.get("minimum", value) <= value <= schema.get("maximum", value):
        raise bad(path, f"must be between {schema.get('minimum')} and {schema.get('maximum')}")
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)):
            raise bad(path, f"must have {schema.get('minItems', 0)}–{schema.get('maxItems')} items")
        for i, item in enumerate(value):
            check(schema.get("items", {}), item, f"{path}[{i}]")
    if isinstance(value, dict) and "properties" in schema:
        missing = [f for f in schema.get("required", ()) if value.get(f) in (None, "")]
        if missing:
            raise bad(f"{path}.{missing[0]}", "is required" + (f" ({schema['title']})" if "title" in schema else ""))
        extra = sorted(set(value) - set(schema["properties"]))
        if extra and schema.get("additionalProperties") is False:
            raise bad(f"{path}.{extra[0]}", f"is not a field here; fields: {', '.join(schema['properties'])}")
        for name, sub in schema["properties"].items():
            if name in value:
                check(sub, value[name], f"{path}.{name}")


def bad(path, problem):
    return DomainError("invalid_argument", f"{path} {problem}", field=path)


def content_path(kind, key):
    key = str(key)
    if kind == "note":
        category, _, name = key.partition(":")
        if category == "daily":
            return f"memory/{datetime.strptime(name, '%Y-%m-%d').date().isoformat()}.md"
        if category in ("person", "group") and name and name.upper() != "INDEX":
            return f"memory/{'people' if category == 'person' else 'groups'}/{name}.md"
        raise ValueError("note id must be daily:YYYY-MM-DD, person:<name> or group:<name>")
    if kind == "dream":
        return f"dreams/{datetime.strptime(key, '%Y-%m-%d').date().isoformat()}.md"
    if kind == "goal_file":
        goal, _, name = key.partition("/")
        if not goal or not name.endswith(".md") or "/" in name:
            raise ValueError("goal_file id must be <goal id>/<name>.md")
        return f"{goals.ROOT}/{goal}/files/{name}"
    return {"alignment": "dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md", "tools_note": "TOOLS.md",
            "working_lessons": "AGENTS.md", "preferences": "PROACTIVE_PREFERENCES.md"}[kind]


def page(field, text, offset):
    """At most READ_MAX characters of `text` from `offset`, with next_offset while more remains."""
    part = text[offset:offset + READ_MAX]
    return {field: part, **({"next_offset": offset + len(part)} if offset + len(part) < len(text) else {})}


def row(e):
    p = e["payload"]
    label = p.get("title") or p.get("text") or p.get("message") or p.get("reason") or p.get("excerpt") or ""
    return {"id": e["id"], "state": e["state"], "title": str(label)[:200], "updated": e["updated"],
            **({"deadline": e["deadline"]} if e["deadline"] else {})}


class Surface:
    def __init__(self, kernel):
        self.k = kernel
        self.files = Files(kernel.home)

    def now(self):
        return self.k.clock()

    def time(self, value):
        if value is None:
            return None
        try:
            at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{value!r} is not an ISO 8601 time") from None
        return (at if at.tzinfo else at.replace(tzinfo=self.k.tz())).timestamp()

    def lock(self):
        return file_lock(self.k.home / "muse" / "mutations.lock")

    # -- entry -------------------------------------------------------------------------------------
    def handle(self, tool, args, caller):
        """{ok, result} or {ok: false, code, error[, field]}; `caller` is {kind: HostAdapter.caller(), session_id}.
        Any cron run (a Muse job or the user's own) may read, view the calendar and write notes/dreams/alignment;
        muse_job additionally needs a packet id of that run."""
        try:
            actions = TOOLS[tool]
            if not isinstance(args, dict) or args.get("action") not in actions:
                raise bad("action", f"must be one of {', '.join(actions)}")
            action, data = args["action"], args.get("data", {})
            schema = actions[action][2]
            check({**schema, "title": action}, data, "data")
            self.authorize(tool, action, data, caller)
            marker = install.migrating(self.k.home)
            if marker and not marker.get("error"):  # an install still running may be migrating the Store
                raise DomainError("host_unavailable", "Muse is installing or upgrading; try again in a minute")
            return {"ok": True, "result": clean(getattr(self, f"{tool}_{action}")(dict(data), caller))}
        except DomainError as exc:
            return {"ok": False, "code": exc.code, "error": str(exc), **exc.details}
        except PermissionError as exc:
            return {"ok": False, "code": "permission_denied", "error": str(exc)}
        except KeyError as exc:
            return {"ok": False, "code": "not_found", "error": str(exc.args[0] if exc.args else exc)}
        except ValueError as exc:
            return {"ok": False, "code": "invalid_argument", "error": str(exc)}

    @staticmethod
    def authorize(tool, action, data, caller):
        kind = caller.get("kind")
        if kind not in ("user", "cron", "child"):
            raise PermissionError("Muse is available in private conversations only")
        if tool == "muse_job":
            if kind != "cron":
                raise PermissionError("muse_job belongs to a Muse job run")
        elif kind == "child":
            if MAIN[action][0] != "read":
                raise PermissionError("a delegated task may only read; changes belong to the parent conversation")
        elif kind == "cron" and action not in ("read", "calendar_view") and not (
                action == "content_write" and data.get("kind") in CRON_CONTENT):
            raise PermissionError("a job run may write only notes, dreams and alignment; it submits results through muse_job")

    # -- muse_manage writes ------------------------------------------------------------------------
    def muse_manage_goal_create(self, d, call):
        if d.get("parent_id") and not goals.read(self.k.home, d["parent_id"]):
            raise KeyError(f"unknown goal {d['parent_id']!r}")
        extra = {"deadline": self.time(d.get("deadline")), "parent_id": d.get("parent_id"), "no_fade": d.get("no_fade")}
        return goals.create(self.k, title=d["title"], criteria=d["criteria"], now=self.now(), by="user",
                            session_id=call.get("session_id"), extra={f: v for f, v in extra.items() if v is not None})

    def muse_manage_goal_update(self, d, call):
        slug = d.pop("goal_id")
        for field in ("deadline", "next_check_at"):
            if d.get(field):
                d[field] = self.time(d[field])
        record = goals.update(self.k, slug, d, by="user", now=self.now())
        return {"result": "updated", "goal_id": slug, "status": record.get("status"), "next_check_at": record.get("next_check_at")}

    def remember(self, kind, d, extra):
        return records.remember(self.k, kind, d["title"], rationale=d.get("rationale"), expires=self.time(d.get("expires")),
                                extra=extra, now=self.now())

    def muse_manage_interest_record(self, d, call):
        return self.remember("interest", d, {"session_id": call.get("session_id")})

    def muse_manage_idea_add(self, d, call):
        return self.remember("idea", d, {"goal_id": d.get("goal_id"), "sources": d.get("sources") or [], "origin": "user"})

    def muse_manage_preferences(self, d, call):
        pause = d.pop("pause_jobs", None)
        if d.get("fade_question"):
            try:
                d["fade_question"].format(title="t", days=7, date="2026-01-01")
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(f"fade_question may use only {{title}}, {{days}} and {{date}}: {exc}") from None
        rel = content_path("preferences", "current")
        with self.lock():
            try:
                raw = self.files.read(rel)
            except FileNotFoundError:
                raw = None
            old = (raw or b"").decode("utf-8")
            record = header(old)
            body = old.partition("\n")[2] if record is not None else old
            body = d.pop("notes", body)
            self.files.replace(rel, render({**(record or {}), **d}, body), revision(raw) if raw is not None else "absent")
        paused = [job_id for job_id in self.k.adapter.cron.jobs() if self.k.adapter.cron.pause(job_id, "paused by the user")] if pause else []
        return {"result": "saved", "changed": sorted(d), **({"paused_jobs": paused} if pause else {})}

    def muse_manage_feedback(self, d, call):
        return records.feedback(self.k, self.entity(d["kind"], d["id"]), d["value"], d.get("note"), now=self.now())

    def muse_manage_forget(self, d, call):
        kind = d["kind"]
        if kind in CONTENT:
            if not d.get("expected_revision"):
                raise ValueError("forgetting a file needs expected_revision from read")
            with self.lock():
                self.files.unlink(content_path(kind, d["id"]), d["expected_revision"])
            return {"result": "deleted", "kind": kind, "id": d["id"]}
        return records.forget(self.k, self.entity(kind, d["id"]), now=self.now())

    def muse_manage_watch_create(self, d, call):
        slug = d["goal_id"]
        n, key = goals.watch_slot(self.k, slug)
        job = install.ensure_watch(self.k.adapter, ROOT, key, schedule=d["schedule"], check=d["prompt"],
                                   stop_condition=d["stop_condition"])
        if not job:
            raise DomainError("host_unavailable", "Hermes did not create the watch job; nothing was saved")
        e = goals.add_watch(self.k, slug, n, job_id=job["id"], key=key, schedule=d["schedule"], check=d["prompt"],
                            stop_condition=d["stop_condition"], expires=self.time(d.get("expires")), now=self.now())
        return {"result": "created", "watch_id": e["id"], "job_id": job["id"], "expires": e["deadline"]}

    def muse_manage_watch_stop(self, d, call):
        e = self.entity("watch", d["watch_id"])
        moved, paused = goals.stop_watch(self.k, e, reason="user", now=self.now())
        return {"result": "stopped" if moved else "not_active", "watch_id": e["id"], "job_paused": paused}

    def muse_manage_feed_update(self, d, call):
        e = self.entity("feed", d["id"])
        if d["change"] == "delete":
            records.delete_feed(self.k, e, now=self.now())
            return {"result": "deleted", "id": e["id"]}
        if d["change"] == "feedback" and not d.get("feedback"):
            raise bad("data.feedback", "is required for change=feedback")
        return records.mark_feed(self.k, e, d["change"], d.get("feedback"), now=self.now())

    def muse_manage_content_write(self, d, call):
        rel = content_path(d["kind"], d["id"])
        if d["kind"] == "goal_file" and not goals.read(self.k.home, d["id"].partition("/")[0]):
            raise KeyError(f"unknown goal {d['id'].partition('/')[0]!r}")
        raw = d["body"].encode("utf-8")
        with self.lock():
            changed = self.files.replace(rel, raw, d["expected_revision"])
        return {"result": "written" if changed else "unchanged", "path": rel, "revision": revision(raw)}

    # -- muse_manage reads -------------------------------------------------------------------------
    def muse_manage_read(self, d, call):
        kind, limit, query = d["kind"], d.get("limit", 25), (d.get("query") or "").casefold()
        if kind == "status":
            return self.status()
        if kind in CONTENT:
            return self.read_content(kind, d)
        store, offset = self.k.store, d.get("offset", 0)
        if d.get("id"):
            e = self.entity(kind, d["id"])
            out = {**e, "events": store.events(e["id"])[-10:]}
            found = kind == "goal" and goals.read(self.k.home, e["natural_key"])
            if found:
                out.update(record=found[0], **page("body", found[1], offset))
            if kind == "feed":
                out["path"] = records.feed_path(e)
            return out
        rows = [row(e) for e in reversed(store.query(kind))
                if not query or query in json.dumps(e["payload"], ensure_ascii=False).casefold()]
        items, chars = [], 0
        for r in rows[offset:offset + limit]:
            chars += len(json.dumps(r, ensure_ascii=False, default=str))
            if items and chars > READ_MAX:
                break
            items.append(r)
        more = {"next_offset": offset + len(items)} if offset + len(items) < len(rows) else {}
        return {"kind": kind, "items": items, "total": len(rows), **more}

    def entity(self, kind, entity_id):
        e = self.k.store.get(entity_id) or one(self.k.store, kind, entity_id) or self.k.store.get(f"{kind}:{entity_id}")
        if not e or e["kind"] != kind:
            raise KeyError(f"unknown {kind} {entity_id!r}; list them with read(kind={kind})")
        return e

    def read_content(self, kind, d):
        if not d.get("id") and kind in ("note", "dream", "goal_file"):
            base = {"note": "memory", "dream": "dreams", "goal_file": goals.ROOT}[kind]
            return {"kind": kind, "names": self.files.names(base)[-(d.get("limit", 25)):]}
        rel = content_path(kind, d.get("id") or "current")
        try:
            raw = self.files.read(rel)
        except FileNotFoundError:
            return {"kind": kind, "path": rel, "revision": "absent", "body": ""}
        return {"kind": kind, "path": rel, "revision": revision(raw), **page("body", raw.decode("utf-8"), d.get("offset", 0))}

    def status(self):
        open_states = {"goal": ("active", "waiting"), "notice": ("drafted", "scheduled", "sending", "unknown"),
                       "finding": ("open",), "watch": ("active",), "interest": ("active",), "idea": ("active",),
                       "signal": ("new", "parked")}
        counts = {kind: {s: len(self.k.store.query(kind, state=s)) for s in states} for kind, states in open_states.items()}
        return {"health": health.summary(self.k.home), "open": counts}

    def muse_manage_calendar_view(self, d, call):
        from . import calendar
        now = self.k.adapter.now()
        if "window" not in d:
            return {"window": calendar.window(now, d.get("mode", "rolling")),
                    "next": "query every calendar source for this window, then call calendar_view with this window unchanged and sources"}
        if "sources" not in d:
            raise bad("data.sources", "is required with window")
        return calendar.assemble(d, now)

    def muse_manage_installation_prepare(self, d, call):
        jobs = self.k.adapter.cron.jobs()
        return {"operation": d["operation"], "read_only": True,
                "owned_jobs": [{"id": i, "name": j.get("name"), "enabled": j.get("enabled")} for i, j in jobs.items()],
                "steps": ["Confirm with the user in this conversation.",
                          "muse_manage preferences {pause_jobs: true} pauses the jobs above.",
                          f"The user then runs: hermes plugins {d['operation']} hermes-muse. Muse data stays in <home>/muse."]}

    # -- muse_job ----------------------------------------------------------------------------------
    def muse_job_read(self, d, call):
        return self.k.read(d["packet_id"], d["ref"], d.get("offset", 0))

    def muse_job_observe(self, d, call):
        return self.k.observe(d["packet_id"], d["source_id"], d["items"], d.get("limitation_code"), d.get("error"))

    def muse_job_submit(self, d, call):
        return self.k.submit(d["packet_id"], d["results"])


# -- registration and the generated reference --------------------------------------------------------
def register(ctx, kernel):
    """Register muse_manage and muse_job on a Hermes plugin context (called by runtime.register)."""
    surface = Surface(kernel)

    def handler(tool):
        def run(args, **kwargs):
            session_id = kwargs.get("session_id") or ""
            caller = {"kind": kernel.adapter.caller(session_id=session_id, task_id=kwargs.get("task_id") or ""),
                      "session_id": session_id}
            return json.dumps(surface.handle(tool, args, caller), ensure_ascii=False, default=str)
        return run
    for tool in TOOLS:
        ctx.register_tool(name=tool, toolset="muse", schema=tool_schema(tool), handler=handler(tool))
    return surface


def describe(schema):
    kinds = schema.get("type")
    kind = "|".join(kinds) if isinstance(kinds, list) else kinds or "any"
    bits = [" / ".join(schema["enum"])] if "enum" in schema else [kind]
    if "maxLength" in schema:
        bits.append(f"≤{schema['maxLength']} chars")
    if "minimum" in schema:
        bits.append(f"{schema['minimum']}–{schema['maximum']}")
    if schema.get("type") == "array" and "properties" in schema.get("items", {}):
        bits.append("of {" + ", ".join(f + ("*" if f in schema["items"]["required"] else "") for f in schema["items"]["properties"]) + "}")
    return "; ".join(bits) + (f" — {schema['description']}" if schema.get("description") else "")


def fields_table(schema):
    lines = ["| field | | type |", "|---|---|---|"]
    for name, sub in schema["properties"].items():
        lines.append(f"| `{name}` | {'required' if name in schema.get('required', ()) else ''} | {describe(sub).replace('|', '/')} |")
    return lines


def reference():
    """skills/companion/references/interface.md, generated; tests/surface_acceptance.py fails when it is stale."""
    out = ["<!-- Generated by `python -m hermes_muse.surface`; do not edit. -->", "# Muse tool interface", "",
           "Every call is `{action, data}`. Muse fills IDs, keys, next checks and managed revisions; errors name the field.", ""]
    for tool, actions in TOOLS.items():
        out += [f"## `{tool}`", "", DESCRIPTIONS[tool], ""]
        for name, (kind, summary, schema) in actions.items():
            out += [f"### `{name}` ({kind})", "", summary, "", *fields_table(schema), ""]
    out += ["## submit result shapes", "", "One result per packet item. The packet's `schema` names the shapes its items take.", ""]
    for name, schema in packets.SCHEMAS.items():
        out += [f"### {name}", "", *fields_table(schema), ""]
    out += ["## Content kinds", "", "| kind | id |", "|---|---|", *(f"| `{k}` | {v} |" for k, v in CONTENT.items()), ""]
    return "\n".join(out)


if __name__ == "__main__":
    REFERENCE.write_text(reference(), encoding="utf-8")
    print(f"wrote {REFERENCE.relative_to(ROOT)}", file=sys.stderr)
