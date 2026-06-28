"""P0-2 集成测试: _build_detail_laps 编排器接入自动切圈

V10.0 任务 2 验证。

契约:
  - 户外骑行(FIT 0 或 1 圈)+ 距离 >= 5km + 有 points → 自动切圈
  - FIT >= 2 圈:始终优先返回 FIT 圈
  - 跑步/徒步/室内骑行:完全不受影响
"""
import json
import math
import sys
import unittest

sys.path.insert(0, "/Users/fanglei/应用开发/AI track")


def _make_cycling_points_json(
    total_distance_m: float = 23000.0,
    n_records: int = 3600,
    start_time: float = 0.0,
    start_distance: float = 0.0,
) -> str:
    """构造模拟 FIT 逐秒记录,序列化为 JSON 字符串。"""
    points = []
    for i in range(n_records):
        d = start_distance + (i / n_records) * total_distance_m
        points.append({
            "time": start_time + float(i),
            "distance": d,
            "alt": 500 + math.sin(i / 100) * 20,
            "hr": 140 + int(math.sin(i / 60) * 10),
            "power": 180 + int(math.sin(i / 30) * 20),
            "cadence": 85,
        })
    return json.dumps(points)


class _FakeApi:
    """模拟 Api 实例,提供 _decode_points_json 和 _build_lap_rows。"""

    def __init__(self):
        self.fallback_called = False

    def _decode_points_json(self, points_json):
        if not points_json:
            return []
        try:
            obj = json.loads(points_json)
            return obj if isinstance(obj, list) else []
        except Exception:
            return []

    def _build_lap_rows(self, dist_km, duration_sec, avg_hr, base_power):
        self.fallback_called = True
        if dist_km <= 0 or duration_sec <= 0:
            return []
        return [{
            "lap_no": 1,
            "distance_km": round(dist_km, 2),
            "pace_sec": int(duration_sec / max(dist_km, 0.001)),
            "hr": avg_hr or 148,
            "source_type": "mock",  # V10.0 R-3:对齐契约 §2.2
        }]


class TestP0_2CyclingAutoLapIntegration(unittest.TestCase):
    """V10.0 任务 2:_build_detail_laps 户外骑行自动切圈集成测试。"""

    # ── 行为 1: FIT 1 圈 + 户外骑行 + 距离 ≥ 5km → 自动切圈 ──
    def test_cycling_1_fit_lap_with_points_auto_splits(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "cycling",
            "laps_json": json.dumps([{
                "lap_index": 0,
                "distance_m": 23000,
                "elapsed_sec": 3600,
                "avg_hr": 140,
                "avg_power": 180,
            }]),
            "track_json": _make_cycling_points_json(),
        }

        laps = _build_detail_laps(api, row, "cycling", 23.0, 3600, 140, 180)

        # 23km 骑行,5km 桶 → 应切 5 段
        self.assertEqual(len(laps), 5, f"23km 应切 5 段,实际 {len(laps)}")
        # 自动切圈应带 source_type="frontend_fallback"(V10.0 R-1)
        for lap in laps:
            self.assertEqual(lap["source_type"], "frontend_fallback")
        # 应使用 P0-1 输出字段(distance_m, elapsed_sec)
        self.assertIn("distance_m", laps[0])
        self.assertIn("elapsed_sec", laps[0])
        # 不应触发 mock fallback
        self.assertFalse(api.fallback_called)

    # ── 行为 2: FIT 多圈 → 优先返回 FIT 圈 ──
    def test_cycling_multi_fit_laps_keep_real_fit(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "cycling",
            "laps_json": json.dumps([
                {"lap_index": 0, "distance_m": 8000, "elapsed_sec": 1200, "avg_hr": 130},
                {"lap_index": 1, "distance_m": 8000, "elapsed_sec": 1200, "avg_hr": 140},
                {"lap_index": 2, "distance_m": 7000, "elapsed_sec": 1200, "avg_hr": 150},
            ]),
            "track_json": _make_cycling_points_json(),
        }

        laps = _build_detail_laps(api, row, "cycling", 23.0, 3600, 140, 180)

        # FIT 3 圈应原样返回
        self.assertEqual(len(laps), 3, f"FIT 3 圈应原样返回,实际 {len(laps)}")
        # 不应进入自动切圈(无 source_type="frontend_fallback")
        for lap in laps:
            self.assertNotEqual(lap.get("source_type"), "frontend_fallback")
        self.assertFalse(api.fallback_called)

    # ── 行为 3: 跑步 + 0 圈 → 走 mock fallback(其他运动不受影响) ──
    def test_running_no_laps_keeps_mock_fallback(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {"sport_type": "running"}

        laps = _build_detail_laps(api, row, "running", 5.0, 1800, 150, 245)

        # 跑步不走自动切圈,走 mock fallback(mock 数据带 source_type="mock")
        self.assertTrue(api.fallback_called)
        for lap in laps:
            self.assertNotEqual(lap.get("source_type"), "frontend_fallback")

    # ── 行为 4: 室内骑行 + 0 圈 → 不走自动切圈(保持原状) ──
    def test_indoor_cycling_no_laps_does_not_auto_split(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "indoor_cycling",
            "track_json": _make_cycling_points_json(),
        }

        laps = _build_detail_laps(api, row, "indoor_cycling", 23.0, 3600, 140, 180)

        # 室内骑行不走自动切圈,走 mock fallback
        for lap in laps:
            self.assertNotEqual(lap.get("source_type"), "frontend_fallback")

    # ── 行为 5: 户外骑行 + 距离 < 5km → 不进入自动切圈 ──
    def test_cycling_short_distance_below_threshold_no_auto_split(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "cycling",
            "laps_json": json.dumps([{
                "lap_index": 0,
                "distance_m": 4000,
                "elapsed_sec": 900,
                "avg_hr": 140,
            }]),
            "track_json": _make_cycling_points_json(total_distance_m=4000.0, n_records=900),
        }

        laps = _build_detail_laps(api, row, "cycling", 4.0, 900, 140, 0)

        # 4km < 5km 阈值,FIT 1 圈应原样返回(带 source_type="fit_sdk")
        self.assertEqual(len(laps), 1, f"4km < 5km,应返回 FIT 1 圈,实际 {len(laps)}")
        self.assertEqual(laps[0].get("source_type"), "fit_sdk")  # V10.0 R-4 验证

    # ── 行为 6: FIT 1 圈 + 徒步 + 距离 ≥ 5km → 保持 V4.0 行为,不进入自动切圈 ──
    def test_hiking_1_fit_lap_keeps_v4_behavior(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "hiking",
            "laps_json": json.dumps([{
                "lap_index": 0,
                "distance_m": 17240.78,
                "elapsed_sec": 21710.897,
                "avg_hr": 135,
                "max_hr": 171,
                "total_ascent": 1152,
                "total_descent": 112,
            }]),
        }

        laps = _build_detail_laps(api, row, "hiking", 17.24, 21711, 135, 245)

        # 徒步 1 圈 FIT 应原样返回(保持 V4.0 行为,带 source_type="fit_sdk")
        self.assertEqual(len(laps), 1)
        self.assertEqual(laps[0]["ascent_m"], 1152)
        self.assertFalse(api.fallback_called)
        self.assertEqual(laps[0].get("source_type"), "fit_sdk")  # V10.0 R-4

    # ── 行为 7: FIT 0 圈 + 户外骑行 + 距离 ≥ 5km + 有 points → 自动切圈 ──
    def test_cycling_no_fit_lap_with_points_auto_splits(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "cycling",
            "laps_json": None,
            "track_json": _make_cycling_points_json(),
        }

        laps = _build_detail_laps(api, row, "cycling", 23.0, 3600, 140, 180)

        # 无 FIT 圈 + 有 points + 骑行 ≥ 5km → 应自动切圈
        self.assertEqual(len(laps), 5)
        for lap in laps:
            self.assertEqual(lap["source_type"], "frontend_fallback")  # V10.0 R-1

    # ── 行为 8: FIT 0 圈 + 户外骑行 + 无 points → 走 mock fallback ──
    def test_cycling_no_fit_lap_no_points_falls_back_to_mock(self):
        from main import _build_detail_laps

        api = _FakeApi()
        row = {
            "sport_type": "cycling",
            "laps_json": None,
            "track_json": None,
        }

        laps = _build_detail_laps(api, row, "cycling", 23.0, 3600, 140, 180)

        # 无 FIT 圈 + 无 points → 应走 mock fallback(mock 数据带 source_type="mock")
        self.assertTrue(api.fallback_called)
        for lap in laps:
            # V10.0 R-3:mock 数据必须带 source_type="mock"
            self.assertEqual(lap.get("source_type"), "mock")


if __name__ == "__main__":
    unittest.main()