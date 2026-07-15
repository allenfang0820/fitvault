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
            self.assertNotIn("memory_count", snapshot["summary"])
            self.assertEqual(snapshot["primary_sport"], {"sport": "", "activity_count": 0, "confidence": "none"})
            self.assertEqual(snapshot["pb_summary"], [])
            self.assertEqual(snapshot["major_achievements"], [])
            self.assertEqual(snapshot["timeline_digest"], [])
            self.assertNotIn("representative_memories", snapshot)
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
            self.assertNotIn("memory_count", snapshot["summary"])
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
            pb_types = ["running_5k", "running_10k", "running_half_marathon", "running_marathon"]
            for index in range(1, 15):
                _insert_activity(conn, id=index, sport_type="running", start_time=f"2026-05-{index:02d}T07:00:00+08:00")
                _insert_race(conn, id=f"race:{index}", activity_id=str(index), event_date=f"2026-05-{index:02d}")
                _insert_pb(
                    conn,
                    id=f"pb:{index}",
                    activity_id=str(index),
                    pb_type=pb_types[(index - 1) % len(pb_types)],
                    event_date=f"2026-05-{index:02d}",
                    value=str(1400 + index),
                    status="active" if index <= len(pb_types) else "superseded",
                )
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

            self.assertEqual(len(snapshot["pb_summary"]), 4)
            self.assertEqual(len(snapshot["major_achievements"]), 8)
            self.assertEqual(len(snapshot["timeline_digest"]), 12)
            self.assertNotIn("representative_memories", snapshot)
            self.assertEqual(
                set(snapshot["pb_summary"][0]),
                {"id", "activity_id", "sport", "pb_type", "value", "value_unit", "event_date"},
            )
            self.assertEqual(
                set(snapshot["records_summary"]),
                {
                    "current_records",
                    "formal_records",
                    "recent_refreshes",
                    "candidate_count",
                    "evolution_summary",
                    "curve_availability",
                    "trend_inputs",
                },
            )
            self.assertEqual(len(snapshot["records_summary"]["current_records"]), 4)
            self.assertEqual(
                set(snapshot["major_achievements"][0]),
                {"id", "activity_id", "achievement_type", "title", "event_date", "score"},
            )
            self.assertEqual(
                set(snapshot["timeline_digest"][0]),
                {"id", "activity_id", "type", "title", "date"},
            )
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_records_snapshot_uses_only_record_whitelist(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", pb_type="running_5k")
            conn.execute(
                """
                INSERT INTO career_record_events
                    (id, record_id, activity_id, pb_type, event_type, event_at,
                     evidence_key, resolver_version, source, payload_json)
                VALUES
                    ('event:1', 'pb:running_5k:1', '1', 'running_5k', 'activated',
                     '2026-05-19T00:00:00+00:00', 'evidence:1', 'records-v1', 'resolver',
                     '{"detail_link":{"activity_id":"1"},"file_path":"/tmp/hidden.fit"}')
                """
            )
            conn.execute(
                """
                INSERT INTO career_event_candidates
                    (id, activity_id, candidate_type, title, evidence_json, confidence, status)
                VALUES
                    ('candidate:1', '1', 'pb_record', '10K 候选',
                     '{"record_decision":{"elapsed_time_sec":3600}}', 0.82, 'candidate')
                """
            )

            snapshot = career_backend.build_career_snapshot(conn=conn)
            records_summary = snapshot["records_summary"]

            self.assertEqual(records_summary["candidate_count"], 1)
            self.assertEqual(records_summary["current_records"][0]["id"], "pb:running_5k:1")
            self.assertEqual(records_summary["recent_refreshes"][0]["record_id"], "pb:running_5k:1")
            self.assertEqual(records_summary["evolution_summary"]["refresh_event_count"], 1)
            self.assertEqual(records_summary["evolution_summary"]["by_event_type"], {"activated": 1})
            self.assertEqual(records_summary["trend_inputs"]["basis"], "career_record_events")
            self.assertEqual(records_summary["trend_inputs"]["refresh_frequency_count"], 1)
            self.assertEqual(records_summary["trend_inputs"]["evolution_event_count"], 1)
            self.assertEqual(records_summary["trend_inputs"]["interpretation"], "frequency_and_curve_availability_only")
            self.assertTrue(
                all(not item["creates_formal_record"] for item in records_summary["trend_inputs"]["curve_inputs"])
            )
            self.assertNotIn("record_decision", json.dumps(records_summary, ensure_ascii=False))
            _assert_forbidden_absent(self, snapshot)
        finally:
            conn.close()

    def test_snapshot_excludes_legacy_memory_items(self):
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
            self.assertNotIn("representative_memories", snapshot)
            self.assertNotIn("memory_count", snapshot["summary"])
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
