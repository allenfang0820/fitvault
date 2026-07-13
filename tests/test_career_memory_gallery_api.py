import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


FORBIDDEN_GALLERY_TOKENS = (
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


def _assert_no_gallery_leak(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in FORBIDDEN_GALLERY_TOKENS:
        testcase.assertNotIn(token, serialized)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            region_city TEXT,
            region_country TEXT,
            region_display TEXT,
            deleted_at TEXT,
            is_race INTEGER DEFAULT 1,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(
    conn: sqlite3.Connection,
    activity_id: int,
    title: str,
    start_time: str = "2026-05-19T08:00:00+08:00",
    sport_type: str = "running",
    region_city: str = "",
    region_country: str = "",
    region_display: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO activities
            (id, title, start_time, start_time_utc, sport_type, region_city, region_country, region_display, deleted_at, is_race,
             points_json, track_json, file_path)
        VALUES (?, ?, ?, '', ?, ?, ?, ?, NULL, 1, '[forbidden]', '[forbidden]', '/tmp/forbidden.fit')
        """,
        (activity_id, title, start_time, sport_type, region_city, region_country, region_display),
    )


def _insert_race(
    conn: sqlite3.Connection,
    race_id: str,
    activity_id: str,
    name: str,
    event_date: str = "2026-05-19",
    sport: str = "running",
    city: str = "苏州",
) -> None:
    conn.execute(
        """
        INSERT INTO career_race_events
            (id, activity_id, name, event_type, sport, event_date,
             location_json, performance_summary_json, confidence, source, status, display_metadata_json)
        VALUES (?, ?, ?, '10k', ?, ?, ?, '{}', 1.0, 'user', 'active', '{}')
        """,
        (race_id, activity_id, name, sport, event_date, json.dumps({"city": city}, ensure_ascii=False)),
    )


class TestCareerMemoryGalleryApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_tracks_dir = profile_backend.TRACKS_DIR
        self.original_db_path = profile_backend.DB_PATH
        profile_backend.TRACKS_DIR = self.temp_dir / "workspace" / "tracks"
        profile_backend.TRACKS_DIR.mkdir(parents=True, exist_ok=True)
        self.media_root = self.temp_dir / "workspace" / "career_media"
        self.conn = sqlite3.connect(":memory:")
        _create_activities_table(self.conn)
        career_backend.ensure_career_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        profile_backend.DB_PATH = self.original_db_path
        self.temp_dir_obj.cleanup()

    def _write_photo(self, name: str, content: bytes) -> str:
        target = self.media_root / "activity_race_photo" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return f"memory/photo/activity_race_photo/{name}"

    def test_gallery_returns_race_album_cover_and_ordered_photos(self):
        _insert_activity(self.conn, 1, "苏州 10K")
        _insert_race(self.conn, "race:1", "1", "苏州 10K")
        first_ref = self._write_photo("first.jpg", b"first")
        second_ref = self._write_photo("second.jpg", b"second")

        career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": [first_ref, second_ref]},
            conn=self.conn,
        )
        gallery = career_backend.get_career_memory_gallery(conn=self.conn)

        self.assertEqual(gallery["summary"]["album_count"], 1)
        self.assertEqual(gallery["summary"]["photo_count"], 2)
        album = gallery["albums"][0]
        self.assertEqual(album["race_id"], "race:1")
        self.assertEqual(album["activity_id"], "1")
        self.assertEqual(album["title"], "苏州 10K")
        self.assertEqual(album["photo_count"], 2)
        self.assertFalse(album["is_empty"])
        self.assertEqual(album["footprint"]["region_key"], "CN-JS")
        self.assertEqual(album["footprint"]["country_code"], "CN")
        self.assertEqual([photo["order_index"] for photo in album["photos"]], [0, 1])
        self.assertEqual(album["cover"]["photo_id"], album["photos"][0]["id"])
        self.assertTrue(album["cover"]["image_ref"].startswith("data:image/jpeg;base64,"))
        _assert_no_gallery_leak(self, gallery)

    def test_reorder_changes_gallery_cover_with_banner_first_photo_rule(self):
        _insert_activity(self.conn, 1, "苏州 10K")
        _insert_race(self.conn, "race:1", "1", "苏州 10K")
        first_ref = self._write_photo("first.jpg", b"first")
        second_ref = self._write_photo("second.jpg", b"second")
        added = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": [first_ref, second_ref]},
            conn=self.conn,
        )
        first_id, second_id = [photo["id"] for photo in added["photos"]]

        career_backend.reorder_activity_race_photos(
            {"activity_id": "1", "ordered_ids": [second_id, first_id]},
            conn=self.conn,
        )
        gallery = career_backend.get_career_memory_gallery(conn=self.conn)
        activity_photos = career_backend.get_activity_race_photos("1", conn=self.conn)

        album = gallery["albums"][0]
        expected_second = "data:image/jpeg;base64," + base64.b64encode(b"second").decode("ascii")
        self.assertEqual(album["cover"]["photo_id"], second_id)
        self.assertEqual(album["cover"]["image_ref"], expected_second)
        self.assertEqual(activity_photos["hero_banner_media"]["image_ref"], expected_second)
        self.assertTrue(album["photos"][0]["is_banner"])
        _assert_no_gallery_leak(self, gallery)

    def test_soft_deleted_photo_is_excluded_from_album(self):
        _insert_activity(self.conn, 1, "苏州 10K")
        _insert_race(self.conn, "race:1", "1", "苏州 10K")
        first_ref = self._write_photo("first.jpg", b"first")
        second_ref = self._write_photo("second.jpg", b"second")
        added = career_backend.add_activity_race_photos(
            {"activity_id": "1", "media_refs": [first_ref, second_ref]},
            conn=self.conn,
        )
        first_id = added["photos"][0]["id"]

        career_backend.deactivate_activity_race_photo(
            {"activity_id": "1", "photo_id": first_id},
            conn=self.conn,
        )
        gallery = career_backend.get_career_memory_gallery(conn=self.conn)

        album = gallery["albums"][0]
        self.assertEqual(album["photo_count"], 1)
        self.assertNotIn(first_id, [photo["id"] for photo in album["photos"]])
        self.assertEqual(album["cover"]["photo_id"], album["photos"][0]["id"])
        _assert_no_gallery_leak(self, gallery)

    def test_race_without_photos_returns_empty_album_without_fake_cover(self):
        _insert_activity(self.conn, 1, "苏州 10K")
        _insert_activity(self.conn, 2, "成都半马", start_time="2026-06-01T08:00:00+08:00")
        _insert_race(self.conn, "race:1", "1", "苏州 10K")
        _insert_race(self.conn, "race:2", "2", "成都半马", event_date="2026-06-01", city="成都")

        gallery = career_backend.get_career_memory_gallery(conn=self.conn)

        self.assertEqual(gallery["summary"]["album_count"], 2)
        self.assertEqual(gallery["summary"]["photo_count"], 0)
        self.assertEqual(gallery["summary"]["empty_album_count"], 2)
        self.assertTrue(all(album["is_empty"] for album in gallery["albums"]))
        self.assertTrue(all(album["cover"] == {"has_photo": False, "image_ref": "", "photo_id": ""} for album in gallery["albums"]))
        _assert_no_gallery_leak(self, gallery)

    def test_album_footprint_uses_structured_activity_region(self):
        _insert_activity(
            self.conn,
            1,
            "成都半马",
            region_city="成都市",
            region_country="中国",
            region_display="成都市/中国",
        )
        _insert_activity(
            self.conn,
            2,
            "神户晨跑",
            region_city="神户市",
            region_country="日本",
            region_display="神户市/日本",
        )
        _insert_activity(
            self.conn,
            3,
            "Boston Marathon",
            region_city="Boston",
            region_country="United States",
            region_display="Boston/United States",
        )
        _insert_race(self.conn, "race:1", "1", "成都半马", city="成都")
        _insert_race(self.conn, "race:2", "2", "神户晨跑", city="神户市")
        _insert_race(self.conn, "race:3", "3", "Boston Marathon", city="Boston")

        gallery = career_backend.get_career_memory_gallery(conn=self.conn)
        footprints = {album["race_id"]: album["footprint"] for album in gallery["albums"]}

        self.assertEqual(footprints["race:1"]["region_key"], "CN-SC")
        self.assertEqual(footprints["race:1"]["map_mode"], "china")
        self.assertEqual(footprints["race:2"]["region_key"], "JP-28")
        self.assertEqual(footprints["race:2"]["map_mode"], "japan")
        self.assertEqual(footprints["race:3"]["region_key"], "US-MA")
        self.assertEqual(footprints["race:3"]["map_mode"], "us")
        _assert_no_gallery_leak(self, gallery)

    def test_album_footprint_does_not_infer_from_title(self):
        _insert_activity(self.conn, 1, "成都半马")
        _insert_race(self.conn, "race:1", "1", "成都半马", city="")

        gallery = career_backend.get_career_memory_gallery(conn=self.conn)
        album = gallery["albums"][0]

        self.assertEqual(album["footprint"], {
            "region_key": "",
            "country_code": "",
            "country": "",
            "name": "",
            "level": "",
            "map_mode": "",
        })
        _assert_no_gallery_leak(self, gallery)

    def test_main_api_envelope_and_contract_registration(self):
        db_path = self.temp_dir / "profile.sqlite"
        profile_backend.DB_PATH = db_path
        conn = sqlite3.connect(str(db_path))
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, 1, "苏州 10K")
            _insert_race(conn, "race:1", "1", "苏州 10K")
            conn.commit()
        finally:
            conn.close()

        response = main.Api().get_career_memory_gallery()
        contract = json.loads((Path(__file__).resolve().parents[1] / "docs" / "js_api_contract.json").read_text(encoding="utf-8"))
        method = next(item for item in contract["methods"] if item["name"] == "get_career_memory_gallery")

        self.assertEqual(response["code"], 0)
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["summary"]["album_count"], 1)
        self.assertTrue(method["readonly"])
        self.assertIn("albums", method["returns"])
        self.assertIn("cover", method["returns"])
        self.assertIn("storage_ref", method["description"])
        _assert_no_gallery_leak(self, response)


if __name__ == "__main__":
    unittest.main()
