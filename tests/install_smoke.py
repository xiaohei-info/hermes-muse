"""Exercise the released repository through the official install/remove commands.

Requires a Hermes interpreter and network access to the public GitHub repository.
Never installs into the user's actual profile.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="muse-official-lifecycle-") as temporary:
        home = Path(temporary)
        (home / "config.yaml").write_text("timezone: UTC\n")
        (home / "SOUL.md").write_text("Preserve this identity.\n")
        env = dict(os.environ, HERMES_HOME=str(home))

        def run(*args):
            completed = subprocess.run([sys.executable, *args], env=env, input="y\n", capture_output=True, text=True, timeout=180)
            if completed.returncode:
                raise AssertionError(completed.stdout + "\n" + completed.stderr)
            return completed.stdout

        run("-m", "hermes_cli.main", "plugins", "install", "xiaohei-info/hermes-muse", "--enable")
        assert (home / "plugins/hermes-muse/plugin.yaml").exists()
        # First real host load; installation alone need not have a live host to initialize.
        run("-c", "from hermes_cli.plugins import discover_plugins; discover_plugins(); from cron.jobs import list_jobs,create_job; assert len(list_jobs(True))==4; create_job(prompt='Unrelated user job',schedule='0 12 * * *',name='keep-me',deliver='local')")
        manifest = json.loads((home / "muse/install.json").read_text())
        assert len(manifest["fixed"]) == 4
        run("-m", "hermes_cli.main", "plugins", "remove", "hermes-muse")
        assert not (home / "plugins/hermes-muse").exists()
        assert (home / "muse/install.json").exists()
        run(str(home / "scripts/hermes-muse-memory-upkeep.py"))
        # Simulate the documented AI cleanup using the recorded ownership, preserving unrelated jobs.
        run("-c", "import json; from pathlib import Path; from hermes_constants import get_hermes_home; from cron.jobs import list_jobs,remove_job; h=get_hermes_home(); m=json.loads((h/'muse/install.json').read_text()); [remove_job(i) for i in m['jobs']]; assert [j['name'] for j in list_jobs(True)]==['keep-me']; [(h/p).unlink(missing_ok=True) for p in m['scripts']]")
        assert (home / "SOUL.md").read_text() == "Preserve this identity.\n"
        print("PASS: official GitHub install -> first host load -> four tasks -> official remove -> owned-only cleanup; identity and unrelated jobs preserved")


if __name__ == "__main__":
    main()
