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

    def test_p8_4_overview_dimensions_do_not_infer_from_dom_or_charts(self):
        body = _extract_js_function(self.html, "_buildFatigueReviewOverviewDimensions")
        self.assertIn("data.metrics", body)
        self.assertIn("data.fatigue_zones", body)
        self.assertIn("data.collapse_events", body)
        self.assertIn("data.context_tags", body)
        for forbidden in (
            "querySelector",
            "getOption",
            "chartPayload",
            "points",
            "call_llm",
            "_distanceFromSpeedTime",
            "hr_drift_pct",
            "decoupling_pct",
        ):
            self.assertNotIn(forbidden, body)

    def test_p8_4_ai_overview_dimensions_only_use_key_dimensions(self):
        body = _extract_js_function(self.html, "_buildFatigueReviewOverviewDimensionsFromAi")
        self.assertIn("dimensions", body)
        for forbidden in (
            "data.metrics",
            "data.curves",
            "fatigue_zones",
            "collapse_events",
            "context_tags",
            "call_llm",
            "localStorage",
            "sessionStorage",
        ):
            self.assertNotIn(forbidden, body)


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
                {"start_km": 0.0, "end_km": 0.2, "level": "medium", "startup_trimmed": True},
                {"start_km": 2.0, "end_km": 3.2, "level": "high"},
                {"start_km": 3.6, "end_km": 4.5, "level": "high"},
            ],
            sport_type="running",
            total_distance_m=10000,
        )
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "FATIGUE_PRESSURE_START")
        self.assertEqual(events[0]["title"], "状态压力开始")
        self.assertGreater(events[0]["trigger_km"], 0)
        self.assertIn("SUSTAINED_FATIGUE", {ev["type"] for ev in events})
        self.assertIn("title", events[1])
        self.assertIn("label", events[1])
        self.assertIn("description", events[1])
        self.assertTrue(all(ev["event_id"].startswith("ce_") for ev in events))

    def test_energy_gap_event_keeps_legacy_fields_and_window_metadata(self):
        from main import _build_fatigue_review_collapse_events

        events = _build_fatigue_review_collapse_events(
            bonk_events=[{
                "type": "BONK_WARNING",
                "title": "能量断档风险线索",
                "label": "能量断档线索",
                "trigger_km": 28.4,
                "risk_start_km": 28.4,
                "risk_end_km": 31.2,
                "value_y": 0.8123,
                "confidence": "high",
                "evidence": ["EI持续下降约18%", "速度/配速同步变差"],
                "description": "风险窗口起点，不代表精确撞墙坐标。",
            }],
            fatigue_zones=[],
            sport_type="running",
            total_distance_m=42195,
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        for key in ("event_id", "type", "title", "label", "trigger_km", "value_y", "description"):
            self.assertIn(key, event)
        self.assertEqual(event["risk_start_km"], 28.4)
        self.assertEqual(event["risk_end_km"], 31.2)
        self.assertEqual(event["confidence"], "high")
        self.assertIn("evidence", event)


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
            "fr-chart-axis-note",
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
            "fatigue-review-chart",
        ):
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_4_chart_boundary_copy_is_preserved(self):
        for text in (
            "多维时间轴分析",
            'id="fr-chart-axis-note" hidden',
            "axisNote.hidden = !!distance.length",
        ):
            self.assertIn(text, self.html)
        for text in (
            'id="fr-chart-subtitle"',
            'id="fr-chart-boundary"',
            'id="fr-chart-legend"',
            "按距离展开本次活动的关键变化",
            "心率、配速、海拔和疲劳阶段会在同一条距离轴上对照显示。",
        ):
            self.assertNotIn(text, self.html)
        self.assertNotIn("个采样点", self.html)

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
            "_frRobustAxisRange(pairedData",
            "robustAxis: { hardMin: -35, hardMax: 35, minSpan: 4 }",
            "min: lane.axisMin != null ? lane.axisMin : 'dataMin'",
            "max: lane.axisMax != null ? lane.axisMax : 'dataMax'",
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
            "对应主图上的关键图钉，用来定位值得回看的位置；不是单点结论。",
            "对应主图上方的状态阶段带，帮助理解压力持续出现的路段。",
            "_renderFatigueReviewEvents(data.collapse_events || [], data.sport_type, hasSustainedZone)",
            "_renderFatigueReviewZones(data.fatigue_zones || [], data.sport_type, reviewTotalDistanceKm, data.metrics || {}, data.collapse_events || [])",
            "_fatigueReviewEventDisplayCopy(ev, sportGroup, hasSustainedZone)",
            "_fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)",
        ):
            self.assertIn(text, self.html)

    def test_p8_1_context_factors_move_into_side_summary(self):
        for text in (
            "_renderFatigueReviewContextFactors(contextTags)",
            "影响因素",
            "温度偏高，心率更容易上浮",
            "能量消耗偏高，后程可能更吃补给",
            "本次心肺压力偏高",
            "心率储备占用约",
            "海拔压力会抬高心率",
            "输出压力偏高，需要结合恢复观察",
            "_renderFatigueReviewAdvice(data.advice, data.disclaimer)",
            "主页面不再重复展示建议",
            "AI 洞察弹窗",
        ):
            self.assertIn(text, self.html)
        for removed in (
            'id="fr-context-panel"',
            'id="fr-context-boundary"',
            'id="fr-context-tags"',
            "本次活动未携带上下文标签",
            "暂无上下文",
            "_renderFatigueReviewContextTags(data.context_tags || {})",
        ):
            self.assertNotIn(removed, self.html)

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
            "fr-side-summary-panel",
            "fr-events-panel",
            "fr-fatigue-zones-panel",
        )
        positions = []
        for element_id in ordered_ids:
            pos = self.html.find('id="' + element_id + '"')
            self.assertGreater(pos, 0, element_id)
            positions.append(pos)
        self.assertEqual(positions, sorted(positions))

    def test_p8_1_visual_regression_keeps_sketch_scope_and_opens_ai_entry(self):
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
        self.assertNotIn("disabled", button)
        self.assertNotIn('aria-disabled="true"', button)
        self.assertIn('onclick="onFatigueReviewAiInsight()"', button)
        self.assertIn("AI 洞察", button)
        self.assertIn("✨", button)
        title_idx = self.html.find("本次复盘概览")
        overview_idx = self.html.find('id="fr-overview-dimensions"')
        self.assertGreater(button_idx, title_idx)
        self.assertLess(button_idx, overview_idx)
        self.assertNotIn("call_llm", button)

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
        self.assertIn("var reviewTotalDistanceKm = _fatigueReviewTotalDistanceKm(data)", self.html)
        self.assertIn("_renderFatigueReviewStageOverview(data.fatigue_zones || [], data.sport_type, reviewTotalDistanceKm, data.metrics || {}, data.collapse_events || [])", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _fatigueReviewContextFactorCopy", fn_idx)]
        for text in (
            "zone.start_km",
            "zone.end_km",
            "zone.level",
            "_fatigueReviewZoneDisplayCopy(zone, sportGroup, totalDistanceKm)",
            "_fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, stageItems.length)",
            "fr-stage-segment",
            "_fatigueReviewHasRiskSignals(metrics || {}, events || [])",
            "无持续压力区间",
            "有风险线索",
            "状态平稳",
            "平稳完成",
        ):
            self.assertIn(text, fn_body)
        self.assertNotIn("轻松完成", fn_body)
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

    def test_p2_stage_bar_tooltip_and_boundary_copy_are_preserved(self):
        for text in (
            "阶段条展示压力变化；没有压力区间时表示本次整体更平稳。",
            "阶段条保留多个原始片段；右侧状态区间已将碎片合并为阅读摘要。",
            "function _fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, fragmentCount)",
            "这是系统识别到的原始片段之一",
            "这是系统识别到的一个原始状态片段",
            "不代表身体状态在该公里点突然变化",
            "右侧状态区间摘要",
            "title=\"' + safeHtml(tooltip) + '\"",
            "aria-label=\"' + safeHtml(title + '，' + start + ' 到 ' + end + ' 公里。' + tooltip) + '\"",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, fragmentCount)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewStageOverview", fn_idx)]
        for token in (
            "speed",
            "time",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "echarts",
        ):
            self.assertNotIn(token, fn_body)

    def test_p7_12_chart_architecture_correction_is_preserved(self):
        for text in (
            "grid-template-columns: minmax(0, 1fr) 248px",
            "min-height: 560px",
            "#fatigue-review-chart.fr-chart-canvas",
            "min-height: 360px",
            "var computedHeight = Math.max(432, Math.min(772, lanes.length * lanePx + 84))",
            "topStart = 9",
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
            "min-height: 560px",
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
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _fatigueReviewContextFactorCopy", fn_idx)]
        for text in (
            "var stageItems = []",
            "zone.start_km",
            "zone.end_km",
            "zone.level",
            "_fatigueReviewZoneDisplayCopy(zone, sportGroup, totalDistanceKm)",
            "item.span / fullSpan * 100",
            "Math.max(7, item.span / fullSpan * 100)",
            "暂无有效阶段",
            "compact",
        ):
            self.assertIn(text, fn_body)
        for text in (
            "function _fatigueReviewStageStatusHtml(tone, title, rangeText, tagText, desc)",
            "fr-stage-segment solo",
            ".fr-stage-segment.solo",
            "_fatigueReviewStageStatusHtml('stable', '状态平稳'",
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
            "读图解释",
            "图钉线索",
            "解释原因",
            "先看主图：这里汇总当前最值得回看的风险、图钉和状态区间。",
            "用少量证据解释主图里的波动，避免重复顶部四维总览。",
            "function _renderFatigueReviewSideSummary(data)",
            "_renderFatigueReviewSideSummary(data)",
            "_renderFatigueReviewSideSummary({})",
            "var metrics = data.metrics || {}",
            "var collapseEvents = Array.isArray(data.collapse_events) ? data.collapse_events : []",
            "var fatigueZones = Array.isArray(data.fatigue_zones) ? data.fatigue_zones : []",
            "var contextTags = data.context_tags || {}",
            "var contextFactorsHtml = _renderFatigueReviewContextFactors(contextTags)",
            "fr-context-factor-card",
            "var candidates = []",
            "var topImpactItems = candidates.slice(0, 3)",
        ):
            self.assertIn(text, self.html)
        helper = _extract_js_function(self.html, "_renderFatigueReviewSideSummary")
        self.assertIn("contextTags", helper)
        self.assertIn("contextFactorsHtml", helper)
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
            "var computedHeight = Math.max(432, Math.min(772, lanes.length * lanePx + 84))",
            "containerEl.style.height = computedHeight + 'px'",
            "chart.resize({ height: computedHeight })",
            "chart.resize({ height: containerEl.clientHeight || computedHeight })",
            "lanes[layoutIndex].layout = {",
            "top: topStart + layoutIndex * (laneHeight + laneGap)",
            "height: laneHeight",
            "var laneGap = 2.0",
            "var topStart = 9",
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

    def test_metric_card_user_facing_copy_and_tooltips(self):
        for text in (
            "后程效率变化",
            "能量断档风险",
            "后程基本稳住",
            "心率后半程约上浮",
            "不适合判断",
            "活动时长小于 45 分钟",
            "活动时长小于 20 分钟",
            "活动时长小于 15 分钟",
            "有效采样点不足 20 个",
            "当前运动类型暂不适用",
            "后程效率稳定",
            "有断档风险",
            "有下滑线索",
            "转化效率偏弱",
            "后程保持很好",
            "步频有些波动",
            "负荷很高",
            "fr-metric-info",
            "看后半程是否需要更高的心肺负担",
            "结合能量储备和持续表现变化判断风险线索",
            "getFatigueReviewSportCopyGroup",
            "sport === 'mountaineering'",
            "_fatigueReviewMetricCopy",
            "_fatigueReviewHrDriftHeadline",
            "_fatigueReviewHrDriftEvidence",
            "_fatigueReviewMetricHeadline",
            "_fatigueReviewMetricEvidence",
            "_fatigueReviewMetricMissingReason",
            "label + '约 ' + formatted",
            "_fatigueReviewMetricEvidence('效率变化', decoupling.pct, '%')",
            "_fatigueReviewMetricEvidence('评分', eff.score, '')",
            "_fatigueReviewMetricEvidence('评分', dur.score, '')",
            "_fatigueReviewMetricEvidence('评分', cadStab.score, '')",
            "_fatigueReviewMetricEvidence('训练负荷', tload.load, '')",
        ):
            self.assertIn(text, self.html)
        self.assertNotIn("<div class=\"lbl\">解耦率</div>", self.html)
        self.assertNotIn("<div class=\"lbl\">Bonk 风险</div>", self.html)
        self.assertNotIn("TRIMP 简化版", self.html)
        self.assertNotIn("std + late_decay 综合", self.html)

    def test_metric_card_primary_values_are_user_facing_not_raw_numbers(self):
        body_idx = self.html.find("function _renderFatigueReviewMetrics(metrics, sportType)")
        self.assertGreater(body_idx, 0)
        body = self.html[body_idx:self.html.find("\n    function _renderFatigueReviewDimensions", body_idx)]
        for forbidden in [
            "'fr-decoupling', 'fr-decoupling-status', 'fr-decoupling-sub',\n            pctVal(decoupling.pct)",
            "'fr-efficiency-score', 'fr-efficiency-status', 'fr-efficiency-sub',\n            effMissing ? '--' : String(eff.score)",
            "'fr-durability-score', 'fr-durability-status', 'fr-durability-sub',\n            durMissing ? '--' : String(dur.score)",
            "'fr-cadence-stability-score', 'fr-cadence-stability-status', 'fr-cadence-stability-sub',\n            cadMissing ? '--' : String(cadStab.score)",
            "'fr-training-load-value', 'fr-training-load-status', 'fr-training-load-sub',\n            tloadMissing ? '--' : String(tload.load)",
        ]:
            self.assertNotIn(forbidden, body)

    def test_physiological_impact_cards_are_ranked_top_three(self):
        body_idx = self.html.find("function _renderFatigueReviewSideSummary(data)")
        self.assertGreater(body_idx, 0)
        body = self.html[body_idx:self.html.find("\n    // === P8.0 AI", body_idx)]
        for text in [
            "var candidates = []",
            "var addCandidate = function(item)",
            "candidates.sort(function(a, b)",
            "var topImpactItems = candidates.slice(0, 3)",
            "能量断档风险",
            "后程效率变化",
            "训练负荷",
            "心率漂移",
            "状态下滑事件",
        ]:
            self.assertIn(text, body)
        fixed_block = "factHtml(\n                    '心率漂移'"
        self.assertNotIn(fixed_block, body)
        self.assertNotIn("label: '状态区间'", body)

    def test_p0_sustained_fatigue_zone_copy_is_user_facing(self):
        for text in (
            "function _fatigueReviewTotalDistanceKm(data)",
            "curves.total_distance_m",
            "Array.isArray(curves.distance) ? curves.distance : []",
            "function _fatigueReviewZoneCoverageState(zone, totalDistanceKm)",
            "coverage >= 0.7 && startsEarly",
            "FATIGUE_REVIEW_SUSTAINED_ZONE_COPY",
            "整体偏吃力",
            "本次大部分路段都处在较吃力状态，建议重点看心率、配速和恢复段。",
            "本次大部分路段体能压力偏高，建议重点看爬升、补给和停歇安排。",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _fatigueReviewZoneCoverageState(zone, totalDistanceKm)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _fatigueReviewSustainedZoneCopy", fn_idx)]
        for token in (
            "speed",
            "time",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "echarts",
        ):
            self.assertNotIn(token, fn_body)

    def test_p0b_sustained_event_anchor_is_softened(self):
        for text in (
            "var hasSustainedZone = _fatigueReviewHasSustainedZone(data.fatigue_zones || [], reviewTotalDistanceKm)",
            "FATIGUE_REVIEW_SUSTAINED_EVENT_COPY",
            "function _fatigueReviewHasSustainedZone(zones, totalDistanceKm)",
            "function _fatigueReviewEventDisplayCopy(ev, sportGroup, hasSustainedZone)",
            "这个位置是系统识别到的参考点；本次状态压力更像是在大部分路段持续存在，建议结合整段配速、心率和恢复段回看。",
            "这个位置是系统识别到的参考点；本次输出压力更像在大部分路段持续存在，建议结合心率、坡度和功率回看。",
            "return _fatigueReviewEventCopy(ev, sportGroup)",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _renderFatigueReviewEvents(events, sportType, hasSustainedZone)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewZones", fn_idx)]
        self.assertIn("trigger_km", fn_body)
        self.assertIn("safeHtml(type) + ' · ' + safeHtml(km)", fn_body)
        for token in (
            "_distanceFromSpeedTime",
            "speed_curve",
            "time_curve",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "markLine",
        ):
            self.assertNotIn(token, fn_body)

    def test_p3_event_and_zone_relation_copy_is_unified(self):
        for text in (
            'id="fr-signal-relation-note"',
            "function _fatigueReviewSignalRelationCopy(hasEvents, hasZones, hasRiskSignals)",
            "function _renderFatigueReviewSignalRelation(events, zones, metrics)",
            "_renderFatigueReviewSignalRelation(data.collapse_events || [], data.fatigue_zones || [], data.metrics || {})",
            "事件是点，区间是段",
            "点帮助定位，段帮助理解持续压力",
            "两者都是回看线索，不是精确结论",
            "本次只识别到参考点，建议结合主图查看附近曲线变化。",
            "本次只识别到状态路段，建议结合主图查看压力持续位置。",
            "function _fatigueReviewHasRiskSignals(metrics, events)",
            "本次未识别到持续压力路段，但右侧存在风险线索；请结合能量、效率和负荷卡片复盘。",
            "本次状态整体平稳，未识别到明显压力转折点或持续压力路段。",
            "var trainingLoadRisk = function(metric)",
            "metric.ratio_7d_42d",
        ):
            self.assertIn(text, self.html)
        risk_fn_idx = self.html.find("function _fatigueReviewHasRiskSignals(metrics, events)")
        self.assertGreater(risk_fn_idx, 0)
        risk_fn = self.html[risk_fn_idx:self.html.find("\n    function _fatigueReviewSignalRelationCopy", risk_fn_idx)]
        self.assertIn("trainingLoadRisk(metrics.training_load)", risk_fn)
        self.assertNotIn("riskLevel(metrics.training_load)", risk_fn)
        self.assertNotIn("崩溃触发因素", self.html)
        self.assertNotIn("突然崩", self.html)
        self.assertNotIn("精确诊断", self.html)
        fn_idx = self.html.find("function _fatigueReviewSignalRelationCopy(hasEvents, hasZones, hasRiskSignals)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewEvents", fn_idx)]
        for token in (
            "speed",
            "time",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "echarts",
        ):
            self.assertNotIn(token, fn_body)

    def test_p1_fragmented_fatigue_zones_are_summarized(self):
        for text in (
            "function _fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)",
            "function _fatigueReviewValidZoneItems(zones)",
            "function _fatigueReviewMergeZoneItems(items, totalDistanceKm)",
            "FATIGUE_REVIEW_FRAGMENTED_ZONE_COPY",
            "多段波动",
            "sourceCount",
            "由 ' + item.sourceCount + ' 个状态片段合并",
            "summaryItems.slice(0, 3)",
            "title: '整体偏吃力'",
            "title: '多段波动'",
            "末段输出压力更明显",
        ):
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _renderFatigueReviewZones(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewStageOverview", fn_idx)]
        self.assertIn("_fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)", fn_body)
        for text in (
            "_fatigueReviewHasRiskSignals(metrics || {}, events || [])",
            "无持续压力区间 · 有风险线索",
            "风险来自能量、事件或指标卡片",
            "本次没有识别到持续压力路段，可视为稳定完成。",
        ):
            self.assertIn(text, fn_body)
        self.assertNotIn("轻松跑可视为稳定完成", fn_body)
        self.assertNotIn("zones.map(function(zone", fn_body)
        summary_idx = self.html.find("function _fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)")
        self.assertGreater(summary_idx, 0)
        summary_body = self.html[summary_idx:self.html.find("\n    function _fatigueReviewEventKind", summary_idx)]
        for token in (
            "_distanceFromSpeedTime",
            "speed_curve",
            "time_curve",
            "points",
            "querySelector",
            "getBoundingClientRect",
            "innerText",
            "echarts",
        ):
            self.assertNotIn(token, summary_body)
            self.assertNotIn(token, fn_body)

    def test_p4_review_copy_regression_real_world_acceptance_contract(self):
        for text in (
            "整体偏吃力",
            "这个位置是系统识别到的参考点",
            "多段波动",
            "由 ' + item.sourceCount + ' 个状态片段合并",
            "阶段条展示压力变化；没有压力区间时表示本次整体更平稳。",
            "不代表身体状态在该公里点突然变化",
            "事件是点，区间是段",
            "两者都是回看线索，不是精确结论",
            "本次未识别到持续压力路段，但右侧存在风险线索",
            "本次状态整体平稳，未识别到明显压力转折点或持续压力路段。",
            "事件点",
            "参考位置：",
            "持续压力区间",
            "无持续压力区间",
            "配速、心率和恢复段",
            "爬升、补给和停歇",
            "心率、坡度和功率",
            "这个图钉表示能量断档风险窗口起点",
            "这个图钉表示乏力风险窗口起点",
            "这个图钉表示掉功率风险窗口起点",
        ):
            self.assertIn(text, self.html)
        for text in (
            "崩溃触发因素",
            "触发因素",
            "<div class=\"lbl\">解耦率</div>",
            "<div class=\"lbl\">Bonk 风险</div>",
            "暂无阶段说明",
            "medium 区间",
            "high 区间",
            "fatigue_zones 标记",
            "精确诊断",
            "突然崩",
            "这里出现明显掉电风险",
            "从这里开始",
            "这里之后",
        ):
            self.assertNotIn(text, self.html)

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

    def test_p8_1_ai_button_is_open_and_capability_remains(self):
        button_idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(button_idx, 0)
        start = self.html.rfind("<button", 0, button_idx)
        end = self.html.find("</button>", button_idx)
        button = self.html[start:end]
        self.assertNotIn("disabled", button)
        self.assertNotIn('aria-disabled="true"', button)
        self.assertIn('onclick="onFatigueReviewAiInsight()"', button)
        self.assertNotIn("call_llm", button)
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
