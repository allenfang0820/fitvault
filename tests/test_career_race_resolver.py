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
            title TEXT,
            title_source TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            avg_pace REAL,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            is_race INTEGER DEFAULT 0,
            race_source TEXT,
            race_confidence TEXT,
            race_override INTEGER DEFAULT 0,
            race_confirmed_at TEXT,
            deleted_at TEXT,
            {forbidden_sql}
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "晨跑",
        "title_source": "sport_name",
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-05-19T08:00:00+08:00",
        "start_time_utc": "2026-05-19T00:00:00Z",
        "dist_km": 10.0,
        "distance": None,
        "duration": 3600,
        "duration_sec": 3600,
        "avg_pace": 360,
        "region_city": "成都",
        "region": "四川成都",
        "region_display": "成都",
        "is_race": 0,
        "race_source": None,
        "race_confidence": None,
        "race_override": 0,
        "race_confirmed_at": None,
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


def _race_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, name, event_type, confidence, source, status, display_metadata_json
        FROM career_race_events
        ORDER BY id
        """
    ).fetchall()


def _candidate_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, candidate_type, title, evidence_json, confidence, status
        FROM career_event_candidates
        ORDER BY id
        """
    ).fetchall()


class TestCareerRaceResolver(unittest.TestCase):
    def test_user_confirmed_race_writes_high_confidence_event(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=10,
                title="2026 成都马拉松",
                title_source="user",
                dist_km=42.195,
                is_race=1,
                race_source="user",
                race_confidence="high",
                race_override=1,
            )

            result = career_backend.resolve_race_events(conn)

            self.assertTrue(result["ok"])
            rows = _race_rows(conn)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row[1], "10")
            self.assertEqual(row[2], "2026 成都马拉松")
            self.assertEqual(row[4], 1.0)
            self.assertEqual(row[5], "user")
            self.assertEqual(row[6], "active")
            metadata = json.loads(row[7])
            self.assertEqual(metadata["confidence_level"], "high")
            self.assertIn("activity_id", metadata["evidence"])
        finally:
            conn.close()

    def test_user_cancelled_race_closes_existing_event_and_candidate(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(
                conn,
                id=11,
                title="2026 成都半程马拉松",
                dist_km=21.1,
                is_race=0,
                race_source="user",
                race_confidence="high",
                race_override=1,
            )
            conn.execute(
                """
                INSERT INTO career_race_events
                    (id, activity_id, name, event_type, sport, event_date, confidence, source, status)
                VALUES
                    ('race:11', '11', '旧赛事', 'half_marathon', 'running', '2026-05-19', 1.0, 'user', 'active')
                """
            )
            conn.execute(
                """
                INSERT INTO career_event_candidates
                    (id, activity_id, candidate_type, title, confidence, status)
                VALUES
                    ('race_candidate:11', '11', 'race', '旧候选', 0.35, 'candidate')
                """
            )

            career_backend.resolve_race_events(conn)

            race_status = conn.execute(
                "SELECT status FROM career_race_events WHERE id = 'race:11'"
            ).fetchone()[0]
            candidate_status = conn.execute(
                "SELECT status FROM career_event_candidates WHERE id = 'race_candidate:11'"
            ).fetchone()[0]
            self.assertEqual(race_status, "inactive")
            self.assertEqual(candidate_status, "dismissed")
        finally:
            conn.close()

    def test_fit_sport_event_race_writes_high_confidence_fit_event(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=12,
                title="周末比赛",
                dist_km=10.0,
                is_race=1,
                race_source="fit_sport_event",
                race_confidence="high",
            )

            career_backend.resolve_race_events(conn)

            row = _race_rows(conn)[0]
            self.assertEqual(row[1], "12")
            self.assertEqual(row[4], 1.0)
            self.assertEqual(row[5], "fit_sport_event")
            metadata = json.loads(row[7])
            signal_types = {item["type"] for item in metadata["evidence"]["signals"]}
            self.assertIn("fit_sport_event", signal_types)
        finally:
            conn.close()

    def test_title_keyword_and_standard_distance_writes_medium_event(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=13,
                title="2026 成都半程马拉松",
                title_source="user",
                dist_km=21.0975,
                is_race=0,
            )

            career_backend.resolve_race_events(conn)

            rows = _race_rows(conn)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], "13")
            self.assertEqual(rows[0][3], "half_marathon")
            self.assertAlmostEqual(rows[0][4], 0.75)
            self.assertEqual(rows[0][5], "resolver")
            self.assertEqual(_candidate_rows(conn), [])
        finally:
            conn.close()

    def test_standard_distance_only_writes_low_candidate_not_race_event(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=14, title="晨跑", dist_km=21.1)

            career_backend.resolve_race_events(conn)

            self.assertEqual(_race_rows(conn), [])
            candidates = _candidate_rows(conn)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0][1], "14")
            self.assertEqual(candidates[0][2], "race")
            self.assertEqual(candidates[0][6], "candidate")
            evidence = json.loads(candidates[0][4])
            self.assertEqual(evidence["confidence_level"], "low")
            self.assertEqual(evidence["decision"], "candidate")
        finally:
            conn.close()

    def test_city_and_date_alone_do_not_create_race_candidate(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=19,
                title="周末长距离",
                dist_km=18.0,
                start_time="2026-10-18T07:30:00+08:00",
                region_city="北京",
                region="北京",
                region_display="北京",
            )

            career_backend.resolve_race_events(conn)

            self.assertEqual(_race_rows(conn), [])
            self.assertEqual(_candidate_rows(conn), [])
        finally:
            conn.close()

    def test_resolver_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=15,
                title="2026 上海10K比赛",
                dist_km=10.0,
            )

            career_backend.resolve_race_events(conn)
            career_backend.resolve_race_events(conn)

            race_count = conn.execute("SELECT COUNT(*) FROM career_race_events").fetchone()[0]
            candidate_count = conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0]
            self.assertEqual(race_count, 1)
            self.assertEqual(candidate_count, 0)
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
                    (id, title, title_source, sport_type, start_time, dist_km, is_race,
                     race_source, race_confidence, points_json, track_json, raw_records,
                     fit_records, file_path, advanced_metrics, shadow_diff_json)
                VALUES
                    (16, '2026 成都半程马拉松', 'user', 'running', '2026-05-19T08:00:00',
                     21.1, 0, NULL, NULL, '[1]', '[2]', '{}', '{}', '/tmp/a.fit', '{}', '{}')
                """
            )
            conn.set_trace_callback(captured_sql.append)

            career_backend.resolve_race_events(conn)

            select_sql = "\n".join(sql for sql in captured_sql if sql.lstrip().upper().startswith("SELECT"))
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, select_sql)

            stored_json = "\n".join(
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT display_metadata_json FROM career_race_events
                    UNION ALL
                    SELECT evidence_json FROM career_event_candidates
                    """
                )
            )
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, stored_json)
        finally:
            conn.close()

    def test_overview_race_count_reflects_resolved_events(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(
                conn,
                id=17,
                title="2026 北京马拉松",
                dist_km=42.2,
                is_race=1,
                race_source="user",
                race_confidence="high",
                race_override=1,
            )

            career_backend.resolve_race_events(conn)
            overview = career_backend.get_career_overview(conn)

            self.assertEqual(overview["summary"]["race_count"], 1)
            self.assertTrue(overview["status"]["data_ready"])
        finally:
            conn.close()

    def test_default_connection_uses_temp_profile_db_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-race.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activity_table(conn)
                    _insert_activity(conn, id=18, title="2026 杭州10K比赛", dist_km=10.0)
                    conn.commit()
                finally:
                    conn.close()

                result = career_backend.resolve_race_events()

                self.assertTrue(result["ok"])
                self.assertTrue(profile_backend.DB_PATH.exists())
                check = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    race_count = check.execute("SELECT COUNT(*) FROM career_race_events").fetchone()[0]
                    self.assertEqual(race_count, 1)
                finally:
                    check.close()
            finally:
                profile_backend.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
