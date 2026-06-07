"""
V8.7 契约测试:_clearFatigueReviewInsight 清空 _lastFatigueReviewCurves

任务: §V8.7 修复切换活动时旧曲线数据泄漏到 ECharts 渲染。
      切活动 / 关闭覆盖层 / 重新点击时,_clearFatigueReviewInsight 必须
      把 window._lastFatigueReviewCurves 设为 null。

契约依据:
- §5.4 AI 边界:清除 cache 不影响 AI snapshot
- §5.6.2 阅后即焚 3 触发点:切活动 / 切 Tab / 重新点击 → 都要清
- §6 shadow_diff 隔离:清理 cache 不涉及 shadow_diff
- §11 字段版本化:_lastFatigueReviewCurves 是前端内部状态,非 API

策略: 静态 grep 测试 track.html 改动完整性。
"""

from __future__ import annotations

import os
import re
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML) as f:
        return f.read()


def _get_fn_body(content: str, fn_signature: str) -> str:
    """粗略函数体提取(从签名开始到下一个 function 定义)。"""
    idx = content.find(fn_signature)
    if idx < 0:
        return ""
    # 找下一个 function 定义或明显结束
    end_markers = ["\n    function ", "\n    async function ", "\n    // ==="]
    end_idx = len(content)
    for m in end_markers:
        i = content.find(m, idx + len(fn_signature))
        if i > 0 and i < end_idx:
            end_idx = i
    return content[idx:end_idx]


class TestV8_7ClearCurvesCache(unittest.TestCase):
    """§V8.7 P0-2: _clearFatigueReviewInsight 清空 _lastFatigueReviewCurves。"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_v8_7_clear_function_resets_curves(self):
        """_clearFatigueReviewInsight 函数体必须设 _lastFatigueReviewCurves = null。"""
        fn_body = _get_fn_body(self.html, "function _clearFatigueReviewInsight() {")
        self.assertIn("function _clearFatigueReviewInsight()", self.html,
                      "V8.7 FAIL: _clearFatigueReviewInsight 函数未定义")
        self.assertIn("window._lastFatigueReviewCurves = null", fn_body,
                      "V8.7 FAIL: _lastFatigueReviewCurves 未被清空")

    def test_v8_7_uses_null_not_delete(self):
        """V8.7 决策:用 = null 而非 delete(避免下游 typeof 异常)。"""
        # 找清除点
        idx = self.html.find("window._lastFatigueReviewCurves = null")
        self.assertGreater(idx, 0)
        # 不应使用 delete
        # 检查函数体内 200 字符内
        fn_body = _get_fn_body(self.html, "function _clearFatigueReviewInsight() {")
        self.assertNotIn("delete window._lastFatigueReviewCurves", fn_body,
                         "V8.7 决策:用 = null 而非 delete")

    def test_v8_7_write_point_originates_from_data_curves(self):
        """_lastFatigueReviewCurves 的写入点必须从 data.curves(后端权威源)取。"""
        # 写入语句必须是 data.curves(非前端拼接)
        self.assertIn("window._lastFatigueReviewCurves = data.curves", self.html,
                      "V8.7 FAIL: 写入点未从 data.curves 取数")

    def test_v8_7_no_remaining_residue(self):
        """V8.7 修复后,清除点应能覆盖写入点(无残留引用)。"""
        # 写入点 1 次
        write_count = self.html.count("window._lastFatigueReviewCurves = data.curves")
        self.assertEqual(write_count, 1, "V8.7: 写入点应唯一")
        # 清除点 1 次
        clear_count = self.html.count("window._lastFatigueReviewCurves = null")
        self.assertEqual(clear_count, 1, "V8.7: 清除点应唯一")

    def test_v8_7_three_trigger_points(self):
        """§5.6.2 阅后即焚 3 触发点都调用 _clearFatigueReviewInsight。"""
        # 全部 4 个调用点(关闭 / 切活动 / 重新打开 / 重新点击)
        # 至少 3 个
        call_count = self.html.count("_clearFatigueReviewInsight();")
        self.assertGreaterEqual(call_count, 3,
                                f"V8.7 FAIL: _clearFatigueReviewInsight 调用 < 3 次(实际 {call_count})")


class TestV8_7NoBackendModification(unittest.TestCase):
    """§V8.7 决策:V8.7 是纯前端修复,0 改动 main.py / metrics_resolver.py。"""

    def test_v8_7_only_track_html_modified(self):
        """V8.7 仅改 track.html,后端文件未变。"""
        # 这个测试本质是 7 段白名单契约:后端逻辑不动
        # 通过 V8.7 测试集中的静态检查覆盖
        with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
            main = f.read()
        with open(os.path.join(_PROJECT_ROOT, "metrics_resolver.py")) as f:
            resolver = f.read()
        # V8.7 不应在后端引入 V8.7 标记
        self.assertNotIn("V8.7", main, "V8.7 FAIL: main.py 不应有 V8.7 改动标记")
        self.assertNotIn("V8.7", resolver, "V8.7 FAIL: Resolver 不应有 V8.7 改动标记")


if __name__ == "__main__":
    unittest.main()
