from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


_SIGNAL_KEYS = (
    "intensity_signal",
    "aerobic_drift_signal",
    "power_retention_signal",
    "pacing_signal",
    "cadence_signal",
)


def _assert_signal_shape(testcase: unittest.TestCase, signal: dict) -> None:
    for key in ("status", "level", "summary", "evidence", "reasons"):
        testcase.assertIn(key, signal)
    testcase.assertIn(signal["status"], {"available", "partial", "unavailable"})
    testcase.assertIsInstance(signal["summary"], str)
    testcase.assertIsInstance(signal["evidence"], list)
    testcase.assertIsInstance(signal["reasons"], list)


class TestCyclingExplanationSignalsContract(unittest.TestCase):
    def test_empty_cycling_snapshot_contains_placeholder_contract(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="cycling")
        signals = snapshot.get("cycling_explanation_signals")

        self.assertIsInstance(signals, dict)
        self.assertIn(signals.get("status"), {"partial", "unavailable"})
        self.assertIsInstance(signals.get("evidence"), list)
        self.assertIsInstance(signals.get("unavailable_reasons"), list)
        for key in _SIGNAL_KEYS:
            _assert_signal_shape(self, signals[key])
        self.assertEqual(signals["intensity_signal"]["status"], "unavailable")
        self.assertIn("missing_ftp", signals["intensity_signal"]["reasons"])
        json.dumps(snapshot, ensure_ascii=False)

    def test_empty_running_snapshot_does_not_get_full_cycling_explanations(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="running")
        signals = snapshot.get("cycling_explanation_signals")

        self.assertIsInstance(signals, dict)
        self.assertEqual(signals.get("status"), "unavailable")
        self.assertIn("not_cycling_activity", signals.get("unavailable_reasons") or [])
        for key in _SIGNAL_KEYS:
            _assert_signal_shape(self, signals[key])
            self.assertEqual(signals[key]["status"], "unavailable")

    def test_constructed_cycling_signal_shape_is_stable_without_science_algorithms(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 180,
                "cadence_points_count": 180,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves_snapshot={
                "hr": [130, 132, 134],
                "power": [180, 190, 200],
                "cadence": [82, 84, 86],
            },
        )

        self.assertEqual(signals["status"], "partial")
        self.assertEqual(signals["intensity_signal"]["status"], "unavailable")
        self.assertEqual(signals["intensity_signal"]["level"], "unknown")
        self.assertIn("missing_ftp", signals["unavailable_reasons"])
        self.assertIn("missing_ftp", signals["intensity_signal"]["reasons"])
        self.assertTrue(signals["intensity_signal"]["evidence"])
        for key in _SIGNAL_KEYS:
            _assert_signal_shape(self, signals[key])
            self.assertEqual(signals[key]["level"], "unknown")
        encoded = json.dumps(signals, ensure_ascii=False)
        for forbidden in ("FTP:", "IF:", "TSS", "Pw:Hr", "W/kg", "threshold", "阈值", "高强度", "低强度"):
            self.assertNotIn(forbidden, encoded)

    def test_missing_power_never_produces_power_conclusions(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": False,
                "cadence_available": True,
                "power_data_quality": "missing",
                "cadence_data_quality": "available",
            },
            curves_snapshot={"hr": [130, 132, 134], "cadence": [82, 84, 86]},
        )

        self.assertEqual(signals["intensity_signal"]["status"], "unavailable")
        self.assertIn("power_data_unavailable:missing", signals["intensity_signal"]["reasons"])
        for key in ("power_retention_signal", "pacing_signal"):
            self.assertEqual(signals[key]["status"], "unavailable")
            self.assertIn("power_data_unavailable:missing", signals[key]["reasons"])
        self.assertIn("power_data_unavailable:missing", signals["aerobic_drift_signal"]["reasons"])

    def test_p8_intensity_signal_with_ftp_classifies_relative_intensity(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 180,
                "max_power": 520,
                "normalized_power": 210,
                "duration_sec": 3600,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 240,
                "cadence_points_count": 240,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves_snapshot={"hr": [130, 132, 134], "power": [180, 190, 200], "cadence": [82, 84, 86]},
            profile_ftp_watts=250,
            profile_weight_kg=73.4,
        )

        intensity = signals["intensity_signal"]
        self.assertEqual(intensity["status"], "available")
        self.assertEqual(intensity["level"], "tempo")
        self.assertIn("personal_ftp_available", intensity["reasons"])
        self.assertIn("intensity_basis:normalized_power", intensity["reasons"])
        self.assertNotIn("missing_ftp", signals["unavailable_reasons"])
        encoded = json.dumps(intensity, ensure_ascii=False)
        self.assertIn("avg_power_to_ftp", encoded)
        self.assertIn("normalized_power_to_ftp", encoded)
        self.assertIn("intensity_ratio", encoded)
        self.assertIn("weight_kg", encoded)
        self.assertIn("不是轻松骑", intensity["summary"])
        for forbidden in ("IF", "TSS", "Pw:Hr", "W/kg"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("insufficient_power_hr_points", signals["aerobic_drift_signal"]["reasons"])
        self.assertIn("insufficient_cadence_points", signals["cadence_signal"]["reasons"])

    def test_p8_intensity_signal_classification_levels_are_stable(self):
        import main

        cases = [
            (130, "recovery"),
            (180, "endurance"),
            (210, "tempo"),
            (238, "threshold"),
            (270, "high_intensity"),
        ]
        for normalized_power, expected_level in cases:
            with self.subTest(level=expected_level):
                signals = main._build_cycling_explanation_signals(
                    "cycling",
                    summary={
                        "avg_power": normalized_power - 10,
                        "normalized_power": normalized_power,
                        "power_available": True,
                        "power_points_count": 180,
                        "power_data_quality": "available",
                    },
                    curves_snapshot={"hr": [130] * 180, "power": [normalized_power] * 180},
                    profile_ftp_watts=250,
                )
                intensity = signals["intensity_signal"]
                self.assertEqual(intensity["status"], "available")
                self.assertEqual(intensity["level"], expected_level)

    def test_p8_intensity_signal_degrades_when_power_quality_or_samples_are_insufficient(self):
        import main

        bad_quality = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 180,
                "normalized_power": 210,
                "power_available": True,
                "power_points_count": 180,
                "power_data_quality": "invalid_values",
            },
            curves_snapshot={"hr": [130] * 180, "power": [180] * 180},
            profile_ftp_watts=250,
        )
        self.assertEqual(bad_quality["intensity_signal"]["status"], "unavailable")
        self.assertIn("power_data_unavailable:invalid_values", bad_quality["intensity_signal"]["reasons"])

        short_sample = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 180,
                "normalized_power": 210,
                "power_available": True,
                "power_points_count": 12,
                "power_data_quality": "available",
            },
            curves_snapshot={"hr": [130] * 12, "power": [180] * 12},
            profile_ftp_watts=250,
        )
        self.assertEqual(short_sample["intensity_signal"]["status"], "unavailable")
        self.assertIn("insufficient_power_points", short_sample["intensity_signal"]["reasons"])

    def test_p8_intensity_signal_can_fallback_to_average_power_when_np_missing(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 188,
                "power_available": True,
                "power_points_count": 120,
                "power_data_quality": "available",
            },
            curves_snapshot={"hr": [130] * 120, "power": [188] * 120},
            profile_ftp_watts=250,
        )

        intensity = signals["intensity_signal"]
        self.assertEqual(intensity["status"], "available")
        self.assertEqual(intensity["level"], "tempo")
        self.assertIn("intensity_basis:avg_power", intensity["reasons"])
        self.assertIn("avg_power", json.dumps(intensity["evidence"], ensure_ascii=False))

    def test_p9_aerobic_drift_classifies_stable_power_hr_relationship(self):
        import main

        power = [190] * 100 + [188] * 100
        hr = [140] * 100 + [141] * 100
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 189,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": len(power),
                "cadence_points_count": len(power),
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves_snapshot={
                "hr": hr,
                "power": power,
                "cadence": [84] * len(power),
                "speed": [8] * len(power),
                "time": list(range(len(power))),
            },
            profile_ftp_watts=250,
            metrics={
                "hr_drift": {
                    "pct": 4.2,
                    "level": "good",
                    "confidence": "medium",
                    "reasons": ["steady_aerobic_reference"],
                },
                "decoupling": {
                    "pct": 6.1,
                    "level": "good",
                    "confidence": "medium",
                },
            },
        )

        drift = signals["aerobic_drift_signal"]
        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "stable")
        self.assertIn("effective_power_hr_decoupling", drift["reasons"])
        encoded = json.dumps(drift, ensure_ascii=False)
        self.assertIn("cycling_aerobic_drift", encoded)
        self.assertIn("decoupling_pct", encoded)
        self.assertIn("hr_drift_reference", encoded)
        self.assertIn("review_decoupling_reference", encoded)
        self.assertNotIn("Pw:Hr", encoded)
        for forbidden in ("points", "records", "raw_records", "curves"):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_p9_aerobic_drift_keeps_short_duration_unavailable(self):
        import main

        power = [0] * 40 + [180] * 160
        hr = [135] * 100 + [140] * 100
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 150,
                "normalized_power": 170,
                "duration_sec": 1849,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 160,
                "cadence_points_count": 200,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
                "zero_power_ratio": 0.2,
            },
            curves_snapshot={
                "hr": hr,
                "power": power,
                "cadence": [80] * 200,
                "speed": [7] * 200,
                "time": list(range(200)),
            },
            profile_ftp_watts=250,
        )

        drift = signals["aerobic_drift_signal"]
        self.assertEqual(drift["status"], "unavailable")
        self.assertIn("duration<45min", drift["reasons"])

    def test_p9_aerobic_drift_classifies_significant_drift(self):
        import main

        power = [210] * 100 + [180] * 100
        hr = [138] * 100 + [155] * 100
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 195,
                "power_available": True,
                "power_points_count": len(power),
                "power_data_quality": "available",
            },
            curves_snapshot={
                "hr": hr,
                "power": power,
                "speed": [9] * len(power),
                "time": list(range(len(power))),
            },
            profile_ftp_watts=250,
        )

        drift = signals["aerobic_drift_signal"]
        self.assertEqual(drift["status"], "available")
        self.assertEqual(drift["level"], "significant_drift")
        self.assertIn("有氧漂移较明显", drift["summary"])
        encoded = json.dumps(drift["evidence"], ensure_ascii=False)
        self.assertIn("head_power_per_hr", encoded)
        self.assertIn("tail_power_per_hr", encoded)
        self.assertIn("decoupling_pct", encoded)

    def test_p2_aerobic_drift_missing_hr_or_power_stays_unavailable(self):
        import main

        no_hr = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "cadence_available": True,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves_snapshot={"power": [180, 190, 200]},
        )
        self.assertEqual(no_hr["aerobic_drift_signal"]["status"], "unavailable")
        self.assertIn("missing_hr", no_hr["aerobic_drift_signal"]["reasons"])

        no_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": False,
                "cadence_available": True,
                "power_data_quality": "missing",
                "cadence_data_quality": "available",
            },
            curves_snapshot={"hr": [130, 132, 134], "cadence": [82, 84, 86]},
        )
        self.assertEqual(no_power["aerobic_drift_signal"]["status"], "unavailable")
        self.assertIn("power_data_unavailable:missing", no_power["aerobic_drift_signal"]["reasons"])

    def test_p2_aerobic_drift_evidence_does_not_expose_raw_detail_fields(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_data_quality": "available",
            },
            curves_snapshot={"hr": [130], "power": [180]},
            metrics={
                "hr_drift": {"pct": 4.2, "level": "good", "records": [{"bad": True}]},
                "decoupling": {"pct": 6.1, "level": "good", "curves": [1, 2, 3]},
            },
        )

        encoded = json.dumps(signals["aerobic_drift_signal"]["evidence"], ensure_ascii=False)
        for forbidden in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_p3_effective_pedaling_power_retention_held(self):
        import main

        power = [200] * 80 + [194] * 80
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 197,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [130] * len(power),
                "power": power,
                "speed": [8] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "available")
        self.assertEqual(retention["level"], "held")
        encoded = json.dumps(retention, ensure_ascii=False)
        self.assertIn("effective_pedaling_power_retention", encoded)
        self.assertIn("head_effective_power", encoded)
        self.assertIn("tail_effective_power", encoded)

    def test_p3_effective_pedaling_power_retention_clear_drop(self):
        import main

        power = [220] * 80 + [170] * 80
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 195,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [130] * len(power),
                "power": power,
                "speed": [8] * len(power),
                "time": list(range(len(power))),
            },
            metrics={
                "durability": {
                    "basis": "power_retention",
                    "head_power": 220,
                    "tail_power": 170,
                    "power_retention_pct": 77.3,
                    "power_points_count": len(power),
                    "power_data_quality": "available",
                },
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "available")
        self.assertEqual(retention["level"], "clear_drop")
        encoded = json.dumps(retention, ensure_ascii=False)
        self.assertIn("power_retention_metric_reference", encoded)
        self.assertNotIn("速度后程", encoded)

    def test_p3_effective_pedaling_filters_coasting_instead_of_claiming_drop(self):
        import main

        power = [200] * 80 + [0] * 80
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 100,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [130] * len(power),
                "power": power,
                "speed": [10] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "unavailable")
        self.assertEqual(retention["level"], "unknown")
        self.assertIn("insufficient_effective_pedaling_points", retention["reasons"])
        encoded = json.dumps(retention, ensure_ascii=False)
        self.assertIn("coasting", encoded)
        self.assertNotIn("clear_drop", encoded)

    def test_p3_effective_pedaling_degrades_when_samples_are_insufficient(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": 12,
            },
            curves_snapshot={
                "hr": [130] * 12,
                "power": [200] * 12,
                "speed": [8] * 12,
                "time": list(range(12)),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "unavailable")
        self.assertEqual(retention["level"], "unknown")
        self.assertIn("insufficient_effective_pedaling_points", retention["reasons"])

    def test_p6_downhill_invalid_power_stays_unavailable(self):
        import main

        power = [0] * 60 + [18] * 60 + [0] * 60
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 21,
                "normalized_power": 68,
                "power_available": False,
                "power_data_quality": "invalid_values",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [120] * len(power),
                "power": power,
                "speed": [12] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        pacing = signals["pacing_signal"]
        self.assertEqual(retention["status"], "unavailable")
        self.assertEqual(retention["level"], "unknown")
        self.assertIn("power_data_unavailable:invalid_values", retention["reasons"])
        self.assertEqual(pacing["status"], "unavailable")
        self.assertIn("power_data_unavailable:invalid_values", pacing["reasons"])
        encoded = json.dumps({"retention": retention, "pacing": pacing}, ensure_ascii=False)
        for forbidden in ("clear_drop", "后程功率明显回落", "体能下降", "功率输出波动较大"):
            self.assertNotIn(forbidden, encoded)

    def test_p6_downhill_available_power_requires_filter_evidence_for_drop(self):
        import main

        power = [230] * 80 + [0] * 20 + [165] * 80 + [0] * 20
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 158,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [135] * len(power),
                "power": power,
                "speed": [11] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "available")
        self.assertEqual(retention["level"], "clear_drop")
        evidence = retention["evidence"][0]
        self.assertEqual(evidence["type"], "effective_pedaling_power_retention")
        self.assertGreaterEqual(evidence["head_effective_points_count"], 10)
        self.assertGreaterEqual(evidence["tail_effective_points_count"], 10)
        self.assertGreater(evidence["filtered_points_count"], 0)
        self.assertIn("coasting", evidence["filter_reasons"])
        self.assertEqual(evidence["power_data_quality"], "available")

    def test_p6_downhill_coasting_with_insufficient_effective_tail_degrades(self):
        import main

        power = [210] * 90 + [0] * 90
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 105,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [130] * len(power),
                "power": power,
                "speed": [12] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "unavailable")
        self.assertEqual(retention["level"], "unknown")
        self.assertIn("insufficient_effective_pedaling_points", retention["reasons"])
        evidence = retention["evidence"][0]
        self.assertEqual(evidence["tail_effective_points_count"], 0)
        self.assertIn("coasting", evidence["filter_reasons"])
        self.assertNotIn("体能下降", json.dumps(retention, ensure_ascii=False))

    def test_p3_power_retention_evidence_does_not_expose_raw_detail_fields(self):
        import main

        power = [200] * 40 + [180] * 40
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 190,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={
                "hr": [130] * len(power),
                "power": power,
                "speed": [8] * len(power),
                "time": list(range(len(power))),
            },
            metrics={
                "durability": {
                    "basis": "power_retention",
                    "head_power": 200,
                    "tail_power": 180,
                    "power_retention_pct": 90.0,
                    "records": [{"bad": True}],
                    "curves": [1, 2, 3],
                },
            },
        )

        encoded = json.dumps(signals["power_retention_signal"]["evidence"], ensure_ascii=False)
        for forbidden in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_p4_pacing_signal_steady_power_output(self):
        import main

        power = [200, 202, 198, 201, 199] * 40
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 200,
                "normalized_power": 206,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={"hr": [130] * len(power), "power": power},
            metrics={"power_variability": {"vi": 1.03, "level": "good", "confidence": "high"}},
        )

        pacing = signals["pacing_signal"]
        self.assertEqual(pacing["status"], "available")
        self.assertEqual(pacing["level"], "steady")
        encoded = json.dumps(pacing, ensure_ascii=False)
        self.assertIn("cycling_pacing_reference", encoded)
        self.assertIn("vi", encoded)

    def test_p4_pacing_signal_variable_when_vi_is_high(self):
        import main

        power = [120, 320, 140, 300, 160, 280] * 30
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 220,
                "normalized_power": 265,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={"hr": [130] * len(power), "power": power},
            metrics={"power_variability": {"vi": 1.20, "level": "variable", "confidence": "high"}},
        )

        self.assertEqual(signals["pacing_signal"]["status"], "available")
        self.assertEqual(signals["pacing_signal"]["level"], "variable")

    def test_p4_pacing_signal_front_loaded(self):
        import main

        power = [260] * 40 + [205] * 40 + [190] * 80
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 211,
                "normalized_power": 225,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={"hr": [130] * len(power), "power": power},
            metrics={"power_variability": {"vi": 1.07, "level": "moderate", "confidence": "high"}},
        )

        self.assertEqual(signals["pacing_signal"]["status"], "available")
        self.assertEqual(signals["pacing_signal"]["level"], "front_loaded")

    def test_p4_pacing_signal_late_fade_without_front_loaded_start(self):
        import main

        power = [220] * 80 + [185] * 80
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 202,
                "normalized_power": 215,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={"hr": [130] * len(power), "power": power},
            metrics={
                "power_variability": {"vi": 1.06, "level": "moderate", "confidence": "high"},
                "durability": {"basis": "power_retention", "power_retention_pct": 84.1},
            },
        )

        pacing = signals["pacing_signal"]
        self.assertEqual(pacing["status"], "available")
        self.assertEqual(pacing["level"], "late_fade")
        self.assertIn("power_retention_pct", json.dumps(pacing["evidence"], ensure_ascii=False))

    def test_p4_pacing_signal_degrades_without_power_or_enough_samples(self):
        import main

        no_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={"power_available": False, "power_data_quality": "missing"},
            curves_snapshot={"hr": [130] * 20},
        )
        self.assertEqual(no_power["pacing_signal"]["status"], "unavailable")
        self.assertIn("power_data_unavailable:missing", no_power["pacing_signal"]["reasons"])

        short_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": 8,
            },
            curves_snapshot={"hr": [130] * 8, "power": [200] * 8},
        )
        self.assertEqual(short_power["pacing_signal"]["status"], "unavailable")
        self.assertIn("insufficient_power_points", short_power["pacing_signal"]["reasons"])

    def test_p4_pacing_evidence_does_not_expose_raw_detail_fields(self):
        import main

        power = [200] * 40 + [180] * 40
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 190,
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": len(power),
            },
            curves_snapshot={"hr": [130] * len(power), "power": power},
            metrics={
                "power_variability": {
                    "vi": 1.05,
                    "level": "moderate",
                    "records": [{"bad": True}],
                    "curves": [1, 2, 3],
                },
            },
        )

        encoded = json.dumps(signals["pacing_signal"]["evidence"], ensure_ascii=False)
        for forbidden in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_p10_cadence_signal_steady_rhythm(self):
        import main

        cadence = [86, 87, 85, 86] * 50
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_cadence": 86,
                "cadence_available": True,
                "cadence_data_quality": "available",
                "cadence_points_count": len(cadence),
            },
            curves_snapshot={
                "cadence": cadence,
                "speed": [8] * len(cadence),
                "time": list(range(len(cadence))),
            },
        )

        cadence_signal = signals["cadence_signal"]
        self.assertEqual(cadence_signal["status"], "available")
        self.assertEqual(cadence_signal["level"], "steady")
        encoded = json.dumps(cadence_signal, ensure_ascii=False)
        self.assertIn("cycling_cadence_rhythm", encoded)
        self.assertIn("cadence_cv", encoded)
        self.assertIn("effective_cadence_points_count", encoded)

    def test_p10_cadence_signal_degrades_without_cadence_or_enough_samples(self):
        import main

        no_cadence = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "cadence_available": False,
                "cadence_data_quality": "missing",
                "cadence_points_count": 0,
            },
            curves_snapshot={"hr": [130] * 80},
        )
        self.assertEqual(no_cadence["cadence_signal"]["status"], "unavailable")
        self.assertIn("cadence_data_unavailable:missing", no_cadence["cadence_signal"]["reasons"])

        short_cadence = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "cadence_available": True,
                "cadence_data_quality": "available",
                "cadence_points_count": 12,
            },
            curves_snapshot={"cadence": [86] * 12},
        )
        self.assertEqual(short_cadence["cadence_signal"]["status"], "unavailable")
        self.assertIn("insufficient_cadence_points", short_cadence["cadence_signal"]["reasons"])

    def test_p10_cadence_signal_does_not_expose_raw_or_technical_detail_fields(self):
        import main

        cadence = [72, 96, 78, 100] * 40
        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_cadence": 86,
                "cadence_available": True,
                "cadence_data_quality": "available",
                "cadence_points_count": len(cadence),
            },
            curves_snapshot={"cadence": cadence, "points": [{"bad": True}], "raw_records": [{"bad": True}]},
            metrics={"pedaling_stability": {"score": 62, "level": "moderate", "records": [{"bad": True}]}},
        )

        encoded = json.dumps(signals["cadence_signal"], ensure_ascii=False)
        for forbidden in (
            "points", "records", "raw_records", "curves", "shadow_diff", "diff",
            "齿比", "扭矩", "左右平衡", "踩踏效率", "踩踏平滑度", "踩踏技术差",
        ):
            self.assertNotIn(f'"{forbidden}"', encoded)
            if forbidden not in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
                self.assertNotIn(forbidden, encoded)

    def test_intensity_evidence_does_not_expose_raw_detail_fields(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 180,
                "normalized_power": 210,
                "power_available": True,
                "power_points_count": 240,
                "power_data_quality": "available",
            },
            curves_snapshot={"hr": [130], "power": [180]},
            profile_ftp_watts=250,
        )

        encoded = json.dumps(signals["intensity_signal"]["evidence"], ensure_ascii=False)
        for forbidden in ("points", "records", "raw_records", "curves", "shadow_diff", "diff"):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_frontend_only_reads_backend_cycling_explanation_signals(self):
        track_path = os.path.join(_PROJECT_ROOT, "track.html")
        with open(track_path, encoding="utf-8") as f:
            body = f.read()

        self.assertIn("data.cycling_explanation_signals || {}", body)
        self.assertNotIn("cyclingExplanationSignals", body)
        self.assertNotIn("_build_cycling_explanation_signals(", body)

        start = body.index("function _fatigueReviewCyclingSignal(")
        end = body.index("function _renderFatigueReviewMetrics(", start)
        helpers = body[start:end]
        self.assertIn("signals[key]", helpers)
        self.assertIn("signal['summary']", helpers)
        self.assertIn("signal.evidence", helpers)
        self.assertIn("signal.reasons", helpers)
        self.assertIn("_fatigueReviewCyclingSignalEvidenceItemText", helpers)
        self.assertIn("_fatigueReviewCyclingSignalReasonText", helpers)
        self.assertIn("_fatigueReviewCyclingSignalVisibility", helpers)
        self.assertIn("_fatigueReviewCyclingSignalCanOwnHeadline", helpers)
        self.assertIn("_fatigueReviewCyclingSignalHeadline", helpers)
        self.assertIn("_fatigueReviewCyclingSignalSummaryText", helpers)
        self.assertIn("canOwnHeadline: state === 'available'", helpers)
        self.assertIn("canShowAsReference: state === 'available' || state === 'partial'", helpers)
        self.assertIn("if (!_fatigueReviewCyclingSignalCanOwnHeadline(signal))", helpers)
        self.assertNotIn("String(item.type).replace(/_/g, ' ')", helpers)
        self.assertNotIn("key.replace(/_/g, ' ')", helpers)
        self.assertNotIn("signal.reasons.join", helpers)
        self.assertNotIn("专项算法尚未完成", helpers)
        self.assertNotIn("后端证据", helpers)
        self.assertNotIn("本阶段", helpers)
        self.assertNotIn("后端未返回可展示", helpers)
        for forbidden in (
            "curves.",
            "summary.avg_power",
            "metrics.",
            "querySelector",
            "getOption",
            "points[]",
            ".points",
            "powerVar.vi",
            "hrDrift.pct",
            "durCycling.power_retention_pct",
        ):
            self.assertNotIn(forbidden, helpers)

    def test_ai_compact_snapshot_only_passes_backend_signal_field_through(self):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, encoding="utf-8") as f:
            body = f.read()
        start = body.index("def _build_fatigue_review_insight_snapshot(")
        end = body.index("def _build_fatigue_review_snapshot(", start)
        compact_builder = body[start:end]

        self.assertIn(
            '"cycling_explanation_signals": review_snapshot.get("cycling_explanation_signals") or {}',
            compact_builder,
        )
        self.assertNotIn("_build_cycling_explanation_signals(", compact_builder)


if __name__ == "__main__":
    unittest.main()
