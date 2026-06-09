from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP2SnapshotRealignment(unittest.TestCase):
    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_historical_metrics_avg = MagicMock(return_value={
            "sample_size": 0,
            "hr_drift_pct": None,
            "decoupling_pct": None,
            "bonk_count": 0,
        })
        api._fetch_efficiency_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_ratio": None,
        })
        api._fetch_durability_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_ratio": None,
        })
        api._fetch_cadence_stability_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_cv": None,
        })
        api._fetch_load_ratio_7d_42d = MagicMock(return_value={
            "ratio": None,
            "level": "unknown",
            "acute_7d": None,
            "chronic_42d": None,
            "compared_count": 0,
        })
        api._fetch_training_load_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_load": None,
        })
        return api

    def _row(self, *, calories=1800, include_altitude=True, point_count=80) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(point_count):
            point = {
                "lat": 31.0 + i * 0.00008,
                "lon": 121.0,
                "time": (base + timedelta(seconds=i * 20)).isoformat(),
                "hr": 135 + min(i, 35),
                "speed": 3.2,
                "cadence": 84,
            }
            if include_altitude:
                point["alt"] = 100.0 + i * 1.4
            points.append(point)
        return {
            "id": 42,
            "sport_type": "running",
            "dist_km": 7.5,
            "distance": 7500.0,
            "duration_sec": point_count * 20,
            "calories": calories,
            "track_json": json.dumps(points),
            "points_json": None,
            "merged_track_json": None,
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": json.dumps([p["speed"] for p in points]),
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
        }

    def test_snapshot_curves_are_authoritative_and_length_aligned(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        curves = snapshot["curves"]
        axis_len = len(curves["distance"])

        self.assertGreater(axis_len, 0)
        self.assertEqual(curves["total_distance_m"], 7500.0)
        for key in ("time", "hr", "speed", "altitude", "grade", "gap", "efficiency"):
            if curves[key]:
                self.assertEqual(len(curves[key]), axis_len, key)
        self.assertGreater(curves["distance"][-1], 0)
        self.assertLessEqual(curves["distance"][-1], curves["total_distance_m"] / 1000.0)

    def test_snapshot_missing_calories_keeps_curves_and_disables_bonk_risk(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row(calories=None))

        self.assertGreater(len(snapshot["curves"]["distance"]), 0)
        self.assertFalse(snapshot["metrics"]["bonk_risk"]["is_at_risk"])

    def test_snapshot_incomplete_points_uses_empty_missing_curves(self):
        snapshot = self._api()._build_fatigue_review_snapshot(
            self._row(include_altitude=False, point_count=10)
        )

        curves = snapshot["curves"]
        self.assertIn("distance", curves)
        self.assertIn("altitude", curves)
        self.assertIsInstance(curves["altitude"], list)
        for key in ("metrics", "collapse_events", "fatigue_zones", "context_tags", "advice"):
            self.assertIn(key, snapshot)

    def test_snapshot_recursively_strips_forbidden_fields(self):
        from main import _strip_fatigue_review_forbidden_keys

        cleaned = _strip_fatigue_review_forbidden_keys({
            "curves": {"distance": [0], "records": [{"x": 1}]},
            "context_tags": {"shadow_diff": "debug", "ok": "yes"},
            "events": [{"diff": "debug", "type": "x"}],
        })
        encoded = json.dumps(cleaned, ensure_ascii=False)

        for forbidden in ("records", "shadow_diff", '"diff"'):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(cleaned["context_tags"]["ok"], "yes")

    def test_get_fatigue_review_error_envelope_paths(self):
        from main import API_CODE_NOT_FOUND, API_CODE_VALIDATION, Api

        api = Api()
        invalid = api.get_fatigue_review(0)
        self.assertEqual(invalid["code"], API_CODE_VALIDATION)
        self.assertIn("traceId", invalid)
        self.assertEqual(invalid["data"], {})

        api._fetch_activity_row = MagicMock(return_value=None)
        not_found = api.get_fatigue_review(999999999)
        self.assertEqual(not_found["code"], API_CODE_NOT_FOUND)
        self.assertIn("traceId", not_found)
        self.assertEqual(not_found["data"], {})


if __name__ == "__main__":
    unittest.main()
