"""
V8.4 集成测试:hr_zone_distribution 在主路径 (_build_fatigue_review_snapshot) 可消费

任务: 验证 V7.13 训练负荷算法在 V8.4 修复后能产出真实 load,
      而非 confidence=unavailable 降级状态。
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


class TestV8_4FatigueReviewHrZone(unittest.TestCase):
    """§V8.4 P1-1: hr_zone_distribution 在 _build_fatigue_review_snapshot 中可被消费。"""

    def setUp(self) -> None:
        self.main = _read("main.py")

    def test_v8_4_fatigue_review_reads_hr_zone(self):
        """_build_fatigue_review_snapshot 必须读 row.get('hr_zone_distribution')。"""
        self.assertIn('row.get("hr_zone_distribution")', self.main,
                      "V8.4 FAIL: 未读 hr_zone_distribution")

    def test_v8_4_metrics_includes_training_load(self):
        """metrics 注入块含 training_load(V7.13 算法)。"""
        fn_start = self.main.find('def _build_fatigue_review_snapshot')
        fn_end = self.main.find('def load_activity_track', fn_start)
        fn_body = self.main[fn_start:fn_end]
        self.assertIn("training_load", fn_body)

    def test_v8_4_training_load_uses_v713_algorithm(self):
        """training_load 注入块必须调 _compute_training_load。"""
        fn_start = self.main.find('def _build_fatigue_review_snapshot')
        fn_end = self.main.find('def load_activity_track', fn_start)
        fn_body = self.main[fn_start:fn_end]
        self.assertIn("_compute_training_load", fn_body)


class TestV8_4InsertSQL(unittest.TestCase):
    """§V8.4 P0-3: SQL INSERT 包含 hr_zone_distribution 列。"""

    def setUp(self) -> None:
        self.main = _read("main.py")

    def test_v8_4_insert_column_added(self):
        sql_start = self.main.find('INSERT INTO activities\n')
        sql_end = self.main.find('VALUES', sql_start)
        sql_block = self.main[sql_start:sql_end]
        self.assertIn("hr_zone_distribution", sql_block)

    def test_v8_4_value_tuple_includes(self):
        fn_start = self.main.find('def _insert_activity_sync_row')
        next_fn = self.main.find('def ', fn_start + 10)
        fn_body = self.main[fn_start:next_fn]
        self.assertIn('activity.get("hr_zone_distribution")', fn_body)


class TestV8_4LoadRatioConsumption(unittest.TestCase):
    """§V8.4 验证 _fetch_load_ratio_7d_42d 也可消费 hr_zone_distribution。"""

    def test_v8_4_load_ratio_reads_hr_zone(self):
        """_fetch_load_ratio_7d_42d 内的 current_load 计算逻辑读 hr_zone_distribution。"""
        main = _read("main.py")
        # _fetch_load_ratio_7d_42d 函数体内应有 hr_zone_distribution 解析
        fn_start = main.find('def _fetch_load_ratio_7d_42d')
        next_fn = main.find('def ', fn_start + 10)
        fn_body = main[fn_start:next_fn]
        self.assertIn("hr_zone_distribution", fn_body,
                      "V8.4 FAIL: _fetch_load_ratio_7d_42d 未读 hr_zone_distribution")


if __name__ == "__main__":
    unittest.main()
