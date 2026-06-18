"""活动建议前端接入静态契约测试。"""
from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
LLM_BACKEND = os.path.join(_PROJECT_ROOT, "llm_backend.py")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


def _read_llm_backend() -> str:
    with open(LLM_BACKEND, encoding="utf-8") as f:
        return f.read()


def _slice_function_body(html: str, fn_name: str, max_len: int = 7000) -> str:
    marker = f"function {fn_name}("
    idx = html.find(marker)
    if idx < 0:
        marker = f"async function {fn_name}("
        idx = html.find(marker)
    if idx < 0:
        return ""
    end = html.find("\n    function ", idx + len(marker))
    async_end = html.find("\n    async function ", idx + len(marker))
    candidates = [pos for pos in (end, async_end) if pos >= 0]
    if candidates:
        end = min(candidates)
    else:
        end = idx + max_len
    return html[idx:end]


class TestActivityAdviceFrontendContract(unittest.TestCase):
    def setUp(self):
        self.html = _read_track_html()

    def test_activity_advice_symbols_exist(self):
        for token in (
            "PY_REPORT_ACTIVITY_ADVICE",
            "requestActivityAdvice",
            "buildActivityAdviceHTML",
            "resetActivityAdviceState",
            "currentActivityAdvice",
            "activityAdviceLoading",
        ):
            self.assertIn(token, self.html)

    def test_ui_replaces_risk_warning_copy(self):
        report_body = _slice_function_body(self.html, "buildAIReportHTML")
        self.assertIn("活动建议", report_body)
        self.assertIn("✨ AI 生成建议", report_body)
        self.assertIn("出发计划（可选）", report_body)
        self.assertIn("填写活动类型和计划时间", report_body)
        self.assertIn("activity-advice-type", report_body)
        self.assertIn("activity-advice-planned-time", report_body)
        self.assertIn("type=\"datetime-local\"", report_body)
        self.assertNotIn("风险预警", report_body)
        self.assertNotIn("requestRiskAssessment", report_body)

    def test_old_pace_and_supply_cards_removed_from_report(self):
        report_body = _slice_function_body(self.html, "buildAIReportHTML")
        for forbidden in (
            "配速建议",
            "pace-row",
            "<h3>🎒 补给</h3>",
            "supply-item",
        ):
            self.assertNotIn(forbidden, report_body)

    def test_core_report_sections_still_render(self):
        report_body = _slice_function_body(self.html, "buildAIReportHTML")
        for token in (
            "概览",
            "buildActivitySnapshotHTML",
            "坡度与起伏",
            "活动建议",
            "requestActivityAdvice",
            "activity-advice-type",
            "activity-advice-planned-time",
        ):
            self.assertIn(token, report_body)

    def test_ai_coach_prompt_no_longer_claims_pace_supply_cards_are_visible(self):
        backend = _read_llm_backend()
        self.assertNotIn("用户在 UI 面板上已经看到了这些核心建议", backend)
        self.assertNotIn("如配速、补给、预估用时", backend)
        self.assertIn("路线概览、运动数据快照、坡度起伏和活动建议入口", backend)
        self.assertIn("report_json", backend)

    def test_request_sends_only_planning_context(self):
        body = _slice_function_body(self.html, "requestActivityAdvice")
        self.assertIn("user_activity_type: getActivityAdviceTypeInput()", body)
        self.assertIn("planned_start_time: getActivityAdvicePlannedTimeInput()", body)
        self.assertIn("call_llm(PY_REPORT_ACTIVITY_ADVICE, JSON.stringify(planningContext))", body)

        for forbidden in (
            "appState.points",
            "appState.activityMetrics",
            "appState.currentWeather",
            "activityAdviceRouteFacts",
            "activityMetrics",
            "currentWeather",
            "PY_REPORT_RISK_ASSESSMENT",
            "risk_assessment",
        ):
            self.assertNotIn(forbidden, body)

    def test_overview_route_facts_only_sync_through_track_context(self):
        apply_body = _slice_function_body(self.html, "applyDataAndRender", max_len=14000)
        self.assertIn("appState.currentOverviewStats = stats", apply_body)
        self.assertIn("syncCurrentTrackContextForActivityAdvice('track_loaded')", apply_body)

        builder_body = _slice_function_body(self.html, "buildActivityAdviceRouteFactsFromOverview")
        for token in ("distance_km", "elevation_gain_m", "max_alt_m", "source"):
            self.assertIn(token, builder_body)
        self.assertIn("appState.previewRegionMetrics", builder_body)
        self.assertIn("normalizeActivityAdviceRegion(regionMetrics)", builder_body)

        sync_body = _slice_function_body(self.html, "syncCurrentTrackContextForActivityAdvice")
        self.assertIn("buildActivityAdviceRouteFactsFromOverview(", sync_body)
        self.assertIn("activityAdviceRouteFacts: activityAdviceRouteFacts", sync_body)
        self.assertIn("sync_track_context(JSON.stringify({", sync_body)

    def test_activity_advice_region_uses_overview_fact_source(self):
        body = _slice_function_body(self.html, "normalizeActivityAdviceRegion")
        self.assertIn("m.region", body)
        self.assertIn("m.region_display", body)
        self.assertLess(body.find("m.region"), body.find("m.region_display"))
        for forbidden_ui_text in (
            "正在查询地区",
            "地区查询失败",
            "未知地点",
            "查询中……",
            "待补全",
        ):
            self.assertIn(forbidden_ui_text, body)
        self.assertIn("status === 'pending'", body)
        self.assertIn("status === 'failed'", body)

    def test_preview_region_resync_only_for_temporary_gpx_kml(self):
        guard_body = _slice_function_body(self.html, "isTemporaryRouteImportForRegionResync")
        self.assertIn("appState.persistenceMode === 'temporary_session'", guard_body)
        self.assertIn("ext === 'gpx' || ext === 'kml'", guard_body)
        self.assertNotIn("fit", guard_body)

        preview_body = _slice_function_body(self.html, "buildPreviewRegionMetrics")
        self.assertIn("start_lat", preview_body)
        self.assertIn("start_lon", preview_body)
        self.assertIn("region_status: 'pending'", preview_body)

        apply_body = _slice_function_body(self.html, "applyDataAndRender", max_len=14000)
        self.assertIn("appState.previewRegionMetrics = (!activity && isTemporaryRouteImportForRegionResync())", apply_body)
        self.assertIn("resolvePreviewRegionInBackground(appState.activityMetrics || appState.previewRegionMetrics)", apply_body)

        apply_region_body = _slice_function_body(self.html, "applyPreviewRegionFields")
        self.assertIn("appState.activityMetrics || appState.previewRegionMetrics", apply_region_body)
        self.assertIn("renderTrackReport({ silent: true })", apply_region_body)
        self.assertIn("isTemporaryRouteImportForRegionResync()", apply_region_body)
        self.assertIn("syncCurrentTrackContextForActivityAdvice('preview_region_resolved')", apply_region_body)

    def test_activity_advice_dimensions_rendered(self):
        body = _slice_function_body(self.html, "buildActivityAdviceHTML")
        for token in ("supply_advice", "weather_check", "equipment_advice", "physical_plan"):
            self.assertIn(token, body)
        for label in ("补给建议", "天气检查", "装备建议", "体力安排"):
            self.assertIn(label, body)
        self.assertIn("basis", body)
        self.assertIn("advice", body)

    def test_reset_hooked_into_lifecycle(self):
        for fn_name in ("switchTab", "switchSidebarTab", "applyDataAndRender"):
            body = _slice_function_body(self.html, fn_name, max_len=12000)
            self.assertIn("resetActivityAdviceState", body, f"{fn_name} missing resetActivityAdviceState")

    def test_old_risk_frontend_symbols_removed(self):
        for token in (
            "PY_REPORT_RISK_ASSESSMENT",
            "requestRiskAssessment",
            "buildRiskAssessmentHTML",
            "resetRiskAssessmentState",
            "currentRiskAssessment",
            "riskAssessmentLoading",
            "risk-assessment",
        ):
            self.assertNotIn(token, self.html)


if __name__ == "__main__":
    unittest.main()
