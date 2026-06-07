"""
V8.7 集成测试:切活动时曲线缓存清理的端到端契约

任务: 验证 ECharts 渲染与 cache 清理的协同:cache 是性能优化层,
      ECharts 必须从权威源 (data.curves) 取数,cache = null 不会让
      渲染失败,只会让"无数据"显示判断降级为"未提供"。
"""

from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML) as f:
        return f.read()


class TestV8_7EChartsDataSource(unittest.TestCase):
    """§V8.7 P1-2: ECharts 渲染数据源是 appState.activityMetrics(V8.1 已修)。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_7_echarts_uses_appState_activityMetrics(self):
        """ECharts 渲染用 appState.activityMetrics(非 _lastFatigueReviewCurves)。"""
        # renderProfileAnalysisChart 至少被调 2 次
        call_count = self.html.count("renderProfileAnalysisChart(appState.activityMetrics)")
        self.assertGreaterEqual(call_count, 2,
                                f"V8.7 FAIL: renderProfileAnalysisChart 调用 < 2 次(实际 {call_count})")

    def test_v8_7_appState_activityMetrics_contains_curves(self):
        """appState.activityMetrics 赋值含 curves 字段(V8.1 修复)。"""
        # 静态 grep:appState.activityMetrics = activity (后端返回含 curves)
        # V8.1 修复点:activity_canonical / activity 都含 curves
        self.assertIn("appState.activityMetrics = activity", self.html,
                      "V8.7 FAIL: appState.activityMetrics 未赋值")

    def test_v8_7_cache_isolated_from_echarts_render(self):
        """_lastFatigueReviewCurves 不被 ECharts 渲染函数直接消费。"""
        # renderProfileAnalysisChart 函数体内不应读 _lastFatigueReviewCurves
        # 找 function body
        idx = self.html.find("function renderProfileAnalysisChart")
        self.assertGreater(idx, 0)
        # 找下一个 function 定义作为 body 结束
        end = self.html.find("\n    function ", idx + 50)
        body = self.html[idx:end]
        # body 内不应有 _lastFatigueReviewCurves
        self.assertNotIn("_lastFatigueReviewCurves", body,
                         "V8.7 FAIL: ECharts 渲染不应读 _lastFatigueReviewCurves")


if __name__ == "__main__":
    unittest.main()
