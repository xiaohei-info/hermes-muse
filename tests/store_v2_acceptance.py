"""WP2 acceptance (design 7.3 A1, A2, A3, A5 migration part, A12) on synthetic 0.3.1 / 0.3.16 homes.

A12 judges the bridged v1 db with the real 0.3.x code exported from the git tags.
Usage: python tests/store_v2_acceptance.py   (needs git tags v0.3.1 and v0.3.16)
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse.kernel.store import Store, notice_key  # noqa: E402
from hermes_muse.kernel.store.bridge import bridge  # noqa: E402
from hermes_muse.kernel.store.migrate import copy_home, migrate, signal_revision  # noqa: E402

NOW = 1_800_000_000.0
H, D = 3600, 86400
FAILED = []


def check(name, ok, detail):
    print(f"{name} {'PASS' if ok else 'FAIL'} {json.dumps(detail, ensure_ascii=False, sort_keys=True)}")
    if not ok:
        FAILED.append(name)


def sample(home, shape):
    """Synthetic profile reproducing the audited failure patterns (no real data)."""
    muse = home / "muse"
    (muse / "workspace" / "goals").mkdir(parents=True)
    rows = []

    def rec(kind, key, data):
        rows.append((kind, key, data))

    def signal(key, created, text="note", processed=False, **extra):
        row = {"id": key, "session_id": "s1", "text": text, "created": created, "truncated": False, **extra}
        if processed and shape == "0.3.16":
            row["upkeep"] = {"at": created + 60, "revision": signal_revision(row)}
        rec("signal", key, row)

    signal("s1:t1", NOW - 5 * D, processed=True)
    signal("s1:t2", NOW - 4.6 * D, processed=True)
    signal("s1:long", NOW - 4.5 * D, "pasted data " * 600, truncated=True)  # the stuck long paste
    signal("s1:t3", NOW - 4 * D, processed=True)
    signal("s1:t4", NOW - 3 * D, processed=True)
    signal("s1:t5", NOW - H)
    signal("s1:bg", NOW - 2 * D, '[Cronjob "x"] output')
    rec("cursor", "memory-upkeep", NOW - 4.6 * D)
    rec("cursor", "proactive-watch", NOW - H)

    def notice(key, status, created, item=None, sources=("ref:none",), title="Alert", **extra):
        row = {"id": key, "event_key": "ev-" + key, "issue_key": "issue-" + key, "message": f"{title}: details",
               "rationale": "why", "sources": list(sources), "verified_at": created, "expires": NOW + 3 * D,
               "created": created, "priority": "ordinary", "topic": "", "goal_id": None, "interest_id": None,
               "final_result": False, "status": status, "not_before": created, "session_id": None, "job_id": None, **extra}
        if item:
            row["source_snapshot"] = {"item_id": item, "title": title, "checked_at": created}
        if status in {"sent", "dispatching", "transport_queued", "unknown"}:
            row["dispatched_at"] = created + 60
        rec("notification", key, row)

    # Vendor security alert: sent 4x, one more pending.
    for i, status in enumerate(["sent", "sent", "sent", "sent", "pending"]):
        notice(f"vend{i}", status, NOW - (5 - i) * D, sources=["gmail:message:MSGAAA"] if i % 2 else ["mail:<msgaaa>"],
               item="msgaaa" if i < 3 else None, title="Vendor security alert")
    # New device login: 7 notices on one thread.
    for i, status in enumerate(["sent", "sent", "pending", "pending", "candidate", "cancelled", "cancelled"]):
        notice(f"dev{i}", status, NOW - (2 - i * 0.2) * D, item="thr-bbb", title="New device login")
    # Domain expiry: two unsent duplicates, nothing sent yet.
    notice("dom0", "candidate", NOW - 2 * H, sources=["gmail:message:ccc"], title="Domain expires")
    notice("dom1", "pending", NOW - H, sources=["gmail:message:CCC"], title="Domain expires")
    notice("weak0", "candidate", NOW - H, title="Weekly summary")
    notice("old-q", "transport_queued", NOW - 10 * D, sources=["https://example.com/a?utm_source=x"])
    notice("old-u", "unknown", NOW - 9 * D, sources=["https://example.com/b"])
    notice("sup0", "cancelled", NOW - 3 * D, superseded_by="dom0", title="Domain old")

    rec("interest", "topic-a", {"id": "topic-a", "kind": "interest", "title": "Topic A", "status": "active", "expires": NOW + 5 * D})
    rec("interest", "idea-b", {"id": "idea-b", "kind": "idea", "title": "Idea B", "status": "candidate", "expires": NOW + 9 * D})
    rec("interest", "topic-c", {"id": "topic-c", "kind": "interest", "title": "Topic C", "status": "cancelled", "expires": NOW - D})
    for i in range(2):
        rec("feed", f"feed{i}", {"id": f"feed{i}", "title": f"Feed {i}", "path": f"workspace/your_files/feed/feed{i}.md",
                                 "created": NOW - i * D, "position": NOW - i * D, "sources": [f"https://example.org/{i}"], "feedback": None})
    rec("source_check", "src-mail", {"id": "src-mail", "status": "checked", "last_success": NOW - 2 * H, "finished_at": NOW - 2 * H,
                                     "source": {"connection": "mail", "account": "a", "resource": "inbox"}, "_revision": 3})
    rec("source_check", "src-cal", {"id": "src-cal", "status": "partial", "finished_at": NOW - H,
                                    "source": {"connection": "cal", "account": "a", "resource": "main"}, "_revision": 1})
    for key, state, created in [("mf1", "failed", NOW - H), ("mf2", "staged", NOW - 5 * D), ("mf3", "saved", NOW - H),
                                ("mf4", "submitted_unconfirmed", NOW - 2 * D)]:
        rec("memory_feedback", key, {"id": key, "session_id": "s1", "turn_id": "s1:t5", "tool_call_id": "call-" + key, "tool": "memory",
                                     "classified_state": state, "invalidated": False, "created": created, "decision": "defer", "reply_ref": None})
    rec("operation_finding", "f-open", {"id": "f-open", "status": "open", "summary": "s", "impact": "i", "evidence": ["e"], "updated": NOW - 30 * D})
    rec("operation_finding", "f-done", {"id": "f-done", "status": "resolved", "summary": "s", "impact": "i", "evidence": ["e"], "updated": NOW - D})
    rec("forgotten", "notification:gone", NOW - 7 * D)
    rec("run", "exec-1", {"id": "exec-1", "status": "running", "started": NOW - 20 * D})
    rec("session", "s1", {"id": "s1", "active": True})
    rec("review_window", "w1", {"refs": []})
    rec("budget", "2027-01-15:ordinary", 1)
    if shape == "0.3.16":
        rec("mutation_request", "m1", {"action": "delegate", "status": "pending"})

    with closing(sqlite3.connect(muse / "state.db")) as db, db:
        db.execute("CREATE TABLE records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
        db.execute("PRAGMA user_version=1")
        db.executemany("INSERT INTO records VALUES(?,?,?)", [(k, i, json.dumps(d)) for k, i, d in rows])
    for slug, header in [("g-active", {"status": "active", "next_check_at": NOW - D}),
                         ("g-wait", {"status": "active", "waiting_user": True, "next_check_at": NOW + D}),
                         ("g-done", {"status": "done"})]:
        (muse / "workspace" / "goals" / slug).mkdir()
        (muse / "workspace" / "goals" / slug / "GOAL.md").write_text(
            "<!-- hermes-muse " + json.dumps({"id": slug, "title": slug, "session_id": "s1", **header}) + " -->\n# " + slug + "\n")
    (muse / "workspace" / "goals" / "g-raw").mkdir()
    (muse / "workspace" / "goals" / "g-raw" / "GOAL.md").write_text("# hand-written goal\n")
    (muse / "install.json").write_text(json.dumps({"jobs": {
        "j-fixed": {"key": "proactive-watch"},
        "j-w1": {"key": "watch-aaa", "owner": "g-active", "stop_condition": "done"},
        "j-w2": {"key": "watch-bbb", "owner": "g-done", "expires": NOW + D}}}))
    return rows


def dump(home):
    with closing(sqlite3.connect(home / "muse" / "state-v2.db")) as db, db:
        return [list(db.execute(f"SELECT * FROM {t} ORDER BY 1,2")) for t in ("entity", "event", "meta")]


def tree_hash(home):
    return hashlib.sha256(b"".join(p.relative_to(home).as_posix().encode() + p.read_bytes()
                                   for p in sorted(home.rglob("*")) if p.is_file())).hexdigest()


def simulate_v2(home):
    """Some v2 activity before rollback: ttl tick, a dispatch, new signals and notices."""
    store = Store.for_home(home, clock=lambda: NOW + H)
    store.tick()
    for n in store.query("notice", state=("drafted", "scheduled")):
        if n["natural_key"].startswith("src:"):
            n = store.transition(n["id"], "scheduled", state=n["state"], version=n["version"], reason="t") if n["state"] == "drafted" else n
            n = store.transition(n["id"], "sending", state="scheduled", version=n["version"], reason="dispatch")
            store.transition(n["id"], "sent", state="sending", version=n["version"], reason="receipt")
    for key in ("signal:s1:long", "signal:s1:t4"):  # t4 lies behind the still-new t3 under 0.3.1
        signal = store.get(key)
        if signal["state"] == "new":
            store.transition(key, "disposed", state="new", version=signal["version"], reason="intake", payload={"disposition": "ignored"})
    store.create("signal", "s1:t9", {"session_id": "s1", "created": NOW + 30, "excerpt": "later", "pointer": {"session_id": "s1", "turn_id": "s1:t9"}},
                 state="disposed", now=NOW + 30)
    store.create("signal", "s1:t10", {"session_id": "s1", "created": NOW + 40, "excerpt": "unhandled", "pointer": {"session_id": "s1", "turn_id": "s1:t10"}},
                 now=NOW + 40)
    key, _ = notice_key("v2-item-1")
    store.create("notice", key, {"message": "New v2 alert", "sources": ["mail:<v2-item-1>"]}, state="sent")
    store.create("source", "src-mail-new", {"last_success": NOW}, dedupe=False)
    mail = store.query("source", natural_key="src-mail")[0]
    store.transition(mail["id"], "ok", state="ok", version=mail["version"], reason="observe", payload={"last_success": NOW + H})
    return {n["natural_key"] for n in store.query("notice", state="sent")}, \
        {n["payload"]["pointer"]["turn_id"] for n in store.query("signal", state=("disposed", "parked"))}


OLD_PROBE = r"""
import json, sys
if sys.platform == "win32":
    # Historical tags have only POSIX locking. Supply the current stdlib platform
    # seam for this synthetic fixture; run their real Store and checkpoint logic.
    import importlib.util, os, types
    from contextlib import contextmanager
    spec = importlib.util.spec_from_file_location("fixture_host", sys.argv[5] + "/hermes_muse/host/__init__.py")
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    @contextmanager
    def file_lock(path):
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with host.exclusive(fd):
                yield
        finally:
            os.close(fd)
    locks = types.ModuleType("hermes_muse.locks")
    locks.file_lock = file_lock
    sys.modules[locks.__name__] = locks
sys.path.insert(0, sys.argv[1])
from hermes_muse.store import Store
store = Store(sys.argv[2])
if sys.argv[3] == "0.3.16":
    from hermes_muse.context_pages import pending_signals
    pending = [r["id"] for r in pending_signals(store)]
else:
    from hermes_muse.context_pages import signal_refs
    pending = [r["id"] for r in signal_refs(store, store.read("cursor", "memory-upkeep", 0), float(sys.argv[4]))]
print(json.dumps({"pending": pending, "notices": store.all("notification")}))
"""


def old_view(home, shape, scratch):
    code = scratch / f"v{shape}"
    if not code.exists():
        code.mkdir()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", f"v{shape}", "hermes_muse"], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(code)], input=archive, check=True)
    out = subprocess.run([sys.executable, "-I", "-c", OLD_PROBE, str(code), str(home), shape, str(NOW + 2 * H), str(ROOT)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def run(shape, scratch):
    print(f"--- shape {shape}")
    base = scratch / f"base-{shape}"
    rows = sample(base, shape)
    a, b = scratch / f"a-{shape}", scratch / f"b-{shape}"
    copy_home(base, a)
    copy_home(base, b)

    before = tree_hash(a)
    dry = migrate(a, dry_run=True, now=NOW)
    check("dry-run", tree_hash(a) == before and not (a / "muse" / "state-v2.db").exists(), {"home_unchanged": tree_hash(a) == before})

    report = migrate(a, now=NOW)
    first = dump(a)
    again = migrate(a, now=NOW + D)
    migrate(b, now=NOW)
    check("A1", dump(a) == first == dump(b) and again.get("reason") == "already_migrated" and dry["entities"] == report["entities"],
          {"rerun": again.get("reason"), "copies_equal": dump(a) == dump(b), "dry_equals_real": dry["entities"] == report["entities"]})

    r = report["reconcile"]
    merged = sum(report["notice_merged"].values())
    check("A2", report["unexplained"] == 0 and report["goal_files"] == 3 and r["signal_disposed_v2"] == r["signal_processed_v1_shape"]
          and r["notice_live_v2"] == r["notice_live_v1"] - merged,
          {"from_shape": report["from_shape"], "v1_records": len(rows), "unexplained": report["unexplained"], "reconcile": r,
           "notice_merged": report["notice_merged"], "skipped": report["skipped"]})

    with closing(sqlite3.connect(a / "muse" / "state-v2.db")) as db, db:
        entities = list(db.execute("SELECT kind, state, deadline FROM entity"))
    from hermes_muse.kernel.store import machine
    missing = [(k, s) for k, s, d in entities if not machine(k).terminal(s) and d is None]
    check("A3", not missing, {"nonterminal": sum(not machine(k).terminal(s) for k, s, _ in entities), "without_deadline": len(missing)})

    store = Store.for_home(a)
    live = {}
    for n in store.query("notice", state=("drafted", "scheduled")):
        live.setdefault(n["natural_key"], []).append(n["payload"]["v1_id"])
    sent7 = {n["natural_key"] for n in store.query("notice", state="sent", since=NOW - 7 * D)}
    check("A5-migration", all(len(v) == 1 for v in live.values()) and not (set(live) & sent7),
          {"live_by_key": {k[:20]: v for k, v in sorted(live.items())}, "live_already_sent": sorted(set(live) & sent7)})

    sent_keys, settled = simulate_v2(a)
    report_bridge = bridge(a, now=NOW + 2 * H)
    second = bridge(a, now=NOW + 2 * H)
    view = old_view(a, shape, scratch)
    dup_signals = sorted(set(view["pending"]) & settled)
    sendable = [n for n in view["notices"] if n["status"] in {"candidate", "pending", "queued", "dispatching"}]
    dup_notices = [n["id"] for n in sendable
                   if notice_key((n.get("source_snapshot") or {}).get("item_id"), n.get("sources") or [])[0] in sent_keys]
    v1_sent_keys = {notice_key((n.get("source_snapshot") or {}).get("item_id"), n.get("sources") or [])[0]
                    for n in view["notices"] if n["status"] == "sent"}
    check("A12", not dup_signals and not dup_notices and sent_keys <= v1_sent_keys and second["bridged"] == {}
          and "s1:t10" in view["pending"],
          {"old_version": shape, "bridged": report_bridge["bridged"], "rerun_changes": second["bridged"],
           "old_pending_signals": view["pending"], "duplicate_signal_processing": len(dup_signals),
           "duplicate_notices": len(dup_notices), "v2_unhandled_signal_back_in_v1": "s1:t10" in view["pending"], "v2_sent_visible_in_v1": sorted(sent_keys - v1_sent_keys) == []})


def main():
    with tempfile.TemporaryDirectory(prefix="muse-wp2-") as scratch:
        for shape in ("0.3.1", "0.3.16"):
            run(shape, Path(scratch))
    print("RESULT", "FAIL " + ",".join(FAILED) if FAILED else "PASS")
    raise SystemExit(bool(FAILED))


if __name__ == "__main__":
    main()
