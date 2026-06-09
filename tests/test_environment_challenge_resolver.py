"""
V_ENV.1.1 Environment Challenge 工具函数单元测试

依据:调研报告 §3.1(climb_density) / §3.2(altitude) / §3.3(heat)
契约:fit-arch-contrac §2.1 字段可追溯 / §五 AI 边界 / §六 审计字段隔离

测试范围:
  - calculate_climb_density: 正常值 / 零值 / 负值 / None 降级
  - classify_altitude_stress: 5 档临界 / None / 负数降级
  - classify_heat_stress: 4 档临界 / humidity 缺失单维度降级 / 双 None 降级
"""

from __future__ import annotations
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import (
    calculate_climb_density,
    classify_altitude_stress,
    classify_heat_stress,
    # V_ENV.1.2:语义路由
    get_environment_challenge_semantic,
    RUNNING_SEMANTICS,
    TRAIL_RUNNING_SEMANTICS,
    HIKING_SEMANTICS,
    CYCLING_SEMANTICS,
    MOUNTAIN_BIKING_SEMANTICS,
    COLD_SEMANTICS,
    _ENV_CHALLENGE_SPORT_MAP,
    _COLD_SPORT_SET,
)


class TestCalculateClimbDensity(unittest.TestCase):
    """§3.1 climb_density = total_ascent(m) / distance(km)"""

    def test_normal_calculation(self):
        """1000m / 10km = 100 m/km"""
        self.assertEqual(calculate_climb_density(1000, 10.0), 100.0)

    def test_fractional_result(self):
        """305m / 10km = 30.5 m/km"""
        self.assertAlmostEqual(calculate_climb_density(305, 10.0), 30.5)

    def test_zero_ascent(self):
        """0m / 10km = 0.0"""
        self.assertEqual(calculate_climb_density(0, 10.0), 0.0)

    def test_negative_ascent_treated_as_zero(self):
        """负爬升视为 0"""
        self.assertEqual(calculate_climb_density(-50, 10.0), 0.0)

    def test_zero_distance_degrades_to_zero(self):
        """distance=0 → 降级 0.0,不抛除零异常"""
        self.assertEqual(calculate_climb_density(100, 0.0), 0.0)

    def test_none_ascent_degrades(self):
        """total_ascent=None → 0.0"""
        self.assertEqual(calculate_climb_density(None, 10.0), 0.0)

    def test_none_distance_degrades(self):
        """distance=None → 0.0"""
        self.assertEqual(calculate_climb_density(100, None), 0.0)

    def test_both_none_degrades(self):
        """双 None → 0.0"""
        self.assertEqual(calculate_climb_density(None, None), 0.0)


class TestClassifyAltitudeStress(unittest.TestCase):
    """§3.2 海拔压力 5 档分级"""

    def test_level_0_below_1500(self):
        """< 1500m → 0"""
        self.assertEqual(classify_altitude_stress(0), 0)
        self.assertEqual(classify_altitude_stress(1499), 0)

    def test_level_1_1500_to_2500(self):
        """[1500, 2500) → 1"""
        self.assertEqual(classify_altitude_stress(1500), 1)
        self.assertEqual(classify_altitude_stress(2499), 1)

    def test_level_2_2500_to_3500(self):
        """[2500, 3500) → 2"""
        self.assertEqual(classify_altitude_stress(2500), 2)
        self.assertEqual(classify_altitude_stress(3499), 2)

    def test_level_3_3500_to_4500(self):
        """[3500, 4500) → 3"""
        self.assertEqual(classify_altitude_stress(3500), 3)
        self.assertEqual(classify_altitude_stress(4499), 3)

    def test_level_4_above_4500(self):
        """>= 4500 → 4"""
        self.assertEqual(classify_altitude_stress(4500), 4)
        self.assertEqual(classify_altitude_stress(8848), 4)

    def test_none_degrades_to_0(self):
        """None → 0"""
        self.assertEqual(classify_altitude_stress(None), 0)

    def test_negative_degrades_to_0(self):
        """负数 → 0"""
        self.assertEqual(classify_altitude_stress(-100), 0)


class TestClassifyHeatStress(unittest.TestCase):
    """§3.3 热环境压力 4 档(temp_c × humidity 粗分)"""

    # ── 正常路径(product = temp × humidity, humidity 0~1) ──

    def test_level_0_product_below_500(self):
        """product < 500 → 0"""
        self.assertEqual(classify_heat_stress(20.0, 0.5), 0)   # 10

    def test_level_1_product_500_to_1200(self):
        """[500, 1200) → 1"""
        self.assertEqual(classify_heat_stress(600, 1.0), 1)    # 600

    def test_level_2_product_1200_to_2100(self):
        """[1200, 2100) → 2"""
        self.assertEqual(classify_heat_stress(2000, 1.0), 2)   # 2000

    def test_level_3_product_above_2100(self):
        """>= 2100 → 3"""
        self.assertEqual(classify_heat_stress(3000, 1.0), 3)   # 3000

    def test_boundary_product_equals_500(self):
        """product == 500 → 归 Level 1(闭区间 [500,1200))"""
        self.assertEqual(classify_heat_stress(50.0, 10.0), 1)  # 500

    def test_boundary_product_equals_1200(self):
        """product == 1200 → 归 Level 2"""
        self.assertEqual(classify_heat_stress(60.0, 20.0), 2)  # 1200

    def test_boundary_product_equals_2100(self):
        """product == 2100 → 归 Level 3"""
        self.assertEqual(classify_heat_stress(70.0, 30.0), 3)  # 2100

    def test_zero_humidity(self):
        """humidity=0 → product=0 → Level 0"""
        self.assertEqual(classify_heat_stress(50.0, 0.0), 0)

    # ── 降级路径 ──

    def test_temp_none_returns_0(self):
        """temp=None → 0(温度缺失无法判定)"""
        self.assertEqual(classify_heat_stress(None, 0.6), 0)

    def test_both_none_returns_0(self):
        """双 None → 0"""
        self.assertEqual(classify_heat_stress(None, None), 0)

    def test_humidity_none_uses_temp_only_below_25(self):
        """humidity=None, temp<25 → 0"""
        self.assertEqual(classify_heat_stress(20.0, None), 0)

    def test_humidity_none_uses_temp_only_25_to_30(self):
        """humidity=None, 25≤temp<30 → 1"""
        self.assertEqual(classify_heat_stress(28.0, None), 1)

    def test_humidity_none_uses_temp_only_30_to_35(self):
        """humidity=None, 30≤temp<35 → 2"""
        self.assertEqual(classify_heat_stress(32.0, None), 2)

    def test_humidity_none_uses_temp_only_above_35(self):
        """humidity=None, temp≥35 → 3"""
        self.assertEqual(classify_heat_stress(35.0, None), 3)
        self.assertEqual(classify_heat_stress(40.0, None), 3)


class TestSemanticsIntegrity(unittest.TestCase):
    """§4.2~§4.7 语义常量完整性:每模块 label 非空且不重复"""

    def _assert_labels_unique(self, table, table_name):
        """辅助:验证 table 中每个 module 的 label 列表无重复且无空串。"""
        for module, items in table.items():
            for i, item in enumerate(items):
                self.assertTrue(item.get("label") and item["label"].strip(),
                    f"V_ENV FAIL: {table_name}[{module}][{i}] label 为空串")
                self.assertTrue(item.get("explanation") and item["explanation"].strip(),
                    f"V_ENV FAIL: {table_name}[{module}][{i}] explanation 为空串")
            labels = [item["label"] for item in items]
            self.assertEqual(len(labels), len(set(labels)),
                f"V_ENV FAIL: {table_name}[{module}] 有重复 label: {labels}")

    def test_running_labels_unique(self):
        self._assert_labels_unique(RUNNING_SEMANTICS, "RUNNING_SEMANTICS")

    def test_trail_running_labels_unique(self):
        self._assert_labels_unique(TRAIL_RUNNING_SEMANTICS, "TRAIL_RUNNING_SEMANTICS")

    def test_hiking_labels_unique(self):
        self._assert_labels_unique(HIKING_SEMANTICS, "HIKING_SEMANTICS")

    def test_cycling_labels_unique(self):
        self._assert_labels_unique(CYCLING_SEMANTICS, "CYCLING_SEMANTICS")

    def test_mountain_biking_labels_unique(self):
        self._assert_labels_unique(MOUNTAIN_BIKING_SEMANTICS, "MOUNTAIN_BIKING_SEMANTICS")

    def test_cold_labels_unique(self):
        """低温 5 档无重复"""
        self.assertEqual(len(COLD_SEMANTICS), len(set(i["label"] for i in COLD_SEMANTICS)),
            f"V_ENV FAIL: COLD_SEMANTICS 有重复: {COLD_SEMANTICS}")

    def test_vertical_altitude_terrain_5_levels(self):
        """5 档模块(vertical/altitude/terrain)每行 5 条"""
        for name, table in [("running", RUNNING_SEMANTICS), ("hiking", HIKING_SEMANTICS)]:
            for module in ["vertical", "altitude", "terrain"]:
                self.assertEqual(len(table[module]), 5,
                    f"V_ENV FAIL: {name}[{module}] 应 5 档,实际 {len(table[module])}")

    def test_heat_4_levels(self):
        """4 档模块(heat)每行 4 条"""
        for name, table in [("running", RUNNING_SEMANTICS), ("cycling", CYCLING_SEMANTICS)]:
            self.assertEqual(len(table["heat"]), 4,
                f"V_ENV FAIL: {name}[heat] 应 4 档,实际 {len(table['heat'])}")


class TestSportMapCoverage(unittest.TestCase):
    """§4 路由表 8 键 + cold_set 覆盖"""

    def test_sport_map_has_8_keys(self):
        self.assertEqual(len(_ENV_CHALLENGE_SPORT_MAP), 8,
            f"V_ENV FAIL: _ENV_CHALLENGE_SPORT_MAP 应 8 键,实际 {len(_ENV_CHALLENGE_SPORT_MAP)}")

    def test_required_sports_present(self):
        required = ["running", "trail_running", "hiking", "cycling",
                    "road_cycling", "mountain_biking", "skiing", "mountaineering"]
        for sport in required:
            self.assertIn(sport, _ENV_CHALLENGE_SPORT_MAP,
                f"V_ENV FAIL: _ENV_CHALLENGE_SPORT_MAP 缺少 {sport}")

    def test_cold_sport_set(self):
        self.assertEqual(_COLD_SPORT_SET, {"skiing", "mountaineering"},
            f"V_ENV FAIL: _COLD_SPORT_SET = {_COLD_SPORT_SET}")

    def test_road_cycling_aliases_cycling(self):
        self.assertIs(_ENV_CHALLENGE_SPORT_MAP["road_cycling"],
                      _ENV_CHALLENGE_SPORT_MAP["cycling"],
            "V_ENV FAIL: road_cycling 应别名到 cycling")

    def test_skiing_maps_to_trail_running(self):
        self.assertIs(_ENV_CHALLENGE_SPORT_MAP["skiing"],
                      TRAIL_RUNNING_SEMANTICS,
            "V_ENV FAIL: skiing 应指向 TRAIL_RUNNING_SEMANTICS")

    def test_mountaineering_maps_to_hiking(self):
        self.assertIs(_ENV_CHALLENGE_SPORT_MAP["mountaineering"],
                      HIKING_SEMANTICS,
            "V_ENV FAIL: mountaineering 应指向 HIKING_SEMANTICS")


class TestGetEnvironmentChallengeSemantic(unittest.TestCase):
    """§4.2~§4.7 + §4.7.3 查询函数(含低温替换)"""

    def test_running_vertical_level_0(self):
        r = get_environment_challenge_semantic("running", "vertical", 0)
        self.assertEqual(r["label"], "平路路线")
        self.assertIn("爬升", r["explanation"])

    def test_running_vertical_level_4(self):
        r = get_environment_challenge_semantic("running", "vertical", 4)
        self.assertEqual(r["label"], "极限爬升挑战")
        self.assertIn("爬升", r["explanation"])

    def test_trail_running_altitude_level_2(self):
        r = get_environment_challenge_semantic("trail_running", "altitude", 2)
        self.assertEqual(r["label"], "中高海拔越野")
        self.assertIn("山地", r["explanation"])

    def test_hiking_heat_level_3(self):
        r = get_environment_challenge_semantic("hiking", "heat", 3)
        self.assertEqual(r["label"], "高温登山挑战")
        self.assertIn("高温", r["explanation"])

    def test_cycling_terrain_level_3(self):
        r = get_environment_challenge_semantic("cycling", "terrain", 3)
        self.assertEqual(r["label"], "高技术下坡路线")
        self.assertIn("技术", r["explanation"])

    def test_mountain_biking_vertical_level_4(self):
        r = get_environment_challenge_semantic("mountain_biking", "vertical", 4)
        self.assertEqual(r["label"], "极限山地骑行挑战")
        self.assertIn("爬坡", r["explanation"])

    # ── 低温替换(skiing/mountaineering 的 heat 模块) ──

    def test_skiing_heat_level_0_cold(self):
        """skiing + heat + level 0 → 低温语义第 0 档"""
        r = get_environment_challenge_semantic("skiing", "heat", 0)
        self.assertEqual(r["label"], "温度舒适")
        self.assertIn("冷应激", r["explanation"])

    def test_skiing_heat_level_2_cold(self):
        r = get_environment_challenge_semantic("skiing", "heat", 2)
        self.assertEqual(r["label"], "低温环境")
        self.assertIn("防寒", r["explanation"])

    def test_skiing_heat_level_4_cold(self):
        r = get_environment_challenge_semantic("skiing", "heat", 4)
        self.assertEqual(r["label"], "极寒挑战")
        self.assertIn("寒", r["explanation"])

    def test_mountaineering_heat_level_3_cold(self):
        r = get_environment_challenge_semantic("mountaineering", "heat", 3)
        self.assertEqual(r["label"], "严寒环境")
        self.assertIn("冻伤", r["explanation"])

    # ── skiing/mountaineering 非 heat 模块走兜底表 ──

    def test_skiing_vertical_uses_trail_running(self):
        r = get_environment_challenge_semantic("skiing", "vertical", 0)
        self.assertEqual(r["label"], "轻度山地路线")
        self.assertIn("山地", r["explanation"])

    def test_mountaineering_vertical_uses_hiking(self):
        r = get_environment_challenge_semantic("mountaineering", "vertical", 4)
        self.assertEqual(r["label"], "极限长爬升路线")
        self.assertIn("爬升", r["explanation"])

    # ── fallback(未匹配运动 → running) ──

    def test_treadmill_running_fallback(self):
        r = get_environment_challenge_semantic("treadmill_running", "vertical", 2)
        self.assertEqual(r["label"], "持续爬升路线")
        self.assertIn("爬升", r["explanation"])

    def test_swimming_fallback(self):
        r = get_environment_challenge_semantic("swimming", "altitude", 0)
        self.assertEqual(r["label"], "低海拔环境")
        self.assertIn("海拔", r["explanation"])

    # ── 降级(level 越界/None/非数值) ──

    def test_level_none_returns_level_0(self):
        r = get_environment_challenge_semantic("running", "vertical", None)
        self.assertEqual(r["label"], "平路路线")

    def test_level_99_returns_level_0(self):
        r = get_environment_challenge_semantic("running", "vertical", 99)
        self.assertEqual(r["label"], "平路路线")

    def test_level_negative_returns_level_0(self):
        r = get_environment_challenge_semantic("running", "vertical", -1)
        self.assertEqual(r["label"], "平路路线")

    def test_level_string_returns_level_0(self):
        r = get_environment_challenge_semantic("running", "vertical", "abc")
        self.assertEqual(r["label"], "平路路线")

    # ── 模块名拼错 ──

    def test_wrong_module_returns_dash(self):
        r = get_environment_challenge_semantic("running", "wrong_module", 2)
        self.assertEqual(r, {"label": "--", "explanation": "--"})

    # ── sport_type 大小写 + 空格 ──

    def test_sport_case_insensitive(self):
        r = get_environment_challenge_semantic("RUNNING", "vertical", 0)
        self.assertEqual(r["label"], "平路路线")

    def test_sport_with_spaces(self):
        r = get_environment_challenge_semantic("  Running  ", "vertical", 0)
        self.assertEqual(r["label"], "平路路线")

    def test_sport_none_fallback(self):
        r = get_environment_challenge_semantic(None, "vertical", 0)
        self.assertEqual(r["label"], "平路路线")

    def test_sport_empty_fallback(self):
        r = get_environment_challenge_semantic("", "vertical", 0)
        self.assertEqual(r["label"], "平路路线")


class TestExplanationIntegrity(unittest.TestCase):
    """V_ENV.2.6:explanation 字段非空且语义合理"""

    def test_running_vertical_explanations(self):
        from metrics_resolver import get_environment_challenge_semantic
        for level in range(5):
            r = get_environment_challenge_semantic("running", "vertical", level)
            self.assertTrue(r["explanation"], f"vertical level {level} explanation 空")
            self.assertNotEqual(r["explanation"], "--")

    def test_skiing_heat_cold_explanations(self):
        from metrics_resolver import get_environment_challenge_semantic
        for level in range(5):
            r = get_environment_challenge_semantic("skiing", "heat", level)
            self.assertTrue(r["explanation"], f"skiing heat level {level} explanation 空")

    def test_all_modules_have_explanation(self):
        from metrics_resolver import get_environment_challenge_semantic, _ENV_CHALLENGE_SPORT_MAP
        for sport in ["running", "trail_running", "hiking", "cycling", "mountain_biking"]:
            for module in ["vertical", "altitude", "heat", "terrain"]:
                max_lvl = 3 if module == "heat" else 4
                for level in range(max_lvl + 1):
                    r = get_environment_challenge_semantic(sport, module, level)
                    self.assertTrue(r["explanation"],
                        f"{sport}/{module}/{level} explanation 空")


if __name__ == "__main__":
    unittest.main()
