"""MemoryReceipt: failed or staged results of native memory writes in a private user turn (design 2.2).

Only failed/staged are recorded (saved and unconfirmed stay silent). The next user turn of that session sees
each once; a staged one is shown once more a day later, then left alone. Each says why, and what can be done: a staged
add still applies after a memory cleanup if it fits; a staged patch or remove is pinned by Hermes to the exact entry it
matched, so approval is refused once a cleanup changed that entry.
"""
from .common import D, patch

KIND = "memory_receipt"


def state_of(receipt):
    return receipt.get("state") or receipt.get("classified_state")  # the latter on receipts migrated from 0.3.x


FAILED = {
    "capacity": "the store is full, nothing was saved: {tools}{usage}. Merge or shorten entries in one batch together with the new fact",
    "invalid": "the call's arguments were wrong, nothing was saved: {tools}. Correct them and write it once more",
    "disabled": "this memory store is turned off in the config, nothing was saved: {tools}. Only the user can turn it on",
    "other": "write failed, nothing was saved: {tools}. Say what failed; do not repeat the same write",
}


def record(k, tool_call_id, *, session_id, tool, state, now, **details):
    return k.store.create(KIND, str(tool_call_id), {"session_id": session_id, "tool": tool, "state": state, "at": now, **details}, now=now)


def staged_line(p):
    command = p.get("command")
    review = (f"the user approves with `{command} approve {p.get('pending_id') or '<id>'}` or drops it with "
              f"`{command} reject {p.get('pending_id') or '<id>'}` (`{command} pending` lists them)") if command else "it waits for the user's approval"
    still = ("it is pinned to the exact entry it matched: if a cleanup changed that entry, approval is refused, so reject it and redo the change"
             if p.get("destructive") else "it still applies after a memory cleanup if the store has room when approved")
    return f"write staged, not saved yet ({p.get('tool')}): {review}; {still}. Do not write it again"


def explain(hits):
    """The main-session line for these receipts, one clause per cause."""
    parts = [staged_line(p) for p in hits if state_of(p) == "staged"]
    failed = {}
    for p in hits:
        if state_of(p) == "failed":
            failed.setdefault(p.get("reason") if p.get("reason") in FAILED else "other", []).append(p)
    for reason, group in failed.items():
        usage = next((p["usage"] for p in group if p.get("usage")), "")
        parts.append(FAILED[reason].format(tools=", ".join(sorted({str(p.get("tool")) for p in group})), usage=f" ({usage} chars)" if usage else ""))
    return "[Muse memory receipts] " + "; ".join(parts) + ". Tell the user once if it matters."


def due(k, session_id, now):
    """Payloads to show in this session's next turn; each is marked so it is shown once (staged: once more)."""
    store, hits = k.store, []
    for e in store.query(KIND, state="pending_notice"):
        if e["payload"].get("session_id") == session_id and patch(
                store, e["id"], "noticed", expect=("pending_notice",), reason="injected",
                payload={"noticed_at": now}, now=now):
            hits.append(e["payload"])
    for e in store.query(KIND, state="noticed", since=now - 3 * D):
        p = e["payload"]
        if (p.get("session_id") == session_id and state_of(p) == "staged" and not p.get("reminded")
                and (p.get("noticed_at") or now) <= now - D
                and patch(store, e["id"], expect=("noticed",), reason="staged_reminder",
                          payload={"reminded": True}, now=now)):
            hits.append(p)
    return hits
