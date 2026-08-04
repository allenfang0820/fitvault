import json
import sqlite3
import unittest
from unittest import mock

import career_backend
import main
import profile_backend


def _distance_points(items):
    return json.dumps([{"distance_m": distance, "t_sec": elapsed} for distance, elapsed in items])


def _create_schema(conn):
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            duration REAL,
            gain_m REAL,
            ascent_m REAL,
            max_alt_m REAL,
            max_altitude_m REAL,
            points_json TEXT,
            track_json TEXT,
            power_points TEXT,
            laps_json TEXT,
            lengths_json TEXT,
            pool_length_m REAL,
            pool_length REAL,
            deleted_at TEXT,
            is_mock INTEGER,
            file_path TEXT
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _insert_running_activity(conn):
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, file_path, is_mock
        )
        VALUES ('run-1', 'running', '2026-07-18T08:00:00Z', 6.0, 1900, ?, '/Users/fanglei/private.fit', 0)
        """,
        (_distance_points([(0, 0), (2500, 900), (5000, 1800), (6000, 1900)]),),
    )


def _insert_running_activity_row(conn, *, activity_id, start_time, elapsed_5k, distance_km=5.0):
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, file_path, is_mock
        )
        VALUES (?, 'running', ?, ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            start_time,
            distance_km,
            elapsed_5k,
            _distance_points([(0, 0), (distance_km * 1000, elapsed_5k)]),
            f"/tmp/{activity_id}.fit",
        ),
    )


def _insert_cycling_activity_row(conn, *, activity_id, start_time, distance_km):
    distance_m = distance_km * 1000
    steps = max(2, int(distance_km // 5))
    points = [
        (round(distance_m * index / steps, 3), round(7200 * index / steps, 3))
        for index in range(steps + 1)
    ]
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, distance, duration_sec, points_json, file_path, is_mock
        )
        VALUES (?, 'cycling', ?, ?, ?, 7200, ?, ?, 0)
        """,
        (
            activity_id,
            start_time,
            distance_km,
            distance_m,
            _distance_points(points),
            f"/tmp/{activity_id}.fit",
        ),
    )


def _update_running_stream(conn, *, distance_km=6.0, duration_sec=1900, elapsed_5k=1700):
    conn.execute(
        """
        UPDATE activities
        SET dist_km = ?,
            duration_sec = ?,
            points_json = ?
        WHERE id = 'run-1'
        """,
        (
            distance_km,
            duration_sec,
            _distance_points([(0, 0), (2500, elapsed_5k / 2), (5000, elapsed_5k), (distance_km * 1000, duration_sec)]),
        ),
    )


def _forbidden_tokens():
    return (
        "points_json",
        "track_json",
        "power_points",
        "laps_json",
        "lengths_json",
        "raw_fit",
        "raw_points",
        "file_path",
        "/Users/",
        "\\Users\\",
        "sqlite_master",
        "CREATE TABLE",
    )


class CareerRecordMetricResultMaterializationTest(unittest.TestCase):
    def setUp(self):
        career_backend._clear_record_metric_series_cache()

    def test_schema_creates_metric_results_table_and_indexes_idempotently(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            second = career_backend.ensure_career_schema(conn)

            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            indexes = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
            }

            self.assertIn("career_record_metric_results", tables)
            self.assertIn("idx_career_record_metric_results_key_date", indexes)
            self.assertIn("idx_career_record_metric_results_sport_key", indexes)
            self.assertIn("idx_career_record_metric_results_activity", indexes)
            self.assertIn("idx_career_record_metric_results_fingerprint", indexes)
            self.assertTrue(second["ok"])
        finally:
            conn.close()

    def test_dry_run_planner_returns_metric_result_without_writing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()

            before = conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0]
            plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)
            after = conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0]

            self.assertTrue(plan["ok"])
            self.assertTrue(plan["dry_run"])
            self.assertEqual(before, 0)
            self.assertEqual(after, 0)
            self.assertEqual(plan["summary"]["would_upsert"], ["running_5k"])
            self.assertEqual(plan["summary"]["would_write"], False)
            self.assertEqual(len(plan["results"]), 1)
            result = plan["results"][0]
            self.assertEqual(result["activity_id"], "run-1")
            self.assertEqual(result["record_key"], "running_5k")
            self.assertEqual(result["metric_name"], "elapsed_time_sec")
            self.assertEqual(result["metric_value_num"], 1540.0)
            self.assertEqual(result["status"], "available")
            self.assertTrue(result["input_fingerprint"].startswith("metric_result_input:sha256:"))
            self.assertTrue(result["result_fingerprint"].startswith("metric_result:sha256:"))
        finally:
            conn.close()

    def test_safe_upsert_is_idempotent_and_updates_changed_result(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()
            plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)

            dry = career_backend.upsert_career_record_metric_results(conn, plan, dry_run=True)
            self.assertEqual(dry["would_upsert"], ["running_5k"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0], 0)

            applied = career_backend.upsert_career_record_metric_results(conn, plan, dry_run=False)
            self.assertEqual(applied["upserted"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0], 1)
            first = conn.execute("SELECT result_fingerprint, metric_value_num FROM career_record_metric_results").fetchone()

            unchanged_plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)
            unchanged = career_backend.upsert_career_record_metric_results(conn, unchanged_plan, dry_run=False)
            self.assertEqual(unchanged["upserted"], 0)
            self.assertEqual(unchanged["would_skip"], ["running_5k"])

            _update_running_stream(conn, elapsed_5k=1500)
            changed_row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()
            changed_plan = career_backend.compute_record_metric_results_for_activity(changed_row, record_keys=["running_5k"], conn=conn)
            changed = career_backend.upsert_career_record_metric_results(conn, changed_plan, dry_run=False)
            second = conn.execute("SELECT result_fingerprint, metric_value_num FROM career_record_metric_results").fetchone()

            self.assertEqual(changed["upserted"], 1)
            self.assertNotEqual(first["result_fingerprint"], second["result_fingerprint"])
            self.assertLess(second["metric_value_num"], first["metric_value_num"])
        finally:
            conn.close()

    def test_invalidate_metric_results_for_activity(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()
            plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)
            career_backend.upsert_career_record_metric_results(conn, plan, dry_run=False)

            dry = career_backend.invalidate_career_record_metric_results_for_activity(conn, "run-1", dry_run=True)
            self.assertEqual(dry["would_invalidate"], ["running_5k"])
            self.assertEqual(conn.execute("SELECT status FROM career_record_metric_results").fetchone()["status"], "available")

            applied = career_backend.invalidate_career_record_metric_results_for_activity(conn, "run-1", dry_run=False)
            self.assertEqual(applied["invalidated"], 1)
            self.assertEqual(conn.execute("SELECT status FROM career_record_metric_results").fetchone()["status"], "invalidated")
        finally:
            conn.close()

    def test_upsert_invalidates_existing_row_when_resolver_no_longer_produces_key(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()
            plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)
            career_backend.upsert_career_record_metric_results(conn, plan, dry_run=False)

            _update_running_stream(conn, distance_km=1.0, duration_sec=400, elapsed_5k=400)
            short_row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()
            stale_plan = career_backend.compute_record_metric_results_for_activity(short_row, record_keys=["running_5k"], conn=conn)
            self.assertEqual(stale_plan["summary"]["would_invalidate"], ["running_5k"])
            applied = career_backend.upsert_career_record_metric_results(conn, stale_plan, dry_run=False)

            self.assertEqual(applied["invalidated"], 1)
            self.assertEqual(conn.execute("SELECT status FROM career_record_metric_results").fetchone()["status"], "invalidated")
        finally:
            conn.close()

    def test_rebuild_dry_run_and_apply(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)

            dry = career_backend.rebuild_career_record_metric_results(conn, sport="running", record_keys=["running_5k"], dry_run=True)
            self.assertEqual(dry["scanned"], 1)
            self.assertEqual(dry["summary"]["would_upsert"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0], 0)

            applied = career_backend.rebuild_career_record_metric_results(conn, sport="running", record_keys=["running_5k"], dry_run=False)
            self.assertEqual(applied["summary"]["upserted"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_metric_results").fetchone()[0], 1)
        finally:
            conn.close()

    def test_record_breaking_event_materialization_dry_run_apply_and_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity_row(
                conn,
                activity_id="run-1",
                start_time="2026-07-18T08:00:00Z",
                elapsed_5k=1800,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-2",
                start_time="2026-07-19T08:00:00Z",
                elapsed_5k=1700,
            )
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            conn.execute(
                "DELETE FROM career_record_events WHERE event_type = ?",
                (career_backend.RECORD_BREAKING_EVENT_TYPE,),
            )

            dry = career_backend.materialize_career_record_breaking_events(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=True,
            )
            self.assertTrue(dry["dry_run"])
            self.assertEqual(dry["summary"]["planned"], 1)
            self.assertEqual(dry["summary"]["current_best_planned"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,)).fetchone()[0], 0)

            applied = career_backend.materialize_career_record_breaking_events(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            self.assertFalse(applied["dry_run"])
            self.assertEqual(applied["summary"]["upserted"], 1)
            self.assertEqual(applied["summary"]["current_best_upserted"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,)).fetchone()[0], 1)

            repeat = career_backend.materialize_career_record_breaking_events(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            self.assertEqual(repeat["summary"]["upserted"], 1)
            self.assertEqual(repeat["summary"]["current_best_upserted"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,)).fetchone()[0], 1)
        finally:
            conn.close()

    def test_record_breaking_events_are_generated_from_materialized_progression_idempotently(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity_row(
                conn,
                activity_id="run-1",
                start_time="2026-07-18T08:00:00Z",
                elapsed_5k=1800,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-2",
                start_time="2026-07-19T08:00:00Z",
                elapsed_5k=1700,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-3",
                start_time="2026-07-20T08:00:00Z",
                elapsed_5k=1900,
            )

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )

            rows = conn.execute(
                """
                SELECT id, activity_id, record_key, event_type, source, payload_json
                FROM career_record_events
                WHERE event_type = ?
                ORDER BY event_at, id
                """,
                (career_backend.RECORD_BREAKING_EVENT_TYPE,),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["activity_id"], "run-2")
            self.assertEqual(rows[0]["record_key"], "running_5k")
            self.assertEqual(rows[0]["source"], "metric_series")
            payload = json.loads(rows[0]["payload_json"])
            self.assertEqual(payload["metric"]["value"], 1700.0)
            self.assertEqual(payload["previous_best_metric"]["value"], 1800.0)
            self.assertEqual(payload["detail_link"], {"activity_id": "run-2", "source": "career"})
            best_rows = conn.execute(
                """
                SELECT id, activity_id, record_key, event_type, source, payload_json
                FROM career_record_events
                WHERE event_type = ?
                ORDER BY event_at, id
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchall()
            self.assertEqual(len(best_rows), 1)
            self.assertEqual(best_rows[0]["activity_id"], "run-2")
            self.assertEqual(best_rows[0]["record_key"], "running_5k")
            self.assertEqual(best_rows[0]["source"], "metric_series")
            best_payload = json.loads(best_rows[0]["payload_json"])
            self.assertEqual(best_payload["metric"]["value"], 1700.0)
            self.assertTrue(best_payload["metric_result_id"].startswith("metric_result:"))

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_BREAKING_EVENT_TYPE,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
                ).fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_pywebview_record_breaking_materialization_api_defaults_to_dry_run(self):
        api = main.Api.__new__(main.Api)
        with mock.patch.object(
            main.career_backend,
            "materialize_career_record_breaking_events",
            return_value={"ok": True, "dry_run": True, "summary": {"planned": 1}},
        ) as materialize:
            result = api.materialize_career_record_breaking_events({"sport": "running", "record_keys": ["running_5k"]})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["data"]["dry_run"])
        materialize.assert_called_once()
        self.assertTrue(materialize.call_args.kwargs["dry_run"])

    def test_pywebview_record_breaking_materialization_api_requires_explicit_apply(self):
        api = main.Api.__new__(main.Api)
        with mock.patch.object(
            main.career_backend,
            "materialize_career_record_breaking_events",
            return_value={"ok": True, "dry_run": False, "summary": {"upserted": 1}},
        ) as materialize:
            result = api.materialize_career_record_breaking_events({"sport": "running", "record_key": "running_5k", "dry_run": False})

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["data"]["dry_run"])
        materialize.assert_called_once()
        self.assertFalse(materialize.call_args.kwargs["dry_run"])

    def test_rebuild_backfills_record_breaking_events_from_existing_metric_results(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity_row(
                conn,
                activity_id="run-1",
                start_time="2026-07-18T08:00:00Z",
                elapsed_5k=1800,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-2",
                start_time="2026-07-19T08:00:00Z",
                elapsed_5k=1700,
            )

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            conn.execute(
                "DELETE FROM career_record_events WHERE event_type = ?",
                (career_backend.RECORD_BREAKING_EVENT_TYPE,),
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_BREAKING_EVENT_TYPE,),
                ).fetchone()[0],
                0,
            )

            dry = career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=True,
            )
            self.assertEqual(dry["summary"]["would_upsert"], 0)
            self.assertEqual(dry["summary"]["record_breaking_events"]["planned"], 1)
            self.assertEqual(dry["summary"]["record_breaking_events"]["current_best_planned"], 1)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_BREAKING_EVENT_TYPE,),
                ).fetchone()[0],
                0,
            )

            applied = career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            self.assertEqual(applied["summary"]["upserted"], 0)
            self.assertEqual(applied["summary"]["record_breaking_events"]["upserted"], 1)
            self.assertEqual(applied["summary"]["record_breaking_events"]["current_best_upserted"], 1)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_BREAKING_EVENT_TYPE,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
                ).fetchone()[0],
                1,
            )
        finally:
            conn.close()

    def test_invalidating_breakthrough_activity_recomputes_record_breaking_events(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity_row(
                conn,
                activity_id="run-1",
                start_time="2026-07-18T08:00:00Z",
                elapsed_5k=1800,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-2",
                start_time="2026-07-19T08:00:00Z",
                elapsed_5k=1700,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-3",
                start_time="2026-07-20T08:00:00Z",
                elapsed_5k=1600,
            )
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            before_ids = [
                row["activity_id"]
                for row in conn.execute(
                    """
                    SELECT activity_id
                    FROM career_record_events
                    WHERE event_type = ?
                    ORDER BY event_at, id
                    """,
                    (career_backend.RECORD_BREAKING_EVENT_TYPE,),
                ).fetchall()
            ]
            self.assertEqual(before_ids, ["run-2", "run-3"])

            applied = career_backend.invalidate_career_record_metric_results_for_activity(
                conn,
                "run-2",
                reason="delete_activities",
                dry_run=False,
            )

            self.assertEqual(applied["invalidated"], 1)
            self.assertEqual(applied["record_breaking_events"]["deleted"], 1)
            self.assertEqual(applied["record_breaking_events"]["current_best_deleted"], 0)
            rows = conn.execute(
                """
                SELECT activity_id, payload_json
                FROM career_record_events
                WHERE event_type = ?
                ORDER BY event_at, id
                """,
                (career_backend.RECORD_BREAKING_EVENT_TYPE,),
            ).fetchall()
            self.assertEqual([row["activity_id"] for row in rows], ["run-3"])
            payload = json.loads(rows[0]["payload_json"])
            self.assertEqual(payload["previous_best_metric"]["value"], 1800.0)
            best_rows = conn.execute(
                """
                SELECT activity_id, payload_json
                FROM career_record_events
                WHERE event_type = ?
                ORDER BY event_at, id
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchall()
            self.assertEqual([row["activity_id"] for row in best_rows], ["run-3"])
            best_payload = json.loads(best_rows[0]["payload_json"])
            self.assertEqual(best_payload["metric"]["value"], 1600.0)
        finally:
            conn.close()

    def test_invalidating_current_best_activity_recomputes_current_best_event(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity_row(
                conn,
                activity_id="run-1",
                start_time="2026-07-18T08:00:00Z",
                elapsed_5k=1800,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-2",
                start_time="2026-07-19T08:00:00Z",
                elapsed_5k=1700,
            )
            _insert_running_activity_row(
                conn,
                activity_id="run-3",
                start_time="2026-07-20T08:00:00Z",
                elapsed_5k=1600,
            )
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT activity_id FROM career_record_events WHERE event_type = ?",
                    (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
                ).fetchone()["activity_id"],
                "run-3",
            )

            applied = career_backend.invalidate_career_record_metric_results_for_activity(
                conn,
                "run-3",
                reason="delete_activities",
                dry_run=False,
            )

            self.assertEqual(applied["invalidated"], 1)
            self.assertEqual(applied["record_breaking_events"]["deleted"], 1)
            self.assertEqual(applied["record_breaking_events"]["current_best_deleted"], 1)
            best_rows = conn.execute(
                """
                SELECT activity_id, payload_json
                FROM career_record_events
                WHERE event_type = ?
                ORDER BY event_at, id
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchall()
            self.assertEqual([row["activity_id"] for row in best_rows], ["run-2"])
            best_payload = json.loads(best_rows[0]["payload_json"])
            self.assertEqual(best_payload["metric"]["value"], 1700.0)
        finally:
            conn.close()

    def test_activity_total_record_materializes_current_best_timeline_event(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_cycling_activity_row(
                conn,
                activity_id="ride-1",
                start_time="2026-07-18T08:00:00Z",
                distance_km=80.0,
            )
            _insert_cycling_activity_row(
                conn,
                activity_id="ride-2",
                start_time="2026-07-19T08:00:00Z",
                distance_km=120.0,
            )

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="cycling",
                record_keys=["cycling_longest_distance"],
                dry_run=False,
            )

            row = conn.execute(
                """
                SELECT activity_id, record_key, event_type, payload_json
                FROM career_record_events
                WHERE event_type = ?
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchone()
            self.assertEqual(row["activity_id"], "ride-2")
            self.assertEqual(row["record_key"], "cycling_longest_distance")
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["metric"]["value"], 120000.0)
        finally:
            conn.close()

    def test_metric_series_prefers_materialized_rows_without_activity_stream(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            career_backend.rebuild_career_record_metric_results(conn, sport="running", record_keys=["running_5k"], dry_run=False)
            profile_backend.mark_app_migration_done(conn, career_backend.DERIVED_METRICS_UPGRADE_KEY)
            conn.execute("UPDATE activities SET points_json = NULL WHERE id = 'run-1'")
            career_backend._clear_record_metric_series_cache()

            series = career_backend.get_career_record_metric_series("running_5k", {"sport": "running"}, conn=conn)
            self.assertEqual(series["metrics"]["source"], "materialized")
            self.assertTrue(series["metrics"]["materialized_hit"])
            self.assertEqual(series["summary"]["point_count"], 1)
            self.assertEqual(series["current_best"]["activity_id"], "run-1")
        finally:
            conn.close()

    def test_metric_series_falls_back_when_materialized_rows_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)

            series = career_backend.get_career_record_metric_series("running_5k", {"sport": "running"}, conn=conn)
            self.assertEqual(series["metrics"]["source"], "resolver_fallback")
            self.assertFalse(series["metrics"]["materialized_hit"])
            self.assertEqual(series["summary"]["point_count"], 1)
        finally:
            conn.close()

    def test_metric_series_does_not_fallback_for_empty_key_after_sport_is_materialized(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            career_backend.rebuild_career_record_metric_results(conn, sport="running", record_keys=["running_5k"], dry_run=False)
            profile_backend.mark_app_migration_done(conn, career_backend.DERIVED_METRICS_UPGRADE_KEY)
            career_backend._clear_record_metric_series_cache()

            with mock.patch.object(career_backend, "_record_metric_series_activity_rows") as rows:
                series = career_backend.get_career_record_metric_series("running_10k", {"sport": "running"}, conn=conn)

            rows.assert_not_called()
            self.assertEqual(series["metrics"]["source"], "materialized_empty")
            self.assertTrue(series["metrics"]["materialized_hit"])
            self.assertEqual(series["metrics"]["scanned"], 0)
            self.assertEqual(series["summary"]["point_count"], 0)
        finally:
            conn.close()

    def test_half_materialized_old_cycling_db_does_not_mask_missing_distance_keys(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_cycling_activity_row(
                conn,
                activity_id="ride-52k",
                start_time="2026-06-01T08:00:00Z",
                distance_km=52.0,
            )
            _insert_cycling_activity_row(
                conn,
                activity_id="ride-short-1",
                start_time="2026-07-01T08:00:00Z",
                distance_km=5.24,
            )
            _insert_cycling_activity_row(
                conn,
                activity_id="ride-short-2",
                start_time="2026-07-02T08:00:00Z",
                distance_km=4.8,
            )
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="cycling",
                record_keys=["cycling_longest_distance"],
                dry_run=False,
            )
            conn.execute(
                """
                UPDATE career_record_metric_results
                SET status = 'invalidated'
                WHERE activity_id = 'ride-52k'
                  AND record_key = 'cycling_longest_distance'
                """
            )
            career_backend._clear_record_metric_series_cache()

            longest = career_backend.get_career_record_metric_series(
                "cycling_longest_distance",
                {"sport": "cycling"},
                conn=conn,
            )
            fastest_10k = career_backend.get_career_record_metric_series(
                "cycling_fastest_10k",
                {"sport": "cycling"},
                conn=conn,
            )
            fastest_20k = career_backend.get_career_record_metric_series(
                "cycling_fastest_20k",
                {"sport": "cycling"},
                conn=conn,
            )

            self.assertNotEqual(longest["metrics"]["source"], "materialized_empty")
            self.assertEqual(longest["current_best"]["activity_id"], "ride-52k")
            self.assertEqual(longest["current_best"]["metric"]["value"], 52000.0)
            self.assertEqual(fastest_10k["summary"]["point_count"], 1)
            self.assertEqual(fastest_10k["current_best"]["activity_id"], "ride-52k")
            self.assertEqual(fastest_20k["summary"]["point_count"], 1)
            self.assertEqual(fastest_20k["current_best"]["activity_id"], "ride-52k")
            self.assertNotEqual(fastest_10k["metrics"]["source"], "materialized_empty")
            self.assertNotEqual(fastest_20k["metrics"]["source"], "materialized_empty")
        finally:
            conn.close()

    def test_records_list_current_best_uses_materialized_rows(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            career_backend.rebuild_career_record_metric_results(conn, sport="running", record_keys=["running_5k"], dry_run=False)
            profile_backend.mark_app_migration_done(conn, career_backend.DERIVED_METRICS_UPGRADE_KEY)
            conn.execute("UPDATE activities SET points_json = NULL WHERE id = 'run-1'")
            career_backend._clear_record_metric_series_cache()

            records = career_backend.get_career_records({"sport": "running", "record_key": "running_5k"}, conn=conn)
            self.assertTrue(records["records"])
            self.assertEqual(records["records"][0]["record_key"], "running_5k")
            self.assertEqual(records["records"][0]["activity_id"], "run-1")
        finally:
            conn.close()

    def test_pywebview_maintenance_api_defaults_to_dry_run(self):
        api = main.Api.__new__(main.Api)
        with mock.patch.object(
            main.career_backend,
            "rebuild_career_record_metric_results",
            return_value={"ok": True, "dry_run": True, "summary": {"would_upsert": 1}},
        ) as rebuild:
            result = api.rebuild_career_record_metric_results({"sport": "running", "record_keys": ["running_5k"]})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["data"]["dry_run"])
        rebuild.assert_called_once()
        self.assertTrue(rebuild.call_args.kwargs["dry_run"])

    def test_pywebview_maintenance_api_requires_explicit_apply(self):
        api = main.Api.__new__(main.Api)
        with mock.patch.object(
            main.career_backend,
            "rebuild_career_record_metric_results",
            return_value={"ok": True, "dry_run": False, "summary": {"upserted": 1}},
        ) as rebuild:
            result = api.rebuild_career_record_metric_results({"sport": "running", "record_key": "running_5k", "dry_run": False})

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["data"]["dry_run"])
        rebuild.assert_called_once()
        self.assertFalse(rebuild.call_args.kwargs["dry_run"])

    def test_dry_run_planner_payload_is_safe_and_does_not_touch_ai_insights(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _create_schema(conn)
            _insert_running_activity(conn)
            row = conn.execute("SELECT * FROM activities WHERE id = 'run-1'").fetchone()

            ai_before = conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0]
            plan = career_backend.compute_record_metric_results_for_activity(row, record_keys=["running_5k"], conn=conn)
            ai_after = conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0]

            self.assertEqual(ai_before, ai_after)
            payload = json.dumps(plan, ensure_ascii=False, sort_keys=True)
            for token in _forbidden_tokens():
                self.assertNotIn(token, payload)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
