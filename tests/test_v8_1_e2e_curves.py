"""
V8.1 集成测试:实测 _build_resolved_payload_v81 的 4 段产出

任务: 验证 V8.1 修复后,V6.3 主路径的 gap_curve / efficiency_curve /
      insight_events / context_tags 4 段从"永远空"变为"通常有数"。

策略: 不通过 main.py(避免 pywebview / window 依赖),
      而是 stub 必要的依赖后动态加载 _build_resolved_payload_v81。
      /tmp/probe_v81.py 已实测 MetricsResolver.resolve() 4 段可产出,
      本测试在主项目的测试框架内做一次回归确认。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _build_minimal_curves(n: int = 200):
    """构造 200 点的 hr_curve + speed_curve,模拟一条跑步活动。"""
    hr_curve = []
    speed_curve = []
    for i in range(n):
        hr = 120 + (i / n) * 40
        sp = 3.2 - (i / n) * 0.3
        hr_curve.append(round(hr, 1))
        speed_curve.append(round(sp, 3))
    return hr_curve, speed_curve


def _load_helper_function():
    """动态加载 _build_resolved_payload_v81(避免 import main 触发 pywebview)。

    策略: 把 main.py 内的 _build_resolved_payload_v81 函数定义提取出来,
          用 exec 在一个 stub 模块里执行,直接拿到函数对象。
    """
    import ast

    main_path = os.path.join(_PROJECT_ROOT, "main.py")
    with open(main_path) as f:
        tree = ast.parse(f.read())

    fn_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_resolved_payload_v81":
            fn_node = node
            break
    assert fn_node is not None, "V8.1: _build_resolved_payload_v81 not found in main.py"

    fn_src = ast.get_source_segment(open(main_path).read(), fn_node)

    # 构造 stub 模块上下文
    stub = types.ModuleType("v81_stub")
    stub.__file__ = main_path

    # 真实 metrics_resolver: 先 import 拿到 MetricsResolver 类对象
    import metrics_resolver as _real_mr
    stub.MetricsResolver = _real_mr.MetricsResolver

    # 函数体所需的 datetime 相关模块
    from datetime import datetime, timedelta, timezone
    stub.datetime = datetime
    stub.timedelta = timedelta
    stub.timezone = timezone

    # logger stub
    class _Logger:
        def exception(self, msg, *a, **kw):
            import traceback as _tb
            print(f"[V81 logger.exception] {msg}")
            _tb.print_exc()
        def warning(self, msg, *a, **kw):
            pass
    stub.logger = _Logger()

    # exec 在 stub 命名空间下执行
    exec(compile(fn_src, f"{main_path}:_build_resolved_payload_v81", "exec"),
         stub.__dict__)
    return stub._build_resolved_payload_v81


class TestV8_1EndToEndCurves(unittest.TestCase):
    """§V8.1 P2-2: 端到端验证 4 段产出。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = staticmethod(_load_helper_function())

    def test_v8_1_helper_exists(self):
        """V8.1: 工具函数可加载。"""
        self.assertTrue(callable(self.helper))

    def test_v8_1_empty_inputs_return_empty(self):
        """空 hr_curve + 空 speed_curve → 4 段全空。"""
        result = self.helper([], [], "running")
        self.assertEqual(result["gap_curve"], [])
        self.assertEqual(result["efficiency_curve"], [])
        self.assertEqual(result["insight_events"], [])
        self.assertEqual(result["context_tags"], {})

    def test_v8_1_none_inputs_return_empty(self):
        """None 输入 → 4 段全空(不抛错)。"""
        result = self.helper(None, None, "running")
        self.assertEqual(result["gap_curve"], [])
        self.assertEqual(result["efficiency_curve"], [])

    def test_v8_1_too_short_inputs_return_empty(self):
        """n=1 时返回空(避免 GapCalculator insufficient_records)。"""
        result = self.helper([150], [3.0], "running")
        self.assertEqual(result["gap_curve"], [])

    def test_v8_1_real_curves_produce_gap_and_efficiency(self):
        """真实曲线 → gap_curve + efficiency_curve 有数据。"""
        hr, sp = _build_minimal_curves(200)
        result = self.helper(hr, sp, "running")
        # V8.1 修复前: 永远空
        # V8.1 修复后: 200 点输出
        self.assertGreater(
            len(result["gap_curve"]), 0,
            f"V8.1 FAIL: gap_curve 仍为空,probe 验证应产出 200 点",
        )
        self.assertGreater(
            len(result["efficiency_curve"]), 0,
            f"V8.1 FAIL: efficiency_curve 仍为空",
        )

    def test_v8_1_curves_have_consistent_length(self):
        """gap_curve 与 efficiency_curve 长度应一致(来自同一 resolve())。"""
        hr, sp = _build_minimal_curves(200)
        result = self.helper(hr, sp, "running")
        self.assertEqual(
            len(result["gap_curve"]), len(result["efficiency_curve"]),
            "V8.1: gap_curve 与 efficiency_curve 长度不一致(Resolver 异常)",
        )

    def test_v8_1_resolver_exception_falls_back_to_empty(self):
        """Mock Resolver 抛异常 → 工具函数兜底全空(不污染主流程)。"""
        import metrics_resolver

        original_resolve = metrics_resolver.MetricsResolver.resolve
        metrics_resolver.MetricsResolver.resolve = MagicMock(
            side_effect=RuntimeError("V8.1 mock: Resolver 异常")
        )
        try:
            hr, sp = _build_minimal_curves(200)
            result = self.helper(hr, sp, "running")
            self.assertEqual(result["gap_curve"], [])
            self.assertEqual(result["efficiency_curve"], [])
            self.assertEqual(result["insight_events"], [])
            self.assertEqual(result["context_tags"], {})
        finally:
            metrics_resolver.MetricsResolver.resolve = original_resolve

    def test_v8_1_shadow_diff_isolated(self):
        """实测 Resolver 不会让 shadow_diff 漏出。"""
        hr, sp = _build_minimal_curves(50)
        result = self.helper(hr, sp, "running")
        # 工具函数出口白名单过滤已加,不应出现 shadow_diff
        for forbidden in ("shadow_diff", "shadow_diff_json", "diff"):
            self.assertNotIn(forbidden, result, f"V8.1 FAIL: {forbidden} 漏出")


if __name__ == "__main__":
    unittest.main()
