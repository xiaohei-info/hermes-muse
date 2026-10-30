"""Cutover and rollback runbook steps for one profile (design 7.4; docs/CUTOVER.md has the order).

  preflight  back up muse/ (SQLite files through the backup API) and print the host probes; nothing else
  apply      run the install that plugin load runs: migration marker, v1 -> v2 migration, job refresh,
             Health cron (for an offline copy, or to repeat a failed load)
  verify     one Health pass, then A4 (probes) and A7 (oldest unhandled signal < 2h)
  rollback   set the marker (v2 jobs go silent), write v2 facts back into the 0.3.x state.db, restore the
             0.3.x job prompts, resume the job Muse paused, pause the Health and deliver crons; then reinstall 0.3.x
Run with the Hermes interpreter: PYTHONPATH=<hermes-agent> python scripts/cutover.py <step> --home <profile home>
"""
import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse import health  # noqa: E402
from hermes_muse.host import HostAdapter  # noqa: E402
from hermes_muse.install import MARKER, PROMPTS_BACKUP, RETIRED, ROLLED_BACK, install, owned  # noqa: E402

DB_FILES = ("*.db", "*.db-wal", "*.db-shm", "*.lock")


def backup(home):
    source, target = home / "muse", home / f"muse-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*DB_FILES))
    for db in source.glob("*.db"):
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as src, \
                closing(sqlite3.connect(target / db.name)) as dst:
            src.backup(dst)
    return str(target)


def preflight(adapter):
    return {"backup": backup(adapter.home), "probes": adapter.probe(),
            "owned_jobs": {i: j.get("name") for i, j in adapter.cron.jobs().items()},
            "reminder": "external callers' rewritten prompts/scripts must be ready (docs/CALLER-MIGRATION.md)"}


def verify(adapter, now=None):
    now = time.time() if now is None else now
    alert = health.run(adapter.home, now=now, adapter=adapter)
    found = {f["id"]: f for f in (health.load(adapter.home) or {}).get("invariants", [])}
    probes = [f for i, f in found.items() if i.startswith("probe.") and f["level"] != "ok"]
    watermark = found.get("signal_watermark", {"level": "high", "detail": "not computed (store unreadable?)"})
    return {"alert": alert,
            "A4_probes": {"pass": not probes, "not_ok": [f"{f['id']}: {f['detail'][:160]}" for f in probes]},
            "A7_signal_watermark": {"pass": watermark["level"] == "ok", "detail": watermark["detail"]}}


def rollback(adapter):
    from hermes_muse.kernel.store.bridge import bridge
    home = adapter.home
    (home / MARKER).write_text(json.dumps({"at": time.time(), "error": "rollback in progress"}), encoding="utf-8")
    out = {"marker": str(home / MARKER), "bridge": bridge(home)}
    try:
        saved = json.loads((home / PROMPTS_BACKUP).read_text(encoding="utf-8"))
    except FileNotFoundError:
        saved = {}
    out["prompts_restored"] = sorted(i for i, j in saved.items() if adapter.cron.set_prompt(i, j["prompt"]))
    out["resumed"] = []
    for key, reason in RETIRED.items():
        job = owned(adapter, key)
        if job and not job.get("enabled") and reason in str(job.get("paused_reason") or ""):
            out["resumed"] += [job["id"]] if adapter.cron.resume(job["id"]) else []
    for key in ("health", "deliver"):  # no-agent jobs: whatever an older cron_entry printed would be delivered
        job = owned(adapter, key)
        out[f"{key}_cron_paused"] = bool(job and adapter.cron.pause(job["id"], ROLLED_BACK))
    out["next"] = ["reinstall the 0.3.x plugin version (catalog 0.3.1 SHA, or the previous local checkout)",
                   "put back the external callers' previous prompts/scripts",
                   f"after the 0.3.x plugin loaded, delete {MARKER}; cancel instead: delete it and reload v2"]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=("preflight", "apply", "verify", "rollback"))
    parser.add_argument("--home", required=True, help="absolute profile home, e.g. ~/.hermes/profiles/<name>")
    args = parser.parse_args()
    adapter = HostAdapter(Path(args.home).expanduser())
    result = {"preflight": preflight, "verify": verify, "rollback": rollback,
              "apply": lambda a: install(a, ROOT)}[args.step](adapter)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if args.step == "verify" and not (result["A4_probes"]["pass"] and result["A7_signal_watermark"]["pass"]) else 0


if __name__ == "__main__":
    sys.exit(main())
