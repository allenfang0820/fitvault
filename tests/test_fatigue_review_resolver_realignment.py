from __future__ import annotations

import inspect
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP1Realignment(unittest.TestCase):
    def _sample_row(self) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(60):
            points.append({
                "lat": 31.0 + i * 0.00012,
                "lon": 121.0,
                "alt": 100.0 + i * 1.8,
                "time": (base + timedelta(seconds=i * 30)).isoformat(),
                "hr": 135 + min(i, 25),
                "speed": 3.0,
                "cadence": 82,
            })
        return {
            "sport_type": "running",
            "dist_km": 8.0,
            "distance": 8000.0,
            "duration_sec": 1800,
            "calories": 1800,
            "track_json": __import__("json").dumps(points),
            "points_json": None,
            "merged_track_json": None,
            "cadence_curve": "[82, 83, 84]",
        }

    def test_curve_bundle_uses_track_json_truth(self):
        from main import _build_fatigue_review_curve_bundle

        bundle = _build_fatigue_review_curve_bundle(self._sample_row())
        self.assertEqual(bundle["source"], "track_json")
        self.assertEqual(bundle["sport_type"], "running")
        self.assertEqual(bundle["calories"], 1800.0)
        self.assertEqual(bundle["total_distance_m"], 8000.0)
        self.assertEqual(len(bundle["records"]), 60)
        self.assertEqual(len(bundle["distance_curve_m"]), 60)
        self.assertEqual(len(bundle["time_curve_sec"]), 60)
        self.assertEqual(len(bundle["altitude_curve_m"]), 60)
        self.assertGreater(bundle["distance_curve_m"][-1], 0)
        self.assertGreater(bundle["altitude_curve_m"][-1], bundle["altitude_curve_m"][0])

    def test_resolved_payload_uses_real_altitude_distance_and_calories(self):
        from main import _build_fatigue_review_curve_bundle, _build_resolved_payload_v81

        bundle = _build_fatigue_review_curve_bundle(self._sample_row())
        resolved = _build_resolved_payload_v81(bundle=bundle, sport_type="running")
        self.assertEqual(resolved["distance_curve"], bundle["distance_curve_m"])
        self.assertEqual(resolved["time_curve"], bundle["time_curve_sec"])
        self.assertEqual(resolved["altitude_curve"], bundle["altitude_curve_m"])
        self.assertTrue(any(abs(v) > 0 for v in resolved["grade_curve"]))
        self.assertEqual(len(resolved["efficiency_curve"]), len(bundle["distance_curve_m"]))

    def test_snapshot_exposes_authoritative_curve_axes(self):
        from main import Api

        snapshot = Api()._build_fatigue_review_snapshot(self._sample_row())
        curves = snapshot["curves"]
        self.assertEqual(len(curves["distance"]), 60)
        self.assertEqual(len(curves["time"]), 60)
        self.assertEqual(len(curves["altitude"]), 60)
        self.assertGreater(curves["distance"][-1], 0)
        self.assertGreater(curves["altitude"][-1], curves["altitude"][0])
        self.assertNotIn("records", snapshot)

    def test_main_resolver_path_no_longer_contains_fake_records(self):
        import main

        source = inspect.getsource(main._build_resolved_payload_v81)
        self.assertNotIn('"altitude": 100.0', source)
        self.assertNotIn("'altitude': 100.0", source)
        self.assertNotIn('"session_mesgs": [{}]', source)
        self.assertNotIn("'session_mesgs': [{}]", source)
        self.assertNotIn("dt = 1.0", source)

    def test_metrics_resolver_passes_sport_type_to_bonk(self):
        from metrics_resolver import MetricsResolver

        source = inspect.getsource(MetricsResolver.resolve)
        self.assertIn("sport_type=sport_type", source)


if __name__ == "__main__":
    unittest.main()
