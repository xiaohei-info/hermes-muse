"""Kernel: one profile's Store v2 and HostAdapter behind the calls the judgment layer and hooks need."""
import logging
import time

from ..host import resolve_home
from . import goals, intake, notifier, packets, runs
from .store import Store

log = logging.getLogger(__name__)


class Kernel:
    def __init__(self, home, *, adapter=None, store=None, clock=time.time):
        # Resolved: content_io walks the path with O_NOFOLLOW, so a symlinked prefix (/var -> /private/var) must go.
        self.home, self.clock = resolve_home(home), clock
        if adapter is None:
            from ..host import HostAdapter
            adapter = HostAdapter(home)
        self.adapter = adapter
        (self.home / "muse").mkdir(parents=True, exist_ok=True)
        self._store = store

    @property
    def store(self):
        """Opened on first use: opening writes (schema check), so plugin registration must not do it."""
        if self._store is None:
            self._store = Store.for_home(self.home, clock=self.clock)
        return self._store

    def tz(self):
        return self.adapter.now().tzinfo

    def settings(self):
        return self.adapter.config.get()

    def _now(self, now):
        return self.clock() if now is None else now

    # -- judgment layer ----------------------------------------------------------------------------
    def build_packet(self, job, now=None):
        """{id, type, items, schema, budget[, context]}; id None means nothing to do (stay silent)."""
        return packets.build(self, job, self._now(now))

    def read(self, packet_id, ref, offset=0, now=None):
        return packets.read(self, packet_id, ref, offset, self._now(now))

    def observe(self, packet_id, source_id, items, limitation_code=None, error=None, now=None):
        return packets.observe(self, packet_id, source_id, items, limitation_code, error, self._now(now))

    def submit(self, packet_id, results, now=None):
        return packets.submit(self, packet_id, results, self._now(now))

    def start_run(self, job, *, job_id, execution_id, packet_id=None, now=None):
        return runs.start(self, job, job_id=job_id, execution_id=execution_id, packet_id=packet_id, now=self._now(now))

    # -- clock ---------------------------------------------------------------------------------------
    def tick(self, now=None):
        """Every due business exit once, in dependency order; idempotent and safe from concurrent processes.

        Receipts are read before store TTLs move `sending` to `unknown`; watches renew before they expire.
        Nothing is sent here: only the muse-deliver run claims and prints notices (entry.deliver).
        One failing step is reported and does not stop the others.
        """
        now = self._now(now)
        report, errors = {}, {}
        moved = []

        def step(name, fn):
            try:
                report[name] = fn()
            except Exception as exc:  # reported for Health; the remaining steps still run
                log.warning("Muse kernel tick step %s failed: %s", name, exc)
                errors[name] = f"{type(exc).__name__}: {exc}"

        step("goals_synced", lambda: goals.sync(self, now))
        step("signals_captured", lambda: intake.capture(self, now))
        step("receipts", lambda: notifier.reconcile(self, now))
        step("watches", lambda: self._watches(goals.watches(self, now)))
        step("expired", lambda: moved.extend(self.store.tick(now)) or len(moved))
        step("watch_jobs_paused", lambda: sum(self._pause(self.store.get(m["id"]), "watch expired")
                                              for m in moved if m["kind"] == "watch"))
        step("fade", lambda: goals.fade(self, now))
        step("runs_closed", lambda: runs.check(self, now))
        return {**report, **({"errors": errors} if errors else {})}

    def _pause(self, watch, reason):
        job_id = watch["payload"].get("job_id")
        return bool(job_id) and bool(self.adapter.cron.pause(job_id, reason))

    def _watches(self, result):
        for watch in result["stopped"]:
            self._pause(watch, "goal closed")
        return {"renewed": result["renewed"], "stopped": len(result["stopped"])}
