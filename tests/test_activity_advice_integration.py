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


if __name__ == "__main__":
    unittest.main()
