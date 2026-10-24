"""Tests for contextual weather read recipes and proactivity correlation."""
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import unittest

from hermes_muse.service import Companion
from hermes_muse.views import validate_tools_note
from test_companion import prepare, Host

ROOT = Path(__file__).resolve().parents[1]


class WeatherProactivityTests(unittest.TestCase):
    def test_tools_note_weather_recipe_validates(self):
        tools_text = (ROOT / "templates/TOOLS.md").read_text(encoding="utf-8")
        # Ensure validation passes (no forbidden credentials or private connection URLs)
        validate_tools_note(tools_text)
        self.assertIn("Weather Forecast (Contextual & Extended)", tools_text)
        self.assertIn("Open-Meteo", tools_text)
        self.assertIn("proactive-watch", tools_text)

    def test_proactivity_reference_contains_weather_decision_triggers(self):
        proactivity_text = (ROOT / "skills/companion/references/proactivity.md").read_text(encoding="utf-8")
        self.assertIn("precipitation probability >= 70%", proactivity_text)
        self.assertIn(">= 5°C drop or rise", proactivity_text)
        self.assertIn("forecast:daily", proactivity_text)
        self.assertIn("practical preparation advice", proactivity_text)

    def test_weather_source_check_lifecycle(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = prepare(temp.name)
        host = Host()
        now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc).timestamp()
        companion = Companion(store, host, lambda: now)

        data = {
            "source": {"connection": "weather", "account": "open-meteo", "resource": "forecast:daily"},
            "scope": "Next 5 days rolling forecast for local context",
            "status": "checked",
            "expected_resources": ["forecast:daily"],
            "checked_resources": ["forecast:daily"],
            "summary": "5-day forecast evaluated: 100% rain on Sunday, 8°C temperature drop on Monday",
            "started_at": now - 10,
            "request_id": "weather-patrol-check-001",
            "expected_revision": "absent",
        }
        record = companion.source_check(data)
        self.assertEqual(record["status"], "checked")
        self.assertEqual(record["source"]["connection"], "weather")
        self.assertEqual(record["source"]["account"], "open-meteo")
        self.assertEqual(record["source"]["resource"], "forecast:daily")

        # Verify listing through context
        context = companion.context()
        source_checks = context.get("source_checks", [])
        self.assertTrue(any(s["id"] == record["id"] for s in source_checks))
