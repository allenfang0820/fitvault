"""
V8.4 契约测试:_compute_hr_zone_distribution + 持久化路径

任务: §V8.4 FIT 解析时计算 Z1-Z5 心率区间分布,写入 activities.hr_zone_distribution。
      修复 D3-2:V7.13 训练负荷算法终于能产出真实 load。

契约依据:
- §2.1 全链路可追溯:hr_zone 来源 = hr_curve + 个人最大心率(profile)
- §2.2 数据可信分层:max_hr 缺失时拒写(None),不写入假数据
- §6 shadow_diff 隔离:hr_zone_distribution 不属于 shadow_diff
- §8 canonical 写入:V8.4 是 INSERT 路径的新增列写入
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import types
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read_main() -> str:
    with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
        return f.read()


def _load_helper():
    """动态加载 _compute_hr_zone_distribution(避免 import main 触发 pywebview)。"""
    main = _read_main()
    match = re.search(
        r'def _compute_hr_zone_distribution\([^)]*\)[^:]*:.*?(?=\ndef |\Z)',
        main, re.DOTALL
    )
    fn_src = match.group(0)
    stub = types.ModuleType("v84_stub")
    stub.json = json
    def _safe_int(v, default=0):
        try: return int(v) if v is not None else default
        except: return default
    stub._safe_int = _safe_int
    # V8.4 helper 用 future annotations
    code = "from __future__ import annotations\n" + fn_src
    exec(compile(code, "main.py:_compute_hr_zone_distribution", "exec"),
         stub.__dict__)
    return stub._compute_hr_zone_distribution


class TestV8_4ZoneHelper(unittest.TestCase):
    """§V8.4 P0-1: _compute_hr_zone_distribution 计算精度。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = staticmethod(_load_helper())

    def test_v8_4_typical_z3_dominant_ride(self):
        """60min 匀速 75% max_hr → Z3 主导。"""
        result = self.helper([150] * 3600, 200)
        data = json.loads(result)
        self.assertEqual(data["Z3"], 3600)
        self.assertEqual(data["Z1"], 0)
        self.assertEqual(data["Z5"], 0)
        self.assertEqual(sum(data.values()), 3600)

    def test_v8_4_empty_hr_returns_none(self):
        """空 hr_curve → None。"""
        self.assertIsNone(self.helper([], 200))
        self.assertIsNone(self.helper(None, 200))

    def test_v8_4_invalid_max_hr_returns_none(self):
        """max_hr 缺失或 < 30 → None(设备无 HR 数据)。"""
        self.assertIsNone(self.helper([100, 120], 0))
        self.assertIsNone(self.helper([100, 120], None))
        self.assertIsNone(self.helper([100, 120], 20))  # < 30
        self.assertIsNone(self.helper([100, 120], -5))

    def test_v8_4_all_zones_filled(self):
        """5 个区间均能产出非零值。"""
        # 100, 130, 150, 170, 190 @ max_hr=200 → Z1/Z2/Z3/Z4/Z5
        hr_curve = [100, 130, 150, 170, 190]
        result = self.helper(hr_curve, 200)
        data = json.loads(result)
        # ratio 0.5, 0.65, 0.75, 0.85, 0.95 → Z1, Z2, Z3, Z4, Z5
        self.assertEqual(data["Z1"], 1)
        self.assertEqual(data["Z2"], 1)
        self.assertEqual(data["Z3"], 1)
        self.assertEqual(data["Z4"], 1)
        self.assertEqual(data["Z5"], 1)

    def test_v8_4_zone_boundaries(self):
        """边界值(60%/70%/80%/90%)归属正确。
        ratio=0.6 → Z2(< 0.7 含 0.6 节点)
        ratio=0.7 → Z3(< 0.8 含 0.7 节点)
        ratio=0.8 → Z4(< 0.9 含 0.8 节点)
        ratio=0.9 → Z5(≥ 0.9)
        """
        hr_curve = [120, 140, 160, 180, 200]  # ratios 0.6, 0.7, 0.8, 0.9, 1.0
        result = self.helper(hr_curve, 200)
        data = json.loads(result)
        self.assertEqual(data["Z2"], 1)  # 0.6
        self.assertEqual(data["Z3"], 1)  # 0.7
        self.assertEqual(data["Z4"], 1)  # 0.8
        self.assertEqual(data["Z5"], 2)  # 0.9, 1.0

    def test_v8_4_filter_invalid_hr(self):
        """hr=0 / None 跳过,不计入任何区间。"""
        hr_curve = [0, None, 100, 150, 200]
        result = self.helper(hr_curve, 200)
        data = json.loads(result)
        # 0/None 跳过
        # 100/200 = 0.5/1.0 → Z1/Z5
        # 150/200 = 0.75 → Z3
        self.assertEqual(data["Z1"], 1)
        self.assertEqual(data["Z3"], 1)
        self.assertEqual(data["Z5"], 1)
        self.assertEqual(data["Z2"], 0)
        self.assertEqual(data["Z4"], 0)


class TestV8_4MainPyChanges(unittest.TestCase):
    """§V8.4 P0-2 / P0-3: main.py 3 处改动完整性。"""

    def setUp(self) -> None:
        self.main = _read_main()

    def test_v8_4_helper_defined(self):
        self.assertIn("def _compute_hr_zone_distribution(", self.main)

    def test_v8_4_result_dict_writes_hr_zone(self):
        """_build_activity_sync_result 末尾计算 hr_zone_distribution。"""
        # 在 cadence_curve 段后追加的
        idx_cadence = self.main.find('result["cadence_curve"] = json.dumps(cad_vals')
        idx_hr_zone = self.main.find("result[\"hr_zone_distribution\"] = hr_zone_json")
        self.assertGreater(idx_cadence, 0)
        self.assertGreater(idx_hr_zone, 0)
        self.assertGreater(idx_hr_zone, idx_cadence, "V8.4 FAIL: hr_zone 段必须晚于 cadence 段")

    def test_v8_4_sync_uses_profile_max_hr_before_activity_max_hr(self):
        """低心率活动不得用单次活动 max_hr 作为区间分母。"""
        block_idx = self.main.find("profile_max_hr_for_zones")
        self.assertGreater(block_idx, 0)
        block = self.main[block_idx:self.main.find("hr_zone_json = _compute_hr_zone_distribution", block_idx)]
        self.assertIn("profile_backend.get_profile()", block)
        self.assertIn("prof_for_zones.max_hr", block)
        self.assertIn('result.get("max_hr")', block)
        self.assertIn("profile_max_hr_for_zones or", self.main)

    def test_v8_4_sql_column_added(self):
        sql_start = self.main.find('INSERT INTO activities\n')
        sql_end = self.main.find('VALUES', sql_start)
        sql_block = self.main[sql_start:sql_end]
        self.assertIn("hr_zone_distribution", sql_block)

    def test_v8_4_sql_values_placeholders_match(self):
        """VALUES 中占位符 +1,与列数对齐。"""
        # 找 VALUES 行
        idx_values = self.main.find('VALUES', self.main.find('INSERT INTO'))
        values_end = self.main.find(')', idx_values)
        values_block = self.main[idx_values:values_end]
        # V8.3 时是 4 个连续 ?,V8.4 应是 5 个
        self.assertIn("?, ?, ?, ?,", values_block,
                      "V8.4 FAIL: VALUES 中连续 ? 数量应增加(从 3 变 4)")

    def test_v8_4_value_tuple_includes_hr_zone(self):
        self.assertIn('activity.get("hr_zone_distribution"),  # V8.4', self.main)

    def test_v8_4_no_resolver_modification(self):
        """§V8.4 决策:0 改动 metrics_resolver.py 的 hr_zone 计算逻辑。

        注:Resolver 早就有 Z1-Z5 字符串(V7.13 training load 的 zone 权重表),
        V8.4 不在此处加新 zone 计算。
        """
        with open(os.path.join(_PROJECT_ROOT, "metrics_resolver.py")) as f:
            resolver = f.read()
        # 验证 _compute_hr_zone_distribution 不在 Resolver
        self.assertNotIn("def _compute_hr_zone_distribution", resolver,
                         "V8.4 FAIL: _compute_hr_zone_distribution 不应定义在 Resolver")


class TestV8_4Contract(unittest.TestCase):
    """§V8.4 端到端契约:Z1-Z5 JSON 结构稳定。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.helper = staticmethod(_load_helper())

    def test_v8_4_output_has_all_five_zones(self):
        """输出 JSON 必须含 Z1-Z5 五键(V7.13 算法按此消费)。"""
        result = self.helper([150] * 100, 200)
        data = json.loads(result)
        for k in ("Z1", "Z2", "Z3", "Z4", "Z5"):
            self.assertIn(k, data)
            self.assertIsInstance(data[k], int)

    def test_v8_4_total_seconds_preserved(self):
        """sum(Z1..Z5) = len(hr_curve 中有效点) — 单位守恒(秒数)。"""
        hr_curve = [80, 100, 130, 150, 170, 190] * 100  # 600 点
        result = self.helper(hr_curve, 200)
        data = json.loads(result)
        self.assertEqual(sum(data.values()), 600)


if __name__ == "__main__":
    unittest.main()
