import json
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

import career_backend

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_career_year_snapshot_period_comparison import _create_tables, _insert_activity


class TestCareerYearInsightService(unittest.TestCase):
    def test_concurrent_current_schema_reads_do_not_take_write_locks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "career-year-read.sqlite"
            conn = sqlite3.connect(str(db_path))
            try:
                _create_tables(conn)
                _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00")
                conn.commit()
            finally:
                conn.close()

            def read_year() -> str:
                read_conn = sqlite3.connect(str(db_path), timeout=1)
                try:
                    read_conn.execute("PRAGMA query_only = ON")
                    return career_backend.get_career_year_insight(2026, conn=read_conn)["report_state"]
                finally:
                    read_conn.close()

            with ThreadPoolExecutor(max_workers=4) as executor:
                states = list(executor.map(lambda _: read_year(), range(8)))

            self.assertEqual(states, ["not_generated"] * 8)

    def test_one_read_reuses_activity_rows_for_years_badges_snapshot_and_comparison(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            _insert_activity(conn, id=2, start_time="2025-05-01T07:00:00+08:00", dist_km=8.0)
            _insert_activity(conn, id=3, start_time="2024-05-01T07:00:00+08:00", dist_km=6.0)
            for year in (2026, 2025):
                snapshot = career_backend.build_career_year_snapshot(year, conn=conn)
                career_backend.save_ready_career_ai_insight(
                    scope="career_year",
                    scope_key=str(year),
                    snapshot_fingerprint=snapshot["source_fingerprint"],
                    snapshot_version=snapshot["snapshot_version"],
                    prompt_version="acs.year.summary.zh-CN.v4",
                    model_id="test-model",
                    content={"schema_version": "acs.year.report.v3", "headline": str(year)},
                    content_validated=True,
                    conn=conn,
                )
            _insert_activity(conn, id=4, start_time="2025-06-01T07:00:00+08:00", dist_km=2.0)

            original = career_backend._overview_activity_rows
            with mock.patch.object(
                career_backend,
                "_overview_activity_rows",
                wraps=original,
            ) as activity_reader:
                result = career_backend.get_career_year_insight(2026, conn=conn)

            self.assertEqual(activity_reader.call_count, 1)
            self.assertEqual(result["available_years"], [2026, 2025, 2024])
            self.assertEqual(result["year_update_badges"]["years"], [2025])
            self.assertEqual(result["facts"]["summary"]["activity_count"], 1)
            self.assertEqual(result["facts"]["comparison"]["status"], "available")
            self.assertEqual(result["facts"]["comparison"]["activity_count_delta"], 0)
        finally:
            conn.close()

    def test_generated_at_is_localized_for_display_while_storage_stays_auditable(self):
        localized = career_backend._career_year_display_time(
            "2026-07-14T03:04:05+00:00",
            local_tz=timezone(timedelta(hours=8)),
        )
        self.assertEqual(localized, "2026-07-14T11:04:05+08:00")
        self.assertEqual(career_backend._career_year_display_time("invalid"), "invalid")

    def test_no_data_returns_stable_empty_view_without_fabricating_current_year(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)

            result = career_backend.get_career_year_insight(conn=conn)

            self.assertEqual(result["available_years"], [])
            self.assertIsNone(result["year"])
            self.assertEqual(result["report_state"], "no_data")
            self.assertFalse(result["can_generate"])
            self.assertIsNone(result["report"])
            self.assertEqual(result["local_fallback"]["mode"], "local_fallback")
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_default_year_uses_latest_valid_activity_year_and_does_not_write_cache(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2025-04-01T07:00:00+08:00")
            _insert_activity(conn, id=2, start_time="2026-05-01T07:00:00+08:00")

            result = career_backend.get_career_year_insight(conn=conn)
            cache_count = conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0]

            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual(result["year"], 2026)
            self.assertEqual(result["report_state"], "not_generated")
            self.assertTrue(result["can_generate"])
            self.assertIsNone(result["report"])
            self.assertEqual(result["local_fallback"]["mode"], "local_fallback")
            self.assertEqual(cache_count, 0)
        finally:
            conn.close()

    def test_ready_report_returns_ai_report_and_safe_facts_without_raw_snapshot(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "AI 年度总结"},
                content_validated=True,
                conn=conn,
            )

            result = career_backend.get_career_year_insight(2026, conn=conn)
            serialized_facts = json.dumps(result["facts"], ensure_ascii=False)

            self.assertEqual(result["report_state"], "ready")
            self.assertFalse(result["can_generate"])
            self.assertFalse(result["can_refresh"])
            self.assertEqual(result["report"]["mode"], "ai")
            self.assertEqual(result["report"]["content"]["headline"], "AI 年度总结")
            self.assertTrue(result["format_upgrade_available"])
            self.assertEqual(result["facts"]["summary"]["activity_count"], 1)
            self.assertNotIn("source_fingerprint", serialized_facts)
            self.assertNotIn("evidence_catalog", serialized_facts)
            self.assertNotIn("snapshot_version", serialized_facts)
        finally:
            conn.close()

    def test_v2_report_offers_format_upgrade_but_v3_does_not(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00")
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="acs.year.summary.zh-CN.v2",
                model_id="test-model",
                content={"schema_version": "acs.year.report.v2", "title": "新报告"},
                content_validated=True,
                conn=conn,
            )
            result = career_backend.get_career_year_insight(2026, conn=conn)
            self.assertTrue(result["format_upgrade_available"])
            self.assertEqual(result["report"]["schema_version"], "acs.year.report.v2")

            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="acs.year.summary.zh-CN.v4",
                model_id="test-model",
                content={"schema_version": "acs.year.report.v3", "title": "分享版报告"},
                content_validated=True,
                conn=conn,
            )
            result = career_backend.get_career_year_insight(2026, conn=conn)
            self.assertFalse(result["format_upgrade_available"])
            self.assertEqual(result["report"]["schema_version"], "acs.year.report.v3")
        finally:
            conn.close()

    def test_stale_report_preserves_old_ai_report_and_allows_refresh(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "旧报告"},
                content_validated=True,
                conn=conn,
            )
            _insert_activity(conn, id=2, start_time="2026-06-01T07:00:00+08:00", dist_km=5.0)

            result = career_backend.get_career_year_insight(2026, conn=conn)

            self.assertEqual(result["report_state"], "stale")
            self.assertTrue(result["can_refresh"])
            self.assertTrue(result["has_source_changes"])
            self.assertTrue(result["year_update_badges"]["year_map"]["2026"])
            self.assertEqual(result["report"]["content"]["headline"], "旧报告")
            self.assertEqual(result["facts"]["summary"]["activity_count"], 2)
        finally:
            conn.close()

    def test_format_upgrade_only_does_not_set_year_update_badge(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="acs.year.summary.zh-CN.v2",
                model_id="test-model",
                content={"schema_version": "acs.year.report.v2", "headline": "旧格式报告"},
                content_validated=True,
                conn=conn,
            )

            result = career_backend.get_career_year_insight(2026, conn=conn)

            self.assertEqual(result["report_state"], "ready")
            self.assertFalse(result["has_source_changes"])
            self.assertTrue(result["format_upgrade_available"])
            self.assertFalse(result["year_update_badges"]["year_map"].get("2026", False))
        finally:
            conn.close()

    def test_ai_unavailable_with_history_keeps_report_visible(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-14")
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="year.prompt.v1",
                model_id="test-model",
                content={"headline": "历史报告"},
                content_validated=True,
                conn=conn,
            )

            result = career_backend.get_career_year_insight(2026, ai_available=False, conn=conn)

            self.assertEqual(result["report_state"], "ai_unavailable")
            self.assertFalse(result["can_generate"])
            self.assertFalse(result["can_refresh"])
            self.assertEqual(result["report"]["content"]["headline"], "历史报告")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
