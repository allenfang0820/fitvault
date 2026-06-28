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

    def test_profile_manual_max_hr_controls_exist(self):
        """用户画像必须支持手动保存个人最大心率。"""
        self.assertIn('id="pf-max-hr"', self.html)
        self.assertIn('id="pf-max-hr-input"', self.html)
        self.assertIn('id="pf-save-max-hr-btn"', self.html)
        self.assertIn('class="profile-manual-control"', self.html)
        self.assertIn("width: 122px", self.html)
        self.assertIn("flex: 0 0 122px", self.html)
        self.assertIn("width: 64px", self.html)
        self.assertIn("flex: 0 0 64px", self.html)
        self.assertIn("flex: 0 0 46px", self.html)
        self.assertIn("appearance: textfield", self.html)
        self.assertIn("input::-webkit-inner-spin-button", self.html)
        self.assertIn("width: 46px", self.html)
        self.assertIn('function saveManualMaxHeartRate()', self.html)
        self.assertIn('save_user_profile(nextProfile)', self.html)
        self.assertIn("hasProfileMaxHr", self.html)
        self.assertIn("profileSourcePlatform === 'coros'", self.html)
        self.assertIn("preservedFields.indexOf('max_hr') < 0", self.html)
        self.assertIn("maxHrInput.disabled = isCorosSyncedMaxHr", self.html)
        self.assertIn("maxHrSaveBtn.disabled = isCorosSyncedMaxHr", self.html)
        self.assertIn("maxHrSaveBtn.textContent = '保存'", self.html)
        self.assertNotIn('id="pf-max-hr-source"', self.html)
        self.assertNotIn("来自画像同步", self.html)
        self.assertNotIn("已同步' : '保存'", self.html)

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

    def test_metric_card_user_copy_and_tooltips_exist(self):
        """指标卡标题应使用用户语言,并提供桌面 hover 说明。"""
        for text in [
            "后程效率变化",
            "能量断档风险",
            "fr-metric-info",
            "data-tooltip=\"看后半程心率是否比前半程更难控制",
            "data-tooltip=\"看这次运动给身体带来的整体刺激大小",
            "getFatigueReviewSportCopyGroup",
            "sport === 'mountaineering'",
        ]:
            self.assertIn(text, self.html)
        self.assertNotIn("<div class=\"lbl\">解耦率</div>", self.html)
        self.assertNotIn("<div class=\"lbl\">Bonk 风险</div>", self.html)

    def test_radar_card_uses_single_dimension_info_and_bottom_ai_button(self):
        """雷达图只在卡片标题提供维度说明,AI 洞察按钮固定在右下角。"""
        for text in [
            "radar-title-main",
            "radar-capability-info",
            "radar-info-letter",
            '<span class="radar-info-letter">i</span>',
            'aria-label="运动能力维度说明"',
            "耐力：近期训练负荷与持续运动能力",
            "恢复：HRV、休息和身体恢复线索",
            "心肺稳定：心率与速度或输出关系是否稳定",
            "阈值：可持续高强度能力",
            "爬升：上坡或爬升场景承受力",
            "无氧爆发：短时间高速度或高输出能力",
            ".profile-radar-card",
            "position: relative",
            ".radar-ai-btn",
            ".profile-radar-card .radar-ai-btn",
            ".tab-panel:not(.active) #radar-ai-insight-btn",
            "#panel-profile:not(.active) #radar-ai-insight-btn",
            "radarAiBtn.style.display = activePanel === 'profile' ? '' : 'none'",
            "bottom: 10px",
            "right: 12px",
            ".radar-capability-info::after",
            "top: calc(100% + 8px)",
            "bottom: auto",
            "text-transform: none",
        ]:
            self.assertIn(text, self.html)
        self.assertNotIn("radar-dim-label-layer", self.html)
        self.assertNotIn("RADAR_DIMENSION_TOOLTIPS", self.html)
        self.assertNotIn("function _renderRadarDimensionLabels(dimensions)", self.html)
        global_btn_idx = self.html.find(".radar-ai-btn {")
        scoped_btn_idx = self.html.find(".profile-radar-card .radar-ai-btn {")
        self.assertGreater(global_btn_idx, 0)
        self.assertGreater(scoped_btn_idx, global_btn_idx)
        global_btn_body = self.html[global_btn_idx:scoped_btn_idx]
        self.assertNotIn("position: absolute", global_btn_body)
        self.assertIn("position: absolute", self.html[scoped_btn_idx:self.html.find("}", scoped_btn_idx)])

    def test_radar_sport_switch_preserves_update_animation(self):
        """切换运动类型时雷达图应显式插值,让点和线产生可见过渡动画。"""
        fn_idx = self.html.find("function renderRadarChart(activityType, metricsData)")
        self.assertGreater(fn_idx, 0)
        body = self.html[fn_idx:self.html.find("async function renderPerformanceRadar()", fn_idx)]
        for text in [
            "var previousDimensions = _lastRadarDimensions",
            "var shouldAnimateRadar",
            "_animateRadarScores(",
            "_radarStartScores(previousDimensions, dimensions)",
            "_lastRadarDimensions = dimensions.map",
        ]:
            self.assertIn(text, body)
        for text in [
            "let _lastRadarDimensions = null",
            "let _radarAnimationFrame = null",
            "function _radarStartScores(previousDimensions, nextDimensions)",
            "function _animateRadarScores(chart, indicators, fromScores, toScores, dimensions, done)",
            "var duration = 650",
            "window.requestAnimationFrame(step)",
            "_setRadarChartOption(chart, indicators, frameScores, false, dimensions)",
            "id: 'performance-radar-series'",
            "id: 'performance-radar-profile'",
            "{ notMerge: false, lazyUpdate: false }",
        ]:
            self.assertIn(text, self.html)
        self.assertNotIn("radarChartInstance.setOption(option, true)", body)

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

    def test_radar_ai_error_modal_close_is_not_blocked_by_nested_modal(self):
        """雷达 AI 错误态不能在 body 内嵌套 .radar-ai-modal,否则会遮住关闭按钮。"""
        close_idx = self.html.find("function closeRadarAiInsightModal()")
        self.assertGreater(close_idx, 0)
        close_body = self.html[close_idx:self.html.find("\n    // §5.6 Modal 化:打开弹窗", close_idx)]
        self.assertIn("_clearRadarInsight();", close_body)
        self.assertNotIn("if (_radarInsightModalOpen)", close_body)

        render_idx = self.html.find("function _renderRadarInsightModal(data)")
        self.assertGreater(render_idx, 0)
        render_body = self.html[render_idx:self.html.find("\n    // === V9.0 §5.6 Modal 化:复盘 AI 洞察 Modal", render_idx)]
        self.assertIn('class="radar-ai-modal-error"', render_body)
        self.assertIn('role="alert"', render_body)
        self.assertNotIn('class="radar-ai-modal error"', render_body)
        self.assertIn(".radar-ai-modal-error", self.html)

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
            "fr-side-summary-panel", "fr-events-panel",
            "fr-side-summary-list", "fr-event-list",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P4 FAIL: 复盘主页面缺 #{el_id}")
        for text in ["关键证据", "补充证据", "多维时间轴分析", "本次复盘概览", "读图解释"]:
            self.assertIn(text, self.html)

    def test_p8_1_ai_entry_is_opened_minimally(self):
        """P8.1:UI 定稿后 AI 洞察入口最小闭环打开。"""
        idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(idx, 0, "P6.1 FAIL: 缺少 AI 按钮")
        start = self.html.rfind("<button", 0, idx)
        end = self.html.find("</button>", idx)
        button = self.html[start:end]
        self.assertNotIn("disabled", button)
        self.assertNotIn('aria-disabled="true"', button)
        self.assertIn("AI 洞察", button)
        self.assertIn("✨", button)
        self.assertIn('onclick="onFatigueReviewAiInsight()"', button)
        self.assertNotIn("call_llm", button)
        title_idx = self.html.find("本次复盘概览")
        overview_idx = self.html.find('id="fr-overview-dimensions"')
        self.assertGreater(idx, title_idx)
        self.assertLess(idx, overview_idx)

    def test_p7_2_summary_band_exists(self):
        """P7.2:复盘 Tab 内部顶部分析摘要带必须存在。"""
        for el_id in [
            "fr-status-strip", "fr-summary", "fr-summary-desc",
            "fr-data-source-pill", "fr-distance-axis-pill",
            "fr-curve-status-pill", "fr-risk-pill",
            "fr-event-pill", "fr-ai-status-pill", "fr-overview-dimensions",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.2 FAIL: 摘要带缺 #{el_id}")
        for text in ["本次复盘概览", "汇总本次活动的疲劳、风险和建议状态。", "AI 可用"]:
            self.assertIn(text, self.html)

    def test_p8_4_overview_dimension_cards_exist(self):
        """P8.4:本次复盘概览承载四维总览卡。"""
        for key in (
            "overall_stability",
            "fatigue_progression",
            "risk_triggers",
            "context_impact",
        ):
            self.assertIn('data-fr-ai-dim="' + key + '"', self.html)
        for text in ("全程稳定性", "疲劳阶段", "风险触发", "外部影响"):
            self.assertIn(text, self.html)

    def test_review_placeholder_header_is_removed(self):
        """复盘顶部旧占位头部不得占用可视空间。"""
        review_idx = self.html.find('id="detail-tab-review"')
        layout_idx = self.html.find('id="fr-review-layout"', review_idx)
        self.assertGreater(review_idx, 0)
        self.assertGreater(layout_idx, review_idx)
        review_lead = self.html[review_idx:layout_idx]
        self.assertNotIn("review-tab-header", review_lead)
        self.assertNotIn("fr-subtitle", review_lead)
        self.assertNotIn("正在加载复盘数据", review_lead)

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
        """P7.3:指标驾驶舱渲染只消费 metrics 和 sportType 文案分组,不得从曲线/DOM 推导业务状态。"""
        idx = self.html.find("function _renderFatigueReviewMetrics(metrics, sportType)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewDimensions", idx)
        body = self.html[idx:end]
        for required in [
            "metrics.hr_drift", "metrics.decoupling", "metrics.bonk_risk",
            "metrics.events", "metrics.efficiency", "metrics.durability",
            "metrics.cadence_stability", "metrics.training_load",
            "getFatigueReviewSportCopyGroup(sportType)",
        ]:
            self.assertIn(required, body)
        for forbidden in [
            "window._lastFatigueReviewCurves", "curves.", "distance",
            "total_distance_m", "points", "querySelector",
            "getBoundingClientRect", "innerText",
        ]:
            self.assertNotIn(forbidden, body)

    def test_p5_cycling_metric_cards_use_power_and_pedaling_profile(self):
        """P5-cycling:骑行指标卡展示功率变异和踏频稳定性,跑步卡片保持原语义。"""
        defs_start = self.html.find("function _fatigueReviewMetricCardDefs")
        render_start = self.html.find("function _renderFatigueReviewMetrics(metrics, sportType)")
        self.assertGreater(defs_start, 0)
        self.assertGreater(render_start, defs_start)
        defs_body = self.html[defs_start:render_start]
        render_body = self.html[render_start:self.html.find("\n    function _renderFatigueReviewDimensions", render_start)]

        self.assertIn("function _fatigueReviewMetricSportMode(sportType)", self.html)
        self.assertIn("sport === 'cycling' || sport === 'road_cycling' || sport === 'mountain_biking'", self.html)
        for text in [
            "withSlot('hr_drift', 'power_variability', '输出节奏'",
            "withSlot('decoupling', 'efficiency', '功率效率'",
            "withSlot('bonk_risk', 'durability', '后程功率保持'",
            "withSlot('events', 'events', '状态下滑点'",
            "withSlot('efficiency', 'hr_drift', '心肺对照'",
            "withSlot('durability', 'pedaling_stability', '踩踏组织'",
            "withSlot('cadence_stability', 'training_load', '相对强度'",
            "withSlot('training_load', 'bonk_risk', '能量风险'",
            "withSlot('cadence_stability', 'cadence_stability', '步频稳定性'",
            "var powerVar = metrics.power_variability || {}",
            "var pedaling = metrics.pedaling_stability || {}",
            "unstable:'明显波动'",
            "poor:'波动很大'",
            "var effCycling = metrics.efficiency || {}",
            "var durCycling = metrics.durability || {}",
            "_fatigueReviewPowerVariabilityHeadline(powerVar, pvMissing)",
            "_fatigueReviewPowerVariabilityEvidence(powerVar, pvMissing)",
            "_fatigueReviewPedalingStabilityEvidence(pedaling, pedalingMissing)",
            "_fatigueReviewPowerEfficiencyEvidence(effCycling, effMissingCycling)",
            "_fatigueReviewPowerRetentionEvidence(durCycling, durMissingCycling)",
        ]:
            self.assertIn(text, defs_body + render_body)

        cycling_start = defs_body.find("if (sportMode === 'cycling')")
        cycling_end = defs_body.find("\n        return [", cycling_start + 1)
        cycling_block = defs_body[cycling_start:cycling_end]
        self.assertNotIn("withSlot('bonk_risk', 'cadence_stability'", cycling_block)
        self.assertNotIn("'心率漂移'", cycling_block)
        self.assertNotIn("'踏频稳定性'", cycling_block)
        self.assertNotIn("'训练负荷'", cycling_block)
        self.assertNotIn("后程保持参考", cycling_block)
        self.assertNotIn("当前不等同于 power-based durability", cycling_block)
        for forbidden in [
            "summary.",
            "curves.",
            "chartPayload",
            "getOption",
            "querySelector",
            "innerText",
            "'VI ' + _fatigueReviewMetricNumber(powerVar.vi, 2)",
            "normalized_power / avg_power",
            "avg_power / normalized_power",
            "avg_power / avg_hr",
            "tail_power / head_power",
            "power_per_hr =",
            "power_retention_pct =",
            "curves.cadence",
        ]:
            self.assertNotIn(forbidden, render_body)

    def test_p7_4_chart_container_keeps_only_compact_title(self):
        """P7.4:主图容器只保留紧凑标题，不展示说明和图例。"""
        for el_id in [
            "fr-chart-section", "fr-chart-title",
            "fr-chart-axis-note", "fatigue-review-chart",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.4 FAIL: 主图区缺 #{el_id}")
        self.assertIn("多维时间轴分析", self.html)
        for text in [
            'id="fr-chart-subtitle"',
            'id="fr-chart-boundary"',
            'id="fr-chart-legend"',
            "按距离展开本次活动的关键变化",
            "心率、配速、海拔和疲劳阶段会在同一条距离轴上对照显示。",
        ]:
            self.assertNotIn(text, self.html)

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
        self.assertIn("sport_type: data.sport_type", body)
        self.assertIn("distance_curve: Array.isArray(curvesObj.distance) ? curvesObj.distance : []", body)
        self.assertIn("hr_curve:        data.curves && data.curves.hr", body)
        self.assertIn("power_curve:     data.curves && data.curves.power", body)
        self.assertIn("cadence_curve:   data.curves && data.curves.cadence", body)
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
            "_distanceFromSpeedTime", "total_distance_m /", "speed *", "speed_curve",
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
        lane_defs = self.html[
            self.html.find("function _fatigueReviewChartLaneDefs"):
            self.html.find("\n    function _renderFatigueReviewLayeredEcharts")
        ]
        for text in [
            "var grid = []",
            "var xAxis = []",
            "var yAxis = []",
            "var laneDefs = _fatigueReviewChartLaneDefs(activityData)",
            "grid.push({",
            "xAxis.push({",
            "yAxis.push({",
            "xAxisIndex: laneIndex",
            "yAxisIndex: laneIndex",
            "axisPointer: { link: [{ xAxisIndex: 'all' }] }",
            "_frRobustAxisRange(pairedData",
            "min: lane.axisMin != null ? lane.axisMin : (shouldPlayIntroAnimation",
            "max: lane.axisMax != null ? lane.axisMax : (shouldPlayIntroAnimation",
            "grid: grid",
            "xAxis: xAxis",
            "yAxis: yAxis",
        ]:
            self.assertIn(text, fn_body)
        self.assertIn("robustAxis: { hardMin: -35, hardMax: 35, minSpan: 4 }", lane_defs)

    def test_p7_10_layered_echarts_uses_backend_curves_and_layers(self):
        """P7.10:分层主图消费后端曲线、展示曲线、疲劳带和事件。"""
        fn_idx = self.html.find("function _renderFatigueReviewLayeredEcharts")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function clearProfileAnalysisChart", fn_idx)]
        lane_defs = self.html[
            self.html.find("function _fatigueReviewChartLaneDefs"):
            self.html.find("\n    function _renderFatigueReviewLayeredEcharts")
        ]
        for text in [
            "hr_curve", "pace_curve", "altitude_curve",
            "efficiency_curve", "gap_pace_curve", "grade_curve",
            "_frLayeredMarkArea(fatigueZones)",
            "_frLayeredEventMarkLine(insightEvents)",
            "markArea: { silent: true, data: markAreaData }",
            "markLine:",
        ]:
            self.assertIn(text, fn_body + lane_defs)
        for forbidden in [
            "_distanceFromSpeedTime", "total_distance_m", "points",
            "querySelector", "getBoundingClientRect", "innerText",
            "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p4_cycling_layered_echarts_uses_power_and_cadence_mode(self):
        """P4-cycling:骑行主图使用功率/踏频 lane,不默认使用跑步配速 lane。"""
        lane_start = self.html.find("function _fatigueReviewChartLaneDefs")
        chart_start = self.html.find("\n    function _renderFatigueReviewLayeredEcharts", lane_start)
        self.assertGreater(lane_start, 0)
        self.assertGreater(chart_start, lane_start)
        lane_defs = self.html[lane_start:chart_start]
        self.assertIn("function _fatigueReviewChartSportMode(sportType)", self.html)
        self.assertIn("normalized === 'cycling'", self.html)
        self.assertIn("normalized === 'road_cycling'", self.html)
        self.assertIn("normalized === 'mountain_biking'", self.html)
        self.assertIn("if (sportMode === 'cycling')", lane_defs)
        self.assertIn("key: 'power_curve'", lane_defs)
        self.assertIn("name: '功率'", lane_defs)
        self.assertIn("unit: 'W'", lane_defs)
        self.assertIn("key: 'cadence_curve'", lane_defs)
        self.assertIn("name: '踏频'", lane_defs)
        self.assertIn("unit: 'rpm'", lane_defs)

        cycling_start = lane_defs.find("if (sportMode === 'cycling')")
        cycling_end = lane_defs.find("\n        return [", cycling_start + 1)
        cycling_block = lane_defs[cycling_start:cycling_end]
        for forbidden in [
            "key: 'pace_curve'",
            "key: 'gap_pace_curve'",
            "key: 'efficiency_curve'",
            "displayAsPace: true",
            "1000 /",
            "speedMps",
        ]:
            self.assertNotIn(forbidden, cycling_block)

    def test_fatigue_review_main_chart_intro_animates_line_y_once(self):
        """复盘主图区加载后只播一次 Y 轴方向折线过渡,resize/图层开关不重播。"""
        self.assertIn("renderProfileAnalysisChart(chartPayload, 'fatigue-review-chart', { introAnimation: true })", self.html)
        self.assertIn("function _frPlayFatigueReviewChartIntro(chart, option, lineSeriesMap, done)", self.html)
        self.assertIn("function _frInterpolateLineData(fromData, toData, progress)", self.html)
        self.assertIn("return [targetPoint[0], fromY + (targetY - fromY) * progress]", self.html)
        self.assertIn("var shouldPlayIntroAnimation = targetId === 'fatigue-review-chart' && renderOptions.introAnimation === true", self.html)
        self.assertIn("introLineSeriesMap[lineSeriesIndex]", self.html)
        self.assertIn("seriesType: def.seriesType || 'line'", self.html)
        self.assertIn("if (lane.seriesType === 'bar')", self.html)
        self.assertIn("_frCancelFatigueReviewChartIntro()", self.html)
        toggle_idx = self.html.find("function onFatigueReviewLayerToggle")
        resize_idx = self.html.find("function refreshFatigueReviewChartWhenVisible")
        self.assertGreater(toggle_idx, 0)
        self.assertGreater(resize_idx, 0)
        toggle_body = self.html[toggle_idx:self.html.find("\n    function refreshFatigueReviewChartWhenVisible", toggle_idx)]
        resize_body = self.html[resize_idx:self.html.find("\n    function _resizeFatigueReviewChartWhenStable", resize_idx)]
        self.assertNotIn("introAnimation", toggle_body)
        self.assertNotIn("introAnimation", resize_body)

    def test_p7_11_stage_overview_exists_and_uses_fatigue_zones_only(self):
        """P7.11:状态阶段概览只能消费 data.fatigue_zones。"""
        for el_id in [
            "fr-stage-overview-section", "fr-stage-boundary", "fr-stage-track",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P7.11 FAIL: 缺少 #{el_id}")
        self.assertIn("var reviewTotalDistanceKm = _fatigueReviewTotalDistanceKm(data)", self.html)
        self.assertIn("_renderFatigueReviewStageOverview(data.fatigue_zones || [], data.sport_type, reviewTotalDistanceKm, data.metrics || {}, data.collapse_events || [])", self.html)
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _fatigueReviewContextFactorCopy", fn_idx)]
        for text in [
            "zone.start_km", "zone.end_km", "zone.level",
            "if (zone.startup_trimmed) continue",
            "_fatigueReviewZoneDisplayCopy(zone, sportGroup, totalDistanceKm)",
            "_fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, stageItems.length)",
            "fr-stage-segment", "_fatigueReviewHasRiskSignals(metrics || {}, events || [])",
            "无持续压力区间", "有风险线索", "状态平稳", "平稳完成",
        ]:
            self.assertIn(text, fn_body)
        self.assertNotIn("轻松完成", fn_body)
        for forbidden in [
            "curves.", "speed", "time", "total_distance_m", "points",
            "querySelector", "getBoundingClientRect", "innerText", "call_llm",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_p2_stage_bar_hover_explains_raw_fragments(self):
        """P2:阶段条 hover/说明应解释原始片段与右侧摘要的关系。"""
        for text in [
            "阶段条展示压力变化；没有压力区间时表示本次整体更平稳。",
            "阶段条保留多个原始片段；右侧状态区间已将碎片合并为阅读摘要。",
            "function _fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, fragmentCount)",
            "这是系统识别到的原始片段之一",
            "这是系统识别到的一个原始状态片段",
            "不代表身体状态在该公里点突然变化",
            "右侧状态区间摘要",
            "title=\"' + safeHtml(tooltip) + '\"",
            "aria-label=\"' + safeHtml(title + '，' + start + ' 到 ' + end + ' 公里。' + tooltip) + '\"",
        ]:
            self.assertIn(text, self.html)
        fn_idx = self.html.find("function _fatigueReviewStageTooltip(zone, sportGroup, totalDistanceKm, fragmentCount)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _renderFatigueReviewStageOverview", fn_idx)]
        for text in [
            "配速、心率和恢复段",
            "爬升、路况和心率",
            "爬升、补给和停歇",
            "心率、坡度和功率输出",
        ]:
            self.assertIn(text, self.html)
        for forbidden in [
            "speed", "time", "points", "querySelector",
            "getBoundingClientRect", "innerText", "echarts",
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
        fn_idx = self.html.find("function _renderFatigueReviewStageOverview(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(fn_idx, 0)
        fn_body = self.html[fn_idx:self.html.find("\n    function _fatigueReviewContextFactorCopy", fn_idx)]
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
        for text in [
            "function _fatigueReviewStageStatusHtml(tone, title, rangeText, tagText, desc)",
            "fr-stage-segment solo",
            ".fr-stage-segment.solo",
            "_fatigueReviewStageStatusHtml('stable', '状态平稳'",
        ]:
            self.assertIn(text, self.html)
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
            "对应主图上的关键图钉，用来定位值得回看的位置；不是单点结论。",
            "对应主图上方的状态阶段带，帮助理解压力持续出现的路段。",
        ]:
            self.assertIn(text, self.html)

    def test_p7_5_event_and_zone_render_use_backend_arrays_only(self):
        """P7.5:事件和疲劳区间只消费后端数组,sportType 仅用于文案分组。"""
        self.assertIn("var hasSustainedZone = _fatigueReviewHasSustainedZone(data.fatigue_zones || [], reviewTotalDistanceKm)", self.html)
        self.assertIn("_renderFatigueReviewEvents(data.collapse_events || [], data.sport_type, hasSustainedZone)", self.html)
        self.assertIn("_renderFatigueReviewZones(data.fatigue_zones || [], data.sport_type, reviewTotalDistanceKm, data.metrics || {}, data.collapse_events || [])", self.html)
        event_idx = self.html.find("function _renderFatigueReviewEvents(events, sportType, hasSustainedZone)")
        zone_idx = self.html.find("function _renderFatigueReviewZones(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(event_idx, 0)
        self.assertGreater(zone_idx, 0)
        event_body = self.html[event_idx:self.html.find("\n    function _renderFatigueReviewZones", event_idx)]
        zone_body = self.html[zone_idx:self.html.find("\n    function _fatigueReviewContextFactorCopy", zone_idx)]
        for required in [
            "trigger_km",
            "event_id",
            "_fatigueReviewEventTitle(ev)",
            "_fatigueReviewEventDisplayCopy(ev, sportGroup, hasSustainedZone)",
            "状态平稳",
        ]:
            self.assertIn(required, event_body)
        for required in [
            "_fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)",
            "_fatigueReviewHasRiskSignals(metrics || {}, events || [])",
            "summaryItems.slice(0, 3)",
            "sourceCount",
            "无持续压力区间 · 有风险线索",
            "无压力区间",
        ]:
            self.assertIn(required, zone_body)
        self.assertNotIn("轻松跑可视为稳定完成", zone_body)
        self.assertIn("if (zone.startup_trimmed) return null", self.html)
        for body in (event_body, zone_body):
            for forbidden in [
                "_distanceFromSpeedTime", "speed_curve", "time_curve",
                "total_distance_m", "points", "querySelector",
                "getBoundingClientRect", "innerText",
            ]:
                self.assertNotIn(forbidden, body)
        for forbidden_text in [
            "fatigue_zones 标记",
            "medium 区间",
            "high 区间",
            "暂无区间说明",
            "暂无阶段说明",
        ]:
            self.assertNotIn(forbidden_text, self.html)

    def test_p0_sustained_zone_display_semantics(self):
        """P0:覆盖大部分全程的状态区间应显示为整体状态,避免误导为某个点开始吃力。"""
        for text in [
            "function _fatigueReviewTotalDistanceKm(data)",
            "curves.total_distance_m",
            "Array.isArray(curves.distance) ? curves.distance : []",
            "function _fatigueReviewZoneCoverageState(zone, totalDistanceKm)",
            "var coverage = (end - start) / total",
            "var startsEarly = start <= Math.max(0.5, total * 0.1)",
            "coverage >= 0.7 && startsEarly",
            "FATIGUE_REVIEW_SUSTAINED_ZONE_COPY",
            "整体偏吃力",
            "本次大部分路段都处在较吃力状态，建议重点看心率、配速和恢复段。",
            "本次大部分路段体能压力偏高，建议重点看爬升、补给和停歇安排。",
        ]:
            self.assertIn(text, self.html)
        coverage_idx = self.html.find("function _fatigueReviewZoneCoverageState(zone, totalDistanceKm)")
        self.assertGreater(coverage_idx, 0)
        coverage_body = self.html[coverage_idx:self.html.find("\n    function _fatigueReviewSustainedZoneCopy", coverage_idx)]
        for forbidden in [
            "speed", "time", "points", "querySelector",
            "getBoundingClientRect", "innerText", "echarts",
        ]:
            self.assertNotIn(forbidden, coverage_body)

    def test_p0b_sustained_zone_event_anchor_is_softened(self):
        """P0-b:全程型区间下,事件说明应弱化为参考点,但仍保留 trigger_km。"""
        for text in [
            "FATIGUE_REVIEW_SUSTAINED_EVENT_COPY",
            "function _fatigueReviewHasSustainedZone(zones, totalDistanceKm)",
            "function _fatigueReviewEventDisplayCopy(ev, sportGroup, hasSustainedZone)",
            "_fatigueReviewEventDisplayCopy(ev, sportGroup, hasSustainedZone)",
            "这个位置是系统识别到的参考点；本次状态压力更像是在大部分路段持续存在，建议结合整段配速、心率和恢复段回看。",
            "这个位置是系统识别到的参考点；本次体能压力更像在较长路段中持续累积，建议结合爬升、补给和停歇安排回看。",
            "return _fatigueReviewEventCopy(ev, sportGroup)",
        ]:
            self.assertIn(text, self.html)
        event_idx = self.html.find("function _renderFatigueReviewEvents(events, sportType, hasSustainedZone)")
        self.assertGreater(event_idx, 0)
        event_body = self.html[event_idx:self.html.find("\n    function _renderFatigueReviewZones", event_idx)]
        self.assertIn("ev.trigger_km != null ? Number(ev.trigger_km).toFixed(1) + ' km' : '?'", event_body)
        self.assertIn("safeHtml(type) + ' · ' + safeHtml(km)", event_body)
        for forbidden in [
            "_distanceFromSpeedTime", "speed_curve", "time_curve",
            "points", "querySelector", "getBoundingClientRect",
            "innerText", "markLine",
        ]:
            self.assertNotIn(forbidden, event_body)

    def test_p3_event_and_zone_relation_copy_is_unified(self):
        """P3:事件点与状态区间的关系说明应统一且用户化。"""
        for text in [
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
            "先看主图：这里汇总当前最值得回看的风险、图钉和状态区间。",
        ]:
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
        for forbidden in [
            "speed", "time", "points", "querySelector",
            "getBoundingClientRect", "innerText", "echarts",
        ]:
            self.assertNotIn(forbidden, fn_body)

    def test_pressure_event_copy_not_confused_with_hr_drift_metric(self):
        """状态区间事件不应命名成心率漂移，避免和 hr_drift 指标冲突。"""
        for text in [
            "状态压力开始上来",
            "它是状态区间起点，不等同于心率漂移指标。",
            "状态压力上升",
        ]:
            self.assertIn(text, self.html)
        for text in [
            "漂移开始",
            "心率压力开始上来",
            "FATIGUE_DRIFT_START",
        ]:
            self.assertNotIn(text, self.html)

    def test_p1_zone_summary_items_reduce_fragmented_zones(self):
        """P1:右侧状态区间应先摘要化,避免逐条铺开碎片区间。"""
        for text in [
            "function _fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)",
            "function _fatigueReviewValidZoneItems(zones)",
            "function _fatigueReviewMergeZoneItems(items, totalDistanceKm)",
            "FATIGUE_REVIEW_FRAGMENTED_ZONE_COPY",
            "多段波动",
            "sourceCount",
            "由 ' + item.sourceCount + ' 个状态片段合并",
            "summaryItems.slice(0, 3)",
            "前段开始吃力",
            "中后段压力持续存在",
            "末段状态下滑更明显",
            "末段状态变化更明显，不能单独判断为后程功率保持下降。",
        ]:
            self.assertIn(text, self.html)
        summary_idx = self.html.find("function _fatigueReviewZoneSummaryItems(zones, sportType, totalDistanceKm)")
        render_idx = self.html.find("function _renderFatigueReviewZones(zones, sportType, totalDistanceKm, metrics, events)")
        self.assertGreater(summary_idx, 0)
        self.assertGreater(render_idx, 0)
        summary_body = self.html[summary_idx:self.html.find("\n    function _fatigueReviewEventKind", summary_idx)]
        render_body = self.html[render_idx:self.html.find("\n    function _renderFatigueReviewStageOverview", render_idx)]
        self.assertIn("return [{", summary_body)
        self.assertIn("title: sportGroup === 'cycling' ? '整体参考区间' : '整体偏吃力'", summary_body)
        self.assertIn("title: '多段波动'", summary_body)
        self.assertIn("_fatigueReviewZoneSummaryFromItem(item, sportGroup, totalDistanceKm)", summary_body)
        self.assertNotIn("zones.map(function(zone", render_body)
        for forbidden in [
            "_distanceFromSpeedTime", "speed_curve", "time_curve",
            "points", "querySelector", "getBoundingClientRect",
            "innerText", "echarts",
        ]:
            self.assertNotIn(forbidden, summary_body)
            self.assertNotIn(forbidden, render_body)

    def test_p4_review_copy_regression_real_world_acceptance_contract(self):
        """P4:P0-P3 文案应一致,运动类型不串味,旧开发语言不回流。"""
        for text in [
            "整体偏吃力",
            "这个位置是系统识别到的参考点",
            "多段波动",
            "由 ' + item.sourceCount + ' 个状态片段合并",
            "阶段条展示压力变化；没有压力区间时表示本次整体更平稳。",
            "不代表身体状态在该公里点突然变化",
            "事件是点，区间是段",
            "两者都是回看线索，不是精确结论",
            "本次状态整体平稳，未识别到明显压力转折点或持续压力路段。",
            "事件点",
            "参考位置：",
            "参考区间：这段状态变化较明显，需结合功率、踏频、心率和地形判断。",
            "不直接等同于输出下降或体能下降",
        ]:
            self.assertIn(text, self.html)
        for text in [
            "配速、心率和恢复段",
            "爬升、补给和停歇",
            "心率、坡度和功率",
            "这个图钉表示能量断档风险窗口起点",
            "这个图钉表示乏力风险窗口起点",
            "这个图钉表示后端识别到的风险窗口起点",
        ]:
            self.assertIn(text, self.html)
        forbidden_visible_copy = [
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
        ]
        for text in forbidden_visible_copy:
            self.assertNotIn(text, self.html)

    def test_p8_1_context_factors_sidebar_exists_and_advice_moves_to_ai_modal(self):
        """P8.1:上下文标签保留在读图解释,建议只留在 AI 洞察 Modal。"""
        for el_id in [
            "fr-side-summary-panel", "fr-side-summary-list",
            "fr-ai-advice", "fr-ai-disclaimer",
        ]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"P8.1 FAIL: 缺少 #{el_id}")
        for text in [
            "影响因素",
            "温度偏高，心率更容易上浮",
        ]:
            self.assertIn(text, self.html)
        for removed in ("fr-advice-panel", "fr-advice-boundary", "fr-advice-status", 'id="fr-advice"'):
            self.assertNotIn(removed, self.html)
        for text in [
            'id="fr-context-panel"',
            'id="fr-context-tags"',
            "本次活动未携带上下文标签",
            "暂无上下文",
        ]:
            self.assertNotIn(text, self.html)

    def test_p8_1_context_factors_render_uses_whitelisted_fields_only(self):
        """P8.1:影响因素/建议/免责声明只消费白名单字段。"""
        self.assertIn("var contextTags = data.context_tags || {}", self.html)
        self.assertIn("_renderFatigueReviewContextFactors(contextTags)", self.html)
        self.assertIn("_renderFatigueReviewAdvice(data.advice, data.disclaimer)", self.html)
        ctx_idx = self.html.find("function _renderFatigueReviewContextFactors(tags)")
        adv_idx = self.html.find("function _renderFatigueReviewAdvice(advice, disclaimer)")
        self.assertGreater(ctx_idx, 0)
        self.assertGreater(adv_idx, 0)
        ctx_body = self.html[ctx_idx:self.html.find("\n    function _renderFatigueReviewAdvice", ctx_idx)]
        adv_body = self.html[adv_idx:self.html.find("\n    // === V6.3 AI", adv_idx)]
        for required in ["Object.keys(tags)", "fr-context-factor", "影响因素"]:
            self.assertIn(required, ctx_body)
        for required in ["主页面不再重复展示建议", "AI 洞察弹窗", "return;"]:
            self.assertIn(required, adv_body)
        for body in (ctx_body, adv_body):
            for forbidden in [
                "metrics.", "curves.", "collapse_events", "fatigue_zones",
                "points", "querySelector", "getBoundingClientRect", "innerText",
                "call_llm",
            ]:
                self.assertNotIn(forbidden, body)

    def test_p8_1_context_overview_uses_product_copy_not_raw_tags(self):
        """P8.1:外部影响概览卡片不得裸露 context_tags 的英文标签和原始字段。"""
        self.assertIn("function _fatigueReviewContextOverviewComment(tags)", self.html)
        idx = self.html.find("function _buildFatigueReviewOverviewDimensions(data)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _fatigueReviewContextOverviewComment", idx)
        body = self.html[idx:end]
        self.assertIn("var contextComment = _fatigueReviewContextOverviewComment(contextTags)", body)
        self.assertIn("? contextComment", body)
        self.assertNotIn("key + ': ' + String(contextTags[key])", body)
        self.assertNotIn(".slice(0, 24)", body)
        helper = self.html[end:self.html.find("\n    function _buildFatigueReviewOverviewDimensionsFromAi", end)]
        for text in (
            "_fatigueReviewContextFactorCopy(key, tags[key])",
            "copies.slice(0, 2).join('；')",
            "可作为解释本次波动的背景",
        ):
            self.assertIn(text, helper)

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
            "fr-review-layout",
            "fr-status-strip",
            "fr-ai-generate-btn",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-chart-section",
            "fr-side-summary-panel",
            "fr-events-panel",
            "fr-fatigue-zones-panel",
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

    def test_lane_rail_titles_have_tooltips(self):
        """折线图泳道标题应复用圆圈 i tooltip 解释复杂指标。"""
        for text in [
            "fr-lane-rail-label",
            "fr-lane-rail-info",
            ".fr-lane-rail-info::after",
            ".fr-derived-metrics-strip .metric-card:first-child .fr-metric-info::after",
            ".fr-capacity-metrics-strip .metric-card:first-child .fr-metric-info::after",
            "lane.tooltip",
            "tooltip: def.tooltip || ''",
            "把上坡和下坡影响折算进去后的配速",
            "用速度和心率的关系观察推进效率",
            "显示路线所处高度变化",
            "显示当前路段的上坡或下坡程度",
            "把坡度、速度和持续时间合成的地形压力参考",
        ]:
            self.assertIn(text, self.html)
        for text in [
            "fr-layer-toggle-info",
            'aria-label="坡度修正配速说明"',
            'aria-label="效率说明"',
            'aria-label="海拔说明"',
            'aria-label="坡度说明"',
            'aria-label="地形负荷说明"',
        ]:
            self.assertNotIn(text, self.html)

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

    def test_p8_1_visual_regression_ai_entry_has_no_inline_llm_payload(self):
        """P8.1:AI 入口可点击,但按钮不内联 call_llm 或事实 payload。"""
        idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(idx, 0, "P8.1 FAIL: 缺少 AI 按钮")
        start = self.html.rfind("<button", 0, idx)
        end = self.html.find("</button>", idx)
        button = self.html[start:end]
        self.assertNotIn("disabled", button)
        self.assertNotIn('aria-disabled="true"', button)
        self.assertIn('onclick="onFatigueReviewAiInsight()"', button)
        self.assertNotIn("call_llm", button)

    def test_p8_3_ai_dimension_label_fallback_uses_new_semantics(self):
        """P8.3:AI 维度展示兜底必须使用新四维中文语义。"""
        self.assertIn("function _fatigueReviewAiDimensionLabel(key, fallback)", self.html)
        for text in (
            "overall_stability: '全程稳定性'",
            "fatigue_progression: '疲劳阶段'",
            "risk_triggers: '风险触发'",
            "context_impact: '外部影响'",
            "_fatigueReviewAiDimensionLabel(d.key, d.label)",
        ):
            self.assertIn(text, self.html)

    def test_p8_4_ai_success_updates_overview_dimensions(self):
        """P8.4:AI 成功后只用 insight.key_dimensions 增强四维总览。"""
        idx = self.html.find("function _renderFatigueReviewAiSuccess(insight)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewAiError", idx)
        body = self.html[idx:end]
        self.assertIn("_buildFatigueReviewOverviewDimensionsFromAi(insight.key_dimensions)", body)
        self.assertIn("_renderFatigueReviewOverviewDimensions", body)
        for forbidden in ("metrics", "curves", "fatigue_zones", "collapse_events", "localStorage.", "sessionStorage."):
            self.assertNotIn(forbidden, body)

    def test_p8_5_ai_loading_transition_animation_exists(self):
        """P8.5:AI 等待过程需要有过渡动画和骨架态。"""
        for text in (
            "fr-ai-loading-flow",
            "fr-ai-loading-track",
            "fr-ai-loading-steps",
            "fr-ai-skeleton-line",
            "@keyframes frAiScan",
            "@keyframes frAiPulse",
            "@keyframes frAiSkeleton",
        ):
            self.assertIn(text, self.html)
        idx = self.html.find("function _renderFatigueReviewAiLoading()")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _fatigueReviewAiDimensionLabel", idx)
        body = self.html[idx:end]
        for text in ("读取快照", "组织四维", "生成建议", "fatigue-ai-modal-spinner"):
            self.assertIn(text, body)
        self.assertNotIn("call_llm", body)

    def test_p8_6_ai_user_visible_text_is_localized(self):
        """P8.6:AI 用户可见文本不得直接暴露英文枚举和代码词。"""
        for text in (
            "function _fatigueReviewAiLevelLabel(level)",
            "function _fatigueReviewLocalizeAiText(text)",
            "BONK_WARNING",
            "效率指标",
            "心率储备占用",
            "_fatigueReviewAiLevelLabel(d.level)",
            "_fatigueReviewLocalizeAiText(d.comment || '')",
            "_fatigueReviewLocalizeAiText(insight.summary || '--')",
            "_fatigueReviewLocalizeAiText(insight.training_advice || '--')",
            "_fatigueReviewLocalizeAiText(item.comment || '暂无足够数据')",
            "level: _fatigueReviewAiLevelLabel(item.level || 'unknown')",
        ):
            self.assertIn(text, self.html)
        idx = self.html.find("function _renderFatigueReviewAiSuccess(insight)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewAiError", idx)
        body = self.html[idx:end]
        self.assertNotIn("safeHtml(d.level || '--')", body)

    def test_p8_7_ai_event_section_replaces_loading_and_syncs_count(self):
        """P8.7:AI 成功态必须替换关键事件骨架,且标题数量跟事件解释一致。"""
        idx = self.html.find("function _renderFatigueReviewAiSuccess(insight)")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function _renderFatigueReviewAiError", idx)
        body = self.html[idx:end]
        for text in (
            "var eventList = document.getElementById('fr-ai-event-list')",
            "var eventCount = document.getElementById('fr-ai-event-count')",
            "eventCount.textContent = eventText ? '1' : '0'",
            "eventList.innerHTML = '<div class=\"event-card active\"",
            "暂无关键事件",
        ):
            self.assertIn(text, body)
        self.assertNotIn("evSection.querySelector('.event-list').after(exist)", body)


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
