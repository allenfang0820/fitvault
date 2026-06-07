"""
V8.9 契约测试:closeActivityDetailModal 不再清理死容器

任务: §V8.9 删除 V7.4 时代的误导代码 —— 详情舱从未实现 ECharts 双容器,
      但 closeActivityDetailModal 仍调 clearProfileAnalysisChart('activity-detail-profile-chart')
      清理一个永远不存在的实例。

契约依据:
- §11 字段版本化:保留 renderProfileAnalysisChart 的 containerId 参数(V7.4 API)
- §6 shadow_diff 隔离:清理调用不涉及 shadow_diff
- §5.4 AI 边界:删除清理调用不影响 AI snapshot

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


class TestV8_9CloseModalNoDeadClear(unittest.TestCase):
    """§V8.9 P0-2: closeActivityDetailModal 不再清理死容器。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_9_close_modal_no_clear_dead_container(self):
        """closeActivityDetailModal 函数体内不含 clearProfileAnalysisChart('activity-detail-profile-chart')。"""
        idx = self.html.find("function closeActivityDetailModal() {")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 1000
        body = self.html[idx:end]
        self.assertNotIn(
            "clearProfileAnalysisChart('activity-detail-profile-chart')",
            body,
            "V8.9 FAIL: closeActivityDetailModal 仍调死容器清理",
        )

    def test_v8_9_container_id_param_preserved(self):
        """renderProfileAnalysisChart 函数签名仍含 containerId 参数(V7.4 API 保留)。"""
        # 函数定义 + containerId 参数
        self.assertIn("function renderProfileAnalysisChart(activityData, containerId)", self.html,
                      "V8.9 FAIL: renderProfileAnalysisChart containerId 参数应保留")

    def test_v8_9_no_backend_modification(self):
        """V8.9 决策:0 改动 main.py / metrics_resolver.py。"""
        with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
            main = f.read()
        with open(os.path.join(_PROJECT_ROOT, "metrics_resolver.py")) as f:
            resolver = f.read()
        # V8.9 不应在后端引入 V8.9 标记
        self.assertNotIn("V8.9", main, "V8.9 FAIL: main.py 不应有 V8.9 标记")
        self.assertNotIn("V8.9", resolver, "V8.9 FAIL: Resolver 不应有 V8.9 标记")


if __name__ == "__main__":
    unittest.main()
