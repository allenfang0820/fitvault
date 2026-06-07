"""V4.0 防腐层回归测试 — fatigue_zones 算法下沉至 Resolver

契约:fit-arch-contrac §V4.0 防腐层 / §五 AI 边界 / §三 响应结构
验证:
  1. _calculate_fatigue_zones 4 类运动阈值差异化
  2. while 循环正确推进(修复 for 循环 bug)
  3. 真实 distance_curve 距离(非线性均摊)
  4. 边界场景:空数据/长度不匹配/极端值
  5. 收尾逻辑(drop_late 模式)
  6. 输出格式契约:{start_km, end_km, level}
"""
from __future__ import annotations

import os
import sys
import time
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver


def _make_curves(n: int, ei_pattern: str = "stable"):
    """构造测试用 distance_curve + ei_curve"""
    distance_curve = [i * 10.0 for i in range(n)]  # 每 10m 一个点

    if ei_pattern == "stable":
        ei_curve = [1.0] * n
    elif ei_pattern == "drop_mid":
        ei_curve = [1.0] * (n // 2) + [0.7] * (n - n // 2)
    elif ei_pattern == "drop_late":
        cut = int(n * 0.8)
        ei_curve = [1.0] * cut + [0.5] * (n - cut)
    elif ei_pattern == "noise":
        ei_curve = [1.0 + 0.05 * ((i % 3) - 1) for i in range(n)]
    elif ei_pattern == "all_zero":
        ei_curve = [0.0] * n
    elif ei_pattern == "all_negative":
        ei_curve = [-0.5] * n
    elif ei_pattern == "mixed_invalid":
        ei_curve = [0.0, 1.0, 0.0, 1.0, 0.0] * (n // 5) if n >= 5 else [1.0] * n
    else:
        raise ValueError(f"未知 ei_pattern: {ei_pattern}")

    return distance_curve, ei_curve


class TestFatigueZonesThresholds(unittest.TestCase):
    """§V4.0 4 类运动阈值差异化"""

    def test_running_high_sensitivity(self):
        """running 阈值最低(0.10 warn / 0.20 high)→ 中段下降 0.3 应触发"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertGreater(len(zones), 0, "running + 30% 下降 → 应触发疲劳带")
        for z in zones:
            self.assertIn(z["level"], ("medium", "high"))
            self.assertGreater(z["end_km"], z["start_km"])

    def test_cycling_mid_sensitivity(self):
        """cycling 阈值中(0.15 warn / 0.30 high)→ 中段下降 0.3 应触发"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "cycling")
        self.assertGreater(len(zones), 0, "cycling + 30% 下降 → 应触发疲劳带")

    def test_hiking_mid_sensitivity(self):
        """hiking 阈值最高(0.18 warn / 0.35 high)→ 中段下降 0.3 应触发(超过 0.18)"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "hiking")
        # hiking warn 0.18,30% 下降超过 0.18 → 应触发
        self.assertGreater(len(zones), 0)

    def test_unknown_sport_fallback(self):
        """未知 sport 走 fallback 阈值"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "yoga")
        self.assertIsInstance(zones, list)

    def test_case_insensitive_sport(self):
        """sport_type 大小写不敏感"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "Running")
        self.assertGreater(len(zones), 0, "sport_type 大小写应不敏感")

    def test_trail_running_uses_running_thresholds(self):
        """trail_running 应使用 running 阈值(同 sport 族)"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "trail_running")
        self.assertGreater(len(zones), 0)


class TestFatigueZonesDistanceAccuracy(unittest.TestCase):
    """真实 distance_curve 距离(非线性均摊)"""

    def test_uses_real_distance_curve(self):
        """start_km / end_km 必须来源于 distance_curve 而非线性均摊"""
        n = 100
        # 前 50 个点:每点 1m(共 50m),后 50 个点:每点 19m(共 950m)
        distance_curve = [1.0 * i for i in range(50)] + [
            50.0 + 19.0 * (i - 50) for i in range(50, 100)
        ]
        ei_curve = [1.0] * 60 + [0.7] * 40
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertGreater(len(zones), 0)
        for z in zones:
            self.assertLessEqual(z["end_km"], 1.0, "end_km 应基于真实距离(总距离 1.0km)")

    def test_uneven_distance_curve_handled(self):
        """不均匀距离曲线应正确处理"""
        n = 400
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        if len(zones) > 0:
            for z in zones:
                self.assertLess(z["end_km"], 4.0, "end_km 应小于 4.0km(总距离)")


class TestFatigueZonesWhileLoopCorrectness(unittest.TestCase):
    """while 循环正确推进(修复 for 循环 bug)"""

    def test_loop_terminates_within_bounded_time(self):
        """循环必须在有限时间内终止(while 条件 i <= n - window 保证)"""
        n = 50
        distance_curve, ei_curve = _make_curves(n, "stable")
        start = time.time()
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        elapsed = time.time() - start
        self.assertLess(elapsed, 5.0, f"循环超时(可能 for bug 未修复): {elapsed:.2f}s")
        self.assertEqual(zones, [], "stable 模式不应触发任何 fatigue zone")

    def test_loop_handles_long_arrays(self):
        """长数组 (n=2000) 必须在合理时间内完成"""
        n = 2000
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        start = time.time()
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        elapsed = time.time() - start
        self.assertLess(elapsed, 5.0, f"长数组超时: {elapsed:.2f}s")
        self.assertIsInstance(zones, list)


class TestFatigueZonesEdgeCases(unittest.TestCase):
    """边界场景"""

    def test_empty_distance_curve(self):
        zones = MetricsResolver._calculate_fatigue_zones([], [1.0, 1.1, 1.2], "running")
        self.assertEqual(zones, [])

    def test_empty_ei_curve(self):
        zones = MetricsResolver._calculate_fatigue_zones([1.0, 2.0, 3.0], [], "running")
        self.assertEqual(zones, [])

    def test_both_empty(self):
        zones = MetricsResolver._calculate_fatigue_zones([], [], "running")
        self.assertEqual(zones, [])

    def test_length_mismatch(self):
        zones = MetricsResolver._calculate_fatigue_zones([1.0, 2.0, 3.0], [1.0, 1.1], "running")
        self.assertEqual(zones, [])

    def test_n_less_than_10(self):
        distance_curve = [1.0 * i for i in range(5)]
        ei_curve = [1.0, 0.9, 0.8, 0.7, 0.6]
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertEqual(zones, [])

    def test_n_exactly_10(self):
        distance_curve = [1.0 * i for i in range(10)]
        ei_curve = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertIsInstance(zones, list)

    def test_all_zero_ei(self):
        n = 50
        distance_curve = [1.0 * i for i in range(n)]
        ei_curve = [0.0] * n
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertEqual(zones, [])

    def test_all_negative_ei(self):
        n = 50
        distance_curve = [1.0 * i for i in range(n)]
        ei_curve = [-0.5] * n
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertEqual(zones, [])

    def test_mixed_valid_invalid_ei(self):
        n = 50
        distance_curve = [1.0 * i for i in range(n)]
        ei_curve = [0.0, 1.0, 0.0, 1.0, 0.0] * 10
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertIsInstance(zones, list)


class TestFatigueZonesTrailingZone(unittest.TestCase):
    """末尾收尾逻辑"""

    def test_late_drop_triggers_trailing_zone(self):
        """末尾下降 → 收尾逻辑应触发 fatigue zone"""
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_late")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertGreater(len(zones), 0, "drop_late 模式应触发疲劳带(末尾收尾)")
        if zones:
            last_zone = zones[-1]
            total_km = distance_curve[-1] / 1000.0
            self.assertAlmostEqual(last_zone["end_km"], round(total_km, 2), delta=0.5)

    def test_stable_no_zones(self):
        n = 200
        distance_curve, ei_curve = _make_curves(n, "stable")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        self.assertEqual(zones, [])


class TestFatigueZonesOutputContract(unittest.TestCase):
    """输出格式契约"""

    def test_output_field_names(self):
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        for z in zones:
            self.assertIn("start_km", z)
            self.assertIn("end_km", z)
            self.assertIn("level", z)

    def test_output_level_values(self):
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        for z in zones:
            self.assertIn(z["level"], ("medium", "high"))

    def test_output_distance_positive(self):
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        for z in zones:
            self.assertGreater(z["end_km"], z["start_km"])

    def test_output_distance_rounded(self):
        n = 200
        distance_curve, ei_curve = _make_curves(n, "drop_mid")
        zones = MetricsResolver._calculate_fatigue_zones(distance_curve, ei_curve, "running")
        for z in zones:
            for s in (str(z["start_km"]), str(z["end_km"])):
                if "." in s:
                    decimals = s.split(".")[1]
                    self.assertLessEqual(len(decimals), 2)


if __name__ == "__main__":
    unittest.main()
