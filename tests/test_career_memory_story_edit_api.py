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


def _insert_activity(conn: sqlite3.Connection, activity_id: int = 1) -> None:
    conn.execute(
        """
        INSERT INTO activities
            (id, start_time, start_time_utc, deleted_at, points_json, track_json, file_path)
        VALUES
            (?, '2026-05-19T07:00:00+08:00', '', NULL, '[forbidden]', '[forbidden]', '/tmp/forbidden.fit')
        """,
        (activity_id,),
    )


def _save_story(conn: sqlite3.Connection) -> str:
    result = career_backend.save_career_memory_story(
        {
            "activity_id": "1",
            "race_id": "race:1",
            "title": "第一次半马",
            "story": "那天最后 3 公里很难，但我撑住了。",
        },
        conn=conn,
    )
    return result["item"]["id"]


def _memory_row(conn: sqlite3.Connection, memory_id: str):
    return conn.execute(
        """
        SELECT id, race_id, activity_id, memory_type, storage_ref, story_text,
               metadata_json, title, event_date, status, created_at, updated_at
        FROM career_memory_items
        WHERE id = ?
        """,
        (memory_id,),
    ).fetchone()


class TestCareerMemoryStoryEditApi(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _create_activities_table(self.conn)
        _insert_activity(self.conn, 1)

    def tearDown(self):
        self.conn.close()

    def test_update_missing_or_unknown_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "记忆 ID 不能为空"):
            career_backend.update_career_memory_story(
                {"title": "标题", "story": "故事"},
                conn=self.conn,
            )
        with self.assertRaisesRegex(ValueError, "记忆不存在"):
            career_backend.update_career_memory_story(
                {"id": "memory:missing", "title": "标题", "story": "故事"},
                conn=self.conn,
            )

    def test_update_inactive_item_is_rejected(self):
        memory_id = _save_story(self.conn)
        career_backend.deactivate_career_memory_item({"id": memory_id}, conn=self.conn)

        with self.assertRaisesRegex(ValueError, "只能编辑 active 记忆"):
            career_backend.update_career_memory_story(
                {"id": memory_id, "title": "新的标题", "story": "新的故事"},
                conn=self.conn,
            )

    def test_update_non_story_item_is_rejected(self):
        career_backend.ensure_career_schema(self.conn)
        self.conn.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status, created_at, updated_at)
            VALUES
                ('memory:photo:1', '', '1', 'photo', 'asset:photo:1', '', '{}',
                 '照片记忆', '2026-05-19', 'active', '2026-05-19T00:00:00+00:00',
                 '2026-05-19T00:00:00+00:00')
            """
        )

        with self.assertRaisesRegex(ValueError, "只能编辑故事型记忆"):
            career_backend.update_career_memory_story(
                {"id": "memory:photo:1", "title": "新的标题", "story": "新的故事"},
                conn=self.conn,
            )

    def test_update_empty_or_too_long_fields_are_rejected(self):
        memory_id = _save_story(self.conn)
        cases = [
            ({"id": memory_id, "title": " ", "story": "故事"}, "记忆标题不能为空"),
            ({"id": memory_id, "title": "标题", "story": " "}, "记忆故事不能为空"),
            ({"id": memory_id, "title": "题" * 81, "story": "故事"}, "记忆标题不能超过 80 个字符"),
            ({"id": memory_id, "title": "标题", "story": "事" * 501}, "记忆故事不能超过 500 个字符"),
        ]
        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    career_backend.update_career_memory_story(payload, conn=self.conn)

    def test_update_changes_only_story_fields_and_public_response_has_no_paths(self):
        memory_id = _save_story(self.conn)
        self.conn.execute(
            """
            UPDATE career_memory_items
            SET storage_ref = 'asset:keep',
                created_at = '2026-05-19T00:00:00+00:00',
                updated_at = '2026-05-19T00:00:00+00:00'
            WHERE id = ?
            """,
            (memory_id,),
        )
        before = _memory_row(self.conn, memory_id)

        result = career_backend.update_career_memory_story(
            {
                "id": memory_id,
                "title": "第一次半马复盘",
                "story": "最后 3 公里依然很难，但这次我知道该怎么配速。",
            },
            conn=self.conn,
        )
        after = _memory_row(self.conn, memory_id)

        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1], before[1])
        self.assertEqual(after[2], before[2])
        self.assertEqual(after[3], before[3])
        self.assertEqual(after[4], before[4])
        self.assertEqual(after[8], before[8])
        self.assertEqual(after[9], before[9])
        self.assertEqual(after[10], before[10])
        self.assertEqual(after[5], "最后 3 公里依然很难，但这次我知道该怎么配速。")
        self.assertEqual(after[7], "第一次半马复盘")
        self.assertNotEqual(after[6], before[6])
        self.assertNotEqual(after[11], before[11])
        self.assertEqual(result["item"]["id"], memory_id)
        self.assertEqual(result["item"]["title"], "第一次半马复盘")
        self.assertEqual(result["item"]["story"], "最后 3 公里依然很难，但这次我知道该怎么配速。")
        _assert_forbidden_absent(self, result)

    def test_deactivate_missing_or_unknown_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "记忆 ID 不能为空"):
            career_backend.deactivate_career_memory_item({}, conn=self.conn)
        with self.assertRaisesRegex(ValueError, "记忆不存在"):
            career_backend.deactivate_career_memory_item({"id": "memory:missing"}, conn=self.conn)

    def test_deactivate_marks_inactive_without_physical_delete_and_memory_list_excludes_it(self):
        memory_id = _save_story(self.conn)

        result = career_backend.deactivate_career_memory_item({"id": memory_id}, conn=self.conn)
        row = self.conn.execute(
            "SELECT status, COUNT(*) FROM career_memory_items WHERE id = ?",
            (memory_id,),
        ).fetchone()
        memory = career_backend.get_career_memory(conn=self.conn)

        self.assertEqual(result, {"id": memory_id, "status": "inactive"})
        self.assertEqual(row, ("inactive", 1))
        self.assertEqual(memory["summary"]["total"], 0)
        self.assertEqual(memory["items"], [])
        _assert_forbidden_absent(self, memory)


if __name__ == "__main__":
    unittest.main()
