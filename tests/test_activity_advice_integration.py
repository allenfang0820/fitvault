"""活动建议 Api.call_llm 集成契约测试。"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from main import Api  # noqa: E402


def _sample_points(distance_lon_delta=0.01, with_alt=True):
    first = {"lat": 40.0, "lon": 116.0}
    second = {"lat": 40.0, "lon": 116.0 + distance_lon_delta}
    third = {"lat": 40.0, "lon": 116.0 + distance_lon_delta * 2}
    if with_alt:
        first["alt"] = 100
        second["alt"] = 160
        third["alt"] = 120
    return [first, second, third]


class TestActivityAdviceIntegration(unittest.TestCase):
    def setUp(self):
        self.api = Api()
        self.api._ai_snapshot = {
            "activity_id": 1,
            "distance_km": 12.0,
            "elevation_gain_m": 600,
            "start_time": "2020-01-01T08:00:00",
            "start_time_utc": "2020-01-01T00:00:00Z",
        }
        self.api._activity_advice_snapshot = {
            "activity_id": 1,
            "distance_km": 12.0,
            "elevation_gain_m": 600,
            "source": "DB Canonical / Resolver Truth",
        }
        self.api._track_weather = {"temperature_c": 20}
        self.api._track_filename = "route.fit"

    def test_happy_path_returns_activity_advice_and_uses_new_session(self):
        old_sid = self.api._session_id
        self.api._chat_messages = [{"role": "user", "content": "stale"}]
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return json.dumps({
                "supply_advice": {"status": "提示", "basis": "距离 12km", "advice": "带水"},
                "weather_check": {"status": "信息不足", "basis": "缺少计划时间", "advice": "出发前查天气"},
            }, ensure_ascii=False)

        context = json.dumps({"user_activity_type": "hiking", "planned_start_time": "2026-06-12T08:30"})
        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m", "api_key": "", "agent_id": ""}):
            with patch("llm_backend.chat_completions", side_effect=fake_chat):
                res = self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, context)

        self.assertTrue(res["ok"])
        self.assertIn("activity_advice", res)
        self.assertNotIn("risk_assessment", res)
        self.assertEqual(self.api._chat_messages, [])
        self.assertNotEqual(self.api._session_id, old_sid)
        self.assertEqual(captured["session_id"], self.api._session_id)
        encoded_messages = json.dumps(captured["messages"], ensure_ascii=False)
        self.assertIn("2026-06-12T08:30", encoded_messages)
        self.assertNotIn("2020-01-01", encoded_messages)
        self.assertNotIn("temperature_c", encoded_messages)

    def test_empty_without_snapshot_clears_session(self):
        old_sid = self.api._session_id
        self.api._ai_snapshot = None
        self.api._activity_advice_snapshot = None
        self.api._chat_messages = [{"role": "user", "content": "stale"}]

        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            res = self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "{}")

        self.assertTrue(res["ok"])
        self.assertIn("activity_advice", res)
        self.assertNotEqual(res["activity_advice"]["error"], "")
        self.assertEqual(self.api._chat_messages, [])
        self.assertNotEqual(self.api._session_id, old_sid)

    def test_missing_llm_config_still_clears_session(self):
        old_sid = self.api._session_id
        self.api._chat_messages = [{"role": "user", "content": "stale"}]

        with patch("llm_backend.load_llm_config", return_value={"url": "", "model": "m"}):
            res = self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "{}")

        self.assertTrue(res["ok"])
        self.assertIn("activity_advice", res)
        self.assertIn("API 接口地址未配置", res["activity_advice"]["error"])
        self.assertEqual(self.api._chat_messages, [])
        self.assertNotEqual(self.api._session_id, old_sid)

    def test_llm_exception_returns_empty_activity_advice(self):
        self.api._chat_messages = [{"role": "user", "content": "stale"}]

        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            with patch("llm_backend.chat_completions", side_effect=Exception("gateway timeout")):
                res = self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "{}")

        self.assertTrue(res["ok"])
        self.assertIn("activity_advice", res)
        self.assertIn("LLM 调用失败", res["activity_advice"]["error"])
        self.assertEqual(self.api._chat_messages, [])

    def test_invalid_context_is_treated_as_activity_type_only(self):
        captured = {}

        def fake_messages(snapshot, planning_context):
            captured["planning_context"] = planning_context
            return [{"role": "system", "content": "{}"}, {"role": "user", "content": "go"}]

        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            with patch("main._build_activity_advice_messages", side_effect=fake_messages):
                with patch("llm_backend.chat_completions", return_value="{}"):
                    self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "hiking")

        self.assertEqual(captured["planning_context"]["user_activity_type"], "hiking")
        self.assertEqual(captured["planning_context"]["planned_start_time"], "")
        self.assertEqual(captured["planning_context"]["planned_time_source"], "missing")

    def test_messages_builder_does_not_accept_weather_argument(self):
        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            with patch("main._build_activity_advice_messages", return_value=[{"role": "user", "content": "go"}]) as builder:
                with patch("llm_backend.chat_completions", return_value="{}"):
                    self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "{}")

        args, _kwargs = builder.call_args
        self.assertEqual(len(args), 2)

    def test_sync_db_activity_builds_whitelisted_activity_advice_snapshot(self):
        db_snapshot = {
            "activity_id": 9,
            "distance_km": 21.1,
            "elevation_gain_m": 900,
            "max_alt_m": 1019,
            "start_time": "2020-01-01T08:00:00",
            "weather_json": {"temperature_c": 20},
            "hr_curve": [1, 2, 3],
        }

        with patch("main._build_ai_snapshot", return_value=db_snapshot):
            res = self.api.sync_track_context(json.dumps({
                "activityId": 9,
                "points": [],
                "placemarks": [{"name": "cp1"}],
                "weather": {"temperature_c": 20},
                "filename": "route.fit",
            }))

        self.assertTrue(res["ok"])
        snapshot = self.api._activity_advice_snapshot
        self.assertEqual(snapshot["activity_id"], 9)
        self.assertEqual(snapshot["distance_km"], 21.1)
        self.assertEqual(snapshot["elevation_gain_m"], 900)
        for forbidden in ("points", "placemarks", "weather", "weather_json", "start_time", "time", "hr_curve"):
            self.assertNotIn(forbidden, snapshot)

    def test_sync_track_context_prefers_overview_route_facts_for_activity_advice(self):
        db_snapshot = {
            "activity_id": 9,
            "distance_km": 18.82,
            "elevation_gain_m": 1349,
            "max_alt_m": 4241,
        }

        with patch("main._build_ai_snapshot", return_value=db_snapshot):
            res = self.api.sync_track_context(json.dumps({
                "activityId": 9,
                "points": _sample_points(),
                "filename": "route.fit",
                "activityAdviceRouteFacts": {
                    "activity_id": 9,
                    "distance_km": 17.24,
                    "distance_display": "17.24km",
                    "elevation_gain_m": 1152,
                    "max_alt_m": 4241,
                    "source": "overview_canonical_metrics",
                },
            }))

        self.assertTrue(res["ok"])
        snapshot = self.api._activity_advice_snapshot
        self.assertEqual(self.api._ai_snapshot["distance_km"], 18.82)
        self.assertEqual(snapshot["distance_km"], 17.24)
        self.assertEqual(snapshot["distance_display"], "17.24km")
        self.assertEqual(snapshot["elevation_gain_m"], 1152)
        self.assertEqual(snapshot["max_alt_m"], 4241)
        self.assertEqual(snapshot["source"], "overview_canonical_metrics")

    def test_activity_advice_overview_route_facts_are_whitelisted(self):
        res = self.api.sync_track_context(json.dumps({
            "points": _sample_points(),
            "filename": "route.gpx",
            "activityAdviceRouteFacts": {
                "distance_km": 8.34,
                "elevation_gain_m": 896,
                "max_alt_m": 5337,
                "points": [{"lat": 1, "lon": 2}],
                "placemarks": [{"name": "cp"}],
                "weather_json": {"rain": True},
                "start_time": "2020-01-01T08:00:00",
                "diff": {"distance_km": 10},
            },
        }))

        self.assertTrue(res["ok"])
        snapshot = self.api._activity_advice_snapshot
        self.assertEqual(snapshot["distance_km"], 8.34)
        self.assertEqual(snapshot["elevation_gain_m"], 896)
        self.assertEqual(snapshot["max_alt_m"], 5337)
        for forbidden in ("points", "placemarks", "weather_json", "start_time", "diff"):
            self.assertNotIn(forbidden, snapshot)

    def test_temporary_track_context_builds_route_facts_for_activity_advice(self):
        captured = {}

        def fake_messages(snapshot, planning_context):
            captured["snapshot"] = snapshot
            captured["planning_context"] = planning_context
            return [{"role": "system", "content": "{}"}, {"role": "user", "content": "go"}]

        self.api.sync_track_context(json.dumps({
            "points": _sample_points(),
            "placemarks": [{"name": "cp1"}],
            "weather": {"temperature_c": 20},
            "filename": "route.gpx",
        }))

        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            with patch("main._build_activity_advice_messages", side_effect=fake_messages):
                with patch("llm_backend.chat_completions", return_value="{}") as chat:
                    res = self.api.call_llm(self.api.REPORT_ACTIVITY_ADVICE, "{}")

        self.assertTrue(res["ok"])
        chat.assert_called_once()
        snapshot = captured["snapshot"]
        self.assertGreater(snapshot["distance_km"], 0)
        self.assertEqual(snapshot["elevation_gain_m"], 60)
        self.assertEqual(snapshot["total_descent_m"], 40)
        self.assertEqual(snapshot["max_alt_m"], 160)
        self.assertEqual(snapshot["source"], "temporary_track_context")
        for forbidden in ("points", "placemarks", "weather", "start_time", "time", "timestamp"):
            self.assertNotIn(forbidden, snapshot)

    def test_empty_without_track_context_returns_load_track_message(self):
        api = Api()

        with patch("llm_backend.load_llm_config", return_value={"url": "http://llm", "model": "m"}):
            res = api.call_llm(api.REPORT_ACTIVITY_ADVICE, "{}")

        self.assertTrue(res["ok"])
        self.assertIn("请先加载活动轨迹", res["activity_advice"]["error"])

    def test_sync_track_context_overwrites_activity_advice_snapshot(self):
        self.api.sync_track_context(json.dumps({
            "points": _sample_points(distance_lon_delta=0.01, with_alt=True),
            "filename": "first.gpx",
        }))
        first_snapshot = dict(self.api._activity_advice_snapshot)

        self.api.sync_track_context(json.dumps({
            "points": _sample_points(distance_lon_delta=0.02, with_alt=False),
            "filename": "second.gpx",
        }))
        second_snapshot = self.api._activity_advice_snapshot

        self.assertNotEqual(first_snapshot["distance_km"], second_snapshot["distance_km"])
        self.assertNotIn("elevation_gain_m", second_snapshot)
        self.assertEqual(second_snapshot["source"], "temporary_track_context")


if __name__ == "__main__":
    unittest.main()
