import sqlite3
import unittest

import career_backend


def _table_names(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


class TestCareerAiInsightsRepository(unittest.TestCase):
    def test_current_schema_ensure_is_read_only_and_skips_migration(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            statements: list[str] = []
            conn.set_trace_callback(statements.append)
            conn.execute("PRAGMA query_only = ON")

            result = career_backend.ensure_career_schema(conn)

            write_prefixes = ("CREATE", "ALTER", "INSERT", "UPDATE", "DELETE", "SAVEPOINT")
            writes = [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith(write_prefixes)
            ]
            self.assertTrue(result["cached"])
            self.assertEqual(writes, [])
        finally:
            conn.close()

    def test_schema_creates_table_unique_constraint_and_indexes_idempotently(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = career_backend.ensure_career_schema(conn)
            second = career_backend.ensure_career_schema(conn)
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(career_ai_insights)").fetchall()
            }
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(career_ai_insights)").fetchall()
            }

            self.assertIn("career_ai_insights", first["created"])
            self.assertIn("career_ai_insights", _table_names(conn))
            self.assertEqual(second["ok"], True)
            self.assertTrue(
                {
                    "id",
                    "scope",
                    "scope_key",
                    "snapshot_fingerprint",
                    "snapshot_version",
                    "prompt_version",
                    "model_id",
                    "content_json",
                    "generated_at",
                    "created_at",
                    "status",
                }.issubset(columns)
            )
            self.assertTrue(
                any("scope_key_status_generated" in index_name for index_name in indexes),
                indexes,
            )
            self.assertTrue(
                any("sqlite_autoindex_career_ai_insights" in index_name for index_name in indexes),
                indexes,
            )
        finally:
            conn.close()

    def test_ready_cache_requires_validation_and_switches_current_atomically(self):
        conn = sqlite3.connect(":memory:")
        try:
            with self.assertRaises(ValueError):
                career_backend.save_ready_career_ai_insight(
                    scope="career_year",
                    scope_key="2026",
                    snapshot_fingerprint="sha256:a",
                    snapshot_version="acs.year.v1",
                    prompt_version="year.prompt.v1",
                    model_id="test-model",
                    content={"headline": "未经校验"},
                    content_validated=False,
                    conn=conn,
                )

            first = career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:a",
                snapshot_version="acs.year.v1",
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "第一版"},
                content_validated=True,
                generated_at="2026-07-14T00:00:00+00:00",
                conn=conn,
            )
            second = career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:b",
                snapshot_version="acs.year.v1",
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "第二版"},
                content_validated=True,
                generated_at="2026-07-15T00:00:00+00:00",
                conn=conn,
            )

            statuses = dict(
                conn.execute("SELECT snapshot_fingerprint, status FROM career_ai_insights").fetchall()
            )
            current = career_backend.get_current_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                conn=conn,
            )

            self.assertEqual(first["status"], "ready")
            self.assertEqual(second["status"], "ready")
            self.assertEqual(statuses["sha256:a"], "superseded")
            self.assertEqual(statuses["sha256:b"], "ready")
            self.assertEqual(current["snapshot_fingerprint"], "sha256:b")
            self.assertEqual(current["content"]["headline"], "第二版")
        finally:
            conn.close()

    def test_same_fingerprint_can_store_distinct_prompt_and_model_versions(self):
        first_id = career_backend._career_ai_insight_id(
            "career_year", "2026", "sha256:same", "prompt.v1", "model-a"
        )
        second_id = career_backend._career_ai_insight_id(
            "career_year", "2026", "sha256:same", "prompt.v2", "model-b"
        )
        self.assertNotEqual(first_id, second_id)

    def test_ready_cache_allows_backend_detail_link_but_rejects_unsafe_content(self):
        conn = sqlite3.connect(":memory:")
        try:
            saved = career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:detail-link",
                snapshot_version="acs.year.v1",
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={
                    "headline": "ok",
                    "key_moments": [
                        {
                            "evidence_id": "race:1",
                            "activity_id": "1",
                            "detail_link": {"activity_id": "1", "source": "activity"},
                        }
                    ],
                },
                content_validated=True,
                conn=conn,
            )
            self.assertEqual(saved["status"], "ready")

            with self.assertRaises(ValueError):
                career_backend.save_ready_career_ai_insight(
                    scope="career_year",
                    scope_key="2026",
                    snapshot_fingerprint="sha256:unsafe",
                    snapshot_version="acs.year.v1",
                    prompt_version="year.prompt.v1",
                    model_id="test-model",
                    content={"headline": "bad", "file_path": "/Users/fanglei/raw.fit"},
                    content_validated=True,
                    conn=conn,
                )
        finally:
            conn.close()

    def test_multiple_years_fingerprints_prompts_and_models_do_not_overlap(self):
        conn = sqlite3.connect(":memory:")
        try:
            base = {
                "scope": "career_year",
                "snapshot_version": "acs.year.v1",
                "content": {"headline": "ok"},
                "content_validated": True,
                "conn": conn,
            }
            career_backend.save_ready_career_ai_insight(
                **base,
                scope_key="2025",
                snapshot_fingerprint="sha256:2025",
                prompt_version="year.prompt.v1",
                model_id="model-a",
            )
            career_backend.save_ready_career_ai_insight(
                **base,
                scope_key="2026",
                snapshot_fingerprint="sha256:2026-a",
                prompt_version="year.prompt.v1",
                model_id="model-a",
            )
            career_backend.save_ready_career_ai_insight(
                **base,
                scope_key="2026",
                snapshot_fingerprint="sha256:2026-b",
                prompt_version="year.prompt.v2",
                model_id="model-a",
            )
            career_backend.save_ready_career_ai_insight(
                **base,
                scope_key="2026",
                snapshot_fingerprint="sha256:2026-c",
                prompt_version="year.prompt.v2",
                model_id="model-b",
            )

            current_2025 = career_backend.get_current_career_ai_insight(
                scope="career_year",
                scope_key="2025",
                conn=conn,
            )
            current_2026 = career_backend.get_current_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                conn=conn,
            )
            cached = career_backend.get_career_ai_insight_by_cache_key(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:2026-a",
                prompt_version="year.prompt.v1",
                model_id="model-a",
                conn=conn,
            )

            self.assertEqual(current_2025["snapshot_fingerprint"], "sha256:2025")
            self.assertEqual(current_2026["snapshot_fingerprint"], "sha256:2026-c")
            self.assertEqual(cached["status"], "superseded")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 4)
        finally:
            conn.close()

    def test_insert_candidate_and_activate_are_separate_repository_steps(self):
        conn = sqlite3.connect(":memory:")
        try:
            inserted = career_backend.insert_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:candidate",
                snapshot_version="acs.year.v1",
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "候选"},
                conn=conn,
            )

            self.assertEqual(inserted["status"], "candidate")
            self.assertIsNone(
                career_backend.get_current_career_ai_insight(
                    scope="career_year",
                    scope_key="2026",
                    conn=conn,
                )
            )

            with self.assertRaises(ValueError):
                career_backend.activate_career_ai_insight(
                    inserted["id"],
                    content_validated=False,
                    conn=conn,
                )
            activated = career_backend.activate_career_ai_insight(
                inserted["id"],
                content_validated=True,
                conn=conn,
            )

            self.assertEqual(activated["status"], "ready")
        finally:
            conn.close()

    def test_ai_cache_does_not_write_canonical_fact_or_photo_tables(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:a",
                snapshot_version="acs.year.v1",
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "年度报告"},
                content_validated=True,
                conn=conn,
            )
            counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "career_race_events",
                    "career_pb_records",
                    "career_achievement_events",
                    "career_memory_items",
                    "career_snapshots",
                )
            }

            self.assertEqual(set(counts.values()), {0})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 1)
        finally:
            conn.close()

    def test_schema_failure_rolls_back_without_losing_existing_snapshots(self):
        conn = sqlite3.connect(":memory:")
        original = career_backend._ensure_career_indexes
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_snapshots
                    (id, snapshot_type, generated_at, content_json, source_version)
                VALUES
                    ('career_snapshot:latest', 'career', '2026-07-14T00:00:00+00:00', '{}', 'test')
                """
            )
            conn.execute("DROP TABLE career_ai_insights")
            conn.commit()

            def fail_indexes(db):
                raise RuntimeError("forced migration failure")

            career_backend._ensure_career_indexes = fail_indexes
            with self.assertRaises(RuntimeError):
                career_backend.ensure_career_schema(conn)

            self.assertNotIn("career_ai_insights", _table_names(conn))
            row = conn.execute(
                "SELECT content_json FROM career_snapshots WHERE id = 'career_snapshot:latest'"
            ).fetchone()
            self.assertEqual(row[0], "{}")
        finally:
            career_backend._ensure_career_indexes = original
            conn.close()


if __name__ == "__main__":
    unittest.main()
