"""
雷达 90 天聚合 VAM 可信度过滤单元测试。

任务 2 修复:即使单次 calculate_vam 已修复,历史 advanced_metrics 中
可能残留 gain_m=0/4/5m 的通勤骑行旧 VAM。本测试覆盖 _rolling_aggregate_radar_metrics
中 _is_valid_vam_activity 过滤逻辑,确保通勤旧 VAM 不再污染雷达图。

遵循 fit-arch-contrac 契约:
- 不依赖真实 DB(用 unittest.mock 隔离)
- 不依赖 AI/LLM
- 不写回 canonical 层
- 不使用 shadow_diff
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch


def _ts_iso(days_ago: int = 10) -> str:
    """构造一个 N 天前的 UTC ISO 时间字符串。"""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _make_row(
    *,
    sport_type: str,
    gain_m: float = 0.0,
    dist_km: float = 5.0,
    distance: Optional[float] = None,
    duration_sec: int = 1800,
    vam: float = 0.0,
    trimp: float = 50.0,
    threshold_hr: Optional[float] = None,
    threshold_source: Optional[str] = None,
    threshold_confidence: Optional[str] = None,
    threshold_power: Optional[float] = None,
    threshold_wkg: Optional[float] = None,
    anaerobic_peak: Optional[float] = None,
    anaerobic_peak_source: Optional[str] = None,
    anaerobic_peak_confidence: Optional[str] = None,
    decoupling: Optional[float] = None,
    is_intermittent: bool = False,
    paused_time: Optional[float] = None,
    moving_time: Optional[float] = None,
    elapsed_time: Optional[float] = None,
    workout_type: Optional[str] = None,
    days_ago: int = 10,
    metrics_version: Optional[int] = None,
) -> dict:
    """构造一条模拟活动行(对齐 _rolling_aggregate_radar_metrics SQL 列)。"""
    from main import CURRENT_METRICS_VERSION

    metrics = {"vam": vam, "trimp": trimp}
    metrics["metrics_version"] = CURRENT_METRICS_VERSION if metrics_version is None else metrics_version
    if threshold_hr is not None:
        metrics["threshold_hr"] = threshold_hr
    if threshold_source is not None:
        metrics["threshold_source"] = threshold_source
    if threshold_confidence is not None:
        metrics["threshold_confidence"] = threshold_confidence
    if threshold_power is not None:
        metrics["threshold_power"] = threshold_power
    if threshold_wkg is not None:
        metrics["threshold_wkg"] = threshold_wkg
    if anaerobic_peak is not None:
        metrics["anaerobic_peak"] = anaerobic_peak
    if anaerobic_peak_source is not None:
        metrics["anaerobic_peak_source"] = anaerobic_peak_source
    if anaerobic_peak_confidence is not None:
        metrics["anaerobic_peak_confidence"] = anaerobic_peak_confidence
    if decoupling is not None:
        metrics["decoupling"] = decoupling
    if is_intermittent:
        metrics["is_intermittent"] = True
    if paused_time is not None:
        metrics["paused_time"] = paused_time
    if moving_time is not None:
        metrics["moving_time"] = moving_time
    if elapsed_time is not None:
        metrics["elapsed_time"] = elapsed_time
    if workout_type is not None:
        metrics["workout_type"] = workout_type
    return {
        "id": 1,
        "start_time_utc": _ts_iso(days_ago),
        "start_time": _ts_iso(days_ago),
        "sport_type": sport_type,
        "gain_m": gain_m,
        "dist_km": dist_km,
        "distance": distance,
        "duration_sec": duration_sec,
        "duration": duration_sec,
        "is_intermittent": is_intermittent,
        "advanced_metrics": json.dumps(metrics),
    }


def _run_aggregation(rows: list[dict], sport_type: str = "running") -> dict:
    """运行 _rolling_aggregate_radar_metrics,使用 mock 隔离 DB / profile。"""
    # 延迟导入:确保 main.py 模块副作用在 mock 之后生效
    from main import _rolling_aggregate_radar_metrics

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = rows
    mock_conn.close = MagicMock()

    mock_profile = MagicMock()
    mock_profile.hrv_baseline = 60
    mock_profile.max_hr = 190
    mock_profile.to_dict.return_value = {"hrv_baseline": 60, "max_hr": 190}

    with patch("main.profile_backend._conn", return_value=mock_conn), \
         patch("main.profile_backend.get_profile", return_value=mock_profile):
        return _rolling_aggregate_radar_metrics(sport_type)


def _climbing_score(result: dict) -> int:
    """从 radar.dimensions 中取出 climbing 维度得分。"""
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "climbing":
            return dim["score"]
    return 0


def _anaerobic_score(result: dict) -> int:
    """从 radar.dimensions 中取出 anaerobic 维度得分。"""
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "anaerobic":
            return dim["score"]
    return 0


def _threshold_score(result: dict) -> int:
    """从 radar.dimensions 中取出 threshold 维度得分。"""
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "threshold":
            return dim["score"]
    return 0


def _endurance_score(result: dict) -> int:
    """从 radar.dimensions 中取出 endurance 维度得分。"""
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "endurance":
            return dim["score"]
    return 0


def _hiking_has_climbing_dim(result: dict) -> bool:
    """hiking schema 含 climbing 维度(用于确认维度未丢)。"""
    keys = [d["key"] for d in result["radar"]["dimensions"]]
    return "climbing" in keys


class TestVamCredibilityFilter(unittest.TestCase):
    """任务 2: 雷达 90 天聚合 VAM 可信度过滤。"""

    # === 1. 通勤骑行旧 VAM 应被过滤 ===

    def test_commute_cycling_zeroes_vam(self):
        """gain_m=0/4/5m 的通勤骑行,vam=720/900 应被过滤 → vam=0, climbing=0。"""
        rows = [
            _make_row(sport_type="cycling", gain_m=0, dist_km=10, vam=720),
            _make_row(sport_type="cycling", gain_m=4, dist_km=8, vam=900),
            _make_row(sport_type="cycling", gain_m=5, dist_km=15, vam=900),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)
        self.assertEqual(_climbing_score(result), 0)

    def test_commute_cycling_short_distance_filtered(self):
        """gain_m=80m 但距离 < 1km 也应过滤。"""
        rows = [_make_row(sport_type="cycling", gain_m=80, dist_km=0.5, vam=900)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)

    # === 2. 真实骑行 80m 爬升应进入聚合 ===

    def test_real_cycling_80m_climb_enters_aggregation(self):
        """gain_m=80m cycling 应进入聚合,但单样本复合爬升分应保守封顶。"""
        rows = [_make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=600)]
        result = _run_aggregation(rows, sport_type="cycling")
        # N=1 → _p90 退化为算术平均 = 600
        self.assertEqual(result["vam"], 600.0)
        self.assertLessEqual(_climbing_score(result), 75)
        self.assertEqual(result["climbing_score_cap"], 75)
        self.assertEqual(result["climbing_sample_count"], 1)
        self.assertEqual(result["climbing_confidence"], "low")

    def test_zero_vam_cycling_does_not_mask_real_climbs_but_sample_cap_applies(self):
        """3个高 VAM 骑行样本仍应受样本封顶约束,不能直接给 95。"""
        rows = [
            *[
                _make_row(
                    sport_type="cycling",
                    gain_m=100,
                    dist_km=12,
                    vam=0,
                )
                for _ in range(50)
            ],
            _make_row(sport_type="cycling", gain_m=473, dist_km=8.04, vam=1227.2),
            _make_row(sport_type="cycling", gain_m=251, dist_km=26.88, vam=1060.6),
            _make_row(sport_type="cycling", gain_m=1214, dist_km=67.85, vam=837.0),
        ]

        result = _run_aggregation(rows, sport_type="cycling")

        self.assertEqual(result["vam"], 1041.6)
        self.assertLessEqual(_climbing_score(result), 85)
        self.assertEqual(result["climbing_sample_count"], 3)
        self.assertEqual(result["climbing_confidence"], "medium")
        self.assertEqual(result["climbing_score_cap"], 85)
        self.assertIn("有效爬坡样本3-5个", result["climbing_reason"])
        self.assertIn("缺少爬坡功率", result["climbing_reason"])

    # === 3. running 10m 应被过滤(running 阈值 >=20m) ===

    def test_running_10m_climb_filtered(self):
        """running gain_m=10m vam=720 应被过滤(未达 20m 阈值)。"""
        rows = [_make_row(sport_type="running", gain_m=10, dist_km=5, vam=720)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["vam"], 0.0)
        self.assertEqual(_climbing_score(result), 0)

    # === 4. running 30m 应保留,climbing 按 running 阈值 ===

    def test_running_30m_climb_retained_75(self):
        """running gain_m=30m vam=750 应保留,climbing=75 (running 600-900 段)。"""
        rows = [_make_row(sport_type="running", gain_m=30, dist_km=8, vam=750)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["vam"], 750.0)
        # RadarScoreEngine.score_climbing(750, "running") = 75 (600 <= vam < 900)
        self.assertEqual(_climbing_score(result), 75)

    # === 5. hiking 阈值 (50m) 边界 ===

    def test_hiking_40m_climb_filtered(self):
        """hiking gain_m=40m 应被过滤(未达 50m hiking 阈值)。"""
        rows = [_make_row(sport_type="hiking", gain_m=40, dist_km=10, vam=400)]
        result = _run_aggregation(rows, sport_type="hiking")
        self.assertEqual(result["vam"], 0.0)

    def test_hiking_100m_climb_retained(self):
        """hiking gain_m=100m 应保留,climbing=75 (P2 hiking 300~500 档)。"""
        rows = [_make_row(sport_type="hiking", gain_m=100, dist_km=15, vam=400)]
        result = _run_aggregation(rows, sport_type="hiking")
        # vam=400 → p90(N=1) = 400
        self.assertEqual(result["vam"], 400.0)
        self.assertEqual(_climbing_score(result), 75)
        # hiking schema 仍含 climbing 维度
        self.assertTrue(_hiking_has_climbing_dim(result))


class TestVamCredibilityFilterEdgeCases(unittest.TestCase):
    """边界:缺失字段、distance 回退、road_cycling/mountain_biking 变体。"""

    def test_gain_m_missing_treated_as_zero(self):
        """gain_m 缺失(None)按 0 处理,不通过阈值。"""
        row = _make_row(sport_type="cycling", gain_m=0, dist_km=20, vam=600)
        row["gain_m"] = None
        result = _run_aggregation([row], sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)

    def test_dist_km_missing_falls_back_to_distance(self):
        """dist_km 缺失时回退 distance(米)/1000。distance=2000m → 2km → 通过。"""
        row = _make_row(sport_type="cycling", gain_m=30, dist_km=0, vam=600)
        row["dist_km"] = None
        row["distance"] = 2000.0  # 2 km
        result = _run_aggregation([row], sport_type="cycling")
        self.assertEqual(result["vam"], 600.0)

    def test_road_cycling_uses_cycling_thresholds(self):
        """road_cycling 复用 cycling 阈值(gain_m=20m 边界通过)。"""
        row = _make_row(sport_type="road_cycling", gain_m=20, dist_km=5, vam=400)
        result = _run_aggregation([row], sport_type="cycling")
        # road_cycling 在 _CYCLING_SPORT_TYPES,SQL 已 unicycle 进来;row.sport_type=road_cycling,
        # 阈值表中 road_cycling=20m,正好通过。
        self.assertEqual(result["vam"], 400.0)

    def test_mountain_biking_uses_cycling_thresholds(self):
        """mountain_biking 复用 cycling 阈值。"""
        row = _make_row(sport_type="mountain_biking", gain_m=20, dist_km=5, vam=400)
        result = _run_aggregation([row], sport_type="cycling")
        self.assertEqual(result["vam"], 400.0)

    def test_trail_running_30m_threshold(self):
        """trail_running 阈值 30m:20m 不通过,30m 通过。"""
        row_filtered = _make_row(sport_type="trail_running", gain_m=20, dist_km=5, vam=500)
        result_filtered = _run_aggregation([row_filtered], sport_type="trail_running")
        self.assertEqual(result_filtered["vam"], 0.0)

        row_passed = _make_row(sport_type="trail_running", gain_m=30, dist_km=5, vam=500)
        result_passed = _run_aggregation([row_passed], sport_type="trail_running")
        self.assertEqual(result_passed["vam"], 500.0)

    def test_age_over_90_days_excluded(self):
        """超过 90 天的活动即使真实爬坡也不进入聚合。"""
        old_row = _make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=600, days_ago=100)
        result = _run_aggregation([old_row], sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)

    def test_no_valid_vam_returns_zero(self):
        """90 天内无任何有效 VAM,返回 vam=0,climbing=0。"""
        rows = [
            _make_row(sport_type="cycling", gain_m=0, dist_km=5, vam=720),
            _make_row(sport_type="cycling", gain_m=4, dist_km=8, vam=900),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["vam"], 0.0)
        self.assertEqual(_climbing_score(result), 0)
        # API 返回结构完整(契约 §4.2)
        for key in ("ctl", "atl", "tsb", "hrv", "decoupling",
                    "recovery_score", "recovery_source", "recovery_confidence", "recovery_reasons",
                    "stability_sample_count", "stability_confidence",
                    "vam", "climbing_sample_count", "climbing_confidence",
                    "threshold_hr", "threshold_source", "threshold_confidence",
                    "threshold_sample_count", "threshold_power", "threshold_wkg",
                    "anaerobic_peak", "anaerobic_peak_source",
                    "anaerobic_peak_confidence", "anaerobic_sample_count", "radar"):
            self.assertIn(key, result)


class TestClimbingConfidence(unittest.TestCase):
    """P2:climbing 有效样本数可信度。"""

    def test_no_valid_vam_confidence_low(self):
        rows = [_make_row(sport_type="cycling", gain_m=0, dist_km=20, vam=900)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["climbing_sample_count"], 0)
        self.assertEqual(result["climbing_confidence"], "low")

    def test_one_to_two_samples_confidence_low(self):
        rows = [
            _make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=700),
            _make_row(sport_type="cycling", gain_m=90, dist_km=20, vam=800),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["climbing_sample_count"], 2)
        self.assertEqual(result["climbing_confidence"], "low")

    def test_three_to_five_samples_confidence_medium(self):
        rows = [
            _make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=700)
            for _ in range(5)
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["climbing_sample_count"], 5)
        self.assertEqual(result["climbing_confidence"], "medium")

    def test_six_samples_confidence_high(self):
        rows = [
            _make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=700)
            for _ in range(6)
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["climbing_sample_count"], 6)
        self.assertEqual(result["climbing_confidence"], "high")


class TestAnaerobicAggregation(unittest.TestCase):
    """P0:无氧爆发聚合 source 优先级与历史兼容。"""

    def test_power_wkg_takes_precedence_over_speed_fallback(self):
        rows = [
            _make_row(
                sport_type="cycling",
                anaerobic_peak=18.0,
                anaerobic_peak_source="speed_fallback",
                anaerobic_peak_confidence="low",
            ),
            _make_row(
                sport_type="cycling",
                anaerobic_peak=8.0,
                anaerobic_peak_source="power_wkg",
                anaerobic_peak_confidence="high",
            ),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["anaerobic_peak"], 8.0)
        self.assertEqual(result["anaerobic_peak_source"], "power_wkg")
        self.assertEqual(_anaerobic_score(result), 75)

    def test_speed_fallback_cycling_score_caps_at_75(self):
        rows = [
            _make_row(
                sport_type="cycling",
                anaerobic_peak=20.0,
                anaerobic_peak_source="speed_fallback",
                anaerobic_peak_confidence="low",
            )
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["anaerobic_peak_source"], "speed_fallback")
        self.assertEqual(_anaerobic_score(result), 75)

    def test_legacy_anaerobic_metrics_do_not_crash(self):
        rows = [_make_row(sport_type="cycling", anaerobic_peak=20.0)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["anaerobic_peak_source"], "legacy")
        self.assertEqual(_anaerobic_score(result), 75)


class TestRecoveryAggregation(unittest.TestCase):
    """P1:恢复维度不再直接使用 HRV baseline 绝对值。"""

    def test_baseline_only_recovery_fields_are_returned(self):
        rows = [_make_row(sport_type="running", trimp=50)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertNotEqual(result["recovery_score"], result["hrv"])
        self.assertEqual(result["recovery_source"], "load_balance")
        self.assertIn(result["recovery_confidence"], ("low", "medium"))
        self.assertIn("recovery_reasons", result)
        scores = {dim["key"]: dim["score"] for dim in result["radar"]["dimensions"]}
        self.assertEqual(scores["recovery"], result["recovery_score"])


class TestThresholdAggregation(unittest.TestCase):
    """P1:骑行阈值聚合 source 优先级与 fallback 封顶。"""

    def test_ftp_wkg_takes_precedence_over_threshold_hr(self):
        rows = [
            _make_row(
                sport_type="cycling",
                threshold_hr=180,
                threshold_source="threshold_hr",
                threshold_confidence="low",
            ),
            _make_row(
                sport_type="cycling",
                threshold_hr=150,
                threshold_source="ftp_wkg",
                threshold_confidence="high",
                threshold_wkg=3.2,
            ),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["threshold_source"], "ftp_wkg")
        self.assertEqual(result["threshold_wkg"], 3.2)
        self.assertEqual(_threshold_score(result), 82)

    def test_ftp_w_takes_precedence_over_threshold_hr_and_caps(self):
        rows = [
            _make_row(sport_type="cycling", threshold_hr=180, threshold_source="threshold_hr"),
            _make_row(sport_type="cycling", threshold_hr=150, threshold_source="ftp_w", threshold_power=320),
        ]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["threshold_source"], "ftp_w")
        self.assertEqual(result["threshold_power"], 320)
        self.assertEqual(_threshold_score(result), 82)

    def test_cycling_threshold_hr_fallback_caps_at_82(self):
        rows = [_make_row(sport_type="cycling", threshold_hr=180)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["threshold_source"], "legacy")
        self.assertEqual(_threshold_score(result), 82)


class TestStabilityAggregation(unittest.TestCase):
    """P2:心肺稳定只纳入稳定有氧活动。"""

    def test_running_45min_decoupling_enters(self):
        rows = [_make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=4)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["decoupling"], 4)
        self.assertEqual(result["stability_sample_count"], 1)
        self.assertEqual(result["stability_confidence"], "low")

    def test_running_30min_decoupling_filtered(self):
        rows = [_make_row(sport_type="running", duration_sec=1800, dist_km=6, gain_m=10, decoupling=4)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["stability_sample_count"], 0)
        self.assertEqual(result["stability_confidence"], "low")

    def test_cycling_45min_decoupling_enters(self):
        rows = [_make_row(sport_type="cycling", duration_sec=2700, dist_km=25, gain_m=100, decoupling=4)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["decoupling"], 4)
        self.assertEqual(result["stability_sample_count"], 1)

    def test_hiking_45min_decoupling_filtered(self):
        rows = [_make_row(sport_type="hiking", duration_sec=2700, dist_km=4, gain_m=100, decoupling=4)]
        result = _run_aggregation(rows, sport_type="hiking")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_hiking_90min_decoupling_enters(self):
        rows = [_make_row(sport_type="hiking", duration_sec=5400, dist_km=8, gain_m=300, decoupling=4)]
        result = _run_aggregation(rows, sport_type="hiking")
        self.assertEqual(result["stability_sample_count"], 1)
        self.assertEqual(result["decoupling"], 4)

    def test_high_climb_density_filtered(self):
        rows = [_make_row(sport_type="cycling", duration_sec=2700, dist_km=10, gain_m=400, decoupling=4)]
        result = _run_aggregation(rows, sport_type="cycling")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_intermittent_filtered(self):
        rows = [_make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=4, is_intermittent=True)]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_workout_type_interval_filtered(self):
        rows = [_make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=4, workout_type="intervals")]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_paused_ratio_filtered(self):
        rows = [
            _make_row(
                sport_type="running",
                duration_sec=2700,
                dist_km=8,
                gain_m=20,
                decoupling=4,
                paused_time=500,
                elapsed_time=2700,
            )
        ]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_extreme_decoupling_filtered(self):
        rows = [
            _make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=55),
            _make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=-25),
        ]
        result = _run_aggregation(rows, sport_type="running")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_swimming_excluded_from_stability_samples(self):
        rows = [_make_row(sport_type="swimming", duration_sec=2700, dist_km=2, gain_m=0, decoupling=4)]
        result = _run_aggregation(rows, sport_type="swimming")
        self.assertEqual(result["stability_sample_count"], 0)

    def test_stability_confidence_buckets(self):
        one = [_make_row(sport_type="running", duration_sec=2700, dist_km=8, gain_m=20, decoupling=4)]
        medium = one * 3
        high = one * 5
        self.assertEqual(_run_aggregation(one, sport_type="running")["stability_confidence"], "low")
        self.assertEqual(_run_aggregation(medium, sport_type="running")["stability_confidence"], "medium")
        self.assertEqual(_run_aggregation(high, sport_type="running")["stability_confidence"], "high")


class TestIsValidVamActivity(unittest.TestCase):
    """_is_valid_vam_activity 函数纯逻辑测试。"""

    def test_unknown_sport_excluded(self):
        """未登记的运动类型(swimming 等)默认不纳入。"""
        from main import _is_valid_vam_activity
        row = {"gain_m": 100, "dist_km": 10}
        self.assertFalse(_is_valid_vam_activity(row, "swimming"))
        self.assertFalse(_is_valid_vam_activity(row, "yoga"))
        self.assertFalse(_is_valid_vam_activity(row, None))
        self.assertFalse(_is_valid_vam_activity(row, ""))

    def test_threshold_table_values(self):
        """阈值表:cycling=20,trail_running=30,hiking=50。"""
        from main import _VAM_CREDIBILITY_THRESHOLDS
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["cycling"], (20.0, 1.0))
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["road_cycling"], (20.0, 1.0))
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["mountain_biking"], (20.0, 1.0))
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["running"], (20.0, 1.0))
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["trail_running"], (30.0, 1.0))
        self.assertEqual(_VAM_CREDIBILITY_THRESHOLDS["hiking"], (50.0, 1.0))
        # swimming 等不在表中
        self.assertNotIn("swimming", _VAM_CREDIBILITY_THRESHOLDS)


class TestEnduranceAggregation(unittest.TestCase):
    """P3:耐力运动类型阈值 + 28 天训练连续性。"""

    def test_training_days_28d_dedupes_dates_and_excludes_short_sessions(self):
        same_day_a = _make_row(sport_type="running", trimp=50, duration_sec=1800, days_ago=1)
        same_day_b = _make_row(sport_type="running", trimp=40, duration_sec=1800, days_ago=1)
        short_session = _make_row(sport_type="running", trimp=30, duration_sec=599, days_ago=2)
        valid_other_day = _make_row(sport_type="running", trimp=35, duration_sec=600, days_ago=3)
        old_but_in_90d = _make_row(sport_type="running", trimp=60, duration_sec=1800, days_ago=40)

        result = _run_aggregation(
            [old_but_in_90d, valid_other_day, short_session, same_day_a, same_day_b],
            sport_type="running",
        )

        self.assertEqual(result["endurance_sample_count"], 5)
        self.assertEqual(result["endurance_training_days_28d"], 2)
        self.assertEqual(result["endurance_consistency_score"], 20)
        self.assertEqual(result["endurance_confidence"], "low")
        self.assertEqual(_endurance_score(result), result["endurance_score"])

    def test_training_days_confidence_buckets(self):
        low = [_make_row(sport_type="cycling", trimp=30, days_ago=i + 1) for i in range(5)]
        medium = [_make_row(sport_type="cycling", trimp=30, days_ago=i + 1) for i in range(6)]
        high = [_make_row(sport_type="cycling", trimp=30, days_ago=i + 1) for i in range(12)]

        self.assertEqual(_run_aggregation(low, sport_type="cycling")["endurance_confidence"], "low")
        self.assertEqual(_run_aggregation(medium, sport_type="cycling")["endurance_confidence"], "medium")
        self.assertEqual(_run_aggregation(high, sport_type="cycling")["endurance_confidence"], "high")

    def test_aggregation_returns_endurance_contract_fields(self):
        result = _run_aggregation(
            [_make_row(sport_type="hiking", trimp=20, duration_sec=1800, days_ago=1)],
            sport_type="hiking",
        )

        for key in (
            "endurance_score",
            "endurance_ctl_score",
            "endurance_consistency_score",
            "endurance_training_days_28d",
            "endurance_sample_count",
            "endurance_confidence",
            "endurance_source",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["endurance_sample_count"], 1)
        self.assertEqual(result["endurance_source"], "ctl_42d_plus_28d_consistency")

    def test_radar_dimensions_include_confidence_context(self):
        result = _run_aggregation(
            [
                _make_row(
                    sport_type="cycling",
                    trimp=30,
                    duration_sec=1800,
                    days_ago=1,
                    gain_m=80,
                    dist_km=20,
                    vam=600,
                    anaerobic_peak=9,
                    anaerobic_peak_source="speed_fallback",
                )
            ],
            sport_type="cycling",
        )
        dims = {dim["key"]: dim for dim in result["radar"]["dimensions"]}

        self.assertEqual(dims["endurance"]["confidence"], result["endurance_confidence"])
        self.assertEqual(dims["endurance"]["sample_count"], result["endurance_sample_count"])
        self.assertEqual(dims["endurance"]["source"], result["endurance_source"])
        self.assertIn("28天训练", dims["endurance"]["reason"])
        self.assertEqual(dims["climbing"]["sample_count"], result["climbing_sample_count"])
        self.assertEqual(dims["climbing"]["source"], "cycling_climb_composite")
        self.assertIn("VAM(每小时爬升速度) P90", dims["climbing"]["reason"])
        self.assertIn("score_cap", dims["climbing"])
        self.assertEqual(dims["anaerobic"]["source"], "speed_fallback")


class TestAdvancedMetricsVersionContract(unittest.TestCase):
    """P5:advanced_metrics 版本识别与 radar 返回契约。"""

    def test_needs_rebuild_boundaries(self):
        from main import CURRENT_METRICS_VERSION, needs_advanced_metrics_rebuild

        self.assertTrue(needs_advanced_metrics_rebuild(None))
        self.assertTrue(needs_advanced_metrics_rebuild(""))
        self.assertTrue(needs_advanced_metrics_rebuild("{bad json"))
        self.assertTrue(needs_advanced_metrics_rebuild("[]"))
        self.assertTrue(needs_advanced_metrics_rebuild({}))
        self.assertTrue(needs_advanced_metrics_rebuild({"metrics_version": CURRENT_METRICS_VERSION - 1}))
        self.assertFalse(needs_advanced_metrics_rebuild({"metrics_version": CURRENT_METRICS_VERSION}))
        self.assertFalse(needs_advanced_metrics_rebuild(json.dumps({"metrics_version": CURRENT_METRICS_VERSION + 1})))

    def test_radar_metrics_returns_version_contract_for_current_data(self):
        from main import CURRENT_METRICS_VERSION

        result = _run_aggregation(
            [_make_row(sport_type="running", trimp=30, duration_sec=1800, days_ago=1)],
            sport_type="running",
        )

        self.assertEqual(result["metrics_version"], CURRENT_METRICS_VERSION)
        self.assertEqual(result["expected_metrics_version"], CURRENT_METRICS_VERSION)
        self.assertFalse(result["needs_rebuild"])
        self.assertEqual(result["stale_metrics_count"], 0)

    def test_radar_metrics_flags_old_advanced_metrics(self):
        from main import CURRENT_METRICS_VERSION

        result = _run_aggregation(
            [_make_row(sport_type="running", trimp=30, duration_sec=1800, days_ago=1, metrics_version=CURRENT_METRICS_VERSION - 1)],
            sport_type="running",
        )

        self.assertEqual(result["metrics_version"], CURRENT_METRICS_VERSION - 1)
        self.assertEqual(result["expected_metrics_version"], CURRENT_METRICS_VERSION)
        self.assertTrue(result["needs_rebuild"])
        self.assertEqual(result["stale_metrics_count"], 1)

    def test_api_force_rebuild_returns_counts_and_version(self):
        from main import Api, CURRENT_METRICS_VERSION

        api = Api.__new__(Api)
        rebuild_result = {
            "ok": True,
            "rebuilt_count": 3,
            "skipped_count": 1,
            "failed_count": 2,
            "metrics_version": CURRENT_METRICS_VERSION,
        }
        with patch("main.force_rebuild_all_records", return_value=rebuild_result):
            response = api.api_force_rebuild_radar_data()

        self.assertTrue(response["ok"])
        data = response["data"]
        self.assertEqual(data["rebuilt_count"], 3)
        self.assertEqual(data["skipped_count"], 1)
        self.assertEqual(data["failed_count"], 2)
        self.assertEqual(data["metrics_version"], CURRENT_METRICS_VERSION)


if __name__ == "__main__":
    unittest.main()
