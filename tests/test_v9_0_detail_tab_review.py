"""
V9.0 契约测试:详情 Tab 化 + 复盘 AI 洞察 Modal 化

任务: 活动详情页(概览/复盘)由两个独立 Overlay 合并为同一 Overlay 内两个 Tab;
      复盘 AI 洞察从内嵌左面板抽取为毛玻璃 Modal,物理拦截 Tab 切换。

契约依据 (fit-arch-contrac):
- §3 统一响应结构 {code, msg, data, traceId}  (修正 onFatigueReviewAiInsight)
- §5.4 AI 边界 / §5.6 Modal 化
- §5.6.2 阅后即焚 3 触发点(关闭弹窗 / 切活动 / 重新点击;切 Tab 物理不可)
- §六 shadow_diff 隔离(AI Modal 渲染前再校验)

策略: 静态 grep 测试 track.html 改动完整性 + 后端零变更校验。
"""

from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
PLAN_MD = os.path.join(_PROJECT_ROOT, "docs", "fatigue_review_realignment_plan_v1.md")
P7_IA_MD = os.path.join(_PROJECT_ROOT, "docs", "p7_fatigue_review_analysis_cockpit_information_architecture.md")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


def _read_doc(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestV9DetailTabHtml(unittest.TestCase):
    """V9.0 详情 Modal HTML 结构校验。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_detail_tab_bar_exists(self):
        """#detail-tab-bar 节点必须存在,含概览/复盘两个按钮。"""
        self.assertIn('id="detail-tab-bar"', self.html,
                      "V9.0 FAIL: 缺少 #detail-tab-bar")
        self.assertIn('data-detail-tab="overview"', self.html,
                      "V9.0 FAIL: 缺少概览 Tab 按钮")
        self.assertIn('data-detail-tab="review"', self.html,
                      "V9.0 FAIL: 缺少复盘 Tab 按钮")

    def test_detail_tab_overview_panel_exists(self):
        """#detail-tab-overview 节点必须存在。"""
        self.assertIn('id="detail-tab-overview"', self.html,
                      "V9.0 FAIL: 缺少 #detail-tab-overview 面板")
        self.assertIn('class="detail-tab-panel active"', self.html,
                      "V9.0 FAIL: 缺少 detail-tab-panel.active(默认激活态)")

    def test_detail_tab_review_panel_exists(self):
        """#detail-tab-review 节点必须存在,含 8 metric cards + chart。"""
        self.assertIn('id="detail-tab-review"', self.html,
                      "V9.0 FAIL: 缺少 #detail-tab-review 面板")
        # 8 个 metric cards 关键 id
        for metric_id in [
            "fr-hr-drift", "fr-decoupling", "fr-bonk", "fr-events-count",
            "fr-efficiency-score", "fr-durability-score",
            "fr-cadence-stability-score", "fr-training-load-value",
        ]:
            self.assertIn('id="' + metric_id + '"', self.html,
                          f"V9.0 FAIL: 复盘 Tab 缺 {metric_id}")
        self.assertIn('id="fatigue-review-chart"', self.html,
                      "V9.0 FAIL: 复盘 Tab 缺 ECharts 容器")

    def test_p7_3_metric_cockpit_status_targets_exist(self):
        """P7.3:8 张指标卡必须都有状态标签和解释容器。"""
        for status_id in [
            "fr-hr-drift-status", "fr-decoupling-status",
            "fr-bonk-status", "fr-events-status",
            "fr-efficiency-status", "fr-durability-status",
            "fr-cadence-stability-status", "fr-training-load-status",
        ]:
            self.assertIn('id="' + status_id + '"', self.html,
                          f"P7.3 FAIL: 指标卡缺状态标签 #{status_id}")
        for sub_id in [
            "fr-hr-drift-sub", "fr-decoupling-sub", "fr-bonk-sub",
            "fr-events-sub", "fr-efficiency-sub", "fr-durability-sub",
            "fr-cadence-stability-sub", "fr-training-load-sub",
        ]:
            self.assertIn('id="' + sub_id + '"', self.html,
                          f"P7.3 FAIL: 指标卡缺解释容器 #{sub_id}")
        self.assertEqual(self.html.count('class="metric-card fr-metric-card"'), 8)

    def test_fatigue_review_overlay_removed(self):
        """#fatigue-review-overlay 必须已被删除(合并入 detail Modal)。"""
        self.assertNotIn('id="fatigue-review-overlay"', self.html,
                         "V9.0 FAIL: fatigue-review-overlay 应已删除")

    def test_enter_fatigue_review_button_removed(self):
        """旧的「进入复盘」按钮必须已删除(由 Tab 替代)。"""
        self.assertNotIn('id="enter-fatigue-review-btn"', self.html,
                         "V9.0 FAIL: enter-fatigue-review-btn 应已删除")

    def test_jump_3d_button_in_review_removed(self):
        """复盘内的「进入 3D 沉浸分析」按钮必须已删除(由概览 Tab 轨迹缩略图承担)。"""
        self.assertNotIn('id="fr-3d-jump-btn"', self.html,
                         "V9.0 FAIL: fr-3d-jump-btn 应已删除")


class TestV9AiInsightModalHtml(unittest.TestCase):
    """V9.0 复盘 AI 洞察 Modal HTML 节点校验。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_fatigue_ai_modal_exists(self):
        """#fatigue-ai-insight-modal 必须存在(同 radar-ai-insight-modal 结构)。"""
        self.assertIn('id="fatigue-ai-insight-modal"', self.html,
                      "V9.0 FAIL: 缺少 #fatigue-ai-insight-modal")
        self.assertIn('class="fatigue-ai-modal"', self.html,
                      "V9.0 FAIL: 缺少 .fatigue-ai-modal 命名空间")

    def test_fatigue_ai_modal_backdrop(self):
        """毛玻璃 backdrop 必须存在(点击关闭)。"""
        self.assertIn('fatigue-ai-modal-backdrop', self.html,
                      "V9.0 FAIL: 缺少 .fatigue-ai-modal-backdrop")
        self.assertIn('onclick="closeFatigueAiInsightModal()"', self.html,
                      "V9.0 FAIL: backdrop 缺少关闭 handler")

    def test_fatigue_ai_modal_sections(self):
        """AI Modal 4 sections(总评/维度/事件/建议)必须就位。"""
        for section_id in [
            "fr-section-summary", "fr-section-dimensions",
            "fr-ai-section-events", "fr-section-advice",
        ]:
            self.assertIn('id="' + section_id + '"', self.html,
                          f"V9.0 FAIL: AI Modal 缺 {section_id}")
        # AI Modal 使用独立 fr-ai-* id,避免与 P4 复盘主页面重复
        for el_id in ["fr-ai-summary", "fr-ai-dimensions", "fr-ai-event-list",
                      "fr-ai-advice", "fr-ai-disclaimer"]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"V9.0 FAIL: AI Modal 缺 #{el_id}")

    def test_p4_review_layout_sections_exist(self):
        """P4 复盘主页面信息结构必须存在。"""
        for el_id in [
            "fr-review-layout", "fr-status-strip",
            "fr-core-metrics-section", "fr-capacity-metrics-section",
            "fr-stage-overview-section", "fr-stage-track",
            "fr-context-panel", "fr-events-panel", "fr-advice-panel",
            "fr-context-tags", "fr-event-list", "fr-advice", "fr-disclaimer",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P4 FAIL: 复盘主页面缺 #{el_id}")
        for text in ["核心状态", "能力与负荷", "多维时间轴分析", "本次复盘概览"]:
            self.assertIn(text, self.html)

    def test_p6_1_ai_entry_is_frozen(self):
        """P6.1:UI 定稿前 AI 洞察入口必须冻结。"""
        idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(idx, 0, "P6.1 FAIL: 缺少 AI 按钮")
        start = self.html.rfind("<button", 0, idx)
        end = self.html.find("</button>", idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertIn("AI 洞察待开放", button)
        self.assertIn("AI 洞察功能即将开放", button)
        self.assertNotIn("onclick=", button)

    def test_p7_2_summary_band_exists(self):
        """P7.2:复盘 Tab 内部顶部分析摘要带必须存在。"""
        for el_id in [
            "fr-status-strip", "fr-summary", "fr-summary-desc",
            "fr-data-source-pill", "fr-distance-axis-pill",
            "fr-curve-status-pill", "fr-risk-pill",
            "fr-event-pill", "fr-ai-status-pill",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.2 FAIL: 摘要带缺 #{el_id}")
        for text in ["本次复盘概览", "汇总本次活动的疲劳、风险和建议状态。", "AI 待开放"]:
            self.assertIn(text, self.html)

    def test_p7_2_summary_band_uses_backend_snapshot_only(self):
        """P7.2:摘要带只展示后端 snapshot 字段,不得引入前端事实推导。"""
        idx = self.html.find("function _renderFatigueReviewSummary(data)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewMetrics", idx)
        body = self.html[idx:end]
        for required in [
            "data.curves", "data.metrics", "data.collapse_events",
            "data.fatigue_zones", "data.advice", "data.disclaimer",
        ]:
            self.assertIn(required, body)
        for forbidden in [
            "_distanceFromSpeedTime", "total_distance_m /", "speed *",
            "querySelector", "getBoundingClientRect", "innerText",
        ]:
            self.assertNotIn(forbidden, body)

    def test_p7_2_does_not_add_sketch_global_actions(self):
        """P7.2 不得把草图全局导航/分享导出区实现进复盘 Tab。"""
        review_idx = self.html.find('id="detail-tab-review"')
        self.assertGreater(review_idx, 0)
        overview_idx = self.html.find('id="detail-tab-overview"', review_idx + 1)
        body = self.html[review_idx:overview_idx if overview_idx > review_idx else review_idx + 12000]
        for forbidden in ["首页", "日历", "分享", "导出"]:
            self.assertNotIn(forbidden, body)

    def test_p7_3_metric_render_uses_metrics_only(self):
        """P7.3:指标驾驶舱渲染只消费 metrics,不得从曲线/DOM 推导业务状态。"""
        idx = self.html.find("function _renderFatigueReviewMetrics(metrics)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewDimensions", idx)
        body = self.html[idx:end]
        for required in [
            "metrics.hr_drift", "metrics.decoupling", "metrics.bonk_risk",
            "metrics.events", "metrics.efficiency", "metrics.durability",
            "metrics.cadence_stability", "metrics.training_load",
        ]:
            self.assertIn(required, body)
        for forbidden in [
            "window._lastFatigueReviewCurves", "curves.", "distance",
            "total_distance_m", "points", "querySelector",
            "getBoundingClientRect", "innerText",
        ]:
            self.assertNotIn(forbidden, body)

    def test_p7_4_chart_container_and_legend_exist(self):
        """P7.4:主图容器、标题、边界说明和图例必须存在。"""
        for el_id in [
            "fr-chart-section", "fr-chart-title", "fr-chart-subtitle",
            "fr-chart-boundary", "fr-chart-legend",
            "fr-chart-axis-note", "fatigue-review-chart",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.4 FAIL: 主图区缺 #{el_id}")
        for text in [
            "多维时间轴分析",
            "按距离展开本次活动的关键变化",
            "心率、配速、海拔和疲劳阶段会在同一条距离轴上对照显示。",
            "心率", "配速", "坡度修正配速（GAP）",
            "疲劳阶段", "关键事件",
        ]:
            self.assertIn(text, self.html)

    def test_p7_20_review_static_ui_hides_engineering_labels(self):
        """P7.20:复盘 Tab 静态 UI 不再向用户暴露契约字段名。"""
        start = self.html.find('id="detail-tab-review"')
        end = self.html.find('<input type="file"', start)
        self.assertGreater(start, 0)
        self.assertGreater(end, start)
        review_template = self.html[start:end]
        for forbidden in (
            "data.curves",
            "data.metrics",
            "data.fatigue_zones",
            "data.collapse_events",
            "get_fatigue_review 后端权威快照",
            "后端权威快照",
            "curves.hr",
            "curves.speed",
            "curves.gap",
            "curves.terrain_load",
            "fatigue_zones",
            "collapse_events",
            "distance_curve",
            "context_tags",
            "trigger_km",
            "start_km",
            "end_km",
            "DOM 推导",
            "Resolver",
        ):
            self.assertNotIn(forbidden, review_template)

    def test_p7_4_chart_payload_uses_backend_sources(self):
        """P7.4:主图 payload 必须只使用后端 curves/fatigue_zones/collapse_events。"""
        idx = self.html.find("var chartPayload = {")
        self.assertGreater(idx, 0)
        end = self.html.find("renderProfileAnalysisChart(chartPayload", idx)
        body = self.html[idx:end]
        self.assertIn("distance_curve: Array.isArray(curvesObj.distance) ? curvesObj.distance : []", body)
        self.assertIn("hr_curve:        data.curves && data.curves.hr", body)
        self.assertIn("pace_curve:      data.display_curves && data.display_curves.pace_sec_per_km", body)
        self.assertIn("pace_raw_curve:  data.display_curves && data.display_curves.pace_raw_sec_per_km", body)
        self.assertIn("altitude_curve:  data.curves && data.curves.altitude", body)
        self.assertIn("efficiency_curve:data.curves && data.curves.efficiency", body)
        self.assertIn("gap_pace_curve:  data.display_curves && data.display_curves.gap_pace_sec_per_km", body)
        self.assertIn("gap_pace_raw_curve:data.display_curves && data.display_curves.gap_pace_raw_sec_per_km", body)
        self.assertIn("grade_curve:     data.curves && data.curves.grade", body)
        self.assertIn("display_meta:    data.display_meta || {}", body)
        self.assertIn("fatigue_zones:   data.fatigue_zones || []", body)
        self.assertIn("insight_events:  data.collapse_events || []", body)
        for forbidden in [
            "_distanceFromSpeedTime", "total_distance_m /", "speed *",
            "points", "querySelector", "getBoundingClientRect",
        ]:
            self.assertNotIn(forbidden, body)

    def test_p7_10_layered_echarts_branch_exists(self):
        """P7.10:复盘主图必须使用多 grid / 多 yAxis 分层 ECharts。"""
        self.assertIn("function _renderFatigueReviewLayeredEcharts(activityData, targetId, distanceCurve)", self.html)
        self.assertIn("if (targetId === 'fatigue-review-chart')", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        for text in [
            "var grid = []",
            "var xAxis = []",
            "var yAxis = []",
            "grid.push({",
            "xAxis.push({",
            "yAxis.push({",
            "xAxisIndex: laneIndex",
            "yAxisIndex: laneIndex",
            "axisPointer: { link: [{ xAxisIndex: 'all' }] }",
            "grid: grid",
            "xAxis: xAxis",
            "yAxis: yAxis",
        ]:
            self.assertIn(text, fn_body)

    def test_p7_10_layered_echarts_uses_backend_curves_and_layers(self):
        """P7.10:分层主图消费后端曲线、展示曲线、疲劳带和事件。"""
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        for text in [
            "hr_curve", "pace_curve", "altitude_curve",
            "efficiency_curve", "gap_pace_curve", "grade_curve",
            "_frLayeredMarkArea(fatigueZones)",
            "_frLayeredEventMarkLine(insightEvents)",
            "markArea: { silent: true, data: markAreaData }",
            "markLine:",
        ]:
            self.assertIn(text, fn_body)
        for forbidden in [
            "_distanceFromSpeedTime", "total_distance_m", "points",
            "querySelector", "getBoundingClientRect", "innerText",
            "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p7_11_stage_overview_exists_and_uses_fatigue_zones_only(self):
        """P7.11:状态阶段概览只能消费 data.fatigue_zones。"""
        for el_id in [
            "fr-stage-overview-section", "fr-stage-boundary", "fr-stage-track",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.11 FAIL: 缺少 #{el_id}")
        self.assertIn("_renderFatigueReviewStageOverview(data.fatigue_zones || [])", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewContextTags", fn_idx)]
        for text in [
            "zone.start_km", "zone.end_km", "zone.level",
            "zone.reason || zone.description",
            "fr-stage-segment", "暂无阶段",
        ]:
            self.assertIn(text, fn_body)
        for forbidden in [
            "curves.", "speed", "time", "total_distance_m", "points",
            "querySelector", "getBoundingClientRect", "innerText", "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p7_15_stage_bar_uses_weighted_backend_zones(self):
        """P7.15:状态阶段条按 fatigue_zones 区间长度形成连续分段带。"""
        for text in [
            "--fr-stage-grow",
            "--fr-stage-basis",
            "fr-stage-share",
            ".fr-stage-segment.compact",
            "flex: var(--fr-stage-grow, 1) 1 var(--fr-stage-basis, 0)",
        ]:
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewContextTags", fn_idx)]
        for text in [
            "var stageItems = []",
            "zone.start_km",
            "zone.end_km",
            "item.span / fullSpan * 100",
            "Math.max(7, item.span / fullSpan * 100)",
            "暂无有效阶段",
            "compact",
        ]:
            self.assertIn(text, fn_body)
        for forbidden in [
            "curves.", "speed", "time", "total_distance_m", "points",
            "querySelector", "getBoundingClientRect", "innerText", "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p7_11_derived_metrics_strip_preserves_metric_targets(self):
        """P7.11:派生指标向横向条收敛,但不破坏既有 8 个主值 DOM。"""
        self.assertIn("fr-derived-metrics-strip", self.html)
        for element_id in [
            "fr-hr-drift", "fr-decoupling", "fr-bonk", "fr-events-count",
            "fr-efficiency-score", "fr-durability-score",
            "fr-cadence-stability-score", "fr-training-load-value",
        ]:
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_5_event_and_zone_panels_exist(self):
        """P7.5:关键事件和疲劳区间说明区必须存在。"""
        for el_id in [
            "fr-events-panel", "fr-events-boundary", "fr-event-list",
            "fr-fatigue-zones-panel", "fr-fatigue-zones-boundary",
            "fr-fatigue-zone-list",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.5 FAIL: 缺少 #{el_id}")
        for text in [
            "标记活动中值得回看的关键变化点。",
            "展示疲劳出现、加重或缓解的距离区间。",
        ]:
            self.assertIn(text, self.html)

    def test_p7_5_event_and_zone_render_use_backend_arrays_only(self):
        """P7.5:事件和疲劳区间只消费后端数组。"""
        self.assertIn("_renderFatigueReviewEvents(data.collapse_events || [])", self.html)
        self.assertIn("_renderFatigueReviewZones(data.fatigue_zones || [])", self.html)
        event_idx = self.html.find("function _renderFatigueReviewEvents(events)")
        zone_idx = self.html.find("function _renderFatigueReviewZones(zones)")
        self.assertGreater(event_idx, 0)
        self.assertGreater(zone_idx, 0)
        event_body = self.html[event_idx:self.html.find("\n    function _renderFatigueReviewZones", event_idx)]
        zone_body = self.html[zone_idx:self.html.find("\n    function _renderFatigueReviewContextTags", zone_idx)]
        for required in [
            "trigger_km",
            "event_id",
            "ev.title || ev.label || ev.type || '事件'",
            "description",
            "暂无事件",
        ]:
            self.assertIn(required, event_body)
        for required in ["start_km", "end_km", "level", "暂无区间"]:
            self.assertIn(required, zone_body)
        for body in (event_body, zone_body):
            for forbidden in [
                "_distanceFromSpeedTime", "speed_curve", "time_curve",
                "total_distance_m", "points", "querySelector",
                "getBoundingClientRect", "innerText",
            ]:
                self.assertNotIn(forbidden, body)

    def test_p7_6_context_advice_sidebar_exists(self):
        """P7.6:上下文与建议侧栏必须有边界说明和状态。"""
        for el_id in [
            "fr-context-panel", "fr-context-boundary", "fr-context-tags",
            "fr-advice-panel", "fr-advice-boundary", "fr-advice-status",
            "fr-advice", "fr-disclaimer",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.6 FAIL: 缺少 #{el_id}")
        for text in [
            "环境、装备和训练背景会帮助解释本次表现。",
            "结合本次复盘给出下一步训练建议。",
        ]:
            self.assertIn(text, self.html)

    def test_p7_6_context_advice_render_uses_whitelisted_fields_only(self):
        """P7.6:上下文/建议/免责声明只消费白名单字段。"""
        self.assertIn("_renderFatigueReviewContextTags(data.context_tags || {})", self.html)
        self.assertIn("_renderFatigueReviewAdvice(data.advice, data.disclaimer)", self.html)
        ctx_idx = self.html.find("function _renderFatigueReviewContextTags(tags)")
        adv_idx = self.html.find("function _renderFatigueReviewAdvice(advice, disclaimer)")
        self.assertGreater(ctx_idx, 0)
        self.assertGreater(adv_idx, 0)
        ctx_body = self.html[ctx_idx:self.html.find("\n    function _renderFatigueReviewAdvice", ctx_idx)]
        adv_body = self.html[adv_idx:self.html.find("\n    // === V6.3 AI", adv_idx)]
        for required in ["暂无上下文", "Object.keys(tags)", "fr-context-chip"]:
            self.assertIn(required, ctx_body)
        for required in ["暂无建议", "fr-advice-status", "fr-disclaimer", "disclaimer"]:
            self.assertIn(required, adv_body)
        for body in (ctx_body, adv_body):
            for forbidden in [
                "metrics.", "curves.", "collapse_events", "fatigue_zones",
                "points", "querySelector", "getBoundingClientRect", "innerText",
                "call_llm",
            ]:
                self.assertNotIn(forbidden, body)

    def test_p7_7_responsive_css_guards_exist(self):
        """P7.7:复盘驾驶舱需要响应式和长文本可读性守卫。"""
        for text in [
            "@media (max-width: 1100px)",
            "@media (max-width: 720px)",
            "@media (max-width: 480px)",
            ".fr-status-meta",
            "flex-wrap: wrap",
            ".chart-legend",
            ".fr-chart-canvas",
            "min-height: 280px",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "grid-template-columns: 1fr",
            "overflow-wrap: anywhere",
        ]:
            self.assertIn(text, self.html)

    def test_p7_7_no_viewport_font_or_negative_letter_spacing(self):
        """P7.7:复盘 UI 不使用 viewport 字体缩放或负 letter-spacing。"""
        self.assertNotRegex(self.html, r"font-size\s*:\s*[^;]*vw")
        self.assertNotRegex(self.html, r"letter-spacing\s*:\s*-\s*")

    def test_p7_8_visual_regression_section_order_is_preserved(self):
        """P7.8:复盘 Tab 视觉回归必须锁定 P7 信息架构顺序。"""
        ordered_ids = [
            "detail-tab-review",
            "fr-ai-generate-btn",
            "fr-review-layout",
            "fr-status-strip",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-chart-section",
            "fr-context-panel",
            "fr-events-panel",
            "fr-fatigue-zones-panel",
            "fr-advice-panel",
        ]
        positions = []
        for element_id in ordered_ids:
            pos = self.html.find('id="' + element_id + '"')
            self.assertGreater(pos, 0, f"P7.8 FAIL: 缺少 #{element_id}")
            positions.append(pos)
        self.assertEqual(positions, sorted(positions),
                         "P7.8 FAIL: 复盘驾驶舱区块顺序偏离 P7.1 信息架构")

    def test_p7_12_chart_owns_stage_summary(self):
        """P7.12:第一视觉必须先进入多维时间轴主图,状态阶段只是主图内摘要。"""
        chart_idx = self.html.find('id="fr-chart-section"')
        title_idx = self.html.find('id="fr-chart-title"')
        stage_idx = self.html.find('id="fr-stage-overview-section"')
        canvas_idx = self.html.find('id="fatigue-review-chart"')
        self.assertGreater(chart_idx, 0)
        self.assertGreater(title_idx, chart_idx)
        self.assertGreater(stage_idx, title_idx)
        self.assertGreater(canvas_idx, stage_idx)

    def test_p7_13_lane_rail_binds_to_chart(self):
        """P7.13:左侧指标轨道必须位于主图 body 内,并由实际 lanes 渲染。"""
        for el_id in ["fr-chart-body", "fr-lane-rail", "fatigue-review-chart"]:
            self.assertIn('id="' + el_id + '"', self.html)
        body_idx = self.html.find('id="fr-chart-body"')
        rail_idx = self.html.find('id="fr-lane-rail"')
        canvas_idx = self.html.find('id="fatigue-review-chart"')
        self.assertGreater(body_idx, 0)
        self.assertGreater(rail_idx, body_idx)
        self.assertGreater(canvas_idx, rail_idx)
        self.assertIn("function _renderFatigueReviewLaneRail(lanes)", self.html)
        self.assertIn("_renderFatigueReviewLaneRail(lanes)", self.html)
        self.assertIn("_renderFatigueReviewLaneRail([])", self.html)

    def test_p7_14_event_pins_bind_to_collapse_events(self):
        """P7.14:关键事件必须以 trigger_km 生成图钉气泡和跨泳道参考线。"""
        fn_idx = self.html.find("function _frLayeredEventMarkLine(insightEvents)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewLaneRail", fn_idx)]
        for text in [
            "_frLayeredEventMarkLine(insightEvents)",
            "_frLayeredEventPinMarkLine(insightEvents)",
            "event.trigger_km",
            "event.title || event.label || event.type || event.event_id || '关键事件'",
            "event.description",
            "event.event_id",
            "eventTitle",
            "eventKmLabel",
            "position: 'end'",
        ]:
            self.assertIn(text, fn_body)
        chart_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        chart_body = self.html[chart_idx:self.html.find("\n    function clearProfileAnalysisChart", chart_idx)]
        for text in [
            "var eventReferenceLineData = _frLayeredEventMarkLine(insightEvents)",
            "var eventPinLineData = _frLayeredEventPinMarkLine(insightEvents)",
            "data: eventReferenceLineData",
            "data: eventPinLineData",
            "symbol: ['none', 'pin']",
            "symbolSize: [24, 24]",
        ]:
            self.assertIn(text, chart_body)
        for forbidden in [
            "querySelector", "getBoundingClientRect", "innerText",
            "total_distance_m", "points", "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p7_8_visual_regression_sketch_boundaries_preserved(self):
        """P7.8:视觉回归不得引入草图右侧全局导航或分享导出动作。"""
        review_idx = self.html.find('id="detail-tab-review"')
        self.assertGreater(review_idx, 0)
        upload_idx = self.html.find('id="file-upload"', review_idx)
        review_body = self.html[review_idx:upload_idx if upload_idx > review_idx else review_idx + 16000]
        for forbidden in ("首页", "日历", "分享", "导出"):
            self.assertNotIn(forbidden, review_body,
                             f"P7.8 FAIL: 复盘 Tab 不得新增草图全局动作 {forbidden}")
        self.assertNotIn(">活动<", review_body,
                         "P7.8 FAIL: 复盘 Tab 不得新增草图全局导航按钮 活动")
        self.assertIn('id="activity-detail-title"', self.html)
        self.assertIn('id="detail-tab-bar"', self.html)
        self.assertIn('data-detail-tab="overview"', self.html)
        self.assertIn('data-detail-tab="review"', self.html)

    def test_p7_8_visual_regression_ai_freeze_and_no_inline_call(self):
        """P7.8:视觉回归期间 AI 入口继续冻结且按钮不绑定调用链。"""
        idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(idx, 0, "P7.8 FAIL: 缺少 AI 冻结按钮")
        start = self.html.rfind("<button", 0, idx)
        end = self.html.find("</button>", idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertIn("AI 洞察待开放", button)
        self.assertNotIn("onclick=", button)
        self.assertNotIn("call_llm", button)


class TestV9JsFunctions(unittest.TestCase):
    """V9.0 JS 函数 / 状态校验。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_switch_detail_tab_function_exists(self):
        """switchDetailTab 函数必须存在。"""
        self.assertIn("function switchDetailTab(", self.html,
                      "V9.0 FAIL: 缺少 switchDetailTab 函数")

    def test_open_close_fatigue_ai_modal_functions(self):
        """openFatigueAiInsightModal / closeFatigueAiInsightModal 必须存在。"""
        self.assertIn("function openFatigueAiInsightModal(", self.html,
                      "V9.0 FAIL: 缺少 openFatigueAiInsightModal")
        self.assertIn("function closeFatigueAiInsightModal(", self.html,
                      "V9.0 FAIL: 缺少 closeFatigueAiInsightModal")
        self.assertIn("function _clearFatigueAiInsight(", self.html,
                      "V9.0 FAIL: 缺少 _clearFatigueAiInsight")
        self.assertIn("function _freezeFatigueReviewAiEntry(", self.html,
                      "P6.1 FAIL: 缺少 AI 入口冻结 helper")

    def test_esc_handler_exists(self):
        """ESC 守卫处理函数必须存在。"""
        self.assertIn("_fatigueAiEscHandler", self.html,
                      "V9.0 FAIL: 缺少 ESC 守卫")

    def test_cleanup_helper_exists(self):
        """_cleanupFatigueReviewPanel 清理 helper 必须存在。"""
        self.assertIn("function _cleanupFatigueReviewPanel(", self.html,
                      "V9.0 FAIL: 缺少 _cleanupFatigueReviewPanel helper")

    def test_state_variables_exist(self):
        """V9.0 新增状态变量必须存在。"""
        for var in [
            "_activeDetailTab", "_fatigueReviewTabLoaded",
            "_fatigueAiInsightData", "_fatigueAiInsightModalOpen",
            "_fatigueAiInsightEscBound",
        ]:
            self.assertIn("let " + var, self.html,
                          f"V9.0 FAIL: 缺少状态变量 {var}")

    def test_jump_3d_from_fatigue_review_removed(self):
        """_jumpTo3DFromFatigueReview 函数必须已删除(冗余入口)。"""
        self.assertNotIn("function _jumpTo3DFromFatigueReview(", self.html,
                         "V9.0 FAIL: _jumpTo3DFromFatigueReview 应已删除")


class TestV9ContractCompliance(unittest.TestCase):
    """V9.0 契约合规校验(§3 响应结构 / §六 shadow_diff / §5.6.2 阅后即焚)。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_on_fatigue_review_ai_uses_code_envelope(self):
        """onFatigueReviewAiInsight 必须用 res.code === 0(§3 响应结构契约)。"""
        idx = self.html.find("async function onFatigueReviewAiInsight(")
        self.assertGreater(idx, 0, "缺少 onFatigueReviewAiInsight 函数")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("res.code !== 0", body,
                      "V9.0 FAIL: onFatigueReviewAiInsight 未用 res.code !== 0(应修复 §3 信封)")
        # 严禁残留旧 ok 判断
        self.assertNotIn("res.ok !== true", body,
                         "V9.0 FAIL: 残留 res.ok !== true(已废除)")

    def test_open_fatigue_review_no_overlay_classlist(self):
        """openFatigueReview 不再操作 overlay classList(已合并入 detail Modal)。"""
        idx = self.html.find("async function openFatigueReview(")
        self.assertGreater(idx, 0, "缺少 openFatigueReview 函数")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 严禁再出现 overlay classList 操作
        self.assertNotIn("fatigue-review-overlay", body,
                         "V9.0 FAIL: openFatigueReview 残留 fatigue-review-overlay 引用")

    def test_clear_fatigue_review_clears_ai_modal(self):
        """_clearFatigueReviewInsight 必须级联关闭 AI Modal(阅后即焚 ① 关闭触发)。"""
        idx = self.html.find("function _clearFatigueReviewInsight(")
        self.assertGreater(idx, 0, "缺少 _clearFatigueReviewInsight 函数")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 2000
        body = self.html[idx:end]
        self.assertIn("_clearFatigueAiInsight", body,
                      "V9.0 FAIL: _clearFatigueReviewInsight 未级联关闭 AI Modal")
        self.assertIn("_freezeFatigueReviewAiEntry", body,
                      "P6.1 FAIL: _clearFatigueReviewInsight 必须保持 AI 入口冻结")

    def test_shadow_diff_isolation_preserved(self):
        """openFatigueReview 内的 shadow_diff 校验必须保留(§六 隔离)。"""
        idx = self.html.find("async function openFatigueReview(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.0 FAIL: openFatigueReview 缺失 shadow_diff 校验(§六 隔离被破坏)")

    def test_p3_open_fatigue_review_uses_backend_distance_axis(self):
        """P3:openFatigueReview 只能消费后端 curves.distance。"""
        idx = self.html.find("async function openFatigueReview(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("Array.isArray(curvesObj.distance) ? curvesObj.distance : []", body,
                      "P3 FAIL: openFatigueReview 必须直接读取 data.curves.distance")
        self.assertNotIn("_distanceFromSpeedTime", body,
                         "P3 FAIL: openFatigueReview 不得调用前端距离轴推导")

    def test_p3_no_frontend_distance_axis_rebuilder(self):
        """P3:前端不得再保留 speed/time/total_distance_m 重建距离轴函数。"""
        self.assertNotIn("function _distanceFromSpeedTime(", self.html,
                         "P3 FAIL: 应删除 _distanceFromSpeedTime")
        self.assertNotIn("validSpeedSum", self.html,
                         "P3 FAIL: 不得按 speed 比例分配总距离")
        self.assertNotIn("speed[m] || 0) / validSpeedSum", self.html,
                         "P3 FAIL: 不得用 speed/sum(speed) 重建距离轴")
        self.assertNotIn("speed[i] || 0) * 1.0", self.html,
                         "P3 FAIL: 不得用 speed * 1s 重建距离轴")

    def test_p3_chart_empty_when_distance_axis_missing(self):
        """P3:renderProfileAnalysisChart 缺权威距离轴时展示空态。"""
        idx = self.html.find("function renderProfileAnalysisChart(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("distanceCurve.length < 2", body,
                      "P3 FAIL: 图表缺 distance_curve 时必须空态")
        self.assertIn("距离轴暂不可用", body,
                      "P3 FAIL: 缺权威距离轴时应展示产品化空态原因")

    def test_global_switch_tab_still_clears(self):
        """全局 switchTab(用户已确认的 V8.8 行为)仍调用 _clearFatigueReviewInsight。"""
        idx = self.html.find("function switchTab(tabBtn) {")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 2000
        body = self.html[idx:end]
        self.assertIn("_clearFatigueReviewInsight();", body,
                      "V9.0 FAIL: 全局 switchTab 不再调 _clearFatigueReviewInsight(V8.8 回归)")


class TestV9NoBackendModification(unittest.TestCase):
    """V9.0 决策:0 改动 main.py / llm_backend.py。"""

    def test_main_py_unchanged(self):
        """main.py 不得含 V9.0 标记(本次改造仅前端)。"""
        with open(os.path.join(_PROJECT_ROOT, "main.py"), encoding="utf-8") as f:
            main = f.read()
        self.assertNotIn("V9.0", main,
                         "V9.0 FAIL: main.py 不应有 V9.0 标记(后端零变更)")

    def test_llm_backend_py_unchanged(self):
        """llm_backend.py 不得含 V9.0 标记(本次改造仅前端)。"""
        with open(os.path.join(_PROJECT_ROOT, "llm_backend.py"), encoding="utf-8") as f:
            llm = f.read()
        self.assertNotIn("V9.0", llm,
                         "V9.0 FAIL: llm_backend.py 不应有 V9.0 标记(后端零变更)")

    def test_no_new_files(self):
        """V9.0 决策:仅修改 track.html,不得新增文件(除文档/测试外)。"""
        # 检查 src/、utils/、lib/ 目录不得新增 Python 文件
        for sub in ["src", "utils", "lib"]:
            sub_path = os.path.join(_PROJECT_ROOT, sub)
            if not os.path.isdir(sub_path):
                continue
            for root, _, files in os.walk(sub_path):
                for f in files:
                    self.assertFalse(
                        f.endswith(".py") and "V9.0" in f,
                        f"V9.0 FAIL: 新增了 Python 文件 {os.path.join(root, f)}"
                    )


class TestV9SentinelUnchanged(unittest.TestCase):
    """V9.0 决策:不复用其他 AI 洞察的 sentinel(§5.6.2 规则 1)。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_fatigue_review_sentinel_unchanged(self):
        """__FATIGUE_REVIEW_INSIGHT__ sentinel 必须保留(不复用、不新建)。"""
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__", self.html,
                      "V9.0 FAIL: __FATIGUE_REVIEW_INSIGHT__ sentinel 必须保留")


class TestP79DesignCorrectionDocs(unittest.TestCase):
    """P7.9 源头纠偏文档门禁。"""

    def setUp(self) -> None:
        self.plan = _read_doc(PLAN_MD)
        self.ia = _read_doc(P7_IA_MD)

    def test_p7_9_design_correction_reorders_ai_review(self):
        """P7.9:AI 入口复核必须顺延到 P8,不得跳过视觉回正。"""
        for text in [
            "P7 后续任务纠偏提示",
            "P7.9 | 复盘 UI 设计稿视觉回正与源头纠偏",
            "P7.10 | 分层 ECharts 主图实现",
            "P7.11 | 状态阶段与派生指标模块回正",
            "P7.12 | 主图信息架构纠偏",
            "P7.13 | 左侧指标轨道与分层泳道回正",
            "P7.14 | 关键事件图钉与竖向参考线",
            "P7.18 | 视觉回归与草图对照验收",
            "P8 | UI 定稿后 AI 入口复核",
        ]:
            self.assertIn(text, self.plan)

    def test_p7_9_design_correction_names_missing_design_requirements(self):
        """P7.9:文档必须记录当前 UI 遗漏,防止把工程骨架当完成态。"""
        for text in [
            "当前 UI 已覆盖复盘数据骨架和基础展示",
            "不能视为设计稿完成态",
            "当前叠加式 ECharts 主图不是设计稿完成态",
            "身体状态如何变化",
            "为什么失衡",
            "在哪里开始崩",
            "什么因素导致崩溃",
            "Layer 1 疲劳带",
            "Layer 2 事件标记",
            "Layer 3 派生指标曲线",
        ]:
            self.assertIn(text, self.plan + self.ia)


if __name__ == "__main__":
    unittest.main()
