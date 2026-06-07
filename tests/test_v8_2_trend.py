"""
V8.2 契约测试:_fetch_historical_metrics_avg 重写 + compute helpers

任务: §V8.2 修复 _fetch_historical_metrics_avg 的 storage_model 死依赖,
      从 hr_curve / speed_curve 列直接计算历史 baseline。
      一次性修复 D2(4 个 trend 静默失败)缺陷。

契约依据:
- §2.1 全链路可追溯:trend 来源 = hr_curve + speed_curve(最终来源 = FIT 解析)
- §8 canonical 只读:纯 SELECT + 纯计算,不写 activities 表
- §7.2 安全:返回 sample_size 而非 raw rows

策略: 计算函数为 module-level,可直接 import 测试;
      趋势函数为 Api class 方法,用静态 AST 检查。
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read_main_py() -> str:
    with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
        return f.read()


def _get_function_source(content: str, fn_name: str) -> str:
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(content, node) or ""
    return ""


class TestV8_2ComputeHelpers(unittest.TestCase):
    """§V8.2 P0-1: _compute_hr_drift_from_curve / _compute_speed_decay_from_curve 计算精度。"""

    @classmethod
    def setUpClass(cls) -> None:
        # 动态加载 compute helpers(避免 import main 触发 pywebview)
        content = _read_main_py()
        hr_drift_fn = _get_function_source(content, "_compute_hr_drift_from_curve")
        speed_decay_fn = _get_function_source(content, "_compute_speed_decay_from_curve")
        # exec into a stub
        import types as _t
        stub = _t.ModuleType("v82_stub")
        exec(compile(hr_drift_fn, "main.py:_compute_hr_drift_from_curve", "exec"), stub.__dict__)
        exec(compile(speed_decay_fn, "main.py:_compute_speed_decay_from_curve", "exec"), stub.__dict__)
        cls._hr_drift = staticmethod(stub._compute_hr_drift_from_curve)
        cls._speed_decay = staticmethod(stub._compute_speed_decay_from_curve)

    def test_hr_drift_rising(self):
        """心率从 120 线性上升至 180 → 漂移 > 0。"""
        curve = [120 + i * 0.3 for i in range(200)]  # 120→180
        result = self._hr_drift(curve)
        self.assertIsNotNone(result)
        self.assertGreater(result, 10)  # ~45%

    def test_hr_drift_flat(self):
        """心率恒定 150 → 漂移 ≈ 0。"""
        curve = [150] * 200
        result = self._hr_drift(curve)
        self.assertIsNotNone(result)
        self.assertLess(abs(result), 1.0)

    def test_hr_drift_too_short(self):
        """少于 20 点 → None。"""
        result = self._hr_drift([150] * 10)
        self.assertIsNone(result)

    def test_hr_drift_all_zero(self):
        """全部 0 值 → None(first_mean=0)。"""
        result = self._hr_drift([0] * 200)
        self.assertIsNone(result)

    def test_speed_decay_dropping(self):
        """速度从 3.5 下降至 2.5 → 衰减 > 0。"""
        curve = [3.5 - i * 0.005 for i in range(200)]  # 3.5→2.5
        result = self._speed_decay(curve)
        self.assertIsNotNone(result)
        self.assertGreater(result, 5)  # ~25%

    def test_speed_decay_negative_split(self):
        """后程加速 → 衰减 < 0(负配速)。"""
        curve = [2.5 + i * 0.005 for i in range(200)]  # 2.5→3.5
        result = self._speed_decay(curve)
        self.assertIsNotNone(result)
        self.assertLess(result, 0)

    def test_speed_decay_too_short(self):
        """少于 20 点 → None。"""
        result = self._speed_decay([3.0] * 10)
        self.assertIsNone(result)


class TestV8_2HistoricalMetricsAvg(unittest.TestCase):
    """§V8.2 P0-1: _fetch_historical_metrics_avg 重写验证(静态检查 + 逻辑)。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        self.fn_src = _get_function_source(self.content, "_fetch_historical_metrics_avg")

    def test_no_storage_model_in_sql(self):
        """SQL 段不含 storage_model。"""
        sql_section = self.fn_src[self.fn_src.find("SELECT"):self.fn_src.rfind("LIMIT")]
        self.assertNotIn("storage_model", sql_section)

    def test_query_uses_hr_curve(self):
        """SQL SELECT 含 hr_curve, speed_curve。"""
        self.assertIn("hr_curve", self.fn_src)
        self.assertIn("speed_curve", self.fn_src)

    def test_processing_uses_safe_json_list(self):
        """曲线列用 _safe_json_list 安全解析。"""
        self.assertIn('_safe_json_list(r["hr_curve"])', self.fn_src)
        self.assertIn('_safe_json_list(r["speed_curve"])', self.fn_src)

    def test_processing_calls_compute_helpers(self):
        """计算逻辑调 _compute_hr_drift_from_curve + _compute_speed_decay_from_curve。"""
        self.assertIn("_compute_hr_drift_from_curve", self.fn_src)
        self.assertIn("_compute_speed_decay_from_curve", self.fn_src)

    def test_return_format_has_four_keys(self):
        """返回值含 hr_drift_pct / decoupling_pct / bonk_count / sample_size。"""
        for k in ('"hr_drift_pct"', '"decoupling_pct"', '"bonk_count"', '"sample_size"'):
            self.assertIn(k, self.fn_src, f"return key {k} missing")

    def test_bonk_count_hardcoded_zero(self):
        """bonk_count = 0(V8.2: 无法从曲线列计算,V8.x 扩展)。"""
        self.assertIn("bonk_count", self.fn_src)
        # "bonk_count": 0 在代码中，但带逗号和空格；只验证存在
        self.assertIn(": 0", self.fn_src.split('"bonk_count"')[1][:10])

    def test_empty_rows_returns_early(self):
        """0 行时提前返回 None 值。"""
        self.assertIn('"sample_size": 0', self.fn_src)


class TestV8_2ConsumerCompatibility(unittest.TestCase):
    """§V8.2 P0-2: 消费端 4 键不变。"""

    def setUp(self) -> None:
        self.content = _read_main_py()
        start = self.content.find('historical_avg = self._fetch_historical_metrics_avg')
        end = self.content.find('V7.9 指标 5', start)
        self.consumer_src = self.content[start:end]

    def test_consumer_reads_hr_drift_pct(self):
        self.assertIn("historical_avg.get(\"hr_drift_pct\")", self.consumer_src)

    def test_consumer_reads_decoupling_pct(self):
        self.assertIn("historical_avg.get(\"decoupling_pct\")", self.consumer_src)

    def test_consumer_reads_bonk_count(self):
        self.assertIn("historical_avg.get(\"bonk_count\"", self.consumer_src)

    def test_consumer_reads_sample_size(self):
        self.assertIn("historical_avg.get(\"sample_size\"", self.consumer_src)


if __name__ == "__main__":
    unittest.main()
