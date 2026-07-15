import json
import sqlite3
import sys
import unittest
from pathlib import Path

import career_backend

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_career_year_snapshot_period_comparison import _create_tables, _insert_activity


class TestCareerYearSnapshotPersistence(unittest.TestCase):
    def test_save_year_snapshot_uses_stable_id_type_and_version(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00")

            result = career_backend.save_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            row = conn.execute(
                """
                SELECT id, snapshot_type, source_version, content_json
                FROM career_snapshots
                WHERE id = 'career_snapshot:year:2026'
                """
            ).fetchone()
            content = json.loads(row[3])

            self.assertTrue(result["saved"])
            self.assertEqual(row[0], "career_snapshot:year:2026")
            self.assertEqual(row[1], "career_year")
            self.assertEqual(row[2], "acs.year.v2")
            self.assertEqual(content["year"], 2026)
            self.assertEqual(result["source_fingerprint"], content["source_fingerprint"])
        finally:
            conn.close()

    def test_multiple_years_and_full_career_snapshot_are_isolated(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00")
            _insert_activity(conn, id=2, start_time="2025-05-01T07:00:00+08:00")

            career_backend.save_career_snapshot(conn=conn)
            career_backend.save_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            career_backend.save_career_year_snapshot(2025, conn=conn, as_of_date="2026-07-14")

            rows = conn.execute("SELECT id, snapshot_type FROM career_snapshots ORDER BY id").fetchall()

            self.assertEqual(
                rows,
                [
                    ("career_snapshot:latest", "career"),
                    ("career_snapshot:year:2025", "career_year"),
                    ("career_snapshot:year:2026", "career_year"),
                ],
            )
        finally:
            conn.close()

    def test_get_year_snapshot_empty_state_does_not_generate(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)

            result = career_backend.get_career_year_snapshot(2026, conn=conn)
            count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]

            self.assertIsNone(result["snapshot"])
            self.assertEqual(result["status"]["message"], "暂无 Year Snapshot")
            self.assertEqual(count, 0)
        finally:
            conn.close()

    def test_get_year_snapshot_returns_sanitized_historical_dirty_content(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            dirty = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            dirty["summary"]["activity_count"] = 1
            dirty["summary"]["file_path"] = "/Users/example/private.fit"
            dirty["evidence_catalog"] = []
            dirty["data_quality"]["storage_ref"] = "/Users/example/private.jpg"
            dirty["source_fingerprint"] = career_backend.compute_career_year_source_fingerprint(dirty)
            conn.execute(
                """
                INSERT INTO career_snapshots
                    (id, snapshot_type, generated_at, content_json, source_version)
                VALUES
                    ('career_snapshot:year:2026', 'career_year', '2026-07-14T00:00:00+00:00', ?, 'acs.year.v2')
                """,
                (json.dumps(dirty, ensure_ascii=False),),
            )

            result = career_backend.get_career_year_snapshot(2026, conn=conn)
            serialized = repr(result)

            self.assertEqual(result["snapshot"]["year"], 2026)
            self.assertNotIn("file_path", serialized)
            self.assertNotIn("storage_ref", serialized)
            self.assertNotIn("/Users/example", serialized)
            self.assertEqual(
                result["source_fingerprint"],
                career_backend.compute_career_year_source_fingerprint(result["snapshot"]),
            )
        finally:
            conn.close()

    def test_save_rolls_back_when_snapshot_contains_forbidden_content(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00")
            original = career_backend.build_career_year_snapshot

            def dirty_builder(*args, **kwargs):
                snapshot = original(*args, **kwargs)
                snapshot["summary"]["file_path"] = "/Users/example/private.fit"
                return snapshot

            career_backend.build_career_year_snapshot = dirty_builder
            with self.assertRaises(ValueError):
                career_backend.save_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            count = conn.execute("SELECT COUNT(*) FROM career_snapshots").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            career_backend.build_career_year_snapshot = original
            conn.close()

    def test_no_pywebview_write_api_is_exposed_for_year_snapshot(self):
        import inspect
        import main

        source = inspect.getsource(main.Api)
        self.assertNotIn("save_career_year_snapshot", source)


if __name__ == "__main__":
    unittest.main()
