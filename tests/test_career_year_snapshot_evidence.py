import sqlite3
import unittest

import career_backend


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            dist_km REAL,
            duration INTEGER,
            region_city TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "start_time": "2026-05-19T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "dist_km": 10.0,
        "duration": 3600,
        "region_city": "北京",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/Users/example/private.fit",
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
        "id": "123",
        "activity_id": "1",
        "name": "上海半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-04-19",
        "location_json": "{}",
        "performance_summary_json": '{"file_path":"/Users/example/private.fit"}',
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": '{"points_json":"hidden"}',
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
        "id": "456",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1180",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-06-01",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": '{"track_json":"hidden"}',
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
        "id": "789",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-05-20",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": '{"storage_ref":"/Users/example/private.jpg"}',
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerYearSnapshotEvidence(unittest.TestCase):
    def test_active_resolver_events_enter_evidence_catalog_and_summary_counts(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn)
            _insert_race(conn)
            _insert_pb(conn)
            _insert_achievement(conn)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual(snapshot["summary"]["race_count"], 1)
            self.assertEqual(snapshot["summary"]["pb_count"], 1)
            self.assertEqual(snapshot["summary"]["achievement_count"], 1)
            self.assertEqual(
                [item["evidence_id"] for item in snapshot["evidence_catalog"]],
                ["race:123", "achievement:789", "pb:456"],
            )
            self.assertEqual(
                set(snapshot["evidence_catalog"][0]),
                {"evidence_id", "activity_id", "type", "title", "date", "value"},
            )
            self.assertTrue(career_backend.validate_career_year_snapshot_contract(snapshot))
        finally:
            conn.close()

    def test_cross_year_inactive_candidate_and_unbound_events_are_excluded(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-19T07:00:00+08:00")
            _insert_activity(conn, id=2, start_time="2025-05-19T07:00:00+08:00")
            _insert_race(conn, id="active", activity_id="1", event_date="2026-05-19")
            _insert_race(conn, id="inactive", activity_id="1", event_date="2026-05-20", status="inactive")
            _insert_race(conn, id="cross-year", activity_id="2", event_date="2025-05-19")
            _insert_pb(conn, id="unbound", activity_id="999", event_date="2026-06-01")
            conn.execute(
                """
                INSERT INTO career_event_candidates
                    (id, activity_id, candidate_type, title, evidence_json, confidence, status)
                VALUES
                    ('candidate:1', '1', 'race', '候选赛事', '{}', 0.6, 'candidate')
                """
            )

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual([item["evidence_id"] for item in snapshot["evidence_catalog"]], ["race:active"])
            self.assertEqual(snapshot["summary"]["race_count"], 1)
            self.assertEqual(snapshot["summary"]["pb_count"], 0)
            serialized = repr(snapshot)
            self.assertNotIn("candidate:1", serialized)
            self.assertNotIn("cross-year", serialized)
            self.assertNotIn("unbound", serialized)
        finally:
            conn.close()

    def test_evidence_dedupes_and_sorts_by_date_type_and_id(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-01-01T07:00:00+08:00")
            _insert_activity(conn, id=2, start_time="2026-01-02T07:00:00+08:00")
            _insert_race(conn, id="b", activity_id="2", event_date="2026-01-02")
            _insert_race(conn, id="race:a", activity_id="1", event_date="2026-01-01")
            _insert_pb(conn, id="a", activity_id="1", event_date="2026-01-01")
            _insert_race(conn, id="a", activity_id="1", event_date="2026-01-01")

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

            self.assertEqual(
                [(item["date"], item["type"], item["evidence_id"]) for item in snapshot["evidence_catalog"]],
                [
                    ("2026-01-01", "pb", "pb:a"),
                    ("2026-01-01", "race", "race:a"),
                    ("2026-01-02", "race", "race:b"),
                ],
            )
        finally:
            conn.close()

    def test_evidence_does_not_include_media_paths_or_raw_metadata(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn)
            _insert_race(conn)
            _insert_pb(conn)
            _insert_achievement(conn)

            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")
            serialized = repr(snapshot)

            self.assertNotIn("points_json", serialized)
            self.assertNotIn("track_json", serialized)
            self.assertNotIn("storage_ref", serialized)
            self.assertNotIn("file_path", serialized)
            self.assertNotIn("/Users/example", serialized)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
