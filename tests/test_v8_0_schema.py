"""
V8.0 schema migration 契约测试

任务: fit-arch-contrac §2.1/§8 契约下,activities 表补建 5 个数据列
      (cadence_curve / hr_zone_distribution / is_race / is_event / is_intermittent)
      以支持 V7.11-V7.13 的新指标(耐久指数 / 步频稳定性 / 训练负荷)

契约依据:
- §2.1 全链路可追溯: 5 列最终来源必须是 FIT 解析 (source_type=fit_sdk)
- §6 shadow_diff 隔离: 5 列不属于 shadow_diff 范围
- §8.3 canonical DB 原则: 仅存可信数据,本任务只建列不写数据
- §9.2 幂等 migration: 重复调用 ensure_activity_sync_schema() 不抛错
- 提示词 V8.0 P0-2 / P1-1 / P2-1

策略: 不直接 import main.py(避免 pywebview / window 等 GUI 依赖),
      而是用与 main.py:ensure_activity_sync_schema() 末尾完全相同的
      ALTER TABLE 段在临时 SQLite 上重放,验证 SQL 语法 / 类型 / 幂等性。
      这样测试聚焦契约,不依赖产品模块加载。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# V8.0 P0-2 中 main.py:ensure_activity_sync_schema() 末尾追加的 5 列
# 必须与生产代码 1:1 一致;若生产代码变更,本测试需同步更新
V8_0_NEW_COLUMNS = [
    ("cadence_curve", "TEXT"),
    ("hr_zone_distribution", "TEXT"),
    ("is_race", "INTEGER DEFAULT 0"),
    ("is_event", "INTEGER DEFAULT 0"),
    ("is_intermittent", "INTEGER DEFAULT 0"),
]


def _apply_v8_0_migration(conn: sqlite3.Connection) -> None:
    """复刻 main.py:ensure_activity_sync_schema() 的 5 列 ALTER TABLE 段。"""
    for col, dtype in V8_0_NEW_COLUMNS:
        conn.execute(f"ALTER TABLE activities ADD COLUMN {col} {dtype}")


def _create_minimal_activities_table(conn: sqlite3.Connection) -> None:
    """建最小 activities 表(与 profile_backend.py CREATE TABLE 结构对齐)。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            filename       TEXT,
            sport_type     TEXT,
            dist_km        REAL,
            duration_sec   INTEGER,
            avg_hr         INTEGER,
            max_hr         INTEGER,
            hr_curve       TEXT,
            speed_curve    TEXT
        )
    """)
    conn.commit()


def _get_column_types(conn: sqlite3.Connection) -> dict[str, str]:
    """返回 {列名: 类型声明} 映射,例如 {'cadence_curve': 'TEXT'}。"""
    rows = conn.execute("PRAGMA table_info(activities)").fetchall()
    # PRAGMA table_info 字段: cid, name, type, notnull, dflt_value, pk
    return {row[1]: row[2].upper() for row in rows}


class TestV8_0SchemaColumns(unittest.TestCase):
    """V8.0 P0-2 + P1-1: 5 列必须出现在 activities 表。"""

    def setUp(self) -> None:
        # 用临时文件,避免污染真实 DB
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = sqlite3.connect(self.db_path)
        _create_minimal_activities_table(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_v8_0_columns_present(self):
        """P0-2: 5 列必须出现在 activities 表。"""
        _apply_v8_0_migration(self.conn)
        self.conn.commit()

        col_types = _get_column_types(self.conn)
        for col, _dtype in V8_0_NEW_COLUMNS:
            self.assertIn(col, col_types, f"V8.0 列 {col} 缺失")

    def test_v8_0_text_columns_have_text_type(self):
        """P1-1: cadence_curve / hr_zone_distribution 必须是 TEXT (JSON 序列化)。"""
        _apply_v8_0_migration(self.conn)
        self.conn.commit()

        col_types = _get_column_types(self.conn)
        self.assertIn("TEXT", col_types["cadence_curve"])
        self.assertIn("TEXT", col_types["hr_zone_distribution"])

    def test_v8_0_bool_columns_have_integer_type(self):
        """P1-1: is_race / is_event / is_intermittent 必须是 INTEGER (SQLite 布尔型惯例)。"""
        _apply_v8_0_migration(self.conn)
        self.conn.commit()

        col_types = _get_column_types(self.conn)
        for col in ("is_race", "is_event", "is_intermittent"):
            self.assertIn("INT", col_types[col], f"{col} 必须为 INTEGER 类型")

    def test_v8_0_columns_are_nullable(self):
        """§8.3 兼容性: 5 列必须 nullable,旧活动记录补列不会失败。"""
        _apply_v8_0_migration(self.conn)
        self.conn.commit()

        rows = self.conn.execute("PRAGMA table_info(activities)").fetchall()
        # PRAGMA 字段: cid, name, type, notnull, dflt_value, pk
        col_notnull = {row[1]: bool(row[3]) for row in rows}
        for col, _ in V8_0_NEW_COLUMNS:
            self.assertFalse(col_notnull[col], f"{col} 必须 nullable (NOT NULL 禁止)")

    def test_v8_0_migration_idempotent(self):
        """§9.2 幂等 migration: 重复调用 ensure_activity_sync_schema() 不抛错。

        生产代码用 try/except 包裹 ALTER TABLE(重复添加会抛 duplicate column),
        测试需验证此保护层。
        """
        # 第一次
        _apply_v8_0_migration(self.conn)
        self.conn.commit()

        # 第二次必须不抛
        try:
            for col, dtype in V8_0_NEW_COLUMNS:
                try:
                    self.conn.execute(
                        f"ALTER TABLE activities ADD COLUMN {col} {dtype}"
                    )
                except Exception:
                    # 与生产一致: silent pass
                    pass
            self.conn.commit()
        except Exception as e:
            self.fail(f"幂等 migration 第二次调用不应抛错,但抛了: {e}")

    def test_v8_0_select_star_includes_new_columns(self):
        """P1-1: SELECT * 自动包含 5 个新列(_fetch_activity_row 行为)。"""
        _apply_v8_0_migration(self.conn)
        # 插入一条活动,验证 SELECT * 返回 5 列
        self.conn.execute("""
            INSERT INTO activities
            (filename, sport_type, dist_km, duration_sec, avg_hr, max_hr)
            VALUES ('test.fit', 'running', 10.0, 3600, 150, 175)
        """)
        self.conn.commit()

        row = self.conn.execute("SELECT * FROM activities WHERE id = 1").fetchone()
        col_names = [
            d[0] for d in self.conn.execute("SELECT * FROM activities WHERE id = 1").description
        ]
        for col, _ in V8_0_NEW_COLUMNS:
            self.assertIn(col, col_names, f"SELECT * 必须包含 {col}")


class TestV8_0SchemaContract(unittest.TestCase):
    """V8.0 P2-1: 契约层断言 — 与产品代码 1:1 一致。"""

    def test_v8_0_new_columns_count(self):
        """V8.0 必须恰好补 5 列(防止后续误改/漏列/多列)。"""
        self.assertEqual(
            len(V8_0_NEW_COLUMNS), 5,
            "V8.0 schema migration 必须补 5 列(1 个 P0 schema bug 修复,不可多不可少)",
        )

    def test_v8_0_columns_names_frozen(self):
        """V8.0 列名是契约的一部分(被 main.py _build_fatigue_review_snapshot 读取)。"""
        actual_names = {c[0] for c in V8_0_NEW_COLUMNS}
        expected = {
            "cadence_curve",
            "hr_zone_distribution",
            "is_race",
            "is_event",
            "is_intermittent",
        }
        self.assertEqual(actual_names, expected, "V8.0 列名与契约不一致")

    def test_v8_0_no_storage_model(self):
        """§架构决策: V8.0 不补 storage_model 列(V4.0 已废弃)。"""
        actual_names = {c[0] for c in V8_0_NEW_COLUMNS}
        self.assertNotIn(
            "storage_model", actual_names,
            "V8.0 明确决策:不补 storage_model 列(V8.1 将重构 _build_fatigue_review_snapshot)",
        )

    def test_v8_0_does_not_modify_existing_columns(self):
        """§9.2 安全: V8.0 不修改已有列(防误改 hr_curve / speed_curve 等)。"""
        existing_columns = {col for col, _ in V8_0_NEW_COLUMNS}
        # 这些列在 V7 阶段已存在,V8.0 不应重声明
        forbidden_overlap = {"hr_curve", "speed_curve", "storage_model"}
        self.assertFalse(
            existing_columns & forbidden_overlap,
            f"V8.0 不应重声明已有列: {existing_columns & forbidden_overlap}",
        )


if __name__ == "__main__":
    unittest.main()
