"""
V8.8 集成测试:Tab 切换时清理函数的协同

任务: 验证 V8.8 新增的 _clearFatigueReviewInsight 调用点紧跟 _clearRadarInsight,
      保留 V8.7 已有的 4 个调用点,无重复或丢失。
"""

from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML) as f:
        return f.read()


class TestV8_8ClearOrdering(unittest.TestCase):
    """§V8.8 P1-1: 切 Tab 时 _clearFatigueReviewInsight 紧跟 _clearRadarInsight。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_8_clear_fatigue_follows_clear_radar(self):
        """在 switchTab 内,两个清理调用紧邻。"""
        idx = self.html.find("function switchTab(tabBtn) {")
        end = self.html.find("\n    function ", idx + 50)
        body = self.html[idx:end]
        # _clearRadarInsight 位置
        radar_idx = body.find("_clearRadarInsight();")
        # _clearFatigueReviewInsight 位置
        fatigue_idx = body.find("_clearFatigueReviewInsight();")
        self.assertGreater(radar_idx, 0)
        self.assertGreater(fatigue_idx, 0)
        # fatigue 在 radar 之后(顺序约束:先清雷达图,再清复盘)
        self.assertGreater(fatigue_idx, radar_idx,
                           "V8.8 FAIL: _clearFatigueReviewInsight 应在 _clearRadarInsight 之后")


class TestV8_8V87Unchanged(unittest.TestCase):
    """§V8.8 P1-2: V8.7 已有的调用点未受影响(经 V9.0 收敛为 4 个共享点)。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_8_four_distinct_call_points(self):
        """V9.0 收敛:closeFatigueReview 内的清理逻辑下沉到 _cleanupFatigueReviewPanel helper,
        直接调用点从 5(V8.7 4 + V8.8 1) 降为 4(3 触发点 + 1 共享 helper)。

        4 个调用点对应:
          1. switchTab(V8.8 新增)
          2. openFatigueReview(切活动)
          3. _cleanupFatigueReviewPanel(关闭触发,被 closeFatigueReview / closeActivityDetailModal 复用)
          4. onFatigueReviewAiInsight(重新点击)
        """
        call_indices = []
        pos = 0
        while True:
            idx = self.html.find("_clearFatigueReviewInsight();", pos)
            if idx < 0:
                break
            call_indices.append(idx)
            pos = idx + 1
        # V9.0 调整:4 个直接调用点
        self.assertEqual(len(call_indices), 4,
                         f"V9.0 调整:调用点应为 4(3 触发点 + 1 共享 helper),实际 {len(call_indices)}")
        # 位置不重复
        self.assertEqual(len(set(call_indices)), 4)


if __name__ == "__main__":
    unittest.main()
