"""Profile-local files and transactional operational records (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.17"
PLUGIN = "hermes-muse"
DAY = 86400
GOVERNANCE_JOBS = ("weekly-governance-review", "monthly-system-audit")


def stamp(value=None):
    return datetime.fromtimestamp(time.time() if value is None else value, timezone.utc).isoformat()


def epoch(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.timestamp()


def identifier(value):
    value = str(value)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError("ID must be 1–80 letters, numbers, hyphens or underscores")
    return value


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def bounded(value, limit=8000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Expected nonempty text, at most {limit} characters")
    return value.strip()


def is_background_message(text):
    return isinstance(text, str) and text.lstrip().startswith((
        '[Cronjob "', '[ASYNC DELEGATION ', '[Hermes Muse notification ',
        '[Hermes Muse background evidence]', '[Hermes Muse internal delivery]',
    ))


class Store:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.root = self.home / "muse"
        if self.root.is_symlink():
            raise ValueError("Muse state directory must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (self.root / "state.db").is_symlink():
            raise ValueError("Muse state.db must not be a symlink")
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("State schema is newer than this plugin; upgrade before opening")
            db.execute("PRAGMA user_version=1")
            # Preserve old observations as evidence, outside active user signals/checkpoints.
            for row in self.rows(db, "signal"):
                if is_background_message(row.get("text")):
                    self.put(db, "background_signal", row["id"], row)
                    self.delete(db, "signal", row["id"])
                    session = self.get(db, "session", row.get("session_id"), {})
                    if session.get("turn_id") == row["id"]:
                        session["active"] = False
                        self.put(db, "session", row["session_id"], session)
            for row in self.rows(db, "source_check"):
                if not row.get("source"):
                    self.put(db, "source_check_legacy", row["id"], row)
                    self.delete(db, "source_check", row["id"])
        os.chmod(self.root / "state.db", 0o600)

    def path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()) or path == self.root:
            raise ValueError("Path escapes the Muse workspace")
        return path

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.root / "state.db", timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, kind, key, default=None):
        row = db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(db, kind, key, value):
        db.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    @staticmethod
    def rows(db, kind):
        # ponytail: scan a personal profile's bounded records; add indexed columns if scale warrants.
        return [json.loads(row[0]) for row in db.execute("SELECT data FROM records WHERE kind=? ORDER BY id", (kind,))]

    @staticmethod
    def delete(db, kind, key):
        db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))

    def read(self, kind, key, default=None):
        with self.transaction() as db:
            return self.get(db, kind, key, default)

    def write(self, kind, key, value):
        with self.transaction() as db:
            self.put(db, kind, key, value)

    def all(self, kind):
        with self.transaction() as db:
            return self.rows(db, kind)

    def write_text(self, relative, content, *, create_only=False):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if create_only:
            try:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(content)
                os.chmod(path, 0o600)
            except FileExistsError:
                pass
            return path
        fd, temporary = tempfile.mkstemp(prefix=".muse-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def goal(self, key):
        path = self.path(f"workspace/goals/{identifier(key)}/GOAL.md")
        if not path.exists():
            raise ValueError(f"Unknown goal: {key}")
        text = path.read_text(encoding="utf-8")
        first, _, body = text.partition("\n")
        if not first.startswith("<!-- hermes-muse ") or not first.endswith(" -->"):
            raise ValueError(f"Goal {key} has no valid managed metadata; preserve it and repair explicitly")
        return json.loads(first[len("<!-- hermes-muse "):-len(" -->")]), body

    def goals(self):
        result = []
        for path in sorted(self.path("workspace/goals").glob("*/GOAL.md")):
            record, _ = self.goal(path.parent.name)
            result.append(record)
        return result

    def save_goal(self, record, body):
        key = identifier(record["id"])
        self.write_text(f"workspace/goals/{key}/GOAL.md", "<!-- hermes-muse " + json.dumps(record, ensure_ascii=False, allow_nan=False) + " -->\n" + body)
