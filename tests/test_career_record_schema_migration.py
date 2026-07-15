import sqlite3
import unittest
from unittest import mock

import career_backend


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _index_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table_name})")}


def _create_legacy_pb_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE career_pb_records (
            id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            pb_type TEXT NOT NULL,
            value TEXT NOT NULL,
            value_unit TEXT NOT NULL DEFAULT '',
            improvement TEXT,
            event_date TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL DEFAULT 'resolver',
            status TEXT NOT NULL DEFAULT 'active',
            display_metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _insert_legacy_pb(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_pb_records
            (id, activity_id, sport, pb_type, value, value_unit, improvement,
             event_date, confidence, source, status, display_metadata_json)
        VALUES
            ('pb:running_5k:1', '1', 'running', 'running_5k', '1500', 'seconds',
             NULL, '2026-05-19', 1.0, 'resolver', 'active', '{}')
        """
    )


class CareerRecordSchemaMigrationTest(unittest.TestCase):
    def test_empty_database_creates_record_schema_and_indexes(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.ensure_career_schema(conn)

            self.assertTrue(result["ok"])
            pb_columns = _columns(conn, "career_pb_records")
            for column in {
                "evidence_key",
                "source_mode",
                "sport_scope",
                "previous_record_id",
                "resolver_version",
                "confirmed_at",
                "rejected_at",
                "invalidated_at",
                "decision_source",
                "decided_at",
                "record_key",
                "record_family",
                "scope_json",
                "scope_key",
                "scope_hash",
                "range_json",
                "quality_json",
                "metric_value_num",
                "metric_name",
                "catalog_state",
                "rule_version",
            }:
                self.assertIn(column, pb_columns)
            self.assertIn("event_type", _columns(conn, "career_record_events"))
            self.assertIn("payload_json", _columns(conn, "career_record_events"))
            for column in {"record_key", "scope_hash", "scope_key", "run_id", "decision", "reason_codes_json"}:
                self.assertIn(column, _columns(conn, "career_record_events"))
            self.assertTrue(career_backend._table_exists(conn, "career_record_curve_cache"))
            self.assertFalse(career_backend._table_exists(conn, "career_route_signatures"))
            self.assertFalse(career_backend._table_exists(conn, "career_route_matches"))

            pb_indexes = _index_names(conn, "career_pb_records")
            self.assertIn("ux_career_pb_records_active_scope", pb_indexes)
            self.assertIn("ux_career_pb_records_evidence_version", pb_indexes)
            self.assertIn("ux_career_pb_records_active_v2_scope", pb_indexes)
            self.assertIn("ux_career_pb_records_evidence_v2", pb_indexes)
            event_indexes = _index_names(conn, "career_record_events")
            self.assertIn("idx_career_record_events_record", event_indexes)
            self.assertIn("idx_career_record_events_evidence", event_indexes)
            self.assertIn("idx_career_record_events_record_scope", event_indexes)
            self.assertIn("ux_career_record_curve_cache_current", _index_names(conn, "career_record_curve_cache"))
        finally:
            conn.close()

    def test_migration_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = career_backend.ensure_career_schema(conn)
            second = career_backend.ensure_career_schema(conn)

            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertEqual(second["created"], [])
            self.assertEqual(second["migrated"], [])
        finally:
            conn.close()

    def test_legacy_pb_table_is_upgraded_and_still_readable(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_legacy_pb_table(conn)
            _insert_legacy_pb(conn)

            result = career_backend.ensure_career_schema(conn)

            self.assertTrue(result["ok"])
            self.assertIn("career_pb_records.evidence_key", result["migrated"])
            row = conn.execute(
                """
                SELECT evidence_key, source_mode, sport_scope, resolver_version, decision_source,
                       record_key, record_family, scope_json, scope_key, scope_hash,
                       metric_value_num, metric_name, catalog_state, rule_version, quality_json
                FROM career_pb_records
                WHERE id = 'pb:running_5k:1'
                """
            ).fetchone()
            self.assertEqual(row[0], "activity_total:1:running_5k:1500")
            self.assertEqual(row[1], "activity_total")
            self.assertEqual(row[2], "default")
            self.assertEqual(row[3], "legacy")
            self.assertEqual(row[4], "resolver")
            self.assertEqual(row[5], "running_5k")
            self.assertEqual(row[6], "distance_time_pb")
            self.assertEqual(row[7], '{"sport_scope":"default"}')
            self.assertEqual(row[8], "default")
            self.assertTrue(str(row[9]).startswith("scope:v2:sha256:"))
            self.assertEqual(row[10], 1500)
            self.assertEqual(row[11], "elapsed_time_sec")
            self.assertEqual(row[12], "available")
            self.assertEqual(row[13], "records-v1")
            self.assertIn('"legacy":true', row[14])

            pb_payload = career_backend.get_career_pb(conn=conn)
            self.assertEqual(pb_payload["summary"]["total"], 1)
            self.assertEqual(pb_payload["pb_records"][0]["id"], "pb:running_5k:1")
        finally:
            conn.close()

    def test_partial_legacy_schema_adds_only_missing_pb_columns(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_legacy_pb_table(conn)
            conn.execute("ALTER TABLE career_pb_records ADD COLUMN evidence_key TEXT NOT NULL DEFAULT ''")

            result = career_backend.ensure_career_schema(conn)

            self.assertNotIn("career_pb_records.evidence_key", result["migrated"])
            self.assertIn("career_pb_records.source_mode", result["migrated"])
            self.assertIn("career_pb_records.decided_at", result["migrated"])
        finally:
            conn.close()

    def test_failed_migration_rolls_back_schema_changes_without_losing_legacy_pb(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_legacy_pb_table(conn)
            _insert_legacy_pb(conn)

            with mock.patch.object(career_backend, "_ensure_career_indexes", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    career_backend.ensure_career_schema(conn)

            row = conn.execute("SELECT id, value FROM career_pb_records WHERE id = 'pb:running_5k:1'").fetchone()
            self.assertEqual(row, ("pb:running_5k:1", "1500"))
            self.assertNotIn("evidence_key", _columns(conn, "career_pb_records"))
            self.assertFalse(career_backend._table_exists(conn, "career_record_events"))
        finally:
            conn.close()

    def test_v2_schema_dry_run_plan_is_read_only(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_legacy_pb_table(conn)
            _insert_legacy_pb(conn)
            before_tables = set(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            before_columns = _columns(conn, "career_pb_records")

            plan = career_backend.plan_career_records_v2_schema_migration(conn)

            after_tables = set(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            self.assertTrue(plan["dry_run"])
            self.assertIn("career_record_curve_cache", plan["would_create_tables"])
            self.assertIn("career_pb_records.scope_hash", plan["would_add_columns"])
            self.assertIn("ux_career_pb_records_active_v2_scope", plan["would_create_indexes"])
            self.assertEqual(before_tables, after_tables)
            self.assertEqual(before_columns, _columns(conn, "career_pb_records"))
        finally:
            conn.close()

    def test_v2_schema_dry_run_reports_active_scope_conflicts(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE career_pb_records (
                    id TEXT PRIMARY KEY,
                    activity_id TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    pb_type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_unit TEXT NOT NULL DEFAULT '',
                    event_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    source_mode TEXT NOT NULL DEFAULT 'activity_total',
                    record_key TEXT,
                    scope_hash TEXT
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO career_pb_records
                    (id, activity_id, sport, pb_type, value, value_unit, event_date, status, source_mode, record_key, scope_hash)
                VALUES (?, ?, 'running', 'running_5k', '1500', 'seconds', '2026-01-01', 'active', 'activity_total', 'running_5k', 'scope:v2:sha256:duplicate')
                """,
                [("one", "1"), ("two", "2")],
            )

            plan = career_backend.plan_career_records_v2_schema_migration(conn)

            self.assertFalse(plan["ok"])
            self.assertTrue(plan["blocked"])
            self.assertEqual(plan["active_scope_conflicts"][0]["record_key"], "running_5k")
            self.assertEqual(plan["active_scope_conflicts"][0]["count"], 2)
        finally:
            conn.close()

    def test_v2_curve_cache_does_not_store_raw_stream_or_path_columns(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            forbidden = {"points", "track_json", "power_stream", "file_path", "storage_ref", "real_lat", "real_lon", "weight_history"}
            self.assertTrue(forbidden.isdisjoint(_columns(conn, "career_record_curve_cache")))
        finally:
            conn.close()

    def test_curve_cache_fingerprint_is_stable_and_scope_sensitive(self):
        scope = {"sport_scope": "outdoor", "indoor_scope": "", "ignored": "x"}

        first = career_backend.compute_career_record_curve_input_fingerprint(
            activity_id="42",
            sport="cycling",
            source_mode="best_effort_duration",
            canonical_facts_version="facts:v1",
            stream_summary_hash="stream:abc",
            algorithm_version="power-curve:v1",
            rule_version="records-v2",
            scope=scope,
        )
        second = career_backend.compute_career_record_curve_input_fingerprint(
            activity_id="42",
            sport="cycling",
            source_mode="best_effort_duration",
            canonical_facts_version="facts:v1",
            stream_summary_hash="stream:abc",
            algorithm_version="power-curve:v1",
            rule_version="records-v2",
            scope={"ignored": "y", "sport_scope": "outdoor"},
        )
        changed = career_backend.compute_career_record_curve_input_fingerprint(
            activity_id="42",
            sport="cycling",
            source_mode="best_effort_duration",
            canonical_facts_version="facts:v1",
            stream_summary_hash="stream:changed",
            algorithm_version="power-curve:v1",
            rule_version="records-v2",
            scope=scope,
        )

        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_curve_cache_save_hit_refresh_and_activity_invalidation(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
                activity_id="42",
                sport="cycling",
                source_mode="best_effort_duration",
                canonical_facts_version="facts:v1",
                stream_summary_hash="stream:abc",
                algorithm_version="power-curve:v1",
                rule_version="records-v2",
                scope={"sport_scope": "outdoor"},
            )

            saved = career_backend.save_career_record_curve_cache(
                activity_id="42",
                sport="cycling",
                curve_type="cycling_power_duration_curve",
                source_mode="best_effort_duration",
                scope={"sport_scope": "outdoor"},
                input_fingerprint=fingerprint,
                algorithm_version="power-curve:v1",
                curve={"anchors": [{"duration_sec": 300, "value": 250}]},
                quality={"confidence": 0.98},
                generated_at="2026-07-14T01:00:00Z",
                conn=conn,
            )
            refreshed = career_backend.save_career_record_curve_cache(
                activity_id="42",
                sport="cycling",
                curve_type="cycling_power_duration_curve",
                source_mode="best_effort_duration",
                scope={"sport_scope": "outdoor"},
                input_fingerprint=fingerprint,
                algorithm_version="power-curve:v1",
                curve={"anchors": [{"duration_sec": 300, "value": 252}]},
                quality={"confidence": 0.99},
                generated_at="2026-07-14T01:05:00Z",
                conn=conn,
            )
            hit = career_backend.get_career_record_curve_cache(
                activity_id="42",
                curve_type="cycling_power_duration_curve",
                source_mode="best_effort_duration",
                scope={"sport_scope": "outdoor"},
                input_fingerprint=fingerprint,
                algorithm_version="power-curve:v1",
                conn=conn,
            )

            self.assertEqual(saved["id"], refreshed["id"])
            self.assertEqual(hit["curve"]["anchors"][0]["value"], 252)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_curve_cache").fetchone()[0], 1)

            invalidated = career_backend.invalidate_career_record_curve_cache(activity_id="42", conn=conn)
            self.assertEqual(invalidated, 1)
            self.assertIsNone(
                career_backend.get_career_record_curve_cache(
                    activity_id="42",
                    curve_type="cycling_power_duration_curve",
                    source_mode="best_effort_duration",
                    scope={"sport_scope": "outdoor"},
                    input_fingerprint=fingerprint,
                    algorithm_version="power-curve:v1",
                    conn=conn,
                )
            )
        finally:
            conn.close()

    def test_curve_cache_version_cleanup_invalidates_old_current_rows(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            for version in ("power-curve:v1", "power-curve:v2"):
                fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
                    activity_id=f"42-{version}",
                    sport="cycling",
                    source_mode="best_effort_duration",
                    canonical_facts_version="facts:v1",
                    stream_summary_hash=f"stream:{version}",
                    algorithm_version=version,
                    rule_version="records-v2",
                )
                career_backend.save_career_record_curve_cache(
                    activity_id=f"42-{version}",
                    sport="cycling",
                    curve_type="cycling_power_duration_curve",
                    source_mode="best_effort_duration",
                    input_fingerprint=fingerprint,
                    algorithm_version=version,
                    curve={"anchors": [{"duration_sec": 60, "value": 200}]},
                    conn=conn,
                )

            result = career_backend.cleanup_career_record_curve_cache_versions(
                curve_type="cycling_power_duration_curve",
                keep_algorithm_versions=("power-curve:v2",),
                conn=conn,
            )

            active_versions = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT algorithm_version
                    FROM career_record_curve_cache
                    WHERE invalidated_at IS NULL
                    ORDER BY algorithm_version
                    """
                ).fetchall()
            ]
            self.assertEqual(result, {"invalidated": 1})
            self.assertEqual(active_versions, ["power-curve:v2"])
        finally:
            conn.close()

    def test_curve_cache_rejects_raw_stream_paths_and_private_payload(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            fingerprint = career_backend.compute_career_record_curve_input_fingerprint(
                activity_id="42",
                sport="cycling",
                source_mode="best_effort_duration",
                canonical_facts_version="facts:v1",
                stream_summary_hash="stream:abc",
                algorithm_version="power-curve:v1",
                rule_version="records-v2",
            )

            with self.assertRaisesRegex(ValueError, "power_stream"):
                career_backend.save_career_record_curve_cache(
                    activity_id="42",
                    sport="cycling",
                    curve_type="cycling_power_duration_curve",
                    source_mode="best_effort_duration",
                    input_fingerprint=fingerprint,
                    algorithm_version="power-curve:v1",
                    curve={"power_stream": [100, 101, 102]},
                    conn=conn,
                )

            with self.assertRaisesRegex(ValueError, "local path"):
                career_backend.save_career_record_curve_cache(
                    activity_id="42",
                    sport="cycling",
                    curve_type="cycling_power_duration_curve",
                    source_mode="best_effort_duration",
                    input_fingerprint=fingerprint,
                    algorithm_version="power-curve:v1",
                    curve={"anchors": [{"duration_sec": 60, "value": 200}]},
                    quality={"source": "/Users/fanglei/private.fit"},
                    conn=conn,
                )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_record_curve_cache").fetchone()[0], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
