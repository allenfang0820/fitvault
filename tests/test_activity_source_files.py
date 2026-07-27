import sqlite3
import tempfile
import unittest
from pathlib import Path

import profile_backend


class TestActivitySourceFiles(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "profile.sqlite"
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        profile_backend._init_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_schema_and_indexes_are_created_idempotently(self):
        profile_backend._init_schema(self.conn)
        table = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'activity_source_files'"
        ).fetchone()
        indexes = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        self.assertIsNotNone(table)
        self.assertTrue({
            "uq_activity_source_files_provider_activity",
            "idx_activity_source_files_sha256",
            "idx_activity_source_files_activity_id",
            "idx_activity_source_files_file_path",
        }.issubset(indexes))

    def test_provider_activity_id_is_idempotent_and_sha256_is_queryable(self):
        first_id = profile_backend.upsert_activity_source_file(
            self.conn,
            provider="garmin",
            provider_activity_id="123",
            file_path="/tracks/activity.fit",
            filename="activity.fit",
            sha256="ABC123",
            file_size=10,
            file_mtime=1.5,
            ingest_status="pending",
        )
        second_id = profile_backend.upsert_activity_source_file(
            self.conn,
            provider="garmin",
            provider_activity_id="123",
            file_path="/tracks/activity.fit",
            filename="activity.fit",
            sha256="abc123",
            file_size=11,
            file_mtime=2.5,
            activity_id=7,
            ingest_status="parsed",
        )
        self.assertEqual(first_id, second_id)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM activity_source_files").fetchone()[0],
            1,
        )
        row = profile_backend.get_activity_source_file_by_provider_activity_id(
            self.conn, "garmin", "123"
        )
        self.assertEqual(row["ingest_status"], "parsed")
        self.assertEqual(row["activity_id"], 7)
        self.assertEqual(
            profile_backend.get_activity_source_file_by_sha256(self.conn, "ABC123")["id"],
            first_id,
        )
        self.assertEqual(
            [row["id"] for row in profile_backend.get_activity_source_files_by_sha256(self.conn, "ABC123")],
            [first_id],
        )

    def test_provider_activity_id_may_be_empty_and_status_can_be_retried(self):
        source_id = profile_backend.upsert_activity_source_file(
            self.conn,
            provider="coros",
            file_path="/tracks/coros.fit",
            filename="coros.fit",
            ingest_status="failed",
            error="token=secret-value; parser failed",
        )
        row = self.conn.execute(
            "SELECT * FROM activity_source_files WHERE id = ?", (source_id,)
        ).fetchone()
        self.assertIsNone(row["provider_activity_id"])
        self.assertEqual(row["ingest_status"], "failed")
        self.assertNotIn("secret-value", row["error"])
        self.assertIn("[REDACTED]", row["error"])

        retried_id = profile_backend.upsert_activity_source_file(
            self.conn,
            provider="coros",
            file_path="/tracks/coros.fit",
            filename="coros.fit",
            ingest_status="skipped",
            error=None,
            source_file_id=source_id,
        )
        self.assertEqual(retried_id, source_id)
        self.assertEqual(
            self.conn.execute(
                "SELECT ingest_status FROM activity_source_files WHERE id = ?",
                (source_id,),
            ).fetchone()[0],
            "skipped",
        )

    def test_helper_does_not_commit_or_close_callers_connection(self):
        source_id = profile_backend.upsert_activity_source_file(
            self.conn,
            provider="local",
            file_path="/tracks/local.fit",
            filename="local.fit",
        )
        self.assertGreater(source_id, 0)
        self.assertTrue(self.conn.in_transaction)
        self.conn.rollback()
        self.assertIsNone(
            self.conn.execute(
                "SELECT id FROM activity_source_files WHERE id = ?", (source_id,)
            ).fetchone()
        )

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            profile_backend.upsert_activity_source_file(
                self.conn,
                provider="local",
                file_path="/tracks/local.fit",
                filename="local.fit",
                ingest_status="processing",
            )

    def test_error_sanitizer_redacts_authorization_and_limits_length(self):
        error = "Authorization=Bearer private-token " + ("x" * 1000)
        sanitized = profile_backend._sanitize_activity_source_file_error(error)
        self.assertNotIn("private-token", sanitized)
        self.assertIn("[REDACTED]", sanitized)
        self.assertLessEqual(len(sanitized), profile_backend.ACTIVITY_SOURCE_FILE_ERROR_MAX_LENGTH)


if __name__ == "__main__":
    unittest.main()
