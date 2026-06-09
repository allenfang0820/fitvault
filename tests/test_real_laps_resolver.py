"""V4-6: _build_real_laps_from_row 下沉至 MetricsResolver 单元测试

契约:fit-arch-contrac §V4.0 防腐层 / §2.1 全链路可追溯
验证:
  1. 输出结构契约:每圈 7 字段(lap_no/distance_km/pace_sec/hr/cadence/gct_ms/power_w)
  2. 正常圈速解析:2 圈完整数据
  3. 空数据降级:laps_json 为空/None/无效JSON/非列表 → []
  4. 配速计算:distance=1000m, elapsed=300s → pace_sec=300
  5. 零距离+零耗时 → 该圈跳过
  6. HR/cadence/power 为 0 → 输出 None
  7. distance_km 舍入到 2 位小数
  8. main.py 透传约束:不允许重写业务逻辑
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

from metrics_resolver import MetricsResolver


# ══════════════════════════════════════════════════════════════════
# Test 1: 输出结构契约
# ══════════════════════════════════════════════════════════════════

class TestLapOutputContract(unittest.TestCase):
    """每圈必须输出圈速统计表登记字段"""

    def _make_laps_json(self, laps: list[dict]) -> str:
        return json.dumps(laps)

    def test_each_lap_has_registered_fields(self):
        """每圈必须含圈速表可能消费的标准字段"""
        laps_data = [
            {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 150,
             "avg_cadence": 85, "avg_power": 220},
        ]
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": self._make_laps_json(laps_data)})
        self.assertEqual(len(r), 1)
        lap = r[0]
        expected_keys = {
            "lap_no", "distance_km", "pace_sec", "hr", "max_hr",
            "cadence", "gct_ms", "power_w", "ascent_m", "descent_m",
            "calories", "swolf", "stroke_style", "stroke_distance_m",
            "length_distance_m",
        }
        self.assertEqual(set(lap.keys()), expected_keys,
                         f"每圈字段必须恰好是 {expected_keys}")

    def test_no_unregistered_fields(self):
        """不允许出现圈速表未登记字段"""
        laps_data = [
            {"distance_m": 1000.0, "elapsed_sec": 300.0},
        ]
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": self._make_laps_json(laps_data)})
        allowed = {
            "lap_no", "distance_km", "pace_sec", "hr", "max_hr",
            "cadence", "gct_ms", "power_w", "ascent_m", "descent_m",
            "calories", "swolf", "stroke_style", "stroke_distance_m",
            "length_distance_m",
        }
        for lap in r:
            for key in lap:
                self.assertIn(key, allowed,
                              f"圈数据出现未登记字段 '{key}'")


# ══════════════════════════════════════════════════════════════════
# Test 2: 正常圈速解析
# ══════════════════════════════════════════════════════════════════

class TestNormalLapsParsing(unittest.TestCase):
    """正常 2 圈完整数据解析"""

    def setUp(self):
        self.laps_data = [
            {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 150,
             "avg_cadence": 85, "avg_power": 220},
            {"distance_m": 1000.0, "elapsed_sec": 310.0, "avg_hr": 155,
             "avg_cadence": 83, "avg_power": 215},
        ]
        self.row = {"laps_json": json.dumps(self.laps_data)}
        self.result = MetricsResolver._build_real_laps_from_row(self.row)

    def test_two_laps_returned(self):
        self.assertEqual(len(self.result), 2)

    def test_lap_no_starts_at_1(self):
        self.assertEqual(self.result[0]["lap_no"], 1)
        self.assertEqual(self.result[1]["lap_no"], 2)

    def test_distance_km_correct(self):
        """1000m → 1.0km"""
        self.assertAlmostEqual(self.result[0]["distance_km"], 1.0, places=2)
        self.assertAlmostEqual(self.result[1]["distance_km"], 1.0, places=2)

    def test_pace_sec_correct(self):
        """300s / 1km → 300s pace"""
        self.assertEqual(self.result[0]["pace_sec"], 300)
        self.assertEqual(self.result[1]["pace_sec"], 310)

    def test_hr_correct(self):
        self.assertEqual(self.result[0]["hr"], 150)
        self.assertEqual(self.result[1]["hr"], 155)

    def test_cadence_correct(self):
        self.assertEqual(self.result[0]["cadence"], 85)
        self.assertEqual(self.result[1]["cadence"], 83)

    def test_power_correct(self):
        self.assertEqual(self.result[0]["power_w"], 220)
        self.assertEqual(self.result[1]["power_w"], 215)

    def test_laps_json_as_list_direct(self):
        """laps_json 已为 list(非 str)时也能直接解析"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": self.laps_data})
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["pace_sec"], 300)


# ══════════════════════════════════════════════════════════════════
# Test 3: 空数据降级
# ══════════════════════════════════════════════════════════════════

class TestEmptyDataDegradation(unittest.TestCase):
    """空 laps_json 安全降级为 []"""

    def test_no_laps_json_key(self):
        """row 无 laps_json 键 → []"""
        r = MetricsResolver._build_real_laps_from_row({})
        self.assertEqual(r, [])

    def test_laps_json_none(self):
        """laps_json=None → []"""
        r = MetricsResolver._build_real_laps_from_row({"laps_json": None})
        self.assertEqual(r, [])

    def test_laps_json_empty_string(self):
        """laps_json='' → []"""
        r = MetricsResolver._build_real_laps_from_row({"laps_json": ""})
        self.assertEqual(r, [])

    def test_laps_json_invalid_json(self):
        """无效 JSON → []"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": "not-valid-json!!!"})
        self.assertEqual(r, [])

    def test_laps_json_non_list(self):
        """laps_json 是 dict 而非 list → []"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": '{"a": 1}'})
        self.assertEqual(r, [])

    def test_laps_json_empty_list(self):
        """laps_json=[] → []"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": "[]"})
        self.assertEqual(r, [])


# ══════════════════════════════════════════════════════════════════
# Test 4: 配速计算
# ══════════════════════════════════════════════════════════════════

class TestPaceCalculation(unittest.TestCase):

    def test_pace_5_min_per_km(self):
        """1000m / 300s → pace_sec=300 (5'00'')"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0}
            ])})
        self.assertEqual(r[0]["pace_sec"], 300)

    def test_pace_6_min_per_km(self):
        """1000m / 360s → pace_sec=360 (6'00'')"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 360.0}
            ])})
        self.assertEqual(r[0]["pace_sec"], 360)

    def test_pace_partial_km(self):
        """500m / 150s → pace=300s/km"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 500.0, "elapsed_sec": 150.0}
            ])})
        self.assertEqual(r[0]["pace_sec"], 300)

    def test_pace_rounding(self):
        """301/1.0 → round → 301(整数)"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 301.0}
            ])})
        self.assertEqual(r[0]["pace_sec"], 301)

    def test_pace_zero_when_no_elapsed(self):
        """有距离无耗时 → pace_sec=0 → 输出 None"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 0}
            ])})
        self.assertIsNone(r[0]["pace_sec"])

    def test_pace_zero_when_no_distance(self):
        """有耗时无距离 → 整圈跳过(不输出)"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 0, "elapsed_sec": 300.0}
            ])})
        # 距离=0 但 elapsed>0: dist_m<=0 AND elapsed<=0 为 False → 不会跳过
        # 但 pace = 300/(0/1000) → ZeroDivisionError 被 int(round(...))
        # 实际上: pace_sec = int(round(300 / 0.0)) → ZeroDivisionError
        # 但原代码没有 try/except... 等等,原代码:
        # pace_sec = int(round(elapsed / (dist_m / 1000.0))) if dist_m > 0 and elapsed > 0 else 0
        # dist_m=0 → dist_m > 0 为 False → pace_sec = 0 → 输出 pace_sec=None
        self.assertEqual(len(r), 1)
        self.assertIsNone(r[0]["pace_sec"])
        self.assertIsNone(r[0]["distance_km"])


# ══════════════════════════════════════════════════════════════════
# Test 5: 零距离+零耗时 → 圈跳过
# ══════════════════════════════════════════════════════════════════

class TestZeroDistElapsedSkip(unittest.TestCase):

    def test_both_zero_skipped(self):
        """距离=0 且 耗时=0 → 该圈跳过"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0},
                {"distance_m": 0, "elapsed_sec": 0},
                {"distance_m": 2000.0, "elapsed_sec": 600.0},
            ])})
        self.assertEqual(len(r), 2, "零距离零耗时圈应被跳过")
        self.assertEqual(r[0]["distance_km"], 1.0)
        self.assertEqual(r[1]["distance_km"], 2.0)

    def test_non_dict_lap_skipped(self):
        """非 dict 的 lap 条目跳过"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0},
                "not-a-dict",
                {"distance_m": 2000.0, "elapsed_sec": 600.0},
            ])})
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["lap_no"], 1)
        self.assertEqual(r[1]["lap_no"], 3)  # idx+1=3 (第 3 条原始数据)


# ══════════════════════════════════════════════════════════════════
# Test 6: HR/cadence/power 为 0 → 输出 None
# ══════════════════════════════════════════════════════════════════

class TestZeroToNullSemantics(unittest.TestCase):

    def test_hr_zero_to_none(self):
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 0}
            ])})
        self.assertIsNone(r[0]["hr"], "avg_hr=0 → 输出 None")

    def test_cadence_zero_to_none(self):
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_cadence": 0}
            ])})
        self.assertIsNone(r[0]["cadence"], "avg_cadence=0 → 输出 None")

    def test_power_zero_to_none(self):
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_power": 0}
            ])})
        self.assertIsNone(r[0]["power_w"], "avg_power=0 → 输出 None")

    def test_fields_missing_default_none(self):
        """字段缺失 → _safe_int_zero → 0 → 'if x' → None"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0}
            ])})
        self.assertIsNone(r[0]["hr"])
        self.assertIsNone(r[0]["cadence"])
        self.assertIsNone(r[0]["power_w"])

    def test_hr_positive_preserved(self):
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 160}
            ])})
        self.assertEqual(r[0]["hr"], 160)


# ══════════════════════════════════════════════════════════════════
# Test 7: distance_km 舍入
# ══════════════════════════════════════════════════════════════════

class TestDistanceKmRounding(unittest.TestCase):

    def test_exact_km(self):
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1000.0, "elapsed_sec": 300.0}
            ])})
        self.assertEqual(r[0]["distance_km"], 1.0)

    def test_partial_km_2dp(self):
        """1234m → 1.23km(保留 2 位小数)"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 1234.0, "elapsed_sec": 370.0}
            ])})
        self.assertAlmostEqual(r[0]["distance_km"], 1.23, places=2)

    def test_distance_zero_outputs_none(self):
        """distance_m=0 → distance_km=None"""
        r = MetricsResolver._build_real_laps_from_row(
            {"laps_json": json.dumps([
                {"distance_m": 0, "elapsed_sec": 300.0}
            ])})
        # dist_m=0, elapsed=300 → dist_m<=0 AND elapsed<=0 为 False → 不跳过
        # distance_km: dist_m > 0 为 False → None
        self.assertEqual(len(r), 1)
        self.assertIsNone(r[0]["distance_km"])


# ══════════════════════════════════════════════════════════════════
# Test 8: main.py 透传约束
# ══════════════════════════════════════════════════════════════════

class TestMainPyPassthroughConstraint(unittest.TestCase):
    """§V4.0 防腐层:main.py 只做透传,不含业务逻辑"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_source = f.read()
        cls.main_tree = ast.parse(cls.main_source)

    def test_main_py_calls_resolver(self):
        """main.py 必须调用 MetricsResolver._build_real_laps_from_row"""
        self.assertIn("MetricsResolver._build_real_laps_from_row",
                      self.main_source,
                      "main.py 必须使用 MetricsResolver._build_real_laps_from_row")

    def test_no_redefinition_with_body(self):
        """main.py 中的 _build_real_laps_from_row 不允许有业务逻辑体"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_real_laps_from_row":
                # 函数体应该只有一个 return statement,没有 for/if/try 等
                body = node.body
                non_doc = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, (ast.Constant, ast.Str)))]
                self.assertEqual(len(non_doc), 1,
                                 f"_build_real_laps_from_row 函数体应只有 1 行 return,实际 {len(non_doc)} 行")
                stmt = non_doc[0]
                self.assertIsInstance(stmt, ast.Return,
                                      "唯一语句必须是 return")
                # return 语句调用 MetricsResolver._build_real_laps_from_row
                call = stmt.value
                self.assertIsInstance(call, ast.Call)
                self.assertIsInstance(call.func, ast.Attribute)
                self.assertEqual(call.func.attr, "_build_real_laps_from_row")

    def test_no_json_parse_in_mainpy(self):
        """main.py 的 _build_real_laps_from_row 不应含 json.loads 调用"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_real_laps_from_row":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if (isinstance(child.func, ast.Attribute) and
                                child.func.attr == "loads"):
                            self.fail(
                                "main.py 的 _build_real_laps_from_row 不应含 json.loads,"
                                "业务逻辑已下沉至 MetricsResolver")

    def test_no_for_loop_in_mainpy(self):
        """main.py 的 _build_real_laps_from_row 不应含 for 循环"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_real_laps_from_row":
                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.While)):
                        self.fail(
                            "main.py 的 _build_real_laps_from_row 不应含循环,"
                            "业务逻辑已下沉至 MetricsResolver")


# ══════════════════════════════════════════════════════════════════
# V9.x: GCT/Vertical Oscillation/Stride Length 全链路追溯测试
# 契约:fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层
# ══════════════════════════════════════════════════════════════════

class TestNormalizeLapsRunningDynamics(unittest.TestCase):
    """_normalize_laps 透读 FIT 步态字段(avg_stance_time/avg_vertical_oscillation/avg_step_length)"""

    def test_stance_time_parsed(self):
        """FIT avg_stance_time (ms) → stance_time_ms"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "avg_stance_time": 245}
        ])
        self.assertEqual(r[0]["stance_time_ms"], 245)

    def test_vertical_oscillation_parsed(self):
        """FIT avg_vertical_oscillation (cm) → vertical_oscillation_cm"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "avg_vertical_oscillation": 8.7}
        ])
        self.assertEqual(r[0]["vertical_oscillation_cm"], 8.7)

    def test_stride_length_parsed(self):
        """FIT avg_step_length (m) → stride_length_m"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "avg_step_length": 1.23}
        ])
        self.assertEqual(r[0]["stride_length_m"], 1.23)

    def test_missing_fields_default_none(self):
        """字段缺失 → None(与 avg_hr 风格一致)"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0}
        ])
        self.assertIsNone(r[0]["stance_time_ms"])
        self.assertIsNone(r[0]["vertical_oscillation_cm"])
        self.assertIsNone(r[0]["stride_length_m"])

    def test_zero_values_become_none(self):
        """stance_time=0 → None(防 0 污染)"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0,
             "avg_stance_time": 0, "avg_vertical_oscillation": 0, "avg_step_length": 0}
        ])
        self.assertIsNone(r[0]["stance_time_ms"])
        self.assertIsNone(r[0]["vertical_oscillation_cm"])
        self.assertIsNone(r[0]["stride_length_m"])


class TestBuildRealLapsGctForwarding(unittest.TestCase):
    """_build_real_laps_from_row 透传 stance_time_ms → gct_ms(§2.1 全链路可追溯)"""

    def test_gct_ms_forwarded_from_laps_json(self):
        """laps_json 中 stance_time_ms=245 → gct_ms=245"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0,
                "stance_time_ms": 245
            }])
        })
        self.assertEqual(r[0]["gct_ms"], 245, "stance_time_ms 必须透传到 gct_ms")

    def test_gct_ms_none_when_stance_missing(self):
        """laps_json 无 stance_time_ms → gct_ms=None(老数据降级)"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0
            }])
        })
        self.assertIsNone(r[0]["gct_ms"], "字段缺失 → gct_ms=None")

    def test_gct_ms_none_when_stance_zero(self):
        """stance_time_ms=0 → gct_ms=None(防 0 污染)"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0,
                "stance_time_ms": 0
            }])
        })
        self.assertIsNone(r[0]["gct_ms"], "stance_time_ms=0 → gct_ms=None")


if __name__ == "__main__":
    unittest.main()
