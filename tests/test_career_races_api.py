import json
import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

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
}
FORBIDDEN_METADATA_KEYS = FORBIDDEN_RESPONSE_KEYS | {
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key).lower(), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _assert_forbidden_metadata_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key).lower(), FORBIDDEN_METADATA_KEYS)
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "2026 成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-19",
        "location_json": json.dumps({"city": "成都"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "user",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "confidence_level": "high",
                "evidence": {
                    "resolver": "race",
                    "activity_id": "1",
                    "confidence_level": "high",
                },
            },
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            title TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            avg_pace REAL,
            avg_hr INTEGER,
            gain_m REAL,
            calories INTEGER,
            avg_power INTEGER,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            is_race INTEGER,
            race_source TEXT,
            race_confidence TEXT,
            race_override INTEGER,
            race_confirmed_at TEXT,
            deleted_at TEXT
        )
        """
    )
    data = {
        "id": "1",
        "title": "2026 成都半程马拉松",
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T07:30:00",
        "dist_km": 21.1,
        "duration_sec": 5400,
        "avg_pace": 256,
        "avg_hr": 156,
        "gain_m": 120,
        "calories": 900,
        "avg_power": 0,
        "deleted_at": "",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerRacesApi(unittest.TestCase):
    def test_backend_empty_state_returns_stable_shape(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_races(conn=conn)

            self.assertEqual(result["races"], [])
            self.assertEqual(result["summary"], {
                "total": 0,
                "by_event_type": {},
                "by_sport": {},
                "by_year": {},
            })
            self.assertEqual(result["filters"], {
                "sport": "all",
                "year": None,
                "event_type": "all",
                "source": "all",
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_returns_only_active_races(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", status="active")
            _insert_race(conn, id="race:2", activity_id="2", name="已关闭赛事", status="inactive")

            result = career_backend.get_career_races(conn=conn)

            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(len(result["races"]), 1)
            race = result["races"][0]
            self.assertEqual(race["id"], "race:1")
            self.assertEqual(race["activity_id"], "1")
            self.assertEqual(race["race_title"], "2026 成都半程马拉松")
            self.assertEqual(race["event_type_label"], "半程马拉松")
            self.assertEqual(race["sport_label"], "跑步")
            self.assertEqual(race["year"], 2026)
            self.assertEqual(race["month"], 5)
            self.assertEqual(race["display_date"], "2026-05-19")
            self.assertEqual(race["city"], "成都")
            self.assertEqual(race["location"], {"city": "成都", "display": "成都"})
            self.assertEqual(race["source_label"], "用户确认")
            self.assertEqual(race["confidence_label"], "高置信度")
            self.assertTrue(race["is_user_confirmed"])
            self.assertFalse(race["is_system_detected"])
            self.assertFalse(race["needs_user_judgement"])
            self.assertEqual(race["confidence_level"], "high")
            self.assertEqual(race["detail_link"], {"activity_id": "1", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_marks_resolver_races_as_needing_user_judgement(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(
                conn,
                id="race:auto",
                activity_id="2",
                name="标题距离规则识别赛事",
                source="resolver",
                confidence=0.82,
                display_metadata_json=json.dumps({"confidence_level": "medium"}, ensure_ascii=False),
            )

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertFalse(race["is_user_confirmed"])
            self.assertTrue(race["is_system_detected"])
            self.assertTrue(race["needs_user_judgement"])
            self.assertEqual(race["source_label"], "规则识别")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_race_archive_title_follows_activity_title(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id="1", title="用户编辑后的赛事标题")
            _insert_race(conn, id="race:1", activity_id="1", name="旧派生赛事标题", status="active")

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertEqual(race["name"], "用户编辑后的赛事标题")
            self.assertEqual(race["race_title"], "用户编辑后的赛事标题")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_race_archive_card_metrics_use_activity_safe_summary(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn)
            _insert_race(conn, id="race:1", activity_id="1", sport="running", event_type="half_marathon")

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertEqual(race["card_metrics"], [
                {"label": "成绩", "value": "01:30:00"},
                {"label": "距离", "value": "21.1 km"},
                {"label": "配速", "value": "4'16\"/km"},
                {"label": "心率", "value": "156 bpm"},
            ])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_race_archive_card_metrics_are_sport_aware_for_cycling(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_activity(
                conn,
                id="2",
                sport_type="cycling",
                dist_km=80.0,
                duration_sec=7200,
                avg_pace=None,
                avg_hr=138,
                gain_m=850,
                avg_power=188,
            )
            _insert_race(conn, id="race:2", activity_id="2", sport="cycling", event_type="race")

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertEqual(race["card_metrics"], [
                {"label": "时间", "value": "02:00:00"},
                {"label": "距离", "value": "80 km"},
                {"label": "均速", "value": "40.0 km/h"},
                {"label": "爬升", "value": "850 m"},
            ])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_race_archive_labels_sources_and_performance_summary(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(
                conn,
                id="race:fit",
                activity_id="7",
                name="2026 设备标记赛事",
                event_type="10k",
                sport="cycling",
                source="fit_sport_event",
                confidence=0.75,
                performance_summary_json=json.dumps(
                    {
                        "duration_text": "42:00",
                        "storage_ref": "/Users/private/race.png",
                    },
                    ensure_ascii=False,
                ),
                display_metadata_json=json.dumps({"confidence_level": "medium"}, ensure_ascii=False),
            )

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertEqual(race["race_title"], "2026 设备标记赛事")
            self.assertEqual(race["event_type_label"], "10K")
            self.assertEqual(race["sport_label"], "骑行")
            self.assertEqual(race["source_label"], "设备赛事标记")
            self.assertEqual(race["confidence_label"], "中置信度")
            self.assertFalse(race["is_user_confirmed"])
            self.assertEqual(race["performance_summary"], {"duration_text": "42:00"})
            _assert_forbidden_metadata_absent(self, race["performance_summary"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_race_archive_media_uses_safe_image_ref_or_empty(self):
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_backend.TRACKS_DIR = str(Path(tmpdir) / "tracks")
            media_dir = Path(tmpdir) / "career_media" / "activity_race_photo"
            media_dir.mkdir(parents=True, exist_ok=True)
            (media_dir / "cover.jpg").write_bytes(b"safe-race-cover")
            conn = sqlite3.connect(":memory:")
            try:
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:1", activity_id="1")
                career_backend.add_activity_race_photos(
                    {"activity_id": "1", "media_refs": ["memory/photo/activity_race_photo/cover.jpg"]},
                    conn=conn,
                )

                result = career_backend.get_career_races(conn=conn)

                race = result["races"][0]
                self.assertEqual(race["media"]["has_photo"], True)
                self.assertTrue(race["media"]["image_ref"].startswith("data:image/jpeg;base64,"))
                _assert_forbidden_keys_absent(self, result)
            finally:
                conn.close()
                profile_backend.TRACKS_DIR = original_tracks_dir

    def test_backend_race_archive_media_prefers_thumbnail_derivative(self):
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_backend.TRACKS_DIR = str(Path(tmpdir) / "tracks")
            media_root = Path(tmpdir) / "career_media"
            (media_root / "activity_race_photo").mkdir(parents=True, exist_ok=True)
            (media_root / "activity_race_photo_preview").mkdir(parents=True, exist_ok=True)
            (media_root / "activity_race_photo_thumb").mkdir(parents=True, exist_ok=True)
            (media_root / "activity_race_photo" / "cover.jpg").write_bytes(b"original-cover")
            (media_root / "activity_race_photo_preview" / "cover-1920.jpg").write_bytes(b"preview-cover")
            (media_root / "activity_race_photo_thumb" / "cover-640.jpg").write_bytes(b"thumb-cover")
            conn = sqlite3.connect(":memory:")
            try:
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:1", activity_id="1")
                career_backend.add_activity_race_photos(
                    {
                        "activity_id": "1",
                        "media_items": [{
                            "media_ref": "memory/photo/activity_race_photo/cover.jpg",
                            "preview_ref": "memory/photo/activity_race_photo_preview/cover-1920.jpg",
                            "thumbnail_ref": "memory/photo/activity_race_photo_thumb/cover-640.jpg",
                        }],
                    },
                    conn=conn,
                )

                result = career_backend.get_career_races(conn=conn)

                expected_thumb = "data:image/jpeg;base64," + base64.b64encode(b"thumb-cover").decode("ascii")
                race = result["races"][0]
                self.assertEqual(race["media"], {"has_photo": True, "image_ref": expected_thumb})
                serialized = json.dumps(result, ensure_ascii=False)
                self.assertNotIn("thumbnail_ref", serialized)
                self.assertNotIn("preview_ref", serialized)
                self.assertNotIn("derivatives", serialized)
                _assert_forbidden_keys_absent(self, result)
            finally:
                conn.close()
                profile_backend.TRACKS_DIR = original_tracks_dir

    def test_backend_race_archive_media_allows_practical_uploaded_cover_size(self):
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_backend.TRACKS_DIR = str(Path(tmpdir) / "tracks")
            media_dir = Path(tmpdir) / "career_media" / "activity_race_photo"
            media_dir.mkdir(parents=True, exist_ok=True)
            cover_bytes = b"x" * (5 * 1024 * 1024)
            (media_dir / "uploaded-cover.jpg").write_bytes(cover_bytes)
            conn = sqlite3.connect(":memory:")
            try:
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:1", activity_id="1")
                career_backend.add_activity_race_photos(
                    {"activity_id": "1", "media_refs": ["memory/photo/activity_race_photo/uploaded-cover.jpg"]},
                    conn=conn,
                )

                result = career_backend.get_career_races(conn=conn)

                race = result["races"][0]
                self.assertEqual(race["media"]["has_photo"], True)
                self.assertTrue(race["media"]["image_ref"].startswith("data:image/jpeg;base64,"))
                _assert_forbidden_keys_absent(self, result)
            finally:
                conn.close()
                profile_backend.TRACKS_DIR = original_tracks_dir

    def test_backend_race_archive_media_skips_large_cover_payloads(self):
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_backend.TRACKS_DIR = str(Path(tmpdir) / "tracks")
            media_dir = Path(tmpdir) / "career_media" / "activity_race_photo"
            media_dir.mkdir(parents=True, exist_ok=True)
            large_bytes = b"x" * (career_backend.CAREER_RACE_ARCHIVE_COVER_MAX_BYTES + 1)
            (media_dir / "large-cover.jpg").write_bytes(large_bytes)
            conn = sqlite3.connect(":memory:")
            try:
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:1", activity_id="1")
                career_backend.add_activity_race_photos(
                    {"activity_id": "1", "media_refs": ["memory/photo/activity_race_photo/large-cover.jpg"]},
                    conn=conn,
                )

                result = career_backend.get_career_races(conn=conn)

                race = result["races"][0]
                self.assertEqual(race["media"], {"has_photo": False, "image_ref": ""})
                self.assertLess(len(json.dumps(result)), career_backend.CAREER_RACE_ARCHIVE_COVER_MAX_BYTES)
                _assert_forbidden_keys_absent(self, result)
            finally:
                conn.close()
                profile_backend.TRACKS_DIR = original_tracks_dir

    def test_backend_filters_by_sport_year_event_type_and_source(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", sport="running", event_type="half_marathon", source="user", event_date="2026-05-19")
            _insert_race(conn, id="race:2", activity_id="2", sport="cycling", event_type="race", source="resolver", event_date="2026-06-01")
            _insert_race(conn, id="race:3", activity_id="3", sport="running", event_type="marathon", source="fit_sport_event", event_date="2025-11-01")

            result = career_backend.get_career_races(
                {"sport": "running", "year": "2026", "event_type": "half_marathon", "source": "user"},
                conn=conn,
            )

            self.assertEqual(result["filters"], {
                "sport": "running",
                "year": 2026,
                "event_type": "half_marathon",
                "source": "user",
            })
            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(result["races"][0]["id"], "race:1")
        finally:
            conn.close()

    def test_backend_summary_counts_returned_races(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", sport="running", event_type="half_marathon", event_date="2026-05-19")
            _insert_race(conn, id="race:2", activity_id="2", sport="running", event_type="marathon", event_date="2026-11-01")
            _insert_race(conn, id="race:3", activity_id="3", sport="cycling", event_type="race", event_date="2025-04-01")

            result = career_backend.get_career_races(conn=conn)

            self.assertEqual(result["summary"]["total"], 3)
            self.assertEqual(result["summary"]["by_event_type"], {
                "half_marathon": 1,
                "marathon": 1,
                "race": 1,
            })
            self.assertEqual(result["summary"]["by_sport"], {"running": 2, "cycling": 1})
            self.assertEqual(result["summary"]["by_year"], {"2026": 2, "2025": 1})
            self.assertEqual([race["id"] for race in result["races"]], ["race:2", "race:1", "race:3"])
        finally:
            conn.close()

    def test_backend_sanitizes_extended_forbidden_metadata_keys(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(
                conn,
                display_metadata_json=json.dumps(
                    {
                        "confidence_level": "high",
                        "storage_ref": "/Users/private/race.jpg",
                        "Storage_Ref": "/Users/private/case-race.jpg",
                        "path": "/tmp/private.fit",
                        "File_Path": "/Users/private/case.fit",
                        "thumbnail_url": "file:///Users/private/thumb.jpg",
                        "detail_link": {"activity_id": "999", "source": "leak"},
                        "nested": {
                            "track_json": "[forbidden]",
                            "SQLite_Schema": "CREATE TABLE secret",
                            "safe_note": "kept",
                        },
                    },
                    ensure_ascii=False,
                ),
            )

            result = career_backend.get_career_races(conn=conn)

            race = result["races"][0]
            self.assertEqual(race["detail_link"], {"activity_id": "1", "source": "career"})
            self.assertEqual(
                race["display_metadata"],
                {
                    "confidence_level": "high",
                    "nested": {"safe_note": "kept"},
                },
            )
            _assert_forbidden_metadata_absent(self, race["display_metadata"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_main_api_get_career_races_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-races.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                    _insert_race(conn, id="race:10", activity_id="10", name="2026 杭州10K比赛", event_type="10k")
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_races({"event_type": "10k"})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertIsInstance(response["traceId"], str)
                self.assertEqual(response["data"]["summary"]["total"], 1)
                self.assertEqual(response["data"]["races"][0]["activity_id"], "10")
                _assert_forbidden_keys_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_get_career_races(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_races", methods)
        method = methods["get_career_races"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("races", method["returns"])


if __name__ == "__main__":
    unittest.main()
