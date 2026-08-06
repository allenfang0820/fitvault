from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestCyclingNoObservedSpeedReview(unittest.TestCase):
    """Generic no-speed FIT-equivalent cycling review regression tests.

    The fixture intentionally does not mention any device brand. It represents
    a valid cycling activity that has distance/time/power/hr/cadence facts but
    no observed speed/enhanced_speed field.
    """

    def _row_without_observed_speed(self, points_count: int = 3600) -> dict:
        start = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)
        points: list[dict] = []
        for idx in range(points_count):
            distance = idx * 7.0
            points.append({
                "time": (start + timedelta(seconds=idx)).isoformat().replace("+00:00", "Z"),
                "distance": distance,
                "hr": 128 + (idx % 18),
                "alt": 120.0 + (idx % 8) * 0.2,
                "power": 0 if idx % 24 == 0 else 185 + (idx % 35),
                "cadence": 0 if idx % 30 == 0 else 82 + (idx % 6),
            })
        return {
            "track_json": json.dumps(points),
            "points_json": json.dumps(points),
            "dist_km": ((points_count - 1) * 7.0) / 1000.0,
            "duration_sec": points_count - 1,
            "sport_type": "cycling",
            "avg_hr": 136,
            "avg_power": 198,
            "max_power": 260,
            "normalized_power": 210,
            "avg_cadence": 84,
        }

    def _build_review_parts(self) -> tuple[dict, dict, dict, dict]:
        import main

        row = self._row_without_observed_speed()
        bundle = main._build_fatigue_review_curve_bundle(row)
        curves = main._build_fatigue_review_curves_snapshot(bundle, {})
        summary = main._build_fatigue_review_summary(row, bundle, curves)
        metrics = main._build_cycling_review_metrics(
            "cycling",
            summary,
            curves,
            avg_hr=row.get("avg_hr"),
        )
        return row, bundle, curves, summary | {"_metrics": metrics}

    def _row_without_speed_axis(self) -> dict:
        start = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)
        points = []
        for idx in range(80):
            points.append({
                "time": (start + timedelta(seconds=idx)).isoformat().replace("+00:00", "Z"),
                "hr": 135,
                "power": 190,
                "cadence": 84,
            })
        return {
            "track_json": json.dumps(points),
            "dist_km": 0.0,
            "duration_sec": 80,
            "sport_type": "cycling",
        }

    def _evidence_by_type(self, signal: dict, evidence_type: str) -> dict:
        for item in signal.get("evidence") or []:
            if isinstance(item, dict) and item.get("type") == evidence_type:
                return item
        self.fail(f"missing evidence item: {evidence_type}")

    def test_no_observed_speed_is_not_zero_filled_as_authoritative_speed(self):
        _, bundle, curves, summary_with_metrics = self._build_review_parts()
        summary = {key: value for key, value in summary_with_metrics.items() if key != "_metrics"}

        self.assertNotIn("speed", json.loads(self._row_without_observed_speed()["track_json"])[0])
        self.assertEqual(bundle["speed_observed_points_count"], 0)
        self.assertGreater(summary["speed_derived_points_count"], 0)
        self.assertEqual(summary["speed_source"], "derived_distance_time")
        self.assertEqual(summary["speed_data_quality"], "derived")
        self.assertTrue(any((isinstance(value, (int, float)) and value > 0) for value in curves["speed"]))
        self.assertFalse(all(value == 0 for value in curves["speed"]))

    def test_missing_observed_speed_does_not_clear_effective_cycling_signals(self):
        import main

        _, _, curves, summary_with_metrics = self._build_review_parts()
        metrics = summary_with_metrics.pop("_metrics")
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary_with_metrics,
            curves,
            profile_ftp_watts=213,
            metrics=metrics,
        )

        retention = self._evidence_by_type(
            signals["power_retention_signal"],
            "effective_pedaling_power_retention",
        )
        cadence = self._evidence_by_type(
            signals["cadence_signal"],
            "cycling_cadence_rhythm",
        )
        aerobic = self._evidence_by_type(
            signals["aerobic_drift_signal"],
            "cycling_aerobic_drift",
        )

        self.assertGreater(retention["effective_power_points_count"], 0)
        self.assertGreater(cadence["effective_cadence_points_count"], 0)
        self.assertGreater(aerobic["effective_points_count"], 0)
        self.assertNotIn("stopped", retention.get("filter_reasons") or [])
        self.assertNotIn("stopped", cadence.get("filter_reasons") or [])
        self.assertNotIn("stopped", aerobic.get("filter_reasons") or [])

    def test_unresolvable_speed_is_missing_not_observed_stop(self):
        import main

        row = self._row_without_speed_axis()
        bundle = main._build_fatigue_review_curve_bundle(row)
        curves = main._build_fatigue_review_curves_snapshot(bundle, {})
        summary = main._build_fatigue_review_summary(row, bundle, curves)

        self.assertEqual(summary["speed_source"], "missing")
        self.assertEqual(summary["speed_data_quality"], "missing")
        self.assertEqual(summary["speed_observed_points_count"], 0)
        self.assertEqual(summary["speed_derived_points_count"], 0)
        self.assertGreater(summary["speed_missing_points_count"], 0)
        self.assertEqual(curves["speed"], [])

    def test_hr_drift_marks_speed_missing_when_speed_cannot_be_resolved(self):
        import main

        row = self._row_without_speed_axis()
        row["duration_sec"] = 3600
        snapshot = main.Api()._build_fatigue_review_snapshot(row)

        self.assertEqual(snapshot["metrics"]["hr_drift"]["confidence"], "unavailable")
        self.assertIn("speed_missing", snapshot["metrics"]["hr_drift"]["reasons"])

    def test_grade_curve_clamps_near_zero_distance_deltas(self):
        from gap_calculator import GapCalculator

        grade = GapCalculator._calculate_grade_pct(
            distance_series=[0.0, 0.0, 0.1, 0.1, 0.2, 1.0],
            smoothed_alt_series=[100.0, 110.0, 120.0, 121.0, 121.5, 122.0],
        )

        self.assertEqual(len(grade), 6)
        self.assertTrue(all(isinstance(value, float) for value in grade))
        self.assertTrue(all(abs(value) < 500 for value in grade))
        self.assertTrue(all(value == value for value in grade))  # no NaN

    def test_observed_zero_speed_remains_observed_zero(self):
        import main

        row = self._row_without_speed_axis()
        points = json.loads(row["track_json"])
        for idx, point in enumerate(points):
            point["speed"] = 0.0
            point["distance"] = idx * 0.0
        row["track_json"] = json.dumps(points)
        row["dist_km"] = 0.0

        bundle = main._build_fatigue_review_curve_bundle(row)
        summary = main._build_fatigue_review_summary(
            row,
            bundle,
            main._build_fatigue_review_curves_snapshot(bundle, {}),
        )

        self.assertEqual(summary["speed_source"], "observed")
        self.assertEqual(summary["speed_data_quality"], "available")
        self.assertEqual(summary["speed_observed_points_count"], len(points))
        self.assertEqual(summary["speed_derived_points_count"], 0)

    def test_explicit_missing_speed_is_not_used_as_stop_filter(self):
        import main

        axis_len = 120
        curves = {
            "distance": [idx * 0.01 for idx in range(axis_len)],
            "time": list(range(axis_len)),
            "power": [190] * axis_len,
            "hr": [138] * axis_len,
            "cadence": [84] * axis_len,
            "speed": [0.0] * axis_len,
        }
        summary = {
            "avg_power": 190,
            "duration_sec": 3600,
            "power_available": True,
            "cadence_available": True,
            "power_points_count": axis_len,
            "cadence_points_count": axis_len,
            "power_data_quality": "available",
            "cadence_data_quality": "available",
            "speed_source": "missing",
            "speed_data_quality": "missing",
        }
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary,
            curves,
            profile_ftp_watts=213,
            metrics=main._build_cycling_review_metrics("cycling", summary, curves, avg_hr=138),
        )

        for signal_key, evidence_type, count_key in (
            ("power_retention_signal", "effective_pedaling_power_retention", "effective_power_points_count"),
            ("cadence_signal", "cycling_cadence_rhythm", "effective_cadence_points_count"),
            ("aerobic_drift_signal", "cycling_aerobic_drift", "effective_points_count"),
        ):
            with self.subTest(signal=signal_key):
                evidence = self._evidence_by_type(signals[signal_key], evidence_type)
                self.assertFalse(evidence["speed_stop_filter_applied"])
                self.assertGreater(evidence[count_key], 0)
                self.assertNotIn("stopped", evidence.get("filter_reasons") or [])

    def test_observed_zero_speed_still_filters_stopped_samples(self):
        import main

        axis_len = 120
        curves = {
            "distance": [idx * 0.01 for idx in range(axis_len)],
            "time": list(range(axis_len)),
            "power": [190] * axis_len,
            "hr": [138] * axis_len,
            "cadence": [84] * axis_len,
            "speed": [0.0] * axis_len,
        }
        summary = {
            "avg_power": 190,
            "duration_sec": 3600,
            "power_available": True,
            "cadence_available": True,
            "power_points_count": axis_len,
            "cadence_points_count": axis_len,
            "power_data_quality": "available",
            "cadence_data_quality": "available",
            "speed_source": "observed",
            "speed_data_quality": "available",
        }
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary,
            curves,
            profile_ftp_watts=213,
            metrics=main._build_cycling_review_metrics("cycling", summary, curves, avg_hr=138),
        )

        for signal_key, evidence_type in (
            ("power_retention_signal", "effective_pedaling_power_retention"),
            ("cadence_signal", "cycling_cadence_rhythm"),
            ("aerobic_drift_signal", "cycling_aerobic_drift"),
        ):
            with self.subTest(signal=signal_key):
                evidence = self._evidence_by_type(signals[signal_key], evidence_type)
                self.assertTrue(evidence["speed_stop_filter_applied"])
                self.assertIn("stopped", evidence.get("filter_reasons") or [])

    def test_contract_declares_speed_source_quality_and_frontend_boundary(self):
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        with open(contract_path, encoding="utf-8") as f:
            doc = json.load(f)
        item = next(
            item for item in doc.get("methods", doc.get("apis", []))
            if item.get("name") == "get_fatigue_review"
        )
        combined = " ".join((
            item.get("returns", ""),
            item.get("contract", ""),
            item.get("description", ""),
            json.dumps(doc.get("architectural_constraints") or {}, ensure_ascii=False),
        ))

        for token in (
            "speed_source",
            "observed",
            "derived_distance_time",
            "missing",
            "speed_data_quality",
            "insufficient_axis",
            "low_confidence",
            "缺失速度不得零填充为真实停顿证据",
            "前端不得从距离/时间自行推导速度用于卡片分析",
        ):
            self.assertIn(token, combined)


if __name__ == "__main__":
    unittest.main()
