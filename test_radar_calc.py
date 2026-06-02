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
import unittest
from datetime import datetime, timedelta, timezone

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

    def test_empty_records_returns_zero(self):
        self.assertEqual(AdvancedMetricsCalc.calculate_vam([]), 0.0)

    def test_single_record_returns_zero(self):
        records = [_record(_ts(2026, 1, 1), altitude=100, distance=0)]
        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

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

    def test_gradient_below_3pct_excluded(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=100.2, distance=10),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    def test_gradient_above_3pct_counted(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=100.5, distance=10),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertGreater(result, 0.0)

    def test_anomalous_rate_5ms_filtered(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=106, distance=10),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 0.0)

    def test_time_gap_gt_300s_skipped(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=100, distance=0),
            _record(start + timedelta(seconds=1), altitude=101, distance=10),
            _record(start + timedelta(seconds=400), altitude=200, distance=20),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertGreater(result, 0.0)

    def test_vam_formula_uses_3600(self):
        start = _ts(2026, 1, 1)
        records = [
            _record(start, altitude=0, distance=0),
            _record(start + timedelta(seconds=60), altitude=10, distance=200),
        ]
        result = AdvancedMetricsCalc.calculate_vam(records)
        self.assertEqual(result, 600.0)

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

    def test_zero_speed_counted(self):
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


class TestScoreAnaerobic(unittest.TestCase):

    def test_zero_returns_0(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(0), 0)
        self.assertEqual(RadarScoreEngine.score_anaerobic(None), 0)

    def test_running_bracket_below_3(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(2.5, "running"), 20)

    def test_running_bracket_3_to_5(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4, "running"), 50)

    def test_running_bracket_5_to_7(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(6, "running"), 75)

    def test_running_bracket_above_7(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(8, "running"), 95)

    def test_cycling_uses_different_brackets(self):
        self.assertEqual(RadarScoreEngine.score_anaerobic(4, "cycling"), 20)
        self.assertEqual(RadarScoreEngine.score_anaerobic(10, "cycling"), 50)
        self.assertEqual(RadarScoreEngine.score_anaerobic(14, "cycling"), 75)
        self.assertEqual(RadarScoreEngine.score_anaerobic(20, "cycling"), 95)

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

    def test_strength_has_2_dimensions(self):
        self.assertEqual(len(RadarScoreEngine.RADAR_SCHEMAS["strength"]), 2)

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

    def test_strength_returns_2_dimensions(self):
        profile = RadarScoreEngine.build_radar_profile(
            "strength",
            {"hrv": 60, "anaerobic_peak": 3},
            {"max_hr": 190},
        )
        self.assertEqual(len(profile["dimensions"]), 2)

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


if __name__ == "__main__":
    unittest.main()
