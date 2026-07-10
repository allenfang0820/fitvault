import json
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import career_backend
import main
import profile_backend


def _create_activity_table(conn: sqlite3.Connection) -> None:
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


def _assert_no_private_media_paths(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    testcase.assertNotIn("storage_ref", serialized)
    testcase.assertNotIn("file_path", serialized)
    testcase.assertNotIn("track_json", serialized)
    testcase.assertNotIn("points_json", serialized)
    testcase.assertNotIn("/tmp/", serialized)
    testcase.assertNotIn("/Users/", serialized)
    testcase.assertNotIn("\\Users\\", serialized)


class TestCareerMemoryPhotoLifecycleApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_tracks_dir = profile_backend.TRACKS_DIR
        self.original_main_media_dir = main.CAREER_MEDIA_DIR
        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.TRACKS_DIR = self.temp_dir / "workspace" / "tracks"
        main.CAREER_MEDIA_DIR = str(self.temp_dir / "workspace" / "career_media")
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend.TRACKS_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(profile_backend.DB_PATH))
        _create_activity_table(self.conn)
        self.conn.execute(
            """
            INSERT INTO activities
                (id, start_time, deleted_at, points_json, track_json, file_path)
            VALUES
                (1, '2026-05-19T08:00:00+08:00', NULL, '[forbidden]', '[forbidden]', '/tmp/source.fit')
            """
        )
        career_backend.ensure_career_schema(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        profile_backend.DB_PATH = self.original_db_path
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        main.CAREER_MEDIA_DIR = self.original_main_media_dir
        self.temp_dir_obj.cleanup()

    def test_pick_and_save_career_memory_photo_copies_renders_and_deactivates_without_path_leak(self):
        source = self.temp_dir / "训练营 终点.png"
        source.write_bytes(b"memory-image-bytes")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}), \
             mock.patch.object(profile_backend, "_SCHEMA_READY_FOR", None):
            result = main.Api().pick_and_save_career_memory_photo({
                "activity_id": "1",
                "title": "训练营终点",
            })

        self.assertTrue(result["ok"], result)
        data = result["data"]
        self.assertFalse(data["cancelled"])
        item = data["item"]
        self.assertEqual(item["activity_id"], "1")
        self.assertEqual(item["type"], "photo")
        self.assertEqual(item["title"], "训练营终点")
        self.assertTrue(item["has_media"])
        self.assertTrue(item["thumbnail_url"].startswith("data:image/png;base64,"))
        copied_files = list((Path(main.CAREER_MEDIA_DIR) / "memory_photo").glob("*.png"))
        self.assertEqual(len(copied_files), 1)
        self.assertEqual(copied_files[0].read_bytes(), b"memory-image-bytes")
        self.assertTrue(copied_files[0].name.startswith("activity-1-"))
        _assert_no_private_media_paths(self, result)

        memory = career_backend.get_career_memory(conn=self.conn)
        self.assertEqual(len(memory["items"]), 1)
        self.assertTrue(memory["items"][0]["thumbnail_url"].startswith("data:image/png;base64,"))
        career_backend.deactivate_career_memory_item({"id": item["id"]}, conn=self.conn)
        memory_after_deactivate = career_backend.get_career_memory(conn=self.conn)
        self.assertEqual(memory_after_deactivate["items"], [])

    def test_pick_and_save_career_memory_photo_cancel_is_stable(self):
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.Api().pick_and_save_career_memory_photo({"activity_id": "1", "title": "照片"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"], {"cancelled": True})

    def test_pick_and_save_career_memory_photo_rejects_non_image_file(self):
        source = self.temp_dir / "not-image.txt"
        source.write_text("nope", encoding="utf-8")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.Api().pick_and_save_career_memory_photo({"activity_id": "1", "title": "照片"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], main.API_CODE_VALIDATION)
        self.assertIn("仅支持", result["msg"])

    def test_pick_and_save_career_memory_photo_requires_activity_id(self):
        result = main.Api().pick_and_save_career_memory_photo({"title": "照片"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], main.API_CODE_VALIDATION)
        self.assertIn("activity_id", result["msg"])


if __name__ == "__main__":
    unittest.main()
