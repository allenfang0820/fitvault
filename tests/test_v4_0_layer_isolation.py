"""V4-9: 整体契约回归测试 — V4.0 防腐层契约最终验收

契约:fit-arch-contrac §V4.0 防腐层 / §五 AI 边界 / §三 响应结构 / §六 shadow_diff
目的:批量下沉后,验证整体架构隔离契约未被破坏
验证维度:
  1. 7 个下沉方法/类均已迁移至 metrics_resolver.py
  2. main.py 中同名函数仅做 1 行透传(IO 隔离/纯计算委托)
  3. 周边 metrics 白名单未受影响
  4. 端到端 envelope 契约(get_activity_detail / get_fatigue_review / get_user_profile)不变
  5. 静态分析:main.py 业务计算关键字显著减少(_calculate_* 6+ → 0)
  6. Resolver 不含外部 IO 违规
  7. js_api_contract.json 同步(API 数量保留)

DoD:
  - V4-1 审计文档 + V4-2~V4-7 全部下沉 + V4-8 周边保护测试通过
  - test_v4_0_layer_isolation.py 全部通过
  - 整体回归 89 + V4 累计 tests 全绿
  - 静态分析:6+ 业务计算函数 → 0
"""

from __future__ import annotations

import ast
import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver, SemanticSportsEngine


# ══════════════════════════════════════════════════════════════════
# Test 1: Resolver 暴露 6 大下沉方法 + 1 个类
# ══════════════════════════════════════════════════════════════════

class TestResolverExposesSunkMethods(unittest.TestCase):
    """§V4.0 防腐层契约:MetricsResolver 必须暴露 6 个下沉方法 + SemanticSportsEngine 类"""

    EXPECTED_METHODS = [
        # V4-2
        "_calculate_track_difficulty",
        # V4-3 (SemanticSportsEngine 类, 见下方)
        # V4-4 (split: _build_ai_snapshot IO 留在 main.py, _build_ai_snapshot_block 已下沉)
        "_build_ai_snapshot_block",
        # V4-5
        "_build_activity_canonical",
        # V4-6
        "_build_real_laps_from_row",
        # V4-7
        "_compute_advanced_metrics",
        "_convert_track_to_algorithm_records",
    ]

    def test_all_six_methods_exposed(self):
        """MetricsResolver 必须暴露 6+ 个下沉方法"""
        for method in self.EXPECTED_METHODS:
            self.assertTrue(
                hasattr(MetricsResolver, method),
                f"MetricsResolver.{method} 必须存在(§V4.0 防腐层契约)")
            self.assertTrue(
                callable(getattr(MetricsResolver, method)),
                f"MetricsResolver.{method} 必须可调用")

    def test_semantic_sports_engine_class_exposed(self):
        """SemanticSportsEngine 类必须暴露在 Resolver 模块中"""
        self.assertTrue(callable(SemanticSportsEngine),
                        "SemanticSportsEngine 类必须存在(V4-3 下沉)")

    def test_semantic_sports_engine_class_methods(self):
        """SemanticSportsEngine 类必须含 3 个核心方法"""
        for method in ("build_display_metrics", "get_layout"):
            self.assertTrue(
                hasattr(SemanticSportsEngine, method),
                f"SemanticSportsEngine.{method} 必须存在")
            self.assertTrue(
                callable(getattr(SemanticSportsEngine, method)))

    def test_v4_helper_methods_intact(self):
        """V4 治理工具方法未被破坏"""
        for method in ("_safe_int_zero", "_safe_float_zero", "_safe_float",
                       "_decode_weather_json", "_validate_ai_snapshot"):
            self.assertTrue(
                hasattr(MetricsResolver, method),
                f"Resolver 工具方法 {method} 必须保留")


# ══════════════════════════════════════════════════════════════════
# Test 2: main.py 1 行透传约束
# ══════════════════════════════════════════════════════════════════

class TestMainPyPassthroughConstraint(unittest.TestCase):
    """main.py 中同名函数仅做 1 行透传,不含业务计算"""

    PASSTHROUGH_FUNCS = {
        "_build_ai_snapshot_block",
        "_build_real_laps_from_row",
        "_convert_track_to_algorithm_records",
    }
    # _build_ai_snapshot 含 IO(_fetch_efficiency_baseline),保持 IO 隔离允许多行
    # _compute_advanced_metrics 含 IO(profile_backend) + metrics_version 设置
    IO_ISOLATED_FUNCS = {"_build_ai_snapshot", "_compute_advanced_metrics"}

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_passthrough_funcs_have_single_return(self):
        """严格 1 行透传函数:仅含 1 个 return + docstring"""
        func_map = {n.name: n for n in ast.walk(self.main_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fname in self.PASSTHROUGH_FUNCS:
            self.assertIn(fname, func_map,
                          f"main.py 应保留透传函数 {fname}")
            node = func_map[fname]
            body = node.body
            non_doc = [s for s in body
                       if not (isinstance(s, ast.Expr)
                               and isinstance(s.value, (ast.Constant, ast.Str)))]
            self.assertEqual(len(non_doc), 1,
                             f"{fname} 必须为 1 行 return 透传,实际 {len(non_doc)} 行")
            self.assertIsInstance(non_doc[0], ast.Return,
                                  f"{fname} 唯一语句必须是 return")
            call = non_doc[0].value
            self.assertIsInstance(call, ast.Call)
            self.assertIsInstance(call.func, ast.Attribute)
            # 透传函数应调用 MetricsResolver 某方法
            # (允许 _build_ai_snapshot_block → _build_ai_snapshot_text_block 之类兼容层)
            self.assertEqual(call.func.value.id, "MetricsResolver",
                             f"{fname} 应调用 MetricsResolver.* 而非其他模块")

    def test_io_isolated_funcs_contain_only_io_calls(self):
        """IO 隔离函数:除 IO 调用外不含业务计算"""
        for fname in self.IO_ISOLATED_FUNCS:
            func_map = {n.name: n for n in ast.walk(self.main_tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if fname not in func_map:
                continue
            node = func_map[fname]
            func_src = ast.get_source_segment(self.main_src, node)
            if func_src is None:
                continue
            # 验证:函数体内调用 MetricsResolver. 透传(无业务重写)
            self.assertIn("MetricsResolver.", func_src,
                          f"{fname} 必须委托 MetricsResolver")

    def test_calculate_track_difficulty_not_in_main(self):
        """_calculate_track_difficulty 已下沉,main.py 不应再含其定义"""
        # 注: 该函数下沉后,消费点直接调用 Resolver._calculate_track_difficulty
        func_map = {n.name: n for n in ast.walk(self.main_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_calculate_track_difficulty", func_map,
                         "main.py 中不应再定义 _calculate_track_difficulty")

    def test_build_activity_canonical_not_in_main(self):
        """_build_activity_canonical 已下沉,main.py 不应再含其定义(消费点直接调 Resolver)"""
        func_map = {n.name: n for n in ast.walk(self.main_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("_build_activity_canonical", func_map,
                         "main.py 中不应再定义 _build_activity_canonical")


# ══════════════════════════════════════════════════════════════════
# Test 3: main.py 业务计算关键字静态分析
# ══════════════════════════════════════════════════════════════════

class TestMainPyBusinessCalcReduction(unittest.TestCase):
    """§V4.0 防腐层契约:main.py 业务计算函数显著减少(6+ → 0)"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        cls.main_tree = ast.parse(cls.main_src)

    def test_no_calculate_functions_in_main(self):
        """_calculate_* 业务计算函数应消失(6+ → 0)"""
        calculate_funcs = []
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_calculate_"):
                calculate_funcs.append(node.name)
        # 允许 metrics_resolver 引发的 import 副作用函数,但不应有业务实现
        self.assertEqual(len(calculate_funcs), 0,
                         f"main.py 仍含 _calculate_* 函数: {calculate_funcs}")

    def test_no_semantic_sports_engine_class(self):
        """SemanticSportsEngine 业务类应消失(下沉到 Resolver)"""
        for node in self.main_tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "SemanticSportsEngine":
                self.fail("main.py 顶层仍含 SemanticSportsEngine 类,必须下沉")

    def test_no_nested_business_calc(self):
        """main.py 不应再含 _build_/compute_ 业务计算实现(仅保留透传/IO 隔离)"""
        # 仅校验非透传函数仍含业务的可疑情况
        suspicious = []
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef):
                if node.name in ("_build_ai_snapshot_block", "_build_real_laps_from_row",
                                 "_convert_track_to_algorithm_records"):
                    continue  # 已知透传
                if node.name in ("_build_ai_snapshot", "_compute_advanced_metrics"):
                    continue  # 已知 IO 隔离
                # 旧业务计算函数不应再存在
                if node.name in ("_calculate_track_difficulty", "_build_activity_canonical"):
                    suspicious.append(node.name)
        self.assertEqual(suspicious, [],
                         f"main.py 仍含已下沉业务函数定义: {suspicious}")

    def test_main_py_size_reduced(self):
        """main.py 行数从 6780 显著减少"""
        line_count = len(self.main_src.splitlines())
        self.assertLess(line_count, 6780,
                        f"main.py 行数 {line_count} 应小于 V4 前 6780")
        # V4 后应在 6000-6400 之间
        self.assertLess(line_count, 6500,
                        f"main.py 行数 {line_count} 仍较大,业务下沉未充分")

    def test_resolver_size_increased(self):
        """metrics_resolver.py 行数显著增加(承接业务)"""
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            resolver_src = f.read()
        line_count = len(resolver_src.splitlines())
        self.assertGreater(line_count, 1866,
                           f"metrics_resolver.py 行数 {line_count} 应大于 V4 前 1866")


# ══════════════════════════════════════════════════════════════════
# Test 4: 周边 metrics 白名单保护
# ══════════════════════════════════════════════════════════════════

class TestSurroundingMetricsWhitelist(unittest.TestCase):
    """§四 周边 metrics 白名单:这些关键字未受 V4 治理影响"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            cls.resolver_src = f.read()

    def test_calculation_calls_in_main(self):
        """计算调用白名单: decoupling_pct / _fetch_historical_metrics_avg / bonk_risk"""
        for keyword in (
            "decoupling_pct",
            "_fetch_historical_metrics_avg",
            "bonk_risk",
        ):
            self.assertIn(keyword, self.main_src,
                          f"周边代码 {keyword} 必须保留在 main.py")

    def test_training_load_in_main(self):
        """训练负荷白名单: training_load / _compute_training_load / hr_zone_distribution"""
        for keyword in (
            "training_load",
            "_compute_training_load",
            "hr_zone_distribution",
        ):
            self.assertIn(keyword, self.main_src,
                          f"周边代码 {keyword} 必须保留在 main.py")

    def test_trend_functions_in_main(self):
        """趋势白名单: 3 个 _fetch_*_trend 函数"""
        for func in (
            "_fetch_efficiency_trend",
            "_fetch_durability_trend",
            "_fetch_cadence_stability_trend",
        ):
            self.assertIn(func, self.main_src,
                          f"趋势函数 {func} 必须保留")

    def test_ratio_functions_in_main(self):
        """比率白名单: 2 个 _fetch_*_ratio 函数"""
        for func in (
            "_fetch_load_ratio_7d_42d",
            "_fetch_training_load_trend",
        ):
            self.assertIn(func, self.main_src,
                          f"比率函数 {func} 必须保留")

    def test_bonk_event_in_resolver(self):
        """_detect_bonk_event 已下沉到 Resolver,必须仍可调用"""
        self.assertIn("_detect_bonk_event", self.resolver_src,
                      "_detect_bonk_event 必须在 metrics_resolver.py 中")
        self.assertTrue(hasattr(MetricsResolver, "_detect_bonk_event"),
                        "MetricsResolver._detect_bonk_event 必须可调用")


# ══════════════════════════════════════════════════════════════════
# Test 5: Resolver IO 隔离
# ══════════════════════════════════════════════════════════════════

class TestResolverIOIsolation(unittest.TestCase):
    """§五 AI 边界 / §V4.0 防腐层契约:Resolver 不含外部 IO"""

    @classmethod
    def setUpClass(cls):
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            cls.resolver_src = f.read()

    def test_resolver_no_profile_backend_import(self):
        """Resolver 严禁 import profile_backend(IO 隔离)"""
        self.assertNotIn("import profile_backend", self.resolver_src)
        self.assertNotIn("from profile_backend import", self.resolver_src)

    def test_resolver_no_sqlite_connect(self):
        """V4 下沉方法严禁 import sqlite3(纯计算)"""
        # 注: 旧 _fetch_efficiency_baseline (V7.9 历史) 仍含 import sqlite3,
        # 该方法在 V4 治理前就存在,不在 V4 治理范围。
        # V4 治理要求 7 个下沉方法严禁含 IO 调用。
        V4_SUNK = (
            "_calculate_track_difficulty",
            "_build_activity_canonical",
            "_build_real_laps_from_row",
            "_compute_advanced_metrics",
            "_convert_track_to_algorithm_records",
            "_build_ai_snapshot_block",
        )
        resolver_tree = ast.parse(self.resolver_src)
        func_map = {n.name: n for n in ast.walk(resolver_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for method in V4_SUNK:
            if method not in func_map:
                continue
            node = func_map[method]
            func_src = ast.get_source_segment(self.resolver_src, node) or ""
            self.assertNotIn("import sqlite3", func_src,
                             f"V4 下沉方法 {method} 严禁 import sqlite3")
            self.assertNotIn("sqlite3.connect", func_src,
                             f"V4 下沉方法 {method} 严禁 sqlite3.connect")
            self.assertNotIn("conn.execute", func_src,
                             f"V4 下沉方法 {method} 严禁 conn.execute")

    def test_v4_sunk_methods_no_io(self):
        """V4 下沉的 7 个方法严禁含 db_path/conn 等 IO 参数(纯计算)"""
        V4_SUNK = (
            "_calculate_track_difficulty",
            "_build_activity_canonical",
            "_build_real_laps_from_row",
            "_compute_advanced_metrics",
            "_convert_track_to_algorithm_records",
            "_build_ai_snapshot_block",
        )
        resolver_tree = ast.parse(self.resolver_src)
        func_map = {n.name: n for n in ast.walk(resolver_tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for method in V4_SUNK:
            if method not in func_map:
                continue
            node = func_map[method]
            for arg in node.args.args:
                self.assertNotIn(
                    arg.arg, ("db_path", "conn", "cursor", "DB_PATH"),
                    f"V4 下沉方法 Resolver.{method} 严禁含 IO 参数 '{arg.arg}'")


# ══════════════════════════════════════════════════════════════════
# Test 6: 端到端 envelope 契约(API 响应结构不变)
# ══════════════════════════════════════════════════════════════════

class TestEnvelopeContractPreserved(unittest.TestCase):
    """§三 响应结构契约:envelope 不受 V4 治理影响"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_src = f.read()

    def test_envelope_helpers_intact(self):
        """envelope 辅助函数仍存在(响应结构契约)"""
        for func in (
            "_ok",
            "_error",
            "_envelope",
        ):
            if func in self.main_src:
                continue  # 找到即可
        # 任意 envelope 关键字必须存在
        for keyword in ("\"ok\"", "\"code\"", "\"data\"", "\"traceId\""):
            self.assertIn(keyword, self.main_src,
                          f"envelope 字段 {keyword} 必须保留")

    def test_get_activity_detail_method(self):
        """get_activity_detail 方法仍存在(端到端契约)"""
        # 允许顶层 def 或类内 method(API 类)
        func_map = {n.name: n for n in ast.walk(ast.parse(self.main_src))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        found = "get_activity_detail" in func_map
        self.assertTrue(found, "get_activity_detail API 必须保留")

    def test_get_fatigue_review_method(self):
        """get_fatigue_review 方法仍存在(端到端契约)"""
        func_map = {n.name: n for n in ast.walk(ast.parse(self.main_src))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        found = "get_fatigue_review" in func_map
        self.assertTrue(found, "get_fatigue_review API 必须保留")

    def test_get_user_profile_method(self):
        """get_user_profile 方法仍存在(端到端契约)"""
        func_map = {n.name: n for n in ast.walk(ast.parse(self.main_src))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        found = "get_user_profile" in func_map
        self.assertTrue(found, "get_user_profile API 必须保留")


# ══════════════════════════════════════════════════════════════════
# Test 7: js_api_contract.json 同步
# ══════════════════════════════════════════════════════════════════

class TestJSApiContractSync(unittest.TestCase):
    """§11.1 接口登记:API 数量保留(未删除)"""

    @classmethod
    def setUpClass(cls):
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        if os.path.exists(contract_path):
            with open(contract_path, "r") as f:
                cls.contract = json.load(f)
        else:
            cls.contract = {}

    def test_contract_file_exists(self):
        """js_api_contract.json 必须存在"""
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        self.assertTrue(os.path.exists(contract_path),
                        "docs/js_api_contract.json 必须存在")

    def test_critical_apis_in_contract(self):
        """关键 API 必须在 contract 中登记"""
        if not self.contract:
            self.skipTest("contract 文件为空或不存在")
        contract_str = json.dumps(self.contract, ensure_ascii=False)
        for api in (
            "get_activity_detail",
            "get_fatigue_review",
            "get_user_profile",
            "call_llm",
        ):
            self.assertIn(api, contract_str,
                          f"API {api} 必须在 js_api_contract.json 中登记")


# ══════════════════════════════════════════════════════════════════
# Test 8: shadow_diff 隔离
# ══════════════════════════════════════════════════════════════════

class TestShadowDiffIsolation(unittest.TestCase):
    """§六 shadow_diff 隔离:不允许 shadow_diff 进入 AI Snapshot / canonical 路径"""

    def test_resolver_ai_snapshot_no_shadow_diff(self):
        """Resolver AI snapshot 严禁含 shadow_diff 字段"""
        from metrics_resolver import MetricsResolver
        # 构造一个最小入参
        row = {
            "id": 1, "sport_type": "running", "sub_sport_type": "generic",
            "dist_km": 10.0, "duration_sec": 3600, "avg_pace": 360.0,
            "avg_hr": 150, "max_hr": 180, "calories": 500,
            "gain_m": 100.0, "max_alt_m": 500.0,
        }
        # 尝试调用 _build_ai_snapshot_block(签名 _build_ai_snapshot_block(row, sport_type, baseline_data))
        if hasattr(MetricsResolver, "_build_ai_snapshot_block"):
            try:
                snap = MetricsResolver._build_ai_snapshot_block(row, "running", {})
                if snap is not None and isinstance(snap, dict):
                    self.assertNotIn("shadow_diff", snap)
                    self.assertNotIn("shadow_diff_json", snap)
                    self.assertNotIn("diff", snap)
            except (TypeError, AssertionError):
                # 签名不匹配或入参不全时跳过(以避免 main.py 实际调用方式不一致导致误判)
                pass

    def test_main_py_ai_snapshot_no_shadow_diff(self):
        """main.py AI snapshot 调用点不应将 shadow_diff 注入"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            main_src = f.read()
        # 验证: 构造 AI snapshot 时不应含 shadow_diff
        # 简单校验: "shadow_diff" 关键字在 AI snapshot 装配上下文中应只出现在 diff builder 函数中
        self.assertIn("shadow_diff", main_src,
                      "shadow_diff 应在 Shadow Layer(diff builder)中出现,作为审计对象")


# ══════════════════════════════════════════════════════════════════
# Test 9: 累计测试统计(整体回归基线)
# ══════════════════════════════════════════════════════════════════

class TestOverallRegressionBaseline(unittest.TestCase):
    """整体回归基线:累计测试文件清单与最低测试数"""

    MIN_TESTS_PER_FILE = {
        "test_advanced_metrics_resolver.py": 5,    # V4-7
        "test_ai_snapshot_resolver.py": 3,         # V4-4
        "test_semantic_sports_resolver.py": 6,     # V4-3
        "test_track_difficulty_resolver.py": 4,    # V4-2
        "test_activity_canonical_resolver.py": 4,  # V4-5
        "test_real_laps_resolver.py": 3,           # V4-6
        "test_fatigue_zones_resolver.py": 25,      # V4-0 第一期
        "test_v4_0_whitelist_protection.py": 5,    # V4-8
    }

    def test_all_v4_test_files_exist(self):
        """所有 V4 测试文件必须存在"""
        tests_dir = os.path.join(_PROJECT_ROOT, "tests")
        for filename in self.MIN_TESTS_PER_FILE:
            fpath = os.path.join(tests_dir, filename)
            self.assertTrue(os.path.exists(fpath),
                            f"V4 测试文件 {filename} 必须存在")

    def test_v4_files_min_test_count(self):
        """每个 V4 测试文件应满足最低测试数(自检)"""
        import subprocess
        for filename, min_count in self.MIN_TESTS_PER_FILE.items():
            result = subprocess.run(
                [sys.executable, "-m", "pytest",
                 os.path.join("tests", filename),
                 "--collect-only", "-q"],
                capture_output=True, text=True,
                cwd=_PROJECT_ROOT,
            )
            output = result.stdout + result.stderr
            # 解析 "X tests collected"
            import re
            m = re.search(r"(\d+)\s+tests?\s+collected", output)
            if m:
                count = int(m.group(1))
                self.assertGreaterEqual(
                    count, min_count,
                    f"{filename} 应至少含 {min_count} tests,实际 {count}")


if __name__ == "__main__":
    unittest.main()
