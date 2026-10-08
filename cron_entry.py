"""Called only by the native per-profile Cron launchers."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hermes_muse.host import cron_run, profile_scope

if __name__ == "__main__":
    with profile_scope(MUSE_HOME):
        result = cron_run(MUSE_HOME, MUSE_JOB)
    print(json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result)
