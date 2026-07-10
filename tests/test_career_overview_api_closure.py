import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


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
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _assert_forbidden_metadata_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_METADATA_KEYS)
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            sport_type TEXT,
            region_city TEXT,
            max_alt_m REAL,
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
        "start_time": "2024-03-01T08:00:00+08:00",
        "start_time_utc": "",
        "dist_km": 10.5,
        "distance": None,
        "sport_type": "running",
        "region_city": "北京",
        "max_alt_m": None,
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
        "display_metadata_json": json.dumps({"confidence_level": "high"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_pb(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "pb:running_5k:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-19",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps({"resolver": "pb"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:first_running_5k:1",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-05-19",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K：5.0 km",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps({"resolver": "achievement"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerOverviewApiClosure(unittest.TestCase):
    def test_overview_full_aggregation_uses_safe_active_sources(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_time="2024-03-01T08:00:00+08:00", start_time_utc="", dist_km=10.5, distance=None, region_city="北京", max_alt_m=120.4)
            _insert_activity(conn, id=2, start_time="", start_time_utc="2023-01-01T00:00:00Z", dist_km=None, distance=5000, region_city="上海", max_alt_m=3840.2)
            _insert_activity(conn, id=3, start_time="2025-05-01T08:00:00+08:00", dist_km=2.0, distance=None, region_city=" 北京 ", max_alt_m=860.0)
            _insert_activity(conn, id=4, start_time="2026-01-01T08:00:00+08:00", dist_km=1.0, distance=None, region_city="")
            _insert_activity(conn, id=5, start_time="2022-01-01T08:00:00+08:00", dist_km=99.0, region_city="杭州", max_alt_m=5500.0, deleted_at="2026-01-02")
            _insert_race(conn, id="race:active-old", activity_id="1", event_date="2025-10-01", name="2025 北京马拉松")
            _insert_race(
                conn,
                id="race:active-new",
                activity_id="2",
                event_date="2026-05-19",
                name="2026 成都半程马拉松",
                display_metadata_json=json.dumps(
                    {
                        "confidence_level": "high",
                        "storage_ref": "/Users/private/race.jpg",
                        "detail_link": {"activity_id": "999"},
                    },
                    ensure_ascii=False,
                ),
            )
            _insert_race(conn, id="race:inactive-newer", activity_id="3", event_date="2027-05-19", status="inactive")
            _insert_pb(conn, id="pb:active-old", activity_id="1", pb_type="running_5k", event_date="2025-05-19")
            _insert_pb(
                conn,
                id="pb:active-new",
                activity_id="2",
                pb_type="running_10k",
                event_date="2026-06-01",
                improvement="120",
                display_metadata_json=json.dumps(
                    {
                        "resolver": "pb",
                        "path": "/tmp/private.fit",
                        "thumbnail_url": "file:///Users/private/thumb.jpg",
                    },
                    ensure_ascii=False,
                ),
            )
            _insert_pb(conn, id="pb:superseded-newer", activity_id="3", pb_type="running_half_marathon", event_date="2027-06-01", status="superseded")
            _insert_achievement(
                conn,
                id="achievement:active-high",
                activity_id="1",
                score=90,
                event_date="2026-07-01",
                display_metadata_json=json.dumps(
                    {
                        "resolver": "achievement",
                        "nested": {
                            "detail_link": {"activity_id": "999"},
                            "safe": "kept",
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            _insert_achievement(conn, id="achievement:active-low", activity_id="2", score=70, event_date="2026-05-19")
            _insert_achievement(conn, id="achievement:superseded", activity_id="3", score=100, event_date="2027-01-01", status="superseded")
            conn.execute(
                """
                INSERT INTO career_memory_items (id, activity_id, memory_type, storage_ref, story_text)
                VALUES ('memory:1', '1', 'story', '', '第一次认真记录比赛')
                """
            )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"], {
                "career_start_year": 2023,
                "activity_count": 4,
                "race_count": 2,
                "pb_count": 2,
                "achievement_count": 2,
                "memory_count": 1,
                "covered_city_count": 2,
                "total_distance_km": 18.5,
            })
            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["identity"]["primary_sport"], "running")
            self.assertEqual(result["identity"]["primary_sport_label"], "跑步")
            self.assertGreaterEqual(result["identity"]["career_years"], 1)
            self.assertEqual(result["identity"]["career_stage"], "成熟期")
            self.assertEqual(result["identity"]["identity_title"], "跑步成熟期运动者")
            self.assertIn("累计完成 4 次活动", result["identity"]["identity_summary"])
            self.assertIn("跑步", result["identity"]["identity_tags"])
            self.assertIn("2 场赛事", result["identity"]["identity_tags"])
            self.assertIn("2 项 PB", result["identity"]["identity_tags"])
            self.assertIn("2 项成就", result["identity"]["identity_tags"])
            self.assertIn("who", result["identity"]["question_answers"])
            self.assertIn("journey", result["identity"]["question_answers"])
            self.assertIn("experience", result["identity"]["question_answers"])
            self.assertEqual(result["latest_race"]["id"], "race:active-new")
            self.assertEqual(result["hero_banner"]["mode"], "title_art")
            self.assertEqual(result["hero_banner"]["title"], "2026 成都半程马拉松")
            self.assertEqual(result["hero_banner"]["race_id"], "race:active-new")
            self.assertEqual(result["hero_banner"]["detail_link"], {"activity_id": "2", "source": "career"})
            self.assertFalse(result["hero_banner"]["media"]["has_photo"])
            self.assertEqual(result["hero_banner"]["media"]["image_ref"], "")
            self.assertIn("半程马拉松", result["hero_banner"]["badges"])
            self.assertEqual(result["sport_totals"]["running_distance_km"], 18.5)
            self.assertEqual(result["sport_totals"]["strength_total_weight_kg"], None)
            self.assertEqual(result["sport_totals"]["strength_total_weight_status"], "unavailable")
            self.assertEqual(result["career_stats"]["activity_count"], 4)
            self.assertEqual(result["career_stats"]["race_count"], 2)
            self.assertEqual(result["career_stats"]["covered_country_count"], 0)
            self.assertEqual(result["career_stats"]["max_altitude_m"], 3840.2)
            self.assertEqual(result["best_pb"]["title"], "5K PB")
            self.assertEqual(result["latest_race"]["detail_link"], {"activity_id": "2", "source": "career"})
            _assert_forbidden_metadata_absent(self, result["latest_race"]["display_metadata"])
            self.assertEqual(result["latest_pb"]["id"], "pb:active-new")
            self.assertEqual(result["latest_pb"]["detail_link"], {"activity_id": "2", "source": "career"})
            _assert_forbidden_metadata_absent(self, result["latest_pb"]["display_metadata"])
            self.assertEqual(
                [record["id"] for record in result["representative_pb_records"]],
                ["pb:active-old", "pb:active-new"],
            )
            self.assertEqual(
                [achievement["id"] for achievement in result["representative_achievements"]],
                ["achievement:active-high", "achievement:active-low"],
            )
            for achievement in result["representative_achievements"]:
                self.assertEqual(achievement["detail_link"], {"activity_id": achievement["activity_id"], "source": "career"})
                _assert_forbidden_metadata_absent(self, achievement["display_metadata"])
            for record in result["representative_pb_records"]:
                _assert_forbidden_metadata_absent(self, record["display_metadata"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_is_data_ready_with_only_plain_activities(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, start_time="2026-01-01T08:00:00+08:00", dist_km=5.0, region_city="北京")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["activity_count"], 1)
            self.assertEqual(result["identity"]["primary_sport"], "running")
            self.assertEqual(result["identity"]["career_stage"], "起步期")
            self.assertEqual(result["identity"]["identity_title"], "跑步起步期运动者")
            self.assertIn("累计完成 1 次活动", result["identity"]["identity_summary"])
            self.assertEqual(result["summary"]["race_count"], 0)
            self.assertEqual(result["summary"]["pb_count"], 0)
            self.assertEqual(result["summary"]["achievement_count"], 0)
            self.assertEqual(result["summary"]["memory_count"], 0)
            self.assertIsNone(result["latest_race"])
            self.assertIsNone(result["latest_pb"])
            self.assertEqual(result["hero_banner"]["mode"], "title_art")
            self.assertEqual(result["hero_banner"]["badges"], ["运动记忆"])
            self.assertEqual(result["hero_banner"]["race_id"], "")
            self.assertEqual(result["hero_banner"]["detail_link"], {"activity_id": "1", "source": "career"})
            self.assertEqual(result["sport_totals"]["running_distance_km"], 5.0)
            self.assertEqual(result["career_stats"]["activity_count"], 1)
            self.assertEqual(result["representative_pb_records"], [])
            self.assertEqual(result["representative_achievements"], [])
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_hero_banner_uses_safe_race_photo_when_available(self):
        conn = sqlite3.connect(":memory:")
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                temp_root = Path(tmpdir)
                profile_backend.TRACKS_DIR = temp_root / "workspace" / "tracks"
                media_dir = temp_root / "workspace" / "career_media" / "race_banner"
                media_dir.mkdir(parents=True)
                (media_dir / "苏州-10k.jpg").write_bytes(b"race-photo-bytes")
                _create_activity_table(conn)
                _insert_activity(conn, id=1, start_time="2026-05-19T08:00:00+08:00", dist_km=10.0, region_city="苏州")
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:1", activity_id="1", name="苏州 10K", event_type="10k", event_date="2026-05-19")
                career_backend.save_career_race_photo(
                    {
                        "activity_id": "1",
                        "media_ref": "memory/photo/race_banner/苏州-10k.jpg",
                    },
                    conn=conn,
                )

                result = career_backend.get_career_overview(conn)

                self.assertEqual(result["hero_banner"]["mode"], "photo")
                self.assertTrue(result["hero_banner"]["media"]["has_photo"])
                self.assertTrue(result["hero_banner"]["media"]["image_ref"].startswith("data:image/jpeg;base64,"))
                self.assertEqual(result["hero_banner"]["detail_link"], {"activity_id": "1", "source": "career"})
                self.assertNotIn(str(temp_root), result["hero_banner"]["media"]["image_ref"])
                self.assertNotIn("storage_ref", result["hero_banner"]["media"])
                _assert_forbidden_keys_absent(self, result)
            finally:
                profile_backend.TRACKS_DIR = original_tracks_dir
                conn.close()

    def test_overview_hero_banner_title_follows_activity_title(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            conn.execute("ALTER TABLE activities ADD COLUMN title TEXT")
            _insert_activity(
                conn,
                id=1,
                title="活动标题已编辑",
                start_time="2026-05-19T08:00:00+08:00",
                dist_km=10.0,
                region_city="苏州",
            )
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", name="旧派生赛事标题", event_type="10k", event_date="2026-05-19")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["hero_banner"]["title"], "活动标题已编辑")
            self.assertEqual(result["hero_banner"]["art"]["text"], "活动标题已编辑")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_hero_banner_returns_safe_race_photo_slides(self):
        conn = sqlite3.connect(":memory:")
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                temp_root = Path(tmpdir)
                profile_backend.TRACKS_DIR = temp_root / "workspace" / "tracks"
                media_dir = temp_root / "workspace" / "career_media" / "activity_race_photo"
                media_dir.mkdir(parents=True)
                (media_dir / "shanghai.jpg").write_bytes(b"shanghai-race-photo")
                (media_dir / "suzhou.jpg").write_bytes(b"suzhou-race-photo")
                _create_activity_table(conn)
                _insert_activity(conn, id=1, start_time="2026-04-01T08:00:00+08:00", dist_km=10.0, region_city="上海")
                _insert_activity(conn, id=2, start_time="2026-05-19T08:00:00+08:00", dist_km=21.1, region_city="苏州")
                career_backend.ensure_career_schema(conn)
                _insert_race(conn, id="race:old", activity_id="1", name="上海 10K", event_type="10k", event_date="2026-04-01")
                _insert_race(conn, id="race:new", activity_id="2", name="苏州半程马拉松", event_type="half_marathon", event_date="2026-05-19")
                career_backend.add_activity_race_photos(
                    {"activity_id": "1", "media_refs": ["memory/photo/activity_race_photo/shanghai.jpg"]},
                    conn=conn,
                )
                career_backend.add_activity_race_photos(
                    {"activity_id": "2", "media_refs": ["memory/photo/activity_race_photo/suzhou.jpg"]},
                    conn=conn,
                )

                result = career_backend.get_career_overview(conn)

                slides = result["hero_banner"]["slides"]
                self.assertEqual([slide["activity_id"] for slide in slides], ["2", "1"])
                self.assertEqual([slide["title"] for slide in slides], ["苏州半程马拉松", "上海 10K"])
                for slide in slides:
                    self.assertEqual(slide["mode"], "photo")
                    self.assertTrue(slide["media"]["has_photo"])
                    self.assertTrue(slide["media"]["image_ref"].startswith("data:image/jpeg;base64,"))
                    self.assertEqual(slide["detail_link"], {"activity_id": slide["activity_id"], "source": "career"})
                serialized = json.dumps(result, ensure_ascii=False)
                self.assertNotIn(str(temp_root), serialized)
                self.assertNotIn("storage_ref", serialized)
                _assert_forbidden_keys_absent(self, result)
            finally:
                profile_backend.TRACKS_DIR = original_tracks_dir
                conn.close()

    def test_overview_complete_empty_state_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"], {
                "career_start_year": None,
                "activity_count": 0,
                "race_count": 0,
                "pb_count": 0,
                "achievement_count": 0,
                "memory_count": 0,
                "covered_city_count": 0,
                "total_distance_km": None,
            })
            self.assertIsNone(result["latest_race"])
            self.assertIsNone(result["latest_pb"])
            self.assertEqual(result["representative_pb_records"], [])
            self.assertEqual(result["representative_achievements"], [])
            self.assertEqual(result["hero_banner"]["mode"], "empty")
            self.assertEqual(result["hero_banner"]["title"], "等待第一段运动记忆")
            self.assertEqual(result["hero_banner"]["media"], {"has_photo": False, "image_ref": ""})
            self.assertEqual(result["sport_totals"]["swimming_distance_km"], 0.0)
            self.assertEqual(result["sport_totals"]["strength_total_weight_status"], "unavailable")
            self.assertEqual(result["career_stats"]["covered_country_count"], 0)
            self.assertIsNone(result["career_stats"]["max_altitude_m"])
            self.assertEqual(result["identity"], {
                "primary_sport": "unknown",
                "primary_sport_label": "未知",
                "career_years": 0,
                "career_stage": "等待开启",
                "identity_title": "等待开启运动生涯",
                "identity_summary": "导入运动记录后，脉图会在这里生成你的运动生涯身份、累计足迹和代表经历。",
                "identity_tags": ["等待首条运动记录"],
                "question_answers": {
                    "who": "你的运动生涯身份将在活动导入后生成。",
                    "journey": "暂无累计足迹。",
                    "experience": "暂无赛事、PB 或荣誉经历。",
                },
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_v2_sport_totals_include_swim_and_strength_when_reliable(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            conn.execute("ALTER TABLE activities ADD COLUMN region_country TEXT")
            conn.execute("ALTER TABLE activities ADD COLUMN duration_sec INTEGER")
            conn.execute("ALTER TABLE activities ADD COLUMN gain_m REAL")
            conn.execute("ALTER TABLE activities ADD COLUMN strength_total_weight_kg REAL")
            _insert_activity(
                conn,
                id=1,
                sport_type="swimming",
                dist_km=1.5,
                region_city="上海",
                region_country="中国",
                duration_sec=3600,
            )
            _insert_activity(
                conn,
                id=2,
                sport_type="strength_training",
                dist_km=0,
                region_city="上海",
                region_country="中国",
                duration_sec=1800,
                strength_total_weight_kg=5200,
            )
            _insert_activity(
                conn,
                id=3,
                sport_type="hiking",
                dist_km=12,
                region_city="箱根",
                region_country="日本",
                duration_sec=7200,
                gain_m=650,
                max_alt_m=3776.2,
            )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["sport_totals"]["swimming_distance_km"], 1.5)
            self.assertEqual(result["sport_totals"]["walking_hiking_distance_km"], 12.0)
            self.assertEqual(result["sport_totals"]["strength_total_weight_kg"], 5200.0)
            self.assertEqual(result["sport_totals"]["strength_total_weight_status"], "available")
            self.assertEqual(result["career_stats"]["covered_country_count"], 2)
            self.assertEqual(result["career_stats"]["total_duration_seconds"], 12600)
            self.assertEqual(result["career_stats"]["max_elevation_gain_m"], 650.0)
            self.assertEqual(result["career_stats"]["max_altitude_m"], 3776.2)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_overview_default_connection_uses_profile_db_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-overview-api-closure.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activity_table(conn)
                    _insert_activity(conn, id=1, start_time="2026-01-01T08:00:00+08:00", dist_km=5.0, region_city="北京")
                    conn.commit()
                finally:
                    conn.close()

                result = career_backend.get_career_overview()

                self.assertEqual(result["summary"]["activity_count"], 1)
                self.assertEqual(result["identity"]["primary_sport"], "running")
                self.assertTrue(result["status"]["data_ready"])
                _assert_forbidden_keys_absent(self, result)
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_overview_identity_detects_mixed_running_and_cycling(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", start_time="2026-01-01T08:00:00+08:00")
            _insert_activity(conn, id=2, sport_type="cycling", start_time="2026-01-02T08:00:00+08:00", region_city="上海")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["identity"]["primary_sport"], "mixed")
            self.assertEqual(result["identity"]["primary_sport_label"], "多运动")
            self.assertEqual(result["identity"]["identity_title"], "多运动起步期运动者")
            self.assertIn("主运动识别为多运动", result["identity"]["question_answers"]["who"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
