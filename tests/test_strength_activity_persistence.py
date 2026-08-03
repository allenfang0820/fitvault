from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import main
import profile_backend


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "strength_fit_message_snapshots.json"


class TestStrengthActivityPersistence:
    def setup_method(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        profile_backend.DB_PATH = self.root / "user_profile.db"
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

    def teardown_method(self) -> None:
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        self.temp_dir.cleanup()

    def _activity(self, name: str, marker: int | None) -> dict:
        sets = None
        summary = None
        if marker is not None:
            sets = json.dumps(
                [
                    {
                        "set_index": 1,
                        "exercise_key": "weighted_squat",
                        "set_type": "working",
                        "reps": marker,
                        "weight_kg": 60.0,
                        "source": "fit_set_mesgs",
                    }
                ],
                ensure_ascii=False,
            )
            summary = json.dumps(
                {
                    "schema_version": 1,
                    "working_set_count": 1,
                    "total_reps": marker,
                    "total_volume_kg": marker * 60.0,
                    "source": "fit_set_mesgs",
                },
                ensure_ascii=False,
            )
        return {
            "file_name": name,
            "filename": name,
            "title": "Strength Fixture",
            "title_source": "fit",
            "sport_type": "strength_training",
            "sub_sport_type": "strength_training",
            "file_path": str(self.root / name),
            "processing_status": "ready",
            "strength_sets_json": sets,
            "strength_summary_json": summary,
            "muscle_heatmap_json": None,
        }

    def test_schema_migrates_strength_json_columns_for_existing_database(self) -> None:
        conn = sqlite3.connect(profile_backend.DB_PATH)
        conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
        conn.close()

        main.ensure_activity_sync_schema()

        conn = profile_backend._raw_connect()
        try:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()
            }
        finally:
            conn.close()
        assert {
            "strength_sets_json",
            "strength_summary_json",
            "muscle_heatmap_json",
        }.issubset(columns)

    def test_insert_and_reimport_replace_materialized_strength_json(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            activity_id = main._insert_activity_sync_row(
                conn, self._activity("strength.fit", marker=8)
            )
            main._update_activity_sync_row(
                conn, activity_id, self._activity("strength.fit", marker=10)
            )
            conn.commit()
            row = conn.execute(
                "SELECT strength_sets_json, strength_summary_json, muscle_heatmap_json "
                "FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()

        assert json.loads(row["strength_sets_json"])[0]["reps"] == 10
        assert json.loads(row["strength_summary_json"])["total_volume_kg"] == 600.0
        assert row["muscle_heatmap_json"] is None

        conn = profile_backend._conn()
        try:
            main._update_activity_sync_row(
                conn, activity_id, self._activity("strength.fit", marker=None)
            )
            conn.commit()
            cleared = conn.execute(
                "SELECT strength_sets_json, strength_summary_json, muscle_heatmap_json "
                "FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()
        assert dict(cleared) == {
            "strength_sets_json": None,
            "strength_summary_json": None,
            "muscle_heatmap_json": None,
        }

    def test_unstructured_activity_persists_null_instead_of_false_empty_arrays(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            activity_id = main._insert_activity_sync_row(
                conn, self._activity("limited.fit", marker=None)
            )
            conn.commit()
            row = conn.execute(
                "SELECT strength_sets_json, strength_summary_json, muscle_heatmap_json "
                "FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()

        assert dict(row) == {
            "strength_sets_json": None,
            "strength_summary_json": None,
            "muscle_heatmap_json": None,
        }

    def test_sync_parser_materializes_strength_without_detail_time_fit_read(self) -> None:
        raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))[
            "structured_partial_weight"
        ]["raw"]
        fit_path = self.root / "parsed.fit"
        fit_path.write_bytes(b"fixture")
        parsed = {
            "basic_info": {
                "title": "Strength Fixture",
                "title_source": "fit",
                "sport": "training",
                "sub_sport": "strength_training",
                "activity_type": "strength_training",
                "total_distance_km": 0,
                "total_timer_time": 1200,
                "total_calories": 100,
            },
            "track_data": [],
            "lap_data": [],
        }
        resolved = {
            "storage_model": {
                "distance_km": 0,
                "duration_sec": 1200,
                "calories": 100,
            }
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=parsed), \
             mock.patch.object(
                 main.FITCoreEngine,
                 "parse_fit_file_raw",
                 return_value={"raw": raw, "meta": {}},
             ) as raw_parser, \
             mock.patch.object(main.MetricsResolver, "resolve", return_value=resolved), \
             mock.patch.object(main, "_compute_advanced_metrics", return_value={}):
            activity = main._parse_fit_activity_for_sync(fit_path)

        assert raw_parser.call_count == 1
        assert json.loads(activity["strength_summary_json"])["working_set_count"] == 3
        assert json.loads(activity["strength_sets_json"])[0]["exercise_key"] == "pull_up"
        heatmap = json.loads(activity["muscle_heatmap_json"])
        assert heatmap["coverage"]["mapped_working_sets"] == 3
        assert heatmap["coverage"]["unmapped_working_sets"] == 0
        assert activity["strength_materialization_version"] == main.STRENGTH_MATERIALIZATION_VERSION
        assert activity["strength_materialization_status"] == "materialized"
        assert activity["strength_materialization_error"] is None

    def test_sync_parser_marks_true_empty_strength_as_unstructured(self) -> None:
        fit_path = self.root / "unstructured.fit"
        fit_path.write_bytes(b"fixture")
        parsed = {
            "basic_info": {
                "sport": "training",
                "sub_sport": "strength_training",
                "activity_type": "strength_training",
                "total_timer_time": 600,
            },
            "track_data": [],
            "lap_data": [],
        }
        resolved = {"storage_model": {"distance_km": 0, "duration_sec": 600}}
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=parsed), \
             mock.patch.object(
                 main.FITCoreEngine,
                 "parse_fit_file_raw",
                 return_value={"raw": {}, "meta": {}},
             ), \
             mock.patch.object(main.MetricsResolver, "resolve", return_value=resolved), \
             mock.patch.object(main, "_compute_advanced_metrics", return_value={}):
            activity = main._parse_fit_activity_for_sync(fit_path)

        assert activity["strength_sets_json"] is None
        assert activity["strength_summary_json"] is None
        assert activity["muscle_heatmap_json"] is None
        assert activity["strength_materialization_version"] == main.STRENGTH_MATERIALIZATION_VERSION
        assert activity["strength_materialization_status"] == "unstructured"
        assert activity["strength_materialization_error"] is None

    def test_activity_detail_read_does_not_reparse_fit(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            activity_id = main._insert_activity_sync_row(
                conn, self._activity("detail.fit", marker=8)
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main.FITCoreEngine,
            "parse_fit_file_raw",
            side_effect=AssertionError("detail read must not parse FIT"),
        ):
            response = main.Api().get_activity_detail(activity_id)

        assert response["ok"] is True

    def test_detail_apis_expose_sanitized_materialization_state_only(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            activity_id = main._insert_activity_sync_row(
                conn,
                self._activity("failed-detail.fit", marker=None),
            )
            conn.execute(
                """
                UPDATE activities
                SET strength_materialization_version = ?,
                    strength_materialization_status = 'failed',
                    strength_materialization_error = '/private/user/failed-detail.fit decoder traceback'
                WHERE id = ?
                """,
                (main.STRENGTH_MATERIALIZATION_VERSION, activity_id),
            )
            conn.commit()
        finally:
            conn.close()

        api = main.Api()
        responses = (
            api.get_activity_detail_summary(activity_id),
            api.get_activity_detail(activity_id),
        )
        for response in responses:
            assert response["ok"] is True
            state = response["data"]["record"]["detail"]["strength_materialization"]
            assert state == {
                "version": 1,
                "status": "failed",
                "can_retry": True,
                "message_code": "strength_materialization_failed",
            }
            serialized = json.dumps(response, ensure_ascii=False)
            assert "failed-detail.fit decoder" not in serialized
            assert "strength_materialization_error" not in serialized
