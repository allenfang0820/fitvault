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
    days_ago: int = 10,
) -> dict:
    """构造一条模拟活动行(对齐 _rolling_aggregate_radar_metrics SQL 列)。"""
    metrics = {"vam": vam, "trimp": trimp}
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

    with patch("main.profile_backend._conn", return_value=mock_conn), \
         patch("main.profile_backend.get_profile", return_value=mock_profile):
        return _rolling_aggregate_radar_metrics(sport_type)


def _climbing_score(result: dict) -> int:
    """从 radar.dimensions 中取出 climbing 维度得分。"""
    for dim in result["radar"]["dimensions"]:
        if dim["key"] == "climbing":
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
        """gain_m=80m cycling 应进入聚合,climbing=95 (cycling 阈值 >=500)。"""
        rows = [_make_row(sport_type="cycling", gain_m=80, dist_km=20, vam=600)]
        result = _run_aggregation(rows, sport_type="cycling")
        # N=1 → _p90 退化为算术平均 = 600
        self.assertEqual(result["vam"], 600.0)
        # RadarScoreEngine.score_climbing(600, "cycling") = 95
        self.assertEqual(_climbing_score(result), 95)

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
        """hiking gain_m=100m 应保留,climbing=95 (hiking 阈值 >=400 vam=400 边界)。"""
        rows = [_make_row(sport_type="hiking", gain_m=100, dist_km=15, vam=400)]
        result = _run_aggregation(rows, sport_type="hiking")
        # vam=400 → p90(N=1) = 400
        self.assertEqual(result["vam"], 400.0)
        # RadarScoreEngine.score_climbing(400, "hiking") = 95 (vam >= 400)
        self.assertEqual(_climbing_score(result), 95)
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
                    "vam", "threshold_hr", "anaerobic_peak", "radar"):
            self.assertIn(key, result)


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


if __name__ == "__main__":
    unittest.main()
