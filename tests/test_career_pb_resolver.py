import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


FORBIDDEN_FIELDS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
}


def _create_activity_table(conn: sqlite3.Connection, include_forbidden: bool = False) -> None:
    forbidden_sql = ""
    if include_forbidden:
        forbidden_sql = """
            points_json TEXT,
            track_json TEXT,
            raw_records TEXT,
            fit_records TEXT,
            file_path TEXT,
            advanced_metrics TEXT,
            shadow_diff_json TEXT,
        """
    conn.execute(
        f"""
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            deleted_at TEXT,
            {forbidden_sql}
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T08:00:00+08:00",
        "start_time_utc": "2026-05-19T00:00:00Z",
        "dist_km": 5.0,
        "distance": None,
        "duration": 1500,
        "duration_sec": 1500,
        "deleted_at": None,
        "updated_at": "2026-05-19T08:00:00+08:00",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _pb_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, sport, pb_type, value, value_unit, improvement,
               event_date, confidence, source, status, display_metadata_json
        FROM career_pb_records
        ORDER BY pb_type, status, CAST(value AS INTEGER), id
        """
    ).fetchall()


class TestCareerPbResolver(unittest.TestCase):
    def test_running_standard_distances_write_active_pb_records(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, duration=1500)
            _insert_activity(conn, id=2, dist_km=10.0, duration=3200)
            _insert_activity(conn, id=3, dist_km=21.1, duration=7200)
            _insert_activity(conn, id=4, dist_km=42.2, duration=15000)

            result = career_backend.resolve_pb_records(conn)

            self.assertTrue(result["ok"])
            rows = _pb_rows(conn)
            active = [row for row in rows if row[10] == "active"]
            self.assertEqual(len(active), 4)
            self.assertEqual(
                {row[3] for row in active},
                {"running_5k", "running_10k", "running_half_marathon", "running_marathon"},
            )
            self.assertTrue(all(row[5] == "seconds" for row in active))
            self.assertTrue(all(row[9] == "resolver" for row in active))
        finally:
            conn.close()

    def test_same_pb_type_keeps_fastest_activity_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, duration=1600)
            _insert_activity(conn, id=2, dist_km=5.0, duration=1450)

            career_backend.resolve_pb_records(conn)

            active = conn.execute(
                "SELECT activity_id, value, status FROM career_pb_records WHERE pb_type = 'running_5k' AND status = 'active'"
            ).fetchall()
            self.assertEqual(active, [("2", "1450", "active")])
        finally:
            conn.close()

    def test_new_faster_activity_switches_active_and_supersedes_old(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=10.0, duration=3600)
            career_backend.resolve_pb_records(conn)

            _insert_activity(conn, id=2, dist_km=10.0, duration=3300)
            career_backend.resolve_pb_records(conn)

            rows = conn.execute(
                """
                SELECT activity_id, value, status, improvement, display_metadata_json
                FROM career_pb_records
                WHERE pb_type = 'running_10k'
                ORDER BY status, activity_id
                """
            ).fetchall()
            status_by_activity = {row[0]: row for row in rows}
            self.assertEqual(status_by_activity["1"][2], "superseded")
            self.assertEqual(status_by_activity["2"][2], "active")
            self.assertEqual(status_by_activity["2"][3], "300")
            metadata = json.loads(status_by_activity["2"][4])
            self.assertEqual(metadata["previous_activity_id"], "1")
            self.assertEqual(metadata["previous_value"], 3600)
            self.assertEqual(metadata["improvement_sec"], 300)
        finally:
            conn.close()

    def test_non_running_distance_mismatch_and_missing_duration_are_skipped(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="cycling", dist_km=10.0, duration=1800)
            _insert_activity(conn, id=2, sport_type="running", dist_km=8.0, duration=1800)
            _insert_activity(conn, id=3, sport_type="running", dist_km=5.0, duration=None, duration_sec=None)

            result = career_backend.resolve_pb_records(conn)

            self.assertEqual(result["pb_records_upserted"], 0)
            self.assertEqual(_pb_rows(conn), [])
        finally:
            conn.close()

    def test_performance_summary_normalizes_distance_time_and_quality(self):
        summary = career_backend._record_performance_summary({
            "id": 42,
            "sport_type": "running",
            "sub_sport_type": "generic",
            "start_time": "2026-07-01T08:00:00",
            "dist_km": 10.02619,
            "distance": 10026.19,
            "duration": 3278,
            "duration_sec": 3278,
        })

        self.assertEqual(summary["activity_id"], "42")
        self.assertEqual(summary["sport"], "running")
        self.assertEqual(summary["distance_m"], 10026)
        self.assertEqual(summary["elapsed_time_sec"], 3278)
        self.assertEqual(summary["timer_time_sec"], 3278)
        self.assertEqual(summary["distance_quality"], "reliable_distance")
        self.assertEqual(summary["time_quality"], "semantics_unknown")
        self.assertIn("distance_from_dist_km", summary["reason_codes"])
        self.assertIn("duration_semantics_unknown", summary["reason_codes"])

    def test_resolver_persists_safe_performance_summary_metadata(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, distance=5000.0, duration=1500, duration_sec=1500)

            career_backend.resolve_pb_records(conn)

            metadata_json = conn.execute(
                "SELECT display_metadata_json FROM career_pb_records WHERE pb_type = 'running_5k'"
            ).fetchone()[0]
            metadata = json.loads(metadata_json)
            summary = metadata["performance_summary"]
            self.assertEqual(summary["distance_m"], 5000)
            self.assertEqual(summary["elapsed_time_sec"], 1500)
            self.assertEqual(summary["time_quality"], "semantics_unknown")
            self.assertNotIn("points_json", json.dumps(summary))
            self.assertNotIn("track_json", json.dumps(summary))
            self.assertNotIn("file_path", json.dumps(summary))
        finally:
            conn.close()

    def test_resolver_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, duration=1500)

            career_backend.resolve_pb_records(conn)
            career_backend.resolve_pb_records(conn)

            count = conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0]
            active_count = conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(active_count, 1)
        finally:
            conn.close()

    def test_overview_pb_count_reflects_active_records(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, dist_km=5.0, duration=1500)
            _insert_activity(conn, id=2, dist_km=10.0, duration=3300)

            career_backend.resolve_pb_records(conn)
            overview = career_backend.get_career_overview(conn)

            self.assertEqual(overview["summary"]["pb_count"], 2)
            self.assertTrue(overview["status"]["data_ready"])
        finally:
            conn.close()

    def test_resolver_does_not_select_or_store_forbidden_raw_fields(self):
        conn = sqlite3.connect(":memory:")
        try:
            captured_sql = []
            _create_activity_table(conn, include_forbidden=True)
            conn.execute(
                """
                INSERT INTO activities
                    (id, sport_type, start_time, dist_km, duration, points_json, track_json,
                     raw_records, fit_records, file_path, advanced_metrics, shadow_diff_json)
                VALUES
                    (1, 'running', '2026-05-19T08:00:00', 5.0, 1500,
                     '[1]', '[2]', '{}', '{}', '/tmp/a.fit', '{}', '{}')
                """
            )
            conn.set_trace_callback(captured_sql.append)

            career_backend.resolve_pb_records(conn)

            select_sql = "\n".join(sql for sql in captured_sql if sql.lstrip().upper().startswith("SELECT"))
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, select_sql)
            stored_json = "\n".join(
                str(row[0])
                for row in conn.execute("SELECT display_metadata_json FROM career_pb_records")
            )
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, stored_json)
        finally:
            conn.close()

    def test_default_connection_uses_temp_profile_db_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-pb.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activity_table(conn)
                    _insert_activity(conn, id=1, dist_km=21.1, duration=7200)
                    conn.commit()
                finally:
                    conn.close()

                result = career_backend.resolve_pb_records()

                self.assertTrue(result["ok"])
                check = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    pb_count = check.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0]
                    self.assertEqual(pb_count, 1)
                finally:
                    check.close()
            finally:
                profile_backend.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
