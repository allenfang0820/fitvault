import sqlite3
import unittest

import career_backend


FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
    "path",
    "storage_ref",
}


def _assert_forbidden_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "start_time": "2026-05-19T07:00:00+08:00",
        "start_time_utc": "",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/tmp/forbidden.fit",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerMemoryStoryApi(unittest.TestCase):
    def test_missing_binding_is_rejected(self):
        conn = sqlite3.connect(":memory:")
        try:
            with self.assertRaisesRegex(ValueError, "必须绑定活动或赛事"):
                career_backend.save_career_memory_story(
                    {"title": "第一次半马", "story": "值得记住"},
                    conn=conn,
                )
        finally:
            conn.close()

    def test_empty_title_or_story_is_rejected(self):
        conn = sqlite3.connect(":memory:")
        try:
            with self.assertRaisesRegex(ValueError, "记忆标题不能为空"):
                career_backend.save_career_memory_story(
                    {"activity_id": "1", "title": " ", "story": "值得记住"},
                    conn=conn,
                )
            with self.assertRaisesRegex(ValueError, "记忆故事不能为空"):
                career_backend.save_career_memory_story(
                    {"activity_id": "1", "title": "第一次半马", "story": " "},
                    conn=conn,
                )
        finally:
            conn.close()

    def test_title_or_story_too_long_is_rejected(self):
        conn = sqlite3.connect(":memory:")
        try:
            with self.assertRaisesRegex(ValueError, "记忆标题不能超过 80 个字符"):
                career_backend.save_career_memory_story(
                    {"activity_id": "1", "title": "题" * 81, "story": "值得记住"},
                    conn=conn,
                )
            with self.assertRaisesRegex(ValueError, "记忆故事不能超过 500 个字符"):
                career_backend.save_career_memory_story(
                    {"activity_id": "1", "title": "第一次半马", "story": "事" * 501},
                    conn=conn,
                )
        finally:
            conn.close()

    def test_unknown_or_deleted_activity_is_rejected_when_activity_table_exists(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1, deleted_at="2026-06-01")
            with self.assertRaisesRegex(ValueError, "绑定的活动不存在"):
                career_backend.save_career_memory_story(
                    {"activity_id": "999", "title": "第一次半马", "story": "值得记住"},
                    conn=conn,
                )
            with self.assertRaisesRegex(ValueError, "绑定的活动已删除"):
                career_backend.save_career_memory_story(
                    {"activity_id": "1", "title": "第一次半马", "story": "值得记住"},
                    conn=conn,
                )
        finally:
            conn.close()

    def test_successfully_saves_story_memory_without_storage_reference(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1)

            result = career_backend.save_career_memory_story(
                {
                    "activity_id": "1",
                    "title": "第一次半马",
                    "story": "那天最后 3 公里很难，但我撑住了。",
                },
                conn=conn,
            )

            item = result["item"]
            self.assertEqual(item["activity_id"], "1")
            self.assertEqual(item["race_id"], "")
            self.assertEqual(item["type"], "story")
            self.assertEqual(item["title"], "第一次半马")
            self.assertEqual(item["story"], "那天最后 3 公里很难，但我撑住了。")
            self.assertEqual(item["date"], "2026-05-19")
            self.assertEqual(item["thumbnail_url"], "")
            self.assertFalse(item["has_media"])
            self.assertEqual(item["detail_link"], {"activity_id": "1", "source": "career"})
            row = conn.execute(
                "SELECT memory_type, storage_ref, status FROM career_memory_items WHERE id = ?",
                (item["id"],),
            ).fetchone()
            self.assertEqual(row, ("story", "", "active"))
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_chinese_title_and_story_are_preserved_without_path_leak(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1)

            result = career_backend.save_career_memory_story(
                {
                    "activity_id": "1",
                    "title": "苏州河边的第一次 10K",
                    "story": "配速不快，但这次我记住了夜跑时的风。",
                },
                conn=conn,
            )
            memory = career_backend.get_career_memory(conn=conn)

            self.assertEqual(result["item"]["title"], "苏州河边的第一次 10K")
            self.assertEqual(result["item"]["story"], "配速不快，但这次我记住了夜跑时的风。")
            self.assertEqual(memory["items"][0]["title"], "苏州河边的第一次 10K")
            self.assertEqual(memory["items"][0]["story"], "配速不快，但这次我记住了夜跑时的风。")
            _assert_forbidden_absent(self, result)
            _assert_forbidden_absent(self, memory)
        finally:
            conn.close()

    def test_save_is_stable_for_same_activity_title_and_story(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            _insert_activity(conn, id=1)
            payload = {
                "activity_id": "1",
                "title": "第一次半马",
                "story": "那天最后 3 公里很难，但我撑住了。",
            }

            first = career_backend.save_career_memory_story(payload, conn=conn)
            second = career_backend.save_career_memory_story(payload, conn=conn)
            memory = career_backend.get_career_memory(conn=conn)

            self.assertEqual(first["item"]["id"], second["item"]["id"])
            self.assertEqual(memory["summary"]["total"], 1)
            self.assertEqual(memory["items"][0]["id"], first["item"]["id"])
            _assert_forbidden_absent(self, memory)
        finally:
            conn.close()

    def test_race_only_binding_is_allowed_without_fake_activity_link(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.save_career_memory_story(
                {
                    "race_id": "race:1",
                    "title": "赛事故事",
                    "story": "这场比赛值得记住。",
                },
                conn=conn,
            )

            item = result["item"]
            self.assertEqual(item["activity_id"], "")
            self.assertEqual(item["race_id"], "race:1")
            self.assertEqual(item["detail_link"], {"activity_id": "", "source": "career"})
            memory = career_backend.get_career_memory(conn=conn)
            self.assertEqual(memory["summary"]["total"], 1)
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
