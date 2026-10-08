import dataclasses
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hermes_muse.research import start, poll
from hermes_muse.store import Store


@dataclasses.dataclass
class Request:
    goal: str
    context: str
    correlation_id: str
    metadata: dict


class Handle:
    def __init__(self, key):
        self.key = key

    def to_dict(self):
        return {"key": self.key}

    @classmethod
    def from_dict(cls, row):
        return cls(row["key"])


class Lifecycle:
    def __init__(self):
        self.requests = []
        self.results = {}
        self.cancelled = []

    def launch(self, request):
        self.requests.append(request)
        handle = Handle(str(len(self.requests)))
        self.results[handle.key] = self.result_of("RUNNING", False)
        return handle

    @staticmethod
    def result_of(state, ready=True):
        return SimpleNamespace(ready=ready, terminal_state=SimpleNamespace(value=state), structured_payload=None,
                               summary="A sourced result", error_message="Failed to retrieve" if state == "FAILED" else None)

    def result(self, handle):
        return self.results[handle.key]

    def cancel(self, handle, reason):
        self.cancelled.append(handle.key)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.lifecycle = Lifecycle()
        self.ctx = SimpleNamespace(subagent_lifecycle=self.lifecycle)
        module = types.ModuleType("agent.subagent_lifecycle")
        module.SubagentHandle, module.SubagentLaunchRequest = Handle, Request
        self.patch = patch.dict(sys.modules, {"agent.subagent_lifecycle": module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_dedup_bounded_waves_and_coverage(self):
        batch = start(self.store, self.ctx, {"items": ["a", "b", "c", "d", "e", "a"]})
        self.assertEqual(batch["total"], 5)
        self.assertEqual(len(self.lifecycle.requests), 3)
        self.assertFalse(batch["complete"])
        for key in ("1", "2", "3"):
            self.lifecycle.results[key] = self.lifecycle.result_of("SUCCEEDED")
        batch = poll(self.store, self.ctx, {"id": batch["id"]})
        self.assertEqual(len(self.lifecycle.requests), 5)
        self.assertEqual(batch["success_count"], 3)
        for key in ("4", "5"):
            self.lifecycle.results[key] = self.lifecycle.result_of("SUCCEEDED")
        batch = poll(self.store, self.ctx, {"id": batch["id"]})
        self.assertTrue(batch["complete"])
        self.assertEqual(batch["success_count"], 5)
        self.assertTrue(all("handle" not in row for row in batch["results"]))

    def test_failed_item_retries_once_unknown_does_not(self):
        batch = start(self.store, self.ctx, {"items": ["a", "b"]})
        self.lifecycle.results["1"] = self.lifecycle.result_of("FAILED")
        self.lifecycle.results["2"] = self.lifecycle.result_of("UNKNOWN", False)
        batch = poll(self.store, self.ctx, {"id": batch["id"]})
        self.assertEqual(len(self.lifecycle.requests), 3)
        self.lifecycle.results["3"] = self.lifecycle.result_of("FAILED")
        batch = poll(self.store, self.ctx, {"id": batch["id"]})
        self.assertTrue(batch["complete"])
        self.assertEqual(batch["failure_count"], 2)
        self.assertEqual(len(self.lifecycle.requests), 3)
        self.assertNotEqual(self.lifecycle.requests[0].correlation_id, self.lifecycle.requests[2].correlation_id)


if __name__ == "__main__":
    unittest.main()
