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


class TestCareerMemoryMediaApi(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        _create_activities_table(self.conn)
        _insert_activity(self.conn, 1)

    def tearDown(self):
        self.conn.close()

    def test_missing_binding_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "必须绑定活动或赛事"):
            career_backend.save_career_memory_media(
                {
                    "memory_type": "photo",
                    "title": "冲线照片",
                    "media_ref": "memory/photo/finish.jpg",
                },
                conn=self.conn,
            )

    def test_invalid_memory_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "仅支持 photo 或 track"):
            career_backend.save_career_memory_media(
                {
                    "activity_id": "1",
                    "memory_type": "story",
                    "title": "故事",
                    "media_ref": "memory/photo/finish.jpg",
                },
                conn=self.conn,
            )

    def test_empty_or_too_long_title_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "记忆标题不能为空"):
            career_backend.save_career_memory_media(
                {
                    "activity_id": "1",
                    "memory_type": "photo",
                    "title": " ",
                    "media_ref": "memory/photo/finish.jpg",
                },
                conn=self.conn,
            )
        with self.assertRaisesRegex(ValueError, "记忆标题不能超过 80 个字符"):
            career_backend.save_career_memory_media(
                {
                    "activity_id": "1",
                    "memory_type": "track",
                    "title": "题" * 81,
                    "media_ref": "memory/track/map.png",
                },
                conn=self.conn,
            )

    def test_empty_media_ref_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "媒体引用不能为空"):
            career_backend.save_career_memory_media(
                {
                    "activity_id": "1",
                    "memory_type": "photo",
                    "title": "冲线照片",
                    "media_ref": " ",
                },
                conn=self.conn,
            )

    def test_unsafe_media_refs_are_rejected(self):
        unsafe_refs = [
            "/Users/example/private.jpg",
            "/tmp/private.jpg",
            "C:/Users/example/private.jpg",
            "C:\\Users\\example\\private.jpg",
            "\\\\server\\share\\private.jpg",
            "memory/photo/../private.jpg",
            "memory/photo/%2e%2e/private.jpg",
            "asset:memory:%2e%2e/private.jpg",
            "file:///Users/example/private.jpg",
            "file://C:/Users/example/private.jpg",
        ]
        for media_ref in unsafe_refs:
            with self.subTest(media_ref=media_ref):
                with self.assertRaisesRegex(ValueError, "安全引用"):
                    career_backend.save_career_memory_media(
                        {
                            "activity_id": "1",
                            "memory_type": "photo",
                            "title": "冲线照片",
                            "media_ref": media_ref,
                        },
                        conn=self.conn,
                    )

    def test_successfully_saves_photo_memory_without_public_storage_reference(self):
        result = career_backend.save_career_memory_media(
            {
                "activity_id": "1",
                "memory_type": "photo",
                "title": "冲线照片",
                "media_ref": "memory/photo/finish.jpg",
            },
            conn=self.conn,
        )

        item = result["item"]
        self.assertEqual(item["activity_id"], "1")
        self.assertEqual(item["race_id"], "")
        self.assertEqual(item["type"], "photo")
        self.assertEqual(item["title"], "冲线照片")
        self.assertEqual(item["story"], "")
        self.assertEqual(item["date"], "2026-05-19")
        self.assertEqual(item["thumbnail_url"], "")
        self.assertTrue(item["has_media"])
        self.assertEqual(item["detail_link"], {"activity_id": "1", "source": "career"})
        row = self.conn.execute(
            "SELECT memory_type, storage_ref, status FROM career_memory_items WHERE id = ?",
            (item["id"],),
        ).fetchone()
        self.assertEqual(row, ("photo", "memory/photo/finish.jpg", "active"))
        _assert_forbidden_absent(self, result)

    def test_successfully_saves_chinese_media_ref_without_public_storage_reference(self):
        result = career_backend.save_career_memory_media(
            {
                "activity_id": "1",
                "memory_type": "photo",
                "title": "终点照片",
                "media_ref": "memory/photo/苏州 10K 终点.jpg",
            },
            conn=self.conn,
        )

        item = result["item"]
        self.assertEqual(item["title"], "终点照片")
        self.assertEqual(item["type"], "photo")
        self.assertTrue(item["has_media"])
        self.assertEqual(item["thumbnail_url"], "")
        self.assertNotIn("storage_ref", item)
        row = self.conn.execute(
            "SELECT storage_ref FROM career_memory_items WHERE id = ?",
            (item["id"],),
        ).fetchone()
        self.assertEqual(row[0], "memory/photo/苏州 10K 终点.jpg")
        _assert_forbidden_absent(self, result)

    def test_race_photo_banner_requires_confirmed_race_activity(self):
        with self.assertRaisesRegex(ValueError, "已确认赛事活动"):
            career_backend.save_career_race_photo(
                {
                    "activity_id": "1",
                    "media_ref": "memory/photo/race_banner/finish.jpg",
                },
                conn=self.conn,
            )

    def test_successfully_saves_race_photo_banner_without_public_storage_reference(self):
        career_backend.ensure_career_schema(self.conn)
        self.conn.execute(
            """
            INSERT INTO career_race_events
                (id, activity_id, name, event_type, sport, event_date, confidence, source, status)
            VALUES
                ('race:1', '1', '苏州 10K', '10k', 'running', '2026-05-19', 1.0, 'user', 'active')
            """
        )

        result = career_backend.save_career_race_photo(
            {
                "activity_id": "1",
                "title": "苏州 10K 终点",
                "media_ref": "memory/photo/race_banner/苏州 10K 终点.jpg",
            },
            conn=self.conn,
        )

        item = result["item"]
        self.assertEqual(item["activity_id"], "1")
        self.assertEqual(item["race_id"], "race:1")
        self.assertEqual(item["type"], "photo")
        self.assertEqual(item["title"], "苏州 10K 终点")
        self.assertEqual(result["hero_banner_media"], {
            "has_photo": False,
            "image_ref": "",
        })
        row = self.conn.execute(
            "SELECT id, storage_ref, metadata_json FROM career_memory_items WHERE id = ?",
            ("memory:photo:activity:1:overview-banner",),
        ).fetchone()
        self.assertEqual(row[1], "memory/photo/race_banner/苏州 10K 终点.jpg")
        self.assertEqual(career_backend._json_loads_object(row[2]).get("role"), "overview_banner")
        _assert_forbidden_absent(self, result)

    def test_successfully_saves_track_memory_with_asset_reference(self):
        result = career_backend.save_career_memory_media(
            {
                "race_id": "race:1",
                "memory_type": "track",
                "title": "轨迹截图",
                "media_ref": "asset:memory:track:race-1-map",
            },
            conn=self.conn,
        )

        item = result["item"]
        self.assertEqual(item["activity_id"], "")
        self.assertEqual(item["race_id"], "race:1")
        self.assertEqual(item["type"], "track")
        self.assertTrue(item["has_media"])
        self.assertEqual(item["detail_link"], {"activity_id": "", "source": "career"})
        row = self.conn.execute(
            "SELECT memory_type, storage_ref, status FROM career_memory_items WHERE id = ?",
            (item["id"],),
        ).fetchone()
        self.assertEqual(row, ("track", "asset:memory:track:race-1-map", "active"))
        _assert_forbidden_absent(self, result)

    def test_same_binding_and_media_ref_upserts_one_memory_item(self):
        payload = {
            "activity_id": "1",
            "memory_type": "photo",
            "title": "冲线照片",
            "media_ref": "memory/photo/finish.jpg",
        }

        first = career_backend.save_career_memory_media(payload, conn=self.conn)
        second = career_backend.save_career_memory_media(payload, conn=self.conn)
        count = self.conn.execute("SELECT COUNT(*) FROM career_memory_items").fetchone()[0]

        self.assertEqual(first["item"]["id"], second["item"]["id"])
        self.assertEqual(count, 1)
        _assert_forbidden_absent(self, second)

    def test_get_career_memory_returns_photo_and_track_safe_view_models(self):
        career_backend.save_career_memory_media(
            {
                "activity_id": "1",
                "memory_type": "photo",
                "title": "冲线照片",
                "media_ref": "memory/photo/finish.jpg",
            },
            conn=self.conn,
        )
        career_backend.save_career_memory_media(
            {
                "race_id": "race:1",
                "memory_type": "track",
                "title": "轨迹截图",
                "media_ref": "memory/track/race-1-map.png",
            },
            conn=self.conn,
        )

        memory = career_backend.get_career_memory(conn=self.conn)
        items_by_type = {item["type"]: item for item in memory["items"]}

        self.assertEqual(memory["summary"]["total"], 2)
        self.assertEqual(memory["summary"]["photo_count"], 1)
        self.assertEqual(memory["summary"]["track_count"], 1)
        self.assertTrue(items_by_type["photo"]["has_media"])
        self.assertTrue(items_by_type["track"]["has_media"])
        self.assertEqual(items_by_type["photo"]["thumbnail_url"], "")
        self.assertEqual(items_by_type["track"]["thumbnail_url"], "")
        _assert_forbidden_absent(self, memory)


if __name__ == "__main__":
    unittest.main()
