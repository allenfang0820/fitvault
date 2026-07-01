"""V4-5: _build_activity_canonical 下沉至 MetricsResolver 单元测试

契约:fit-arch-contrac §V4.0 防腐层 / §2.1 全链路可追溯 / §5.5 轨迹报告 v3 边界
验证:
  1. 输出必须包含 31 个字段(完整契约)
  2. 完整数据快照:所有字段正确映射
  3. 数据缺失降级:空行/partial 字段不抛异常
  4. 难度等级映射:difficulty_score → 4 类等级
  5. distance_display fallback:dist_km/distance/为 0 三种分支
  6. pace_unit 切换:跑步 /km vs 游泳 /100m
  7. weather_json 解析:str/dict/None 三种入参
  8. main.py 透传约束:不允许在 main.py 中重写业务逻辑
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver


# ══════════════════════════════════════════════════════════════════
# Test 1: 输出结构契约(31 字段完整性)
# ══════════════════════════════════════════════════════════════════

class TestActivityCanonicalOutputContract(unittest.TestCase):
    """§5.5 轨迹报告 v3 边界:输出必须包含 31 个字段"""

    REQUIRED_FIELDS = [
        "id", "sport_type", "sub_sport_type", "region", "weather",
        "dist_km", "distance_display", "duration_sec", "gain_m", "max_alt_m",
        "avg_hr", "max_hr", "calories", "avg_pace", "avg_pace_display",
        "avg_speed_mps", "avg_speed_display", "pace_unit",
        "start_time", "min_alt_m", "total_descent_m",
        "up_count", "down_count", "max_single_climb_m", "difficulty_score",
        "avg_grade_pct", "max_slope_pct", "min_slope_pct",
        "uphill_pct", "downhill_pct", "report_metrics_version",
    ]

    def test_exactly_31_fields(self):
        """输出必须恰好 31 个字段,不得多/不得少"""
        r = MetricsResolver._build_activity_canonical({})
        self.assertEqual(len(r), 31, f"输出字段数应为 31,实际 {len(r)}")

    def test_all_required_fields_present(self):
        """每个必填字段都必须存在"""
        r = MetricsResolver._build_activity_canonical({})
        for field in self.REQUIRED_FIELDS:
            self.assertIn(field, r, f"输出必须含字段 '{field}'")

    def test_no_extra_fields(self):
        """不允许出现规范外字段"""
        r = MetricsResolver._build_activity_canonical({})
        for key in r:
            self.assertIn(key, self.REQUIRED_FIELDS,
                          f"输出中出现未登记字段 '{key}'")


# ══════════════════════════════════════════════════════════════════
# Test 2: 完整数据快照(所有字段正确映射)
# ══════════════════════════════════════════════════════════════════

class TestCompleteDataSnapshot(unittest.TestCase):
    """完整 DB row 输入:所有字段正确映射"""

    def setUp(self):
        self.full_row = {
            "id": 42,
            "sport_type": "running",
            "sub_sport_type": "trail",
            "region": "西湖群山",
            "weather_json": '{"temp": 18, "condition": "多云"}',
            "dist_km": 12.5,
            "distance": 12500.0,
            "duration_sec": 4200,
            "duration": 4200,
            "gain_m": 350.0,
            "max_alt_m": 850.0,
            "avg_hr": 155,
            "max_hr": 188,
            "calories": 890,
            "avg_pace": 336.0,
            "start_time": "2026-05-20 07:30:00",
            "min_alt_m": 120.0,
            "total_descent_m": 340.0,
            "up_count": 8,
            "down_count": 7,
            "max_single_climb_m": 80.0,
            "difficulty_score": 35,
            "avg_grade_pct": 2.8,
            "max_slope_pct": 15.2,
            "min_slope_pct": -12.5,
            "uphill_pct": 42.0,
            "downhill_pct": 38.0,
            "report_metrics_version": 3,
        }
        self.r = MetricsResolver._build_activity_canonical(self.full_row)

    def test_id_correct(self):
        self.assertEqual(self.r["id"], 42)

    def test_sport_type_correct(self):
        self.assertEqual(self.r["sport_type"], "running")

    def test_sub_sport_type_correct(self):
        self.assertEqual(self.r["sub_sport_type"], "trail")

    def test_region_correct(self):
        self.assertEqual(self.r["region"], "西湖群山")

    def test_weather_parsed(self):
        self.assertEqual(self.r["weather"], {"temp": 18, "condition": "多云"})

    def test_dist_km_correct(self):
        self.assertAlmostEqual(self.r["dist_km"], 12.5, places=2)

    def test_duration_sec_correct(self):
        self.assertEqual(self.r["duration_sec"], 4200)

    def test_gain_m_correct(self):
        self.assertAlmostEqual(self.r["gain_m"], 350.0, places=1)

    def test_max_alt_m_correct(self):
        self.assertAlmostEqual(self.r["max_alt_m"], 850.0, places=1)

    def test_min_alt_m_correct(self):
        self.assertAlmostEqual(self.r["min_alt_m"], 120.0, places=1)

    def test_total_descent_m_correct(self):
        self.assertAlmostEqual(self.r["total_descent_m"], 340.0, places=1)

    def test_avg_hr_correct(self):
        self.assertEqual(self.r["avg_hr"], 155)

    def test_max_hr_correct(self):
        self.assertEqual(self.r["max_hr"], 188)

    def test_calories_correct(self):
        self.assertEqual(self.r["calories"], 890)

    def test_avg_pace_correct(self):
        self.assertAlmostEqual(self.r["avg_pace"], 336.0, places=1)

    def test_up_count_correct(self):
        self.assertEqual(self.r["up_count"], 8)

    def test_down_count_correct(self):
        self.assertEqual(self.r["down_count"], 7)

    def test_max_single_climb_m_correct(self):
        self.assertAlmostEqual(self.r["max_single_climb_m"], 80.0, places=1)

    def test_difficulty_score_correct(self):
        self.assertEqual(self.r["difficulty_score"], 35)

    def test_avg_grade_pct_correct(self):
        self.assertAlmostEqual(self.r["avg_grade_pct"], 2.8, places=1)

    def test_max_slope_pct_correct(self):
        self.assertAlmostEqual(self.r["max_slope_pct"], 15.2, places=1)

    def test_min_slope_pct_correct(self):
        self.assertAlmostEqual(self.r["min_slope_pct"], -12.5, places=1)

    def test_uphill_pct_correct(self):
        self.assertAlmostEqual(self.r["uphill_pct"], 42.0, places=1)

    def test_downhill_pct_correct(self):
        self.assertAlmostEqual(self.r["downhill_pct"], 38.0, places=1)

    def test_report_metrics_version_correct(self):
        self.assertEqual(self.r["report_metrics_version"], 3)

    def test_start_time_correct(self):
        self.assertEqual(self.r["start_time"], "2026-05-20 07:30:00")


# ══════════════════════════════════════════════════════════════════
# Test 3: 数据缺失降级(空行/partial 字段不抛异常)
# ══════════════════════════════════════════════════════════════════

class TestDegradedInput(unittest.TestCase):
    """数据缺失降级:空行/partial 字段不抛异常,安全默认值"""

    def test_empty_dict_no_exception(self):
        """空 dict 不抛异常,返回全默认值"""
        r = MetricsResolver._build_activity_canonical({})
        self.assertIsInstance(r, dict)
        self.assertEqual(len(r), 31)

    def test_empty_row_defaults(self):
        """空行默认值:数值为 0/0.0,字符串为 unknown/空"""
        r = MetricsResolver._build_activity_canonical({})
        self.assertEqual(r["id"], 0)
        self.assertEqual(r["sport_type"], "unknown")
        self.assertEqual(r["sub_sport_type"], "unknown")
        self.assertEqual(r["dist_km"], 0.0)
        self.assertEqual(r["gain_m"], 0.0)
        self.assertEqual(r["max_alt_m"], 0.0)
        self.assertEqual(r["avg_hr"], None)
        self.assertEqual(r["max_hr"], None)
        self.assertEqual(r["calories"], None)
        self.assertEqual(r["avg_pace"], None)
        self.assertEqual(r["duration_sec"], 0)
        self.assertEqual(r["difficulty_score"], 0)
        self.assertIsNone(r["weather"])

    def test_none_values_safe(self):
        """所有字段为 None 不抛异常"""
        none_row = {k: None for k in [
            "id", "sport_type", "sub_sport_type", "region", "weather_json",
            "dist_km", "distance", "duration_sec", "duration", "gain_m",
            "max_alt_m", "avg_hr", "max_hr", "calories", "avg_pace",
            "start_time", "min_alt_m", "total_descent_m",
            "up_count", "down_count", "max_single_climb_m",
            "difficulty_score", "avg_grade_pct", "max_slope_pct",
            "min_slope_pct", "uphill_pct", "downhill_pct",
            "report_metrics_version",
        ]}
        r = MetricsResolver._build_activity_canonical(none_row)
        self.assertIsInstance(r, dict)
        self.assertEqual(len(r), 31)

    def test_weather_json_str_invalid(self):
        """无效 JSON 字符串 weather 安全降级为 None"""
        r = MetricsResolver._build_activity_canonical({
            "weather_json": "not-valid-json!!!",
        })
        self.assertIsNone(r["weather"])

    def test_weather_json_dict_direct(self):
        """weather_json 已是 dict,直接透传"""
        r = MetricsResolver._build_activity_canonical({
            "weather_json": {"temp": 25},
        })
        self.assertEqual(r["weather"], {"temp": 25})

    def test_weather_json_none(self):
        """weather_json 为 None,weather 返回 None"""
        r = MetricsResolver._build_activity_canonical({"weather_json": None})
        self.assertIsNone(r["weather"])

    def test_partial_row_safe(self):
        """只给部分字段,其余字段安全降级"""
        r = MetricsResolver._build_activity_canonical({
            "sport_type": "cycling",
            "dist_km": 25.0,
        })
        self.assertEqual(r["sport_type"], "cycling")
        self.assertAlmostEqual(r["dist_km"], 25.0, places=1)
        self.assertEqual(r["gain_m"], 0.0)
        self.assertEqual(r["avg_hr"], None)

    def test_region_none_defaults_to_empty(self):
        """region 为 None → 空字符串(不抛 None 给前端)"""
        r = MetricsResolver._build_activity_canonical({"region": None})
        self.assertEqual(r["region"], "")

    def test_start_time_none_defaults_to_empty(self):
        """start_time 为 None → 空字符串"""
        r = MetricsResolver._build_activity_canonical({"start_time": None})
        self.assertEqual(r["start_time"], "")


# ══════════════════════════════════════════════════════════════════
# Test 4: distance_display fallback(三种分支)
# ══════════════════════════════════════════════════════════════════

class TestDistanceDisplay(unittest.TestCase):
    """distance_display 三种 fallback 分支"""

    def test_dist_km_normal(self):
        """dist_km >= 0.1 → X.XXkm 格式"""
        r = MetricsResolver._build_activity_canonical({"dist_km": 12.5})
        self.assertEqual(r["distance_display"], "12.50km")

    def test_dist_km_small_shows_meters(self):
        """dist_km < 0.1 → 转米显示"""
        r = MetricsResolver._build_activity_canonical({"dist_km": 0.08})
        self.assertEqual(r["distance_display"], "80m")

    def test_dist_km_zero_fallback_to_distance(self):
        """dist_km=0 但有 distance(米),从 distance 反算 dist_km 并显示"""
        r = MetricsResolver._build_activity_canonical({
            "dist_km": 0.0,
            "distance": 8300.0,
        })
        self.assertAlmostEqual(r["dist_km"], 8.3, places=2)
        self.assertEqual(r["distance_display"], "8.30km")

    def test_dist_km_zero_distance_zero(self):
        """dist_km=0 且 distance=0 → '-- km'"""
        r = MetricsResolver._build_activity_canonical({
            "dist_km": 0.0,
            "distance": 0.0,
        })
        self.assertEqual(r["dist_km"], 0.0)
        self.assertEqual(r["distance_display"], "-- km")

    def test_dist_km_zero_no_distance_key(self):
        """dist_km=0 且无 distance 键 → '-- km'"""
        r = MetricsResolver._build_activity_canonical({"dist_km": 0.0})
        self.assertEqual(r["distance_display"], "-- km")

    def test_dist_km_rounding_2dp(self):
        """distance 反算保留 2 位小数"""
        r = MetricsResolver._build_activity_canonical({
            "dist_km": 0.0,
            "distance": 1234.0,
        })
        self.assertAlmostEqual(r["dist_km"], 1.23, places=2)
        self.assertEqual(r["distance_display"], "1.23km")


# ══════════════════════════════════════════════════════════════════
# Test 5: pace_unit 切换(跑步 vs 游泳)
# ══════════════════════════════════════════════════════════════════

class TestPaceUnitSwitching(unittest.TestCase):
    """pace_unit 根据 sub_sport_type 切换"""

    def _make_row(self, sport_type="running", sub_sport_type="generic",
                  avg_pace=336.0):
        return {
            "sport_type": sport_type,
            "sub_sport_type": sub_sport_type,
            "dist_km": 10.0,
            "avg_pace": avg_pace,
            "duration_sec": 3600,
        }

    def test_running_pace_unit_km(self):
        """跑步(非游泳) pace_unit = '/km'"""
        r = MetricsResolver._build_activity_canonical(
            self._make_row("running", "generic", 300.0))
        self.assertEqual(r["pace_unit"], "/km")

    def test_cycling_pace_unit_km(self):
        """骑行 pace_unit = '/km'(非游泳)"""
        r = MetricsResolver._build_activity_canonical(
            self._make_row("cycling", "road", 180.0))
        self.assertEqual(r["pace_unit"], "/km")

    def test_lap_swimming_pace_unit_100m(self):
        """泳池游泳 sub_sport='lap_swimming' → pace_unit='/100m'"""
        r = MetricsResolver._build_activity_canonical(
            self._make_row("swimming", "lap_swimming", 150.0))
        self.assertEqual(r["pace_unit"], "/100m")

    def test_open_water_pace_unit_100m(self):
        """开放水域 sub_sport='open_water' → pace_unit='/100m'"""
        r = MetricsResolver._build_activity_canonical(
            self._make_row("swimming", "open_water", 120.0))
        self.assertEqual(r["pace_unit"], "/100m")

    def test_swimming_unknown_sub_sport(self):
        """游泳但 sub_sport 不识别 → 降级为 '/km'"""
        r = MetricsResolver._build_activity_canonical(
            self._make_row("swimming", "unknown_sub", 150.0))
        self.assertEqual(r["pace_unit"], "/km")

    def test_sub_sport_type_none(self):
        """sub_sport_type 为 None → pace_unit='/km'"""
        row = self._make_row("swimming", None, 150.0)
        row["sub_sport_type"] = None
        r = MetricsResolver._build_activity_canonical(row)
        self.assertEqual(r["pace_unit"], "/km")


# ══════════════════════════════════════════════════════════════════
# Test 6: avg_pace_display 格式(含 pace 为 0/None)
# ══════════════════════════════════════════════════════════════════

class TestAvgPaceDisplay(unittest.TestCase):
    """avg_pace_display 格式化"""

    def test_normal_pace_display(self):
        """avg_pace=336s → 5'36''/km"""
        r = MetricsResolver._build_activity_canonical({
            "sub_sport_type": "generic",
            "avg_pace": 336.0,
            "dist_km": 10.0,
        })
        self.assertEqual(r["avg_pace_display"], "5'36''/km")

    def test_pace_zero_no_display(self):
        """avg_pace=0 → '-- /km'"""
        r = MetricsResolver._build_activity_canonical({
            "sub_sport_type": "generic",
            "avg_pace": 0.0,
            "dist_km": 10.0,
        })
        self.assertEqual(r["avg_pace_display"], "-- /km")

    def test_pace_none_no_display(self):
        """avg_pace=None → '-- /km'"""
        r = MetricsResolver._build_activity_canonical({
            "sub_sport_type": "generic",
            "avg_pace": None,
            "dist_km": 10.0,
        })
        self.assertEqual(r["avg_pace_display"], "-- /km")

    def test_pace_with_swimming_unit(self):
        """avg_pace=90s 游泳 → 1'30''/100m"""
        r = MetricsResolver._build_activity_canonical({
            "sport_type": "swimming",
            "sub_sport_type": "lap_swimming",
            "avg_pace": 90.0,
            "dist_km": 1.0,
        })
        self.assertEqual(r["avg_pace_display"], "1'30''/100m")
        self.assertEqual(r["pace_unit"], "/100m")

    def test_pace_exactly_60s(self):
        """avg_pace=60s → 1'00''/km"""
        r = MetricsResolver._build_activity_canonical({
            "sub_sport_type": "generic",
            "avg_pace": 60.0,
            "dist_km": 5.0,
        })
        self.assertEqual(r["avg_pace_display"], "1'00''/km")

    def test_pace_seconds_padding(self):
        """秒数始终补零到 2 位"""
        r = MetricsResolver._build_activity_canonical({
            "sub_sport_type": "generic",
            "avg_pace": 305.0,  # 5'05''
            "dist_km": 10.0,
        })
        self.assertEqual(r["avg_pace_display"], "5'05''/km")


class TestAvgSpeedDisplay(unittest.TestCase):
    """avg_speed_display 由后端 canonical 生成,前端只消费"""

    def test_avg_speed_display_from_distance_and_duration(self):
        r = MetricsResolver._build_activity_canonical({
            "dist_km": 140.41,
            "duration_sec": 16627,
        })
        self.assertAlmostEqual(r["avg_speed_mps"], 8.445, places=3)
        self.assertEqual(r["avg_speed_display"], "30.4 km/h")

    def test_avg_speed_missing_without_distance_or_duration(self):
        r = MetricsResolver._build_activity_canonical({
            "dist_km": 0,
            "duration_sec": 0,
        })
        self.assertIsNone(r["avg_speed_mps"])
        self.assertEqual(r["avg_speed_display"], "--")


# ══════════════════════════════════════════════════════════════════
# Test 7: 难度等级映射(difficulty_score → 4 类映射)
# ══════════════════════════════════════════════════════════════════

class TestDifficultyScoreMapping(unittest.TestCase):
    """difficulty_score 字段直接透传(不做等级计算,由 MTDI 负责)"""

    def test_difficulty_score_in_range_0_100(self):
        """difficulty_score 应直接映射(0-100 范围)"""
        for score in (0, 15, 35, 60, 85, 100):
            r = MetricsResolver._build_activity_canonical({"difficulty_score": score})
            self.assertEqual(r["difficulty_score"], score,
                             f"difficulty_score={score} 应直接透传")

    def test_difficulty_score_missing_defaults_0(self):
        """difficulty_score 缺失 → 0"""
        r = MetricsResolver._build_activity_canonical({})
        self.assertEqual(r["difficulty_score"], 0)

    def test_difficulty_score_none_defaults_0(self):
        """difficulty_score=None → 0"""
        r = MetricsResolver._build_activity_canonical({"difficulty_score": None})
        self.assertEqual(r["difficulty_score"], 0)


# ══════════════════════════════════════════════════════════════════
# Test 8: 坡度字段透传(_safe_float)
# ══════════════════════════════════════════════════════════════════

class TestSlopeFields(unittest.TestCase):
    """avg_grade_pct / max_slope_pct / min_slope_pct / uphill_pct / downhill_pct"""

    def test_slope_fields_normal(self):
        r = MetricsResolver._build_activity_canonical({
            "avg_grade_pct": 3.5,
            "max_slope_pct": 18.0,
            "min_slope_pct": -10.0,
            "uphill_pct": 45.0,
            "downhill_pct": 35.0,
        })
        self.assertEqual(r["avg_grade_pct"], 3.5)
        self.assertEqual(r["max_slope_pct"], 18.0)
        self.assertEqual(r["min_slope_pct"], -10.0)
        self.assertEqual(r["uphill_pct"], 45.0)
        self.assertEqual(r["downhill_pct"], 35.0)

    def test_slope_fields_none_defaults_none(self):
        """坡度字段为 None → None(_safe_float 保留 None 语义)"""
        r = MetricsResolver._build_activity_canonical({
            "avg_grade_pct": None,
            "max_slope_pct": None,
            "min_slope_pct": None,
            "uphill_pct": None,
            "downhill_pct": None,
        })
        self.assertIsNone(r["avg_grade_pct"])
        self.assertIsNone(r["max_slope_pct"])
        self.assertIsNone(r["min_slope_pct"])
        self.assertIsNone(r["uphill_pct"])
        self.assertIsNone(r["downhill_pct"])

    def test_slope_fields_missing_defaults_none(self):
        """坡度字段缺失 → None(_safe_float 对缺失键返回 None)"""
        r = MetricsResolver._build_activity_canonical({})
        self.assertIsNone(r["avg_grade_pct"])
        self.assertIsNone(r["max_slope_pct"])
        self.assertIsNone(r["min_slope_pct"])
        self.assertIsNone(r["uphill_pct"])
        self.assertIsNone(r["downhill_pct"])

    def test_slope_negative_ok(self):
        """min_slope_pct 可以为负(下坡)"""
        r = MetricsResolver._build_activity_canonical({"min_slope_pct": -25.0})
        self.assertEqual(r["min_slope_pct"], -25.0)


# ══════════════════════════════════════════════════════════════════
# Test 9: HR/calories None → None 保留(区分 0 与 无数据)
# ══════════════════════════════════════════════════════════════════

class TestHrCaloriesNullPreservation(unittest.TestCase):
    """avg_hr/max_hr/calories: 0→None 保留语义(区分 0 与无数据)"""

    def test_hr_zero_becomes_none(self):
        """avg_hr=0 → None(表示无心率数据,区别于真实值 0)"""
        r = MetricsResolver._build_activity_canonical({"avg_hr": 0})
        self.assertIsNone(r["avg_hr"])

    def test_max_hr_zero_becomes_none(self):
        r = MetricsResolver._build_activity_canonical({"max_hr": 0})
        self.assertIsNone(r["max_hr"])

    def test_calories_zero_becomes_none(self):
        r = MetricsResolver._build_activity_canonical({"calories": 0})
        self.assertIsNone(r["calories"])

    def test_hr_positive_preserved(self):
        """正数 HR 正常保留"""
        r = MetricsResolver._build_activity_canonical({"avg_hr": 145, "max_hr": 178})
        self.assertEqual(r["avg_hr"], 145)
        self.assertEqual(r["max_hr"], 178)

    def test_calories_positive_preserved(self):
        r = MetricsResolver._build_activity_canonical({"calories": 520})
        self.assertEqual(r["calories"], 520)


# ══════════════════════════════════════════════════════════════════
# Test 10: main.py 透传约束(不允许 main.py 重写业务逻辑)
# ══════════════════════════════════════════════════════════════════

class TestMainPyPassthroughConstraint(unittest.TestCase):
    """§V4.0 防腐层:main.py 只做透传,不含业务逻辑"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_source = f.read()
        cls.main_tree = ast.parse(cls.main_source)

    def test_main_py_calls_resolver_build_activity_canonical(self):
        """main.py 必须调用 MetricsResolver._build_activity_canonical"""
        self.assertIn("MetricsResolver._build_activity_canonical",
                      self.main_source,
                      "main.py 必须使用 MetricsResolver._build_activity_canonical")

    def test_main_py_no_redefinition(self):
        """main.py 不允许重新定义 _build_activity_canonical 函数"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "_build_activity_canonical":
                    self.fail(
                        "main.py 中不允许重新定义 _build_activity_canonical,"
                        "必须使用 MetricsResolver._build_activity_canonical"
                    )

    def test_main_py_no_safe_int_zero_redefinition(self):
        """main.py 不允许重新定义 _safe_int_zero(已下沉到 Resolver)"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "_safe_int_zero":
                    self.fail("main.py 中不允许重新定义 _safe_int_zero")

    def test_main_py_no_safe_float_zero_redefinition(self):
        """main.py 不允许重新定义 _safe_float_zero"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "_safe_float_zero":
                    self.fail("main.py 中不允许重新定义 _safe_float_zero")

    def test_load_activity_track_uses_resolver(self):
        """load_activity_track 中只调用 Resolver,无额外逻辑"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "load_activity_track":
                # 在函数体内查找 _build_activity_canonical 调用
                found = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if (isinstance(child.func, ast.Attribute) and
                                child.func.attr == "_build_activity_canonical" and
                                isinstance(child.func.value, ast.Name) and
                                child.func.value.id == "MetricsResolver"):
                            found = True
                            break
                if not found:
                    self.fail(
                        "load_activity_track 必须调用 "
                        "MetricsResolver._build_activity_canonical"
                    )


if __name__ == "__main__":
    unittest.main()
