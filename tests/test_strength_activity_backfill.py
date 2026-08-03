from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import main
import profile_backend
import pytest


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "strength_fit_message_snapshots.json"


class TestStrengthMaterializationDryRun:
    def setup_method(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.tracks_dir = self.root / "tracks"
        self.tracks_dir.mkdir()
        self.outside_dir = self.root / "outside"
        self.outside_dir.mkdir()
        self.original_db_path = profile_backend.DB_PATH
        self.original_tracks_dir = main.TRACKS_DIR
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        self.original_worker_status = dict(main._STRENGTH_MATERIALIZATION_STATUS)
        self.original_worker_thread = main._STRENGTH_MATERIALIZATION_THREAD
        self.original_app_shutdown = main._APP_SHUTTING_DOWN.is_set()
        profile_backend.DB_PATH = self.root / "user_profile.db"
        main.TRACKS_DIR = str(self.tracks_dir)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main._APP_SHUTTING_DOWN.clear()
        main._STRENGTH_MATERIALIZATION_STATUS.update(
            {
                "running": False,
                "retry_only": False,
                "version": main.STRENGTH_MATERIALIZATION_VERSION,
                "total": 0,
                "processed": 0,
                "updated": 0,
                "materialized": 0,
                "unstructured": 0,
                "source_missing": 0,
                "failed": 0,
                "skipped": 0,
                "limited": False,
                "started_at": 0.0,
                "finished_at": 0.0,
                "error_code": "",
            }
        )
        main._STRENGTH_MATERIALIZATION_THREAD = None

    def teardown_method(self) -> None:
        profile_backend.DB_PATH = self.original_db_path
        main.TRACKS_DIR = self.original_tracks_dir
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        if self.original_app_shutdown:
            main._APP_SHUTTING_DOWN.set()
        else:
            main._APP_SHUTTING_DOWN.clear()
        main._STRENGTH_MATERIALIZATION_STATUS.clear()
        main._STRENGTH_MATERIALIZATION_STATUS.update(self.original_worker_status)
        main._STRENGTH_MATERIALIZATION_THREAD = self.original_worker_thread
        self.temp_dir.cleanup()

    def _fit(self, name: str, *, outside: bool = False) -> Path:
        parent = self.outside_dir if outside else self.tracks_dir
        path = parent / name
        path.write_bytes(b"sanitized-fit-fixture")
        return path

    def _insert(
        self,
        conn: sqlite3.Connection,
        *,
        name: str,
        file_path: str,
        sport_type: str = "training",
        sub_sport_type: str = "strength_training",
        version: int = 0,
        status: str | None = None,
        complete_json: bool = False,
        deleted: bool = False,
    ) -> None:
        sets_json = summary_json = heatmap_json = None
        if complete_json:
            sets_json = json.dumps([{"set_type": "working", "reps": 8}])
            summary_json = json.dumps({"schema_version": 1, "working_set_count": 1})
            heatmap_json = json.dumps({"schema_version": 1, "regions": []})
        conn.execute(
            """
            INSERT INTO activities (
                file_name, filename, sport_type, sub_sport_type, file_path, deleted_at,
                strength_sets_json, strength_summary_json, muscle_heatmap_json,
                strength_materialization_version, strength_materialization_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                name,
                sport_type,
                sub_sport_type,
                file_path,
                "2026-07-29T00:00:00" if deleted else None,
                sets_json,
                summary_json,
                heatmap_json,
                version,
                status,
            ),
        )

    def _seed_matrix(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._raw_connect()
        try:
            self._insert(
                conn,
                name="legacy.fit",
                file_path=str(self._fit("legacy.fit")),
                complete_json=True,
            )
            self._insert(
                conn,
                name="current.fit",
                file_path=str(self._fit("current.fit")),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="materialized",
                complete_json=True,
            )
            self._insert(
                conn,
                name="unstructured.fit",
                file_path=str(self._fit("unstructured.fit")),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="unstructured",
            )
            self._insert(
                conn,
                name="pending.fit",
                file_path=str(self._fit("pending.fit")),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="pending",
            )
            self._insert(
                conn,
                name="stale.fit",
                file_path=str(self._fit("stale.fit")),
                version=0,
                status="materialized",
                complete_json=True,
            )
            self._insert(
                conn,
                name="missing.fit",
                file_path=str(self.tracks_dir / "missing.fit"),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="pending",
            )
            outside_path = self._fit("outside.fit", outside=True)
            self._insert(
                conn,
                name="outside.fit",
                file_path=str(outside_path),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="pending",
            )
            self._insert(
                conn,
                name="failed.fit",
                file_path=str(self._fit("failed.fit")),
                version=main.STRENGTH_MATERIALIZATION_VERSION,
                status="failed",
            )
            self._insert(
                conn,
                name="deleted.fit",
                file_path=str(self._fit("deleted.fit")),
                status="pending",
                deleted=True,
            )
            self._insert(
                conn,
                name="running.fit",
                file_path=str(self._fit("running.fit")),
                sport_type="running",
                sub_sport_type="generic",
                status="pending",
            )
            conn.commit()
        finally:
            conn.close()

    def test_schema_migrates_versioned_materialization_columns_idempotently(self) -> None:
        conn = sqlite3.connect(profile_backend.DB_PATH)
        conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
        conn.close()

        main.ensure_activity_sync_schema()
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.ensure_activity_sync_schema()

        conn = profile_backend._raw_connect()
        try:
            columns = {
                row[1]: row[4]
                for row in conn.execute("PRAGMA table_info(activities)").fetchall()
            }
        finally:
            conn.close()
        assert columns["strength_materialization_version"] == "0"
        assert "strength_materialization_status" in columns
        assert "strength_materialization_error" in columns

    def test_dry_run_reads_pre_migration_strength_schema_without_writing(self) -> None:
        fit_path = self._fit("legacy-schema.fit")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                sub_sport_type TEXT,
                file_path TEXT,
                deleted_at TEXT,
                strength_sets_json TEXT,
                strength_summary_json TEXT,
                muscle_heatmap_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, file_path, deleted_at,
                strength_sets_json, strength_summary_json, muscle_heatmap_json
            ) VALUES (1, 'training', 'strength_training', ?, NULL, NULL, NULL, NULL)
            """,
            (str(fit_path),),
        )
        conn.commit()
        changes_before = conn.total_changes

        result = main.strength_materialization_dry_run(
            tracks_dir=self.tracks_dir,
            conn=conn,
        )

        assert conn.total_changes == changes_before
        assert result["candidate_count"] == 1
        assert result["processable_count"] == 1
        assert result["version_outdated_count"] == 1
        assert result["status_distribution"]["pending"] == 1
        conn.close()

    def test_dry_run_classifies_candidates_and_never_writes_or_leaks_paths(self) -> None:
        self._seed_matrix()
        conn = profile_backend._raw_connect()
        try:
            changes_before = conn.total_changes
            result = main.strength_materialization_dry_run(
                limit=500,
                tracks_dir=self.tracks_dir,
                conn=conn,
            )
            changes_after = conn.total_changes
        finally:
            conn.close()

        assert changes_after == changes_before
        assert result == {
            "version": 1,
            "dry_run": True,
            "limit": 500,
            "strength_rows": 8,
            "scanned_count": 8,
            "limited": False,
            "candidate_count": 5,
            "processable_count": 3,
            "already_materialized_count": 2,
            "unstructured_count": 1,
            "source_missing_count": 2,
            "version_outdated_count": 1,
            "soft_deleted_skipped_count": 1,
            "status_distribution": {
                "pending": 4,
                "materialized": 2,
                "unstructured": 1,
                "source_missing": 0,
                "failed": 1,
            },
        }
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in ("legacy.fit", "outside", "file_path", "activity_id"):
            assert forbidden not in serialized

    def test_api_uses_unified_envelope_and_clamps_limit(self) -> None:
        self._seed_matrix()

        response = main.Api().get_strength_materialization_dry_run({"limit": 999999})

        assert response["ok"] is True
        assert response["code"] == 0
        assert response["data"]["dry_run"] is True
        assert response["data"]["limit"] == main.STRENGTH_MATERIALIZATION_DRY_RUN_MAX_LIMIT
        assert response["data"]["candidate_count"] == 5
        assert set(response) == {"ok", "code", "msg", "data", "traceId"}

        readonly_conn = main._open_readonly_profile_connection()
        try:
            assert readonly_conn.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                readonly_conn.execute("UPDATE activities SET title = title")
        finally:
            readonly_conn.close()

    def test_worker_materializes_terminal_states_and_preserves_unrelated_fields(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._raw_connect()
        try:
            self._insert(
                conn,
                name="structured.fit",
                file_path=str(self._fit("structured.fit")),
                version=0,
                status="pending",
            )
            self._insert(
                conn,
                name="empty.fit",
                file_path=str(self._fit("empty.fit")),
                version=0,
                status="pending",
            )
            self._insert(
                conn,
                name="missing.fit",
                file_path=str(self.tracks_dir / "missing.fit"),
                version=0,
                status="pending",
            )
            self._insert(
                conn,
                name="broken.fit",
                file_path=str(self._fit("broken.fit")),
                version=0,
                status="pending",
                complete_json=True,
            )
            conn.execute(
                """
                UPDATE activities
                SET title = 'Protected title', region = 'Protected region',
                    device_name = 'Protected device', weather_json = '{"temp":20}',
                    race_source = 'user'
                """
            )
            conn.commit()
        finally:
            conn.close()

        structured_raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))[
            "structured_partial_weight"
        ]["raw"]

        def parse_raw(path: Path) -> dict:
            if path.name == "structured.fit":
                return {"raw": structured_raw, "meta": {}}
            if path.name == "empty.fit":
                return {"raw": {}, "meta": {}}
            raise ValueError(f"private parser detail: {path}")

        with mock.patch.object(main.FITCoreEngine, "parse_fit_file_raw", side_effect=parse_raw):
            main._run_strength_materialization_backfill_worker(
                str(profile_backend.DB_PATH),
                str(self.tracks_dir),
                20,
            )

        conn = profile_backend._raw_connect()
        try:
            rows = {
                row["filename"]: dict(row)
                for row in conn.execute(
                    """
                    SELECT filename, title, region, device_name, weather_json, race_source,
                           strength_sets_json, strength_summary_json, muscle_heatmap_json,
                           strength_materialization_version, strength_materialization_status,
                           strength_materialization_error
                    FROM activities
                    ORDER BY id
                    """
                ).fetchall()
            }
        finally:
            conn.close()

        assert rows["structured.fit"]["strength_materialization_status"] == "materialized"
        assert json.loads(rows["structured.fit"]["strength_summary_json"])["working_set_count"] == 3
        assert json.loads(rows["structured.fit"]["muscle_heatmap_json"])["coverage"]["mapped_working_sets"] == 3
        assert rows["empty.fit"]["strength_materialization_status"] == "unstructured"
        assert rows["empty.fit"]["strength_sets_json"] is None
        assert rows["missing.fit"]["strength_materialization_status"] == "source_missing"
        assert rows["missing.fit"]["strength_materialization_error"] == "source_unavailable"
        assert rows["broken.fit"]["strength_materialization_status"] == "failed"
        assert rows["broken.fit"]["strength_materialization_error"] == "fit_materialization_failed"
        assert rows["broken.fit"]["strength_sets_json"] is not None
        assert "private" not in json.dumps(rows, ensure_ascii=False)
        for row in rows.values():
            assert row["strength_materialization_version"] == main.STRENGTH_MATERIALIZATION_VERSION
            assert row["title"] == "Protected title"
            assert row["region"] == "Protected region"
            assert row["device_name"] == "Protected device"
            assert row["weather_json"] == '{"temp":20}'
            assert row["race_source"] == "user"

        status = main._strength_materialization_backfill_status()
        assert status["running"] is False
        assert status["processed"] == 4
        assert status["updated"] == 4
        assert status["materialized"] == 1
        assert status["unstructured"] == 1
        assert status["source_missing"] == 1
        assert status["failed"] == 1
        assert status["error_code"] == ""

    def test_retry_processes_only_failed_and_source_missing_rows(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._raw_connect()
        try:
            for name, status in (
                ("failed.fit", "failed"),
                ("restored.fit", "source_missing"),
                ("pending.fit", "pending"),
            ):
                path = self._fit(name)
                self._insert(
                    conn,
                    name=name,
                    file_path=str(path),
                    version=main.STRENGTH_MATERIALIZATION_VERSION,
                    status=status,
                )
            conn.commit()
        finally:
            conn.close()

        parsed_names: list[str] = []

        def parse_raw(path: Path) -> dict:
            parsed_names.append(path.name)
            return {"raw": {}, "meta": {}}

        with mock.patch.object(main.FITCoreEngine, "parse_fit_file_raw", side_effect=parse_raw):
            main._run_strength_materialization_backfill_worker(
                str(profile_backend.DB_PATH),
                str(self.tracks_dir),
                20,
                retry_only=True,
            )

        assert parsed_names == ["failed.fit", "restored.fit"]
        conn = profile_backend._raw_connect()
        try:
            states = dict(
                conn.execute(
                    "SELECT filename, strength_materialization_status FROM activities"
                ).fetchall()
            )
        finally:
            conn.close()
        assert states == {
            "failed.fit": "unstructured",
            "restored.fit": "unstructured",
            "pending.fit": "pending",
        }

    def test_worker_is_limited_idempotent_and_single_instance(self) -> None:
        main.ensure_activity_sync_schema()
        conn = profile_backend._raw_connect()
        try:
            for index in range(3):
                name = f"batch-{index}.fit"
                self._insert(
                    conn,
                    name=name,
                    file_path=str(self._fit(name)),
                    version=0,
                    status="pending",
                )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main.FITCoreEngine,
            "parse_fit_file_raw",
            return_value={"raw": {}, "meta": {}},
        ) as parser:
            main._run_strength_materialization_backfill_worker(
                str(profile_backend.DB_PATH),
                str(self.tracks_dir),
                2,
            )
            assert parser.call_count == 2
            first_status = main._strength_materialization_backfill_status()
            assert first_status["limited"] is True
            assert first_status["processed"] == 2

            main._run_strength_materialization_backfill_worker(
                str(profile_backend.DB_PATH),
                str(self.tracks_dir),
                2,
            )
            assert parser.call_count == 3
            second_status = main._strength_materialization_backfill_status()
            assert second_status["limited"] is False
            assert second_status["processed"] == 1

            main._run_strength_materialization_backfill_worker(
                str(profile_backend.DB_PATH),
                str(self.tracks_dir),
                2,
            )
            assert parser.call_count == 3
            assert main._strength_materialization_backfill_status()["processed"] == 0

        main._STRENGTH_MATERIALIZATION_STATUS["running"] = True
        with mock.patch.object(main.threading, "Thread") as thread_class:
            status = main._start_strength_materialization_backfill(limit=2)
        assert status["running"] is True
        thread_class.assert_not_called()

    def test_worker_apis_use_safe_unified_envelopes(self) -> None:
        safe_status = {
            "running": False,
            "retry_only": False,
            "version": 1,
            "total": 0,
            "processed": 0,
            "updated": 0,
            "materialized": 0,
            "unstructured": 0,
            "source_missing": 0,
            "failed": 0,
            "skipped": 0,
            "limited": False,
            "started_at": 0.0,
            "finished_at": 0.0,
            "error_code": "",
        }
        with mock.patch.object(
            main,
            "_start_strength_materialization_backfill",
            return_value=safe_status,
        ) as start:
            started = main.Api().start_strength_materialization_backfill({"limit": 10})
            retried = main.Api().retry_strength_materialization_backfill({"limit": 5})
        queried = main.Api().get_strength_materialization_backfill_status()

        assert started["ok"] is True
        assert retried["ok"] is True
        assert queried["ok"] is True
        assert start.call_args_list == [
            mock.call(limit=10),
            mock.call(limit=5, retry_only=True),
        ]
        serialized = json.dumps([started, retried, queried], ensure_ascii=False)
        for forbidden in ("file_path", "activity_id", "traceback", "private parser"):
            assert forbidden not in serialized
