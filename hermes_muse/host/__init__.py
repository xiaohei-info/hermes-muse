"""HostAdapter: the only Muse code that imports Hermes, reads its databases or knows its paths and names.

Every host call is tolerant per call (and per row inside loops): a failure degrades that call to its
empty answer, is logged and kept in `faults` for Health, and never propagates into the kernel.
cwd rule: Muse never uses the process cwd or `terminal.cwd`; every path is absolute from the profile home.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path

PLUGIN = "hermes-muse"
log = logging.getLogger(__name__)


def resolve_home(home=None) -> Path:
    """Absolute profile home. os.fspath rejects a non-path such as an uncalled `Path.home`."""
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    path = Path(os.fspath(home)).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Profile home must be absolute, got {path}")  # resolving would read the process cwd
    return path.resolve()


@contextmanager
def profile_scope(home):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    token = set_hermes_home_override(home)
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def interrupted():
    """True when Hermes asked the current tool call to stop."""
    from tools.interrupt import is_interrupted
    return is_interrupted()


@contextmanager
def exclusive(fd):
    """Block until this process holds the exclusive lock on fd (flock; msvcrt on Windows)."""
    if os.name != "nt":
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
        return
    import errno
    import msvcrt
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            break
        except OSError as exc:
            if exc.errno != errno.EDEADLOCK:  # LK_LOCK gives up after ~10 s; keep waiting like flock
                raise
    try:
        yield
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


HOST_ERROR = "host_error"


def tolerant(default):
    """Turn a raised host error into `default` (called when callable) and a recorded fault.

    A call whose answer leads to a write, a resend or a final state must default to an answer the caller can
    tell from "the host has none" (HOST_ERROR), or raise (Cron.by_script); only reads may degrade to empty.
    """
    def wrap(fn):
        @wraps(fn)
        def call(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except Exception as exc:
                self.adapter.fault(f"{type(self).__name__.lower()}.{fn.__name__}", exc)
                return default() if callable(default) else default
        return call
    return wrap


class Part:
    def __init__(self, adapter):
        self.adapter, self.home = adapter, adapter.home

    def scope(self):
        return profile_scope(self.home)


class Config(Part):
    def raw(self):
        from hermes_cli.config import load_config
        with self.scope():
            return load_config() or {}

    @tolerant(dict)
    def get(self):
        """Muse settings: `plugins.entries.hermes-muse.settings`, then `.config`, over legacy `plugins.hermes-muse`."""
        plugins = self.raw().get("plugins") or {}
        entry = (plugins.get("entries") or {}).get(PLUGIN) or {}
        merged = {}
        for part in (plugins.get(PLUGIN), entry.get("config"), entry.get("settings")):
            if isinstance(part, dict):
                merged.update(part)
        return merged

    @tolerant(False)
    def enabled(self):
        """Host consent; unreadable config counts as disabled so launchers stay harmless."""
        plugins = self.raw().get("plugins") or {}
        return PLUGIN in (plugins.get("enabled") or []) and PLUGIN not in (plugins.get("disabled") or [])


FAILED_DELEGATION = {"error", "failed", "failure", "timeout", "stalled", "unknown", "interrupted", "cancelled"}


class Owners(Part):
    @tolerant(lambda: {"state": HOST_ERROR})
    def status(self, handle):
        """Native async delegation `handle` as running/done/failed/unknown (no record), or host_error when the
        host could not be read; never re-dispatches."""
        from tools.async_delegation import get_durable_delegation
        with self.scope():
            row = get_durable_delegation(str(handle))
        if not row:
            return {"state": "unknown"}
        state = row.get("state")
        mapped = ("running" if state in ("running", "finalizing")
                  else "failed" if state in FAILED_DELEGATION else "done")
        return {"state": mapped, "host_state": state, "completed_at": row.get("completed_at")}


class Memory(Part):
    @tolerant(lambda: {"status": HOST_ERROR})
    def stores(self):
        """Enabled built-in memory stores as {target: {entries, chars, limit}}, read with Hermes' own loader,
        limits and delimiter; status host_error when they could not be read."""
        from tools.memory_tool import ENTRY_DELIMITER, load_on_disk_store
        with self.scope():
            store = load_on_disk_store()
        return {target: {"entries": list(entries), "chars": len(ENTRY_DELIMITER.join(entries)), "limit": limit}
                for target, entries, limit, enabled in (
                    ("memory", store.memory_entries, store.memory_char_limit, store.memory_enabled),
                    ("user", store.user_entries, store.user_char_limit, store.user_profile_enabled)) if enabled}


class HostAdapter:
    def __init__(self, home=None):
        from .cron import Cron, Deliver
        from .sessions import Sessions
        self.home = resolve_home(home)
        self.faults, self.fault_count = deque(maxlen=50), 0
        self.sessions, self.cron, self.deliver = Sessions(self), Cron(self), Deliver(self)
        self.owners, self.config, self.memory = Owners(self), Config(self), Memory(self)

    def cwd(self) -> Path:
        """Host directory for any host API that takes a cwd: `<home>/workspace` when it exists, else `<home>`."""
        workspace = self.home / "workspace"
        return workspace if workspace.is_dir() else self.home

    def now(self) -> datetime:
        """Current time in the profile's timezone (local zone when Hermes cannot tell)."""
        try:
            from hermes_time import now
            with profile_scope(self.home):
                return now()
        except Exception as exc:
            self.fault("adapter.now", exc)
            return datetime.now().astimezone()

    def caller(self, session_id="", **kwargs):
        """user | cron | child | group | other for the current hook or tool call (host kwargs, never tool
        arguments); the one classification hooks and tools share. Unknown fails closed as `other`."""
        from .sessions import caller
        try:
            return caller(stored_source=lambda: self.sessions.user_source_of(session_id),
                          stored_transport=lambda: self.sessions.source_of(session_id), **kwargs)
        except Exception as exc:
            self.fault("adapter.caller", exc)
            return "other"

    def probe(self, **kwargs):
        from .probe import run
        return run(self, **kwargs)

    def fault(self, call, exc):
        self.fault_count += 1
        self.faults.append({"at": time.time(), "call": call, "error": f"{type(exc).__name__}: {exc}"})
        log.warning("Muse host call %s failed: %s", call, exc)
