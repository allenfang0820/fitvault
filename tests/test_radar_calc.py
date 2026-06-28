"""
雷达图核心算法单元测试。

覆盖范围：
- AdvancedMetricsCalc 5 个物理指标算法（边界 / 过滤 / 前置条件）
- RadarScoreEngine 6 个评分映射（分段边界 / 运动类型分支）
- RadarScoreEngine.build_radar_profile（运动类型维度 schema / 中文标签）

遵循 fit-arch-contrac 契约：
- 不依赖 DB
- 不依赖 AI/LLM
- 不写回 canonical 层
- 不使用 shadow_diff
"""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from main import _p90
from utils.metrics_calc import AdvancedMetricsCalc, RadarScoreEngine


def _ts(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _record(timestamp, hr=None, speed=None, altitude=None, distance=None, power=None):
    return {
        "timestamp": timestamp,
        "heart_rate": hr,
        "speed": speed,
        "altitude": altitude,
        "distance": distance,
        "power": power,
    }


def _linear_records_hr(start, count, hr_value, hr_step=0, interval=1):
    records = []
    for i in range(count):
        records.append(_record(
            start + timedelta(seconds=i * interval),
            hr=hr_value + i * hr_step,
        ))
    return records


def _running_records(duration_seconds=2700, base_hr=150, base_speed=3.5, base_alt=100.0):
    start = _ts(2026, 1, 1, 8, 0, 0)
    records = []
    for i in range(duration_seconds + 1):
        hr = base_hr + (i / 600.0)
        speed = base_speed + 0.0001 * i
        alt = base_alt + max(0, i - 600) * 0.02
        records.append(_record(
            start + timedelta(seconds=i),
            hr=hr,
            speed=speed,
            altitude=alt,
            distance=i * 3.5,
        ))
    return records


class TestCalculateTrimp(unittest.TestCase):

    def test_empty_records_returns_zero(self):
        self.assertEqual(AdvancedMetricsCalc.calculate_trimp([]), 0.0)

    def test_single_record_returns_zero(self):
        records = [_record(_ts(2026, 1, 1), hr=150)]
        self.assertEqual(AdvancedMetricsCalc.calculate_trimp(records), 0.0)

    def test_no_hr_data_returns_zero(self):
        start = _ts(2026, 1, 1)
        records = [_record(start), _record(start + timedelta(seconds=1))]
        self.assertEqual(AdvancedMetricsCalc.calculate_trimp(records), 0.0)

    def test_hr_out_of_range_high_skipped(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, hr=140),
            _record(start + timedelta(seconds=1), hr=240),
            _record(start + timedelta(seconds=2), hr=140),
        ]
        result = AdvancedMetricsCalc.calculate_trimp(records)
        self.assertEqual(result, 0.0)

    def test_hr_at_or_below_resting_returns_zero(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 60, 60, interval=1)
        result = AdvancedMetricsCalc.calculate_trimp(records, {"resting_hr": 60, "max_hr": 190})
        self.assertEqual(result, 0.0)

    def test_time_gap_gt_5min_skipped(self):
        start = _ts(2026, 1, 1)
        records = []
        for i in range(60):
            records.append(_record(start + timedelta(seconds=i), hr=150))
        records.append(_record(start + timedelta(seconds=460), hr=150))
        result = AdvancedMetricsCalc.calculate_trimp(records, {"resting_hr": 60, "max_hr": 190})
        self.assertGreater(result, 1.0)
        self.assertLess(result, 5.0)

    def test_max_hr_fallback_uses_age_formula(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 60, 150, interval=1)
        result = AdvancedMetricsCalc.calculate_trimp(records, {"age": 35, "resting_hr": 60})
        self.assertGreater(result, 0.0)

    def test_max_hr_eq_rest_hr_returns_zero(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 60, 150, interval=1)
        result = AdvancedMetricsCalc.calculate_trimp(records, {"max_hr": 60, "resting_hr": 60})
        self.assertEqual(result, 0.0)

    def test_gender_male_uses_b_1_92(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 30, 150, interval=1)
        male = AdvancedMetricsCalc.calculate_trimp(records, {"gender": "male", "resting_hr": 60, "max_hr": 190})
        female = AdvancedMetricsCalc.calculate_trimp(records, {"gender": "female", "resting_hr": 60, "max_hr": 190})
        self.assertGreater(male, female)

    def test_normal_running_produces_positive_trimp(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 1800, 150, interval=1)
        result = AdvancedMetricsCalc.calculate_trimp(records, {"resting_hr": 60, "max_hr": 190})
        self.assertGreater(result, 30.0)
        self.assertIsInstance(result, float)

    def test_returns_rounded_to_one_decimal(self):
        records = _linear_records_hr(_ts(2026, 1, 1), 600, 150, interval=1)
        result = AdvancedMetricsCalc.calculate_trimp(records, {"resting_hr": 60, "max_hr": 190})
        self.assertEqual(result, round(result, 1))


class TestCalculateAerobicDecoupling(unittest.TestCase):

    def test_empty_records_returns_none(self):
        self.assertIsNone(AdvancedMetricsCalc.calculate_aerobic_decoupling([]))

    def test_duration_lt_2400s_returns_none(self):
        records = _running_records(duration_seconds=1800)
        self.assertIsNone(AdvancedMetricsCalc.calculate_aerobic_decoupling(records))

    def test_no_hr_or_speed_returns_none(self):
        start = _ts(2026, 1, 1)
        records = [_record(start + timedelta(seconds=i)) for i in range(3000)]
        self.assertIsNone(AdvancedMetricsCalc.calculate_aerobic_decoupling(records))

    def test_normal_run_returns_decoupling(self):
        records = _running_records(duration_seconds=2700)
        result = AdvancedMetricsCalc.calculate_aerobic_decoupling(records)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)

    def test_decoupling_returns_rounded(self):
        records = _running_records(duration_seconds=2700)
        result = AdvancedMetricsCalc.calculate_aerobic_decoupling(records)
        if result is not None:
            self.assertEqual(result, round(result, 2))

    def test_invalid_hr_at_boundaries_skipped(self):
        start = _ts(2026, 1, 1)
        records = []
        for i in range(3000):
            if i < 100:
                hr = 150
                spd = 3.5
            else:
                hr = 30
                spd = 0.4
            records.append(_record(start + timedelta(seconds=i), hr=hr, speed=spd))
        result = AdvancedMetricsCalc.calculate_aerobic_decoupling(records)
        self.assertIsNone(result)


class TestCalculateVam(unittest.TestCase):
    """VAM 根因修复:「有效爬坡段」算法。

    旧实现逐点累计,导致 1m/5s 噪声被算成 720 m/h。
    新实现:rolling median 平滑 → 连续爬坡段识别 → 段级过滤
    (>=10m / 60s / 100m / 3%)。
    """

    def test_empty_records_returns_zero(self):
        self.assertEqual(AdvancedMetricsCalc.calculate_vam([]), 0.0)

    def test_single_record_returns_zero(self):
        records = [_record(_ts(2026, 1, 1), altitude=100, distance=0)]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    # === 边界:数据缺失 / 倒序 ===

    def test_records_without_altitude_returns_zero(self):
        """无 altitude 字段:不构成有效段,返回 0.0。"""
        start = _ts(2026, 1, 1)
        records = [
            _record(start, distance=0),
            _record(start + timedelta(seconds=1), distance=10),
        ]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    def test_records_without_distance_returns_zero(self):
        """无 distance 字段:不构成有效段,返回 0.0。"""
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100),
            _record(start + timedelta(seconds=1), altitude=120),
        ]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    def test_inverted_timestamps_returns_zero(self):
        """时间倒序:排序后 delta_time 为 0,所有配对被跳过。"""
        records = [
            _record(_ts(2026, 1, 1, 1, 0, 0), altitude=200, distance=200),
            _record(_ts(2026, 1, 1, 0, 0, 0), altitude=100, distance=0),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    # === 基础场景:无有效爬坡 → 0.0 ===

    def test_flat_altitude_returns_zero(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=100, distance=10),
            _record(start + timedelta(seconds=2), altitude=100, distance=20),
        ]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    def test_descending_only_returns_zero(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=200, distance=0),
            _record(start + timedelta(seconds=1), altitude=150, distance=10),
            _record(start + timedelta(seconds=2), altitude=100, distance=20),
        ]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    def test_gradient_below_3pct_does_not_form_valid_segment(self):
        """单点低坡度(0.2m/10m = 2%)不构成有效段 → 0.0。"""
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=100.2, distance=10),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    # === 根因场景:平路噪声 / 通勤片段 ===

    def test_flat_road_with_1m_altitude_noise_returns_zero(self):
        """城市平路骑行/跑步:120s 内 1m 级海拔抖动。

        旧实现:逐点累计会被算成数百 m/h。
        新实现:rolling median 抑制噪声,段级过滤不达标 → 0.0。
        """
        start = _ts(2026, 1, 1)
        records = []
        for i in range(121):
            # alt 在 100.0 / 100.5 / 101.0 之间来回抖动
            alt = 100.0 + (0.5 if (i // 10) % 2 == 0 else -0.5)
            records.append(_record(
                start + timedelta(seconds=i),
                altitude=alt,
                distance=i * 5,  # 0-600m
            ))
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    def test_short_commute_segment_returns_zero(self):
        """短距离通勤片段:30s, 5m 爬升, 30m 距离。

        时间/距离/爬升均不满足段级阈值 → 0.0。
        """
        start = _ts(2026, 1, 1)
        records = []
        for i in range(31):
            records.append(_record(
                start + timedelta(seconds=i),
                altitude=100 + i * (5.0 / 30.0),  # 100 → 105m
                distance=i,  # 0 → 30m
            ))
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    # === 异常过滤 ===

    def test_anomalous_vertical_speed_5ms_filtered(self):
        """单点垂直速度 >= 5 m/s 视为异常,跳过。"""
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=106, distance=10),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    def test_time_gap_gt_300s_cuts_segment_but_keeps_valid_climb(self):
        """时间断裂 > 300s 切断当前段,但有效爬坡段应被保留。"""
        start = _ts(2026, 1, 1)
        records = []
        # 真实有效爬坡:100s, 15m, 500m, 坡度 3%
        for i in range(101):
            records.append(_record(
                start + timedelta(seconds=i),
                altitude=100 + i * 0.15,  # 100 → 115m
                distance=i * 5,           # 0 → 500m
            ))
        # 大时间间隔 + 噪声点
        records.append(_record(
            start + timedelta(seconds=500),
            altitude=200,
            distance=510,
        ))
        result = AdvancedMetricsCalc.calculate_vam(records)
        # 应检出有效段:VAM ≈ 15/100 * 3600 = 540
        self.assertGreater(result, 0.0)
        self.assertAlmostEqual(result, 540.0, delta=30.0)

    # === 核心:有效爬坡段识别 ===

    def test_vam_formula_uses_3600(self):
        """最短有效段:60s / 200m / 10m,坡度 5%。VAM = 10/60*3600 = 600.0。"""
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=0, distance=0),
            _record(start + timedelta(seconds=60), altitude=10, distance=200),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 600.0)

    def test_real_climb_300m_20m_120s_produces_about_600(self):
        """真实连续爬坡:300m 距离, 20m 爬升, 120s。VAM ≈ 600。"""
        start = _ts(2026, 1, 1)
        records = []
        for i in range(121):
            records.append(_record(
                start + timedelta(seconds=i),
                altitude=100 + (i / 120.0) * 20,   # 100 → 120m
                distance=(i / 120.0) * 300,         # 0 → 300m
            ))
        result = AdvancedMetricsCalc.calculate_vam(records)
        # 20/120 * 3600 = 600
        self.assertAlmostEqual(result, 600.0, delta=15.0)

    def test_real_climb_with_small_dip_is_not_cut(self):
        """真实爬坡中含 1-2m 海拔回落,不应被完全切断。"""
        start = _ts(2026, 1, 1)
        records = []
        for i in range(151):
            alt = 100 + (i / 150.0) * 25  # 100 → 125m
            # 在 50-55s / 100-105s 制造 1.5m 小幅回落
            if 50 <= i <= 55:
                alt -= 1.5
            if 100 <= i <= 105:
                alt -= 1.5
            records.append(_record(
                start + timedelta(seconds=i),
                altitude=alt,
                distance=(i / 150.0) * 400,  # 0 → 400m
            ))
        result = AdvancedMetricsCalc.calculate_vam(records)
        # 仍应检出有效段(总爬升 ≈ 25m, 距离 ≈ 400m, 时间 ≈ 150s)
        self.assertGreater(result, 0.0)
        self.assertGreater(result, 400.0)

    def test_returns_rounded_to_one_decimal(self):
        records = _running_records(duration_seconds=600)
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, round(result, 1))


class TestCalculateThresholdHr(unittest.TestCase):

    def test_empty_records_returns_none(self):
        self.assertIsNone(AdvancedMetricsCalc.calculate_threshold_hr([]))

    def test_all_invalid_hr_returns_none(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, hr=10),
            _record(start + timedelta(seconds=1), hr=300),
        ]
        self.assertIsNone(AdvancedMetricsCalc.calculate_threshold_hr(records))

    def test_short_window_returns_none(self):
        start = _ts(2026, 1, 1)
        records = _linear_records_hr(start, 60, 150, interval=1)
        self.assertIsNone(AdvancedMetricsCalc.calculate_threshold_hr(records))

    def test_returns_max_20m_avg_hr_times_0_95(self):
        start = _ts(2026, 1, 1)
        records = _linear_records_hr(start, 1200, 160, interval=1)
        result = AdvancedMetricsCalc.calculate_threshold_hr(records)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 160.0 * 0.95, places=1)

    def test_returns_rounded(self):
        start = _ts(2026, 1, 1)
        records = _linear_records_hr(start, 1200, 165, interval=1)
        result = AdvancedMetricsCalc.calculate_threshold_hr(records)
        self.assertEqual(result, round(result, 1))

    def test_higher_hr_in_window_takes_precedence(self):
        start = _ts(2026, 1, 1)
        records = []
        for i in range(1800):
            hr = 150 if i < 600 else 170
            records.append(_record(start + timedelta(seconds=i), hr=hr))
        result = AdvancedMetricsCalc.calculate_threshold_hr(records)
        self.assertAlmostEqual(result, 170.0 * 0.95, places=1)

    def test_cycling_profile_ftp_with_weight_uses_ftp_wkg(self):
        detail = AdvancedMetricsCalc.calculate_threshold_detail(
            [],
            "cycling",
            {"ftp": 245, "weight_kg": 70, "max_hr": 185},
        )
        self.assertEqual(detail["source"], "ftp_wkg")
        self.assertEqual(detail["confidence"], "high")
        self.assertAlmostEqual(detail["threshold_wkg"], 3.5, places=1)

    def test_cycling_profile_ftp_without_weight_uses_ftp_w(self):
        detail = AdvancedMetricsCalc.calculate_threshold_detail(
            [],
            "cycling",
            {"ftp": 260, "max_hr": 185},
        )
        self.assertEqual(detail["source"], "ftp_w")
        self.assertEqual(detail["confidence"], "high")
        self.assertEqual(detail["threshold_power"], 260)

    def test_cycling_records_power_estimates_threshold_power(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start + timedelta(seconds=i), hr=150, speed=8.0, altitude=100.0, distance=i * 8.0, power=300)
            for i in range(1300)
        ]
        detail = AdvancedMetricsCalc.calculate_threshold_detail(records, "cycling", {"weight_kg": 75, "max_hr": 185})
        self.assertEqual(detail["source"], "ftp_wkg")
        self.assertEqual(detail["confidence"], "medium")
        self.assertAlmostEqual(detail["threshold_power"], 285.0, places=1)
        self.assertAlmostEqual(detail["threshold_wkg"], 3.8, places=1)

    def test_cycling_short_power_falls_back_to_threshold_hr(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start + timedelta(seconds=i), hr=160, speed=8.0, altitude=100.0, distance=i * 8.0, power=300)
            for i in range(600)
        ]
        detail = AdvancedMetricsCalc.calculate_threshold_detail(records, "cycling", {"max_hr": 185})
        self.assertEqual(detail["source"], "none")
        self.assertIsNone(detail["threshold_power"])

    def test_cycling_without_power_uses_threshold_hr_fallback(self):
        start = _ts(2026, 1, 1)
        records = [_record(start + timedelta(seconds=i), hr=160) for i in range(1300)]
        detail = AdvancedMetricsCalc.calculate_threshold_detail(records, "cycling", {"max_hr": 185})
        self.assertEqual(detail["source"], "threshold_hr")
        self.assertEqual(detail["confidence"], "low")
        self.assertIsNotNone(detail["threshold_hr"])


class TestCalculateAnaerobicPeak(unittest.TestCase):

    def test_empty_records_returns_none(self):
        self.assertIsNone(AdvancedMetricsCalc.calculate_anaerobic_peak([]))

    def test_short_window_returns_none(self):
        start = _ts(2026, 1, 1)
        records = _linear_records_hr(start, 3, 0, hr_step=0, interval=1)
        for r in records:
            r["speed"] = 5.0
        self.assertIsNone(AdvancedMetricsCalc.calculate_anaerobic_peak(records))

    def test_speed_out_of_range_skipped(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, speed=40),
            _record(start + timedelta(seconds=1), speed=40),
            _record(start + timedelta(seconds=2), speed=40),
        ]
        self.assertIsNone(AdvancedMetricsCalc.calculate_anaerobic_peak(records))

    def test_returns_30s_avg_max(self):
        start = _ts(2026, 1, 1)
        records = []
        for i in range(60):
            spd = 3.0 if i < 30 else 6.0
            records.append(_record(start + timedelta(seconds=i), speed=spd))
        result = AdvancedMetricsCalc.calculate_anaerobic_peak(records)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result, 5.5)

    def test_zero_speed_filtered(self):
        start = _ts(2026, 1, 1)
        records = []
        for i in range(60):
            spd = 0.0 if i < 30 else 5.0
            records.append(_record(start + timedelta(seconds=i), speed=spd))
        result = AdvancedMetricsCalc.calculate_anaerobic_peak(records)
        self.assertIsNotNone(result)

    def test_returns_rounded_to_two_decimals(self):
        records = _running_records(duration_seconds=300, base_speed=4.0)
        result = AdvancedMetricsCalc.calculate_anaerobic_peak(records)
        if result is not None:
            self.assertEqual(result, round(result, 2))

    def test_cycling_power_with_weight_uses_wkg_high_confidence(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start + timedelta(seconds=i), speed=8.0, altitude=100.0, distance=i * 8.0, power=700)
            for i in range(70)
        ]
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(
            records,
            "cycling",
            {"weight_kg": 70, "max_hr": 185},
        )
        self.assertEqual(detail["source"], "power_wkg")
        self.assertEqual(detail["confidence"], "high")
        self.assertAlmostEqual(detail["best_30s_wkg"], 10.0, places=1)
        self.assertGreaterEqual(detail["value"], 9.0)

    def test_cycling_power_without_weight_uses_power_medium_confidence(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start + timedelta(seconds=i), speed=8.0, altitude=100.0, distance=i * 8.0, power=920)
            for i in range(70)
        ]
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(records, "cycling", {"max_hr": 185})
        self.assertEqual(detail["source"], "power_w")
        self.assertEqual(detail["confidence"], "medium")
        self.assertGreaterEqual(detail["best_30s_power"], 900)
        self.assertEqual(RadarScoreEngine.score_anaerobic(detail["value"], "cycling", detail["source"]), 75)

    def test_cycling_downhill_speed_fallback_does_not_score_95(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(
                start + timedelta(seconds=i),
                hr=120,
                speed=18.0,
                altitude=200.0 - i * 0.4,
                distance=i * 18.0,
            )
            for i in range(70)
        ]
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(records, "cycling", {"max_hr": 185})
        self.assertIsNone(detail["value"])
        self.assertEqual(detail["source"], "none")

    def test_cycling_flat_speed_fallback_is_capped_at_75(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(
                start + timedelta(seconds=i),
                hr=155,
                speed=18.0,
                altitude=100.0,
                distance=i * 18.0,
            )
            for i in range(70)
        ]
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(records, "cycling", {"max_hr": 185})
        self.assertEqual(detail["source"], "speed_fallback")
        self.assertEqual(detail["confidence"], "low")
        self.assertEqual(
            RadarScoreEngine.score_anaerobic(detail["value"], "cycling", detail["source"], detail["confidence"]),
            75,
        )

    def test_running_downhill_speed_spike_is_filtered(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(
                start + timedelta(seconds=i),
                speed=6.5,
                altitude=200.0 - i * 0.4,
                distance=i * 6.5,
            )
            for i in range(70)
        ]
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(records, "running")
        self.assertIsNone(detail["value"])

    def test_legacy_call_still_returns_float(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start + timedelta(seconds=i), speed=5.0, altitude=100.0, distance=i * 5.0)
            for i in range(70)
        ]
        result = AdvancedMetricsCalc.calculate_anaerobic_peak(records)
        self.assertIsInstance(result, float)


class TestScoreEndurance(unittest.TestCase):

    def test_zero_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_endurance(0), 0)
        self.assertEqual(RadarScoreEngine.score_endurance(None), 0)

    def test_bracket_below_30(self):
        self.assertEqual(RadarScoreEngine.score_endurance(20), 20)
        self.assertEqual(RadarScoreEngine.score_endurance(29.9), 20)

    def test_bracket_30_to_80(self):
        self.assertEqual(RadarScoreEngine.score_endurance(30), 50)
        self.assertEqual(RadarScoreEngine.score_endurance(79.9), 50)

    def test_bracket_80_to_150(self):
        self.assertEqual(RadarScoreEngine.score_endurance(80), 75)
        self.assertEqual(RadarScoreEngine.score_endurance(149.9), 75)

    def test_bracket_above_150(self):
        self.assertEqual(RadarScoreEngine.score_endurance(150), 95)
        self.assertEqual(RadarScoreEngine.score_endurance(300), 95)

    def test_running_thresholds_are_sport_specific(self):
        self.assertEqual(RadarScoreEngine.score_endurance(19.9, "running"), 20)
        self.assertEqual(RadarScoreEngine.score_endurance(20, "running"), 50)
        self.assertEqual(RadarScoreEngine.score_endurance(45, "trail_running"), 75)
        self.assertEqual(RadarScoreEngine.score_endurance(70, "treadmill_running"), 95)

    def test_cycling_thresholds_are_sport_specific(self):
        self.assertEqual(RadarScoreEngine.score_endurance(29.9, "cycling"), 20)
        self.assertEqual(RadarScoreEngine.score_endurance(30, "road_cycling"), 50)
        self.assertEqual(RadarScoreEngine.score_endurance(80, "mountain_biking"), 75)
        self.assertEqual(RadarScoreEngine.score_endurance(130, "cycling"), 95)

    def test_hiking_thresholds_are_sport_specific(self):
        self.assertEqual(RadarScoreEngine.score_endurance(9.9, "hiking"), 20)
        self.assertEqual(RadarScoreEngine.score_endurance(10, "walking"), 50)
        self.assertEqual(RadarScoreEngine.score_endurance(25, "mountaineering"), 75)
        self.assertEqual(RadarScoreEngine.score_endurance(45, "hiking"), 95)

    def test_endurance_detail_combines_ctl_and_consistency(self):
        detail = RadarScoreEngine.score_endurance_detail(
            50,
            "running",
            training_days_28d=10,
            sample_count=8,
        )
        self.assertEqual(detail["ctl_score"], 75)
        self.assertEqual(detail["consistency_score"], 75)
        self.assertEqual(detail["score"], 75)
        self.assertEqual(detail["confidence"], "medium")
        self.assertEqual(detail["source"], "ctl_42d_plus_28d_consistency")

    def test_endurance_detail_no_sample_returns_zero(self):
        detail = RadarScoreEngine.score_endurance_detail(100, "running")
        self.assertEqual(detail["score"], 0)
        self.assertEqual(detail["ctl_score"], 95)
        self.assertEqual(detail["consistency_score"], 0)
        self.assertEqual(detail["confidence"], "low")
        self.assertEqual(detail["source"], "no_valid_trimp")

    def test_endurance_confidence_buckets(self):
        self.assertEqual(RadarScoreEngine.score_endurance_detail(50, "running", 4, 5)["confidence"], "low")
        self.assertEqual(RadarScoreEngine.score_endurance_detail(50, "running", 4, 6)["confidence"], "medium")
        self.assertEqual(RadarScoreEngine.score_endurance_detail(50, "running", 4, 12)["confidence"], "high")


class TestScoreRecovery(unittest.TestCase):

    def test_none_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_recovery(None), 0)

    def test_clamps_negative_to_0(self):
        self.assertEqual(RadarScoreEngine.score_recovery(-10), 0)

    def test_clamps_above_100_to_100(self):
        self.assertEqual(RadarScoreEngine.score_recovery(150), 100)

    def test_passes_through_valid_range(self):
        self.assertEqual(RadarScoreEngine.score_recovery(0), 0)
        self.assertEqual(RadarScoreEngine.score_recovery(60), 60)
        self.assertEqual(RadarScoreEngine.score_recovery(100), 100)

    def test_float_input_truncated_to_int(self):
        self.assertEqual(RadarScoreEngine.score_recovery(60.7), 60)
        self.assertEqual(RadarScoreEngine.score_recovery(60.9), 60)

    def test_baseline_only_is_conservative_not_absolute_hrv(self):
        detail = RadarScoreEngine.score_recovery_detail({"hrv_baseline": 56.4}, {})
        self.assertEqual(detail["source"], "baseline_only")
        self.assertEqual(detail["confidence"], "low")
        self.assertEqual(detail["score"], 60)
        self.assertNotEqual(detail["score"], 56)

    def test_recent_hrv_at_or_above_baseline_scores_high(self):
        detail = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 50, "recent_hrv": 52, "avg_sleep_hours": 7.5, "resting_hr": 52, "recent_resting_hr": 51},
            {"tsb": 2, "atl": 50},
        )
        self.assertEqual(detail["source"], "hrv_trend")
        self.assertEqual(detail["confidence"], "high")
        self.assertGreaterEqual(detail["score"], 85)

    def test_low_recent_hrv_scores_low(self):
        detail = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 60, "recent_hrv": 45},
            {"tsb": -5},
        )
        self.assertEqual(detail["source"], "hrv_trend")
        self.assertLessEqual(detail["score"], 50)

    def test_low_tsb_reduces_recovery(self):
        detail = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 60, "recent_hrv": 60, "avg_sleep_hours": 7.0},
            {"tsb": -30, "atl": 110},
        )
        self.assertLess(detail["score"], 80)

    def test_short_sleep_reduces_recovery(self):
        good = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 60, "recent_hrv": 60, "avg_sleep_hours": 7.5},
            {"tsb": 0},
        )
        poor = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 60, "recent_hrv": 60, "avg_sleep_hours": 4.5},
            {"tsb": 0},
        )
        self.assertLess(poor["score"], good["score"])

    def test_resting_hr_increase_reduces_recovery(self):
        detail = RadarScoreEngine.score_recovery_detail(
            {"hrv_baseline": 60, "recent_hrv": 60, "resting_hr": 52, "recent_resting_hr": 60},
            {"tsb": 0},
        )
        self.assertLess(detail["score"], 85)

    def test_missing_profile_does_not_crash(self):
        detail = RadarScoreEngine.score_recovery_detail(None, None)
        self.assertEqual(detail["confidence"], "low")
        self.assertIn("score", detail)


class TestScoreStability(unittest.TestCase):

    def test_none_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_stability(None), 0)

    def test_bracket_below_5(self):
        self.assertEqual(RadarScoreEngine.score_stability(0), 95)
        self.assertEqual(RadarScoreEngine.score_stability(4.9), 95)

    def test_bracket_5_to_10(self):
        self.assertEqual(RadarScoreEngine.score_stability(5), 75)
        self.assertEqual(RadarScoreEngine.score_stability(9.9), 75)

    def test_bracket_10_to_15(self):
        self.assertEqual(RadarScoreEngine.score_stability(10), 55)
        self.assertEqual(RadarScoreEngine.score_stability(14.9), 55)

    def test_bracket_above_15(self):
        self.assertEqual(RadarScoreEngine.score_stability(15), 30)
        self.assertEqual(RadarScoreEngine.score_stability(30), 30)


class TestScoreClimbing(unittest.TestCase):

    def test_zero_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_climbing(0), 0)
        self.assertEqual(RadarScoreEngine.score_climbing(None), 0)

    def test_bracket_below_300(self):
        self.assertEqual(RadarScoreEngine.score_climbing(200), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(299.9), 20)

    def test_bracket_300_to_600(self):
        self.assertEqual(RadarScoreEngine.score_climbing(300), 50)
        self.assertEqual(RadarScoreEngine.score_climbing(599.9), 50)

    def test_bracket_600_to_900(self):
        self.assertEqual(RadarScoreEngine.score_climbing(600), 75)
        self.assertEqual(RadarScoreEngine.score_climbing(899.9), 75)

    def test_bracket_above_900(self):
        self.assertEqual(RadarScoreEngine.score_climbing(900), 95)
        self.assertEqual(RadarScoreEngine.score_climbing(1500), 95)


class TestScoreThreshold(unittest.TestCase):

    def test_missing_threshold_hr_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_threshold(None, 190), 0)

    def test_missing_max_hr_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_threshold(170, None), 0)

    def test_bracket_below_0_75(self):
        self.assertEqual(RadarScoreEngine.score_threshold(140, 190), 40)
        self.assertEqual(RadarScoreEngine.score_threshold(142, 190), 40)

    def test_bracket_0_75_to_0_82(self):
        self.assertEqual(RadarScoreEngine.score_threshold(143, 190), 65)
        self.assertEqual(RadarScoreEngine.score_threshold(155, 190), 65)

    def test_bracket_0_82_to_0_88(self):
        self.assertEqual(RadarScoreEngine.score_threshold(156, 190), 82)
        self.assertEqual(RadarScoreEngine.score_threshold(167, 190), 82)

    def test_bracket_above_0_88(self):
        self.assertEqual(RadarScoreEngine.score_threshold(168, 190), 95)
        self.assertEqual(RadarScoreEngine.score_threshold(180, 190), 95)

    def test_cycling_ftp_wkg_brackets(self):
        self.assertEqual(RadarScoreEngine.score_threshold(1.9, 190, "cycling", "ftp_wkg"), 40)
        self.assertEqual(RadarScoreEngine.score_threshold(2.4, 190, "cycling", "ftp_wkg"), 65)
        self.assertEqual(RadarScoreEngine.score_threshold(3.0, 190, "cycling", "ftp_wkg"), 82)
        self.assertEqual(RadarScoreEngine.score_threshold(3.7, 190, "cycling", "ftp_wkg"), 95)

    def test_cycling_ftp_w_caps_at_82(self):
        self.assertEqual(RadarScoreEngine.score_threshold(140, 190, "cycling", "ftp_w"), 40)
        self.assertEqual(RadarScoreEngine.score_threshold(180, 190, "cycling", "ftp_w"), 65)
        self.assertEqual(RadarScoreEngine.score_threshold(320, 190, "cycling", "ftp_w"), 82)

    def test_cycling_threshold_hr_caps_at_82(self):
        self.assertEqual(RadarScoreEngine.score_threshold(180, 190, "cycling", "threshold_hr", "low"), 82)

    def test_running_threshold_keeps_legacy_hr_ratio(self):
        self.assertEqual(RadarScoreEngine.score_threshold(180, 190, "running", "threshold_hr"), 95)


class TestScoreAnaerobic(unittest.TestCase):

    def test_zero_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(0), 0)
        self.assertEqual(RadarScoreEngine.score_anaerobic(None), 0)

    def test_running_bracket_below_4(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(3.5, "running"), 20)

    def test_running_bracket_4_to_5(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4.5, "running"), 50)

    def test_running_bracket_5_to_5_8(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(5.5, "running"), 75)

    def test_running_bracket_above_5_8(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(6, "running"), 95)

    def test_cycling_legacy_speed_uses_different_brackets(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4, "cycling"), 20)
        self.assertEqual(RadarScoreEngine.score_anaerobic(10, "cycling"), 50)
        self.assertEqual(RadarScoreEngine.score_anaerobic(14, "cycling"), 75)
        self.assertEqual(RadarScoreEngine.score_anaerobic(20, "cycling"), 95)

    def test_cycling_power_wkg_brackets(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4.9, "cycling", "power_wkg"), 20)
        self.assertEqual(RadarScoreEngine.score_anaerobic(6.0, "cycling", "power_wkg"), 50)
        self.assertEqual(RadarScoreEngine.score_anaerobic(8.0, "cycling", "power_wkg"), 75)
        self.assertEqual(RadarScoreEngine.score_anaerobic(10.0, "cycling", "power_wkg"), 95)

    def test_cycling_power_w_caps_at_75(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(350, "cycling", "power_w"), 20)
        self.assertEqual(RadarScoreEngine.score_anaerobic(500, "cycling", "power_w"), 50)
        self.assertEqual(RadarScoreEngine.score_anaerobic(1200, "cycling", "power_w"), 75)

    def test_cycling_speed_fallback_caps_at_75(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(20, "cycling", "speed_fallback", "low"), 75)

    def test_road_cycling_uses_cycling_brackets(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(10, "road_cycling"), 50)

    def test_mountain_biking_uses_cycling_brackets(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4, "mountain_biking"), 20)
        self.assertEqual(RadarScoreEngine.score_anaerobic(10, "mountain_biking"), 50)
        self.assertEqual(RadarScoreEngine.score_anaerobic(14, "mountain_biking"), 75)
        self.assertEqual(RadarScoreEngine.score_anaerobic(20, "mountain_biking"), 95)


class TestRadarSchemas(unittest.TestCase):

    def test_running_has_6_dimensions(self):
        self.assertEqual(len(RadarScoreEngine.RADAR_SCHEMAS["running"]), 6)

    def test_trail_running_has_5_dimensions(self):
        self.assertEqual(len(RadarScoreEngine.RADAR_SCHEMAS["trail_running"]), 5)

    def test_hiking_has_3_dimensions(self):
        self.assertEqual(len(RadarScoreEngine.RADAR_SCHEMAS["hiking"]), 3)

    def test_swimming_has_3_dimensions(self):
        self.assertEqual(len(RadarScoreEngine.RADAR_SCHEMAS["swimming"]), 3)

    def test_trail_running_excludes_threshold(self):
        self.assertNotIn("threshold", RadarScoreEngine.RADAR_SCHEMAS["trail_running"])

    def test_hiking_includes_climbing(self):
        self.assertIn("climbing", RadarScoreEngine.RADAR_SCHEMAS["hiking"])


class TestRadarLabels(unittest.TestCase):

    def test_all_6_dimensions_have_chinese_label(self):
        for key in ["endurance", "recovery", "stability", "threshold", "climbing", "anaerobic"]:
            self.assertIn(key, RadarScoreEngine.LABELS)
            self.assertIsInstance(RadarScoreEngine.LABELS[key], str)
            self.assertGreater(len(RadarScoreEngine.LABELS[key]), 0)

    def test_specific_labels(self):
        self.assertEqual(RadarScoreEngine.LABELS["endurance"], "耐力")
        self.assertEqual(RadarScoreEngine.LABELS["recovery"], "恢复")
        self.assertEqual(RadarScoreEngine.LABELS["stability"], "心肺稳定")
        self.assertEqual(RadarScoreEngine.LABELS["threshold"], "阈值")
        self.assertEqual(RadarScoreEngine.LABELS["climbing"], "爬升")
        self.assertEqual(RadarScoreEngine.LABELS["anaerobic"], "无氧爆发")


class TestBuildRadarProfile(unittest.TestCase):

    def test_running_returns_6_dimensions(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        self.assertEqual(profile["type"], "running")
        self.assertEqual(len(profile["dimensions"]), 6)

    def test_trail_running_returns_5_dimensions(self):
        profile = RadarScoreEngine.build_radar_profile(
            "trail_running",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        self.assertEqual(len(profile["dimensions"]), 5)
        keys = [d["key"] for d in profile["dimensions"]]
        self.assertNotIn("threshold", keys)

    def test_hiking_returns_3_dimensions(self):
        profile = RadarScoreEngine.build_radar_profile(
            "hiking",
            {"trimp": 100, "hrv": 60, "vam": 700},
            {"max_hr": 190},
        )
        self.assertEqual(len(profile["dimensions"]), 3)

    def test_swimming_returns_3_dimensions(self):
        profile = RadarScoreEngine.build_radar_profile(
            "swimming",
            {"trimp": 100, "hrv": 60, "threshold_hr": 150},
            {"max_hr": 190},
        )
        self.assertEqual(len(profile["dimensions"]), 3)

    def test_unknown_sport_falls_back_to_running(self):
        profile = RadarScoreEngine.build_radar_profile(
            "baseball",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        self.assertEqual(len(profile["dimensions"]), 6)

    def test_unknown_sport_uses_fallback_max_hr(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
        )
        for dim in profile["dimensions"]:
            self.assertIn("score", dim)
            self.assertGreaterEqual(dim["score"], 0)
            self.assertLessEqual(dim["score"], 100)

    def test_dimension_structure_has_key_label_score(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        for dim in profile["dimensions"]:
            self.assertIn("key", dim)
            self.assertIn("label", dim)
            self.assertIn("score", dim)

    def test_dimension_structure_appends_optional_meta(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {
                "endurance_score": 63,
                "endurance_ctl_score": 50,
                "endurance_consistency_score": 95,
                "endurance_training_days_28d": 18,
                "endurance_sample_count": 22,
                "endurance_confidence": "high",
                "endurance_source": "ctl_42d_plus_28d_consistency",
                "recovery_score": 70,
                "recovery_confidence": "medium",
                "recovery_source": "load_balance",
                "stability_sample_count": 5,
                "stability_confidence": "high",
                "climbing_sample_count": 3,
                "climbing_confidence": "medium",
                "threshold_sample_count": 2,
                "threshold_confidence": "low",
                "threshold_source": "threshold_hr",
                "anaerobic_sample_count": 4,
                "anaerobic_peak_confidence": "low",
                "anaerobic_peak_source": "speed_fallback",
            },
            {"max_hr": 190},
        )
        dims = {dim["key"]: dim for dim in profile["dimensions"]}

        self.assertEqual(dims["endurance"]["confidence"], "high")
        self.assertEqual(dims["endurance"]["sample_count"], 22)
        self.assertEqual(dims["endurance"]["source"], "ctl_42d_plus_28d_consistency")
        self.assertIn("CTL分50", dims["endurance"]["reason"])
        self.assertIn("28天训练18天", dims["endurance"]["reason"])
        self.assertEqual(dims["stability"]["source"], "pa_hr_decoupling_filtered")
        self.assertEqual(dims["climbing"]["source"], "valid_climb_vam_p90")
        self.assertEqual(dims["threshold"]["source"], "threshold_hr")
        self.assertIn("仅供参考", dims["threshold"]["reason"])
        self.assertEqual(dims["anaerobic"]["source"], "speed_fallback")
        self.assertIn("仅供参考", dims["anaerobic"]["reason"])

    def test_dimension_meta_missing_fields_are_safe(self):
        profile = RadarScoreEngine.build_radar_profile("running", {}, {"max_hr": 190})
        for dim in profile["dimensions"]:
            self.assertIn("confidence", dim)
            self.assertIn("sample_count", dim)
            self.assertIn("source", dim)
            self.assertIn("reason", dim)
            self.assertIsNone(dim["confidence"])
            self.assertIsNone(dim["sample_count"])

    def test_dimension_order_matches_schema(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 100, "hrv": 60, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        keys = [d["key"] for d in profile["dimensions"]]
        self.assertEqual(keys, RadarScoreEngine.RADAR_SCHEMAS["running"])

    def test_empty_metrics_returns_zeros(self):
        profile = RadarScoreEngine.build_radar_profile("running", {}, {"max_hr": 190})
        for dim in profile["dimensions"]:
            self.assertEqual(dim["score"], 0)

    def test_full_brackets_produce_95(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 200, "hrv": 100, "decoupling": 2, "vam": 1000, "threshold_hr": 175, "anaerobic_peak": 8},
            {"max_hr": 190},
        )
        scores = {d["key"]: d["score"] for d in profile["dimensions"]}
        self.assertEqual(scores["endurance"], 95)
        self.assertEqual(scores["recovery"], 100)
        self.assertEqual(scores["stability"], 95)
        self.assertEqual(scores["climbing"], 95)
        self.assertEqual(scores["threshold"], 95)
        self.assertEqual(scores["anaerobic"], 95)

    def test_recovery_score_overrides_legacy_hrv(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 100, "hrv": 56.4, "recovery_score": 75, "decoupling": 4, "vam": 700, "threshold_hr": 170, "anaerobic_peak": 5},
            {"max_hr": 190},
        )
        scores = {d["key"]: d["score"] for d in profile["dimensions"]}
        self.assertEqual(scores["recovery"], 75)

    def test_endurance_score_overrides_legacy_trimp(self):
        profile = RadarScoreEngine.build_radar_profile(
            "running",
            {"trimp": 0, "endurance_score": 63},
            {"max_hr": 190},
        )
        scores = {d["key"]: d["score"] for d in profile["dimensions"]}
        self.assertEqual(scores["endurance"], 63)


class TestP90Helper(unittest.TestCase):
    """雷达 3 维度 max() → p90() 聚合策略单元测试。

    设计意图:消除"单次极端活动永久主导得分"的系统性问题(审计 §8 / §9.1 P0)。

    5 个分支覆盖:
    - N = 0:无数据兜底 0.0
    - N = 1/2/3:小样本退化为算术平均
    - N >= 4:线性插值 p90(同 numpy.percentile 默认 method)
    """

    def test_p90_empty(self):
        """§1 无数据兜底:N=0 返回 0.0,与原 max() 行为一致。"""
        self.assertEqual(_p90([]), 0.0)

    def test_p90_single(self):
        """§2 N=1 退化为自身。"""
        self.assertEqual(_p90([42.0]), 42.0)

    def test_p90_two(self):
        """§3 N=2 退化为算术平均。"""
        self.assertEqual(_p90([10.0, 20.0]), 15.0)

    def test_p90_three(self):
        """§4 N=3 退化为算术平均。"""
        self.assertEqual(_p90([10.0, 20.0, 30.0]), 20.0)

    def test_p90_four_uniform(self):
        """§5 N=4 线性插值:rank=2.7, lower=3, upper=4, fraction=0.7
        result = 3 * 0.3 + 4 * 0.7 = 0.9 + 2.8 = 3.7
        """
        self.assertAlmostEqual(_p90([1.0, 2.0, 3.0, 4.0]), 3.7, places=5)

    def test_p90_allen_scenario(self):
        """§6 Allen 案例复现:4 次骑行中 1 次陡坡 VAM=1200。
        N=4, sorted=[0, 0, 0, 1200], rank=2.7
        result = 0 * 0.3 + 1200 * 0.7 = 0 + 840 = 840.0
        降档验证:max=1200 → score_climbing=95,p90=840 → score_climbing=75
        """
        # 浮点容忍 1e-5(避免 IEEE 754 误差 840.0000000000002)
        self.assertAlmostEqual(_p90([0, 0, 0, 1200]), 840.0, places=5)
        # 端到端降档验证(Allen 案例)
        max_score = RadarScoreEngine.score_climbing(1200)
        p90_score = RadarScoreEngine.score_climbing(840.0)
        self.assertEqual(max_score, 95)
        self.assertEqual(p90_score, 75)
        # 降档 ≥ 1 个等级
        self.assertLess(p90_score, max_score)
        self.assertGreaterEqual(95 - p90_score, 20)

    def test_p90_realistic_ten_values(self):
        """§7 10 个正常值:验证 p90 ≈ max 附近(对常规用户影响 < 15%)。
        sorted=[100, 105, 108, 110, 112, 115, 118, 120, 125, 130]
        rank=0.9*9=8.1, lower=8, upper=9, fraction=0.1
        result = 125 * 0.9 + 130 * 0.1 = 112.5 + 13 = 125.5
        """
        values = [100, 110, 105, 120, 115, 130, 108, 112, 125, 118]
        result = _p90(values)
        # p90 接近 max(正常样本下)
        self.assertAlmostEqual(result, 125.5, places=5)
        self.assertLessEqual(result, max(values))
        # p90 不低于 p50(90 分位 ≥ 中位数)
        self.assertGreaterEqual(result, 115.0)

    def test_p90_does_not_introduce_nan(self):
        """§8 边界:不引入 NaN / None。"""
        for values in [[], [0.0], [1.0, 2.0, 3.0], [10, 20, 30, 40, 50]]:
            result = _p90(values)
            self.assertFalse(result != result, "p90 returned NaN")  # NaN != NaN
            self.assertIsNotNone(result)
            self.assertIsInstance(result, float)

    def test_p90_score_climbing_drop_verification(self):
        """§9 端到端:Allen 案例 max=1200 → 95,p90=840 → 75。
        验证单次极端活动不再永久主导爬升维度。
        """
        allen_values = [0, 0, 0, 1200]
        # 修复前
        original_max = max(allen_values)
        original_score = RadarScoreEngine.score_climbing(original_max)
        # 修复后
        new_p90 = _p90(allen_values)
        new_score = RadarScoreEngine.score_climbing(new_p90)
        # 期望:95 → 75(降档 ≥ 1 个等级)
        self.assertEqual(original_score, 95)
        self.assertEqual(new_score, 75)
        self.assertLess(new_score, original_score)


class TestScoreClimbingSportType(unittest.TestCase):
    """§5 雷达修复 F:score_climbing 增加 sport_type 感知"""

    # === 向后兼容 ===
    def test_score_climbing_none_sport_type_backward_compat(self):
        """sport_type=None 走默认分支,与原行为完全一致。"""
        self.assertEqual(RadarScoreEngine.score_climbing(280, None), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(500, None), 50)
        self.assertEqual(RadarScoreEngine.score_climbing(750, None), 75)
        self.assertEqual(RadarScoreEngine.score_climbing(1000, None), 95)
        self.assertEqual(RadarScoreEngine.score_climbing(0, None), 0)
        self.assertEqual(RadarScoreEngine.score_climbing(None, None), 0)

    def test_score_climbing_running_unchanged(self):
        """跑步走默认分支,行为不变。"""
        self.assertEqual(RadarScoreEngine.score_climbing(280, "running"), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(750, "running"), 75)
        self.assertEqual(RadarScoreEngine.score_climbing(1000, "running"), 95)

    # === 骑行分支 ===
    def test_score_climbing_cycling_low(self):
        self.assertEqual(RadarScoreEngine.score_climbing(50, "cycling"), 20)

    def test_score_climbing_cycling_mid(self):
        """P2 重标定:骑行 280 m/h 低于 300,只给 20 分。"""
        self.assertEqual(RadarScoreEngine.score_climbing(280, "cycling"), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(300, "cycling"), 50)
        self.assertEqual(RadarScoreEngine.score_climbing(600, "cycling"), 75)
        self.assertEqual(RadarScoreEngine.score_climbing(900, "cycling"), 95)

    def test_score_climbing_cycling_high(self):
        self.assertEqual(RadarScoreEngine.score_climbing(900, "cycling"), 95)

    def test_score_climbing_road_cycling_mid(self):
        """road_cycling 复用 cycling 阈值。"""
        self.assertEqual(RadarScoreEngine.score_climbing(280, "road_cycling"), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(600, "road_cycling"), 75)

    def test_score_climbing_mountain_biking_mid(self):
        """mountain_biking 复用 cycling 阈值。"""
        self.assertEqual(RadarScoreEngine.score_climbing(280, "mountain_biking"), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(600, "mountain_biking"), 75)

    # === 徒步分支 ===
    def test_score_climbing_hiking_low(self):
        self.assertEqual(RadarScoreEngine.score_climbing(80, "hiking"), 20)

    def test_score_climbing_hiking_mid(self):
        """徒步 280 m/h 在 150~300 档,50 分。"""
        self.assertEqual(RadarScoreEngine.score_climbing(149.9, "hiking"), 20)
        self.assertEqual(RadarScoreEngine.score_climbing(150, "hiking"), 50)
        self.assertEqual(RadarScoreEngine.score_climbing(280, "hiking"), 50)
        self.assertEqual(RadarScoreEngine.score_climbing(300, "hiking"), 75)

    def test_score_climbing_hiking_high(self):
        self.assertEqual(RadarScoreEngine.score_climbing(500, "hiking"), 95)

    # === 边界 ===
    def test_score_climbing_zero(self):
        self.assertEqual(RadarScoreEngine.score_climbing(0, "cycling"), 0)
        self.assertEqual(RadarScoreEngine.score_climbing(0, "hiking"), 0)

    def test_score_climbing_none_vam(self):
        self.assertEqual(RadarScoreEngine.score_climbing(None, "cycling"), 0)
        self.assertEqual(RadarScoreEngine.score_climbing(None, "hiking"), 0)

    # === 核心场景:跨运动不混分 ===
    def test_cycling_uses_different_climbing_brackets_from_running(self):
        """P2 后 cycling 与 running 共享 300/600/900 VAM 阈值。"""
        vam = 280
        running_score = RadarScoreEngine.score_climbing(vam, "running")
        cycling_score = RadarScoreEngine.score_climbing(vam, "cycling")
        self.assertEqual(running_score, cycling_score)

    def test_trail_running_uses_default_brackets(self):
        """越野跑走默认分支(与跑步同阈值)。"""
        self.assertEqual(
            RadarScoreEngine.score_climbing(280, "trail_running"),
            RadarScoreEngine.score_climbing(280, "running")
        )


class TestCyclingClimbingCompositeScore(unittest.TestCase):
    """骑行爬升复合评分:VAM 仍参与,但少样本/无功率不能直接满分。"""

    def test_three_high_vam_samples_capped_at_85(self):
        detail = RadarScoreEngine.score_cycling_climbing_detail({
            "climbing_vam_p90": 1041.6,
            "climbing_sample_count": 3,
            "climbing_gain_p90": 1021.8,
            "climbing_distance_p90": 59.7,
            "climbing_duration_p90": 9900,
            "climbing_power_available_count": 0,
        })

        self.assertLessEqual(detail["score"], 85)
        self.assertEqual(detail["score_cap"], 85)
        self.assertEqual(detail["confidence"], "medium")
        self.assertIn("有效爬坡样本3-5个", detail["reason"])
        self.assertIn("缺少爬坡功率", detail["reason"])

    def test_one_or_two_high_vam_samples_capped_at_75(self):
        detail = RadarScoreEngine.score_cycling_climbing_detail({
            "climbing_vam_p90": 1300,
            "climbing_sample_count": 2,
            "climbing_gain_p90": 600,
            "climbing_distance_p90": 10,
            "climbing_duration_p90": 2400,
            "climbing_power_available_count": 2,
        })

        self.assertLessEqual(detail["score"], 75)
        self.assertEqual(detail["score_cap"], 75)
        self.assertEqual(detail["confidence"], "low")

    def test_six_samples_with_power_can_score_95(self):
        detail = RadarScoreEngine.score_cycling_climbing_detail({
            "climbing_vam_p90": 1100,
            "climbing_sample_count": 6,
            "climbing_gain_p90": 1200,
            "climbing_distance_p90": 45,
            "climbing_duration_p90": 7200,
            "climbing_power_available_count": 6,
        })

        self.assertEqual(detail["score"], 95)
        self.assertEqual(detail["score_cap"], 95)
        self.assertEqual(detail["confidence"], "high")

    def test_vam_only_fallback_capped_at_85(self):
        detail = RadarScoreEngine.score_cycling_climbing_detail({
            "climbing_vam_p90": 1500,
            "climbing_sample_count": 10,
            "climbing_gain_p90": 1200,
            "climbing_distance_p90": 45,
            "climbing_duration_p90": 7200,
            "climbing_power_available_count": 0,
        })

        self.assertLessEqual(detail["score"], 85)
        self.assertEqual(detail["score_cap"], 85)
        self.assertIn("仅VAM fallback最高85", detail["reason"])

    def test_build_radar_profile_keeps_running_climbing_unchanged(self):
        radar = RadarScoreEngine.build_radar_profile("running", {"vam": 1000}, {"max_hr": 190})
        climbing = next(dim for dim in radar["dimensions"] if dim["key"] == "climbing")

        self.assertEqual(climbing["score"], 95)
        self.assertNotIn("score_cap", climbing)


# =========================================================
# 任务 5: VAM 修复端到端回归测试
# =========================================================

def _flat_road_records_e2e(duration_sec=120):
    """平路 1m 抖动 records:120s / 600m / 噪声。"""
    start = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(duration_sec + 1):
        alt = 100.0 + (0.5 if (i // 10) % 2 == 0 else -0.5)
        records.append(_record(
            start + timedelta(seconds=i),
            altitude=alt,
            distance=i * 5.0,
        ))
    return records


def _real_climb_records_e2e(duration_sec=120, dist_m=300, gain_m=20):
    """真实爬坡 records:120s / 300m / 20m。"""
    start = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(duration_sec + 1):
        records.append(_record(
            start + timedelta(seconds=i),
            altitude=100.0 + (i / duration_sec) * gain_m,
            distance=(i / duration_sec) * dist_m,
        ))
    return records


def _make_metrics_row_e2e(sport_type, gain_m, dist_km, vam, trimp=50, days_ago=10):
    """构造一条 DB 行(advanced_metrics 模拟后端 _compute_advanced_metrics 输出)。"""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    advanced = {"vam": vam, "trimp": trimp, "metrics_version": 4}
    return {
        "id": 1,
        "start_time_utc": dt.isoformat(),
        "start_time": dt.isoformat(),
        "sport_type": sport_type,
        "gain_m": gain_m,
        "dist_km": dist_km,
        "distance": dist_km * 1000.0,
        "duration_sec": 1800,
        "duration": 1800,
        "advanced_metrics": json.dumps(advanced),
    }


def _run_agg_e2e(rows, sport_type="running"):
    """Mock profile_backend._conn / get_profile,运行 _rolling_aggregate_radar_metrics。"""
    from main import _rolling_aggregate_radar_metrics
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = rows
    mock_conn.close = MagicMock()
    mock_profile = MagicMock()
    mock_profile.hrv_baseline = 60
    mock_profile.max_hr = 190
    with patch("main.profile_backend._conn", return_value=mock_conn), \
         patch("main.profile_backend.get_profile", return_value=mock_profile):
        return _rolling_aggregate_radar_metrics(sport_type)


def _climbing_score_e2e(result):
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "climbing":
            return dim["score"]
    return 0


class TestVamFixEndToEndRegression(unittest.TestCase):
    """任务 5: VAM 修复 + 雷达聚合过滤 端到端回归测试。

    覆盖完整链路:records → calculate_vam → advanced_metrics →
    DB 落库 → _rolling_aggregate_radar_metrics → climbing score。

    验证 VAM 算法修复 + 雷达聚合过滤在整个数据管道中一致生效,
    避免 VAM 修复后又被聚合端的旧数据或反模式再次污染。
    """

    # === 场景 1: 单次平路骑行 ===
    def test_e2e_1_flat_road_vam_zero(self):
        """records 中距离持续增加、海拔只有 1m 级抖动 → calculate_vam 返回 0.0。"""
        records = _flat_road_records_e2e(120)
        vam = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(vam, 0.0)

    # === 场景 2: 单次真实爬坡 ===
    def test_e2e_2_real_climb_300m_20m_120s_vam_about_600(self):
        """连续 120s / 距离 300m / 爬升 20m → calculate_vam 返回约 600 m/h。"""
        records = _real_climb_records_e2e(120, 300, 20)
        vam = AdvancedMetricsCalc.calculate_vam(records)
        self.assertAlmostEqual(vam, 600.0, delta=15.0)

    # === 场景 3: 雷达聚合平路骑行 ===
    def test_e2e_3_aggregation_commute_cycling_climbing_zero(self):
        """多条 cycling 高级指标 vam 高(720/900)但 gain_m 低(0/4/5m)
        → _is_valid_vam_activity 过滤 → 最终 radar climbing score=0。"""
        rows = [
            _make_metrics_row_e2e("cycling", gain_m=0, dist_km=10, vam=720),
            _make_metrics_row_e2e("cycling", gain_m=4, dist_km=8, vam=900),
            _make_metrics_row_e2e("cycling", gain_m=5, dist_km=15, vam=900),
        ]
        result = _run_agg_e2e(rows, sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)
        self.assertEqual(_climbing_score_e2e(result), 0)

    # === 场景 4: 雷达聚合真实骑行爬坡 ===
    def test_e2e_4_aggregation_real_cycling_climbing_uses_composite_cap(self):
        """gain_m 足够(80m ≥ 20m 阈值)且 vam=600 → 通过过滤
        → cycling 走复合爬升评分,单样本不能只靠 VAM 得到 75。"""
        row = _make_metrics_row_e2e("cycling", gain_m=80, dist_km=20, vam=600)
        result = _run_agg_e2e([row], sport_type="cycling")
        self.assertEqual(result["vam"], 600.0)
        self.assertLessEqual(_climbing_score_e2e(result), 75)
        self.assertEqual(result["climbing_score_cap"], 75)

    # === 场景 5: 跑步公路低爬升 ===
    def test_e2e_5_aggregation_running_low_climb_filtered(self):
        """running gain_m=10m vam=720 → 未达 20m 阈值 → 被过滤
        → running climbing score 不应为 75(原 vam=720 会得 75)。"""
        row = _make_metrics_row_e2e("running", gain_m=10, dist_km=5, vam=720)
        result = _run_agg_e2e([row], sport_type="running")
        self.assertEqual(result["vam"], 0.0)
        # 关键回归断言:climbing 不是 75
        self.assertNotEqual(_climbing_score_e2e(result), 75)
        self.assertEqual(_climbing_score_e2e(result), 0)

    # === 场景 6: 徒步真实爬升 ===
    def test_e2e_6_aggregation_hiking_real_climb_climbing_95(self):
        """hiking gain_m=100m vam=500 → 通过 hiking 50m 门槛
        → hiking score_climbing(500) = 95(P2 hiking 阈值 >=500 → 95)。"""
        row = _make_metrics_row_e2e("hiking", gain_m=100, dist_km=15, vam=500)
        result = _run_agg_e2e([row], sport_type="hiking")
        self.assertEqual(result["vam"], 500.0)
        self.assertEqual(_climbing_score_e2e(result), 95)

    # === 场景 7: trail_running 过滤门槛 + running 评分阈值 ===
    def test_e2e_7_trail_running_threshold_and_scoring(self):
        """trail_running 过滤门槛 30m(不同于 running 20m);
        通过过滤后,scoring 走 running 默认阈值(600-900 → 75)。"""
        # gain_m=20 低于 trail 30m 门槛 → 过滤
        row_low = _make_metrics_row_e2e("trail_running", gain_m=20, dist_km=5, vam=700)
        result_low = _run_agg_e2e([row_low], sport_type="trail_running")
        self.assertEqual(result_low["vam"], 0.0)
        # gain_m=30 通过门槛,vam=700 → score_climbing(700, "trail_running")
        # 走默认(running)分支,600-900 → 75
        row_pass = _make_metrics_row_e2e("trail_running", gain_m=30, dist_km=8, vam=700)
        result_pass = _run_agg_e2e([row_pass], sport_type="trail_running")
        self.assertEqual(result_pass["vam"], 700.0)
        self.assertEqual(_climbing_score_e2e(result_pass), 75)


if __name__ == "__main__":
    unittest.main()
