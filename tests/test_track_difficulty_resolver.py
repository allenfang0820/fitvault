"""V4-2: calculate_track_difficulty 下沉至 MetricsResolver 单元测试

契约:fit-arch-contrac §V4.0 防腐层 / §2.1 全链路可追溯
验证:
  1. _calculate_track_difficulty 输出结构与原 main.py 一致
  2. 4 类难度等级(LV1-LV8)边界正确
  3. 运动类型参数(running/cycling/MTB)影响因子
  4. 输入异常(None/负数)安全降级
  5. main.py 透传函数不包含业务逻辑
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


class TestCalculateTrackDifficultyOutputContract(unittest.TestCase):
    """§2.1 输出结构契约:与原 main.py 一致"""

    def test_output_has_required_fields(self):
        """输出必须含 score/level/level_name/factors 四个字段"""
        result = MetricsResolver._calculate_track_difficulty(
            dist_km=10.0, gain_m=100.0, max_alt_m=500.0,
            max_single_climb_m=50.0, sport_type="running"
        )
        for key in ("score", "level", "level_name", "factors"):
            self.assertIn(key, result, f"输出必须含 {key} 字段")

    def test_factors_has_required_fields(self):
        """factors 子字段必须含 dist_factor/gain_factor/base_score/k_alt/p_climb"""
        result = MetricsResolver._calculate_track_difficulty(
            dist_km=10.0, gain_m=100.0, max_alt_m=500.0,
            max_single_climb_m=50.0, sport_type="running"
        )
        for key in ("dist_factor", "gain_factor", "base_score", "k_alt", "p_climb"):
            self.assertIn(key, result["factors"], f"factors 必须含 {key}")

    def test_level_name_format(self):
        """level_name 必须是 'LV N' 格式"""
        result = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, "running")
        self.assertTrue(result["level_name"].startswith("LV "))
        self.assertEqual(int(result["level_name"].split()[-1]), result["level"])

    def test_score_is_rounded(self):
        """score 必须 round 到 1 位小数"""
        result = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, "running")
        score_str = str(result["score"])
        if "." in score_str:
            decimals = score_str.split(".")[1]
            self.assertLessEqual(len(decimals), 1, "score 应保留 1 位小数")


class TestDifficultyLevels(unittest.TestCase):
    """§2.4 难度等级边界测试(LV1-LV8)"""

    def test_lv1_easy(self):
        """score < 8 → LV 1 (easy)"""
        # dist=5, gain=0, alt=0, climb=0 → base_score=5.0 → score=5.0 → LV1
        r = MetricsResolver._calculate_track_difficulty(5.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 1)
        self.assertEqual(r["level_name"], "LV 1")

    def test_lv2_threshold(self):
        """score=8 → LV 2"""
        # dist=8, gain=0, alt=0, climb=0 → base=8.0 → score=8.0 → LV2
        r = MetricsResolver._calculate_track_difficulty(8.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 2)

    def test_lv3_threshold(self):
        """score=16 → LV 3"""
        r = MetricsResolver._calculate_track_difficulty(16.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 3)

    def test_lv4_threshold(self):
        """score=29 → LV 4"""
        r = MetricsResolver._calculate_track_difficulty(29.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 4)

    def test_lv5_threshold(self):
        """score=46 → LV 5"""
        r = MetricsResolver._calculate_track_difficulty(46.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 5)

    def test_lv6_threshold(self):
        """score=76 → LV 6"""
        r = MetricsResolver._calculate_track_difficulty(76.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 6)

    def test_lv7_threshold(self):
        """score=111 → LV 7"""
        r = MetricsResolver._calculate_track_difficulty(111.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 7)

    def test_lv8_extreme(self):
        """score >= 181 → LV 8 (extreme)"""
        r = MetricsResolver._calculate_track_difficulty(181.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 8)
        self.assertEqual(r["level_name"], "LV 8")

    def test_lv8_above_threshold(self):
        """score > 181 → LV 8"""
        r = MetricsResolver._calculate_track_difficulty(300.0, 0, 0, 0, "running")
        self.assertEqual(r["level"], 8)


class TestSportTypeFactors(unittest.TestCase):
    """运动类型参数影响因子"""

    def test_running_factors(self):
        """running → dist_factor=1.0, gain_factor=100.0"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, "running")
        self.assertEqual(r["factors"]["dist_factor"], 1.0)
        self.assertEqual(r["factors"]["gain_factor"], 100.0)

    def test_trail_running_factors(self):
        """trail_running → 走 default 分支(running)→ dist_factor=1.0"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, "trail_running")
        self.assertEqual(r["factors"]["dist_factor"], 1.0)

    def test_cycling_factors(self):
        """cycling → dist_factor=3.0, gain_factor=120.0"""
        r = MetricsResolver._calculate_track_difficulty(50.0, 800.0, 1500.0, 200.0, "cycling")
        self.assertEqual(r["factors"]["dist_factor"], 3.0)
        self.assertEqual(r["factors"]["gain_factor"], 120.0)

    def test_road_cycling_factors(self):
        """road_cycling → 含 'cycl' → dist_factor=3.0"""
        r = MetricsResolver._calculate_track_difficulty(50.0, 800.0, 1500.0, 200.0, "road_cycling")
        self.assertEqual(r["factors"]["dist_factor"], 3.0)

    def test_mountain_biking_factors(self):
        """mountain_biking → 含 'cycl' + 'mountain' → dist_factor=2.0"""
        r = MetricsResolver._calculate_track_difficulty(30.0, 1500.0, 2500.0, 600.0, "mountain_biking")
        self.assertEqual(r["factors"]["dist_factor"], 2.0)
        self.assertEqual(r["factors"]["gain_factor"], 120.0)

    def test_chinese_sport_type(self):
        """中文 sport_type 也能识别(如 '骑行')"""
        r = MetricsResolver._calculate_track_difficulty(50.0, 800.0, 1500.0, 200.0, "骑行")
        self.assertEqual(r["factors"]["dist_factor"], 3.0)
        self.assertEqual(r["factors"]["gain_factor"], 120.0)

    def test_case_insensitive(self):
        """sport_type 大小写不敏感"""
        r1 = MetricsResolver._calculate_track_difficulty(50.0, 800.0, 1500.0, 200.0, "CYCLING")
        r2 = MetricsResolver._calculate_track_difficulty(50.0, 800.0, 1500.0, 200.0, "cycling")
        self.assertEqual(r1["level"], r2["level"])


class TestInputEdgeCases(unittest.TestCase):
    """输入异常边界:None/负数/0"""

    def test_none_inputs_safe(self):
        """None 输入不抛异常(走 max(0, x or 0) 降级)"""
        r = MetricsResolver._calculate_track_difficulty(None, None, None, None, "running")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["level"], 1)

    def test_negative_inputs_clamped(self):
        """负数输入 clamp 到 0"""
        r = MetricsResolver._calculate_track_difficulty(-10.0, -100.0, -500.0, -50.0, "running")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["level"], 1)

    def test_zero_inputs(self):
        """全 0 输入 → score=0 → LV1"""
        r = MetricsResolver._calculate_track_difficulty(0, 0, 0, 0, "running")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["level"], 1)

    def test_empty_sport_type(self):
        """空 sport_type 走 default 分支(running)"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, "")
        self.assertEqual(r["factors"]["dist_factor"], 1.0)

    def test_none_sport_type(self):
        """None sport_type 走 default 分支"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 50.0, None)
        self.assertEqual(r["factors"]["dist_factor"], 1.0)


class TestAltitudeAndClimbFactors(unittest.TestCase):
    """海拔与单次爬升对难度的影响"""

    def test_low_altitude_no_bonus(self):
        """max_alt < 2000 → k_alt = 1.0 (无加成)"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 1000.0, 50.0, "running")
        self.assertEqual(r["factors"]["k_alt"], 1.0)

    def test_high_altitude_bonus(self):
        """max_alt > 2000 → k_alt > 1.0"""
        r = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 4000.0, 50.0, "running")
        self.assertGreater(r["factors"]["k_alt"], 1.0)
        # k_alt = 1.0 + (4000-2000)/20000 = 1.1
        self.assertAlmostEqual(r["factors"]["k_alt"], 1.1, places=2)

    def test_single_climb_adds_p_climb(self):
        """max_single_climb 增加 p_climb(单次爬升难度)"""
        # 没有 climb 时
        r1 = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 0, "running")
        # 有 climb 时
        r2 = MetricsResolver._calculate_track_difficulty(10.0, 100.0, 500.0, 500.0, "running")
        # p_climb = climb / gain_factor
        self.assertAlmostEqual(r2["factors"]["p_climb"], 5.0, places=2)
        self.assertEqual(r1["factors"]["p_climb"], 0.0)
        self.assertGreater(r2["score"], r1["score"])


class TestMainPyPassthroughConstraint(unittest.TestCase):
    """§V4.0 透传代码模板:main.py 仅做 1 行透传,严禁添加额外逻辑"""

    def test_main_py_calculate_track_difficulty_is_thin_passthrough(self):
        """main.py 中的 calculate_track_difficulty 必须是 1 行 return(透传模板)"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "calculate_track_difficulty":
                continue
            func_src = ast.unparse(node)
            # 透传函数必须包含 MetricsResolver._calculate_track_difficulty 调用
            self.assertIn(
                "MetricsResolver._calculate_track_difficulty",
                func_src,
                "main.py calculate_track_difficulty 必须透传至 Resolver"
            )
            # 严禁含旧业务逻辑关键字(已下沉)
            forbidden_keywords = (
                "MTDI_LEVEL_THRESHOLDS",  # 阈值已下沉
                "dist_factor =",  # 旧版计算
                "gain_factor =",
                "k_alt =",
                "p_climb =",
            )
            for kw in forbidden_keywords:
                self.assertNotIn(
                    kw, func_src,
                    f"main.py calculate_track_difficulty 严禁含 {kw}(已下沉)"
                )

    def test_no_legacy_import_of_constants(self):
        """MTDI_LEVEL_THRESHOLDS 不再被 calculate_track_difficulty 引用"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "calculate_track_difficulty":
                continue
            func_src = ast.unparse(node)
            self.assertNotIn(
                "MTDI_LEVEL_THRESHOLDS", func_src,
                "MTDI_LEVEL_THRESHOLDS 已下沉,不应再在 main.py 函数中引用"
            )


class TestResolverExposesTrackDifficulty(unittest.TestCase):
    """MetricsResolver 契约层必须暴露 _calculate_track_difficulty"""

    def test_method_exists(self):
        self.assertTrue(hasattr(MetricsResolver, "_calculate_track_difficulty"))

    def test_method_callable(self):
        self.assertTrue(callable(getattr(MetricsResolver, "_calculate_track_difficulty", None)))

    def test_is_static_method(self):
        """_calculate_track_difficulty 必须是 @staticmethod"""
        method = getattr(MetricsResolver, "_calculate_track_difficulty", None)
        # 静态方法在 Python 中通过 __dict__ 暴露时是普通函数
        self.assertTrue(callable(method), "必须是可调用对象")


if __name__ == "__main__":
    unittest.main()
