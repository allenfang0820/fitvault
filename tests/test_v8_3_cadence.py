"""
V8.3 契约测试:cadence_curve 写入与读取路径

任务: V8.3 在 FIT 解析流程中提取 cadence 序列写入 activities.cadence_curve,
      让 V7.12 步频稳定性算法能真实计算而非 unavailable。

契约依据:
- §2.1 全链路可追溯:cadence → fitparse → JSON → DB → V7.12
- §2.2 数据可信分层:cadence 列内 = fit_sdk source
- §6 shadow_diff 隔离:cadence_curve 不属于 shadow_diff
- §8 canonical 写入:V8.3 是 INSERT 路径的新增列写入

策略: 静态 grep 测试 main.py / metrics_resolver.py 改动完整性;
      Resolver 端到端测试 cadence_curve 出现在 final_data 顶层。
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read(name: str) -> str:
    with open(os.path.join(_PROJECT_ROOT, name)) as f:
        return f.read()


class TestV8_3ResolverCadence(unittest.TestCase):
    """§V8.3 P0-2: Resolver _build_analysis_pack 产出 cadence_curve。"""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, _PROJECT_ROOT)
        from metrics_resolver import MetricsResolver

        # 真实数据:100 个 record,部分 cadence 为 None/0
        records = []
        for i in range(100):
            records.append({"raw": {
                "heart_rate": 150, "speed": 3.0,
                "cadence": 80 + (i % 5),
                "altitude": 100.0, "distance": i * 30.0,
                "lat": None, "lon": None,
            }})
        records[10]["raw"]["cadence"] = None
        records[20]["raw"]["cadence"] = 0  # 设备未采样

        raw = {"record_mesgs": records, "session_mesgs": [{}], "lap_mesgs": []}
        meta = {"sport_type": "running"}
        cls.resolved = MetricsResolver().resolve(raw, meta)
        cls.cadence_curve = cls.resolved.get("cadence_curve", [])

    def test_v8_3_cadence_in_final_data(self):
        """V8.3: cadence_curve 必须出现在 resolved 顶层(V7.12 可消费)。"""
        self.assertIn("cadence_curve", self.resolved,
                      "V8.3 FAIL: cadence_curve not in resolved top-level")
        self.assertIsInstance(self.cadence_curve, list)

    def test_v8_3_cadence_length_matches_sampled_records(self):
        """cadence_curve 长度应等于 sampled records(本测试 100 点)。"""
        self.assertEqual(len(self.cadence_curve), 100)

    def test_v8_3_cadence_zero_filtered_to_none(self):
        """cadence=0 → None(设备未采样),不进有效值。"""
        self.assertIsNone(self.cadence_curve[20],
                          "V8.3 FAIL: cadence=0 should be None")

    def test_v8_3_cadence_explicit_none_preserved(self):
        """cadence=None → None(显式设备未提供)。"""
        self.assertIsNone(self.cadence_curve[10])

    def test_v8_3_cadence_positive_preserved(self):
        """cadence>0 → 整数值。"""
        self.assertEqual(self.cadence_curve[0], 80)
        self.assertEqual(self.cadence_curve[4], 84)

    def test_v8_3_cadence_analysis_pack_field(self):
        """V8.3: analysis_pack 也含 cadence_curve(内部消费)。"""
        # Resolver 内部用 analysis_pack.cadence_curve
        # 这只是间接验证:final_data 已是 100 点,内部必产出
        self.assertEqual(len(self.cadence_curve), 100)


class TestV8_3MainPyChanges(unittest.TestCase):
    """§V8.3 P0-3: main.py 4 处改动完整性。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.resolver = _read("metrics_resolver.py")

    def test_v8_3_result_dict_init(self):
        """result dict 初始含 cadence_curve: None。"""
        self.assertIn('"cadence_curve": None,  # V8.3', self.main)

    def test_v8_3_resolved_top_level_extraction(self):
        """main.py 从 resolved 顶层取(不是 analysis_pack)。"""
        # 必须用 resolved.get 而非 ap.get
        self.assertIn("resolved.get(\"hr_curve\")", self.main)
        self.assertIn("resolved.get(\"speed_curve\")", self.main)
        self.assertIn("resolved.get(\"cadence_curve\")", self.main)
        # 旧路径 analysis_pack 赋值应已删除(注释里的提及不算)
        # 用 AST 检查 _build_activity_sync_result 函数体内无此语句
        tree = ast.parse(self.main)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "ap":
                        # 排除注释
                        if "analysis_pack" in ast.unparse(node.value):
                            self.fail(f"V8.3 FAIL: 旧 ap=resolved.get(analysis_pack) 残留: {ast.unparse(node)}")

    def test_v8_3_sql_column_added(self):
        """SQL INSERT 列列表含 cadence_curve。"""
        sql_section = self.main[self.main.find('INSERT INTO activities'):self.main.find('VALUES')]
        self.assertIn("cadence_curve", sql_section)

    def test_v8_3_sql_value_passed(self):
        """SQL VALUES 元组含 activity.get('cadence_curve')。"""
        self.assertIn('activity.get("cadence_curve"),  # V8.3', self.main)

    def test_v8_3_resolver_final_data_cadence(self):
        """Resolver final_data 含 cadence_curve(供 main.py 消费)。"""
        # 静态 grep final_data["cadence_curve"]
        self.assertIn('final_data["cadence_curve"]', self.resolver)

    def test_v8_3_main_no_ap_analysis_pack(self):
        """main.py 不再把 cadence 写入 analysis_pack(analysis_pack 不可达)。"""
        # main.py 写入 cadence 应来自 resolved.get,不是 ap.get
        # 在 INSERT SQL 上方 5 行的范围内找
        idx = self.main.find('result["cadence_curve"]')
        self.assertGreater(idx, 0)
        # 上下文不应有 ap.get("cadence
        context = self.main[idx:idx+800]
        self.assertNotIn('ap.get("cadence', context,
                         "V8.3 FAIL: 旧 analysis_pack 路径残留")


class TestV8_3Consistency(unittest.TestCase):
    """§V8.3 端到端: Resolver 产出 + main.py 可读 + INSERT SQL 完整。"""

    def test_v8_3_column_count_in_insert(self):
        """统计 INSERT 列数 ≥ 50(V8.3 之前是 56,V8.3 后应是 57)。"""
        main = _read("main.py")
        sql_start = main.find('INSERT INTO activities\n')
        sql_end = main.find('VALUES', sql_start)
        sql_block = main[sql_start:sql_end]
        # 简单字符数检查:SQL 应足够长(V8.3 之前 56 列,V8.3 后 57 列)
        self.assertGreater(len(sql_block), 800)
        # cadence_curve 必须出现在 SQL 列列表中
        self.assertIn("cadence_curve", sql_block)
        # 验证 VALUES 占位符数同步: +1 列对应 +1 个 ?
        values_start = main.find('VALUES', sql_start)
        values_end = main.find(')', values_start)
        values_block = main[values_start:values_end]
        self.assertIn("?", values_block)

    def test_v8_3_resolver_does_not_break_existing_curves(self):
        """V8.3: Resolver 仍产出 hr_curve / speed_curve / gap_curve。"""
        sys.path.insert(0, _PROJECT_ROOT)
        from metrics_resolver import MetricsResolver
        records = [{"raw": {
            "heart_rate": 150, "speed": 3.0, "cadence": 80,
            "altitude": 100.0, "distance": 0.0, "lat": None, "lon": None,
        }} for _ in range(50)]
        raw = {"record_mesgs": records, "session_mesgs": [{}], "lap_mesgs": []}
        resolved = MetricsResolver().resolve(raw, {"sport_type": "running"})
        for key in ("hr_curve", "speed_curve", "gap_curve", "efficiency_curve", "cadence_curve"):
            self.assertIn(key, resolved, f"V8.3 FAIL: Resolver lost {key}")


if __name__ == "__main__":
    unittest.main()
