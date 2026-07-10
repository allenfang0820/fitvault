import json
import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


FORBIDDEN_MEDIA_TOKENS = (
    "storage_ref",
    "file_path",
    "track_json",
    "points_json",
    "/Users/",
    "\\Users\\",
    "/tmp/",
    "file://",
    "SQLite",
)


def _assert_no_media_leak(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in FORBIDDEN_MEDIA_TOKENS:
        testcase.assertNotIn(token, serialized)


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            deleted_at TEXT,
            is_race INTEGER DEFAULT 0,
            race_source TEXT,
            race_confidence TEXT,
            race_override INTEGER DEFAULT 0,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, activity_id: int = 1, is_race: int = 1) -> None:
    conn.execute(
        """
        INSERT INTO activities
            (id, title, start_time, start_time_utc, deleted_at, is_race,
             race_source, race_confidence, race_override, points_json, track_json, file_path)
        VALUES
            (?, '苏州 10K', '2026-05-19T08:00:00+08:00', '', NULL, ?,
             'user', 'high', 1, '[forbidden]', '[forbidden]', '/tmp/forbidden.fit')
        """,
        (activity_id, is_race),
    )


def _insert_race(conn: sqlite3.Connection, activity_id: str = "1") -> None:
    conn.execute(
        """
        INSERT INTO career_race_events
            (id, activity_id, name, event_type, sport, event_date, confidence, source, status)
        VALUES
            ('race:1', ?, '苏州 10K', '10k', 'running', '2026-05-19', 1.0, 'user', 'active')
        """,
        (activity_id,),
    )


class TestCareerMediaSafePreviewApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_tracks_dir = profile_backend.TRACKS_DIR
        profile_backend.TRACKS_DIR = self.temp_dir / "workspace" / "tracks"
        profile_backend.TRACKS_DIR.mkdir(parents=True, exist_ok=True)
        self.media_root = self.temp_dir / "workspace" / "career_media"
        self.conn = sqlite3.connect(":memory:")
        _create_activity_table(self.conn)
        _insert_activity(self.conn, 1, is_race=1)
        career_backend.ensure_career_schema(self.conn)
        _insert_race(self.conn, "1")

    def tearDown(self):
        self.conn.close()
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        self.temp_dir_obj.cleanup()

    def _write_media(self, relative: str, content: bytes = b"image-bytes") -> str:
        target = self.media_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return "memory/photo/" + relative.replace("\\", "/")

    def test_safe_media_ref_converts_to_data_url_for_memory_gallery(self):
        media_ref = self._write_media("memory_photo/finish.jpg", b"finish")

        saved = career_backend.save_career_memory_media(
            {
                "activity_id": "1",
                "memory_type": "photo",
                "title": "终点照片",
                "media_ref": media_ref,
            },
            conn=self.conn,
        )
        memory = career_backend.get_career_memory(conn=self.conn)

        self.assertTrue(saved["item"]["thumbnail_url"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(memory["items"][0]["thumbnail_url"].startswith("data:image/jpeg;base64,"))
        _assert_no_media_leak(self, saved)
        _assert_no_media_leak(self, memory)

    def test_overview_banner_uses_safe_data_url_or_title_art_fallback(self):
        media_ref = self._write_media("race_banner/banner.png", b"banner")

        saved = career_backend.save_career_race_photo(
            {"activity_id": "1", "media_ref": media_ref, "title": "冲线"},
            conn=self.conn,
        )
        overview = career_backend.get_career_overview(self.conn)

        self.assertTrue(saved["hero_banner_media"]["image_ref"].startswith("data:image/png;base64,"))
        self.assertEqual(overview["hero_banner"]["mode"], "photo")
        self.assertTrue(overview["hero_banner"]["media"]["image_ref"].startswith("data:image/png;base64,"))
        _assert_no_media_leak(self, saved)
        _assert_no_media_leak(self, overview)

    def test_activity_race_photos_include_safe_thumbnail_and_preview_url(self):
        first_ref = self._write_media("activity_race_photo/first.webp", b"first")
        second_ref = self._write_media("activity_race_photo/second.jpg", b"second")

        result = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": [first_ref, second_ref]},
            conn=self.conn,
        )
        gallery = career_backend.get_activity_race_photos("1", conn=self.conn)

        self.assertEqual(len(result["photos"]), 2)
        for photo in gallery["photos"]:
            self.assertTrue(photo["thumbnail_url"].startswith("data:image/"))
            self.assertEqual(photo["preview_url"], photo["thumbnail_url"])
        self.assertTrue(gallery["hero_banner_media"]["image_ref"].startswith("data:image/webp;base64,"))
        _assert_no_media_leak(self, result)
        _assert_no_media_leak(self, gallery)

    def test_activity_race_photo_derivatives_are_preferred_without_leaking_refs(self):
        original_ref = self._write_media("activity_race_photo/original.jpg", b"original-heavy")
        preview_ref = self._write_media("activity_race_photo_preview/original-1920.jpg", b"preview-lite")
        thumbnail_ref = self._write_media("activity_race_photo_thumb/original-640.jpg", b"thumb-lite")

        result = career_backend.add_activity_race_photos(
            {
                "activity_id": "1",
                "media_items": [{
                    "media_ref": original_ref,
                    "preview_ref": preview_ref,
                    "thumbnail_ref": thumbnail_ref,
                }],
            },
            conn=self.conn,
        )
        gallery = career_backend.get_activity_race_photos("1", conn=self.conn)
        overview = career_backend.get_career_overview(self.conn)

        expected_preview = "data:image/jpeg;base64," + base64.b64encode(b"preview-lite").decode("ascii")
        expected_thumb = "data:image/jpeg;base64," + base64.b64encode(b"thumb-lite").decode("ascii")
        self.assertEqual(result["photos"][0]["thumbnail_url"], expected_thumb)
        self.assertEqual(result["photos"][0]["preview_url"], expected_preview)
        self.assertEqual(gallery["hero_banner_media"]["image_ref"], expected_preview)
        self.assertEqual(overview["hero_banner"]["media"]["image_ref"], expected_preview)
        serialized = json.dumps(result, ensure_ascii=False) + json.dumps(gallery, ensure_ascii=False)
        self.assertNotIn("preview_ref", serialized)
        self.assertNotIn("thumbnail_ref", serialized)
        self.assertNotIn("derivatives", serialized)
        _assert_no_media_leak(self, result)
        _assert_no_media_leak(self, gallery)
        _assert_no_media_leak(self, overview)

    def test_unsafe_or_missing_media_preview_degrades_without_path_leak(self):
        self.conn.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status)
            VALUES
                ('memory:photo:bad', '', '1', 'photo', '/Users/private/bad.jpg', '',
                 '{"role":"overview_banner"}', '坏路径', '2026-05-19', 'active')
            """
        )
        self.conn.execute(
            """
            INSERT INTO career_memory_items
                (id, race_id, activity_id, memory_type, storage_ref, story_text,
                 metadata_json, title, event_date, status)
            VALUES
                ('memory:photo:missing', '', '1', 'photo', 'memory/photo/missing.jpg', '',
                 '{"role":"race_gallery","order_index":1}', '缺失文件', '2026-05-19', 'active')
            """
        )

        memory = career_backend.get_career_memory(conn=self.conn)
        gallery = career_backend.get_activity_race_photos("1", conn=self.conn)
        overview = career_backend.get_career_overview(self.conn)

        self.assertEqual([item["thumbnail_url"] for item in memory["items"]], ["", ""])
        self.assertEqual([item["thumbnail_url"] for item in gallery["photos"]], ["", ""])
        self.assertEqual([item["preview_url"] for item in gallery["photos"]], ["", ""])
        self.assertNotEqual(overview["hero_banner"]["mode"], "photo")
        self.assertEqual(overview["hero_banner"]["media"], {"has_photo": False, "image_ref": ""})
        _assert_no_media_leak(self, memory)
        _assert_no_media_leak(self, gallery)
        _assert_no_media_leak(self, overview)


if __name__ == "__main__":
    unittest.main()
