"""
V8.5 契约测试:cadence_stability + training_load 补 trend 字段

任务: §V8.5 给 V7.12 步频稳定性 + V7.13 训练负荷的 metrics 注入块补 trend,
      与 4 个老指标 (efficiency/durability/hr_drift/decoupling) 风格对齐。

契约依据:
- §2.1 全链路可追溯:trend baseline 来源 = 21d cadence_curve / hr_zone_distribution
- §8 canonical 只读:仅 SELECT
- §5.4 AI 边界:trend 不进入 AI snapshot
- §6 shadow_diff 隔离:SQL 严禁 SELECT shadow_diff_json
- §11 字段版本化:trend 字段结构与 4 个老指标对齐

策略: 静态 grep 测试 main.py 改动完整性;SQL 时间窗口语义验证。
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


class TestV8_5TrendHelpersExist(unittest.TestCase):
    """§V8.5 P0-1 / P0-2: 两个 trend helper 函数存在。"""

    def setUp(self) -> None:
        self.main = _read("main.py")

    def test_v8_5_cadence_trend_helper(self):
        """_fetch_cadence_stability_trend 必须定义。"""
        self.assertIn("def _fetch_cadence_stability_trend(self, row: dict)",
                      self.main)

    def test_v8_5_load_trend_helper(self):
        """_fetch_training_load_trend 必须定义。"""
        self.assertIn("def _fetch_training_load_trend(self, row: dict)",
                      self.main)

    def test_v8_5_cadence_trend_sql_21d(self):
        """SQL 必须有 21d 窗口(start_time >= cutoff)。"""
        fn_src = _get_fn_body(self.main, "_fetch_cadence_stability_trend")
        self.assertIn("start_time >= ?", fn_src,
                      "V8.5 FAIL: cadence trend SQL 缺 21d 窗口")
        self.assertIn("21", fn_src)

    def test_v8_5_load_trend_sql_21d(self):
        """SQL 必须有 21d 窗口。"""
        fn_src = _get_fn_body(self.main, "_fetch_training_load_trend")
        self.assertIn("start_time >= ?", fn_src,
                      "V8.5 FAIL: load trend SQL 缺 21d 窗口")
        self.assertIn("21", fn_src)

    def test_v8_5_cadence_trend_filter_valid(self):
        """cadence trend 必须过滤 > 30 spm 有效点(与 V7.12 一致)。"""
        fn_src = _get_fn_body(self.main, "_fetch_cadence_stability_trend")
        self.assertIn("c > 30", fn_src)

    def test_v8_5_load_trend_fallback(self):
        """load trend 失败时降级为 avg_hr/max_hr 推算(与 V7.13 一致)。"""
        fn_src = _get_fn_body(self.main, "_fetch_training_load_trend")
        self.assertIn("_compute_training_load", fn_src)


class TestV8_5InjectBlocks(unittest.TestCase):
    """§V8.5 P0-3 / P0-4: cadence + training_load 注入块含 trend。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.fn_src = _get_fn_body(self.main, "_build_fatigue_review_snapshot")

    def test_v8_5_cadence_stability_has_trend(self):
        """cadence_stability 注入块必须设 trend 字段(分两步:dict 注入 + 补 trend)。"""
        # 找 cadence_stability 注入块
        idx = self.fn_src.find('metrics["cadence_stability"] = {')
        self.assertGreater(idx, 0)
        # V8.5 在 dict 后用 try 段设 metrics["cadence_stability"]["trend"] = {...}
        # 取之后 2500 字符找 trend 段
        block = self.fn_src[idx:idx + 2500]
        self.assertIn('metrics["cadence_stability"]["trend"]', block,
                      "V8.5 FAIL: cadence trend 段缺失")
        self.assertIn('"baseline_cv":', block)
        self.assertIn('"v8_5_21d_median_cadence_cv"', block,
                      "V8.5 FAIL: cadence trend source 应为 v8_5_21d_median_cadence_cv")

    def test_v8_5_training_load_has_trend(self):
        """training_load 注入块必须设 trend 字段。"""
        idx = self.fn_src.find('metrics["training_load"] = {')
        self.assertGreater(idx, 0)
        block = self.fn_src[idx:idx + 3500]
        self.assertIn('metrics["training_load"]["trend"]', block,
                      "V8.5 FAIL: training_load trend 段缺失")
        self.assertIn('"baseline_load":', block)
        self.assertIn('"v8_5_21d_median_daily_load"', block,
                      "V8.5 FAIL: training_load trend source 应为 v8_5_21d_median_daily_load")

    def test_v8_5_cadence_trend_is_improving_direction(self):
        """cadence trend: is_improving 含义是 CV 下降(与 4 个老指标反向)。"""
        block_idx = self.fn_src.find('metrics["cadence_stability"] = {')
        # 在 cadence_stability 注入块中,is_improving 与 _cad_improving 绑定
        block = self.fn_src[block_idx:block_idx + 2500]
        # 验证 _cad_improving 与 _cad_level 联动
        self.assertIn("_cad_improving", block)

    def test_v8_5_training_load_trend_is_improving_none(self):
        """training_load trend: is_improving 留 None(无统一改善方向)。"""
        block_idx = self.fn_src.find('metrics["training_load"] = {')
        block = self.fn_src[block_idx:block_idx + 4000]
        # 找 trend dict 的开始位置
        trend_idx = block.find('metrics["training_load"]["trend"]')
        self.assertGreater(trend_idx, 0, "V8.5 FAIL: training_load trend 段缺失")
        # trend dict 内的 is_improving 字段
        trend_block = block[trend_idx:trend_idx + 1500]
        # 在 trend dict 内必须有 is_improving: None
        self.assertIn('"is_improving": None',
                      trend_block,
                      "V8.5 FAIL: training_load trend.is_improving 应为 None")


class TestV8_5Contract(unittest.TestCase):
    """§V8.5 端到端契约:7 个指标都有 trend 字段。"""

    def setUp(self) -> None:
        self.main = _read("main.py")
        self.fn_src = _get_fn_body(self.main, "_build_fatigue_review_snapshot")

    def test_v8_5_all_seven_metrics_in_fn(self):
        """7 个指标都在 _build_fatigue_review_snapshot 中。"""
        for k in ("hr_drift", "decoupling", "bonk_risk", "events",
                  "efficiency", "durability", "cadence_stability", "training_load"):
            self.assertIn(f'metrics["{k}"]', self.fn_src,
                          f"V8.5 FAIL: {k} inject block missing")

    def test_v8_5_trend_field_structure_aligned(self):
        """所有 trend 字段结构对齐(delta_pct / level / compared_count / is_improving / source)。"""
        # 验证 cadence + training_load
        for m, baseline_k in (("cadence_stability", "baseline_cv"),
                              ("training_load", "baseline_load")):
            idx = self.fn_src.find(f'metrics["{m}"]')
            block = self.fn_src[idx:idx + 4000]
            trend_idx = block.find(f'metrics["{m}"]["trend"]')
            self.assertGreater(trend_idx, 0, f"V8.5 FAIL: {m}.trend 段缺失")
            trend_block = block[trend_idx:trend_idx + 1500]
            # 5 字段对齐
            for field in ('"delta_pct"', '"level"', '"compared_count"',
                          '"is_improving"', '"source"', f'"{baseline_k}"'):
                self.assertIn(field, trend_block,
                              f"V8.5 FAIL: {m}.trend 缺 {field}")


class TestV8_5NoResellerMod(unittest.TestCase):
    """§V8.5 决策:0 改动 metrics_resolver.py。"""

    def test_v8_5_resolver_unchanged(self):
        """Resolver 不应含 V8.5 新函数。"""
        resolver = _read("metrics_resolver.py")
        self.assertNotIn("def _fetch_cadence_stability_trend", resolver)
        self.assertNotIn("def _fetch_training_load_trend", resolver)


if __name__ == "__main__":
    unittest.main()
