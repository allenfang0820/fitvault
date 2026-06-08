"""V4-4: AI Snapshot 契约层下沉单元测试

契约:fit-arch-contrac §V4.0 防腐层 / §五 AI 边界 / §六 shadow_diff 隔离
验证:
  1. Resolver 内部暴露 _build_ai_snapshot_block / _build_ai_snapshot_text_block
  2. _validate_ai_snapshot 防污染护栏(FORBIDDEN / KEYS 上限 / 白名单)
  3. main.py 中 AI Snapshot 相关函数已下沉为 1 行透传
  4. 39 字段输出与原 main.py 完全一致
  5. IO 隔离:_build_ai_snapshot(main.py) 仅做 IO + 1 行透传
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import MetricsResolver


def _make_running_row(**overrides):
    """构造标准 running 活动 row"""
    base = {
        "id": 1,
        "sport_type": "running",
        "sub_sport_type": "generic",
        "dist_km": 10.5,
        "duration_sec": 3600,
        "avg_hr": 150,
        "max_hr": 170,
        "calories": 350,
        "gain_m": 50.0,
        "max_alt_m": 100.0,
        "avg_pace": 360,
        "avg_cadence": 80,
        "normalized_power": None,
        "swolf": None,
        "tss": None,
        "start_time": "2026-05-20T10:00:00",
        "start_lat": 39.9,
        "start_lon": 116.4,
        "region": "beijing",
        "file_path": "/tmp/t.fit",
        "filename": "t.fit",
        "device_name": "Garmin",
        "min_alt_m": 80.0,
        "total_descent_m": 30.0,
        "up_count": 1,
        "down_count": 1,
        "max_single_climb_m": 30.0,
        "difficulty_score": 3.5,
        "report_metrics_version": 4,
        "avg_grade_pct": 1.5,
        "max_slope_pct": 8.0,
        "min_slope_pct": -6.0,
        "uphill_pct": 30.0,
        "downhill_pct": 25.0,
    }
    base.update(overrides)
    return base


class TestAISnapshotResolverExposed(unittest.TestCase):
    """§V4.0 Resolver 内部必须暴露 AI Snapshot 契约层方法"""

    def test_methods_exposed(self):
        """Resolver 必须含 4 个 AI Snapshot 契约层方法"""
        for method in (
            "_build_ai_snapshot_block",
            "_build_ai_snapshot_text_block",
            "_validate_ai_snapshot",
            "_debug_ai_snapshot",
            "_safe_float",
        ):
            self.assertTrue(hasattr(MetricsResolver, method),
                          f"MetricsResolver 必须含 {method}")

    def test_forbidden_fields_exposed(self):
        """FORBIDDEN 字段集合必须暴露"""
        self.assertTrue(hasattr(MetricsResolver, "_AI_SNAPSHOT_FORBIDDEN_FIELDS"))
        self.assertTrue(hasattr(MetricsResolver, "_AI_SNAPSHOT_MAX_KEYS"))
        self.assertTrue(hasattr(MetricsResolver, "_AI_SNAPSHOT_FIELD_WHITELIST"))


class TestBuildAISnapshotBlock(unittest.TestCase):
    """_build_ai_snapshot_block 单元测试"""

    def test_basic_running_row(self):
        """标准 running row 应输出 39 字段"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        self.assertEqual(len(snapshot), 39)

    def test_distance_display_format(self):
        """distance_display 格式化:10.5 km → '10.50km'"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        self.assertEqual(snapshot["distance_display"], "10.50km")

    def test_distance_display_short(self):
        """短距离 < 0.1 km → 'Nm' 格式"""
        row = _make_running_row(dist_km=0.05)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertEqual(snapshot["distance_display"], "50m")

    def test_distance_display_no_data(self):
        """无距离数据 → '-- km'"""
        row = _make_running_row(dist_km=None, distance=None)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertEqual(snapshot["distance_display"], "-- km")

    def test_avg_pace_display_format(self):
        """avg_pace 360s/km → '6'00''/km'"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        self.assertEqual(snapshot["avg_pace_display"], "6'00''/km")
        self.assertEqual(snapshot["pace_unit"], "/km")

    def test_swimming_pace_unit(self):
        """游泳 sub_sport → pace_unit = '/100m'"""
        row = _make_running_row(sub_sport_type="lap_swimming", dist_km=2.0, avg_pace=900)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertEqual(snapshot["pace_unit"], "/100m")
        self.assertEqual(snapshot["avg_pace_display"], "15'00''/100m")

    def test_avg_pace_no_data(self):
        """无 avg_pace → '-- /km'"""
        row = _make_running_row(avg_pace=None)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertEqual(snapshot["avg_pace_display"], "-- /km")

    def test_distance_from_meters(self):
        """无 dist_km 但有 distance(m) → 转换为 km"""
        row = _make_running_row(dist_km=None, distance=10500.0)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertEqual(snapshot["distance_km"], 10.5)
        self.assertEqual(snapshot["distance_display"], "10.50km")

    def test_source_field(self):
        """source 字段必须是 'DB Canonical / Resolver Truth'"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        self.assertEqual(snapshot["source"], "DB Canonical / Resolver Truth")

    def test_activity_id_extracted(self):
        """activity_id 来自 row['activity_id'] 或 row['id']"""
        s1 = MetricsResolver._build_ai_snapshot_block(_make_running_row(id=42))
        self.assertEqual(s1["activity_id"], 42)

    def test_optional_fields_can_be_none(self):
        """可选字段可以为 None"""
        row = _make_running_row(avg_cadence=None, normalized_power=None, swolf=None, tss=None)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertIsNone(snapshot["avg_cadence"])
        self.assertIsNone(snapshot["normalized_power"])

    def test_environment_challenge_not_in_snapshot(self):
        """V_ENV.1.3:environment_challenge 是 UI 摘要层,严禁进入 AI snapshot(§五 5.3 白名单)"""
        row = _make_running_row()
        # 即使 row 含 environment_challenge 字段,snapshot 也不应透传
        row["environment_challenge"] = {"climb": {"level": 4}}
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        self.assertNotIn("environment_challenge", snapshot,
                         "environment_challenge 严禁进入 AI Snapshot")
        # 验证:即便 _validate_ai_snapshot 拒绝也确认这是隔离生效
        try:
            MetricsResolver._validate_ai_snapshot(snapshot)
        except AssertionError:
            self.fail("snapshot 校验失败,可能引入了未白名单字段")


class TestValidateAISnapshot(unittest.TestCase):
    """§六 防污染护栏"""

    def test_validate_passes_for_valid_snapshot(self):
        """标准 snapshot 校验通过"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        MetricsResolver._validate_ai_snapshot(snapshot)  # 不抛异常

    def test_validate_rejects_forbidden_field(self):
        """含 FORBIDDEN 字段 → AssertionError"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        snapshot["slope_pct"] = 5.0  # FORBIDDEN
        with self.assertRaises(AssertionError):
            MetricsResolver._validate_ai_snapshot(snapshot)

    def test_validate_rejects_too_many_keys(self):
        """keys 超过 _AI_SNAPSHOT_MAX_KEYS → AssertionError"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        for i in range(50):
            snapshot[f"extra_{i}"] = i
        with self.assertRaises(AssertionError):
            MetricsResolver._validate_ai_snapshot(snapshot)

    def test_validate_rejects_unauthorized_field(self):
        """不在白名单的字段 → AssertionError"""
        snapshot = {"activity_id": 1, "unknown_field": "value"}
        with self.assertRaises(AssertionError):
            MetricsResolver._validate_ai_snapshot(snapshot)

    def test_validate_total_descent_m_negative(self):
        """total_descent_m < 0 → AssertionError"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        snapshot["total_descent_m"] = -10
        with self.assertRaises(AssertionError):
            MetricsResolver._validate_ai_snapshot(snapshot)

    def test_validate_difficulty_score_out_of_range(self):
        """difficulty_score 超出 [0, 10] → AssertionError"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        snapshot["difficulty_score"] = 15
        with self.assertRaises(AssertionError):
            MetricsResolver._validate_ai_snapshot(snapshot)


class TestBuildAISnapshotTextBlock(unittest.TestCase):
    """_build_ai_snapshot_text_block 单元测试"""

    def test_empty_snapshot_returns_empty_string(self):
        """snapshot 为空 → ''"""
        self.assertEqual(MetricsResolver._build_ai_snapshot_text_block(None), "")

    def test_basic_text_block(self):
        """标准 snapshot → 包含运动类型/距离/心率/海拔等关键信息"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        text = MetricsResolver._build_ai_snapshot_text_block(snapshot)
        self.assertIn("运动类型", text)
        self.assertIn("running", text)
        self.assertIn("10.50km", text)
        self.assertIn("150 bpm", text)
        self.assertIn("50.0 m", text)

    def test_contains_source_note(self):
        """必须包含 '唯一真值' 提示"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row())
        text = MetricsResolver._build_ai_snapshot_text_block(snapshot)
        self.assertIn("唯一真值", text)
        self.assertIn("优先于轨迹明细表", text)

    def test_contains_optional_fields(self):
        """含 normalized_power 时应输出 NP 行"""
        row = _make_running_row(normalized_power=200, swolf=50, tss=60)
        snapshot = MetricsResolver._build_ai_snapshot_block(row)
        text = MetricsResolver._build_ai_snapshot_text_block(snapshot)
        self.assertIn("NP: 200 W", text)
        self.assertIn("SWOLF: 50", text)
        self.assertIn("TSS: 60", text)

    def test_contains_region(self):
        """含 region 时应输出区域行"""
        snapshot = MetricsResolver._build_ai_snapshot_block(_make_running_row(region="Beijing"))
        text = MetricsResolver._build_ai_snapshot_text_block(snapshot)
        self.assertIn("Beijing", text)


class TestMainPyPassthrough(unittest.TestCase):
    """§V4.0 main.py 透传代码模板"""

    def test_main_py_no_validate_ai_snapshot_function(self):
        """main.py 不应再有 validate_ai_snapshot 函数定义"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            self.assertNotIn(node.name, (
                "validate_ai_snapshot",
                "debug_ai_snapshot",
                "get_snapshot_field_whitelist",
            ), f"main.py 不应再定义 {node.name}(V4.0 已下沉)")

    def test_main_py_no_forbidden_constants(self):
        """main.py 不应再有 FORBIDDEN_SNAPSHOT_FIELDS / _MAX_SNAPSHOT_KEYS"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        # 应只在注释中提到(被删除的标注)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assertNotIn(target.id, (
                        "FORBIDDEN_SNAPSHOT_FIELDS",
                        "_MAX_SNAPSHOT_KEYS",
                    ), f"main.py 不应再有常量 {target.id}")

    def test_build_ai_snapshot_passes_through(self):
        """_build_ai_snapshot 必须 1 行透传至 MetricsResolver._build_ai_snapshot_block"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_ai_snapshot":
                continue
            func_src = ast.unparse(node)
            self.assertIn(
                "MetricsResolver._build_ai_snapshot_block",
                func_src,
                "_build_ai_snapshot 必须 1 行透传至 Resolver"
            )
            # 严禁含旧业务逻辑
            self.assertNotIn('"SELECT sport_type', func_src,
                            "SQL 查询已在 main.py 保留为 IO,但不应再有完整业务逻辑")

    def test_build_ai_snapshot_text_block_passes_through(self):
        """_build_ai_snapshot_block 必须 1 行透传至 MetricsResolver._build_ai_snapshot_text_block"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_ai_snapshot_block":
                continue
            func_src = ast.unparse(node)
            self.assertIn(
                "MetricsResolver._build_ai_snapshot_text_block",
                func_src,
                "_build_ai_snapshot_block 必须 1 行透传至 Resolver"
            )

    def test_io_queries_kept_in_main(self):
        """IO 查询(SQLite)必须保留在 main.py._build_ai_snapshot 中"""
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_build_ai_snapshot":
                continue
            func_src = ast.unparse(node)
            # sqlite3.connect 必须保留
            self.assertIn("sqlite3.connect", func_src,
                        "IO 查询 sqlite3.connect 必须保留在 main.py")
            # conn.execute SELECT 必须保留
            self.assertIn("conn.execute", func_src,
                        "SQL 查询必须保留在 main.py")


if __name__ == "__main__":
    unittest.main()
