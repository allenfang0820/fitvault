from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
CONTRACT_JSON = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")


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


class TestCyclingFatigueEventsBackendContract(unittest.TestCase):
    def test_cycling_fatigue_zones_are_reference_only_and_do_not_create_power_drop_events(self):
        from main import (
            _build_fatigue_review_collapse_events,
            _filter_trusted_fatigue_zones_for_review,
        )

        zones = _filter_trusted_fatigue_zones_for_review(
            [
                {"start_km": 8.0, "end_km": 16.0, "level": "high"},
            ],
            sport_type="cycling",
            total_distance_m=30000,
        )

        self.assertEqual(len(zones), 1)
        zone = zones[0]
        self.assertEqual(zone["semantic"], "state_change_reference")
        self.assertEqual(zone["interpretation"], "reference_only")
        self.assertEqual(zone["confidence"], "partial")
        self.assertIn("参考区间", zone["description"])

        events = _build_fatigue_review_collapse_events(
            bonk_events=[],
            fatigue_zones=zones,
            sport_type="cycling",
            total_distance_m=30000,
        )
        self.assertEqual(events, [])
        encoded = json.dumps(events, ensure_ascii=False)
        for forbidden in ("功率回落", "后程功率保持下降", "输出崩", "掉功率", "有氧漂移", "心率压力"):
            self.assertNotIn(forbidden, encoded)

    def test_cycling_specific_event_semantics_must_be_explicit_backend_fields(self):
        from main import _build_fatigue_review_collapse_events

        events = _build_fatigue_review_collapse_events(
            bonk_events=[],
            fatigue_zones=[{
                "start_km": 10.0,
                "end_km": 14.0,
                "level": "high",
                "event_semantic": "cadence_interruption",
                "event_title": "踏频中断参考",
                "description": "踏频组织出现中断，需结合地形和停顿判断。",
            }],
            sport_type="cycling",
            total_distance_m=30000,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "cadence_interruption")
        self.assertEqual(events[0]["title"], "踏频中断参考")
        self.assertIn("踏频组织", events[0]["description"])

    def test_unavailable_cycling_signals_do_not_expose_definitive_event_language(self):
        import main

        no_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": False,
                "power_data_quality": "missing",
                "cadence_available": True,
                "cadence_data_quality": "available",
            },
            curves_snapshot={"hr": [130, 132, 134], "cadence": [82, 84, 86]},
        )
        no_hr = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_data_quality": "available",
                "power_points_count": 180,
            },
            curves_snapshot={"power": [180] * 180},
        )
        invalid_power = main._build_cycling_explanation_signals(
            "cycling",
            summary={
                "power_available": True,
                "power_data_quality": "invalid_values",
                "power_points_count": 180,
            },
            curves_snapshot={"hr": [130] * 180, "power": [0] * 180},
        )

        self.assertEqual(no_power["power_retention_signal"]["status"], "unavailable")
        self.assertEqual(no_power["pacing_signal"]["status"], "unavailable")
        self.assertEqual(no_power["aerobic_drift_signal"]["status"], "unavailable")
        self.assertEqual(no_hr["aerobic_drift_signal"]["status"], "unavailable")
        self.assertEqual(invalid_power["power_retention_signal"]["status"], "unavailable")

        encoded = json.dumps([no_power, no_hr, invalid_power], ensure_ascii=False)
        for forbidden in ("后程功率保持下降", "输出崩掉", "功率回落明显", "有氧漂移较明显", "心率压力明显"):
            self.assertNotIn(forbidden, encoded)

    def test_p14_downhill_coasting_dominant_zone_is_filtered(self):
        from main import _calibrate_cycling_fatigue_zones_for_review

        zones = [{
            "start_km": 1.0,
            "end_km": 2.9,
            "level": "high",
        }]
        curves = {
            "distance": [i / 10 for i in range(0, 41)],
            "power": [180] * 10 + [0] * 20 + [160] * 11,
            "speed": [8] * 41,
            "grade": [2] * 10 + [-6] * 20 + [1] * 11,
            "cadence": [85] * 10 + [0] * 20 + [80] * 11,
            "hr": [135] * 41,
        }

        calibrated = _calibrate_cycling_fatigue_zones_for_review(
            zones,
            summary={
                "power_available": True,
                "power_data_quality": "available",
                "cadence_available": True,
                "cadence_data_quality": "available",
            },
            curves_snapshot=curves,
            cycling_explanation_signals={
                "power_retention_signal": {"status": "available"},
                "aerobic_drift_signal": {"status": "available"},
                "cadence_signal": {"status": "available"},
            },
        )

        self.assertEqual(calibrated, [])

    def test_p14_invalid_power_or_missing_hr_zone_stays_reference_only(self):
        from main import _calibrate_cycling_fatigue_zones_for_review

        calibrated = _calibrate_cycling_fatigue_zones_for_review(
            [{"start_km": 2.0, "end_km": 5.0, "level": "high"}],
            summary={
                "power_available": True,
                "power_data_quality": "invalid_values",
                "cadence_available": False,
                "cadence_data_quality": "missing",
            },
            curves_snapshot={
                "distance": [i / 10 for i in range(0, 71)],
                "power": [0] * 71,
                "speed": [7] * 71,
                "grade": [1] * 71,
                "cadence": [],
                "hr": [],
            },
            cycling_explanation_signals={
                "power_retention_signal": {"status": "unavailable"},
                "aerobic_drift_signal": {"status": "unavailable"},
                "cadence_signal": {"status": "unavailable"},
            },
        )

        self.assertEqual(len(calibrated), 1)
        zone = calibrated[0]
        self.assertEqual(zone["semantic"], "state_change_reference")
        self.assertEqual(zone["interpretation"], "reference_only")
        self.assertEqual(zone["confidence"], "partial")
        self.assertEqual(zone["calibration"], "p14_cycling_reference_zone")
        self.assertIn("不能判断功率回落", zone["description"])
        self.assertIn("不能判断有氧漂移或心率压力", zone["description"])
        self.assertIn("不判断踩踏组织中断", zone["description"])
        encoded = json.dumps(zone, ensure_ascii=False)
        for forbidden in ("后程功率保持下降", "输出崩掉", "功率回落明显", "有氧漂移较明显", "心率压力明显"):
            self.assertNotIn(forbidden, encoded)

    def test_p14_available_signals_still_keep_zone_as_reference_interval(self):
        from main import _calibrate_cycling_fatigue_zones_for_review

        calibrated = _calibrate_cycling_fatigue_zones_for_review(
            [{"start_km": 2.0, "end_km": 5.0, "level": "medium"}],
            summary={
                "power_available": True,
                "power_data_quality": "available",
                "cadence_available": True,
                "cadence_data_quality": "available",
            },
            curves_snapshot={
                "distance": [i / 10 for i in range(0, 71)],
                "power": [180] * 71,
                "speed": [7] * 71,
                "grade": [1] * 71,
                "cadence": [86] * 71,
                "hr": [138] * 71,
            },
            cycling_explanation_signals={
                "power_retention_signal": {"status": "available"},
                "aerobic_drift_signal": {"status": "available"},
                "cadence_signal": {"status": "available"},
            },
        )

        self.assertEqual(len(calibrated), 1)
        zone = calibrated[0]
        self.assertEqual(zone["semantic"], "state_change_reference")
        self.assertEqual(zone["interpretation"], "reference_only")
        self.assertIn("专项解释以可用的骑行解释信号为准", zone["description"])
        self.assertIn("power_signal_available", zone["reasons"])


class TestCyclingFatigueEventsFrontendContract(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_cycling_zone_copy_uses_reference_language_not_fatigue_conclusions(self):
        for text in [
            "参考区间：这段状态变化较明显，需结合功率、踏频、心率和地形判断。",
            "参考区间：这段状态变化更集中，不直接等同于输出下降或体能下降。",
            "参考区间：当前无法可靠区分体能、滑行、停顿或地形影响。",
            "function _fatigueReviewCyclingZoneSummaryTitle(zone, totalDistanceKm)",
            "不能单独判断为后程功率保持下降",
        ]:
            self.assertIn(text, self.html)

        cycling_copy_start = self.html.find("cycling: '参考区间：这段状态变化较明显")
        cycling_copy_body = self.html[cycling_copy_start:cycling_copy_start + 2600]
        for forbidden in ("后程功率保持下降", "输出崩掉", "有氧漂移", "心率压力明显"):
            self.assertNotIn(forbidden, cycling_copy_body)

    def test_p15_cycling_event_copy_has_productized_semantics(self):
        for text in [
            "power_drop",
            "cadence_interruption",
            "hr_power_decoupling",
            "non_fitness_event",
            "data_insufficient",
            "有效踩踏输出回落参考",
            "踩踏节奏被打断",
            "功率和心率关系变化",
            "路线或停顿影响参考",
            "数据不足参考点",
            "不要直接解读为体能下降",
            "暂不判断功率回落、心率压力或踩踏组织问题",
        ]:
            self.assertIn(text, self.html)

        event_copy_start = self.html.find("var FATIGUE_REVIEW_EVENT_COPY = {")
        event_copy_end = self.html.find("var FATIGUE_REVIEW_SUSTAINED_ZONE_COPY", event_copy_start)
        event_copy_body = self.html[event_copy_start:event_copy_end]
        for forbidden in (
            "撞墙已经发生",
            "输出崩掉",
            "体能崩掉",
            "后程功率保持下降",
            "Pw:Hr",
            "IF",
            "TSS",
            "W/kg",
            "齿比",
            "扭矩",
            "左右平衡",
            "踩踏技术",
        ):
            self.assertNotIn(forbidden, event_copy_body)

    def test_p15_event_kind_uses_backend_semantics_before_regex_fallbacks(self):
        body = _extract_js_function(self.html, "_fatigueReviewEventKind")
        self.assertTrue(body)
        self.assertIn("ev.semantic", body)
        self.assertIn("ev.event_semantic", body)
        self.assertIn("ev.reason_code", body)
        self.assertIn("power_drop|cadence_interruption|hr_power_decoupling|non_fitness_event|data_insufficient", body)
        self.assertLess(body.find("ev.semantic"), body.find("bonk|energy"))

    def test_p15_cycling_zone_summary_copy_rewrites_backend_reference_fields(self):
        for text in [
            "function _fatigueReviewCyclingZoneSummaryDesc(zone, totalDistanceKm)",
            "本次存在较长状态变化参考区间",
            "数据依据不足",
            "不判断有效踩踏输出回落",
            "心率依据不足",
            "踏频依据不足",
            "具体原因以功率保持、心率反应和踏频节奏卡片为准",
            "整体参考区间",
        ]:
            self.assertIn(text, self.html)

    def test_events_and_zones_render_only_backend_event_and_zone_fields(self):
        for name in (
            "_fatigueReviewEventKind",
            "_fatigueReviewCyclingZoneSummaryDesc",
            "_renderFatigueReviewEvents",
            "_renderFatigueReviewZones",
            "_renderFatigueReviewStageOverview",
        ):
            body = _extract_js_function(self.html, name)
            self.assertTrue(body, name)
            for forbidden in (
                "data.curves",
                "curves.",
                "points",
                "querySelector",
                "getOption",
                "echarts.getInstance",
                "innerText",
                "getBoundingClientRect",
            ):
                self.assertNotIn(forbidden, body, name + ":" + forbidden)

        self.assertIn("_renderFatigueReviewEvents(data.collapse_events || [], data.sport_type, hasSustainedZone)", self.html)
        self.assertIn("_renderFatigueReviewZones(data.fatigue_zones || [], data.sport_type, reviewTotalDistanceKm, data.metrics || {}, data.collapse_events || [])", self.html)

    def test_contract_documents_cycling_event_and_zone_degradation_boundary(self):
        contract = _read(CONTRACT_JSON)
        for text in [
            "P13 骑行事件与疲劳带契约",
            "fatigue_zones 是压力/状态变化参考区间",
            "collapse_events 必须区分功率回落、踏频中断、心率-功率关系变化、滑行/停顿/下坡导致的非体能事件、数据不足",
            "power_data_quality != available 时不得输出功率回落、后程功率保持下降或输出崩掉等确定性事件文案",
            "无心率时不得输出有氧漂移或心率压力确定性事件文案",
            "partial 只能参考，unavailable 必须温和降级",
        ]:
            self.assertIn(text, contract)
