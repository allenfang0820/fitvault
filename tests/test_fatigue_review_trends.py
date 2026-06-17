"""
V7.6 复盘覆盖层 trend 字段契约测试

契约依据:
- §2.1 全链路可追溯:trend 来源 = activities 表历史均值
- §三 响应结构:trend 作为 metrics 子字段,不扩展 7 段白名单
- §6 shadow_diff 隔离
- §8 canonical 只读
"""
from __future__ import annotations

import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestTrendStructure:
    """trend 必须是 metrics 子字段,不扩展顶级白名单。"""

    def test_trend_under_metrics(self):
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 5000,
            "calories": 800,
            "storage_model": "{}",
            "hr_curve": "[142, 148, 155]",
            "speed_curve": "[3.1, 3.2, 3.0]",
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        metrics = snapshot["metrics"]
        assert "trend" in metrics["hr_drift"]
        assert "trend" in metrics["decoupling"]
        assert "trend" in metrics["bonk_risk"]
        assert "events" in metrics
        assert "trend" in metrics["events"]

    def test_trend_segment_whitelist_unchanged(self):
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 1000,
            "calories": 0,
            "storage_model": "{}",
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        whitelist = [
            "sport_type", "metrics", "collapse_events", "curves",
            "context_tags", "environment_context", "ai_insight", "advice", "disclaimer",
        ]
        for seg in whitelist:
            assert seg in snapshot
        assert "trends" not in snapshot


class TestTrendDegradation:
    """数据不足时 trend 降级。"""

    def test_no_history_returns_unknown_shape(self):
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 1000,
            "calories": 0,
            "storage_model": "{}",
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        hr_trend = snapshot["metrics"]["hr_drift"]["trend"]
        assert "delta_pct" in hr_trend
        assert "level" in hr_trend
        assert "compared_count" in hr_trend
        assert hr_trend.get("source") == "historical_avg"

    def test_bonk_and_events_trend_shape(self):
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 1000,
            "calories": 0,
            "storage_model": "{}",
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        assert "level" in snapshot["metrics"]["bonk_risk"]["trend"]
        assert "delta_count" in snapshot["metrics"]["events"]["trend"]
        assert snapshot["metrics"]["events"]["trend"].get("source") == "historical_avg"


class TestTrendShadowDiffIsolation:
    """trend 字段严禁泄漏 shadow_diff 等 debug 字段。"""

    def test_trend_does_not_carry_shadow_diff(self):
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 5000,
            "calories": 800,
            "storage_model": json.dumps({
                "_fr_snapshot_metrics": {"decoupling_pct": 6.0},
                "shadow_diff": "leak",
                "shadow_diff_json": "leak",
            }),
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        for f in ["shadow_diff", "shadow_diff_json", "diff", "records"]:
            assert f not in snapshot
            assert f not in json.dumps(snapshot, ensure_ascii=False)


class TestHistoricalTrendQuery:
    """历史均值查询必须只读并返回固定形状。"""

    def test_historical_avg_shape(self):
        from main import Api
        api = Api()
        result = api._fetch_historical_metrics_avg("running", 0, 5)
        for key in ["hr_drift_pct", "decoupling_pct", "bonk_count", "sample_size"]:
            assert key in result


class TestFrontendTrendContract:
    """前端契约文本存在性:trend-trend class 和历史文案必须存在。"""

    def test_frontend_trend_markup_exists(self):
        track_path = os.path.join(_PROJECT_ROOT, "track.html")
        with open(track_path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "trend-trend" in html
        assert "较近" in html
        assert "数据不足（需 ≥3 次历史）" in html
        assert "fr-events-count" in html
