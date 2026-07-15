from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    if brace < 0:
        raise AssertionError(f"missing JS function body: {name}")
    depth = 0
    for idx in range(brace, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise AssertionError(f"unterminated JS function: {name}")


def _fatigue_review_missing_reason_js(source: str) -> str:
    return (
        _extract_js_function(source, "_fatigueReviewMetricReasonText")
        + "\n" + _extract_js_function(source, "_fatigueReviewEfficiencyBaselineInsufficient")
        + "\n" + _extract_js_function(source, "_fatigueReviewCadencePartialLowConfidence")
        + "\n" + _extract_js_function(source, "_fatigueReviewMetricMissingReason")
    )


class TestFRCore00HistoricalTimeContract(unittest.TestCase):
    def _make_db(self) -> str:
        fd, path = tempfile.mkstemp(prefix="fr_core00_", suffix=".sqlite")
        os.close(fd)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                CREATE TABLE activities (
                    id INTEGER PRIMARY KEY,
                    sport_type TEXT,
                    start_time TEXT,
                    avg_hr REAL,
                    avg_pace REAL,
                    duration_sec INTEGER,
                    deleted_at TEXT
                )
                """
            )
            rows = [
                (10, "running", "2025-01-03T00:00:00+00:00", 150, 300, 3600, None),
                (11, "running", "2025-01-06T00:00:00+00:00", 150, 300, 3600, None),
                (12, "running", "2025-01-10T00:00:00+00:00", 150, 300, 3600, None),
                (20, "running", "2026-07-01T00:00:00+00:00", 100, 200, 3600, None),
                (21, "running", "2026-07-02T00:00:00+00:00", 100, 200, 3600, None),
                (22, "running", "2026-07-03T00:00:00+00:00", 100, 200, 3600, None),
            ]
            conn.executemany(
                "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return path

    def test_efficiency_trend_uses_activity_start_time_not_wall_clock_future_data(self):
        from main import Api

        db_path = self._make_db()
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))

        current_row = {
            "id": 99,
            "sport_type": "running",
            "start_time": "2025-01-15T00:00:00+00:00",
            "avg_hr": 150,
            "avg_pace": 300,
            "duration_sec": 3600,
        }
        expected_prior_ratio = round((1000.0 / 300.0) / 150.0, 6)

        import profile_backend

        with patch.object(profile_backend, "DB_PATH", db_path):
            trend = Api.__new__(Api)._fetch_efficiency_trend(current_row)

        self.assertEqual(trend["compared_count"], 3)
        self.assertEqual(trend["baseline_ratio"], expected_prior_ratio)


class TestFRCore00AvailabilityAndTrendContract(unittest.TestCase):
    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_historical_metrics_avg = MagicMock(
            return_value={
                "sample_size": 3,
                "hr_drift_pct": 8.0,
                "decoupling_pct": 5.0,
                "bonk_count": 0,
            }
        )
        api._fetch_efficiency_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_ratio": None}
        )
        api._fetch_durability_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_ratio": None}
        )
        api._fetch_cadence_stability_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_cv": None}
        )
        api._fetch_load_ratio_7d_42d = MagicMock(
            return_value={
                "ratio": None,
                "level": "unknown",
                "acute_7d": None,
                "chronic_42d": None,
                "compared_count": 0,
            }
        )
        api._fetch_training_load_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_load": None}
        )
        return api

    def _row(self, *, speed_curve: str = "") -> dict:
        base = datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc)
        points = []
        for idx in range(80):
            points.append(
                {
                    "time": (base + timedelta(seconds=idx * 30)).isoformat(),
                    "distance": float(idx * 100),
                    "hr": 140 + idx % 20,
                    "speed": 3.0 + (idx % 5) * 0.02,
                    "cadence": 172 + idx % 4,
                    "alt": 20.0,
                }
            )
        return {
            "id": 99,
            "sport_type": "running",
            "start_time": base.isoformat(),
            "dist_km": 8.0,
            "distance": 8000.0,
            "duration_sec": 80 * 30,
            "calories": 600,
            "track_json": json.dumps(points),
            "points_json": json.dumps(points),
            "merged_track_json": None,
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": speed_curve,
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
            "avg_hr": 150,
            "avg_pace": 300,
        }

    def test_empty_snapshot_unavailable_metrics_use_null_not_zero(self):
        snapshot = self._api()._empty_fatigue_review_snapshot()
        decoupling = snapshot["metrics"]["decoupling"]

        self.assertEqual(decoupling.get("status"), "unavailable")
        self.assertIsNone(decoupling.get("pct"))
        self.assertIsNone(decoupling["trend"].get("delta_pct"))
        self.assertIsNone(decoupling["trend"].get("is_improving"))

    def test_unavailable_current_metric_does_not_generate_strong_historical_trend(self):
        from main import MetricsResolver

        api = self._api()
        resolved = {
            "distance_curve": [float(i * 100) for i in range(80)],
            "time_curve": [float(i * 30) for i in range(80)],
            "altitude_curve": [20.0] * 80,
            "gap_curve": [3.0] * 80,
            "grade_curve": [0.0] * 80,
            "efficiency_curve": [10.0] * 80,
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }
        with patch("main._build_resolved_payload_v81", return_value=resolved), patch.object(
            MetricsResolver,
            "_compute_hr_drift",
            return_value={
                "drift_pct": None,
                "level": "unknown",
                "confidence": "unavailable",
                "reasons": ["insufficient steady aerobic data"],
            },
        ):
            snapshot = api._build_fatigue_review_snapshot(self._row())

        trend = snapshot["metrics"]["hr_drift"]["trend"]
        self.assertIsNone(trend.get("delta_pct"))
        self.assertIsNone(trend.get("is_improving"))
        self.assertIn(trend.get("level"), ("unknown", "unavailable"))

    def test_running_durability_uses_authoritative_snapshot_speed_when_db_curve_is_empty(self):
        from main import MetricsResolver

        api = self._api()
        resolved = {
            "distance_curve": [float(i * 100) for i in range(80)],
            "time_curve": [float(i * 30) for i in range(80)],
            "altitude_curve": [20.0] * 80,
            "speed_curve": [3.0 + (i % 5) * 0.02 for i in range(80)],
            "gap_curve": [3.0] * 80,
            "grade_curve": [0.0] * 80,
            "efficiency_curve": [10.0] * 80,
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }
        with patch("main._build_resolved_payload_v81", return_value=resolved), patch.object(
            MetricsResolver,
            "_compute_durability_index",
            return_value={"score": 95, "level": "excellent", "confidence": "high"},
        ) as durability_mock:
            api._build_fatigue_review_snapshot(self._row(speed_curve=""))

        speed_stream = durability_mock.call_args.kwargs["speed_stream"]
        self.assertGreaterEqual(len(speed_stream), 20)
        self.assertTrue(set(speed_stream).issubset(set(resolved["speed_curve"])))


class TestFRCore00DecouplingDirectionContract(unittest.TestCase):
    def test_late_efficiency_improvement_is_not_classified_as_decline(self):
        from metrics_resolver import MetricsResolver

        result = MetricsResolver._build_review_decoupling([1.0] * 30 + [1.2] * 30)

        self.assertEqual(result.get("direction"), "improved")
        self.assertGreater(result.get("change_pct"), 0)
        self.assertEqual(result.get("decline_pct"), 0)
        self.assertNotIn(result.get("level"), ("warn", "bad"))


class TestFRCore00AiSnapshotGateContract(unittest.TestCase):
    def test_compact_ai_snapshot_does_not_carry_unavailable_strong_trends(self):
        from main import Api

        api = Api()
        api._fetch_activity_row = MagicMock(return_value={"id": 9, "sport_type": "running"})
        api._build_fatigue_review_snapshot = MagicMock(
            return_value={
                "sport_type": "running",
                "metrics": {
                    "hr_drift": {
                        "status": "unavailable",
                        "pct": None,
                        "confidence": "unavailable",
                        "trend": {
                            "delta_pct": -100.0,
                            "level": "down",
                            "is_improving": True,
                            "compared_count": 5,
                        },
                    }
                },
                "summary": {},
                "fatigue_zones": [],
                "collapse_events": [],
                "curves": {},
                "context_tags": {},
                "environment_context": {},
                "cycling_explanation_signals": {},
                "advice": "",
                "disclaimer": "",
            }
        )

        compact = api._build_fatigue_review_insight_snapshot(9, "running")
        trend = compact["metrics"]["hr_drift"].get("trend") or {}

        self.assertIsNone(trend.get("delta_pct"))
        self.assertIsNone(trend.get("is_improving"))
        self.assertIn(trend.get("level"), (None, "unknown", "unavailable"))


class TestFRCore00FrontendCopyContract(unittest.TestCase):
    def test_running_durability_missing_reason_never_mentions_power_curve(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _fatigue_review_missing_reason_js(source)
            + "\nconst result = _fatigueReviewMetricMissingReason('durability', "
            + "{confidence:'unavailable', reasons:['points<20']});\n"
            + "process.stdout.write(result);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertNotIn("功率", result)
        self.assertIn("速度", result)

    def test_cycling_power_retention_missing_reason_keeps_power_copy(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _fatigue_review_missing_reason_js(source)
            + "\nconst result = _fatigueReviewMetricMissingReason('durability', "
            + "{basis:'power_retention', confidence:'unavailable', reasons:['points<20']});\n"
            + "process.stdout.write(result);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertIn("功率", result)
        self.assertNotIn("速度", result)

    def test_low_confidence_cadence_copy_is_not_device_missing(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _fatigue_review_missing_reason_js(source)
            + "\nconst result = _fatigueReviewMetricMissingReason('cadence_stability', "
            + "{status:'partial', confidence:'low', reasons:['intermittent_cadence_pattern']});\n"
            + "process.stdout.write(result);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertIn("节奏变化较大", result)
        self.assertNotIn("设备未记录", result)

    def test_efficiency_missing_baseline_copy_is_not_sensor_missing(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _fatigue_review_missing_reason_js(source)
            + "\nconst result = _fatigueReviewMetricMissingReason('efficiency', "
            + "{score:null, confidence:'low', sample_size:0, reason_code:'insufficient_efficiency_baseline'});\n"
            + "const noBackendReasonResult = _fatigueReviewMetricMissingReason('efficiency', "
            + "{score:null, confidence:'low', sample_size:0});\n"
            + "process.stdout.write(result + '\\n' + noBackendReasonResult);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertIn("历史对照样本不足", result)
        self.assertEqual(result.count("历史对照样本不足"), 1)
        self.assertNotIn("心率数据不足", result)
        self.assertNotIn("配速数据不足", result)

    def test_efficiency_baseline_missing_headline_and_supplement_do_not_claim_current_data_missing(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _extract_js_function(source, "_fatigueReviewMetricReasonText")
            + "\n" + _extract_js_function(source, "_fatigueReviewEfficiencyBaselineInsufficient")
            + "\n" + _extract_js_function(source, "_fatigueReviewCadencePartialLowConfidence")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricSupplementCopy")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricStatusLabel")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricHeadline")
            + "\nconst metric = {score:null, confidence:'low', sample_size:0, reason_code:'insufficient_efficiency_baseline'};\n"
            + "const headline = _fatigueReviewMetricHeadline('efficiency', 'unknown', true, false, null, metric);\n"
            + "const status = _fatigueReviewMetricStatusLabel('efficiency', true, '未知', metric);\n"
            + "const supplement = _fatigueReviewMetricSupplementCopy('efficiency', 'missing', 'running', metric);\n"
            + "process.stdout.write(headline + '\\n' + status + '\\n' + supplement);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertIn("缺少历史对照", result)
        self.assertIn("历史不足", result)
        self.assertIn("缺少足够历史对照", result)
        self.assertNotIn("当前数据不足", result)
        self.assertNotIn("心率数据不足", result)
        self.assertNotIn("配速数据不足", result)

    def test_frontend_efficiency_copy_only_translates_backend_reason_not_sample_size(self):
        source = _read_text(TRACK_HTML)
        helper = _extract_js_function(source, "_fatigueReviewEfficiencyBaselineInsufficient")

        self.assertIn("insufficient_efficiency_baseline", helper)
        self.assertNotIn("sample_size", helper)
        self.assertNotIn("score == null", helper)

    def test_low_confidence_cadence_headline_and_supplement_do_not_claim_device_missing(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for JS semantic execution")

        source = _read_text(TRACK_HTML)
        script = (
            _extract_js_function(source, "_fatigueReviewMetricReasonText")
            + "\n" + _extract_js_function(source, "_fatigueReviewEfficiencyBaselineInsufficient")
            + "\n" + _extract_js_function(source, "_fatigueReviewCadencePartialLowConfidence")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricSupplementCopy")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricStatusLabel")
            + "\n" + _extract_js_function(source, "_fatigueReviewMetricHeadline")
            + "\nconst metric = {status:'partial', confidence:'low', reasons:['intermittent_cadence_pattern']};\n"
            + "const headline = _fatigueReviewMetricHeadline('cadence_stability', 'unknown', true, false, null, metric);\n"
            + "const status = _fatigueReviewMetricStatusLabel('cadence_stability', true, '未知', metric);\n"
            + "const supplement = _fatigueReviewMetricSupplementCopy('cadence_stability', 'missing', 'running', metric);\n"
            + "process.stdout.write(headline + '\\n' + status + '\\n' + supplement);"
        )
        result = subprocess.check_output([node, "-e", script], text=True)

        self.assertIn("不适合评分", result)
        self.assertIn("有步频记录", result)
        self.assertIn("节奏波动过大", result)
        self.assertNotIn("设备没记到", result)
        self.assertNotIn("设备未记录", result)
        self.assertNotIn("步频记录不足", result)


class TestFRCore00ContractDocs(unittest.TestCase):
    def test_hr_source_defaults_unknown_and_does_not_infer_from_device_name(self):
        from main import _resolve_activity_hr_source

        self.assertEqual(_resolve_activity_hr_source({"device_name": "Garmin Fenix 8"}), "unknown")
        self.assertEqual(_resolve_activity_hr_source({"hr_source": "chest_strap"}), "chest_strap")
        self.assertEqual(_resolve_activity_hr_source({"heart_rate_source": "wrist"}), "optical")

    def test_contract_documents_freeze_availability_and_time_semantics(self):
        contract = _read_text(os.path.join(PROJECT_ROOT, "docs", "js_api_contract.json"))
        manual = _read_text(
            os.path.join(PROJECT_ROOT, "docs", "脉图运动复盘系统_开发团队交付手册_v1.md")
        )
        combined = contract + "\n" + manual

        for required in (
            "as_of_time",
            "available / partial / unavailable / not_applicable",
            "current 与 baseline 必须携带相同 basis/version",
            "AI 不接收不可用趋势",
            "跑步耐久使用速度/配速口径",
        ):
            self.assertIn(required, combined)


if __name__ == "__main__":
    unittest.main()
