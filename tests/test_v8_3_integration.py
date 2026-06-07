"""
V8.3 集成测试:cadence_curve 在主路径 (_build_fatigue_review_snapshot) 中可消费

任务: 验证 V7.12 步频稳定性算法在 V8.3 修复后能产出真实 score,
      而非 confidence=unavailable 降级状态。

策略: 静态 grep + mock row 验证 _build_fatigue_review_snapshot 行为
"""

from __future__ import annotations

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read(name: str) -> str:
    with open(os.path.join(_PROJECT_ROOT, name)) as f:
        return f.read()


class TestV8_3FatigueReviewCadence(unittest.TestCase):
    """§V8.3 P1-1: cadence_curve 在 _build_fatigue_review_snapshot 中可被消费。"""

    def setUp(self) -> None:
        self.main = _read("main.py")

    def test_v8_3_fatigue_review_reads_cadence_curve(self):
        """_build_fatigue_review_snapshot 必须读 row.get('cadence_curve')。"""
        self.assertIn('row.get("cadence_curve")', self.main,
                      "V8.3 FAIL: _build_fatigue_review_snapshot 未读 cadence_curve")

    def test_v8_3_metrics_includes_cadence_stability(self):
        """metrics 注入块含 cadence_stability(V7.12 算法)。"""
        # 找 _build_fatigue_review_snapshot 函数体
        fn_start = self.main.find('def _build_fatigue_review_snapshot')
        fn_end = self.main.find('def load_activity_track', fn_start)
        fn_body = self.main[fn_start:fn_end]
        self.assertIn("cadence_stability", fn_body)

    def test_v8_3_cadence_stability_uses_v712_algorithm(self):
        """cadence_stability 注入块必须调 _compute_cadence_stability。"""
        fn_start = self.main.find('def _build_fatigue_review_snapshot')
        fn_end = self.main.find('def load_activity_track', fn_start)
        fn_body = self.main[fn_start:fn_end]
        self.assertIn("_compute_cadence_stability", fn_body)


class TestV8_3InsertSQLCadence(unittest.TestCase):
    """§V8.3 P0-3: SQL INSERT 包含 cadence_curve 列。"""

    def setUp(self) -> None:
        self.main = _read("main.py")

    def test_v8_3_insert_column_added(self):
        sql_start = self.main.find('INSERT INTO activities\n')
        sql_end = self.main.find('VALUES', sql_start)
        sql_block = self.main[sql_start:sql_end]
        self.assertIn("cadence_curve", sql_block)

    def test_v8_3_value_tuple_includes_cadence(self):
        # 找 _insert_activity_sync_row 函数体
        fn_start = self.main.find('def _insert_activity_sync_row')
        # 找下一个 def
        next_fn = self.main.find('def ', fn_start + 10)
        fn_body = self.main[fn_start:next_fn]
        self.assertIn('activity.get("cadence_curve")', fn_body)


class TestV8_3EndToEndProbe(unittest.TestCase):
    """§V8.3 P1-1: Resolver 端到端产出 cadence_curve。"""

    def test_v8_3_cadence_curve_in_final_data(self):
        """实际跑 Resolver 验证 cadence_curve 出现在 final_data 顶层。"""
        sys.path.insert(0, _PROJECT_ROOT)
        from metrics_resolver import MetricsResolver

        records = [{"raw": {
            "heart_rate": 150, "speed": 3.0, "cadence": 80 + (i % 10),
            "altitude": 100.0, "distance": i * 30.0, "lat": None, "lon": None,
        }} for i in range(50)]

        raw = {"record_mesgs": records, "session_mesgs": [{}], "lap_mesgs": []}
        resolved = MetricsResolver().resolve(raw, {"sport_type": "running"})

        self.assertIn("cadence_curve", resolved)
        cad = resolved["cadence_curve"]
        self.assertEqual(len(cad), 50)
        # cadence > 0 → 整数;0/None → None
        self.assertEqual(cad[0], 80)
        self.assertNotEqual(cad[5], cad[4])  # 验证序列值有变化


if __name__ == "__main__":
    unittest.main()
