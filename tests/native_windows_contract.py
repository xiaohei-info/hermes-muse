"""Native Windows acceptance: synthetic profile, real host, no model/network or live channels.

Run with HERMES_SOURCE and an isolated TMPDIR. Exercises the maintainer's Windows
checklist, including >10s lock contention, junction refusal and an occupied editor.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.environ.get("HERMES_SOURCE"):
    sys.path.insert(0, os.environ["HERMES_SOURCE"])


def main():
    if os.name != "nt":
        print("SKIP native Windows contract requires Windows")
        return
    from hermes_state import SessionDB
    from hermes_muse.host import HostAdapter, resolve_home
    from hermes_muse.install import install
    from hermes_muse.kernel import Kernel
    from hermes_muse.kernel.goals import read as read_goal
    from hermes_muse.surface import register
    from hermes_muse.locks import file_lock
    from hermes_muse.content_io import Files, DomainError
    import sqlite3

    with tempfile.TemporaryDirectory(prefix="muse Windows café ") as tmp:
        base = Path(tmp).resolve()
        home = base / "profile space café"
        home.mkdir()
        (home / "config.yaml").write_text("timezone: UTC\nplugins:\n  enabled: [hermes-muse]\n", encoding="utf-8")
        os.environ.update(HERMES_HOME=str(home), HERMES_IGNORE_USER_CONFIG="1")
        for name in list(os.environ):
            if name.startswith("HERMES_SESSION_") or name in ("HERMES_CRON_SESSION", "HERMES_PLATFORM"):
                del os.environ[name]
        SessionDB(db_path=home / "state.db").close()
        with closing(sqlite3.connect(home / "state.db")) as db, db:
            for sid, source, chat in (("owner", "photon", "dm"), ("room", "photon", "group"),
                                      ("imported", "import", "dm"), ("machine", "oneshot", "dm")):
                db.execute("INSERT INTO sessions(id,source,chat_type,started_at) VALUES(?,?,?,?)", (sid, source, chat, time.time()))
            for sid, text, kind in (("owner", "Please track the synthetic acceptance task", ""),
                                    ("owner", '[Cronjob "test"] background', ""),
                                    ("owner", "Hidden completion", "hidden"),
                                    ("room", "Another sender's group message", ""),
                                    ("imported", "Imported history", ""), ("machine", "Background task", "")):
                db.execute("INSERT INTO messages(session_id,role,content,timestamp,display_kind,message_uid) VALUES(?, 'user', ?, ?, ?, ?)",
                           (sid, text, time.time(), kind, text))
        adapter = HostAdapter(home)
        assert adapter.caller(session_id="owner") == "user"
        assert adapter.caller(session_id="owner", parent_session_id="parent") == "child"
        assert adapter.caller(session_id="machine", platform="photon") == "other"
        assert adapter.caller(session_id="imported", platform="photon") == "other"
        os.environ["HERMES_SESSION_CHAT_TYPE"] = "group"
        assert adapter.caller(session_id="room") == "group"
        del os.environ["HERMES_SESSION_CHAT_TYPE"]
        turns = adapter.sessions.user_turns(0)
        assert len(turns) == 1 and turns[0]["session_id"] == "owner", turns
        install(adapter, ROOT)
        k = Kernel(home, adapter=adapter)
        registered = []
        register(SimpleNamespace(register_tool=lambda **kw: registered.append(kw)), k)
        handler = next(t["handler"] for t in registered if t["name"] == "muse_manage")

        def call(action, data):
            return json.loads(handler({"action": action, "data": data}, session_id="owner"))

        created = call("goal_create", {"title": "Synthetic Windows acceptance", "criteria": "Exercise and cancel"})
        assert created["ok"], created
        goal_id = created["result"]["goal_id"]
        assert call("goal_update", {"goal_id": goal_id, "progress_note": "Updated on Windows"})["ok"]
        assert read_goal(home, goal_id)[0]["progress"][-1]["note"] == "Updated on Windows"
        note = {"kind": "note", "id": "daily:2026-10-30", "body": "Synthetic note café", "expected_revision": "absent"}
        assert call("content_write", note)["ok"]
        stale = call("content_write", {**note, "body": "Stale replacement"})
        assert stale.get("code") == "revision_conflict", stale
        print("PASS Photon owner handler, signal purity, goal lifecycle and stale content CAS")

        # Real NTFS junction; neither reading nor writing may reach the outside directory.
        outside = base / "outside"
        outside.mkdir()
        (outside / "untouched.md").write_bytes(b"outside")
        files = home / "muse/workspace/goals" / goal_id / "files"
        if files.exists():
            files.rmdir()
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(files), str(outside)], check=True, capture_output=True)
        try:
            rel = f"workspace/goals/{goal_id}/files/untouched.md"
            for operation in (lambda: Files(home).read(rel), lambda: Files(home).replace(rel, b"changed", "absent")):
                try:
                    operation()
                    raise AssertionError("junction access accepted")
                except (PermissionError, DomainError) as exc:
                    assert isinstance(exc, PermissionError) or exc.code == "permission_denied", exc
            assert (outside / "untouched.md").read_bytes() == b"outside" and len(list(outside.iterdir())) == 1
        finally:
            files.rmdir()  # remove the junction only, never its target
        print("PASS junction refuses reads/writes and preserves outside bytes")

        # Open like an editor that does not share deletion; os.replace must fail then recover.
        from ctypes import wintypes
        win = ctypes.WinDLL("kernel32", use_last_error=True)
        win.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        win.CreateFileW.restype = wintypes.HANDLE
        win.CloseHandle.argtypes = [wintypes.HANDLE]
        path = home / "muse/workspace/goals" / goal_id / "GOAL.md"
        before = path.read_bytes()
        handle = win.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
        assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
        try:
            blocked = call("goal_update", {"goal_id": goal_id, "progress_note": "Editor recovery"})
            assert blocked.get("code") == "permission_denied", blocked
            assert path.read_bytes() == before
        finally:
            win.CloseHandle(handle)
        assert call("goal_update", {"goal_id": goal_id, "progress_note": "Editor recovery"})["ok"]
        print("PASS occupied editor reports error, preserves bytes and next update recovers")

        # A separate cron-side process holds the shared locks longer than LK_LOCK's first retry window.
        probe = base / "contend.py"
        probe.write_text("import sys,time\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom hermes_muse.host import HostAdapter\nfrom hermes_muse.kernel.store.bridge import v1_lock\nh=Path(sys.argv[2])\nwith v1_lock(h/'muse'), HostAdapter(h).cron.lock():\n print('locked',flush=True)\n time.sleep(11)\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(probe), str(ROOT), str(home)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout.readline().strip() == "locked"
            start = time.monotonic()
            with file_lock(home / "muse/mutations.lock"), adapter.cron.lock():
                waited = time.monotonic() - start
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0 and waited >= 10, (waited, stdout, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()
        assert call("goal_update", {"goal_id": goal_id, "status": "cancelled"})["ok"]
        assert read_goal(home, goal_id)[0]["status"] == "cancelled"
        print("PASS bridge/user/cron shared locks serialize beyond 10s without EDEADLOCK")

        # Execute every generated owned launcher, with actual host APIs but no scheduler or transport.
        for key in ("memory-upkeep", "proactive-watch", "nightly-review", "feed-pulse", "weekly-governance-review", "health"):
            script = home / "scripts" / f"hermes-muse-{key}.py"
            run = subprocess.run([sys.executable, str(script)], env=os.environ, cwd=base, capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert run.returncode == 0, (key, run.stderr)
        report = json.loads((home / "muse/health.json").read_text(encoding="utf-8"))
        highs = [item["id"] for item in report["invariants"] if item["level"] == "high"]
        assert not highs, highs
        assert resolve_home(home) == home
        print("PASS all six owned launchers, no high health items, standard NTFS spaced/non-ASCII home")
    print("RESULT PASS native_windows_contract")


if __name__ == "__main__":
    main()
