import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import career_backend
import main
import profile_backend

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_career_year_snapshot_period_comparison import _create_tables, _insert_activity


PROMPT_VERSION = "acs.year.summary.zh-CN.v4"
MODEL_ID = "fake-year-model"


def _reset_singleflight_registry() -> None:
    with career_backend.CAREER_YEAR_GENERATION_FLIGHT_LOCK:
        career_backend.CAREER_YEAR_GENERATION_FLIGHTS.clear()


def _draft(year: int, headline: str = "稳定推进的一年") -> dict:
    return {
        "schema_version": "acs.year.report.v3",
        "year": year,
        "title": headline,
        "subtitle": "稳定积累，也留下了清楚的痕迹",
        "opening": "这些记录来自一个个普通日子里的出门和回来。",
        "body_sections": [
            {"type": "annual_story", "heading": "这一年的主线", "paragraphs": ["截至当前数据周期，运动保持稳定。"], "evidence_ids": []},
            {"type": "rhythm", "heading": "这一年的节奏", "paragraphs": ["这一年的节奏有据可查。"], "evidence_ids": []},
        ],
        "closing": "这一年值得记住的，是持续留下了真实痕迹。",
        "letter_to_next_year": "写给下一年的你：继续把运动留在生活里。",
        "share_caption": "我没有突然变强，但我一直在回来。",
        "caveats": ["部分年度时仅作阶段总结"],
    }


def _fake_generator(calls: list, *, headline: str = "AI 年度总结"):
    def generate(snapshot: dict) -> dict:
        calls.append(snapshot["year"])
        return {
            "content": _draft(snapshot["year"], headline=headline),
            "prompt_version": PROMPT_VERSION,
            "model_id": MODEL_ID,
            "status": "success",
        }

    return generate


class TestCareerYearGenerateApi(unittest.TestCase):
    def test_not_generated_calls_fake_llm_once_and_read_api_sees_ready_report(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            calls: list[int] = []

            generated = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            read = career_backend.get_career_year_insight(2026, conn=conn)

            self.assertEqual(calls, [2026])
            self.assertEqual(generated["generation"]["status"], "generated")
            self.assertEqual(generated["report_state"], "ready")
            self.assertEqual(generated["report"]["content"]["headline"], "AI 年度总结")
            self.assertEqual(read["report_state"], "ready")
            self.assertEqual(read["report"]["content"]["headline"], "AI 年度总结")
        finally:
            conn.close()

    def test_ready_returns_cache_without_calling_llm(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"schema_version": "acs.year.report.v3", "headline": "已有最新报告"},
                content_validated=True,
                conn=conn,
            )

            def explode(_snapshot):
                raise AssertionError("ready 状态不应调用 LLM")

            result = career_backend.generate_career_year_insight(
                2026,
                generator=explode,
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )

            self.assertEqual(result["generation"]["status"], "already_ready")
            self.assertEqual(result["report_state"], "ready")
            self.assertEqual(result["report"]["content"]["headline"], "已有最新报告")
        finally:
            conn.close()

    def test_repeated_same_request_is_idempotent_and_does_not_call_llm_twice(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            calls: list[int] = []

            first = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls, headline="第一次报告"),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            second = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls, headline="不应出现"),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )

            self.assertEqual(calls, [2026])
            self.assertEqual(first["report_state"], "ready")
            self.assertEqual(second["report_state"], "ready")
            self.assertEqual(second["generation"]["status"], "already_ready")
            self.assertEqual(second["report"]["content"]["headline"], "第一次报告")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 1)
        finally:
            conn.close()

    def test_ready_state_ignores_internal_prompt_or_model_change_for_visible_refresh(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="old-prompt",
                model_id="old-model",
                content={"schema_version": "acs.year.report.v3", "headline": "当前可见报告"},
                content_validated=True,
                conn=conn,
            )

            def explode(_snapshot):
                raise AssertionError("无事实变化时 prompt/model 改变不应暴露重新生成入口")

            read = career_backend.get_career_year_insight(2026, conn=conn)
            generated = career_backend.generate_career_year_insight(
                2026,
                generator=explode,
                prompt_version="new-prompt",
                model_id="new-model",
                conn=conn,
            )

            self.assertEqual(read["report_state"], "ready")
            self.assertFalse(read["can_refresh"])
            self.assertEqual(generated["generation"]["status"], "already_ready")
            self.assertEqual(generated["report"]["content"]["headline"], "当前可见报告")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 1)
        finally:
            conn.close()

    def test_legacy_v1_ready_report_can_upgrade_once_and_failure_preserves_legacy(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version="acs.year.summary.zh-CN.v1",
                model_id="legacy-model",
                content={"schema_version": "acs.year.report.v1", "headline": "旧版年度总结"},
                content_validated=True,
                conn=conn,
            )
            read = career_backend.get_career_year_insight(2026, conn=conn)
            self.assertTrue(read["format_upgrade_available"])
            self.assertEqual(read["report"]["content"]["headline"], "旧版年度总结")

            failed = career_backend.generate_career_year_insight(
                2026,
                generator=lambda _snapshot: (_ for _ in ()).throw(RuntimeError("offline")),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            self.assertEqual(failed["generation"]["status"], "network_failed")
            self.assertEqual(failed["report"]["content"]["headline"], "旧版年度总结")

            calls: list[int] = []
            upgraded = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls, headline="新版年度故事"),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            self.assertEqual(calls, [2026])
            self.assertEqual(upgraded["generation"]["status"], "generated")
            self.assertEqual(upgraded["report"]["schema_version"], "acs.year.report.v3")
            self.assertFalse(upgraded["format_upgrade_available"])
            self.assertEqual(upgraded["report"]["content"]["headline"], "新版年度故事")
        finally:
            conn.close()

    def test_exact_superseded_cache_hit_reactivates_without_llm_but_candidate_is_not_trusted(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"schema_version": "acs.year.report.v3", "headline": "可复用报告"},
                content_validated=True,
                conn=conn,
            )
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint="sha256:other",
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"schema_version": "acs.year.report.v3", "headline": "当前但不同 fingerprint"},
                content_validated=True,
                conn=conn,
            )

            def explode(_snapshot):
                raise AssertionError("已验证的精确缓存应直接复用")

            reused = career_backend.generate_career_year_insight(
                2026,
                generator=explode,
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            self.assertEqual(reused["generation"]["status"], "cache_hit")
            self.assertEqual(reused["report"]["content"]["headline"], "可复用报告")

            # candidate 行没有经过 ready 校验，不得作为缓存命中直接激活。
            conn.execute("DELETE FROM career_ai_insights")
            career_backend.insert_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"schema_version": "acs.year.report.v3", "headline": "未验证 candidate"},
                conn=conn,
            )
            calls: list[int] = []
            generated = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls, headline="重新校验后的报告"),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )

            self.assertEqual(calls, [2026])
            self.assertEqual(generated["generation"]["status"], "generated")
            self.assertEqual(generated["report"]["content"]["headline"], "重新校验后的报告")
        finally:
            conn.close()

    def test_concurrent_same_key_uses_singleflight_and_calls_llm_once(self):
        _reset_singleflight_registry()
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year singleflight ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_tables(conn)
                    _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
                    conn.commit()
                finally:
                    conn.close()

                calls: list[int] = []
                calls_lock = threading.Lock()
                start = threading.Barrier(2)
                results: list[dict] = []
                errors: list[BaseException] = []

                def generator(snapshot: dict) -> dict:
                    with calls_lock:
                        calls.append(snapshot["year"])
                    threading.Event().wait(0.1)
                    return {
                        "content": _draft(snapshot["year"], headline="单飞报告"),
                        "prompt_version": PROMPT_VERSION,
                        "model_id": MODEL_ID,
                    }

                def worker() -> None:
                    try:
                        start.wait(timeout=3)
                        results.append(career_backend.generate_career_year_insight(
                            2026,
                            generator=generator,
                            prompt_version=PROMPT_VERSION,
                            model_id=MODEL_ID,
                        ))
                    except BaseException as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=worker) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)

                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                self.assertEqual(calls, [2026])
                self.assertEqual(len(results), 2)
                self.assertEqual({item["report_state"] for item in results}, {"ready"})
                self.assertEqual({item["report"]["content"]["headline"] for item in results}, {"单飞报告"})
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 1)
                finally:
                    conn.close()
            finally:
                profile_backend.DB_PATH = original_db_path
                _reset_singleflight_registry()

    def test_concurrent_different_years_do_not_share_singleflight_lock(self):
        _reset_singleflight_registry()
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year parallel ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_tables(conn)
                    _insert_activity(conn, id=1, start_time="2025-05-01T07:00:00+08:00", dist_km=8.0)
                    _insert_activity(conn, id=2, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
                    conn.commit()
                finally:
                    conn.close()

                in_llm = threading.Barrier(2)
                calls: list[int] = []
                calls_lock = threading.Lock()
                results: list[dict] = []
                errors: list[BaseException] = []

                def generator(snapshot: dict) -> dict:
                    with calls_lock:
                        calls.append(snapshot["year"])
                    in_llm.wait(timeout=3)
                    return {
                        "content": _draft(snapshot["year"], headline=f"{snapshot['year']} 报告"),
                        "prompt_version": PROMPT_VERSION,
                        "model_id": MODEL_ID,
                    }

                def worker(year: int) -> None:
                    try:
                        results.append(career_backend.generate_career_year_insight(
                            year,
                            generator=generator,
                            prompt_version=PROMPT_VERSION,
                            model_id=MODEL_ID,
                        ))
                    except BaseException as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=worker, args=(year,)) for year in (2025, 2026)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)

                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                self.assertEqual(sorted(calls), [2025, 2026])
                self.assertEqual({item["year"] for item in results}, {2025, 2026})
                self.assertEqual({item["report_state"] for item in results}, {"ready"})
            finally:
                profile_backend.DB_PATH = original_db_path
                _reset_singleflight_registry()

    def test_source_change_during_generation_discards_old_fingerprint_result(self):
        _reset_singleflight_registry()
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 year source change ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_tables(conn)
                    _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
                    conn.commit()
                finally:
                    conn.close()

                def generator(snapshot: dict) -> dict:
                    writer = sqlite3.connect(str(profile_backend.DB_PATH))
                    try:
                        _insert_activity(writer, id=2, start_time="2026-06-01T07:00:00+08:00", dist_km=5.0)
                        writer.commit()
                    finally:
                        writer.close()
                    return {
                        "content": _draft(snapshot["year"], headline="过期报告"),
                        "prompt_version": PROMPT_VERSION,
                        "model_id": MODEL_ID,
                    }

                result = career_backend.generate_career_year_insight(
                    2026,
                    generator=generator,
                    prompt_version=PROMPT_VERSION,
                    model_id=MODEL_ID,
                )

                self.assertEqual(result["generation"]["status"], "source_changed")
                self.assertNotEqual(result["report_state"], "ready")
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 0)
                    read = career_backend.get_career_year_insight(2026, conn=conn)
                    self.assertEqual(read["facts"]["summary"]["activity_count"], 2)
                finally:
                    conn.close()
            finally:
                profile_backend.DB_PATH = original_db_path
                _reset_singleflight_registry()

    def test_persistence_failure_keeps_old_ready_report_current(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"headline": "旧报告"},
                content_validated=True,
                conn=conn,
            )
            _insert_activity(conn, id=2, start_time="2026-06-01T07:00:00+08:00", dist_km=5.0)

            with mock.patch.object(career_backend, "save_ready_career_ai_insight", side_effect=RuntimeError("write failed")):
                result = career_backend.generate_career_year_insight(
                    2026,
                    generator=_fake_generator([], headline="写入失败的新报告"),
                    prompt_version=PROMPT_VERSION,
                    model_id=MODEL_ID,
                    conn=conn,
                )

            current = career_backend.get_current_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                conn=conn,
            )
            self.assertEqual(result["generation"]["status"], "persistence_failed")
            self.assertEqual(result["report_state"], "failed")
            self.assertEqual(current["content"]["headline"], "旧报告")
            self.assertEqual(current["status"], "ready")
        finally:
            conn.close()

    def test_failure_matrix_preserves_facts_and_does_not_pollute_canonical_tables(self):
        cases = [
            ("network_failed", lambda _snapshot: (_ for _ in ()).throw(RuntimeError("token=SECRET raw response"))),
            ("timeout", lambda _snapshot: (_ for _ in ()).throw(TimeoutError("timeout with api_key=SECRET"))),
            ("format_failed", lambda _snapshot: (_ for _ in ()).throw(ValueError("LLM JSON 解析失败 raw=SECRET"))),
            ("schema_failed", lambda snapshot: {"content": {**_draft(snapshot["year"]), "schema_version": "bad"}, "prompt_version": PROMPT_VERSION, "model_id": MODEL_ID}),
            ("schema_failed", lambda snapshot: {"content": {**_draft(snapshot["year"] + 1)}, "prompt_version": PROMPT_VERSION, "model_id": MODEL_ID}),
            (
                "evidence_failed",
                lambda snapshot: {
                    "content": {
                        **_draft(snapshot["year"]),
                        "body_sections": [
                            {
                                **_draft(snapshot["year"])["body_sections"][0],
                                "evidence_ids": ["unknown:1", "unknown:2"],
                            },
                            _draft(snapshot["year"])["body_sections"][1],
                        ],
                    },
                    "prompt_version": PROMPT_VERSION,
                    "model_id": MODEL_ID,
                },
            ),
        ]
        for expected_status, generator in cases:
            with self.subTest(expected_status=expected_status):
                conn = sqlite3.connect(":memory:")
                try:
                    _create_tables(conn)
                    _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
                    before = {
                        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in ("activities", "career_race_events", "career_pb_records", "career_achievement_events")
                    }

                    result = career_backend.generate_career_year_insight(
                        2026,
                        generator=generator,
                        prompt_version=PROMPT_VERSION,
                        model_id=MODEL_ID,
                        conn=conn,
                    )
                    after = {
                        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in ("activities", "career_race_events", "career_pb_records", "career_achievement_events")
                    }

                    self.assertEqual(result["generation"]["status"], expected_status)
                    self.assertEqual(result["report_state"], "failed")
                    self.assertEqual(result["facts"]["summary"]["activity_count"], 1)
                    self.assertIsNone(result["report"])
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_ai_insights").fetchone()[0], 0)
                    self.assertEqual(after, before)
                    serialized = json.dumps(result, ensure_ascii=False)
                    self.assertNotIn("SECRET", serialized)
                    self.assertNotIn("raw response", serialized)
                    self.assertNotIn("LLM JSON", serialized)
                finally:
                    conn.close()

    def test_oversized_output_is_sanitized_without_leaking_raw_text(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)

            def generator(snapshot: dict) -> dict:
                return {
                    "content": {
                        **_draft(snapshot["year"]),
                        "title": "<script>SECRET</script>" + ("很长" * 100),
                        "opening": "```json\n" + ("开篇" * 200) + "\n```",
                    },
                    "prompt_version": PROMPT_VERSION,
                    "model_id": MODEL_ID,
                }

            result = career_backend.generate_career_year_insight(
                2026,
                generator=generator,
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )

            self.assertEqual(result["generation"]["status"], "generated")
            self.assertLessEqual(len(result["report"]["content"]["headline"]), 60)
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("<script", serialized)
            self.assertNotIn("```", serialized)
        finally:
            conn.close()

    def test_failure_logs_use_safe_summary_without_secret_or_raw_response(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)

            def generator(_snapshot: dict) -> dict:
                raise RuntimeError("token=SECRET raw response prompt snapshot http://secret")

            with self.assertLogs("career_backend", level="WARNING") as logs:
                result = career_backend.generate_career_year_insight(
                    2026,
                    generator=generator,
                    prompt_version=PROMPT_VERSION,
                    model_id=MODEL_ID,
                    conn=conn,
                )

            self.assertEqual(result["generation"]["status"], "network_failed")
            log_text = "\n".join(logs.output)
            self.assertIn("year=2026", log_text)
            self.assertIn("status=network_failed", log_text)
            self.assertNotIn("SECRET", log_text)
            self.assertNotIn("raw response", log_text)
            self.assertNotIn("prompt snapshot", log_text)
            self.assertNotIn("http://secret", log_text)
        finally:
            conn.close()

    def test_stale_report_allows_refresh_and_calls_llm_once(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            snapshot = career_backend.build_career_year_snapshot(2026, conn=conn)
            career_backend.save_ready_career_ai_insight(
                scope="career_year",
                scope_key="2026",
                snapshot_fingerprint=snapshot["source_fingerprint"],
                snapshot_version=snapshot["snapshot_version"],
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                content={"headline": "旧报告"},
                content_validated=True,
                conn=conn,
            )
            _insert_activity(conn, id=2, start_time="2026-06-01T07:00:00+08:00", dist_km=5.0)
            calls: list[int] = []

            result = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls, headline="刷新后的报告"),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )

            self.assertEqual(calls, [2026])
            self.assertEqual(result["generation"]["status"], "generated")
            self.assertEqual(result["report_state"], "ready")
            self.assertEqual(result["report"]["content"]["headline"], "刷新后的报告")
        finally:
            conn.close()

    def test_no_data_and_missing_ai_config_do_not_call_llm(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            calls: list[int] = []

            no_data = career_backend.generate_career_year_insight(
                2026,
                generator=_fake_generator(calls),
                prompt_version=PROMPT_VERSION,
                model_id=MODEL_ID,
                conn=conn,
            )
            self.assertEqual(no_data["report_state"], "no_data")
            self.assertEqual(no_data["generation"]["status"], "not_allowed")
            self.assertEqual(calls, [])

            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)

            def explode(_snapshot):
                raise AssertionError("AI 配置缺失时不应调用 LLM")

            with mock.patch.object(
                career_backend,
                "_career_year_default_llm_context",
                return_value=(explode, {}, PROMPT_VERSION, "", False),
            ):
                unavailable = career_backend.generate_career_year_insight(2026, conn=conn)

            self.assertEqual(unavailable["report_state"], "ai_unavailable")
            self.assertEqual(unavailable["generation"]["status"], "ai_unavailable")
            self.assertIsNotNone(unavailable["facts"])
        finally:
            conn.close()

    def test_openclaw_cli_default_model_is_allowed_when_global_config_is_ready(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_tables(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T07:00:00+08:00", dist_km=10.0)
            calls: list[dict] = []

            def generator(snapshot: dict, *, config: dict) -> dict:
                calls.append({"year": snapshot["year"], "config": dict(config)})
                return {
                    "content": _draft(snapshot["year"], headline="OpenClaw 默认模型报告"),
                    "prompt_version": PROMPT_VERSION,
                    "model_id": "openclaw-default",
                }

            with mock.patch.object(
                career_backend,
                "_career_year_default_llm_context",
                return_value=(
                    generator,
                    {"transport": "cli", "cli_type": "openclaw", "cli_path": "/bin/openclaw", "cli_model": "", "model": ""},
                    PROMPT_VERSION,
                    "openclaw-default",
                    True,
                ),
            ):
                result = career_backend.generate_career_year_insight(2026, conn=conn)

            self.assertEqual(calls[0]["config"]["cli_type"], "openclaw")
            self.assertEqual(result["generation"]["status"], "generated")
            self.assertEqual(result["report"]["model_id"], "openclaw-default")
            self.assertEqual(result["report"]["content"]["headline"], "OpenClaw 默认模型报告")
        finally:
            conn.close()

    def test_pywebview_generate_rejects_illegal_payload_without_backend_call(self):
        api = main.Api()
        with mock.patch.object(career_backend, "generate_career_year_insight") as mocked:
            responses = (
                api.generate_career_year_insight({}),
                api.generate_career_year_insight({"year": 2026, "prompt": "bad"}),
                api.generate_career_year_insight({"year": True}),
                api.generate_career_year_insight({"year": "bad"}),
                api.generate_career_year_insight({"year": 1800}),
            )

        self.assertEqual(mocked.call_count, 0)
        for response in responses:
            self.assertFalse(response["ok"])
            self.assertEqual(response["code"], main.API_CODE_VALIDATION)
            self.assertIsInstance(response.get("traceId"), str)

    def test_pywebview_generate_success_envelope_and_js_contract(self):
        api = main.Api()
        backend_result = {
            "year": 2026,
            "report_state": "ready",
            "generation": {"status": "generated"},
            "facts": {},
            "report": {"content": {"headline": "ok"}},
        }
        with mock.patch.object(career_backend, "generate_career_year_insight", return_value=backend_result) as mocked:
            response = api.generate_career_year_insight({"year": "2026"})

        self.assertTrue(response["ok"])
        self.assertEqual(response["code"], main.API_CODE_OK)
        self.assertEqual(response["data"]["generation"]["status"], "generated")
        mocked.assert_called_once_with(2026)

        contract = json.loads(Path("docs/js_api_contract.json").read_text(encoding="utf-8"))
        methods = {entry["name"]: entry for entry in contract.get("methods", [])}
        self.assertIn("generate_career_year_insight", methods)
        method = methods["generate_career_year_insight"]
        self.assertFalse(method["readonly"])
        self.assertIn("仅支持 year", method["description"])
        self.assertIn("v3 ready、no_data 和非法 payload 不调用 LLM", method["description"])
        self.assertIn("旧格式升级失败继续展示旧报告", method["description"])


if __name__ == "__main__":
    unittest.main()
