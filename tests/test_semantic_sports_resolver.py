"""V4-3: SemanticSportsEngine 类下沉至 metrics_resolver 单元测试

契约:fit-arch-contrac §V4.0 防腐层
验证:
  1. Resolver 内部暴露 SemanticSportsEngine 类
  2. METRICS / SPORT_PROFILES 字典完整迁移
  3. 4 类运动(running/cycling/strength/hiking)的 build_display_metrics / get_layout
  4. 未知运动走 fallback (running)
  5. format_duration / format_pace 边界
  6. main.py 中 SemanticSportsEngine 类已彻底删除(透传 import)
  7. 调用点 L6303-6304 仍能正确解析
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import SemanticSportsEngine


class TestSemanticSportsEngineExposed(unittest.TestCase):
    """§V4.0 Resolver 内部必须暴露 SemanticSportsEngine 类"""

    def test_class_importable(self):
        """SemanticSportsEngine 可从 metrics_resolver 导入"""
        from metrics_resolver import SemanticSportsEngine
        self.assertTrue(callable(SemanticSportsEngine))

    def test_class_is_actual_class(self):
        """必须是真实的 class(非函数/实例)"""
        self.assertTrue(isinstance(SemanticSportsEngine, type))

    def test_class_has_required_methods(self):
        """必须含 build_display_metrics / get_layout / format_duration / format_pace"""
        for method in ("build_display_metrics", "get_layout",
                       "format_duration", "format_pace"):
            self.assertTrue(hasattr(SemanticSportsEngine, method),
                          f"SemanticSportsEngine 必须含 {method}")


class TestMetricsDictionary(unittest.TestCase):
    """METRICS 字典完整性"""

    def test_metrics_has_required_keys(self):
        """METRICS 必须含 8 个核心字段"""
        required = ("distance", "duration", "avg_pace", "avg_speed",
                   "avg_hr", "max_hr", "elevation", "calories")
        for key in required:
            self.assertIn(key, SemanticSportsEngine.METRICS,
                         f"METRICS 必须含 {key}")
            self.assertIn("label", SemanticSportsEngine.METRICS[key])
            self.assertIn("unit", SemanticSportsEngine.METRICS[key])


class TestSportProfilesDictionary(unittest.TestCase):
    """SPORT_PROFILES 字典完整性"""

    def test_profiles_has_required_sports(self):
        """SPORT_PROFILES 必须含 6 类运动"""
        for sport in ("running", "trail_running", "cycling",
                     "swimming", "strength", "hiking"):
            self.assertIn(sport, SemanticSportsEngine.SPORT_PROFILES,
                         f"SPORT_PROFILES 必须含 {sport}")

    def test_profile_has_required_keys(self):
        """每个 sport profile 必须含 summary_keys 和 cards"""
        for sport, profile in SemanticSportsEngine.SPORT_PROFILES.items():
            self.assertIn("summary_keys", profile, f"{sport} 缺 summary_keys")
            self.assertIn("cards", profile, f"{sport} 缺 cards")
            self.assertIsInstance(profile["summary_keys"], list)
            self.assertIsInstance(profile["cards"], list)
            self.assertGreater(len(profile["cards"]), 0, f"{sport} cards 应非空")


class TestBuildDisplayMetrics(unittest.TestCase):
    """build_display_metrics 单元测试(6 类运动)"""

    def _assert_display(self, sport_type, raw_data, expected_keys):
        out = SemanticSportsEngine.build_display_metrics(sport_type, raw_data)
        keys = [item["key"] for item in out]
        self.assertEqual(keys, expected_keys,
                        f"{sport_type} summary_keys 应为 {expected_keys},得到 {keys}")
        for item in out:
            self.assertIn("key", item)
            self.assertIn("label", item)
            self.assertIn("value", item)
            self.assertIn("unit", item)

    def test_running_display(self):
        self._assert_display(
            "running",
            {"distance_km": 10.0, "duration_sec": 3600, "avg_pace_sec": 360, "avg_hr": 150},
            ["distance", "avg_pace", "duration", "avg_hr"],
        )

    def test_trail_running_display(self):
        self._assert_display(
            "trail_running",
            {"distance_km": 15.0, "elevation": 800.0, "duration_sec": 5400, "avg_pace_sec": 360},
            ["distance", "elevation", "duration", "avg_pace"],
        )

    def test_cycling_display(self):
        self._assert_display(
            "cycling",
            {"distance_km": 50.0, "duration_sec": 7200, "avg_speed_calc": 25.0, "avg_hr": 140},
            ["distance", "avg_speed", "duration", "avg_hr"],
        )

    def test_swimming_display(self):
        self._assert_display(
            "swimming",
            {"distance_km": 2.0, "duration_sec": 1800, "avg_pace_sec": 900, "avg_hr": 130},
            ["distance", "avg_pace", "duration", "avg_hr"],
        )

    def test_strength_display(self):
        self._assert_display(
            "strength",
            {"duration_sec": 3600, "calories": 350, "avg_hr": 120, "max_hr": 160},
            ["duration", "calories", "avg_hr", "max_hr"],
        )

    def test_hiking_display(self):
        self._assert_display(
            "hiking",
            {"distance_km": 8.0, "duration_sec": 7200, "elevation": 600.0, "avg_hr": 110},
            ["distance", "duration", "elevation", "avg_hr"],
        )

    def test_unknown_sport_fallback(self):
        """未知 sport 走 running fallback"""
        self._assert_display(
            "yoga_unknown",
            {"distance_km": 0.0, "duration_sec": 1800, "avg_hr": 100},
            ["distance", "avg_pace", "duration", "avg_hr"],
        )

    def test_missing_raw_data_fields_safe(self):
        """raw_data 字段缺失时不抛异常(用 0 降级)"""
        out = SemanticSportsEngine.build_display_metrics("running", {})
        self.assertEqual(len(out), 4)
        # 所有 value 应非空(可能是 "--" 或 0 字符串)
        for item in out:
            self.assertNotEqual(item["value"], "")


class TestBuildDisplayMetricsValueFormatting(unittest.TestCase):
    """build_display_metrics 输出 value 格式"""

    def test_distance_format(self):
        """distance: 保留 2 位小数 + km"""
        out = SemanticSportsEngine.build_display_metrics(
            "running", {"distance_km": 10.5, "duration_sec": 3600, "avg_pace_sec": 360, "avg_hr": 150}
        )
        distance = next(i for i in out if i["key"] == "distance")
        self.assertEqual(distance["value"], "10.50")
        self.assertEqual(distance["unit"], "km")

    def test_duration_format_h_m_s(self):
        """duration: 1h30m0s → 1:30:00"""
        out = SemanticSportsEngine.build_display_metrics(
            "running", {"distance_km": 10, "duration_sec": 5400, "avg_pace_sec": 360, "avg_hr": 150}
        )
        duration = next(i for i in out if i["key"] == "duration")
        self.assertEqual(duration["value"], "1:30:00")

    def test_pace_format(self):
        """avg_pace: 360s/km → 6'00" """
        out = SemanticSportsEngine.build_display_metrics(
            "running", {"distance_km": 10, "duration_sec": 3600, "avg_pace_sec": 360, "avg_hr": 150}
        )
        pace = next(i for i in out if i["key"] == "avg_pace")
        self.assertEqual(pace["value"], "6'00\"")

    def test_hr_value_preserved(self):
        """avg_hr: 直接显示数值"""
        out = SemanticSportsEngine.build_display_metrics(
            "running", {"distance_km": 10, "duration_sec": 3600, "avg_pace_sec": 360, "avg_hr": 150}
        )
        hr = next(i for i in out if i["key"] == "avg_hr")
        self.assertEqual(hr["value"], "150")
        self.assertEqual(hr["unit"], "bpm")


class TestGetLayout(unittest.TestCase):
    """get_layout 单元测试"""

    def test_running_layout(self):
        layout = SemanticSportsEngine.get_layout("running")
        self.assertIn("cards", layout)
        self.assertEqual(len(layout["cards"]), 3)

    def test_unknown_sport_fallback_layout(self):
        """未知 sport 走 running fallback layout"""
        layout = SemanticSportsEngine.get_layout("yoga_unknown")
        self.assertIn("cards", layout)
        self.assertEqual(len(layout["cards"]), 3)

    def test_each_sport_has_unique_layout(self):
        """6 类运动应至少有 3 种不同 layout"""
        layouts = set()
        for sport in SemanticSportsEngine.SPORT_PROFILES:
            l = SemanticSportsEngine.get_layout(sport)
            layouts.add(str(l))
        self.assertGreaterEqual(len(layouts), 3, "应有至少 3 种不同 layout")


class TestFormatHelpers(unittest.TestCase):
    """format_duration / format_pace 边界"""

    def test_format_duration_zero(self):
        self.assertEqual(SemanticSportsEngine.format_duration(0), "--")

    def test_format_duration_negative(self):
        self.assertEqual(SemanticSportsEngine.format_duration(-100), "--")

    def test_format_duration_none(self):
        self.assertEqual(SemanticSportsEngine.format_duration(None), "--")

    def test_format_duration_seconds_only(self):
        """< 1 小时 → mm:ss"""
        self.assertEqual(SemanticSportsEngine.format_duration(125), "02:05")

    def test_format_duration_with_hours(self):
        """>= 1 小时 → h:mm:ss"""
        self.assertEqual(SemanticSportsEngine.format_duration(3725), "1:02:05")

    def test_format_pace_zero(self):
        self.assertEqual(SemanticSportsEngine.format_pace(0), "--")

    def test_format_pace_negative(self):
        self.assertEqual(SemanticSportsEngine.format_pace(-100), "--")

    def test_format_pace_5min(self):
        """300s/km → 5'00" """
        self.assertEqual(SemanticSportsEngine.format_pace(300), "5'00\"")

    def test_format_pace_4_30(self):
        """270s/km → 4'30" """
        self.assertEqual(SemanticSportsEngine.format_pace(270), "4'30\"")


class TestMainPyPassthrough(unittest.TestCase):
    """§V4.0 透传代码模板:main.py 通过 import 引用 Resolver 类,严禁重新定义"""

    def test_main_py_no_class_definition(self):
        """main.py 不应再有 `class SemanticSportsEngine` 定义"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            self.assertNotEqual(
                node.name, "SemanticSportsEngine",
                "main.py 不应再定义 SemanticSportsEngine 类(V4.0 已下沉)"
            )

    def test_main_py_imports_from_resolver(self):
        """main.py 顶部 import 必须含 SemanticSportsEngine"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        # 找 import 行
        self.assertIn(
            "from metrics_resolver import",
            text,
            "main.py 必须从 metrics_resolver 导入 SemanticSportsEngine"
        )
        # 只遍历顶级 import(walk 会进入 if TYPE_CHECKING 等子作用域,误判)
        tree = ast.parse(text)
        top_imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        found_resolver_import = False
        for node in top_imports:
            if node.module != "metrics_resolver":
                continue
            found_resolver_import = True
            imported_names = [alias.name for alias in node.names]
            self.assertIn(
                "SemanticSportsEngine", imported_names,
                "main.py 顶部 import 必须含 SemanticSportsEngine"
            )
        self.assertTrue(found_resolver_import,
                      "main.py 必须从 metrics_resolver 导入")

    def test_call_sites_unchanged(self):
        """main.py 调用点 L6303-6304 仍使用 SemanticSportsEngine.build_display_metrics / get_layout"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        # 调用点必须保留(只是从 Resolver 而来,名称仍可用)
        self.assertIn("SemanticSportsEngine.build_display_metrics", text,
                     "调用点必须保留 SemanticSportsEngine.build_display_metrics")
        self.assertIn("SemanticSportsEngine.get_layout", text,
                     "调用点必须保留 SemanticSportsEngine.get_layout")


if __name__ == "__main__":
    unittest.main()
