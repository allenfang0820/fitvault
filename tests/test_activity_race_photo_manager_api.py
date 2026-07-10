import json
import base64
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
            race_source TEXT,
            race_confidence TEXT,
            race_override INTEGER DEFAULT 0,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, activity_id: int, is_race: int = 1) -> None:
    conn.execute(
        """
        INSERT INTO activities
            (id, start_time, deleted_at, is_race, race_source, race_confidence,
             race_override, points_json, track_json, file_path)
        VALUES
            (?, '2026-05-19T08:00:00+08:00', NULL, ?, 'user', 'high',
             1, '[forbidden]', '[forbidden]', '/tmp/source.fit')
        """,
        (activity_id, is_race),
    )


def _assert_no_private_fields(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in ("storage_ref", "file_path", "track_json", "points_json", "/tmp/", "/Users/", "\\Users\\"):
        testcase.assertNotIn(token, serialized)


class TestActivityRacePhotoManagerApi(unittest.TestCase):
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
        _insert_activity(self.conn, 1, is_race=1)
        _insert_activity(self.conn, 2, is_race=0)
        career_backend.ensure_career_schema(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        profile_backend.DB_PATH = self.original_db_path
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        main.CAREER_MEDIA_DIR = self.original_main_media_dir
        self.temp_dir_obj.cleanup()

    def _write_controlled_photo(self, name: str, data: bytes = b"image") -> str:
        target_dir = Path(main.CAREER_MEDIA_DIR) / "activity_race_photo"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        target.write_bytes(data)
        return f"memory/photo/activity_race_photo/{name}"

    def _write_controlled_photo_item(self, stem: str) -> dict[str, str]:
        original = self._write_controlled_photo(f"{stem}.jpg", f"original-{stem}".encode("utf-8"))
        preview_dir = Path(main.CAREER_MEDIA_DIR) / "activity_race_photo_preview"
        thumb_dir = Path(main.CAREER_MEDIA_DIR) / "activity_race_photo_thumb"
        preview_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        preview_name = f"{stem}-1920.jpg"
        thumb_name = f"{stem}-640.jpg"
        (preview_dir / preview_name).write_bytes(f"preview-{stem}".encode("utf-8"))
        (thumb_dir / thumb_name).write_bytes(f"thumb-{stem}".encode("utf-8"))
        return {
            "media_ref": original,
            "preview_ref": f"memory/photo/activity_race_photo_preview/{preview_name}",
            "thumbnail_ref": f"memory/photo/activity_race_photo_thumb/{thumb_name}",
        }

    def test_add_get_and_reorder_activity_race_photos_without_path_leak(self):
        first_ref = self._write_controlled_photo("first.jpg", b"first")
        second_ref = self._write_controlled_photo("second.png", b"second")
        result = career_backend.add_activity_race_photos(
            {
                "activity_id": "1",
                "media_refs": [first_ref, second_ref],
                "title": "终点照片",
            },
            conn=self.conn,
        )

        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["remaining"], 3)
        self.assertEqual([item["order_index"] for item in result["photos"]], [0, 1])
        self.assertTrue(result["photos"][0]["is_banner"])
        self.assertFalse(result["photos"][1]["is_banner"])
        self.assertTrue(result["photos"][0]["thumbnail_url"].startswith("data:image/jpeg;base64,"))
        _assert_no_private_fields(self, result)

        ordered_ids = [result["photos"][1]["id"], result["photos"][0]["id"]]
        reordered = career_backend.reorder_activity_race_photos(
            {"activity_id": "1", "ordered_ids": ordered_ids},
            conn=self.conn,
        )
        self.assertEqual([item["id"] for item in reordered["photos"]], ordered_ids)
        self.assertTrue(reordered["photos"][0]["is_banner"])
        rows = self.conn.execute(
            "SELECT id, metadata_json FROM career_memory_items WHERE activity_id = '1'"
        ).fetchall()
        roles = {row[0]: career_backend._json_loads_object(row[1]).get("role") for row in rows}
        self.assertEqual(roles[ordered_ids[0]], "overview_banner")
        self.assertEqual(roles[ordered_ids[1]], "race_gallery")
        _assert_no_private_fields(self, reordered)

    def test_deactivate_photo_soft_deletes_and_promotes_next_banner(self):
        refs = [
            self._write_controlled_photo("delete-first.jpg", b"first"),
            self._write_controlled_photo("delete-second.jpg", b"second"),
            self._write_controlled_photo("delete-third.jpg", b"third"),
        ]
        result = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": refs},
            conn=self.conn,
        )
        first_id, second_id, third_id = [item["id"] for item in result["photos"]]

        deleted_first = career_backend.deactivate_activity_race_photo(
            {"activity_id": "1", "photo_id": first_id},
            conn=self.conn,
        )

        self.assertEqual([item["id"] for item in deleted_first["photos"]], [second_id, third_id])
        self.assertTrue(deleted_first["photos"][0]["is_banner"])
        self.assertEqual(deleted_first["hero_banner_media"]["has_photo"], True)
        rows = self.conn.execute(
            "SELECT id, status, metadata_json FROM career_memory_items WHERE activity_id = '1'"
        ).fetchall()
        status_by_id = {row[0]: row[1] for row in rows}
        role_by_id = {row[0]: career_backend._json_loads_object(row[2]).get("role") for row in rows}
        self.assertEqual(status_by_id[first_id], "inactive")
        self.assertEqual(status_by_id[second_id], "active")
        self.assertEqual(role_by_id[second_id], "overview_banner")
        self.assertEqual(role_by_id[third_id], "race_gallery")
        _assert_no_private_fields(self, deleted_first)

        deleted_second = career_backend.deactivate_activity_race_photo(
            {"activity_id": "1", "photo_id": second_id},
            conn=self.conn,
        )
        self.assertEqual([item["id"] for item in deleted_second["photos"]], [third_id])
        self.assertTrue(deleted_second["photos"][0]["is_banner"])

        deleted_last = career_backend.deactivate_activity_race_photo(
            {"activity_id": "1", "photo_id": third_id},
            conn=self.conn,
        )
        self.assertEqual(deleted_last["photos"], [])
        self.assertEqual(deleted_last["summary"]["total"], 0)
        self.assertEqual(deleted_last["summary"]["remaining"], 5)
        self.assertEqual(deleted_last["hero_banner_media"], {"has_photo": False, "image_ref": ""})
        self.assertEqual(deleted_last["status"]["message"], "赛事照片已删除")
        physical_files = list((Path(main.CAREER_MEDIA_DIR) / "activity_race_photo").glob("delete-*.jpg"))
        self.assertEqual(len(physical_files), 3)
        _assert_no_private_fields(self, deleted_last)

    def test_reorder_and_delete_keep_derivative_banner_priority(self):
        first = self._write_controlled_photo_item("first-derived")
        second = self._write_controlled_photo_item("second-derived")
        result = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_items": [first, second]},
            conn=self.conn,
        )
        first_id, second_id = [item["id"] for item in result["photos"]]
        expected_second_preview = "data:image/jpeg;base64," + base64.b64encode(b"preview-second-derived").decode("ascii")

        reordered = career_backend.reorder_activity_race_photos(
            {"activity_id": "1", "ordered_ids": [second_id, first_id]},
            conn=self.conn,
        )
        self.assertEqual(reordered["hero_banner_media"]["image_ref"], expected_second_preview)
        self.assertEqual(reordered["photos"][0]["preview_url"], expected_second_preview)

        deleted = career_backend.deactivate_activity_race_photo(
            {"activity_id": "1", "photo_id": second_id},
            conn=self.conn,
        )
        expected_first_preview = "data:image/jpeg;base64," + base64.b64encode(b"preview-first-derived").decode("ascii")
        self.assertEqual([item["id"] for item in deleted["photos"]], [first_id])
        self.assertEqual(deleted["hero_banner_media"]["image_ref"], expected_first_preview)
        _assert_no_private_fields(self, reordered)
        _assert_no_private_fields(self, deleted)

    def test_deactivate_rejects_foreign_or_non_race_photo(self):
        result = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": [self._write_controlled_photo("owned.jpg")]},
            conn=self.conn,
        )
        photo_id = result["photos"][0]["id"]

        with self.assertRaisesRegex(ValueError, "已确认赛事活动"):
            career_backend.deactivate_activity_race_photo(
                {"activity_id": "2", "photo_id": photo_id},
                conn=self.conn,
            )
        with self.assertRaisesRegex(ValueError, "不属于当前赛事活动"):
            career_backend.deactivate_activity_race_photo(
                {"activity_id": "1", "photo_id": "memory:photo:activity:1:missing"},
                conn=self.conn,
            )

    def test_non_race_activity_is_rejected_for_add_and_reorder(self):
        with self.assertRaisesRegex(ValueError, "已确认赛事活动"):
            career_backend.add_activity_race_photos(
                {
                    "activity_id": "2",
                    "media_refs": [self._write_controlled_photo("non-race.jpg")],
                },
                conn=self.conn,
            )
        with self.assertRaisesRegex(ValueError, "已确认赛事活动"):
            career_backend.reorder_activity_race_photos(
                {"activity_id": "2", "ordered_ids": ["memory:missing"]},
                conn=self.conn,
            )
        with self.assertRaisesRegex(ValueError, "已确认赛事活动"):
            career_backend.deactivate_activity_race_photo(
                {"activity_id": "2", "photo_id": "memory:missing"},
                conn=self.conn,
            )

    def test_photo_limit_is_enforced_before_saving_more(self):
        refs = [self._write_controlled_photo(f"p{i}.jpg", bytes([i + 1])) for i in range(5)]
        career_backend.add_activity_race_photos({"activity_id": "1", "media_refs": refs}, conn=self.conn)
        with self.assertRaisesRegex(ValueError, "最多保存 5 张"):
            career_backend.add_activity_race_photos(
                {"activity_id": "1", "media_refs": [self._write_controlled_photo("p6.jpg")]},
                conn=self.conn,
            )

    def test_picker_rejects_selection_over_remaining_before_copying(self):
        existing_refs = [self._write_controlled_photo(f"existing{i}.jpg") for i in range(4)]
        career_backend.add_activity_race_photos({"activity_id": "1", "media_refs": existing_refs}, conn=self.conn)
        self.conn.commit()
        source_a = self.temp_dir / "a.jpg"
        source_b = self.temp_dir / "b.jpg"
        source_a.write_bytes(b"a")
        source_b.write_bytes(b"b")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source_a), str(source_b)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}), \
             mock.patch.object(profile_backend, "_SCHEMA_READY_FOR", None):
            result = main.Api().pick_and_add_activity_race_photos({"activity_id": "1"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], main.API_CODE_VALIDATION)
        self.assertIn("最多还能添加 1 张", result["msg"])
        copied = list((Path(main.CAREER_MEDIA_DIR) / "activity_race_photo").glob("activity-1-*"))
        self.assertEqual(copied, [])

    def test_picker_cancel_is_stable(self):
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}):
            result = main.Api().pick_and_add_activity_race_photos({"activity_id": "1"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"], {"cancelled": True})

    def test_picker_generates_preview_and_thumbnail_derivatives(self):
        try:
            from PIL import Image
        except Exception as exc:
            self.skipTest(f"Pillow unavailable: {exc}")
        source = self.temp_dir / "source.jpg"
        Image.new("RGB", (2400, 1600), (30, 120, 200)).save(source, format="JPEG")
        fake_window = types.SimpleNamespace(create_file_dialog=mock.Mock(return_value=[str(source)]))
        fake_webview = types.SimpleNamespace(
            windows=[fake_window],
            FileDialog=types.SimpleNamespace(OPEN="open"),
        )

        with mock.patch.dict("sys.modules", {"webview": fake_webview}), \
             mock.patch.object(profile_backend, "_SCHEMA_READY_FOR", None):
            result = main.Api().pick_and_add_activity_race_photos({"activity_id": "1"})

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["data"]["cancelled"])
        self.assertEqual(result["data"]["summary"]["total"], 1)
        self.assertTrue(result["data"]["photos"][0]["thumbnail_url"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(result["data"]["photos"][0]["preview_url"].startswith("data:image/jpeg;base64,"))
        originals = list((Path(main.CAREER_MEDIA_DIR) / "activity_race_photo").glob("activity-1-*"))
        previews = list((Path(main.CAREER_MEDIA_DIR) / "activity_race_photo_preview").glob("activity-1-*-1920.jpg"))
        thumbs = list((Path(main.CAREER_MEDIA_DIR) / "activity_race_photo_thumb").glob("activity-1-*-640.jpg"))
        self.assertEqual(len(originals), 1)
        self.assertEqual(len(previews), 1)
        self.assertEqual(len(thumbs), 1)
        rows = self.conn.execute(
            "SELECT metadata_json FROM career_memory_items WHERE activity_id = '1' AND status = 'active'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        metadata = career_backend._json_loads_object(rows[0][0])
        self.assertTrue(metadata["derivatives"]["preview_ref"].startswith("memory/photo/activity_race_photo_preview/"))
        self.assertTrue(metadata["derivatives"]["thumbnail_ref"].startswith("memory/photo/activity_race_photo_thumb/"))
        _assert_no_private_fields(self, result)


if __name__ == "__main__":
    unittest.main()
