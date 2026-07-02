"""V10.0 P1-1: source_type 标记测试(契约 §2.2 数据可信分层)

验证三种数据源都正确打上 source_type 标记,前端可据此过滤 mock。

契约要求:
  - FIT 真实圈 → source_type='fit_sdk'
  - 自动切圈 → source_type='frontend_fallback'(V10.0 R-1 修订)
  - mock 数据 → source_type='mock'(V10.0 R-3 修订)
"""
import json
import sys
import unittest

sys.path.insert(0, "/Users/fanglei/应用开发/AI track")


class TestSourceTypeMarkers(unittest.TestCase):
    """V10.0 P1-1: 三种数据源必须带 source_type 字段"""

    # ── 1. FIT 真实圈必须带 source_type='fit_sdk' ──
    def test_real_fit_laps_have_fit_sdk_marker(self):
        from main import _build_real_laps_from_row
        row = {
            "laps_json": json.dumps([
                {"lap_index": 0, "distance_m": 5000, "elapsed_sec": 1200, "avg_hr": 140},
                {"lap_index": 1, "distance_m": 5000, "elapsed_sec": 1200, "avg_hr": 142},
            ]),
        }
        laps = _build_real_laps_from_row(row)
        self.assertEqual(len(laps), 2)
        for lap in laps:
            self.assertEqual(lap.get("source_type"), "fit_sdk",
                             f"FIT 圈应带 source_type='fit_sdk',实际 {lap.get('source_type')}")

    # ── 2. mock 数据必须带 source_type='mock' ──
    def test_mock_lap_rows_have_mock_marker(self):
        from main import Api
        api = Api()
        rows = api._build_lap_rows(5.0, 1800, 150, 245)
        self.assertTrue(len(rows) > 0)
        for row in rows:
            self.assertEqual(row.get("source_type"), "mock",
                             f"mock 圈应带 source_type='mock',实际 {row.get('source_type')}")

    # ── 3. 自动切圈(P0-1 输出)必须带 source_type='frontend_fallback' ──
    def test_synthetic_laps_have_frontend_fallback_marker(self):
        from metrics_resolver import MetricsResolver
        points = [
            {"time": float(i), "distance": float(i * 6), "hr": 140, "power": 180, "cadence": 85}
            for i in range(1500)
        ]
        laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)
        self.assertTrue(len(laps) > 0, "P0-1 应生成至少 1 段自动切圈")
        for lap in laps:
            self.assertEqual(lap.get("source_type"), "frontend_fallback",
                             f"自动切圈应带 source_type='frontend_fallback',实际 {lap.get('source_type')}")


class TestLapColumnPresetsContract(unittest.TestCase):
    """V10.0 P1-1: LAP_COLUMN_PRESETS 骑行升级为 9 列,其他运动不变"""

    def test_cycling_has_9_columns(self):
        from main import LAP_COLUMN_PRESETS
        cycling_cols = LAP_COLUMN_PRESETS["cycling"]
        self.assertEqual(len(cycling_cols), 9, f"骑行应有 9 列,实际 {len(cycling_cols)}")
        # 验证关键列存在
        for col in ("lap_no", "lap_distance_km", "elapsed_sec", "avg_speed_kmh",
                    "avg_hr", "avg_power", "max_power", "normalized_power", "total_ascent"):
            self.assertIn(col, cycling_cols, f"骑行圈表缺失 {col}")

    def test_road_cycling_has_9_columns(self):
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(len(LAP_COLUMN_PRESETS["road_cycling"]), 9)

    def test_mountain_biking_has_9_columns(self):
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(len(LAP_COLUMN_PRESETS["mountain_biking"]), 9)

    def test_indoor_cycling_unchanged(self):
        """室内骑行不应被 P1-1 影响,保持原 3 列配置"""
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(LAP_COLUMN_PRESETS["indoor_cycling"],
                         ["avg_pace", "avg_hr", "power"])

    def test_running_unchanged(self):
        """跑步基础列保持不变;左右平衡由 detail laps 数据决定"""
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(LAP_COLUMN_PRESETS["running"],
                         ["avg_pace", "avg_hr", "cadence", "gct", "power"])

    def test_running_detail_columns_add_balance_only_when_present(self):
        from main import resolve_detail_lap_columns
        self.assertEqual(
            resolve_detail_lap_columns("running", [{"stance_time_balance_pct": None}]),
            ["avg_pace", "avg_hr", "cadence", "gct", "power"],
        )
        self.assertEqual(
            resolve_detail_lap_columns("running", [{"stance_time_balance_pct": 49.8}]),
            ["avg_pace", "avg_hr", "cadence", "gct", "stance_balance", "power"],
        )

    def test_hiking_unchanged(self):
        """徒步不应被 P1-1 影响"""
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(LAP_COLUMN_PRESETS["hiking"],
                         ["avg_pace", "avg_hr", "max_hr", "ascent", "descent"])

    def test_swimming_unchanged(self):
        """游泳不应被 P1-1 影响"""
        from main import LAP_COLUMN_PRESETS
        self.assertEqual(LAP_COLUMN_PRESETS["swimming"],
                         ["avg_hr", "swolf", "stroke_style", "length_distance"])


if __name__ == "__main__":
    unittest.main()
