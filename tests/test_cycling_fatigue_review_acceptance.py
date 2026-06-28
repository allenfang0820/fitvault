from __future__ import annotations

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_js_function(source: str, name: str) -> str:
    marker = "function " + name + "("
    start = source.find(marker)
    if start < 0:
        return ""
    end = source.find("\n    function ", start + len(marker))
    if end < 0:
        end = source.find("\n    async function ", start + len(marker))
    if end < 0:
        end = start + 5000
    return source[start:end]


class TestCyclingFatigueReviewAcceptanceBackend(unittest.TestCase):
    def _summary(self, **overrides):
        base = {
            "avg_power": 220,
            "normalized_power": 242,
            "avg_cadence": 86,
            "power_points_count": 180,
            "cadence_points_count": 180,
            "power_data_quality": "available",
            "cadence_data_quality": "available",
        }
        base.update(overrides)
        return base

    def test_power_and_cadence_cycling_payload_is_complete(self):
        import main

        metrics = main._build_cycling_review_metrics(
            "road_cycling",
            self._summary(),
            {
                "power": [230] * 90 + [218] * 90,
                "cadence": [86, 87, 85, 86, 88] * 36,
            },
            avg_hr=150,
        )

        self.assertEqual(metrics["power_variability"]["vi"], 1.10)
        self.assertNotEqual(metrics["power_variability"]["confidence"], "unavailable")
        self.assertIsNotNone(metrics["pedaling_stability"]["score"])
        self.assertEqual(metrics["efficiency"]["basis"], "power_hr")
        self.assertEqual(metrics["efficiency"]["power_per_hr"], 1.467)
        self.assertEqual(metrics["durability"]["basis"], "power_retention")
        self.assertEqual(metrics["durability"]["power_retention_pct"], 94.8)
        self.assertEqual(metrics["durability"]["head_speed"], None)
        self.assertEqual(metrics["durability"]["tail_speed"], None)

    def test_no_power_cycling_degrades_without_complete_power_claims(self):
        import main

        metrics = main._build_cycling_review_metrics(
            "cycling",
            self._summary(
                avg_power=None,
                normalized_power=None,
                power_points_count=0,
                power_data_quality="missing",
            ),
            {
                "power": [],
                "cadence": [86, 87, 85, 86, 88] * 36,
            },
            avg_hr=148,
        )

        self.assertIsNone(metrics["power_variability"]["vi"])
        self.assertEqual(metrics["power_variability"]["confidence"], "unavailable")
        self.assertIsNone(metrics["efficiency"]["power_per_hr"])
        self.assertEqual(metrics["efficiency"]["confidence"], "unavailable")
        self.assertEqual(metrics["efficiency"]["basis"], "power_hr")
        self.assertIsNone(metrics["durability"]["power_retention_pct"])
        self.assertEqual(metrics["durability"]["confidence"], "unavailable")
        self.assertEqual(metrics["durability"]["basis"], "power_retention")
        self.assertIn("power data unavailable: missing", metrics["durability"]["reasons"])

    def test_insufficient_power_does_not_fallback_to_speed_durability(self):
        import main

        metrics = main._build_cycling_review_metrics(
            "mountain_biking",
            self._summary(
                power_points_count=10,
                power_data_quality="insufficient_points",
            ),
            {
                "power": [220] * 10,
                "cadence": [80, 82, 81, 83, 80] * 36,
            },
            avg_hr=152,
        )

        self.assertIsNone(metrics["durability"]["power_retention_pct"])
        self.assertIsNone(metrics["durability"]["head_speed"])
        self.assertIsNone(metrics["durability"]["tail_speed"])
        self.assertEqual(metrics["durability"]["basis"], "power_retention")
        self.assertEqual(metrics["durability"]["confidence"], "unavailable")
        self.assertIn("power data unavailable: insufficient_points", metrics["durability"]["reasons"])

    def test_non_cycling_does_not_receive_power_efficiency_or_retention(self):
        import main

        metrics = main._build_cycling_review_metrics(
            "running",
            self._summary(),
            {
                "power": [230] * 90 + [218] * 90,
                "cadence": [86, 87, 85, 86, 88] * 36,
            },
            avg_hr=150,
        )

        self.assertNotIn("efficiency", metrics)
        self.assertNotIn("durability", metrics)
        self.assertIsNone(metrics["power_variability"]["vi"])
        self.assertEqual(metrics["power_variability"]["confidence"], "unavailable")


class TestCyclingFatigueReviewAcceptanceFrontend(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_cycling_cards_and_chart_are_distinct_from_running(self):
        card_defs = _extract_js_function(self.html, "_fatigueReviewMetricCardDefs")
        lane_defs = _extract_js_function(self.html, "_fatigueReviewChartLaneDefs")

        cycling_cards_start = card_defs.find("if (sportMode === 'cycling')")
        cycling_cards_end = card_defs.find("\n        return [", cycling_cards_start + 1)
        cycling_cards = card_defs[cycling_cards_start:cycling_cards_end]
        for text in (
            "withSlot('hr_drift', 'power_variability', '输出节奏'",
            "withSlot('decoupling', 'efficiency', '功率效率'",
            "withSlot('bonk_risk', 'durability', '后程功率保持'",
            "withSlot('events', 'events', '状态下滑点'",
            "withSlot('efficiency', 'hr_drift', '心肺对照'",
            "withSlot('durability', 'pedaling_stability', '踩踏组织'",
            "withSlot('cadence_stability', 'training_load', '相对强度'",
            "withSlot('training_load', 'bonk_risk', '能量风险'",
        ):
            self.assertIn(text, cycling_cards)
        for forbidden in (
            "步频稳定性",
            "'心率漂移'",
            "'踏频稳定性'",
            "'训练负荷'",
            "后程保持参考",
            "当前不等同于 power-based durability",
        ):
            self.assertNotIn(forbidden, cycling_cards)

        cycling_chart_start = lane_defs.find("if (sportMode === 'cycling')")
        cycling_chart_end = lane_defs.find("\n        return [", cycling_chart_start + 1)
        cycling_chart = lane_defs[cycling_chart_start:cycling_chart_end]
        for text in (
            "key: 'power_curve'",
            "name: '功率'",
            "key: 'hr_curve'",
            "key: 'altitude_curve'",
            "key: 'cadence_curve'",
            "name: '踏频'",
        ):
            self.assertIn(text, cycling_chart)
        for forbidden in (
            "key: 'pace_curve'",
            "key: 'gap_pace_curve'",
            "key: 'efficiency_curve'",
        ):
            self.assertNotIn(forbidden, cycling_chart)

    def test_cycling_render_reads_only_backend_metric_fields(self):
        render_body = _extract_js_function(self.html, "_renderFatigueReviewMetrics")

        for text in (
            "var effCycling = metrics.efficiency || {}",
            "effCycling.basis !== 'power_hr'",
            "effCycling.power_per_hr",
            "_fatigueReviewPowerEfficiencyEvidence(effCycling, effMissingCycling)",
            "var durCycling = metrics.durability || {}",
            "durCycling.basis !== 'power_retention'",
            "durCycling.power_retention_pct",
            "_fatigueReviewPowerRetentionEvidence(durCycling, durMissingCycling)",
        ):
            self.assertIn(text, render_body)
        for forbidden in (
            "summary.",
            "curves.",
            "chartPayload",
            "getOption",
            "querySelector",
            "innerText",
            "avg_power / avg_hr",
            "tail_power / head_power",
            "normalized_power / avg_power",
            "power_per_hr =",
            "power_retention_pct =",
        ):
            self.assertNotIn(forbidden, render_body)

    def test_running_cards_keep_general_semantics(self):
        card_defs = _extract_js_function(self.html, "_fatigueReviewMetricCardDefs")
        running_start = card_defs.find("\n        return [")
        running_cards = card_defs[running_start:]

        for text in (
            "withSlot('efficiency', 'efficiency', '运动效率'",
            "withSlot('durability', 'durability', '耐久指数'",
            "withSlot('cadence_stability', 'cadence_stability', '步频稳定性'",
        ):
            self.assertIn(text, running_cards)
        for forbidden in (
            "功率效率",
            "后程功率保持",
            "withSlot('hr_drift', 'power_variability'",
            "withSlot('bonk_risk', 'pedaling_stability'",
        ):
            self.assertNotIn(forbidden, running_cards)


if __name__ == "__main__":
    unittest.main()
