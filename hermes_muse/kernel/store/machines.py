"""State machines of every Store v2 entity kind: the single table behind create/transition/tick.

`ttl` lists the non-terminal states: state -> (seconds, exit). seconds=None means the caller must
supply the deadline (expires, lease, next_check); exit=None means the deadline only makes the
entity due for its owner (Goals/Health decide, e.g. a run needs the host's execution status).
Any state not in `ttl` is terminal and carries no deadline.
"""
from dataclasses import dataclass

H, D = 3600, 86400
ANY = None


@dataclass(frozen=True)
class Machine:
    initial: str
    ttl: dict
    edges: frozenset
    max_attempts: int | None = None
    # (states, window seconds) an existing natural_key must match for create() to return it.
    dedupe: tuple = (ANY, ANY)

    @property
    def states(self):
        return {self.initial, *self.ttl, *(s for edge in self.edges for s in edge)}

    def terminal(self, state):
        return state not in self.ttl


def edges(spec):
    return frozenset((a, b) for a, targets in spec.items() for b in targets.split())


MACHINES = {
    "signal": Machine("new", {"new": (72 * H, "parked")},
                      edges({"new": "disposed parked", "parked": "disposed"}), max_attempts=3),
    "goal": Machine("active", {"active": (None, None), "waiting": (None, None)},
                    edges({"active": "waiting done cancelled", "waiting": "active done cancelled",
                           "done": "active", "cancelled": "active"})),
    "notice": Machine("drafted", {"drafted": (None, "expired"), "scheduled": (None, "expired"),
                                  "sending": (2 * H, "unknown"), "unknown": (48 * H, "closed_unknown")},
                      edges({"drafted": "scheduled withdrawn expired superseded",
                             "scheduled": "drafted sending withdrawn expired superseded",
                             "sending": "sent failed unknown", "unknown": "sent failed closed_unknown"}),
                      dedupe=(frozenset({"drafted", "scheduled", "sending", "sent"}), 7 * D)),
    "watch": Machine("active", {"active": (None, "expired")}, edges({"active": "stopped expired"})),
    "interest": Machine("active", {"active": (14 * D, "expired")},
                        edges({"active": "expired stopped", "expired": "active", "stopped": "active"})),
    "idea": Machine("active", {"active": (14 * D, "expired")},
                    edges({"active": "expired stopped", "expired": "active", "stopped": "active"})),
    "feed": Machine("published", {}, edges({"published": "deleted"})),
    "source": Machine("ok", {}, edges({s: "ok limited failing unavailable" for s in ("ok", "limited", "failing", "unavailable")})),
    "finding": Machine("open", {"open": (14 * D, "dismissed")}, edges({"open": "resolved dismissed"})),
    "memory_receipt": Machine("pending_notice", {"pending_notice": (24 * H, "noticed")},
                       edges({"pending_notice": "noticed", "noticed": "pending_notice"})),
    "packet": Machine("issued", {"issued": (None, "expired")}, edges({"issued": "submitted expired"})),
    "run": Machine("running", {"running": (2 * H, None)}, edges({"running": "ok degraded failed abandoned"})),
    # One piece of work handed to an executor. `running` is due at min(expected end, last check + 2h) and the patrol or
    # kernel.assignments decides; `stalled` and `lost` wait for the user, whose goal keeps its own fade clock.
    "assignment": Machine("running", {"running": (None, None), "waiting": (3 * D, "stalled")},
                          edges({"running": "waiting done failed stalled stopped lost",
                                 "waiting": "running done failed stalled stopped lost",
                                 "stalled": "running done failed stopped", "lost": "running done failed stopped"})),
    # Forgotten keys: old evidence must not recreate what the user deleted.
    "tombstone": Machine("forgotten", {}, frozenset()),
}


def machine(kind):
    try:
        return MACHINES[kind]
    except KeyError:
        raise ValueError(f"Unknown entity kind {kind!r}") from None
