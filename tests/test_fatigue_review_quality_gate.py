from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
MAIN_PY = os.path.join(_PROJECT_ROOT, "main.py")
LLM_BACKEND_PY = os.path.join(_PROJECT_ROOT, "llm_backend.py")
PLAN_MD = os.path.join(_PROJECT_ROOT, "docs", "fatigue_review_realignment_plan_v1.md")
P7_IA_MD = os.path.join(_PROJECT_ROOT, "docs", "p7_fatigue_review_analysis_cockpit_information_architecture.md")


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


class TestP5FrontendZeroInferenceGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_no_frontend_distance_axis_rebuilder_exists(self):
        forbidden = (
            "_distanceFromSpeedTime",
            "validSpeedSum",
            "speed[m] || 0) / validSpeedSum",
            "speed[i] || 0) * 1.0",
            "p / n * totalKm",
            "appState.points",
        )
        review_slice = self.html[self.html.find("async function openFatigueReview("):]
        for token in forbidden:
            self.assertNotIn(token, review_slice, token)

    def test_open_fatigue_review_distance_axis_only_from_backend_curve(self):
        body = _extract_js_function(self.html, "openFatigueReview")
        self.assertIn(
            "distance_curve: Array.isArray(curvesObj.distance) ? curvesObj.distance : []",
            body,
        )
        self.assertNotIn("total_distance_m", body)
        self.assertNotIn("speed_curve", body.split("distance_curve:", 1)[0])

    def test_chart_empty_state_when_backend_distance_axis_missing(self):
        body = _extract_js_function(self.html, "renderProfileAnalysisChart")
        self.assertIn("distanceCurve.length < 2", body)
        self.assertIn("距离轴暂不可用", body)


class TestP5SnapshotWhitelistGate(unittest.TestCase):
    TOP_LEVEL_KEYS = {
        "sport_type",
        "metrics",
        "collapse_events",
        "fatigue_zones",
        "curves",
        "display_curves",
        "display_meta",
        "context_tags",
        "ai_insight",
        "advice",
        "disclaimer",
    }
    CURVE_KEYS = {
        "distance",
        "time",
        "hr",
        "speed",
        "altitude",
        "grade",
        "gap",
        "efficiency",
        "terrain_load",
        "total_distance_m",
    }
    DISPLAY_CURVE_KEYS = {
        "pace_sec_per_km",
        "pace_raw_sec_per_km",
        "pace_capped",
        "gap_pace_sec_per_km",
        "gap_pace_raw_sec_per_km",
        "gap_pace_capped",
    }
    FORBIDDEN_KEYS = {
        "shadow_diff",
        "shadow_diff_json",
        "diff",
        "records",
        "points",
        "raw_records",
        "track_points",
    }

    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_historical_metrics_avg = MagicMock(return_value={
            "sample_size": 0,
            "hr_drift_pct": None,
            "decoupling_pct": None,
            "bonk_count": 0,
        })
        for name, value in {
            "_fetch_efficiency_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_durability_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_cadence_stability_trend": {"level": "flat", "compared_count": 0, "baseline_cv": None},
            "_fetch_training_load_trend": {"level": "flat", "compared_count": 0, "baseline_load": None},
            "_fetch_load_ratio_7d_42d": {
                "ratio": None, "level": "unknown", "acute_7d": None,
                "chronic_42d": None, "compared_count": 0,
            },
        }.items():
            setattr(api, name, MagicMock(return_value=value))
        return api

    def _row(self) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(50):
            points.append({
                "lat": 31.0 + i * 0.0001,
                "lon": 121.0,
                "time": (base + timedelta(seconds=i * 15)).isoformat(),
                "hr": 135 + min(i, 30),
                "speed": 3.0,
                "alt": 100 + i,
                "cadence": 84,
            })
        return {
            "id": 7,
            "sport_type": "running",
            "dist_km": 5.0,
            "distance": 5000.0,
            "duration_sec": 750,
            "calories": 800,
            "track_json": json.dumps(points),
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": json.dumps([p["speed"] for p in points]),
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
        }

    def test_snapshot_top_level_and_curves_whitelist(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        self.assertEqual(set(snapshot.keys()), self.TOP_LEVEL_KEYS)
        self.assertEqual(set(snapshot["curves"].keys()), self.CURVE_KEYS)
        self.assertEqual(set(snapshot["display_curves"].keys()), self.DISPLAY_CURVE_KEYS)
        self.assertIn("pace_display_cap_sec_per_km", snapshot["display_meta"])

    def test_snapshot_forbidden_keys_absent_recursively(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for key in self.FORBIDDEN_KEYS:
            self.assertNotIn('"' + key + '"', encoded)

    def test_non_empty_drawable_curves_align_to_distance_axis(self):
        curves = self._api()._build_fatigue_review_snapshot(self._row())["curves"]
        axis_len = len(curves["distance"])
        self.assertGreater(axis_len, 0)
        for key in ("time", "hr", "speed", "altitude", "grade", "gap", "efficiency", "terrain_load"):
            if curves[key]:
                self.assertEqual(len(curves[key]), axis_len, key)

    def test_display_pace_curves_are_backend_generated_and_capped(self):
        row = self._row()
        points = json.loads(row["track_json"])
        points[10]["speed"] = 0.2
        row["track_json"] = json.dumps(points)
        snapshot = self._api()._build_fatigue_review_snapshot(row)
        display_curves = snapshot["display_curves"]
        axis_len = len(snapshot["curves"]["distance"])
        self.assertEqual(len(display_curves["pace_sec_per_km"]), axis_len)
        self.assertEqual(len(display_curves["pace_raw_sec_per_km"]), axis_len)
        self.assertEqual(len(display_curves["pace_capped"]), axis_len)
        self.assertEqual(snapshot["display_meta"]["pace_display_cap_sec_per_km"], 900)
        self.assertEqual(display_curves["pace_sec_per_km"][10], 900)
        self.assertGreater(display_curves["pace_raw_sec_per_km"][10], 900)
        self.assertTrue(display_curves["pace_capped"][10])

    def test_zone_and_event_coordinates_are_backend_numbers(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        for zone in snapshot["fatigue_zones"]:
            self.assertIsInstance(zone.get("start_km"), (int, float))
            self.assertIsInstance(zone.get("end_km"), (int, float))
        for event in snapshot["collapse_events"]:
            trigger_km = event.get("trigger_km")
            self.assertTrue(trigger_km is None or isinstance(trigger_km, (int, float)))

    def test_fatigue_zones_create_backend_event_anchors(self):
        from main import _build_fatigue_review_collapse_events

        events = _build_fatigue_review_collapse_events(
            bonk_events=[],
            fatigue_zones=[
                {"start_km": 0.0, "end_km": 0.2, "level": "medium"},
                {"start_km": 0.2, "end_km": 1.6, "level": "high"},
                {"start_km": 3.6, "end_km": 4.5, "level": "high"},
            ],
        )
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0]["type"], "FATIGUE_DRIFT_START")
        self.assertEqual(events[0]["title"], "漂移开始")
        self.assertGreater(events[0]["trigger_km"], 0)
        self.assertIn("title", events[1])
        self.assertIn("label", events[1])
        self.assertIn("description", events[1])
        self.assertTrue(all(ev["event_id"].startswith("ce_") for ev in events))


class TestP5P4UiStructureGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_p4_review_structure_is_preserved(self):
        for element_id in (
            "fr-review-layout",
            "fr-status-strip",
            "fr-summary-desc",
            "fr-curve-status-pill",
            "fr-risk-pill",
            "fr-ai-status-pill",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-stage-overview-section",
            "fr-stage-boundary",
            "fr-stage-track",
            "fr-chart-section",
            "fr-chart-title",
            "fr-chart-subtitle",
            "fr-chart-boundary",
            "fr-chart-legend",
            "fr-chart-axis-note",
            "fr-context-panel",
            "fr-context-boundary",
            "fr-side-summary-panel",
            "fr-side-summary-boundary",
            "fr-side-summary-list",
            "fr-events-panel",
            "fr-events-boundary",
            "fr-phys-impact-panel",
            "fr-phys-impact-boundary",
            "fr-phys-impact-list",
            "fr-fatigue-zones-panel",
            "fr-fatigue-zones-boundary",
            "fr-fatigue-zone-list",
            "fr-advice-panel",
            "fr-advice-boundary",
            "fr-advice-status",
            "fatigue-review-chart",
        ):
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_4_chart_boundary_copy_is_preserved(self):
        for text in (
            "按距离展开本次活动的关键变化",
            "心率、配速、海拔和疲劳阶段会在同一条距离轴上对照显示。",
            "距离轴等待加载",
        ):
            self.assertIn(text, self.html)

    def test_p7_10_layered_echarts_is_preserved(self):
        self.assertIn("多维时间轴分析", self.html)
        self.assertIn("function _renderFatigueReviewLayeredEcharts(activityData, targetId, distanceCurve)", self.html)
        self.assertIn("if (targetId === 'fatigue-review-chart')", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        for text in (
            "var grid = []",
            "var xAxis = []",
            "var yAxis = []",
            "hr_curve",
            "pace_curve",
            "altitude_curve",
            "efficiency_curve",
            "gap_pace_curve",
            "grade_curve",
            "terrain_load_curve",
            "_frLayeredMarkArea(fatigueZones)",
            "_frLayeredEventMarkLine(insightEvents)",
            "markArea: { silent: true, data: markAreaData }",
            "markLine:",
            "axisPointer: { link: [{ xAxisIndex: 'all' }] }",
            "grid: grid",
            "xAxis: xAxis",
            "yAxis: yAxis",
        ):
            self.assertIn(text, fn_body)
        for token in (
            "_distanceFromSpeedTime",
            "total_distance_m",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "call_llm",
        ):
            self.assertNotIn(token, fn_body)

    def test_p7_5_event_and_zone_boundaries_are_preserved(self):
        for text in (
            "标记活动中值得回看的关键变化点。",
            "展示疲劳出现、加重或缓解的距离区间。",
            "_renderFatigueReviewEvents(data.collapse_events || [])",
            "_renderFatigueReviewZones(data.fatigue_zones || [])",
        ):
            self.assertIn(text, self.html)

    def test_p7_6_context_advice_boundaries_are_preserved(self):
        for text in (
            "环境、装备和训练背景会帮助解释本次表现。",
            "结合本次复盘给出下一步训练建议。",
            "_renderFatigueReviewContextTags(data.context_tags || {})",
            "_renderFatigueReviewAdvice(data.advice, data.disclaimer)",
            "暂时没有可展示的训练建议。",
        ):
            self.assertIn(text, self.html)

    def test_p7_7_responsive_readability_css_is_preserved(self):
        for text in (
            "@media (max-width: 1100px)",
            "@media (max-width: 720px)",
            "@media (max-width: 480px)",
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "min-height: 280px",
            "overflow-wrap: anywhere",
            "flex-wrap: wrap",
        ):
            self.assertIn(text, self.html)

    def test_p7_7_no_viewport_font_or_negative_letter_spacing(self):
        self.assertNotRegex(self.html, r"font-size\s*:\s*[^;]*vw")
        self.assertNotRegex(self.html, r"letter-spacing\s*:\s*-\s*")

    def test_p7_8_visual_regression_cockpit_order_is_preserved(self):
        ordered_ids = (
            "detail-tab-review",
            "fr-status-strip",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-chart-section",
            "fr-context-panel",
            "fr-events-panel",
            "fr-fatigue-zones-panel",
            "fr-advice-panel",
        )
        positions = []
        for element_id in ordered_ids:
            pos = self.html.find('id="' + element_id + '"')
            self.assertGreater(pos, 0, element_id)
            positions.append(pos)
        self.assertEqual(positions, sorted(positions))

    def test_p7_8_visual_regression_freezes_sketch_scope_and_ai_entry(self):
        review_idx = self.html.find('id="detail-tab-review"')
        upload_idx = self.html.find('id="file-upload"', review_idx)
        review_body = self.html[review_idx:upload_idx if upload_idx > review_idx else review_idx + 16000]
        for token in ("首页", "日历", "分享", "导出"):
            self.assertNotIn(token, review_body)
        self.assertNotIn(">活动<", review_body)
        button_idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(button_idx, 0)
        start = self.html.rfind("<button", 0, button_idx)
        end = self.html.find("</button>", button_idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertNotIn("onclick=", button)

    def test_p7_9_design_correction_plan_is_preserved(self):
        plan = _read(PLAN_MD)
        ia = _read(P7_IA_MD)
        for text in (
            "P7 后续任务纠偏提示",
            "身体状态如何变化",
            "为什么失衡",
            "在哪里开始崩",
            "什么因素导致崩溃",
            "Layer 1 疲劳带",
            "Layer 2 事件标记",
            "Layer 3 派生指标曲线",
            "P7.10 | 分层 ECharts 主图实现",
            "P7.11 | 状态阶段与派生指标模块回正",
            "P7.12 | 主图信息架构纠偏",
            "P7.13 | 左侧指标轨道与分层泳道回正",
            "P7.14 | 关键事件图钉与竖向参考线",
            "P7.18 | 视觉回归与草图对照验收",
            "P8 | UI 定稿后 AI 入口复核",
        ):
            self.assertIn(text, plan + ia)
        self.assertIn("当前叠加式 ECharts 主图不是设计稿完成态", plan + ia)

    def test_p7_11_stage_overview_and_derived_strip_are_preserved(self):
        for element_id in (
            "fr-stage-overview-section",
            "fr-stage-boundary",
            "fr-stage-track",
        ):
            self.assertIn('id="' + element_id + '"', self.html)
        self.assertIn("fr-derived-metrics-strip", self.html)
        self.assertIn("_renderFatigueReviewStageOverview(data.fatigue_zones || [])", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewContextTags", fn_idx)]
        for text in (
            "zone.start_km",
            "zone.end_km",
            "zone.level",
            "zone.reason || zone.description",
            "fr-stage-segment",
            "暂无阶段",
        ):
            self.assertIn(text, fn_body)
        for token in (
            "curves.",
            "speed",
            "time",
            "total_distance_m",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "call_llm",
        ):
            self.assertNotIn(token, fn_body)

    def test_p7_12_chart_architecture_correction_is_preserved(self):
        for text in (
            "grid-template-columns: minmax(0, 1fr) 260px",
            "min-height: 640px",
            "#fatigue-review-chart.fr-chart-canvas",
            "min-height: 360px",
            "var computedHeight = Math.max(420, Math.min(760, lanes.length * lanePx + 72))",
            "topStart = 6",
            "bottomPad = 7",
            ".fr-stage-track .fr-empty-state",
            "fr-stage-overview .fr-panel-boundary",
            "display: none",
        ):
            self.assertIn(text, self.html)
        chart_idx = self.html.find('id="fr-chart-section"')
        stage_idx = self.html.find('id="fr-stage-overview-section"')
        canvas_idx = self.html.find('id="fatigue-review-chart"')
        self.assertGreater(chart_idx, 0)
        self.assertGreater(stage_idx, chart_idx)
        self.assertGreater(canvas_idx, stage_idx)

    def test_p7_13_lane_rail_is_preserved(self):
        for text in (
            'id="fr-chart-body"',
            'id="fr-lane-rail"',
            "function _renderFatigueReviewLaneRail(lanes)",
            "fr-lane-rail-item",
            "fr-lane-rail-name",
            "fr-lane-rail-unit",
            "data-fr-lane-key",
            "lane.layout.top",
            "lane.layout.height",
            "_renderFatigueReviewLaneRail(lanes)",
            "_renderFatigueReviewLaneRail([])",
            "--fr-chart-height: 360px",
            "chartBodyEl.style.setProperty('--fr-chart-height', computedHeight + 'px')",
            "grid-template-columns: 132px minmax(0, 1fr)",
            "#fr-chart-section.chart-container",
            "flex: 0 0 auto",
            "min-height: auto",
            "position: relative",
            "position: absolute",
            "flex: 0 0 var(--fr-chart-height)",
            "height: var(--fr-chart-height)",
            "justify-content: center",
            "text-align: center",
        ):
            self.assertIn(text, self.html)
        rail_fn_idx = self.html.find("function _renderFatigueReviewLaneRail(lanes)")
        self.assertGreater(rail_fn_idx, 0)
        rail_fn = self.html[rail_fn_idx:self.html.find("\n    function _renderFatigueReviewLayeredEcharts", rail_fn_idx)]
        for text in (
            "lane.color",
            "lane.name",
            "lane.unit",
        ):
            self.assertIn(text, rail_fn)
        for forbidden in (
            "fr-lane-rail-index",
            "index + 1",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "total_distance_m",
            "points",
            "call_llm",
        ):
            self.assertNotIn(forbidden, rail_fn)

    def test_p7_15_stage_bar_visual_realignment_is_preserved(self):
        for text in (
            "--fr-stage-grow",
            "--fr-stage-basis",
            "fr-stage-share",
            ".fr-stage-segment.compact",
            "flex: var(--fr-stage-grow, 1) 1 var(--fr-stage-basis, 0)",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewContextTags", fn_idx)]
        for text in (
            "var stageItems = []",
            "zone.start_km",
            "zone.end_km",
            "zone.level",
            "zone.reason || zone.description",
            "item.span / fullSpan * 100",
            "Math.max(7, item.span / fullSpan * 100)",
            "暂无有效阶段",
            "compact",
        ):
            self.assertIn(text, fn_body)
        for forbidden in (
            "curves.",
            "speed",
            "time",
            "total_distance_m",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "call_llm",
        ):
            self.assertNotIn(forbidden, fn_body)

    def test_p7_14_event_pins_and_reference_lines_are_preserved(self):
        for text in (
            "function _frLayeredEventMarkLine(insightEvents)",
            "function _frLayeredEventPinMarkLine(insightEvents)",
            "function _frLayeredEventTitle(event)",
            "function _frLayeredEventKmLabel(triggerKm)",
            "var eventReferenceLineData = _frLayeredEventMarkLine(insightEvents)",
            "var eventPinLineData = _frLayeredEventPinMarkLine(insightEvents)",
            "data: eventReferenceLineData",
            "data: eventPinLineData",
            "symbol: ['none', 'pin']",
            "symbolSize: [24, 24]",
            "position: 'end'",
            "eventTitle",
            "eventKmLabel",
            "trigger_km",
        ):
            self.assertIn(text, self.html)
        event_fn = _extract_js_function(self.html, "_frLayeredEventMarkLine")
        pin_fn = _extract_js_function(self.html, "_frLayeredEventPinMarkLine")
        for text in (
            "event.trigger_km",
            "event.title || event.label || event.type || event.event_id || '关键事件'",
            "event.event_id",
            "event.description",
        ):
            self.assertIn(text, self.html)
        for forbidden in (
            "curves.",
            "speed",
            "time",
            "total_distance_m",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "call_llm",
        ):
            self.assertNotIn(forbidden, event_fn + pin_fn)

    def test_p7_16a_terrain_load_bar_lane_is_preserved(self):
        for text in (
            "地形负荷",
            "terrain_load_curve:data.curves && data.curves.terrain_load",
            "terrain_load_curve",
            "name: '地形负荷'",
            "unit: 'grade×speed×s'",
            "seriesType: 'bar'",
            "type: 'bar'",
            "barWidth: 4",
            "暂无可用曲线",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        for forbidden in (
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "call_llm",
        ):
            self.assertNotIn(forbidden, fn_body)

    def test_p7_16b_terrain_load_discrete_gradient_bars_are_preserved(self):
        for text in (
            "function _frDownsampleTerrainLoadBars(distanceCurve, terrainLoadCurve)",
            "Display-only aggregation: equal-distance bins keep bars visually uniform.",
            "_frPairDistanceCurve(distanceCurve, terrainLoadCurve)",
            "var targetBars = Math.min(128, Math.max(96, Math.round(rangeKm * 18)))",
            "var bucketWidthKm = rangeKm / targetBars",
            "var bucketCenter = bucketStart + bucketWidthKm / 2",
            "var terrainBarData = _frDownsampleTerrainLoadBars(",
            "activityData && activityData.terrain_load_curve",
            "data: terrainBarData",
            "barGap: '45%'",
            "barCategoryGap: '38%'",
            "new echarts.graphic.LinearGradient(0, 0, 0, 1",
            "{ offset: 0, color: '#064e3b' }",
            "{ offset: 0.42, color: '#0f766e' }",
            "{ offset: 1, color: '#99f6e4' }",
            "opacity: 0.96",
        ):
            self.assertIn(text, self.html)
        helper = _extract_js_function(self.html, "_frDownsampleTerrainLoadBars")
        for forbidden in (
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "points",
            "training_load",
            "call_llm",
        ):
            self.assertNotIn(forbidden, helper)

    def test_p7_16_side_summary_panel_is_preserved(self):
        for text in (
            'id="fr-side-summary-panel"',
            'id="fr-side-summary-boundary"',
            'id="fr-side-summary-list"',
            'id="fr-phys-impact-panel"',
            'id="fr-phys-impact-boundary"',
            'id="fr-phys-impact-list"',
            "关键摘要",
            "崩溃触发因素",
            "生理冲击点",
            "快速查看风险状态、触发因素和疲劳路段。",
            "用几个核心指标概括本次训练对身体的影响。",
            "function _renderFatigueReviewSideSummary(data)",
            "_renderFatigueReviewSideSummary(data)",
            "_renderFatigueReviewSideSummary({})",
            "var metrics = data.metrics || {}",
            "var collapseEvents = Array.isArray(data.collapse_events) ? data.collapse_events : []",
            "var fatigueZones = Array.isArray(data.fatigue_zones) ? data.fatigue_zones : []",
            "var contextTags = data.context_tags || {}",
            "var adviceText = data.advice == null ? '' : String(data.advice).trim()",
            "data.disclaimer ? '含注意事项' : '暂无额外注意事项'",
        ):
            self.assertIn(text, self.html)
        helper = _extract_js_function(self.html, "_renderFatigueReviewSideSummary")
        for forbidden in (
            "curves.",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "points",
            "call_llm",
            "training_load_curve",
            "terrain_load_curve",
        ):
            self.assertNotIn(forbidden, helper)

    def test_p7_17_chart_footer_controls_are_preserved(self):
        for text in (
            'id="fr-chart-footer"',
            'id="fr-layer-toggle-row"',
            'id="fr-layer-chip-row"',
            'data-fr-layer-toggle="hr"',
            'data-fr-layer-toggle="speed"',
            'data-fr-layer-toggle="altitude"',
            'data-fr-layer-toggle="terrainLoad"',
            'data-fr-layer-toggle="efficiency"',
            'data-fr-layer-toggle="gap"',
            'data-fr-layer-toggle="grade"',
            'data-fr-layer-toggle="zones"',
            'data-fr-layer-toggle="events"',
            "--fr-layer-color:#ef4444",
            "--fr-layer-color:#3b82f6",
            "--fr-layer-color:#94a3b8",
            "--fr-layer-color:#14b8a6",
            "--fr-layer-color:#22c55e",
            "--fr-layer-color:#eab308",
            "--fr-layer-color:#f97316",
            "function _resizeFatigueReviewChartWhenStable()",
            "function _bindFatigueReviewChartAutoResize()",
            "function _unbindFatigueReviewChartAutoResize()",
            "var lanePx = lanes.length <= 3 ? 96 : (lanes.length <= 5 ? 90 : 88)",
            "var computedHeight = Math.max(420, Math.min(760, lanes.length * lanePx + 72))",
            "containerEl.style.height = computedHeight + 'px'",
            "chart.resize({ height: computedHeight })",
            "chart.resize({ height: containerEl.clientHeight || computedHeight })",
            "lanes[layoutIndex].layout = {",
            "top: topStart + layoutIndex * (laneHeight + laneGap)",
            "height: laneHeight",
            "var laneGap = 2.0",
            "var topStart = 6",
            "var bottomPad = 7",
            "top: lane.layout.top + '%'",
            "height: lane.layout.height + '%'",
            "window.addEventListener('resize', _resizeFatigueReviewChartWhenStable)",
            "window.removeEventListener('resize', _resizeFatigueReviewChartWhenStable)",
            "new ResizeObserver(function()",
            "_fatigueReviewChartResizeObserver.observe(chartBody)",
            "_fatigueReviewChartResizeObserver.observe(chartCanvas)",
            "function _renderFatigueReviewChartFooter(data)",
            "function _applyFatigueReviewLayerVisibility(chartPayload)",
            "function onFatigueReviewLayerToggle(inputEl)",
            "_renderFatigueReviewChartFooter(data)",
            "_renderFatigueReviewChartFooter({})",
            "_lastFatigueReviewChartPayload = chartPayload",
            "chartPayload = _applyFatigueReviewLayerVisibility(chartPayload)",
            "renderProfileAnalysisChart(chartPayload, 'fatigue-review-chart')",
            "_bindFatigueReviewChartAutoResize()",
            "_resizeFatigueReviewChartWhenStable()",
        ):
            self.assertIn(text, self.html)
        footer_idx = self.html.find('id="fr-chart-footer"')
        side_idx = self.html.find('class="fr-side-column"')
        footer_html = self.html[footer_idx:side_idx]
        for removed in (
            "图层与摘要",
            "fr-chart-footer-compact",
            "fr-footer-boundary",
            'id="fr-chart-footer-boundary"',
            'data-fr-layer-toggle="curves"',
        ):
            self.assertNotIn(removed, footer_html)

    def test_p7_17_chart_footer_uses_allowed_sources_only(self):
        helper = _extract_js_function(self.html, "_renderFatigueReviewChartFooter")
        for text in (
            "var curves = data.curves || {}",
            "var fatigueZones = Array.isArray(data.fatigue_zones) ? data.fatigue_zones : []",
            "Array.isArray(curves[key]) ? curves[key].length : 0",
            "availableCurves",
            "curvePointMax",
        ):
            self.assertIn(text, helper)
        for forbidden in (
            "data.collapse_events",
            "data.metrics",
            "data.advice",
            "data.disclaimer",
            "metrics.training_load",
            "metrics.bonk_risk",
            "metrics.hr_drift",
            "metrics.decoupling",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "points",
            "call_llm",
            "localStorage",
            "sessionStorage",
            "INSERT",
            "UPDATE",
        ):
            self.assertNotIn(forbidden, helper)

    def test_p7_18a_footer_does_not_duplicate_side_summary_cards(self):
        footer_idx = self.html.find('id="fr-chart-footer"')
        side_idx = self.html.find('class="fr-side-column"')
        self.assertGreater(footer_idx, -1)
        self.assertGreater(side_idx, footer_idx)
        footer_html = self.html[footer_idx:side_idx]
        for removed in (
            'id="fr-footer-load-energy"',
            'id="fr-footer-state-explain"',
            'id="fr-footer-advice-state"',
            'id="fr-footer-load-card"',
            'id="fr-footer-state-card"',
            'id="fr-footer-advice-card"',
            'id="fr-footer-event-timeline"',
            'class="fr-footer-event-strip"',
            "训练负荷",
            "心率漂移",
            "建议待接入",
            "事件时间线",
        ):
            self.assertNotIn(removed, footer_html)

    def test_p7_17_layer_toggles_are_view_only(self):
        apply_fn = _extract_js_function(self.html, "_applyFatigueReviewLayerVisibility")
        toggle_fn = _extract_js_function(self.html, "onFatigueReviewLayerToggle")
        for text in (
            "next.hr_curve = []",
            "next.pace_curve = []",
            "next.altitude_curve = []",
            "next.efficiency_curve = []",
            "next.gap_pace_curve = []",
            "next.grade_curve = []",
            "next.terrain_load_curve = []",
            "next.fatigue_zones = []",
            "next.insight_events = []",
            "_fatigueReviewLayerVisibility[key] = !!inputEl.checked",
            "_lastFatigueReviewChartPayload",
            "renderProfileAnalysisChart(",
            "_resizeFatigueReviewChartWhenStable()",
        ):
            self.assertIn(text, apply_fn + toggle_fn)
        for forbidden in (
            "call_llm",
            "fetch(",
            "pywebview",
            "localStorage",
            "sessionStorage",
            "INSERT",
            "UPDATE",
            "document.querySelector",
            "innerText",
        ):
            self.assertNotIn(forbidden, apply_fn + toggle_fn)

    def test_p7_18d_lane_order_labels_and_tooltip_format_are_preserved(self):
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        expected_order = [
            "name: '心率'",
            "name: '配速'",
            "name: '坡度修正配速（GAP）'",
            "name: '效率'",
            "name: '海拔'",
            "name: '坡度'",
            "name: '地形负荷'",
        ]
        cursor = -1
        for text in expected_order:
            next_idx = fn_body.find(text)
            self.assertGreater(next_idx, cursor)
            cursor = next_idx
        for text in (
            "function _frFormatTooltipNumber(value)",
            "function _frFormatPaceSecPerKm(value)",
            "function _frFormatPaceAxisSecPerKm(value)",
            "function _frFormatPaceTooltip(value, capped, capLabel)",
            "function _frPairDistanceDisplayCurve(distanceCurve, displayCurve)",
            "Math.round(num * 10) / 10",
            "rounded.toFixed(1)",
            "\"''/km\"",
            "formatted.replace('/km', '')",
        ):
            self.assertIn(text, self.html)
        for text in (
            "formatter: function(params)",
            "byName[params[p].seriesName]",
            "for (var l = 0; l < lanes.length; l++)",
            "safeHtml(lanes[l].name)",
            "var formatValue = lanes[l].valueFormatter || _frFormatTooltipNumber",
            "tooltipValue = _frFormatPaceTooltip(rawValue, isCapped, lanes[l].capLabel)",
            "displayAsPace: true",
            "valueFormatter: def.displayAsPace ? _frFormatPaceSecPerKm : _frFormatTooltipNumber",
            "axisValueFormatter: def.displayAsPace ? _frFormatPaceAxisSecPerKm : _frFormatTooltipNumber",
            "inverseAxis: !!def.displayAsPace",
            "inverse: !!lane.inverseAxis",
            "formatter: lane.axisValueFormatter || _frFormatTooltipNumber",
            "def.displayAsPace",
            "_frPairDistanceDisplayCurve(distanceCurve, curve)",
            "unit: '/km'",
        ):
            self.assertIn(text, fn_body)
        for text in (
            "pace_curve:      data.display_curves && data.display_curves.pace_sec_per_km",
            "gap_pace_curve:  data.display_curves && data.display_curves.gap_pace_sec_per_km",
            "display_meta:    data.display_meta || {}",
        ):
            self.assertIn(text, self.html)
        for forbidden in (
            "name: '速度'",
            "name: 'GAP'",
            "name: 'Terrain Load'",
            "1000 / speedMps",
            "_frSpeedMpsToPaceSecPerKm",
        ):
            self.assertNotIn(forbidden, fn_body)

    def test_p7_20_pace_lanes_are_display_only_and_keep_backend_sources(self):
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        for text in (
            "key: 'pace_curve'",
            "key: 'gap_pace_curve'",
            "name: '配速'",
            "name: '坡度修正配速（GAP）'",
            "displayAsPace: true",
            "_frPairDistanceDisplayCurve(distanceCurve, curve)",
            "terrain_load_curve",
            "activityData && activityData.terrain_load_curve",
            "unit: 'Speed/HR'",
            "unit: 'grade×speed×s'",
        ):
            self.assertIn(text, fn_body)
        for forbidden in (
            "INSERT",
            "UPDATE",
            "pywebview.api",
            "call_llm",
            "1000 /",
            "speedMps",
        ):
            self.assertNotIn(forbidden, fn_body)

    def test_p7_18e_fatigue_review_chart_auto_resize_is_bound_and_cleaned(self):
        for text in (
            "let _fatigueReviewChartResizeObserver = null",
            "let _fatigueReviewChartResizeBound = false",
            "function _bindFatigueReviewChartAutoResize()",
            "function _unbindFatigueReviewChartAutoResize()",
            "_bindFatigueReviewChartAutoResize();",
            "_unbindFatigueReviewChartAutoResize();",
            "if (containerId === 'fatigue-review-chart'",
        ):
            self.assertIn(text, self.html)
        cleanup_fn = _extract_js_function(self.html, "_cleanupFatigueReviewPanel")
        clear_fn = _extract_js_function(self.html, "clearProfileAnalysisChart")
        self.assertIn("_unbindFatigueReviewChartAutoResize()", cleanup_fn)
        self.assertIn("_unbindFatigueReviewChartAutoResize()", clear_fn)

    def test_p7_12_design_correction_plan_is_preserved(self):
        plan = _read(PLAN_MD)
        for text in (
            "P7.12 | 主图信息架构纠偏",
            "P7.13 | 左侧指标轨道与分层泳道回正",
            "P7.14 | 关键事件图钉与竖向参考线",
            "P7.15 | 状态阶段条视觉回正",
            "P7.16A | Terrain Load 柱形泳道接入",
            "P7.16B | Terrain Load 柱间距与离散柱视觉回正",
            "P7.16 | 右侧关键摘要面板纠偏",
            "P7.17 | 底部图例与交互控件回正",
            "P7.18 | 视觉回归与草图对照验收",
            "设计图关联约束",
            "状态阶段概览 / 多维时间轴分析 / 右侧关键摘要",
            "不实现 P7.13 左侧指标轨道",
            "不实现 P7.14 事件图钉细节",
        ):
            self.assertIn(text, plan)

    def test_eight_metric_card_targets_are_preserved(self):
        for element_id in (
            "fr-hr-drift",
            "fr-decoupling",
            "fr-bonk",
            "fr-events-count",
            "fr-efficiency-score",
            "fr-durability-score",
            "fr-cadence-stability-score",
            "fr-training-load-value",
        ):
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_3_metric_cards_have_status_and_explanation(self):
        for element_id in (
            "fr-hr-drift-status",
            "fr-decoupling-status",
            "fr-bonk-status",
            "fr-events-status",
            "fr-efficiency-status",
            "fr-durability-status",
            "fr-cadence-stability-status",
            "fr-training-load-status",
            "fr-hr-drift-sub",
            "fr-decoupling-sub",
            "fr-bonk-sub",
            "fr-events-sub",
            "fr-efficiency-sub",
            "fr-durability-sub",
            "fr-cadence-stability-sub",
            "fr-training-load-sub",
        ):
            self.assertIn('id="' + element_id + '"', self.html)
        self.assertEqual(self.html.count('class="metric-card fr-metric-card"'), 8)

    def test_fatigue_review_ids_are_not_duplicated(self):
        ids = re.findall(r'id="([^"]+)"', self.html)
        counts = {item: ids.count(item) for item in ids if item.startswith("fr")}
        duplicated = {item: count for item, count in counts.items() if count > 1}
        self.assertEqual(duplicated, {})

    def test_p7_2_summary_band_is_inside_review_tab(self):
        review_idx = self.html.find('id="detail-tab-review"')
        strip_idx = self.html.find('id="fr-status-strip"')
        core_idx = self.html.find('id="fr-core-metrics-section"')
        self.assertGreater(review_idx, 0)
        self.assertGreater(strip_idx, review_idx)
        self.assertGreater(core_idx, strip_idx)
        for element_id in (
            "fr-distance-axis-pill",
            "fr-curve-status-pill",
            "fr-risk-pill",
            "fr-event-pill",
            "fr-ai-status-pill",
        ):
            self.assertIn('id="' + element_id + '"', self.html)


class TestP5AiBoundaryGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)
        self.main = _read(MAIN_PY)
        self.llm_backend = _read(LLM_BACKEND_PY)

    def test_fatigue_review_sentinel_is_preserved(self):
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__", self.html)
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__", self.main)

    def test_frontend_ai_call_only_passes_sentinel_and_sport_type(self):
        idx = self.html.find("async function onFatigueReviewAiInsight(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    // === V6.3 渲染辅助", idx)
        body = self.html[idx:end]
        self.assertIn("call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)", body)
        for forbidden in ("metrics", "curves", "points", "chartPayload", "fatigue_zones"):
            self.assertNotIn("call_llm('__FATIGUE_REVIEW_INSIGHT__', " + forbidden, body)

    def test_p6_1_ai_button_is_frozen_but_capability_remains(self):
        button_idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(button_idx, 0)
        start = self.html.rfind("<button", 0, button_idx)
        end = self.html.find("</button>", button_idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertNotIn("onclick=", button)
        self.assertIn("function onFatigueReviewAiInsight(", self.html)
        self.assertIn("function _freezeFatigueReviewAiEntry(", self.html)

    def test_frontend_does_not_build_fatigue_review_prompt(self):
        idx = self.html.find("async function onFatigueReviewAiInsight(")
        body = self.html[idx: self.html.find("\n    // === V6.3 渲染辅助", idx)]
        self.assertNotIn("prompt", body.lower())
        self.assertNotIn("JSON.stringify", body)

    def test_ai_insight_does_not_write_db(self):
        for source in (self.main, self.llm_backend):
            self.assertNotIn("INSERT INTO ai_snapshots", source)
        start = self.main.index("if prompt == self.FATIGUE_REVIEW_INSIGHT")
        end = self.main.index("cfg = llm_backend.load_llm_config()", start + 1)
        branch = self.main[start:end]
        for token in ("INSERT", "UPDATE", "ai_snapshots"):
            self.assertNotIn(token, branch)


if __name__ == "__main__":
    unittest.main()
