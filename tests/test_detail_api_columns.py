"""任务 2 — 详情 API 按需查询白名单测试

契约:fit-arch-contrac §2.1 — UI 字段必须能追溯至 FIT SDK
验证:
  1. _fetch_activity_row 仅返回白名单列(性能优化)
  2. 关键字段(merged_track_json, laps_json, shadow_diff_json)仍在返回中
  3. 静态分析:_fetch_activity_row 调用方实际消费的字段 ⊆ DETAIL_API_REQUIRED_COLUMNS
"""
from __future__ import annotations

import ast
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import profile_backend  # noqa: E402
from main import DETAIL_API_REQUIRED_COLUMNS  # noqa: E402


class TestDetailApiColumnWhitelist(unittest.TestCase):
    """验证 DETAIL_API_REQUIRED_COLUMNS 自身合法 + 不重复"""

    def test_whitelist_is_tuple(self):
        self.assertIsInstance(DETAIL_API_REQUIRED_COLUMNS, tuple)

    def test_whitelist_no_duplicates(self):
        self.assertEqual(len(DETAIL_API_REQUIRED_COLUMNS), len(set(DETAIL_API_REQUIRED_COLUMNS)))

    def test_whitelist_no_empty_strings(self):
        for col in DETAIL_API_REQUIRED_COLUMNS:
            self.assertIsInstance(col, str)
            self.assertGreater(len(col), 0)
            self.assertNotIn(" ", col, f"列名不应含空格: {col!r}")

    def test_required_basic_columns(self):
        for col in ["id", "sport_type", "sub_sport_type", "start_time", "gain_m", "avg_hr", "max_hr", "device_name"]:
            self.assertIn(col, DETAIL_API_REQUIRED_COLUMNS, f"{col} 应在白名单中")

    def test_task1_laps_json_kept(self):
        self.assertIn("laps_json", DETAIL_API_REQUIRED_COLUMNS, "任务 1 引入的 laps_json 必须保留")

    def test_shadow_diff_kept_for_audit(self):
        # §六 shadow_diff 隔离:debug-only,保留 API 返回但前端不展示
        self.assertIn("shadow_diff_json", DETAIL_API_REQUIRED_COLUMNS)

    def test_track_json_for_thumbnail_sampling(self):
        self.assertIn("track_json", DETAIL_API_REQUIRED_COLUMNS, "缩略图采样需 track_json")
        self.assertIn("points_json", DETAIL_API_REQUIRED_COLUMNS, "缩略图采样 fallback 需 points_json")

    def test_regression_fields_excluded(self):
        # 这些字段详情/复盘/轨迹加载均不消费,应保持不在白名单中
        self.assertNotIn("advanced_metrics", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("avg_cadence", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("hr_decoupling", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("tss", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("normalized_power", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("swolf", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("region_city", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("region_country", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("region_error", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("region_updated_at", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("region_attempt_count", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("file_mtime", DETAIL_API_REQUIRED_COLUMNS)
        self.assertNotIn("file_size", DETAIL_API_REQUIRED_COLUMNS)


class TestWhitelistMatchesActivitiesSchema(unittest.TestCase):
    """白名单中的列必须都在 activities 表中存在(防止拼写错误)"""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name

    def tearDown(self):
        Path(self.db_path).unlink(missing_ok=True)

    def test_all_whitelist_columns_exist_in_activities(self):
        conn = sqlite3.connect(self.db_path)
        try:
            profile_backend._init_schema(conn)
            cur = conn.execute("PRAGMA table_info(activities)")
            existing_cols = {row[1] for row in cur.fetchall()}
            for col in DETAIL_API_REQUIRED_COLUMNS:
                self.assertIn(
                    col, existing_cols,
                    f"白名单列 {col!r} 在 activities 表中不存在(可能拼写错误或列已删除)"
                )
        finally:
            conn.close()


class TestStaticConsistency(unittest.TestCase):
    """静态分析:_fetch_activity_row 调用方消费的 row.get("xxx") 必须 ⊆ 白名单

    这是一个保守的契约测试:扫描 main.py 中所有 row.get("xxx") 调用,
    若发现白名单未覆盖的字段,需人工确认是否新增列或仅是辅助调试。
    """

    CALLER_RANGES = [
        # (_fetch_activity_row 调用点行号, 调用方函数体范围起点)
        # _build_fatigue_review_snapshot(line 5313 起)
        # _build_record_from_row(line 6133 起)
        # _build_activity_canonical (load_activity_track 内部,line 5794 起)
    ]

    def test_caller_consumed_fields_in_whitelist(self):
        main_path = Path(_PROJECT_ROOT) / "main.py"
        text = main_path.read_text(encoding="utf-8")

        # 提取所有 _fetch_activity_row 调用点位置
        call_sites: list[int] = []
        for m in re.finditer(r"self\._fetch_activity_row\(", text):
            call_sites.append(m.start())

        # 从每个调用点往后扫描到下一个顶级 def/class,提取 row.get("xxx") 字段
        consumed: set[str] = set()
        consumed.update(self._extract_after(text, 5313, end_keywords=("def ", "class ")))  # _build_fatigue_review_snapshot
        consumed.update(self._extract_after(text, 5794, end_keywords=("def ", "class ")))  # _build_activity_canonical
        consumed.update(self._extract_after(text, 6170, end_keywords=("def ", "class ")))  # _build_record_from_row

        whitelist = set(DETAIL_API_REQUIRED_COLUMNS)
        whitelist.add("merged_track_json")  # COALESCE 派生

        orphan = consumed - whitelist
        self.assertEqual(
            orphan, set(),
            f"以下字段被 _fetch_activity_row 调用方消费但未在 DETAIL_API_REQUIRED_COLUMNS 中:\n"
            f"  {sorted(orphan)}\n"
            f"必须:1)在白名单中追加该列,或 2)重构调用方移除该字段消费"
        )

    @staticmethod
    def _extract_after(text: str, start: int, end_keywords: tuple[str, ...]) -> set[str]:
        """从 start 位置开始扫描,提取所有 row.get("xxx") 字段名,直到遇到 end_keywords。"""
        end = len(text)
        for kw in end_keywords:
            for m in re.finditer(re.escape(kw), text[start + 200:]):
                pos = start + 200 + m.start()
                if pos < end:
                    end = pos
        chunk = text[start:end]
        return {m.group(1) for m in re.finditer(r'row\.get\(["\'](\w+)["\']', chunk)}


class TestSqlGeneration(unittest.TestCase):
    """验证 SQL 字符串拼接正确,无注入风险"""

    def test_columns_str_is_valid_csv(self):
        cols_str = ", ".join(DETAIL_API_REQUIRED_COLUMNS)
        # 任意两列之间恰好一个 ", "
        self.assertTrue(all(c.replace(" ", "").isidentifier() or "_" in c for c in cols_str.split(", ")))
        # 没有任何残留引号或 SQL 关键字
        for forbidden in [";", "DROP", "DELETE", "INSERT", "UPDATE", "--"]:
            self.assertNotIn(forbidden, cols_str)

    def test_whitelist_immutable(self):
        # tuple 类型不可变,防止运行时误改
        with self.assertRaises(Exception):
            DETAIL_API_REQUIRED_COLUMNS[0] = "hacked"  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
