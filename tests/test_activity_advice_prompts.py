"""活动建议 prompt / payload / normalizer 契约测试。"""
from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import llm_backend  # noqa: E402


class TestActivityAdvicePayload(unittest.TestCase):
    def test_payload_keeps_route_facts_and_planning_context(self):
        raw = llm_backend._activity_advice_payload(
            {
                "activity_id": 7,
                "distance_km": 12.3,
                "elevation_gain_m": 800,
                "start_lat": 31.2,
                "start_lon": 121.4,
                "start_time": "2020-01-01T08:00:00",
                "start_time_utc": "2020-01-01T00:00:00Z",
                "weather_context": {"temperature_c": 20},
                "shadow_diff": {"x": 1},
            },
            {"user_activity_type": "hiking", "planned_start_time": "2026-06-12T08:30"},
        )
        payload = json.loads(raw)

        self.assertEqual(payload["route_facts"]["distance_km"], 12.3)
        self.assertEqual(payload["planning_context"]["user_activity_type"], "hiking")
        self.assertEqual(payload["planning_context"]["planned_start_time"], "2026-06-12T08:30")
        self.assertEqual(payload["planning_context"]["activity_type_source"], "user_input")
        self.assertEqual(payload["planning_context"]["planned_time_source"], "user_input")

        route_facts = payload["route_facts"]
        for forbidden in ("start_time", "start_time_utc", "weather_context", "shadow_diff", "shadow_diff_json", "diff"):
            self.assertNotIn(forbidden, route_facts)

    def test_missing_planned_time_is_explicit(self):
        payload = json.loads(llm_backend._activity_advice_payload({"activity_id": 1}, {}))
        self.assertEqual(payload["planning_context"]["planned_start_time"], "")
        self.assertEqual(payload["planning_context"]["planned_time_source"], "missing")

    def test_temporary_snapshot_source_is_allowed_but_raw_route_context_is_filtered(self):
        raw = llm_backend._activity_advice_payload(
            {
                "distance_km": 19.19,
                "elevation_gain_m": 1118,
                "max_alt_m": 1019,
                "source": "temporary_track_context",
                "points": [{"lat": 40, "lon": 116, "time": "2020-01-01T08:00:00"}],
                "placemarks": [{"name": "cp1"}],
                "weather": {"temperature_c": 20},
                "start_time": "2020-01-01T08:00:00",
            },
            {"planned_start_time": ""},
        )
        payload = json.loads(raw)
        route_facts = payload["route_facts"]

        self.assertEqual(route_facts["source"], "temporary_track_context")
        self.assertEqual(route_facts["distance_km"], 19.19)
        for forbidden in ("points", "placemarks", "weather", "start_time", "time"):
            self.assertNotIn(forbidden, route_facts)
        self.assertEqual(payload["planning_context"]["planned_time_source"], "missing")


class TestActivityAdvicePrompt(unittest.TestCase):
    def test_schema_contains_four_advice_dimensions(self):
        schema = llm_backend.ACTIVITY_ADVICE_OUTPUT_SCHEMA
        for key in ("supply_advice", "weather_check", "equipment_advice", "physical_plan", "disclaimer"):
            self.assertIn(key, schema)

    def test_system_prompt_contains_boundaries(self):
        prompt = llm_backend.build_activity_advice_system_prompt(
            {"activity_id": 1, "distance_km": 10, "start_time": "2020-01-01"},
            {"user_activity_type": "hiking"},
        )

        self.assertIn("DATA BOUNDARY", prompt)
        self.assertIn("planned_start_time", prompt)
        self.assertIn("历史 start_time", prompt)
        self.assertIn("历史天气", prompt)
        self.assertIn("只能给出出发前天气检查清单", prompt)
        self.assertIn("医学诊断", prompt)
        self.assertNotIn("2020-01-01", prompt)

    def test_user_prompt_does_not_inject_facts(self):
        prompt = llm_backend.build_activity_advice_user_prompt()
        self.assertIn("JSON", prompt)
        self.assertNotIn("distance", prompt)
        self.assertNotIn("start_time", prompt)


class TestNormalizeActivityAdviceJson(unittest.TestCase):
    def test_empty_returns_fallback(self):
        out = llm_backend.normalize_activity_advice_json("")
        self.assertEqual(out["weather_check"]["status"], "信息不足")
        self.assertNotEqual(out["error"], "")

    def test_markdown_wrapped_json_stripped(self):
        raw = """```json
{"supply_advice":{"status":"注意","basis":"距离较长","advice":"带足水"}}
```"""
        out = llm_backend.normalize_activity_advice_json(raw)
        self.assertEqual(out["supply_advice"]["status"], "注意")
        self.assertEqual(out["supply_advice"]["basis"], "距离较长")

    def test_invalid_json_returns_error(self):
        out = llm_backend.normalize_activity_advice_json("{not json")
        self.assertNotEqual(out["error"], "")

    def test_non_dict_returns_error(self):
        out = llm_backend.normalize_activity_advice_json("[1,2,3]")
        self.assertNotEqual(out["error"], "")

    def test_invalid_status_falls_back(self):
        out = llm_backend.normalize_activity_advice_json(
            '{"supply_advice":{"status":"高风险","basis":"x","advice":"y"},'
            '"weather_check":{"status":"高风险","basis":"x","advice":"y"}}'
        )
        self.assertEqual(out["supply_advice"]["status"], "提示")
        self.assertEqual(out["weather_check"]["status"], "信息不足")

    def test_missing_dimensions_are_defaulted(self):
        out = llm_backend.normalize_activity_advice_json("{}")
        for key in ("supply_advice", "weather_check", "equipment_advice", "physical_plan"):
            self.assertIn("status", out[key])
            self.assertIn("basis", out[key])
            self.assertIn("advice", out[key])


if __name__ == "__main__":
    unittest.main()
