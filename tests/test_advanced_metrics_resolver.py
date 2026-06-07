"""V4-7: _compute_advanced_metrics + _convert_track_to_algorithm_records 下沉测试

契约:fit-arch-contrac §V4.0 防腐层 / IO 隔离
验证:
  1. _convert_track_to_algorithm_records:空输入/正常转换/时间解析/字段回退
  2. _compute_advanced_metrics:输出 5 键契约/空 records 安全/None 过滤
  3. main.py 透传约束:不含业务逻辑/不直接调 AdvancedMetricsCalc
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
from datetime import datetime, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver


# ══════════════════════════════════════════════════════════════════
# 测试辅助:构建模拟轨迹点
# ══════════════════════════════════════════════════════════════════

def _make_track_point(
    time_str: str,
    lat: float | None = None,
    lon: float | None = None,
    hr: int | None = None,
    speed: float | None = None,
    altitude: float | None = None,
    power: int | None = None,
) -> dict:
    pt: dict = {"time": time_str}
    if lat is not None:
        pt["lat"] = lat
    if lon is not None:
        pt["lon"] = lon
    if hr is not None:
        pt["hr"] = hr
    if speed is not None:
        pt["speed"] = speed
    if altitude is not None:
        pt["altitude"] = altitude
    if power is not None:
        pt["power"] = power
    return pt


# ══════════════════════════════════════════════════════════════════
# Test 1: _convert_track_to_algorithm_records
# ══════════════════════════════════════════════════════════════════

class TestConvertTrackToAlgorithmRecords(unittest.TestCase):
    """轨迹点 → 算法记录格式转换"""

    def test_empty_input(self):
        """空列表 → 空输出"""
        r = MetricsResolver._convert_track_to_algorithm_records([])
        self.assertEqual(r, [])

    def test_none_input(self):
        """None → []"""
        r = MetricsResolver._convert_track_to_algorithm_records(None)  # type: ignore
        self.assertEqual(r, [])

    def test_normal_conversion(self):
        """正常 2 个轨迹点含 GPS + HR + speed"""
        pts = [
            _make_track_point("2026-05-20T10:00:00Z", lat=30.0, lon=120.0, hr=140, speed=4.0),
            _make_track_point("2026-05-20T10:00:05Z", lat=30.001, lon=120.001, hr=145, speed=4.2),
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(len(r), 2)

    def test_output_fields(self):
        """输出每条记录含 timestamp/heart_rate/speed/altitude/distance/power"""
        pts = [
            _make_track_point("2026-05-20T10:00:00Z", lat=30.0, lon=120.0, hr=140,
                              speed=4.0, altitude=100.0, power=220),
            _make_track_point("2026-05-20T10:00:05Z", lat=30.001, lon=120.001, hr=145,
                              speed=4.2, altitude=105.0, power=225),
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(len(r), 2)
        rec = r[1]  # 第 2 个点有前驱点可计算 cumulative distance
        self.assertIsInstance(rec["timestamp"], datetime)
        self.assertEqual(rec["heart_rate"], 145)
        self.assertGreater(rec["speed"], 0)
        self.assertGreater(rec["altitude"], 0)
        self.assertGreater(rec["distance"], 0, "第 2 个点应有累计距离")
        self.assertEqual(rec["power"], 225)

    def test_skip_point_without_time(self):
        """无 time 字段的点应被跳过"""
        pts = [
            {"lat": 30.0, "lon": 120.0, "hr": 140},
            _make_track_point("2026-05-20T10:00:05Z", lat=30.001, lon=120.001, hr=145),
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(len(r), 1)

    def test_invalid_time_skipped(self):
        """无效时间格式 → 跳过该点"""
        pts = [
            _make_track_point("not-a-date", lat=30.0, lon=120.0, hr=140),
            _make_track_point("2026-05-20T10:00:05Z", lat=30.001, lon=120.001, hr=145),
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(len(r), 1)

    def test_enhanced_field_fallback(self):
        """enhanced_speed/altitude/hr 回退到 speed/altitude/hr"""
        pts = [
            {"time": "2026-05-20T10:00:00Z", "lat": 30.0, "lon": 120.0,
             "enhanced_speed": 5.0, "enhanced_altitude": 200.0, "heart_rate": 150},
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(r[0]["speed"], 5.0)
        self.assertEqual(r[0]["altitude"], 200.0)
        self.assertEqual(r[0]["heart_rate"], 150)

    def test_speed_from_pace_fallback(self):
        """无 speed 时有 pace → 从 pace 计算 speed"""
        pts = [
            _make_track_point("2026-05-20T10:00:00Z", lat=30.0, lon=120.0)
        ]
        pts[0]["pace"] = 300.0  # 5:00/km → speed = 1000/300 = 3.33 m/s
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertAlmostEqual(r[0]["speed"], 1000.0 / 300.0, places=2)

    def test_alt_field_fallback(self):
        """无 altitude 有 alt → 使用 alt"""
        pts = [
            {"time": "2026-05-20T10:00:00Z", "lat": 30.0, "lon": 120.0, "alt": 150.0},
        ]
        r = MetricsResolver._convert_track_to_algorithm_records(pts)
        self.assertEqual(r[0]["altitude"], 150.0)


# ══════════════════════════════════════════════════════════════════
# Test 2: _compute_advanced_metrics 输出契约
# ══════════════════════════════════════════════════════════════════

class TestComputeAdvancedMetricsContract(unittest.TestCase):
    """6 维高级指标输出契约"""

    def _make_sample_records(self, count: int = 10) -> list[dict]:
        """生成模拟算法记录(每次间隔 5s,恒定速度+HR)"""
        base = datetime(2026, 5, 20, 10, 0, 0, tzinfo=timezone.utc)
        records = []
        for i in range(count):
            records.append({
                "timestamp": base.replace(second=base.second + i * 5),
                "heart_rate": 140 + i,
                "speed": 4.0,
                "altitude": 100.0 + i * 2,
                "distance": i * 20.0,
                "power": 200 + i * 5,
            })
        return records

    def test_output_has_5_keys(self):
        """输出必须含 trimp/decoupling/vam/threshold_hr/anaerobic_peak 5 键"""
        records = self._make_sample_records(10)
        profile = {"rest_hr": 55, "max_hr": 190, "age": 30}
        r = MetricsResolver._compute_advanced_metrics(records, profile)
        expected = {"trimp", "decoupling", "vam", "threshold_hr", "anaerobic_peak"}
        self.assertEqual(set(r.keys()), expected,
                         f"输出必须恰好含 {expected} 5 个键")

    def test_no_metrics_version_in_output(self):
        """metrics_version 由 main.py 设置,不应出现在 Resolver 输出中"""
        records = self._make_sample_records(10)
        r = MetricsResolver._compute_advanced_metrics(records, {})
        self.assertNotIn("metrics_version", r,
                         "metrics_version 不应由 Resolver 返回")

    def test_empty_records_safe(self):
        """空 records → 仍返回 5 键结构(AdvancedMetricsCalc 内部处理)"""
        r = MetricsResolver._compute_advanced_metrics([], {"rest_hr": 55})
        self.assertEqual(set(r.keys()), {"trimp", "decoupling", "vam", "threshold_hr", "anaerobic_peak"})

    def test_performance_stable(self):
        """10 点数据调用不应超时(性能基准)"""
        import time
        records = self._make_sample_records(10)
        start = time.time()
        MetricsResolver._compute_advanced_metrics(records, {"rest_hr": 55, "max_hr": 190})
        elapsed = time.time() - start
        self.assertLess(elapsed, 5.0, "10 点高级指标计算应在 5 秒内完成")

    def test_profile_none_values_filtered(self):
        """profile 中含 None 值的字段被过滤,不影响计算"""
        records = self._make_sample_records(10)
        profile = {"rest_hr": 55, "max_hr": None, "age": None, "lactate_threshold": None}
        r = MetricsResolver._compute_advanced_metrics(records, profile)
        self.assertIn("trimp", r)
        self.assertIn("decoupling", r)

    def test_empty_profile_safe(self):
        """空 profile dict → 安全降级"""
        records = self._make_sample_records(10)
        r = MetricsResolver._compute_advanced_metrics(records, {})
        self.assertIn("trimp", r)
        self.assertIn("vam", r)


# ══════════════════════════════════════════════════════════════════
# Test 3: main.py 透传约束
# ══════════════════════════════════════════════════════════════════

class TestMainPyPassthroughConstraint(unittest.TestCase):
    """§V4.0 防腐层:main.py 只做 IO + 透传,不含业务计算"""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        with open(main_path, "r") as f:
            cls.main_source = f.read()
        cls.main_tree = ast.parse(cls.main_source)

    def test_convert_track_calls_resolver(self):
        """_convert_track_to_algorithm_records 调用 MetricsResolver"""
        self.assertIn("MetricsResolver._convert_track_to_algorithm_records",
                      self.main_source,
                      "main.py 必须使用 MetricsResolver._convert_track_to_algorithm_records")

    def test_convert_track_no_business_logic(self):
        """_convert_track_to_algorithm_records 不含 for 循环/业务逻辑"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_convert_track_to_algorithm_records":
                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.While)):
                        self.fail("main.py _convert_track_to_algorithm_records 不应含循环")
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                        if child.func.attr == "haversine_m":
                            self.fail("main.py 不应直接调 haversine_m")

    def test_compute_advanced_metrics_calls_resolver(self):
        """_compute_advanced_metrics 调用 MetricsResolver._compute_advanced_metrics"""
        self.assertIn("MetricsResolver._compute_advanced_metrics",
                      self.main_source,
                      "main.py 必须使用 MetricsResolver._compute_advanced_metrics")

    def test_compute_advanced_no_direct_calc(self):
        """_compute_advanced_metrics 不直接调 AdvancedMetricsCalc"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_compute_advanced_metrics":
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and child.id == "AdvancedMetricsCalc":
                        self.fail(
                            "main.py _compute_advanced_metrics 不应直接引用 AdvancedMetricsCalc,"
                            "应通过 MetricsResolver._compute_advanced_metrics")

    def test_profile_backend_still_in_main(self):
        """profile_backend.get_profile() IO 调用留在 main.py(IO 隔离验证)"""
        for node in ast.walk(self.main_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_compute_advanced_metrics":
                found_profile_call = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if (isinstance(child.func, ast.Attribute) and
                                child.func.attr == "get_profile"):
                            found_profile_call = True
                            break
                self.assertTrue(found_profile_call,
                                "IO 调用 profile_backend.get_profile() 必须留在 main.py")

    def test_resolver_no_profile_backend_import(self):
        """Resolver 不应 import profile_backend"""
        resolver_path = os.path.join(_PROJECT_ROOT, "metrics_resolver.py")
        with open(resolver_path, "r") as f:
            resolver_src = f.read()
        self.assertNotIn("import profile_backend", resolver_src,
                         "Resolver 严禁 import profile_backend(IO 隔离违规)")
        self.assertNotIn("from profile_backend import", resolver_src,
                         "Resolver 严禁 from profile_backend import(IO 隔离违规)")


if __name__ == "__main__":
    unittest.main()
