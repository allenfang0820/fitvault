from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP6AiInsight(unittest.TestCase):
    def _row(self) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(60):
            points.append({
                "lat": 31.0 + i * 0.00008,
                "lon": 121.0,
                "time": (base + timedelta(seconds=i * 20)).isoformat(),
                "hr": 135 + min(i, 35),
                "speed": 3.1,
                "alt": 100.0 + i,
                "cadence": 84,
            })
        return {
            "id": 9,
            "sport_type": "running",
            "dist_km": 6.0,
            "distance": 6000.0,
            "duration_sec": 1200,
            "calories": 900,
            "track_json": json.dumps(points),
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": json.dumps([p["speed"] for p in points]),
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
        }

    def _api(self):
        from main import Api

        api = Api()
        api._fetch_activity_row = MagicMock(return_value=self._row())
        api._fetch_historical_metrics_avg = MagicMock(return_value={
            "sample_size": 0,
            "hr_drift_pct": None,
            "decoupling_pct": None,
            "bonk_count": 0,
        })
        for name, value in {
            "_fetch_efficiency_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_durability_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_cadence_stability_trend": {"level": "flat", "compared_count": 0, "baseline_cv": None},
            "_fetch_training_load_trend": {"level": "flat", "compared_count": 0, "baseline_load": None},
            "_fetch_load_ratio_7d_42d": {
                "ratio": None, "level": "unknown", "acute_7d": None,
                "chronic_42d": None, "compared_count": 0,
            },
        }.items():
            setattr(api, name, MagicMock(return_value=value))
        return api

    def test_extract_activity_id_candidates(self):
        from main import Api

        self.assertEqual(Api._extract_fatigue_review_activity_id({"activity_id": 11}), 11)
        self.assertEqual(Api._extract_fatigue_review_activity_id({"id": 12}), 12)
        self.assertEqual(Api._extract_fatigue_review_activity_id({"activity": {"id": 13}}), 13)
        self.assertEqual(Api._extract_fatigue_review_activity_id({"record": {"id": 14}}), 14)
        self.assertEqual(Api._extract_fatigue_review_activity_id({}), 0)

    def test_insight_snapshot_is_compact_and_forbidden_free(self):
        api = self._api()
        snapshot = api._build_fatigue_review_insight_snapshot(9, "running")
        encoded = json.dumps(snapshot, ensure_ascii=False)

        self.assertIn("curves_summary", snapshot)
        self.assertNotIn("curves", snapshot)
        for key in ("records", "points", "raw_records", "track_points", "shadow_diff", "shadow_diff_json", "diff"):
            self.assertNotIn('"' + key + '"', encoded)
        summary = snapshot["curves_summary"]
        self.assertGreater(summary["distance_points_count"], 0)
        self.assertIn("has_hr", summary)
        self.assertIn("total_distance_m", summary)

    def test_call_llm_empty_without_activity_context_is_enveloped(self):
        api = self._api()
        api._ai_snapshot = None
        api._chat_messages = [{"role": "user", "content": "old"}]
        old_sid = api._session_id

        res = api.call_llm("__FATIGUE_REVIEW_INSIGHT__", "running")

        self.assertEqual(res["code"], 0)
        self.assertEqual(api._chat_messages, [])
        self.assertNotEqual(api._session_id, old_sid)
        insight = res["data"]["fatigue_review_insight"]
        self.assertEqual(insight["error"], "请先加载活动轨迹")

    def test_call_llm_db_not_found_returns_empty_insight(self):
        api = self._api()
        api._ai_snapshot = {"activity_id": 9}
        api._fetch_activity_row = MagicMock(return_value=None)

        res = api.call_llm("__FATIGUE_REVIEW_INSIGHT__", "running")

        self.assertEqual(res["code"], 0)
        self.assertEqual(res["data"]["fatigue_review_insight"]["error"], "未找到该活动记录")

    def test_call_llm_happy_path_uses_compact_snapshot(self):
        api = self._api()
        api._ai_snapshot = {"activity_id": 9}
        captured = {}

        def fake_messages(snapshot, sport_type, sport_cn):
            captured["snapshot"] = snapshot
            captured["sport_type"] = sport_type
            captured["sport_cn"] = sport_cn
            return [{"role": "system", "content": "{}"}, {"role": "user", "content": "go"}]

        with patch("llm_backend.load_llm_config", return_value={
            "url": "http://localhost:1",
            "model": "test",
            "api_key": "",
            "agent_id": "",
        }), patch("llm_backend.build_fatigue_review_messages", side_effect=fake_messages), \
             patch("llm_backend.chat_completions", return_value=json.dumps({
                 "summary": "本次状态稳定",
                 "sport_type": "running",
                 "key_dimensions": [],
                 "event_interpretation": "无明显事件",
                 "training_advice": "保持节奏",
                 "disclaimer": "AI 生成仅供参考",
             })):
            res = api.call_llm("__FATIGUE_REVIEW_INSIGHT__", "running")

        self.assertEqual(res["code"], 0)
        self.assertEqual(res["data"]["fatigue_review_insight"]["summary"], "本次状态稳定")
        self.assertIn("curves_summary", captured["snapshot"])
        self.assertNotIn("curves", captured["snapshot"])
        self.assertEqual(captured["sport_cn"], "跑步")

    def test_call_llm_llm_exception_returns_empty_insight(self):
        api = self._api()
        api._ai_snapshot = {"activity_id": 9}
        with patch("llm_backend.load_llm_config", return_value={
            "url": "http://localhost:1",
            "model": "test",
            "api_key": "",
            "agent_id": "",
        }), patch("llm_backend.chat_completions", side_effect=RuntimeError("gateway timeout")):
            res = api.call_llm("__FATIGUE_REVIEW_INSIGHT__", "running")

        self.assertEqual(res["code"], 0)
        self.assertIn("gateway timeout", res["data"]["fatigue_review_insight"]["error"])

    def test_sentinel_branch_does_not_write_db(self):
        import inspect
        from main import Api

        source = inspect.getsource(Api.call_llm)
        start = source.index("if prompt == self.FATIGUE_REVIEW_INSIGHT")
        end = source.index("cfg = llm_backend.load_llm_config()", start + 1)
        branch = source[start:end]
        for token in ("INSERT", "UPDATE", "ai_snapshots"):
            self.assertNotIn(token, branch)


if __name__ == "__main__":
    unittest.main()
