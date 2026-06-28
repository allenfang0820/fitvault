from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestCyclingCadenceSignalAlgorithm(unittest.TestCase):
    def _cadence_signal(self, *, cadence, summary=None, power=None, speed=None, time=None):
        import main

        curves = {
            "cadence": cadence,
            "speed": speed if speed is not None else [8] * len(cadence),
            "time": time if time is not None else list(range(len(cadence))),
        }
        if power is not None:
            curves["power"] = power
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_cadence": sum([x for x in cadence if isinstance(x, (int, float))]) / len(cadence) if cadence else None,
                "cadence_available": True,
                "cadence_points_count": len(cadence),
                "cadence_data_quality": "available",
                **(summary or {}),
            },
            curves_snapshot=curves,
            profile_ftp_watts=250,
        )
        return signals["cadence_signal"]

    def test_steady_cadence_is_available(self):
        signal = self._cadence_signal(cadence=[86, 87, 85, 86] * 60)

        self.assertEqual(signal["status"], "available")
        self.assertEqual(signal["level"], "steady")
        self.assertIn("踏频节奏比较稳定", signal["summary"])

    def test_variable_cadence_is_available(self):
        signal = self._cadence_signal(cadence=[72, 98, 75, 102, 80, 96] * 40)

        self.assertEqual(signal["status"], "available")
        self.assertEqual(signal["level"], "variable")
        self.assertIn("踏频波动较大", signal["summary"])

    def test_low_cadence_bias_is_available(self):
        signal = self._cadence_signal(cadence=[62, 64, 66, 68, 70] * 50)

        self.assertEqual(signal["status"], "available")
        self.assertEqual(signal["level"], "low_cadence_bias")
        self.assertIn("偏力量型输出", signal["summary"])

    def test_tail_cadence_drop_is_available(self):
        signal = self._cadence_signal(cadence=[88] * 120 + [76] * 120)

        self.assertEqual(signal["status"], "available")
        self.assertEqual(signal["level"], "cadence_drop")
        self.assertIn("后半程踏频有所下降", signal["summary"])

    def test_coasting_heavy_sample_reports_interrupted_or_degrades(self):
        signal = self._cadence_signal(
            cadence=[86] * 90 + [0] * 70 + [84] * 90,
            power=[190] * 90 + [0] * 70 + [185] * 90,
            speed=[8] * 250,
        )

        self.assertIn(signal["status"], {"available", "unavailable"})
        if signal["status"] == "available":
            self.assertEqual(signal["level"], "interrupted")
            self.assertIn("踩踏中断较多", signal["summary"])
        else:
            self.assertIn("insufficient_cadence_points", signal["reasons"])
        encoded = json.dumps(signal, ensure_ascii=False)
        self.assertIn("coasting", encoded)
        for forbidden in ("踩踏技术差", "技术下降", "左右平衡", "扭矩", "齿比"):
            self.assertNotIn(forbidden, encoded)

    def test_missing_or_bad_cadence_stays_unavailable(self):
        import main

        no_cadence = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "cadence_available": False,
                "cadence_points_count": 0,
                "cadence_data_quality": "missing",
            },
            curves_snapshot={"hr": [130] * 80},
            profile_ftp_watts=250,
        )["cadence_signal"]
        self.assertEqual(no_cadence["status"], "unavailable")
        self.assertIn("cadence_data_unavailable:missing", no_cadence["reasons"])

        bad_quality = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "cadence_available": True,
                "cadence_points_count": 80,
                "cadence_data_quality": "invalid_values",
            },
            curves_snapshot={"cadence": [85] * 80},
            profile_ftp_watts=250,
        )["cadence_signal"]
        self.assertEqual(bad_quality["status"], "unavailable")
        self.assertIn("cadence_data_unavailable:invalid_values", bad_quality["reasons"])

    def test_short_or_unaligned_samples_stay_unavailable(self):
        short = self._cadence_signal(cadence=[86] * 12)
        self.assertEqual(short["status"], "unavailable")
        self.assertIn("insufficient_cadence_points", short["reasons"])

        import main

        unaligned = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "cadence_available": True,
                "cadence_points_count": 120,
                "cadence_data_quality": "available",
            },
            curves_snapshot={"cadence": [86] * 120, "speed": [8] * 90},
            profile_ftp_watts=250,
        )["cadence_signal"]
        self.assertEqual(unaligned["status"], "unavailable")
        self.assertIn("curve_length_mismatch", unaligned["reasons"])

    def test_evidence_does_not_expose_raw_detail_fields(self):
        signal = self._cadence_signal(
            cadence=[86, 87, 85, 86] * 40,
            summary={"points": [{"bad": True}]},
        )

        encoded = json.dumps(signal["evidence"], ensure_ascii=False)
        for forbidden in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
            self.assertNotIn(f'"{forbidden}"', encoded)


if __name__ == "__main__":
    unittest.main()
