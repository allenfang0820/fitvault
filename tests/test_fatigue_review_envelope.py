"""V4.0 端到端 envelope 契约 — get_fatigue_review / 防腐层隔离

契约:fit-arch-contrac §V4.0 防腐层 / §三 响应结构
验证:
  1. main.py._build_fatigue_review_snapshot 不再含业务计算(静态分析)
  2. _build_resolved_payload_v81 透传 fatigue_zones 字段
  3. 周边 metrics 白名单(decoupling_pct / _fetch_historical_metrics_avg)未被误删
  4. MetricsResolver 暴露 _calculate_fatigue_zones 静态方法
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestSurroundingCodeProtection(unittest.TestCase):
    """Step 3 保护:周边 metrics 白名单代码未被误删"""

    def test_build_fatigue_review_snapshot_still_exists(self):
        """_build_fatigue_review_snapshot 函数仍存在(未被误删整个函数)"""
        # 该函数是 Api 类方法,不是模块级
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        self.assertIn("def _build_fatigue_review_snapshot(", text,
                     "_build_fatigue_review_snapshot 函数必须仍存在")

    def test_metrics_keywords_preserved(self):
        """decoupling_pct / _fetch_historical_metrics_avg 等周边代码仍存在"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        for keyword in ("decoupling_pct", "_fetch_historical_metrics_avg"):
            self.assertIn(keyword, text, f"{keyword} 周边代码必须保留(Step 3 保护)")

    def test_no_legacy_fatigue_zones_logic(self):
        """旧版滑窗逻辑的关键标识符不再出现于 _build_fatigue_review_snapshot"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_fatigue_review_snapshot":
                continue
            func_src = ast.unparse(node)
            # 旧版典型锚点
            self.assertNotIn("n = len(efficiency_curve)", func_src,
                            "旧版 n=len() 算法已下沉,不应在 main.py 残留")
            self.assertNotIn("dist_step_m", func_src,
                            "旧版线性均摊距离变量已下沉,不应在 main.py 残留")

    def test_resolved_payload_v81_passes_fatigue_zones(self):
        """_build_resolved_payload_v81 必须透传 fatigue_zones 字段"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        found_func = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_resolved_payload_v81":
                continue
            found_func = True
            func_src = ast.unparse(node)
            # ast.unparse 会统一使用单引号,这里两种都接受
            self.assertTrue(
                "'fatigue_zones'" in func_src or '"fatigue_zones"' in func_src,
                "_build_resolved_payload_v81 必须透传 fatigue_zones 字段"
            )
        self.assertTrue(found_func, "_build_resolved_payload_v81 函数必须存在")


class TestNoBusinessLogicInMainPy(unittest.TestCase):
    """V4.0 防腐层:本次修复后,main.py 不再含 fatigue_zones 业务计算"""

    def test_no_window_computation_in_main(self):
        """main.py._build_fatigue_review_snapshot 中不应再有 window= 计算"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_fatigue_review_snapshot":
                continue
            func_src = ast.unparse(node)
            self.assertNotIn("window = max(", func_src,
                            "window= 计算已下沉,main.py 不应再含")
            self.assertNotIn("n = len(", func_src,
                            "n=len() 计算已下沉,main.py 不应再含")

    def test_fatigue_zones_only_passes_through(self):
        """_build_fatigue_review_snapshot 中 fatigue_zones 变量只来自契约层"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_fatigue_review_snapshot":
                continue
            func_src = ast.unparse(node)
            # fatigue_zones 必须从 resolved_v81.get() 获取(ast.unparse 单引号)
            self.assertIn(
                "fatigue_zones = resolved_v81.get('fatigue_zones')",
                func_src,
                "fatigue_zones 必须从契约层获取,不能本地计算"
            )
            # 不应再含 list/append 修改
            self.assertNotIn("fatigue_zones.append(", func_src,
                            "不应在 main.py 中 append fatigue_zones(已下沉)")

    def test_thresholds_constants_not_in_main(self):
        """sport-aware 阈值常量已在 resolver,main.py 不应再硬编码 0.10/0.20 等"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        # 0.85 / 0.7 是旧版 V8.11 阈值(avg < cur_start_val * 0.85 / * 0.7)
        # 0.15 warn 是 V8.11 硬编码
        # 修复后,这些常量应只在 metrics_resolver.py 中
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_fatigue_review_snapshot":
                continue
            func_src = ast.unparse(node)
            self.assertNotIn("0.85", func_src,
                            "旧版 0.85 阈值已下沉")
            self.assertNotIn("0.7", func_src,
                            "旧版 0.7 阈值已下沉")


class TestResolverExposesFatigueZones(unittest.TestCase):
    """MetricsResolver 契约层必须暴露 _calculate_fatigue_zones"""

    def test_method_exists(self):
        from metrics_resolver import MetricsResolver
        self.assertTrue(hasattr(MetricsResolver, "_calculate_fatigue_zones"),
                      "MetricsResolver 必须含 _calculate_fatigue_zones 静态方法")

    def test_method_callable(self):
        from metrics_resolver import MetricsResolver
        self.assertTrue(callable(getattr(MetricsResolver, "_calculate_fatigue_zones", None)))

    def test_resolve_produces_fatigue_zones_field(self):
        """resolve() 返回的 dict 必须含 fatigue_zones 字段"""
        from metrics_resolver import MetricsResolver
        # 静态分析
        main_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "resolve":
                continue
            func_src = ast.unparse(node)
            # ast.unparse 使用单引号
            self.assertIn(
                "final_data['fatigue_zones']",
                func_src,
                "resolve() 必须装配 fatigue_zones 到 final_data"
            )
            # 旧版硬编码 = [] 已删除
            self.assertNotIn(
                "final_data['fatigue_zones'] = []",
                func_src,
                "旧版空数组硬编码已删除,改为实际计算结果"
            )


if __name__ == "__main__":
    unittest.main()
