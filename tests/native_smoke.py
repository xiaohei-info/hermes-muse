"""Real Hermes integration, isolated profiles; no models or live channels used.

Run with a Hermes interpreter: python tests/native_smoke.py
Set HERMES_SOURCE to a public checkout to test that source with the same interpreter.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
if os.environ.get("HERMES_SOURCE"):
    sys.path.insert(0, os.environ["HERMES_SOURCE"])
    os.environ["PYTHONPATH"] = os.environ["HERMES_SOURCE"] + os.pathsep + os.environ.get("PYTHONPATH", "")


def main():
    with tempfile.TemporaryDirectory(prefix="hermes-muse-integration-") as temporary:
        base = Path(temporary)
        homes = [base / "a", base / "b"]
        for home in homes:
            home.mkdir()
            (home / "config.yaml").write_text("plugins:\n  enabled: [hermes-muse]\ntimezone: UTC\n")
            (home / "SOUL.md").write_text("Keep this identity exactly.\n")
            (home / "memories").mkdir()
            for name in ("USER.md", "MEMORY.md"):
                (home / "memories" / name).write_text("Existing private information.\n")
            shutil.copytree(PROJECT, home / "plugins/hermes-muse", ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".hermes-core"))
        # Bind a scratch home before importing any Hermes module.
        os.environ["HERMES_HOME"] = str(homes[0])
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import discover_plugins, get_plugin_manager, render_system_prompt_sections
        from tools.skills_tool import skill_view
        from tools.registry import registry
        from cron.jobs import list_jobs, pause_job, get_job
        from cron.scheduler_script import _run_job_script
        from cron.scheduler_prompt import _parse_wake_gate
        from hermes_muse.host import HermesHost, profile_scope
        from hermes_muse.store import Store
        first_ids = None
        for index in (0, 1, 0):
            home = homes[index]
            token = set_hermes_home_override(home)
            try:
                discover_plugins(force=True)
                manager = get_plugin_manager()
                loaded = manager._plugins.get("hermes-muse")
                assert loaded and loaded.enabled, repr(loaded)
                jobs = list_jobs(include_disabled=True)
                assert len(jobs) == 4, [(j["name"], j["id"]) for j in jobs]
                ids = {j["id"] for j in jobs}
                if index == 0 and first_ids is not None:
                    assert first_ids == ids, "Reload duplicated jobs"
                    assert not get_job(next(iter(first_ids)))["enabled"], "Reload silently resumed a paused job"
                if index == 0 and first_ids is None:
                    first_ids = ids
                    pause_job(next(iter(ids)), reason="user paused")
                prompt = render_system_prompt_sections({"session_id": "integration"})
                rendered = str(prompt)
                assert str(home / "muse") in rendered, rendered
                assert str(homes[1 - index] / "muse") not in rendered
                skill = skill_view("hermes-muse:companion")
                assert "Goal" in str(skill) or "goal" in str(skill), str(skill)
                entry = registry.get_entry("muse_manage")
                assert entry, "Plugin tool absent"
                status = json.loads(entry.handler({"action": "context"}))
                assert status["ok"], status
                assert status["result"]["workspace"] == str(home / "muse")
                ok, gate = _run_job_script("hermes-muse-memory-upkeep.py", workdir=str(home / "muse"))
                assert ok and not _parse_wake_gate(gate), (ok, gate)
                assert (home / "SOUL.md").read_text() == "Keep this identity exactly.\n"
                assert (home / "memories/USER.md").read_text() == "Existing private information.\n"
                assert (home / "memories/MEMORY.md").read_text() == "Existing private information.\n"
                # User edits to workspace templates survive a second initialization.
                prefs = home / "muse/TOOLS.md"
                prefs.write_text("User maintained source list.\n")
                HermesHost(Store(home), plugin_root=home / "plugins/hermes-muse").initialize()
                assert prefs.read_text() == "User maintained source list.\n"
                assert len(list_jobs(include_disabled=True)) == 4
            finally:
                reset_hermes_home_override(token)
        for home in homes:
            with profile_scope(home):
                assert get_plugin_manager().unload("hermes-muse")
                shutil.rmtree(home / "plugins/hermes-muse")
                ok, output = _run_job_script("hermes-muse-memory-upkeep.py", workdir=str(home / "muse"))
                assert ok and not _parse_wake_gate(output), (ok, output)
                assert (home / "muse/install.json").exists()
                # Host remove intentionally leaves native tasks for the documented cleanup flow.
                assert len(list_jobs(include_disabled=True)) == 4
        from native_review_smoke import run as review_checks
        review_checks(base / "review")
        print("PASS: native registration, Skill, prompt, tools, four Cron jobs, real script gates, A->B->A isolation, idempotent reload, preserved native files and harmless removed-plugin launchers")


if __name__ == "__main__":
    main()
