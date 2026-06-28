from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestCyclingExplanationEvidenceLabels(unittest.TestCase):
    def _signals(self) -> dict:
        import main

        power = [190, 195, 200, 188, 192, 196] * 40
        hr = [130, 131, 132, 131, 133, 134] * 20 + [137, 138, 139, 140, 141, 142] * 20
        cadence = [86, 87, 85, 86, 88, 87] * 40
        return main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 192,
                "max_power": 430,
                "normalized_power": 205,
                "avg_cadence": 86,
                "duration_sec": 3600,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": len(power),
                "cadence_points_count": len(cadence),
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves_snapshot={
                "power": power,
                "hr": hr,
                "cadence": cadence,
                "speed": [8] * len(power),
                "time": list(range(len(power))),
            },
            profile_ftp_watts=250,
            profile_weight_kg=73.4,
            metrics={
                "power_variability": {"vi": 1.07, "level": "stable", "confidence": "high"},
                "pedaling_stability": {
                    "score": 92,
                    "level": "stable",
                    "confidence": "high",
                    "cv": 0.025,
                    "decay_pct": -1.0,
                    "avg_cadence": 86,
                    "cadence_points_count": len(cadence),
                    "cadence_data_quality": "available",
                },
                "durability": {
                    "basis": "power_retention",
                    "head_power": 194,
                    "tail_power": 191,
                    "power_retention_pct": 98.5,
                    "power_points_count": len(power),
                    "power_data_quality": "available",
                },
            },
        )

    def test_visible_evidence_has_productized_display_fields(self):
        signals = self._signals()
        expected_labels = {
            "intensity_signal": {"本次功率", "相对个人阈值"},
            "aerobic_drift_signal": {"功率心率关系"},
            "power_retention_signal": {"有效踩踏后程"},
            "pacing_signal": {"功率节奏"},
            "cadence_signal": {"踏频节奏"},
        }
        for signal_key, labels in expected_labels.items():
            visible = [
                item for item in signals[signal_key]["evidence"]
                if item.get("visibility") == "visible"
            ]
            self.assertTrue(visible, signal_key)
            for item in visible:
                self.assertIn("label", item)
                self.assertIn("display_value", item)
                self.assertIn("description", item)
                self.assertIn("source", item)
                self.assertIsInstance(item["display_value"], str)
                self.assertNotEqual(item["display_value"].strip(), "")
            self.assertTrue(labels.intersection({item.get("label") for item in visible}), signal_key)

    def test_user_visible_evidence_does_not_expose_internal_or_raw_terms(self):
        signals = self._signals()
        visible_text = []
        for signal in signals.values():
            if not isinstance(signal, dict):
                continue
            for item in signal.get("evidence") or []:
                if item.get("visibility") == "visible":
                    visible_text.extend([
                        str(item.get("label") or ""),
                        str(item.get("display_value") or ""),
                        str(item.get("description") or ""),
                    ])
        encoded = json.dumps(visible_text, ensure_ascii=False)
        for forbidden in (
            "avg_cadence",
            "cadence_cv",
            "decoupling_pct",
            "head_power_per_hr",
            "tail_power_per_hr",
            "intensity_ratio",
            "training_load",
            "pending_algorithm",
            "backend",
            "placeholder",
            "raw",
            "curve",
            "points",
            "records",
            "diff",
            "shadow_diff",
            "TSS",
            "CTL",
            "ATL",
            "TSB",
            "IF",
            "W/kg",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_hidden_evidence_can_keep_machine_fields_without_becoming_visible(self):
        signals = self._signals()
        hidden = [
            item
            for signal in signals.values()
            if isinstance(signal, dict)
            for item in (signal.get("evidence") or [])
            if item.get("visibility") == "hidden"
        ]
        self.assertTrue(hidden)
        self.assertTrue(any(item.get("type") == "power_data_quality" for item in hidden))
        self.assertTrue(all(not str(item.get("display_value") or "").strip() for item in hidden))

    def test_unavailable_power_summary_is_not_visible_key_evidence(self):
        import main

        signals = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "avg_power": 0,
                "max_power": 0,
                "normalized_power": None,
                "duration_sec": 900,
                "power_available": False,
                "cadence_available": False,
                "power_points_count": 0,
                "cadence_points_count": 0,
                "power_data_quality": "missing",
                "cadence_data_quality": "missing",
            },
            curves_snapshot={"power": [], "hr": [90] * 120, "cadence": []},
            profile_ftp_watts=213,
            profile_weight_kg=73.4,
        )
        evidence = signals["intensity_signal"]["evidence"]
        power_summary = [item for item in evidence if item.get("type") == "ride_power_summary"]

        self.assertTrue(power_summary)
        self.assertTrue(all(item.get("visibility") == "hidden" for item in power_summary))
        visible_labels = {
            item.get("label")
            for item in evidence
            if item.get("visibility") == "visible"
        }
        self.assertNotIn("本次功率", visible_labels)

    def test_frontend_prefers_backend_display_fields_without_reconstructing_evidence(self):
        track_html = _read(os.path.join(_PROJECT_ROOT, "track.html"))
        start = track_html.index("function _fatigueReviewCyclingSignalEvidenceItemText(")
        end = track_html.index("function _fatigueReviewCyclingSignalEvidence(", start)
        helper = track_html[start:end]

        for expected in (
            "item.display_value",
            "item.label",
            "item.visibility",
            "return label ? (label + '：' + value) : value;",
        ):
            self.assertIn(expected, helper)
        for forbidden in (
            "summary.avg_power",
            "metrics.",
            "curves.",
            "querySelector",
            "getOption",
            "String(item.type).replace",
        ):
            self.assertNotIn(forbidden, helper)

    def test_load_language_stays_reference_not_training_load_model(self):
        signals = self._signals()
        encoded = json.dumps(signals["intensity_signal"]["evidence"], ensure_ascii=False)
        self.assertIn("相对个人阈值", encoded)
        for forbidden in ("TSS", "CTL", "ATL", "TSB", "IF", "训练负荷模型"):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
