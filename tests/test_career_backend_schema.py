import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


EXPECTED_CAREER_TABLES = {
    "career_schema_meta",
    "career_race_events",
    "career_pb_records",
    "career_achievement_events",
    "career_memory_items",
    "career_snapshots",
    "career_event_candidates",
}

FORBIDDEN_RAW_FACT_COLUMNS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "gps",
    "heart_rate",
    "file_path",
}


def _table_columns(conn, table_name):
    return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table_name})")}


class TestCareerBackendSchema(unittest.TestCase):
    def test_module_exports_schema_entrypoint(self):
        self.assertTrue(hasattr(career_backend, "ensure_career_schema"))
        self.assertIsInstance(career_backend.CAREER_SCHEMA_VERSION, str)
        self.assertTrue(career_backend.CAREER_SCHEMA_VERSION)
        self.assertTrue(hasattr(career_backend, "CAREER_BUSINESS_TABLES"))

    def test_ensure_career_schema_is_idempotent_with_external_connection(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = career_backend.ensure_career_schema(conn)
            second = career_backend.ensure_career_schema(conn)

            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertEqual(first["schema_version"], career_backend.CAREER_SCHEMA_VERSION)
            self.assertEqual(second["schema_version"], career_backend.CAREER_SCHEMA_VERSION)
            self.assertIn("career_schema_meta", first["created"])
            self.assertNotIn("career_schema_meta", second["created"])
            for table_name in career_backend.CAREER_BUSINESS_TABLES:
                self.assertIn(table_name, first["created"])
                self.assertNotIn(table_name, second["created"])

            tables = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
            self.assertTrue(EXPECTED_CAREER_TABLES.issubset(tables))

            version = conn.execute(
                "SELECT value FROM career_schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            self.assertEqual(version[0], career_backend.CAREER_SCHEMA_VERSION)
        finally:
            conn.close()

    def test_ensure_career_schema_uses_profile_db_path_without_platform_specific_path(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"

                result = career_backend.ensure_career_schema()

                self.assertTrue(result["ok"])
                self.assertTrue(profile_backend.DB_PATH.exists())
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM career_schema_meta"
                    ).fetchone()[0]
                    self.assertGreaterEqual(count, 1)
                    tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        ).fetchall()
                    }
                    self.assertTrue(EXPECTED_CAREER_TABLES.issubset(tables))
                finally:
                    conn.close()
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_ensure_career_schema_supports_unicode_and_space_db_paths(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 ACS 路径 ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "含 空格 子目录" / "运动生涯 数据库.sqlite"

                first = career_backend.ensure_career_schema()
                second = career_backend.ensure_career_schema()

                self.assertTrue(first["ok"])
                self.assertTrue(second["ok"])
                self.assertTrue(profile_backend.DB_PATH.exists())
                self.assertIn("career_schema_meta", first["created"])
                self.assertNotIn("career_schema_meta", second["created"])
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        ).fetchall()
                    }
                    self.assertTrue(EXPECTED_CAREER_TABLES.issubset(tables))
                finally:
                    conn.close()
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_career_business_tables_keep_activity_traceability(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            required_columns = {
                "career_race_events": {
                    "id",
                    "activity_id",
                    "name",
                    "event_type",
                    "sport",
                    "event_date",
                    "location_json",
                    "performance_summary_json",
                    "achievement_ids_json",
                    "confidence",
                    "source",
                    "status",
                    "display_metadata_json",
                },
                "career_pb_records": {
                    "id",
                    "activity_id",
                    "sport",
                    "pb_type",
                    "value",
                    "value_unit",
                    "improvement",
                    "event_date",
                    "confidence",
                    "source",
                    "status",
                    "display_metadata_json",
                },
                "career_achievement_events": {
                    "id",
                    "activity_id",
                    "achievement_type",
                    "title",
                    "event_date",
                    "score",
                    "icon",
                    "description",
                    "confidence",
                    "source",
                    "status",
                    "display_metadata_json",
                },
                "career_memory_items": {
                    "id",
                    "race_id",
                    "activity_id",
                    "memory_type",
                    "storage_ref",
                    "story_text",
                    "metadata_json",
                },
                "career_event_candidates": {
                    "id",
                    "activity_id",
                    "candidate_type",
                    "title",
                    "evidence_json",
                    "confidence",
                    "status",
                },
            }
            for table_name, columns in required_columns.items():
                actual = set(_table_columns(conn, table_name))
                self.assertTrue(columns.issubset(actual), table_name)
                self.assertIn("activity_id", actual, table_name)
        finally:
            conn.close()

    def test_career_schema_does_not_store_raw_activity_facts_or_local_paths(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            for table_name in career_backend.CAREER_BUSINESS_TABLES:
                columns = set(_table_columns(conn, table_name))
                self.assertFalse(
                    FORBIDDEN_RAW_FACT_COLUMNS.intersection(columns),
                    f"{table_name} contains forbidden raw fact columns",
                )
            memory_columns = set(_table_columns(conn, "career_memory_items"))
            self.assertIn("storage_ref", memory_columns)
            self.assertNotIn("path", memory_columns)
            self.assertNotIn("file_path", memory_columns)
        finally:
            conn.close()

    def test_career_snapshots_are_ai_snapshot_records_not_raw_inputs(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            columns = set(_table_columns(conn, "career_snapshots"))
            self.assertTrue(
                {
                    "id",
                    "snapshot_type",
                    "generated_at",
                    "content_json",
                    "source_version",
                    "created_at",
                }.issubset(columns)
            )
            self.assertNotIn("activity_id", columns)
            self.assertFalse(FORBIDDEN_RAW_FACT_COLUMNS.intersection(columns))
        finally:
            conn.close()

    def test_career_indexes_exist_for_core_lookup_paths(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            self.assertIn("idx_career_race_events_activity", indexes)
            self.assertIn("idx_career_pb_records_sport_type_date", indexes)
            self.assertIn("idx_career_event_candidates_status", indexes)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
