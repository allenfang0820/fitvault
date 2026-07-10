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
            is_race INTEGER DEFAULT 0,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


class TestCareerRacePhotoBannerApi(unittest.TestCase):
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
                (id, start_time, deleted_at, is_race, points_json, track_json, file_path)
            VALUES
                (1, '2026-05-19T08:00:00+08:00', NULL, 1, '[forbidden]', '[forbidden]', '/tmp/source.fit')
            """
        )
        career_backend.ensure_career_schema(self.conn)
        self.conn.execute(
            """
            INSERT INTO career_race_events
                (id, activity_id, name, event_type, sport, event_date, confidence, source, status)
            VALUES
                ('race:1', '1', '苏州 10K', '10k', 'running', '2026-05-19', 1.0, 'user', 'active')
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        profile_backend.DB_PATH = self.original_db_path
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        main.CAREER_MEDIA_DIR = self.original_main_media_dir
        self.temp_dir_obj.cleanup()

    def test_pick_and_save_career_race_photo_copies_to_controlled_dir_without_path_leak(self):
        source = self.temp_dir / "苏州 10K 终点.jpg"
        source.write_bytes(b"image-bytes")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}), \
             mock.patch.object(profile_backend, "_SCHEMA_READY_FOR", None):
            result = main.Api().pick_and_save_career_race_photo(1)

        self.assertTrue(result["ok"], result)
        data = result["data"]
        self.assertFalse(data["cancelled"])
        image_ref = data["hero_banner_media"]["image_ref"]
        self.assertTrue(image_ref.startswith("data:image/jpeg;base64,"))
        copied_files = list((Path(main.CAREER_MEDIA_DIR) / "race_banner").glob("*.jpg"))
        self.assertEqual(len(copied_files), 1)
        self.assertEqual(copied_files[0].read_bytes(), b"image-bytes")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(str(source), serialized)
        self.assertNotIn(str(copied_files[0]), serialized)
        self.assertNotIn("storage_ref", serialized)
        self.assertNotIn("file_path", serialized)

    def test_pick_and_save_career_race_photo_rejects_non_image_file(self):
        source = self.temp_dir / "not-image.txt"
        source.write_text("nope", encoding="utf-8")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.Api().pick_and_save_career_race_photo(1)

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], main.API_CODE_VALIDATION)
        self.assertIn("仅支持", result["msg"])

    def test_pick_and_save_career_race_photo_cancel_is_stable(self):
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.Api().pick_and_save_career_race_photo(1)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"], {"cancelled": True})


if __name__ == "__main__":
    unittest.main()
