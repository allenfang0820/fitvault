"""LTTB 降采样算法测试

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层
覆盖: docs/v9_x_lttb_sampling_prompt.md §4.1.3 测试场景
"""

import math
import unittest
from metrics_resolver import MetricsResolver


class TestLttbSample(unittest.TestCase):
    """MetricsResolver._lttb_sample 单元测试"""

    # ---- T1: 空输入 ----
    def test_t1_empty_input(self):
        r = MetricsResolver._lttb_sample([], 60)
        self.assertEqual(r, [])

    # ---- T2: 单点 / 双点 ----
    def test_t2_single_point(self):
        pts = [{"lat": 39.96, "lon": 116.40}]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["lat"], 39.96)

    def test_t2_two_points(self):
        pts = [{"lat": 39.96, "lon": 116.40}, {"lat": 39.97, "lon": 116.41}]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 2)

    # ---- T3: 不需要采样 ----
    def test_t3_under_threshold(self):
        """50 < 60, 不采样, 返回原 50 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(50)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 50, "少于阈值应原样返回")

    def test_t3_equal_threshold(self):
        """60 == 60, 不采样, 返回原 60 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(60)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)

    # ---- T4: 标准 LTTB 降采样 ----
    def test_t4_oversample_returns_threshold(self):
        """5000 点 → 60 点 (LTTB 采样)"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(5000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60, f"应返回 60 个点, 实际 {len(r)}")

    # ---- T5: 起点 / 终点强制保留 ----
    def test_t5_endpoints_preserved(self):
        """起点 points[0] 和终点 points[n-1] 必须保留"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(5000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(r[0]["lat"], pts[0]["lat"], "起点必须保留")
        self.assertEqual(r[0]["lon"], pts[0]["lon"])
        self.assertEqual(r[-1]["lat"], pts[-1]["lat"], "终点必须保留")
        self.assertEqual(r[-1]["lon"], pts[-1]["lon"])

    # ---- T6: 弯道顶点保留 (曲率感知) ----
    def test_t6_curve_vertex_preserved(self):
        """发夹弯顶点必须被保留(曲率感知)"""
        # 构造: 直线 1000 点 + 急弯顶点 + 直线 1000 点
        pts = []
        # 前段直线
        for i in range(1000):
            pts.append({"lat": 39.96, "lon": 116.40 + i * 0.0001})
        # 急弯顶点 (lat 突变)
        pts.append({"lat": 40.50, "lon": 116.50})  # 顶点
        pts.append({"lat": 40.50, "lon": 116.50})  # 顶点
        # 后段直线
        for i in range(1000):
            pts.append({"lat": 40.50, "lon": 116.50 + i * 0.0001})

        r = MetricsResolver._lttb_sample(pts, 60)
        # 急弯顶点应在采样结果中
        vertex_found = any(abs(p["lat"] - 40.50) < 0.01 and abs(p["lon"] - 116.50) < 0.01 for p in r)
        self.assertTrue(vertex_found, "发夹弯顶点必须被保留")

    # ---- T7: 单调轨迹不退化 ----
    def test_t7_monotonic_no_exception(self):
        """南北向单调直线, 不抛异常, 返回 threshold 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40} for i in range(2000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)
        # 起点 / 终点保留
        self.assertEqual(r[0]["lat"], pts[0]["lat"])
        self.assertEqual(r[-1]["lat"], pts[-1]["lat"])

    # ---- T8: 圆形轨迹 (起点=终点附近) ----
    def test_t8_circular_track(self):
        """圆形操场轨迹, 起点终点同一区域"""
        pts = []
        for i in range(800):
            angle = i / 800 * 2 * math.pi
            pts.append({"lat": 39.96 + 0.001 * math.sin(angle), "lon": 116.40 + 0.001 * math.cos(angle)})
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)
        # 起点是 (39.96, 116.41), 终点是 (39.96, 116.41)
        self.assertAlmostEqual(r[0]["lat"], 39.96, places=4)
        self.assertAlmostEqual(r[-1]["lat"], 39.96, places=4)

    # ---- T9: 阈值边界 ----
    def test_t9_threshold_2(self):
        """threshold=2, 仅保留首尾"""
        pts = [{"lat": i, "lon": i} for i in range(100)]
        r = MetricsResolver._lttb_sample(pts, 2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["lat"], 0)
        self.assertEqual(r[1]["lat"], 99)

    def test_t9_threshold_3(self):
        """threshold=3, 保留首尾 + 1 个中间点"""
        pts = [{"lat": i, "lon": i} for i in range(100)]
        r = MetricsResolver._lttb_sample(pts, 3)
        self.assertEqual(len(r), 3)

    # ---- T10: 抽样后点数 ≤ 原始点数 ----
    def test_t10_shrink_guarantee(self):
        """任意 N, 采样后点数 <= N 且 <= threshold"""
        for n in [10, 100, 1000, 5000, 10000]:
            pts = [{"lat": i * 0.0001, "lon": i * 0.0001} for i in range(n)]
            r = MetricsResolver._lttb_sample(pts, 60)
            self.assertLessEqual(len(r), n, f"n={n} 时采样后不能超过原数")
            self.assertLessEqual(len(r), 60, f"n={n} 时采样后不能超过 threshold")


class TestSampleThumbnailPointsTransparent(unittest.TestCase):
    """main.py._sample_thumbnail_points 防腐层自检 (1 行透传)"""

    def test_sample_thumbnail_points_is_one_line(self):
        """§V4.0 防腐层契约: _sample_thumbnail_points 必须是 1 行透传"""
        import ast
        from pathlib import Path
        main_path = Path(__file__).resolve().parent.parent / "main.py"
        src = main_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_sample_thumbnail_points":
                # 计算非 docstring 语句数
                non_doc = [s for s in node.body if not (
                    isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                )]
                # 容忍 docstring + 1 行 return = 2 条语句
                self.assertEqual(
                    len(non_doc), 1,
                    f"main.py._sample_thumbnail_points 防腐层被破坏: "
                    f"实际 {len(non_doc)} 条非 docstring 语句 (期望 1 行 return)"
                )


if __name__ == "__main__":
    unittest.main()
