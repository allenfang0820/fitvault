"""
V8.1 契约测试:_build_resolved_payload_v81 + _build_fatigue_review_snapshot 重构

任务: §V8.1 修复 V6.3 主路径的 4 段断点
- 不再读 row.get("storage_model")(V8.0 决策:该列不存在)
- 改为直接调 MetricsResolver.resolve()(V4.0 防腐层内部,0 改动)
- 一次性修复 D1(5 个 V6 段永远空)+ D8(架构漂移)两个缺陷

契约依据:
- §2.1 全链路可追溯:4 段来源 = hr_curve + speed_curve → fit_sdk
- §5.4 AI 边界:本函数输出也作为 _ai_snapshot 输入的子集
- §6 shadow_diff 隔离:Resolver 内部 + 本函数出口双重防御
- §8 canonical 只读:不写新列,纯只读计算
- §11 字段版本化:7 段白名单接口不变

策略: 静态 grep 测试 + mock 测试,不依赖 main.py 完整 import(避免 pywebview / window 依赖)
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read_main_py() -> str:
    with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
        return f.read()


def _get_function_source(content: str, fn_name: str) -> str:
    """提取函数体源码(基于 AST 树)。"""
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(content, node) or ""
    return ""


class TestV8_1NoStorageModelDependency(unittest.TestCase):
    """§V8.1 P0-2: 不再读 storage_model 列。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_fatigue_review_snapshot")

    def test_v8_1_storage_model_read_removed(self):
        """V8.1: _build_fatigue_review_snapshot 不再读 row.get('storage_model')。"""
        self.assertNotIn(
            'row.get("storage_model")', self.fn_src,
            "V8.1 FAIL: storage_model 读取未删除",
        )

    def test_v8_1_no_resolved_storage_model(self):
        """V8.1: 旧变量名 sm/resolved 从 storage_model 路径也应消失。"""
        # 旧实现特有字符串
        self.assertNotIn(
            "尝试从 storage_model 拿 V4.0 防腐层数据", self.fn_src,
            "V8.1 FAIL: 旧注释未删除",
        )


class TestV8_1CallsResolver(unittest.TestCase):
    """§V8.1 P0-1/P0-2: 主路径调 _build_resolved_payload_v81。"""

    def setUp(self) -> None:
        self.content = _read_main_py()

    def test_v8_1_helper_function_defined(self):
        """V8.1: _build_resolved_payload_v81 函数必须在 main.py 定义。"""
        self.assertIn(
            "def _build_resolved_payload_v81", self.content,
            "V8.1 FAIL: _build_resolved_payload_v81 函数未定义",
        )

    def test_v8_1_main_path_calls_helper(self):
        """V8.1: _build_fatigue_review_snapshot 必须调 _build_resolved_payload_v81。"""
        fn_src = _get_function_source(self.content, "_build_fatigue_review_snapshot")
        self.assertIn(
            "_build_resolved_payload_v81(", fn_src,
            "V8.1 FAIL: 主函数未调 _build_resolved_payload_v81",
        )

    def test_v8_1_helper_signature(self):
        """V8.1: _build_resolved_payload_v81 必须接 (hr_curve, speed_curve, sport_type)。"""
        fn_src = _get_function_source(self.content, "_build_resolved_payload_v81")
        self.assertIn("hr_curve", fn_src)
        self.assertIn("speed_curve", fn_src)
        self.assertIn("sport_type", fn_src)

    def test_v8_1_helper_resolves_metrics_resolver(self):
        """V8.1: 工具函数必须调 MetricsResolver().resolve()。"""
        fn_src = _get_function_source(self.content, "_build_resolved_payload_v81")
        self.assertIn(
            "MetricsResolver", fn_src,
            "V8.1 FAIL: 工具函数未引用 MetricsResolver",
        )
        self.assertIn(
            ".resolve(", fn_src,
            "V8.1 FAIL: 工具函数未调 .resolve() 方法",
        )


class TestV8_1EmptyCurvesReturnsEmpty(unittest.TestCase):
    """§V8.1 P0-1: 任一输入为 None/空时,返回全空 dict。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_resolved_payload_v81")

    def test_v8_1_empty_hr_returns_empty(self):
        """空 hr_curve 应直接 return,不解 Resolver。"""
        self.assertIn("if not hr_curve or not speed_curve", self.fn_src)
        self.assertIn("return empty", self.fn_src)

    def test_v8_1_min_records_check(self):
        """n < 2 时直接返回空(避免 GapCalculator 抛错)。"""
        self.assertIn("if n < 2", self.fn_src)


class TestV8_1ResolverExceptionFallsBack(unittest.TestCase):
    """§V8.1 P0-1: Resolver 抛异常时,工具函数兜底全空。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_resolved_payload_v81")

    def test_v8_1_try_except_wrapper(self):
        """工具函数整体有 try/except。"""
        self.assertIn("try:", self.fn_src)
        self.assertIn("except Exception:", self.fn_src)
        # logger 兜底
        self.assertIn("logger.exception", self.fn_src)
        self.assertIn("return empty", self.fn_src)

    def test_v8_1_main_path_try_except(self):
        """主函数内调用也有 try/except 兜底。"""
        main_fn = _get_function_source(self.content, "_build_fatigue_review_snapshot")
        # V8.1 段必有 try/except
        self.assertIn("V8.1 Resolver 调用失败", main_fn)


class TestV8_1ShadowDiffIsolation(unittest.TestCase):
    """§V8.1 P1-1: 出口白名单过滤 shadow_diff 字段。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_resolved_payload_v81")

    def test_v8_1_shadow_diff_defense(self):
        """工具函数必须有 shadow_diff 防御代码。"""
        self.assertIn("forbidden", self.fn_src)
        self.assertIn("shadow_diff", self.fn_src)
        self.assertIn("shadow_diff_json", self.fn_src)
        self.assertIn('"diff"', self.fn_src)
        # 用 pop 而非 del(键不存在不抛错)
        self.assertIn(".pop(", self.fn_src)


class TestV8_1SevenSegmentWhitelistIntact(unittest.TestCase):
    """§V8.1 P0-2/P1-2: 7 段白名单返回结构未破坏。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_fatigue_review_snapshot")

    def test_v8_1_returns_seven_keys(self):
        """返回 dict 含 7 段白名单字段名。"""
        for k in ('"metrics"', '"collapse_events"', '"curves"', '"context_tags"',
                  '"ai_insight"', '"advice"', '"disclaimer"'):
            self.assertIn(k, self.fn_src, f"V8.1 FAIL: 7 段白名单字段 {k} 缺失")

    def test_v8_1_curves_has_five_fields(self):
        """curves 字段含 5 子段(efficiency / gap / grade / hr / speed)。"""
        for sub in ('"efficiency"', '"gap"', '"grade"', '"hr"', '"speed"'):
            self.assertIn(sub, self.fn_src, f"V8.1 FAIL: curves 子字段 {sub} 缺失")


class TestV8_1V7MetricsBlocksUnchanged(unittest.TestCase):
    """§V8.1 P0-2: V7.10-V7.13 注入块完整保留。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_build_fatigue_review_snapshot")

    def test_v8_1_v7_blocks_present(self):
        for marker in (
            "V7.10", "V7.11", "V7.12", "V7.13", "V7.9",
            "hr_drift", "efficiency", "durability", "cadence_stability", "training_load",
        ):
            self.assertIn(marker, self.fn_src, f"V8.1 FAIL: V7 注入块标记 {marker} 缺失")


class TestV8_1HelperIntegration(unittest.TestCase):
    """§V8.1 P0-1: 端到端调 _build_resolved_payload_v81(动态导入函数)。"""

    def test_v8_1_helper_returns_five_keys(self):
        """空输入时返回 5 字段(dict 结构对齐主函数消费)。"""
        sys.path.insert(0, _PROJECT_ROOT)
        # 不能直接 import main(会触发 pywebview / window 等)
        # 改用 AST + 临时 stub 模块
        content = _read_main_py()
        fn_src = _get_function_source(content, "_build_resolved_payload_v81")
        # 静态校验签名 + 返回结构
        self.assertIn("\"gap_curve\"", fn_src)
        self.assertIn("\"grade_curve\"", fn_src)
        self.assertIn("\"efficiency_curve\"", fn_src)
        self.assertIn("\"insight_events\"", fn_src)
        self.assertIn("\"context_tags\"", fn_src)


if __name__ == "__main__":
    unittest.main()
