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


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
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
            "fr-section-events", "fr-section-advice",
        ]:
            self.assertIn('id="' + section_id + '"', self.html,
                          f"V9.0 FAIL: AI Modal 缺 {section_id}")
        # 关键 element id(fr-summary / fr-dimensions / fr-event-list / fr-advice)
        for el_id in ["fr-summary", "fr-dimensions", "fr-event-list",
                      "fr-advice", "fr-disclaimer"]:
            self.assertIn('id="' + el_id + '"', self.html,
                          f"V9.0 FAIL: AI Modal 缺 #{el_id}")


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


if __name__ == "__main__":
    unittest.main()
