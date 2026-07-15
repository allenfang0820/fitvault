from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TRACK_HTML = os.path.join(PROJECT_ROOT, "track.html")


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_js_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing JS function: {name}")
    brace = source.find("{", start)
    depth = 0
    for idx in range(brace, len(source)):
        if source[idx] == "{":
            depth += 1
        elif source[idx] == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise AssertionError(f"unterminated JS function: {name}")


class TestFRCore06SportCapabilityRegistry(unittest.TestCase):
    def test_registry_matrix_covers_review_modes_and_special_sports(self):
        from metrics_registry import get_review_capabilities, get_review_mode, normalize_review_sport_type

        cases = {
            "indoor_cycling": "cycling",
            "e_biking": "cycling",
            "treadmill_running": "running",
            "lap_swimming": "swimming",
            "open_water": "swimming",
            "walking": "general",
            "hiking": "general",
            "strength_training": "not_applicable",
            "breathing": "not_applicable",
            "stair_climbing": "not_applicable",
            "cardio": "not_applicable",
            "stand_up_paddleboarding": "general",
            "9999": "not_applicable",
        }
        for sport, expected_mode in cases.items():
            with self.subTest(sport=sport):
                normalized = normalize_review_sport_type(sport)
                self.assertEqual(get_review_mode(normalized), expected_mode)
                caps = get_review_capabilities(normalized)
                self.assertEqual(caps["review_mode"], expected_mode)
                self.assertEqual(caps["is_applicable"], expected_mode != "not_applicable")

    def test_backend_snapshot_exports_review_mode_and_capabilities(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="indoor_cycling")

        self.assertEqual(snapshot["sport_type"], "indoor_cycling")
        self.assertEqual(snapshot["review_mode"], "cycling")
        self.assertTrue(snapshot["capabilities"]["uses_cycling_power"])
        self.assertFalse(snapshot["capabilities"]["uses_running_durability"])

    def test_ai_prompt_uses_backend_review_mode(self):
        import llm_backend

        messages = llm_backend.build_fatigue_review_messages(
            {
                "sport_type": "indoor_cycling",
                "review_mode": "cycling",
                "metrics": {},
                "summary": {},
            },
            "indoor_cycling",
            "室内骑行",
        )
        body = "\n".join(message.get("content", "") for message in messages)

        self.assertIn('"review_mode": "cycling"', body)
        self.assertIn("cycling 模式", body)

    def test_frontend_sport_mode_consumes_backend_review_mode(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        fn = _extract_js_function(source, "_fatigueReviewMetricSportMode")
        script = (
            fn
            + "\nconst out = ["
            + "_fatigueReviewMetricSportMode('indoor_cycling', 'cycling'),"
            + "_fatigueReviewMetricSportMode('strength_training', 'not_applicable'),"
            + "_fatigueReviewMetricSportMode('treadmill_running', 'running')"
            + "].join('|'); process.stdout.write(out);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertEqual(result, "cycling|not_applicable|running")


if __name__ == "__main__":
    unittest.main()
