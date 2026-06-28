from __future__ import annotations

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestCyclingFatigueReviewMetrics(unittest.TestCase):
    def _summary(self, **overrides):
        base = {
            "avg_power": 200,
            "normalized_power": 220,
            "avg_cadence": 86,
            "power_points_count": 180,
            "cadence_points_count": 180,
            "power_data_quality": "available",
            "cadence_data_quality": "available",
        }
        base.update(overrides)
        return base

    def test_power_variability_calculates_vi_from_np_and_avg_power(self):
        import main

        metric = main._build_cycling_power_variability_metric(self._summary())

        self.assertEqual(metric["vi"], 1.10)
        self.assertEqual(metric["level"], "moderate")
        self.assertEqual(metric["confidence"], "high")
        self.assertEqual(metric["avg_power"], 200.0)
        self.assertEqual(metric["normalized_power"], 220.0)
        self.assertEqual(metric["power_data_quality"], "available")
        self.assertEqual(metric["reasons"], [])

    def test_power_variability_levels(self):
        import main

        cases = [
            (200, 208, "good"),
            (200, 220, "moderate"),
            (200, 240, "variable"),
            (200, 270, "surging"),
        ]
        for avg_power, normalized_power, expected_level in cases:
            with self.subTest(expected_level=expected_level):
                metric = main._build_cycling_power_variability_metric(
                    self._summary(avg_power=avg_power, normalized_power=normalized_power)
                )
                self.assertEqual(metric["level"], expected_level)

    def test_power_variability_degrades_when_power_quality_missing(self):
        import main

        metric = main._build_cycling_power_variability_metric(
            self._summary(power_data_quality="missing", power_points_count=0)
        )

        self.assertIsNone(metric["vi"])
        self.assertEqual(metric["level"], "unknown")
        self.assertEqual(metric["confidence"], "unavailable")
        self.assertIn("power data unavailable: missing", metric["reasons"])

    def test_power_variability_does_not_compute_without_normalized_power(self):
        import main

        metric = main._build_cycling_power_variability_metric(
            self._summary(normalized_power=None, power_points_count=180)
        )

        self.assertIsNone(metric["vi"])
        self.assertEqual(metric["confidence"], "low")
        self.assertIn("missing normalized_power", metric["reasons"])

    def test_pedaling_stability_scores_stable_cadence_high(self):
        import main

        cadence = [84, 85, 86, 85, 84, 86] * 30
        metric = main._build_cycling_pedaling_stability_metric(self._summary(), cadence)

        self.assertGreaterEqual(metric["score"], 90)
        self.assertEqual(metric["level"], "good")
        self.assertEqual(metric["confidence"], "high")
        self.assertLess(metric["cv"], 0.02)
        self.assertAlmostEqual(metric["decay_pct"], 0.0, delta=1.0)
        self.assertEqual(metric["cadence_data_quality"], "available")

    def test_pedaling_stability_score_drops_for_large_decay(self):
        import main

        cadence = [95] * 90 + [70] * 90
        metric = main._build_cycling_pedaling_stability_metric(self._summary(), cadence)

        self.assertLess(metric["score"], 60)
        self.assertIn(metric["level"], {"unstable", "poor"})
        self.assertLess(metric["decay_pct"], -20)

    def test_pedaling_stability_degrades_when_cadence_missing(self):
        import main

        metric = main._build_cycling_pedaling_stability_metric(
            self._summary(cadence_data_quality="missing", cadence_points_count=0),
            [],
        )

        self.assertIsNone(metric["score"])
        self.assertIsNone(metric["cv"])
        self.assertEqual(metric["level"], "unknown")
        self.assertEqual(metric["confidence"], "unavailable")
        self.assertIn("cadence data unavailable: missing", metric["reasons"])

    def test_power_efficiency_uses_power_per_hr_for_cycling(self):
        import main

        metric = main._build_cycling_power_efficiency_metric(self._summary(avg_power=240), avg_hr=150)

        self.assertEqual(metric["basis"], "power_hr")
        self.assertEqual(metric["power_per_hr"], 1.6)
        self.assertEqual(metric["avg_power"], 240.0)
        self.assertEqual(metric["avg_hr"], 150.0)
        self.assertEqual(metric["level"], "moderate")
        self.assertEqual(metric["confidence"], "high")
        self.assertIsNone(metric["delta_pct"])
        self.assertEqual(metric["sample_size"], 0)
        self.assertEqual(metric["reasons"], [])

    def test_power_efficiency_degrades_without_power_or_hr(self):
        import main

        no_power = main._build_cycling_power_efficiency_metric(
            self._summary(power_data_quality="missing", power_points_count=0),
            avg_hr=150,
        )
        no_hr = main._build_cycling_power_efficiency_metric(self._summary(avg_power=220), avg_hr=None)

        self.assertIsNone(no_power["power_per_hr"])
        self.assertEqual(no_power["confidence"], "unavailable")
        self.assertIn("power data unavailable: missing", no_power["reasons"])
        self.assertIsNone(no_hr["power_per_hr"])
        self.assertEqual(no_hr["confidence"], "low")
        self.assertIn("missing avg_hr", no_hr["reasons"])

    def test_power_durability_uses_late_ride_power_retention(self):
        import main

        power = [220] * 90 + [180] * 90
        metric = main._build_cycling_power_durability_metric(self._summary(), power)

        self.assertEqual(metric["basis"], "power_retention")
        self.assertEqual(metric["head_speed"], None)
        self.assertEqual(metric["tail_speed"], None)
        self.assertEqual(metric["head_power"], 220.0)
        self.assertEqual(metric["tail_power"], 180.0)
        self.assertEqual(metric["power_retention_pct"], 81.8)
        self.assertEqual(metric["score"], 62)
        self.assertEqual(metric["level"], "dropping")
        self.assertEqual(metric["confidence"], "high")

    def test_power_durability_degrades_without_usable_power_curve(self):
        import main

        metric = main._build_cycling_power_durability_metric(
            self._summary(power_data_quality="insufficient_points", power_points_count=10),
            [200] * 10,
        )

        self.assertIsNone(metric["power_retention_pct"])
        self.assertEqual(metric["basis"], "power_retention")
        self.assertEqual(metric["confidence"], "unavailable")
        self.assertIn("power data unavailable: insufficient_points", metric["reasons"])

    def test_cycling_review_metrics_apply_only_to_cycling_types(self):
        import main

        cycling = main._build_cycling_review_metrics(
            "cycling",
            self._summary(),
            {
                "power": [220] * 90 + [210] * 90,
                "cadence": [85, 86, 84, 85, 86] * 36,
            },
            avg_hr=140,
        )
        running = main._build_cycling_review_metrics(
            "running",
            self._summary(),
            {
                "power": [220] * 90 + [210] * 90,
                "cadence": [85, 86, 84, 85, 86] * 36,
            },
            avg_hr=140,
        )

        self.assertEqual(cycling["efficiency"]["basis"], "power_hr")
        self.assertEqual(cycling["durability"]["basis"], "power_retention")
        self.assertEqual(cycling["power_variability"]["vi"], 1.10)
        self.assertIsNotNone(cycling["pedaling_stability"]["score"])
        self.assertNotIn("efficiency", running)
        self.assertNotIn("durability", running)
        self.assertIsNone(running["power_variability"]["vi"])
        self.assertEqual(running["power_variability"]["confidence"], "unavailable")
        self.assertIn("unavailable for this sport", running["power_variability"]["reasons"][0])

    def test_empty_snapshot_contains_p3_metric_shape(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="cycling")
        power = snapshot["metrics"]["power_variability"]
        cadence = snapshot["metrics"]["pedaling_stability"]

        for key in ("vi", "level", "confidence", "avg_power", "normalized_power", "power_points_count", "power_data_quality", "reasons"):
            self.assertIn(key, power)
        for key in ("score", "level", "confidence", "cv", "decay_pct", "avg_cadence", "cadence_points_count", "cadence_data_quality", "reasons"):
            self.assertIn(key, cadence)

    def test_empty_cycling_snapshot_contains_p3b_metric_shape(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="cycling")
        efficiency = snapshot["metrics"]["efficiency"]
        durability = snapshot["metrics"]["durability"]

        for key in ("basis", "power_per_hr", "avg_power", "avg_hr", "power_data_quality"):
            self.assertIn(key, efficiency)
        for key in ("basis", "head_power", "tail_power", "power_retention_pct", "power_points_count", "power_data_quality"):
            self.assertIn(key, durability)
        self.assertEqual(efficiency["basis"], "power_hr")
        self.assertEqual(durability["basis"], "power_retention")

    def test_empty_running_snapshot_does_not_gain_power_efficiency_basis(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="running")

        self.assertNotIn("basis", snapshot["metrics"]["efficiency"])
        self.assertNotIn("power_retention_pct", snapshot["metrics"]["durability"])


if __name__ == "__main__":
    unittest.main()
