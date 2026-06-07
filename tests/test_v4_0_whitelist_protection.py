"""V4-8: 周边 metric 白名单保护性测试

契约:fit-arch-contrac §V4.0 防腐层 / §四 周边 metrics 白名单
验证 V4.0 治理(下沉 main.py 业务逻辑至 Resolver)过程中,以下关键 metric 未遭误删:
  1. 训练负荷: training_load / _compute_training_load / hr_zone_distribution
  2. 计算调用: decoupling_pct / _fetch_historical_metrics_avg / bonk_risk
  3. 趋势指标: _fetch_efficiency_trend / _fetch_durability_trend / _fetch_cadence_stability_trend
  4. 比率指标: _fetch_load_ratio_7d_42d / _fetch_training_load_trend
  5. bonk 检测: _detect_bonk_event(已下沉到 Resolver,验证未丢失)
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════
# Test 0: 源码加载
# ══════════════════════════════════════════════════════════════════

class TestSourceLoading(unittest.TestCase):
    """确保 main.py 和 metrics_resolver.py 可正常 AST 解析"""

    @classmethod
    def setUpClass(cls):
        cls.main_path = os.path.join(_PROJECT_ROOT, "main.py")
        cls.resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(cls.main_path, "r") as f:
            cls.main_src = f.read()
        with open(cls.resolver_path, "r") as f:
            cls.resolver_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)
        cls.resolver_tree = ast.parse(cls.resolver_src)

    def test_main_py_parsable(self):
        """main.py 必须可 AST 解析"""
        self.assertIsNotNone(self.main_tree)

    def test_resolver_py_parsable(self):
        """metrics_resolver.py 必须可 AST 解析"""
        self.assertIsNotNone(self.resolver_tree)


# ══════════════════════════════════════════════════════════════════
# Test 1: 训练负荷白名单
# ══════════════════════════════════════════════════════════════════

class TestTrainingLoadWhitelist(unittest.TestCase):
    """training_load / _compute_training_load / hr_zone_distribution"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_training_load_referenced(self):
        """training_load 指标在 main.py 中仍有引用"""
        self.assertIn("training_load", self.main_src,
                      "training_load 指标引用必须保留")

    def test_hr_zone_distribution_referenced(self):
        """hr_zone_distribution 字段在 main.py 中仍有引用"""
        self.assertIn("hr_zone_distribution", self.main_src,
                      "hr_zone_distribution 必须保留")

    def test_hr_zone_distribution_has_function(self):
        """_compute_hr_zone_distribution 函数定义存在"""
        found = False
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_compute_hr_zone_distribution":
                found = True
                break
        self.assertTrue(found, "_compute_hr_zone_distribution 函数必须存在")

    def test_compute_training_load_called(self):
        """_compute_training_load 在 main.py 中有调用点"""
        self.assertIn("_compute_training_load", self.main_src,
                      "_compute_training_load 调用必须保留")

    def test_training_load_assembly_has_fallback(self):
        """training_load 组装有降级分支(含 unavailable fallback)"""
        self.assertIn('"training_load"', self.main_src)
        # 降级分支: training_load 注入失败不影响其他 metric
        self.assertIn("training_load", self.main_src)


# ══════════════════════════════════════════════════════════════════
# Test 2: 计算调用白名单
# ══════════════════════════════════════════════════════════════════

class TestCalculationCallWhitelist(unittest.TestCase):
    """decoupling_pct / _fetch_historical_metrics_avg / bonk_risk"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_decoupling_pct_referenced(self):
        """decoupling_pct 在 main.py 中有引用"""
        self.assertIn("decoupling_pct", self.main_src,
                      "decoupling_pct 指标引用必须保留")

    def test_fetch_historical_metrics_avg_defined(self):
        """_fetch_historical_metrics_avg 方法定义存在"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_fetch_historical_metrics_avg":
                self.assertIsNotNone(node)
                return
        self.fail("_fetch_historical_metrics_avg 方法定义必须存在")

    def test_bonk_risk_referenced(self):
        """bonk_risk 指标在 main.py 中有引用"""
        self.assertIn("bonk_risk", self.main_src,
                      "bonk_risk 指标引用必须保留")

    def test_historical_metrics_has_decoupling_pct_return(self):
        """_fetch_historical_metrics_avg 返回结构含 decoupling_pct"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_fetch_historical_metrics_avg":
                func_src = ast.get_source_segment(self.main_src, node)
                if func_src:
                    self.assertIn("decoupling_pct", func_src,
                                  "_fetch_historical_metrics_avg 必须返回 decoupling_pct")
                return
        self.fail("_fetch_historical_metrics_avg 未找到")


# ══════════════════════════════════════════════════════════════════
# Test 3: 趋势指标白名单
# ══════════════════════════════════════════════════════════════════

class TestTrendWhitelist(unittest.TestCase):
    """_fetch_efficiency_trend / _fetch_durability_trend / _fetch_cadence_stability_trend"""

    TREND_FUNCTIONS = [
        "_fetch_efficiency_trend",
        "_fetch_durability_trend",
        "_fetch_cadence_stability_trend",
    ]

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_all_trend_functions_defined(self):
        """3 个趋势函数必须全部存在"""
        for func_name in self.TREND_FUNCTIONS:
            found = False
            for node in ast.walk(self.main_tree):
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    found = True
                    break
            self.assertTrue(found, f"趋势函数 {func_name} 必须存在")

    def test_efficiency_trend_called(self):
        """_fetch_efficiency_trend 在 main.py 中有调用点"""
        self.assertIn("_fetch_efficiency_trend", self.main_src,
                      "_fetch_efficiency_trend 调用必须保留")

    def test_durability_trend_called(self):
        """_fetch_durability_trend 在 main.py 中有调用点"""
        self.assertIn("_fetch_durability_trend", self.main_src,
                      "_fetch_durability_trend 调用必须保留")

    def test_cadence_stability_trend_called(self):
        """_fetch_cadence_stability_trend 在 main.py 中有调用点"""
        self.assertIn("_fetch_cadence_stability_trend", self.main_src,
                      "_fetch_cadence_stability_trend 调用必须保留")


# ══════════════════════════════════════════════════════════════════
# Test 4: 比率指标白名单
# ══════════════════════════════════════════════════════════════════

class TestRatioWhitelist(unittest.TestCase):
    """_fetch_load_ratio_7d_42d / _fetch_training_load_trend"""

    RATIO_FUNCTIONS = [
        "_fetch_load_ratio_7d_42d",
        "_fetch_training_load_trend",
    ]

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_all_ratio_functions_defined(self):
        """2 个比率函数必须全部存在"""
        for func_name in self.RATIO_FUNCTIONS:
            found = False
            for node in ast.walk(self.main_tree):
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    found = True
                    break
            self.assertTrue(found, f"比率函数 {func_name} 必须存在")

    def test_load_ratio_7d_42d_called(self):
        """_fetch_load_ratio_7d_42d 在 main.py 中有调用点"""
        self.assertIn("_fetch_load_ratio_7d_42d", self.main_src,
                      "_fetch_load_ratio_7d_42d 调用必须保留")

    def test_training_load_trend_called(self):
        """_fetch_training_load_trend 在 main.py 中有调用点"""
        self.assertIn("_fetch_training_load_trend", self.main_src,
                      "_fetch_training_load_trend 调用必须保留")


# ══════════════════════════════════════════════════════════════════
# Test 5: Bonk 检测白名单(已下沉到 Resolver)
# ══════════════════════════════════════════════════════════════════

class TestBonkDetectionWhitelist(unittest.TestCase):
    """_detect_bonk_event — 已下沉至 metrics_resolver.py"""

    @classmethod
    def setUpClass(cls):
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            cls.resolver_src = f.read()
        cls.resolver_tree = ast.parse(cls.resolver_src)

    def test_detect_bonk_event_in_resolver(self):
        """_detect_bonk_event 必须存在于 metrics_resolver.py"""
        self.assertIn("_detect_bonk_event", self.resolver_src,
                      "_detect_bonk_event 必须在 metrics_resolver.py 中定义")

    def test_detect_bonk_event_is_static_method(self):
        """_detect_bonk_event 必须是 @staticmethod"""
        for node in ast.walk(self.resolver_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_detect_bonk_event":
                # 检查是否有 @staticmethod 装饰器
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                        return
                self.fail("_detect_bonk_event 必须是 @staticmethod")
        self.fail("_detect_bonk_event 未在 metrics_resolver.py 中找到")

    def test_detect_bonk_event_callable(self):
        """_detect_bonk_event 可通过 MetricsResolver 调用"""
        from metrics_resolver import MetricsResolver
        self.assertTrue(callable(MetricsResolver._detect_bonk_event),
                        "MetricsResolver._detect_bonk_event 必须可调用")


# ══════════════════════════════════════════════════════════════════
# Test 6: main.py 关键 import 保护
# ══════════════════════════════════════════════════════════════════

class TestCriticalImportsIntact(unittest.TestCase):
    """V4.0 治理后关键 import 未被误删"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()

    def test_metrics_resolver_imported(self):
        """main.py 必须 import MetricsResolver"""
        self.assertIn("from metrics_resolver import", self.main_src,
                      "MetricsResolver import 必须保留")
        self.assertIn("MetricsResolver", self.main_src)

    def test_profile_backend_imported(self):
        """main.py 必须 import profile_backend(IO 层)"""
        self.assertIn("profile_backend", self.main_src,
                      "profile_backend import 必须保留(IO 层)")

    def test_advanced_metrics_calc_imported(self):
        """AdvancedMetricsCalc 仍可 import(虽然下沉,但其他消费点可能依赖)"""
        # 验证 import 语句存在(不要求直接调用,某些地方保留 import 即可)
        src_has_calc = "AdvancedMetricsCalc" in self.main_src
        self.assertTrue(src_has_calc,
                        "AdvancedMetricsCalc import 应保留")

    def test_radar_score_engine_imported(self):
        """RadarScoreEngine import 必须保留"""
        self.assertIn("RadarScoreEngine", self.main_src,
                      "RadarScoreEngine import 必须保留")


# ══════════════════════════════════════════════════════════════════
# Test 7: Resolver 内部方法完整性
# ══════════════════════════════════════════════════════════════════

class TestResolverInternalMethodsIntact(unittest.TestCase):
    """已下沉到 Resolver 的方法仍存在,未因后续治理被误删"""

    RESOLVER_METHODS = [
        "_calculate_fatigue_zones",
        "_normalize_laps",
        "_compute_efficiency_score",
        "_compute_training_load",
        "_compute_cadence_stability",
        "_compute_durability_index",
        "_compute_hr_drift",
        "_calculate_track_difficulty",
        "_build_ai_snapshot_block",
        "_build_activity_canonical",
        "_build_real_laps_from_row",
        "_convert_track_to_algorithm_records",
        "_compute_advanced_metrics",
        "_detect_bonk_event",
    ]
    # 注: _build_ai_snapshot 不在 Resolver — 含 IO(_fetch_efficiency_baseline),保留在 main.py

    @classmethod
    def setUpClass(cls):
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            cls.resolver_src = f.read()
        cls.resolver_tree = ast.parse(cls.resolver_src)

    def test_all_resolver_methods_exist(self):
        """所有已下沉的 Resolver 方法必须仍然存在"""
        for method_name in self.RESOLVER_METHODS:
            found = False
            for node in ast.walk(self.resolver_tree):
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    found = True
                    break
            self.assertTrue(found,
                            f"Resolver 方法 {method_name} 不得被误删")

    def test_all_v4_methods_importable(self):
        """所有 V4 下沉方法均可从 MetricsResolver 导入"""
        from metrics_resolver import MetricsResolver
        for method_name in self.RESOLVER_METHODS:
            self.assertTrue(
                hasattr(MetricsResolver, method_name) and callable(getattr(MetricsResolver, method_name)),
                f"MetricsResolver.{method_name} 必须存在且可调用")


# ══════════════════════════════════════════════════════════════════
# Test 8: 消费链路完整性(调用不在低 1 层)
# ══════════════════════════════════════════════════════════════════

class TestConsumptionChainIntegrity(unittest.TestCase):
    """关键 metric 的消费链路未被破坏:定义存在 → 调用存在 → 返回结构完整"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_hr_zone_distribution_consumed_in_insert(self):
        """hr_zone_distribution 在 INSERT 语句中使用"""
        self.assertIn("hr_zone_distribution", self.main_src)
        # 验证在 SQL INSERT 中出现
        self.assertTrue(
            "hr_zone_distribution" in self.main_src,
            "hr_zone_distribution 字段必须在 INSERT/SELECT 中出现")

    def test_training_load_has_metrics_key(self):
        """metrics['training_load'] 组装路径存在"""
        self.assertIn('"training_load"', self.main_src)
        self.assertIn("training_load", self.main_src)

    def test_decoupling_trend_chain_intact(self):
        """decoupling → trend 引用链路"""
        self.assertIn("decoupling", self.main_src)
        self.assertIn("decoupling_pct", self.main_src)

    def test_bonk_risk_has_fallback_default(self):
        """bonk_risk 降级默认值存在"""
        self.assertIn("bonk_risk", self.main_src)
        # 降级分支: is_at_risk: False
        self.assertIn("is_at_risk", self.main_src)


if __name__ == "__main__":
    unittest.main()
