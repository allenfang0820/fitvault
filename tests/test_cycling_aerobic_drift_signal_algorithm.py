from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestCyclingAerobicDriftSignalAlgorithm(unittest.TestCase):
    def _drift(self, *, power, hr, summary=None, speed=None, time=None):
        import main

        curves = {
            "power": power,
            "hr": hr,
            "speed": speed if speed is not None else [8] * len(power),
            "time": time if time is not None else list(range(len(power))),
        }
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": sum(power) / len(power) if power else 0,
                "power_available": True,
                "power_points_count": len(power),
                "power_data_quality": "available",
                **(summary or {}),
            },
            curves_snapshot=curves,
            profile_ftp_watts=250,
        )
        return signals["aerobic_drift_signal"]

    def test_stable_power_hr_relationship_is_available(self):
        drift = self._drift(
            power=[200] * 120 + [198] * 120,
            hr=[140] * 120 + [141] * 120,
        )

        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "stable")
        self.assertIn("暂未看到明显有氧漂移", drift["summary"])

    def test_mild_drift_is_available_when_tail_ratio_drops_moderately(self):
        drift = self._drift(
            power=[205] * 120 + [196] * 120,
            hr=[140] * 120 + [148] * 120,
        )

        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "mild_drift")
        self.assertIn("轻微有氧漂移", drift["summary"])

    def test_significant_drift_is_available_when_power_hr_ratio_separates(self):
        drift = self._drift(
            power=[215] * 120 + [180] * 120,
            hr=[138] * 120 + [156] * 120,
        )

        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "significant_drift")
        self.assertIn("有氧漂移较明显", drift["summary"])

    def test_coasting_and_stops_are_filtered_before_drift_classification(self):
        drift = self._drift(
            power=[210] * 100 + [0] * 40 + [205] * 100,
            hr=[140] * 100 + [142] * 40 + [142] * 100,
            speed=[8] * 100 + [10] * 40 + [8] * 100,
        )

        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "stable")
        encoded = json.dumps(drift["evidence"], ensure_ascii=False)
        self.assertIn("coasting", encoded)

    def test_short_or_unaligned_samples_stay_unavailable(self):
        short = self._drift(power=[190] * 18, hr=[140] * 18)
        self.assertEqual(short["status"], "unavailable")
        self.assertIn("insufficient_power_hr_points", short["reasons"])

        import main

        unaligned = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_points_count": 120,
                "power_data_quality": "available",
            },
            curves_snapshot={"power": [190] * 120, "hr": [140] * 80},
            profile_ftp_watts=250,
        )["aerobic_drift_signal"]
        self.assertEqual(unaligned["status"], "unavailable")
        self.assertIn("curve_length_mismatch", unaligned["reasons"])

    def test_missing_inputs_do_not_emit_drift_conclusion(self):
        import main

        no_hr = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_points_count": 120,
                "power_data_quality": "available",
            },
            curves_snapshot={"power": [190] * 120},
            profile_ftp_watts=250,
        )["aerobic_drift_signal"]
        self.assertEqual(no_hr["status"], "unavailable")
        self.assertIn("missing_hr", no_hr["reasons"])

        no_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": False,
                "power_points_count": 0,
                "power_data_quality": "missing",
            },
            curves_snapshot={"hr": [140] * 120},
            profile_ftp_watts=250,
        )["aerobic_drift_signal"]
        self.assertEqual(no_power["status"], "unavailable")
        self.assertIn("power_data_unavailable:missing", no_power["reasons"])


if __name__ == "__main__":
    unittest.main()
