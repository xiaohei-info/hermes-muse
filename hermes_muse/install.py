"""Install / upgrade (design 7.4 step 2), under muse/install.lock. `upgrade` runs it on plugin load only when
muse/installed.json says this code has not finished installing here, so an ordinary load never opens the window
below. A process killed inside the window leaves a marker `migrating` reads as stale: the next load, or the next
launcher (silent jobs load nothing, so a load may never come), installs again. `migrating` alone decides.

1. Write the migration marker muse/migrating.json: every Muse cron launcher and the background tick stay
   silent while it exists (a failed install leaves it, with the error, and the main session is told).
2. Migrate 0.3.1/0.3.16 muse/state.db into muse/state-v2.db once (idempotent; v1 stays read-only).
3. Create missing content files from templates (never overwrite) and the content folders.
4. Refresh the Muse cron jobs in place. Keys keep their 0.3.x names, so job ids, user schedules, routes
   and pauses survive and external callers keep their job references; each gets `prompts/jobs/<job>.md`
   and runs cron_entry.py. The monthly audit is paused (merged into the weekly digest). Watch jobs get
   the current watch prompt (ensure_watch is also how muse_manage watch_create makes them). The no-agent
   `deliver` job has no prompt; the finished 0.4.1 one-shot delivery jobs whose notice settled are removed.
5. Create or refresh the Health no_agent cron and resume the jobs a cancelled rollback paused (user pauses stay).
6. Record what was installed in muse/installed.json and remove the marker.
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from . import health
from .content_io import Files
from .host import PLUGIN
from .kernel import Kernel, notifier
from .kernel.common import preferences
from .kernel.store import Store
from .locks import file_lock, lock_free

log = logging.getLogger(__name__)
MARKER = "muse/migrating.json"
LOCK = "muse/install.lock"
INSTALLED = "muse/installed.json"  # fingerprint of the last finished install
INSTALLS_FROM = ("hermes_muse/**/*.py", "prompts/**/*.md", "templates/**/*.md", "cron_entry.py", "health_entry.py", "plugin.yaml")
PROMPTS_BACKUP = "muse/backup/cron-prompts-0.3.json"
# cron key (0.3.x name) -> (job, default schedule for a new install, delivers to the user); prompt prompts/jobs/<job>.md
JOBS = {
    "memory-upkeep": ("intake", "0 * * * *", False),
    "proactive-watch": ("patrol", "*/30 * * * *", True),
    "nightly-review": ("nightly", "20 3 * * *", False),
    "feed-pulse": ("feed", "0 8 * * *", False),
    "weekly-governance-review": ("weekly", "15 21 * * 0", True),
    "deliver": ("deliver", "*/10 * * * *", True),
}
NO_AGENT = {"deliver"}  # jobs whose stdout is the delivery itself: no prompt, no model
RETIRED = {"monthly-system-audit": "merged into the weekly digest"}
ROLLED_BACK = "rolled back to 0.3.x"  # pause reason of scripts/cutover.py rollback; a reinstall undoes only that pause
SKILLS = [f"{PLUGIN}:companion"]
WATCH_PROMPT = """You run one Hermes Muse watch for the user's goal (its state is in Script Output).
Check: {check}
Stop condition: {stop}
Use only read-only tools. If the stop condition is met, or something the user must act on changed, answer in one or two
short sentences in the user's language with the evidence link. Otherwise answer exactly [SILENT]."""
FOLDERS = ("memory/people", "memory/groups", "dreams/alignment/derived", "workspace/goals", "workspace/your_files/feed")


def migrating(home):
    """The marker's content while an install is running, failed or was killed (`stale` set), else None.

    Without an error, install.lock tells a running install from a dead one: the marker is removed under the lock,
    so a marker still there once the lock is seen free has no process left to finish it."""
    path = Path(home) / MARKER
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        mark = json.loads(raw)
    except ValueError:  # a kill can truncate the write
        mark = {"at": 0}
    if mark.get("error") or not lock_free(Path(home) / LOCK):
        return mark
    return {**mark, "stale": True} if path.exists() else None


def route(adapter):
    """The profile's main delivery route: preference, plugin setting, then the profile's Bot Chat."""
    try:
        deliver = preferences(adapter.home).get("deliver")
    except ValueError:
        deliver = None
    return deliver or adapter.config.get().get("deliver") or "bot-chat"


def templates(home, root):
    files, created = Files(home), []
    for path in sorted((root / "templates").rglob("*.md")):
        relative = path.relative_to(root / "templates").as_posix()
        try:
            files.read(relative)
            continue
        except FileNotFoundError:
            pass
        body = path.read_text(encoding="utf-8").replace("{{MUSE_HOME}}", str(home / "muse")).replace("{{HERMES_HOME}}", str(home))
        files.replace(relative, body.encode(), "absent")
        created.append(relative)
    for folder in FOLDERS:
        (home / "muse" / folder).mkdir(parents=True, exist_ok=True)
    return created


def owned(adapter, key):
    return adapter.cron.job(key)


def backup_prompts(adapter):
    """Keep the 0.3.x prompts of owned jobs once, before the first refresh: they carry the 0.3.x
    installation markers, so a rollback that restores them is not answered with a duplicate job set."""
    path = adapter.home / PROMPTS_BACKUP
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    jobs = {i: {"name": j.get("name"), "prompt": j.get("prompt"), "enabled": j.get("enabled")}
            for i, j in adapter.cron.owned_jobs().items()}
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    path.chmod(0o600)
    return True


def watch_check(prompt):
    """What a watch checks, from its current prompt: v2 (`Check: …`) or 0.3.x (after the generated instructions)."""
    prompt = str(prompt or "")
    head, found, _ = prompt.rpartition("\nStop condition: ")
    if not found:
        return None
    for marker in ("\nCheck: ", "With nothing approved return [SILENT].\n"):
        if marker in head:
            return head.rpartition(marker)[2].strip() or None
    return None


def ensure_watch(adapter, root, key, *, schedule, check, stop_condition, deliver=None):
    """Create or refresh the owned job of one watch; a refresh keeps its schedule, route and pause."""
    prompt = WATCH_PROMPT.format(check=check.strip(), stop=str(stop_condition or "").strip())
    return adapter.cron.ensure(key, schedule=schedule, entry=Path(root) / "cron_entry.py", prompt=prompt,
                               skills=SKILLS, deliver=deliver or route(adapter))


def job_prompt(root, job):
    return (root / "prompts" / "jobs" / f"{job}.md").read_text(encoding="utf-8")


def jobs(adapter, root, store):
    entry, out = root / "cron_entry.py", {}
    for key, (job, schedule, delivered) in JOBS.items():
        quiet = job in NO_AGENT
        found = adapter.cron.ensure(key, schedule=schedule, entry=entry, skills=None if quiet else SKILLS, no_agent=quiet,
                                    prompt=None if quiet else job_prompt(root, job),
                                    deliver=route(adapter) if delivered else "local")
        out[key] = found["id"] if found else None
    for key, reason in RETIRED.items():
        job = owned(adapter, key)
        out[key] = "paused" if job and adapter.cron.pause(job["id"], reason) else None
    by_id = adapter.cron.jobs()
    for w in store.query("watch", state="active"):
        job = by_id.get(w["payload"].get("job_id"))
        check = job and (w["payload"].get("check") or watch_check(job.get("prompt")))
        if check:  # shortcut: a watch whose prompt Muse cannot parse keeps it; the user recreates it
            key = job["script"][len("hermes-muse-"):-3]
            out[key] = (ensure_watch(adapter, root, key, schedule=job.get("schedule"), check=check,
                                     stop_condition=w["payload"].get("stop_condition")) or {}).get("id")
    return out


def install(adapter, root, now=None):
    """Idempotent; returns what it did. Raises after leaving the marker (with the error) on failure."""
    from .kernel.store.migrate import migrate
    home, root = adapter.home, Path(root).resolve()
    now = time.time() if now is None else now
    marker = home / MARKER
    with file_lock(home / LOCK):
        mark = {"at": now, "pid": os.getpid()}
        marker.write_text(json.dumps(mark), encoding="utf-8")
        try:
            report = {"migration": migrate(home, now=now) if (home / "muse" / "state.db").is_file() else None}
            store = Store.for_home(home)
            report["templates"] = templates(home, root)
            report["prompts_backed_up"] = backup_prompts(adapter)
            report["jobs"] = jobs(adapter, root, store)
            report["one_shots_removed"] = notifier.sweep(Kernel(home, adapter=adapter, store=store))
            report["health_cron"] = (health.ensure_cron(adapter, route(adapter)) or {}).get("id")
            report["resumed"] = sorted(i for i, j in adapter.cron.jobs().items() if not j.get("enabled")
                                       and ROLLED_BACK in str(j.get("paused_reason") or "") and adapter.cron.resume(i))
            (home / INSTALLED).write_text(json.dumps({"fingerprint": fingerprint(home, root), "at": now}), encoding="utf-8")
        except Exception as exc:
            marker.write_text(json.dumps({**mark, "error": f"{type(exc).__name__}: {exc}"[:500]}), encoding="utf-8")
            raise
        marker.unlink()
    return report


def fingerprint(home, root):
    """This code in this home: another version, checkout or copied profile installs again."""
    digest = hashlib.sha256(f"{home}\n{root}".encode())
    for path in sorted(p for pattern in INSTALLS_FROM for p in root.glob(pattern)):
        digest.update(path.relative_to(root).as_posix().encode() + b"\n" + path.read_bytes())
    return digest.hexdigest()


def current(adapter, root):
    """Whether an install has nothing to do: this code finished here, none is unfinished since, and what it
    creates is still as it left it (a removed job or template comes back, an older version's prompt is replaced)."""
    home = adapter.home
    try:
        done = json.loads((home / INSTALLED).read_text(encoding="utf-8")).get("fingerprint")
    except (OSError, ValueError):
        return False
    if (home / MARKER).exists() or done != fingerprint(home, root):
        return False
    if not all((home / "muse" / p.relative_to(root / "templates")).exists() for p in (root / "templates").rglob("*.md")):
        return False
    for key, (job, _, _) in JOBS.items():
        found = owned(adapter, key)
        if not found or (job not in NO_AGENT and found.get("prompt") != job_prompt(root, job)):
            return False
    return bool(owned(adapter, "health"))


def upgrade(adapter, root):
    """Install when there is something to do, one process at a time; a process that waited finds it done. Returns
    the install's report, or None when it did not run or failed (the marker then holds the error: jobs stay silent
    and the main session is told; the next load retries)."""
    root = Path(root).resolve()
    try:
        if current(adapter, root):
            return None
        with file_lock(adapter.home / LOCK):
            return None if current(adapter, root) else install(adapter, root)
    except Exception as exc:
        log.error("Hermes Muse install failed: %s", exc)
        return None
