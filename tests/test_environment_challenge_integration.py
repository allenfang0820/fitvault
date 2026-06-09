"""
V_ENV.1.10 Environment Challenge 集成测试

依据:调研报告 §3 / §4
契约:fit-arch-contrac §2.1 全链路 / §五 AI 边界 / §六 审计字段隔离
- 任务 1.3 派生块注入到 MetricsResolver.resolve() 输出 final_data["environment_challenge"]
- 任务 1.1 / 1.2 工具函数被派生块消费
- 任务 1.5 颜色常量与 1.6 渲染函数依赖结构稳定性

测试范围:
  - 5 运动 × 4 子块派生正确性
  - humidity 入口(raw / meta / 0~1 / 0~100)防御性归一化
  - skiing/mountaineering 自动走低温 5 档
  - 全降级(无数据/无 weather)各子块不崩
  - 端到端 AI snapshot 黑盒隔离(不重复 1.3 的 build_ai_snapshot_block 路径)
"""

from __future__ import annotations
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver


def _make_raw(sport="running", total_ascent=0, total_distance=0, max_altitude=0,
              avg_temperature=None, weather=None, lat=None, lon=None):
    """构造 minimal raw dict,模拟 parse_fit_file_raw + main 注入 weather。"""
    session = {
        "sport": sport,
        "total_ascent": total_ascent,
        "total_distance": total_distance,
        "max_altitude": max_altitude,
    }
    if avg_temperature is not None:
        session["avg_temperature"] = avg_temperature
    if lat is not None:
        session["start_position_lat"] = lat
        session["position_lat"] = lat
    if lon is not None:
        session["start_position_long"] = lon
        session["position_long"] = lon
    raw = {
        "session_mesgs": [session],
        "lap_mesgs": [],
        "record_mesgs": [],
    }
    if weather is not None:
        raw["weather"] = weather
    return raw


class TestEnvironmentChallengeInjection(unittest.TestCase):
    """§任务 1.3:final_data["environment_challenge"] 注入"""

    def test_block_present_in_final_data(self):
        """resolve() 输出顶层含 environment_challenge 键"""
        out = MetricsResolver().resolve(_make_raw(sport="running"), meta={})
        self.assertIn("environment_challenge", out,
            "V_ENV FAIL: final_data 缺少 environment_challenge")

    def test_block_top_level_structure(self):
        """4 子块 + sport_type + phase + data_source 键齐全"""
        out = MetricsResolver().resolve(_make_raw(sport="running"), meta={})
        ec = out["environment_challenge"]
        for key in ("sport_type", "climb", "altitude", "heat",
                    "technical_terrain", "phase", "data_source"):
            self.assertIn(key, ec, f"V_ENV FAIL: environment_challenge 缺少 {key}")
        self.assertEqual(ec["phase"], 1)
        self.assertEqual(ec["data_source"], "fit_sdk")
        for sub in ("climb", "altitude", "heat"):
            for k in ("metric_name", "metric_value", "level", "label"):
                self.assertIn(k, ec[sub], f"V_ENV FAIL: {sub} 缺少 {k}")
        # v1.1: label is dict with label+explanation
        for sub in ("climb", "altitude", "heat"):
            self.assertIsInstance(ec[sub]["label"], dict, f"{sub} label 应为 dict")
            self.assertIn("explanation", ec[sub]["label"], f"{sub} label 缺 explanation")
        self.assertEqual(ec["technical_terrain"]["metric_value"], None)
        self.assertEqual(ec["technical_terrain"]["level"], 0)
        self.assertEqual(ec["technical_terrain"]["label"], "--")
        self.assertEqual(ec["technical_terrain"]["available"], False)

    def test_running_1000m_10km_800m_28c(self):
        """running 1000m爬升/10km/800m/28°C 无 humidity"""
        out = MetricsResolver().resolve(
            _make_raw(sport="running", total_ascent=1000, total_distance=10000,
                      max_altitude=800, avg_temperature=28),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["climb"]["metric_value"], 100.0)
        self.assertEqual(ec["climb"]["level"], 4)
        self.assertEqual(ec["climb"]["label"]["label"], "极限爬升挑战")
        self.assertTrue(ec["climb"]["label"]["explanation"])
        self.assertEqual(ec["altitude"]["level"], 0)
        self.assertEqual(ec["altitude"]["label"]["label"], "低海拔环境")
        self.assertTrue(ec["altitude"]["label"]["explanation"])
        # 28°C 单维度降级 → [25,30) → level 1「略有热感」
        self.assertIsNone(ec["heat"]["metric_value"])
        self.assertEqual(ec["heat"]["level"], 1)
        self.assertEqual(ec["heat"]["label"]["label"], "略有热感")
        self.assertTrue(ec["heat"]["label"]["explanation"])

    def test_trail_running_3500m_uses_trail_running_semantics(self):
        """trail_running + 海拔 3500m → altitude level 3(高海拔山地环境)"""
        out = MetricsResolver().resolve(
            _make_raw(sport="trail_running", total_ascent=200, total_distance=5000,
                      max_altitude=3500, avg_temperature=15),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["altitude"]["level"], 3)
        self.assertEqual(ec["altitude"]["label"]["label"], "高海拔山地环境")
        self.assertTrue(ec["altitude"]["label"]["explanation"])

    def test_skiing_auto_uses_cold_5_levels(self):
        """skiing + 海拔 2500m + -15°C:heat 走低温 5 档"""
        out = MetricsResolver().resolve(
            _make_raw(sport="skiing", total_ascent=1500, total_distance=15000,
                      max_altitude=2500, avg_temperature=-15),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["sport_type"], "skiing")
        self.assertEqual(ec["altitude"]["level"], 2)
        self.assertEqual(ec["altitude"]["label"]["label"], "中高海拔越野")
        self.assertTrue(ec["altitude"]["label"]["explanation"])
        self.assertEqual(ec["heat"]["level"], 2)
        self.assertEqual(ec["heat"]["label"]["label"], "低温环境")
        self.assertTrue(ec["heat"]["label"]["explanation"])
        self.assertEqual(ec["heat"]["metric_value"], -15.0)

    def test_mountaineering_cold_extreme(self):
        """mountaineering + -35°C → 极寒挑战 level 4(<= -30 触发)"""
        out = MetricsResolver().resolve(
            _make_raw(sport="mountaineering", total_ascent=2000, total_distance=20000,
                      max_altitude=5000, avg_temperature=-35),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["heat"]["level"], 4)
        self.assertEqual(ec["heat"]["label"]["label"], "极寒挑战")
        self.assertTrue(ec["heat"]["label"]["explanation"])

    def test_humidity_raw_0_to_100_normalized(self):
        """raw.weather.humidity=85(0~100)→ 归一化 0.85,30°C × 0.85 = 25.5"""
        out = MetricsResolver().resolve(
            _make_raw(
                sport="running", total_ascent=100, total_distance=10000,
                max_altitude=100, avg_temperature=30,
                weather={"humidity": 85, "temperature_c": 30}
            ),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["heat"]["metric_value"], 25.5)

    def test_humidity_raw_0_to_1_passthrough(self):
        """raw.weather.humidity=0.85(0~1)→ 直接传"""
        out = MetricsResolver().resolve(
            _make_raw(
                sport="running", total_ascent=100, total_distance=10000,
                max_altitude=100, avg_temperature=30,
                weather={"humidity": 0.85}
            ),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["heat"]["metric_value"], 25.5)

    def test_humidity_meta_weather_fallback(self):
        """raw 无 weather → meta.weather.humidity 兜底"""
        out = MetricsResolver().resolve(
            _make_raw(
                sport="running", total_ascent=100, total_distance=10000,
                max_altitude=100, avg_temperature=30
            ),
            meta={"weather": {"humidity": 70}}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["heat"]["metric_value"], 21.0)

    def test_humidity_meta_bare_fallback(self):
        """meta.humidity(裸字段)兜底"""
        out = MetricsResolver().resolve(
            _make_raw(
                sport="running", total_ascent=100, total_distance=10000,
                max_altitude=100, avg_temperature=30
            ),
            meta={"humidity": 0.5}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["heat"]["metric_value"], 15.0)

    def test_humidity_out_of_range_degrades(self):
        """humidity=150(>100 异常)→ 视为 None,heat.metric_value=None"""
        out = MetricsResolver().resolve(
            _make_raw(
                sport="running", total_ascent=100, total_distance=10000,
                max_altitude=100, avg_temperature=30,
                weather={"humidity": 150}
            ),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertIsNone(ec["heat"]["metric_value"])
        self.assertEqual(ec["heat"]["level"], 2)

    def test_sport_type_fallback_treadmill(self):
        """treadmill_running 未在表中 → 走 running fallback(100m/km → level 4)"""
        out = MetricsResolver().resolve(
            _make_raw(sport="treadmill_running", total_ascent=500, total_distance=5000),
            meta={}
        )
        ec = out["environment_challenge"]
        self.assertEqual(ec["sport_type"], "treadmill_running")
        # 500m / 5km = 100 m/km → level 4 → 跑步 4 档 label
        self.assertEqual(ec["climb"]["level"], 4)
        self.assertEqual(ec["climb"]["label"]["label"], "极限爬升挑战")
        self.assertTrue(ec["climb"]["label"]["explanation"])

    def test_all_zero_degrades_gracefully(self):
        """全零输入:4 子块全部 level 0"""
        out = MetricsResolver().resolve(_make_raw(sport="running"), meta={})
        ec = out["environment_challenge"]
        self.assertEqual(ec["climb"]["metric_value"], 0.0)
        self.assertEqual(ec["climb"]["level"], 0)
        self.assertEqual(ec["climb"]["label"]["label"], "平路路线")
        self.assertTrue(ec["climb"]["label"]["explanation"])
        self.assertEqual(ec["altitude"]["metric_value"], 0.0)
        self.assertEqual(ec["altitude"]["level"], 0)
        self.assertEqual(ec["altitude"]["label"]["label"], "低海拔环境")
        self.assertTrue(ec["altitude"]["label"]["explanation"])
        self.assertIsNone(ec["heat"]["metric_value"])
        self.assertEqual(ec["heat"]["level"], 0)
        self.assertEqual(ec["heat"]["label"]["label"], "环境舒适")
        self.assertTrue(ec["heat"]["label"]["explanation"])


class TestEnvironmentChallengeNoShadowDiff(unittest.TestCase):
    """§六 审计字段隔离:派生块严禁写 shadow_diff / 不读 shadow_diff"""

    def test_no_shadow_diff_in_block(self):
        """environment_challenge 4 子块不含 shadow_diff 审计字段"""
        out = MetricsResolver().resolve(
            _make_raw(sport="running", total_ascent=500, total_distance=5000,
                      max_altitude=2000, avg_temperature=25,
                      weather={"humidity": 60}),
            meta={"shadow_diff": {"climb_density": 99.9}}
        )
        ec = out["environment_challenge"]
        for sub in ("climb", "altitude", "heat", "technical_terrain"):
            self.assertNotIn("shadow_diff", ec[sub],
                f"V_ENV FAIL: {sub} 不应有 shadow_diff")
            self.assertNotIn("shadow_diff_json", ec[sub])
        self.assertNotIn("shadow_diff", ec)
        self.assertNotIn("shadow_diff_json", ec)

    def test_ai_snapshot_end_to_end_isolation(self):
        """端到端:resolve() 输出的 environment_challenge 不会进入 ai_snapshots"""
        row = {"id": 1, "sport_type": "running"}
        out = MetricsResolver().resolve(_make_raw(sport="running"), meta={})
        row["environment_challenge"] = out["environment_challenge"]
        snap = MetricsResolver._build_ai_snapshot_block(row)
        self.assertNotIn("environment_challenge", snap,
            "V_ENV FAIL: environment_challenge 端到端不应进入 AI snapshot")
        self.assertNotIn("environment_challenge", out.get("context_tags", {}),
            "V_ENV FAIL: environment_challenge 不应误入 context_tags")


if __name__ == "__main__":
    unittest.main()
