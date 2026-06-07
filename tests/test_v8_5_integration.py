"""
V8.5 集成测试:trend 字段在主路径 (_build_fatigue_review_snapshot) 中可消费
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


def _get_fn_body(content: str, fn_name: str) -> str:
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(content, node) or ""
    return ""


class TestV8_5AllMetricsHaveTrend(unittest.TestCase):
    """§V8.5: 7 个指标都有 trend 字段(对齐契约)。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.fn_src = _get_fn_body(self.main, "_build_fatigue_review_snapshot")

    def _has_trend(self, metric_name: str, window: int = 5000) -> bool:
        """在 metric 注入段后 5000 字符内查 'trend'。"""
        idx = self.fn_src.find(f'metrics["{metric_name}"]')
        if idx < 0:
            return False
        block = self.fn_src[idx:idx + window]
        return '"trend"' in block

    def test_v8_5_hr_drift_trend(self):
        self.assertTrue(self._has_trend("hr_drift"))

    def test_v8_5_decoupling_trend(self):
        self.assertTrue(self._has_trend("decoupling"))

    def test_v8_5_bonk_risk_trend(self):
        self.assertTrue(self._has_trend("bonk_risk"))

    def test_v8_5_events_trend(self):
        self.assertTrue(self._has_trend("events"))

    def test_v8_5_efficiency_trend(self):
        self.assertTrue(self._has_trend("efficiency"))

    def test_v8_5_durability_trend(self):
        self.assertTrue(self._has_trend("durability"))

    def test_v8_5_cadence_stability_trend(self):
        self.assertTrue(self._has_trend("cadence_stability"))

    def test_v8_5_training_load_trend(self):
        self.assertTrue(self._has_trend("training_load"))


class TestV8_5TrendSourceLabels(unittest.TestCase):
    """§V8.5: trend 字段有可追溯的 source 标签。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.fn_src = _get_fn_body(self.main, "_build_fatigue_review_snapshot")

    def test_v8_5_cadence_trend_source(self):
        """cadence trend source 标签 = v8_5_21d_median_cadence_cv。"""
        idx = self.fn_src.find('metrics["cadence_stability"]')
        block = self.fn_src[idx:idx + 3000]
        self.assertIn("v8_5_21d_median_cadence_cv", block)

    def test_v8_5_load_trend_source(self):
        """load trend source 标签 = v8_5_21d_median_daily_load。"""
        idx = self.fn_src.find('metrics["training_load"]')
        block = self.fn_src[idx:idx + 5000]
        self.assertIn("v8_5_21d_median_daily_load", block)


class TestV8_5V7BaselineUnchanged(unittest.TestCase):
    """§V8.5: 4 个老指标的 trend 注入块(V7.9/V7.14 范围)未动。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.fn_src = _get_fn_body(self.main, "_build_fatigue_review_snapshot")

    def test_v8_5_efficiency_uses_v714_baseline(self):
        idx = self.fn_src.find('metrics["efficiency"]')
        block = self.fn_src[idx:idx + 2000]
        self.assertIn('"source": "v7_14_baseline"', block,
                      "V8.5 FAIL: efficiency.source 不应改")

    def test_v8_5_durability_uses_v714_baseline(self):
        idx = self.fn_src.find('metrics["durability"]')
        block = self.fn_src[idx:idx + 2000]
        self.assertIn('"source": "v7_14_baseline"', block,
                      "V8.5 FAIL: durability.source 不应改")


if __name__ == "__main__":
    unittest.main()
