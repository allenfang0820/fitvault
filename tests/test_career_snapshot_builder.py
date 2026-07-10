import inspect
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
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
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
            sport_type TEXT,
            dist_km REAL,
            distance REAL,
            region_city TEXT,
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
        "start_time": "2026-05-19T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "dist_km": 10.0,
        "distance": None,
        "region_city": "北京",
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
        "name": "2026 北京半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-19",
        "location_json": json.dumps({"city": "北京"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps({"track_json": "[forbidden]"}, ensure_ascii=False),
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
        "id": "pb:1",
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
        "display_metadata_json": json.dumps({"file_path": "/tmp/hidden.fit"}, ensure_ascii=False),
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
        "id": "achievement:1",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-05-19",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps({"points_json": "[forbidden]"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_memory(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "memory:1",
        "race_id": "",
        "activity_id": "1",
        "memory_type": "story",
        "title": "第一次半马记忆",
        "event_date": "2026-05-19",
        "storage_ref": "/Users/example/private.jpg",
        "story_text": "最后三公里很难，但撑住了。",
        "metadata_json": json.dumps({"path": "/tmp/private.jpg"}, ensure_ascii=False),
        "status": "active",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_memory_items ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerSnapshotBuilder(unittest.TestCase):
    def test_empty_database_returns_stable_snapshot_shape(self):
        conn = sqlite3.connect(":memory:")
        try:
            snapshot = career_backend.build_career_snapshot(conn=conn)

            self.assertEqual(snapshot["snapshot_version"], "acs.v1")
            self.assertIn("generated_at", snapshot)
            self.assertEqual(snapshot["summary"]["activity_count"], 0)
            self.assertEqual(snapshot["summary"]["race_count"], 0)
            self.assertEqual(snapshot["summary"]["pb_count"], 0)
            self.assertEqual(snapshot["summary"]["achievement_count"], 0)
            self.assertEqual(snapshot["summary"]["memory_count"], 0)
            self.assertEqual(snapshot["primary_sport"], {"sport": "", "activity_count": 0, "confidence": "none"})
            self.assertEqual(snapshot["pb_summary"], [])
            self.assertEqual(snapshot["major_achievements"], [])
            self.assertEqual(snapshot["timeline_digest"], [])
            self.assertEqual(snapshot["representative_memories"], [])
            self.assertTrue(snapshot["status"]["schema_ready"])
            self.assertFalse(snapshot["status"]["data_ready"])
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_summary_and_primary_sport_use_safe_aggregates(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=10.0, region_city="北京")
            _insert_activity(conn, id=2, sport_type="running", dist_km=5.0, region_city="上海")
            _insert_activity(conn, id=3, sport_type="cycling", dist_km=30.0, region_city="北京")
            _insert_activity(conn, id=4, sport_type="running", dist_km=99.0, region_city="杭州", deleted_at="2026-01-01")
            _insert_race(conn)
            _insert_pb(conn)
            _insert_achievement(conn)
            _insert_memory(conn)

            snapshot = career_backend.build_career_snapshot(conn=conn)

            self.assertEqual(snapshot["summary"]["activity_count"], 3)
            self.assertEqual(snapshot["summary"]["race_count"], 1)
            self.assertEqual(snapshot["summary"]["pb_count"], 1)
            self.assertEqual(snapshot["summary"]["achievement_count"], 1)
            self.assertEqual(snapshot["summary"]["memory_count"], 1)
            self.assertEqual(snapshot["summary"]["covered_city_count"], 2)
            self.assertEqual(snapshot["summary"]["total_distance_km"], 45.0)
            self.assertEqual(snapshot["primary_sport"], {"sport": "running", "activity_count": 2, "confidence": "derived"})
            self.assertTrue(snapshot["status"]["data_ready"])
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_snapshot_sections_are_limited_and_field_whitelisted(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            for index in range(1, 15):
                _insert_activity(conn, id=index, sport_type="running", start_time=f"2026-05-{index:02d}T07:00:00+08:00")
                _insert_race(conn, id=f"race:{index}", activity_id=str(index), event_date=f"2026-05-{index:02d}")
                _insert_pb(conn, id=f"pb:{index}", activity_id=str(index), event_date=f"2026-05-{index:02d}", value=str(1400 + index))
                _insert_achievement(
                    conn,
                    id=f"achievement:{index}",
                    activity_id=str(index),
                    event_date=f"2026-05-{index:02d}",
                    score=50 + index,
                )
                _insert_memory(
                    conn,
                    id=f"memory:{index}",
                    activity_id=str(index),
                    event_date=f"2026-05-{index:02d}",
                    story_text=f"记忆 {index}",
                )

            snapshot = career_backend.build_career_snapshot(conn=conn)

            self.assertEqual(len(snapshot["pb_summary"]), 6)
            self.assertEqual(len(snapshot["major_achievements"]), 8)
            self.assertEqual(len(snapshot["timeline_digest"]), 12)
            self.assertEqual(len(snapshot["representative_memories"]), 6)
            self.assertEqual(
                set(snapshot["pb_summary"][0]),
                {"id", "activity_id", "sport", "pb_type", "value", "value_unit", "event_date"},
            )
            self.assertEqual(
                set(snapshot["major_achievements"][0]),
                {"id", "activity_id", "achievement_type", "title", "event_date", "score"},
            )
            self.assertEqual(
                set(snapshot["timeline_digest"][0]),
                {"id", "activity_id", "type", "title", "date"},
            )
            self.assertEqual(
                set(snapshot["representative_memories"][0]),
                {"id", "activity_id", "race_id", "type", "title", "story", "date", "has_media"},
            )
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_representative_memories_exclude_ui_media_and_storage_fields(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1)
            _insert_memory(
                conn,
                id="memory:photo:1",
                activity_id="1",
                memory_type="photo",
                title="冲线照片",
                story_text="",
                storage_ref="/Users/example/private.jpg",
            )

            snapshot = career_backend.build_career_snapshot(conn=conn)
            memory = snapshot["representative_memories"][0]

            self.assertEqual(memory["type"], "photo")
            self.assertTrue(memory["has_media"])
            self.assertNotIn("thumbnail_url", memory)
            self.assertNotIn("detail_link", memory)
            self.assertNotIn("storage_ref", memory)
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_snapshot_builder_does_not_persist_or_call_llm_entrypoints(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            before = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            snapshot = career_backend.build_career_snapshot(conn=conn)
            after = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]
            source = inspect.getsource(career_backend.build_career_snapshot)

            self.assertEqual(before, 0)
            self.assertEqual(after, 0)
            self.assertNotIn("INSERT INTO career_snapshots", source)
            self.assertNotIn("call_llm", source)
            self.assertNotIn("main.", source)
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
