import json
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


def _insert_memory(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "memory:1",
        "race_id": "",
        "activity_id": "1",
        "memory_type": "story",
        "title": "第一次半马记忆",
        "event_date": "2026-05-19",
        "storage_ref": "/Users/example/private/photo.jpg",
        "story_text": "第一次认真记录比赛",
        "metadata_json": json.dumps(
            {
                "title": "metadata title",
                "path": "/tmp/private.jpg",
                "file_path": "/tmp/private.fit",
                "points": [1, 2, 3],
            },
            ensure_ascii=False,
        ),
        "status": "active",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_memory_items ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerMemoryApi(unittest.TestCase):
    def test_missing_table_returns_stable_empty_state(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_memory(conn=conn)

            self.assertEqual(result["items"], [])
            self.assertEqual(result["summary"], {
                "total": 0,
                "photo_count": 0,
                "story_count": 0,
                "track_count": 0,
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
            self.assertEqual(result["status"]["message"], "暂无生涯记忆")
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_empty_table_returns_stable_empty_state(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            result = career_backend.get_career_memory(conn=conn)

            self.assertEqual(result["items"], [])
            self.assertEqual(result["summary"]["total"], 0)
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_active_memory_items_enter_view_model_without_storage_reference(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_memory(conn)
            _insert_memory(
                conn,
                id="memory:2",
                activity_id="2",
                memory_type="photo",
                title="冲线照片",
                story_text="",
            )
            _insert_memory(
                conn,
                id="memory:3",
                activity_id="",
                race_id="race:1",
                memory_type="track",
                title="轨迹截图",
                story_text="路线值得回看",
            )

            result = career_backend.get_career_memory(conn=conn)

            self.assertEqual(result["summary"], {
                "total": 3,
                "photo_count": 1,
                "story_count": 1,
                "track_count": 1,
            })
            self.assertTrue(result["status"]["data_ready"])
            ids = {item["id"] for item in result["items"]}
            self.assertEqual(ids, {"memory:1", "memory:2", "memory:3"})
            for item in result["items"]:
                self.assertTrue(item["activity_id"] or item["race_id"])
                self.assertIn(item["type"], {"photo", "story", "track"})
                self.assertIn("thumbnail_url", item)
                self.assertEqual(item["thumbnail_url"], "")
                self.assertIn("has_media", item)
                self.assertEqual(item["detail_link"]["source"], "career")
            story = next(item for item in result["items"] if item["id"] == "memory:1")
            self.assertEqual(story["detail_link"], {"activity_id": "1", "source": "career"})
            race_only = next(item for item in result["items"] if item["id"] == "memory:3")
            self.assertEqual(race_only["detail_link"], {"activity_id": "", "source": "career"})
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_inactive_and_deleted_memory_items_are_excluded(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_memory(conn, id="memory:active", status="active")
            _insert_memory(conn, id="memory:inactive", status="inactive")
            _insert_memory(conn, id="memory:deleted", status="deleted")

            result = career_backend.get_career_memory(conn=conn)

            self.assertEqual([item["id"] for item in result["items"]], ["memory:active"])
            self.assertEqual(result["summary"]["total"], 1)
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()

    def test_type_filter_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_memory(conn, id="memory:story", memory_type="story")
            _insert_memory(conn, id="memory:photo", memory_type="photo")

            result = career_backend.get_career_memory({"type": "photo"}, conn=conn)

            self.assertEqual([item["id"] for item in result["items"]], ["memory:photo"])
            self.assertEqual(result["filters"], {"type": "photo"})
            self.assertEqual(result["summary"]["photo_count"], 1)
            self.assertEqual(result["summary"]["story_count"], 0)
            _assert_forbidden_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
