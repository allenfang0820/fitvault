"""
V8.8 契约测试:switchTab 调 _clearFatigueReviewInsight

任务: §V8.8 修复 §5.6.2 阅后即焚 3 触发点中的"切 Tab"触发点。
      切活动 / 切 Tab / 重新点击 → 都要清 AI 洞察状态。

契约依据:
- §5.4 AI 边界:切 Tab 不影响 AI snapshot 主链路
- §5.6.2 阅后即焚 3 触发点:切活动 / 切 Tab / 重新点击
- §6 shadow_diff 隔离:清理函数不涉及 shadow_diff
- §11 字段版本化:保留 _clearFatigueReviewInsight 函数名

策略: 静态 grep 测试 track.html 改动完整性。
"""

from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML) as f:
        return f.read()


class TestV8_8SwitchTabCallClear(unittest.TestCase):
    """§V8.8 P0-2: switchTab 调 _clearFatigueReviewInsight。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_8_switch_tab_calls_clear_fatigue_review(self):
        """switchTab 函数体必须调 _clearFatigueReviewInsight()。"""
        idx = self.html.find("function switchTab(tabBtn) {")
        self.assertGreater(idx, 0)
        # 找下一个 function 结束
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 2000
        body = self.html[idx:end]
        self.assertIn("_clearFatigueReviewInsight();", body,
                      "V8.8 FAIL: switchTab 未调 _clearFatigueReviewInsight")

    def test_v8_8_switch_tab_preserves_clear_radar_insight(self):
        """V8.8 决策:保留 _clearRadarInsight()(V8.8 不删原有清理)。"""
        idx = self.html.find("function switchTab(tabBtn) {")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 2000
        body = self.html[idx:end]
        self.assertIn("_clearRadarInsight();", body,
                      "V8.8 FAIL: _clearRadarInsight() 不应被删")

    def test_v8_8_v5_6_2_three_trigger_points(self):
        """§5.6.2 阅后即焚 3 触发点全部覆盖。

        切活动 → openFatigueReview 内(line ~10237)
        切 Tab → switchTab 内(V8.8 新增,line 5007)
        重新点击 → onFatigueReviewAiInsight(line ~10375)
        关闭触发 → _cleanupFatigueReviewPanel(V9.0 收敛,line ~10360)
                      复用入口:closeFatigueReview / closeActivityDetailModal
        """
        # V9.0:closeFatigueReview 内的清理逻辑收敛到 _cleanupFatigueReviewPanel helper,
        # 故直接调用点从 5(V8.7 4 + V8.8 1) 降为 4。
        # 4 个调用点对应 3 触发点 + 1 共享 helper(行为不变)。
        call_count = self.html.count("_clearFatigueReviewInsight();")
        self.assertGreaterEqual(
            call_count, 4,
            f"V9.0 调整:调用点应 ≥ 4(3 触发点 + 1 共享 helper),实际 {call_count}",
        )

    def test_v8_8_no_backend_modification(self):
        """V8.8 决策:0 改动 main.py / metrics_resolver.py。"""
        with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
            main = f.read()
        with open(os.path.join(_PROJECT_ROOT, "metrics_resolver.py")) as f:
            resolver = f.read()
        # V8.8 不应在后端引入 V8.8 标记
        self.assertNotIn("V8.8", main, "V8.8 FAIL: main.py 不应有 V8.8 标记")
        self.assertNotIn("V8.8", resolver, "V8.8 FAIL: Resolver 不应有 V8.8 标记")


if __name__ == "__main__":
    unittest.main()
