"""任务 5 — capability 字段判据修正测试

契约:fit-arch-contrac §二 2.1 字段可追溯 / §五 数据可信分层
验证:
  1. has_elevation 判据正确(平坦路段不再误判)
  2. has_power 不再硬编码为 False
  3. 判据与 has_gps/has_hr 风格一致
  4. 轨迹报告 / 雷达图 / AI 不受影响(回归保障)
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class _FakeApi:
    """最小化的 Api 占位类,只为复用 _build_record_from_row 中的字段访问"""

    def __init__(self):
        self._build_lap_rows = lambda *a, **k: []
        self._sample_thumbnail_points = lambda points, limit=48: []
        self._decode_points_json = lambda value: []  # 始终返回空 points 列表


def _make_row(**overrides):
    """构造 activities 表 row 默认值(覆盖测试需要修改的字段)"""
    base = {
        "id": 1,
        "filename": "test.fit",
        "file_name": "test.fit",
        "title": "test",
        "title_source": "filename",
        "sport_type": "running",
        "sub_sport_type": "generic",
        "dist_km": 5.0,
        "distance": 5000.0,
        "duration": 1800,
        "duration_sec": 1800,
        "avg_pace": 360.0,
        "avg_hr": 150,
        "max_hr": 170,
        "calories": 350,
        "gain_m": None,
        "max_alt_m": None,
        "min_alt_m": None,
        "total_descent_m": None,
        "avg_power": None,
        "normalized_power": None,
        "points_json": None,
        "track_json": None,
        "merged_track_json": None,
        "start_time": "2026-05-20T10:00:00",
        "start_time_utc": "2026-05-20T02:00:00Z",
        "start_lat": None,
        "start_lon": None,
        "region": None,
        "region_status": "pending",
        "region_display": None,
        "weather_json": None,
        "file_path": "/tmp/test.fit",
        "device_name": "TestDevice",
        "shadow_diff_json": None,
        "laps_json": None,
        "hr_curve": None,
        "speed_curve": None,
        "cadence_curve": None,
        "hr_zone_distribution": None,
        "is_race": 0,
        "is_event": 0,
        "is_intermittent": 0,
        "up_count": 0,
        "down_count": 0,
        "max_single_climb_m": 0.0,
        "difficulty_score": 0,
        "report_metrics_version": 0,
        "avg_grade_pct": 0.0,
        "max_slope_pct": 0.0,
        "min_slope_pct": 0.0,
        "uphill_pct": 0.0,
        "downhill_pct": 0.0,
        "deleted_at": None,
    }
    base.update(overrides)
    return base


class TestHasElevation(unittest.TestCase):
    """验证 has_elevation 判据修正:平坦路段不再误判"""

    def _caps(self, **overrides):
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row(**overrides)
        record = _build_record_from_row(api, row, 0)
        return record["detail"]["capabilities"]

    def test_gain_m_zero_but_has_max_alt(self):
        """平坦路段(gain_m=0, max_alt_m=1500) → has_elevation=True"""
        caps = self._caps(gain_m=0, max_alt_m=1500.0, min_alt_m=1450.0)
        self.assertTrue(
            caps["has_elevation"],
            "平坦路段(gain_m=0) 但 max_alt_m/min_alt_m 存在 → 应为 True"
        )

    def test_all_four_fields_none(self):
        """完全无海拔数据(4 字段全部 None) → has_elevation=False"""
        # 全部 4 个海拔字段都未解析(None)→ 判为无海拔数据
        caps = self._caps(gain_m=None, max_alt_m=None, min_alt_m=None, total_descent_m=None)
        self.assertFalse(
            caps["has_elevation"],
            "4 字段全部 None → 应为 False (无 FIT 海拔数据)"
        )

    def test_gain_m_zero_with_only_gain_m(self):
        """仅 gain_m=0(传感器工作但全程平坦)→ has_elevation=True"""
        # 修复后语义: gain_m=0 表示传感器存在并记录了数据,只是累计爬升为 0
        # 4 字段交叉验证应判为 True(契约 §五 数据可信分层)
        caps = self._caps(gain_m=0, max_alt_m=None, min_alt_m=None, total_descent_m=None)
        self.assertTrue(
            caps["has_elevation"],
            "仅 gain_m=0(其余 None) → 应为 True (传感器存在,值合法为 0)"
        )

    def test_gain_m_normal(self):
        """正常爬升 gain_m=200 → has_elevation=True"""
        caps = self._caps(gain_m=200.0)
        self.assertTrue(caps["has_elevation"])

    def test_gain_m_none(self):
        """gain_m=None (未解析) → has_elevation=False"""
        caps = self._caps(gain_m=None)
        self.assertFalse(caps["has_elevation"])

    def test_total_descent_only(self):
        """仅 total_descent_m 存在 → has_elevation=True (4 字段交叉验证)"""
        caps = self._caps(gain_m=None, max_alt_m=None, min_alt_m=None, total_descent_m=50.0)
        self.assertTrue(
            caps["has_elevation"],
            "仅 total_descent_m 存在 → 4 字段交叉验证应判为 True"
        )

    def test_regression_no_legacy_strict_zero(self):
        """回归测试:原判据 'gain_m > 0' 已不再使用"""
        caps = self._caps(gain_m=0, max_alt_m=1500.0)
        # 原实现: gain_m=0 → has_elevation=False
        # 修复后: max_alt_m=1500 → has_elevation=True
        self.assertTrue(caps["has_elevation"])

    def test_four_fields_independent(self):
        """4 字段覆盖:gain_m / max_alt_m / min_alt_m / total_descent_m 各自独立可触发 True"""
        for field, value in [
            ("gain_m", 50.0),
            ("max_alt_m", 1500.0),
            ("min_alt_m", 1450.0),
            ("total_descent_m", 50.0),
        ]:
            kwargs = {f: None for f in ("gain_m", "max_alt_m", "min_alt_m", "total_descent_m")}
            kwargs[field] = value
            caps = self._caps(**kwargs)
            self.assertTrue(
                caps["has_elevation"],
                f"仅 {field}={value} 存在时 has_elevation 应为 True"
        )


class TestDetailSummaryFields(unittest.TestCase):
    """验证详情核心卡片依赖的 summary 派生字段完整。"""

    def test_cycling_summary_exposes_avg_speed_mps(self):
        from main import _build_record_from_row

        api = _FakeApi()
        row = _make_row(
            sport_type="cycling",
            sub_sport_type="generic",
            dist_km=23.64418,
            distance=23644.18,
            duration=2791,
            duration_sec=2791,
        )
        record = _build_record_from_row(api, row, 0)

        summary = record["detail"]["summary"]
        self.assertIn("avg_speed", summary)
        self.assertAlmostEqual(summary["avg_speed"], 23644.18 / 2791, places=6)


class TestHasPower(unittest.TestCase):
    """验证 has_power 不再硬编码为 False"""

    def _caps(self, **overrides):
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row(**overrides)
        record = _build_record_from_row(api, row, 0)
        return record["detail"]["capabilities"]

    def test_has_avg_power(self):
        """avg_power 存在 → has_power=True"""
        caps = self._caps(avg_power=250, normalized_power=None)
        self.assertTrue(
            caps["has_power"],
            "avg_power=250 存在 → has_power 必须为 True (骑行台/功率计场景)"
        )

    def test_has_normalized_power(self):
        """normalized_power 存在 → has_power=True"""
        caps = self._caps(avg_power=None, normalized_power=230)
        self.assertTrue(caps["has_power"])

    def test_no_power_data(self):
        """无功率数据 → has_power=False"""
        caps = self._caps(avg_power=None, normalized_power=None)
        self.assertFalse(caps["has_power"])

    def test_zero_power_treated_as_no_data(self):
        """avg_power=0 视为无数据(FIT 协议中 0 通常表示未启用)"""
        caps = self._caps(avg_power=0, normalized_power=0)
        # bool(0) = False → has_power=False
        # 这与 has_hr 的判据一致(0/None=无数据)
        self.assertFalse(caps["has_power"])


class TestCapabilityConsistency(unittest.TestCase):
    """判据风格与同侪一致(has_gps/has_hr)"""

    def test_all_four_capabilities_present(self):
        """capabilities 必须包含 4 个字段"""
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row()
        record = _build_record_from_row(api, row, 0)
        caps = record["detail"]["capabilities"]
        for key in ("has_gps", "has_hr", "has_elevation", "has_power"):
            self.assertIn(key, caps, f"{key} 应在 capabilities 中")

    def test_judgement_style_aligned(self):
        """静态分析:旧判据字符串不再出现,新判据存在"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_record_from_row":
                continue
            func_src = ast.unparse(node)
            # 旧判据
            self.assertNotIn(
                'has_elevation": bool(row.get("gain_m") and float(row.get("gain_m")) > 0)',
                func_src,
                "旧判据 has_elevation 已被替换",
            )
            self.assertNotIn(
                '"has_power": False',
                func_src,
                "硬编码 has_power: False 已废弃",
            )
            # 新判据必须存在
            self.assertIn(
                'has_elevation',
                func_src,
                "has_elevation 仍需存在",
            )
            self.assertIn(
                'has_power',
                func_src,
                "has_power 仍需存在",
            )
            self.assertIn(
                "'total_descent_m'",
                func_src,
                "4 字段交叉验证元组必须存在",
            )
            # 额外确认 4 字段都出现
            for field in ("gain_m", "max_alt_m", "min_alt_m", "total_descent_m"):
                self.assertIn(
                    f"'{field}'",
                    func_src,
                    f"4 字段交叉验证必须包含 {field}",
                )


class TestTrajectoryReportUnaffected(unittest.TestCase):
    """轨迹报告 / 雷达图 / AI 不受任务 5 改动影响(回归保障)"""

    def test_activity_summary_elevation_independent(self):
        """raw_for_engine.elevation 与 has_elevation capability 独立"""
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row(gain_m=200.0)
        record = _build_record_from_row(api, row, 0)
        # raw_for_engine.elevation 仍正确(独立于 capabilities)
        self.assertEqual(record["detail"]["summary"]["elevation"], 200)
        self.assertTrue(record["detail"]["capabilities"]["has_elevation"])

    def test_elevation_zero_passes_through(self):
        """gain_m=0 时,raw_for_engine.elevation 透传为 0(契约 §五 透传原则)"""
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row(gain_m=0, max_alt_m=1500.0)
        record = _build_record_from_row(api, row, 0)
        # elevation 透传 0(契约 §五:DB 透传,UI/AI 不二次修改)
        self.assertEqual(record["detail"]["summary"]["elevation"], 0)
        # capability 判据: max_alt_m 存在 → True(任务 5 修复)
        self.assertTrue(record["detail"]["capabilities"]["has_elevation"])

    def test_record_top_level_gain_m_preserved(self):
        """record 顶层 gain_m 字段仍正确(供轨迹报告消费)"""
        from main import _build_record_from_row
        api = _FakeApi()
        row = _make_row(gain_m=200.0)
        record = _build_record_from_row(api, row, 0)
        self.assertEqual(record["gain_m"], 200)


if __name__ == "__main__":
    unittest.main()
