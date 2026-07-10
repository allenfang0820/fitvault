import unittest
import os
import logging
import sqlite3
from pathlib import Path
import profile_backend
import tempfile
import json
import main
from unittest import mock


def _reset_logger(name: str) -> None:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

class TestDuplicateCheck(unittest.TestCase):
    def setUp(self):
        # Setup a temporary database for testing
        self.temp_db_path = "temp_test_db.sqlite"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{self.temp_db_path}{suffix}").unlink(missing_ok=True)
        profile_backend.DB_PATH = Path(self.temp_db_path)
        
        # Initialize schema
        conn = profile_backend._conn()
        conn.close()
        
        # Mock some points for spatial matching tests
        self.points_test1 = [
            {"lat": 30.0001, "lon": 104.0001, "time": "2023-01-01T10:00:00Z"},
            {"lat": 30.0002, "lon": 104.0002, "time": "2023-01-01T10:00:10Z"},
            {"lat": 30.0003, "lon": 104.0003, "time": "2023-01-01T10:00:20Z"}
        ]
        
        self.points_test2 = [
            {"lat": 31.0001, "lon": 105.0001, "time": "2023-01-02T10:00:00Z"},
            {"lat": 31.0002, "lon": 105.0002, "time": "2023-01-02T10:00:10Z"}
        ]

        # Insert some test data
        profile_backend.save_activity({
            "filename": "test1.fit",
            "dist_km": 10.5,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": "/mock/path/test1.fit",
            "points_json": self.points_test1
        })
        
        profile_backend.save_activity({
            "filename": "test2.fit",
            "dist_km": 5.2,
            "duration_sec": 1800,
            "start_time": "2023-01-02T10:00:00Z",
            "file_path": "/mock/path/test2.fit",
            "points_json": self.points_test2
        })
        
    def tearDown(self):
        _reset_logger("duplicate_check")
        # Clean up temporary database
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)

    def test_no_duplicate(self):
        # Test a completely different track
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-03T10:00:00Z",
            dist_km=20.0,
            duration_sec=7200,
            points_json=[]
        )
        self.assertFalse(res["is_duplicate"])
        self.assertTrue(res["score"] < 80.0)

    def test_exact_duplicate(self):
        # Test an exact duplicate of test1
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.5,
            duration_sec=3600,
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")

    def test_exact_duplicate_without_points(self):
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.5,
            duration_sec=3600,
            points_json=[]
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")

    def test_duplicate_check_continues_when_log_file_handler_fails(self):
        _reset_logger("duplicate_check")
        with mock.patch.object(profile_backend.logging, "FileHandler", side_effect=PermissionError("denied")):
            res = profile_backend.check_duplicate_activity(
                start_time="2023-01-01T10:00:00Z",
                dist_km=10.5,
                duration_sec=3600,
                points_json=[],
            )

        self.assertTrue(res["is_duplicate"])
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")

    def test_duplicate_check_log_prefers_localappdata_on_windows(self):
        with tempfile.TemporaryDirectory() as temp_local_app_data:
            with mock.patch.object(profile_backend.sys, "platform", "win32"), \
                 mock.patch.dict(profile_backend.os.environ, {"LOCALAPPDATA": temp_local_app_data}, clear=False):
                self.assertEqual(
                    profile_backend._fitvault_log_path("duplicate_check.log"),
                    Path(temp_local_app_data) / "FitVault" / "logs" / "duplicate_check.log",
                )

    def test_deleted_activity_does_not_count_as_duplicate(self):
        conn = profile_backend._conn()
        try:
            conn.execute(
                "UPDATE activities SET deleted_at = datetime('now') WHERE filename = ?",
                ("test1.fit",),
            )
            conn.commit()
        finally:
            conn.close()

        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.5,
            duration_sec=3600,
            points_json=self.points_test1
        )

        self.assertFalse(res["is_duplicate"])
        self.assertIsNone(res["duplicate_record"])

    def test_activity_list_filtered_dedupes_semantic_duplicates_before_paging(self):
        profile_backend.save_activity({
            "filename": "test1_copy.fit",
            "dist_km": 10.5,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": "/mock/path/test1_copy.fit",
            "points_json": []
        })

        rows, total = profile_backend.get_activity_list_filtered(0, 20, "all")

        self.assertEqual(total, 2)
        identities = {
            (row.get("sport_type"), row.get("start_time"), row.get("dist_km"), row.get("duration"))
            for row in rows
        }
        self.assertEqual(len(identities), len(rows))


class TestActivityDataLayerDedup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = profile_backend.DB_PATH
        self.original_tracks_dir = profile_backend.TRACKS_DIR
        self.original_schema_ready = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        profile_backend.DB_PATH = Path(self.temp_dir.name) / "dedupe.sqlite"
        profile_backend.TRACKS_DIR = Path(self.temp_dir.name) / "tracks"
        profile_backend.TRACKS_DIR.mkdir()

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend.TRACKS_DIR = self.original_tracks_dir
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_schema_ready
        self.temp_dir.cleanup()

    def _activity_count(self) -> int:
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
            return int(row[0])
        finally:
            conn.close()

    def _activity_exists(self, activity_id: int) -> bool:
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT id FROM activities WHERE id = ?", (activity_id,)).fetchone()
            return row is not None
        finally:
            conn.close()

    def _insert_activity_row(
        self,
        filename: str,
        file_path: str,
        updated_at: str,
        *,
        start_time: str = "2023-01-01T10:00:00Z",
        dist_km: float = 10.5,
        duration_sec: int = 3600,
        deleted_at=None,
    ) -> int:
        conn = profile_backend._conn()
        try:
            profile_backend._init_schema(conn)
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, file_name, sport_type, sub_sport_type, dist_km, duration_sec,
                     start_time, file_path, points_json, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    filename,
                    "running",
                    "unknown",
                    dist_km,
                    duration_sec,
                    start_time,
                    file_path,
                    "[]",
                    updated_at,
                    deleted_at,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def test_save_activity_strict_duplicate_returns_existing_id(self):
        first_id = profile_backend.save_activity({
            "filename": "a.fit",
            "sport_type": "running",
            "sub_sport_type": "unknown",
            "dist_km": 10.5,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": str(profile_backend.TRACKS_DIR / "a.fit"),
            "points_json": [],
        })
        second_id = profile_backend.save_activity({
            "filename": "b.fit",
            "sport_type": "running",
            "sub_sport_type": "unknown",
            "dist_km": 10.5,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": str(profile_backend.TRACKS_DIR / "b.fit"),
            "points_json": [],
        })

        self.assertEqual(second_id, first_id)
        self.assertEqual(self._activity_count(), 1)

    def test_persist_sync_activity_uses_in_memory_dedupe_index(self):
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.ensure_activity_sync_schema()
        dedupe_index = {}
        first_path = profile_backend.TRACKS_DIR / "sync-a.fit"
        second_path = profile_backend.TRACKS_DIR / "sync-b.fit"
        first_path.write_text("fit-a", encoding="utf-8")
        second_path.write_text("fit-b", encoding="utf-8")
        base_activity = {
            "file_name": "sync-a.fit",
            "filename": "sync-a.fit",
            "title": "sync-a",
            "title_source": "fit",
            "sport_type": "running",
            "sub_sport_type": "unknown",
            "distance": 10.5,
            "dist_km": 10.5,
            "duration": 3600,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": str(first_path),
            "points": [],
            "points_json": "[]",
            "track_json": "[]",
        }

        first = main._persist_sync_activity(dict(base_activity), dedupe_index=dedupe_index)
        placeholder_id = main._upsert_processing_activity_placeholder(second_path, "sync-b.fit")
        second_activity = dict(base_activity)
        second_activity.update({
            "file_name": "sync-b.fit",
            "filename": "sync-b.fit",
            "title": "sync-b",
            "file_path": str(second_path),
        })
        second = main._persist_sync_activity(second_activity, dedupe_index=dedupe_index)

        self.assertEqual(first["op"], "inserted")
        self.assertEqual(second["op"], "skipped")
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["dedupe"], "strict_key")
        self.assertTrue(second["duplicate"])
        self.assertEqual(self._activity_count(), 1)
        self.assertFalse(self._activity_exists(placeholder_id))

    def test_persist_sync_activity_ignores_soft_deleted_semantic_duplicate(self):
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.ensure_activity_sync_schema()
        deleted_path = profile_backend.TRACKS_DIR / "deleted.fit"
        new_path = profile_backend.TRACKS_DIR / "resynced.fit"
        deleted_path.write_text("deleted", encoding="utf-8")
        new_path.write_text("resynced", encoding="utf-8")
        self._insert_activity_row(
            "deleted.fit",
            str(deleted_path),
            "2023-01-02T00:00:00",
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.5,
            duration_sec=3600,
            deleted_at="2023-01-03T00:00:00",
        )
        activity = {
            "file_name": "resynced.fit",
            "filename": "resynced.fit",
            "title": "resynced",
            "title_source": "fit",
            "sport_type": "running",
            "sub_sport_type": "unknown",
            "distance": 10.5,
            "dist_km": 10.5,
            "duration": 3600,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": str(new_path),
            "points": [],
            "points_json": "[]",
            "track_json": "[]",
        }

        res = main._persist_sync_activity(activity)

        self.assertEqual(res["op"], "inserted")
        conn = profile_backend._conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM activities WHERE deleted_at IS NULL").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 2)
        self.assertEqual(active, 1)

    def test_cleanup_duplicate_activities_dry_run_does_not_delete(self):
        keep_path = profile_backend.TRACKS_DIR / "keep.fit"
        dup_path = profile_backend.TRACKS_DIR / "dup.fit"
        keep_path.write_text("keep", encoding="utf-8")
        dup_path.write_text("dup", encoding="utf-8")
        keep_id = self._insert_activity_row("keep.fit", str(keep_path), "2023-01-02T00:00:00")
        dup_id = self._insert_activity_row("dup.fit", str(dup_path), "2023-01-01T00:00:00")

        res = profile_backend.cleanup_duplicate_activities(dry_run=True)

        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["groups_found"], 1)
        self.assertEqual(res["rows_deleted"], 0)
        self.assertIn(keep_id, res["kept_ids"])
        self.assertIn(dup_id, res["deleted_ids"])
        self.assertTrue(dup_path.exists())
        self.assertEqual(self._activity_count(), 2)

    def test_cleanup_duplicate_activities_deletes_rows_and_controlled_files(self):
        keep_path = profile_backend.TRACKS_DIR / "keep.fit"
        dup_path = profile_backend.TRACKS_DIR / "dup.fit"
        outside_dir = Path(self.temp_dir.name) / "outside"
        outside_dir.mkdir()
        outside_path = outside_dir / "outside.fit"
        keep_path.write_text("keep", encoding="utf-8")
        dup_path.write_text("dup", encoding="utf-8")
        outside_path.write_text("outside", encoding="utf-8")
        keep_id = self._insert_activity_row("keep.fit", str(keep_path), "2023-01-03T00:00:00")
        dup_id = self._insert_activity_row("dup.fit", str(dup_path), "2023-01-02T00:00:00")
        unsafe_id = self._insert_activity_row("outside.fit", str(outside_path), "2023-01-01T00:00:00")

        res = profile_backend.cleanup_duplicate_activities(dry_run=False)

        self.assertTrue(res["ok"])
        self.assertFalse(res["dry_run"])
        self.assertEqual(res["groups_found"], 1)
        self.assertEqual(res["rows_deleted"], 2)
        self.assertEqual(res["files_deleted"], 1)
        self.assertEqual(res["kept_ids"], [keep_id])
        self.assertEqual(sorted(res["deleted_ids"]), sorted([dup_id, unsafe_id]))
        self.assertEqual(len(res["skipped_unsafe_paths"]), 1)
        self.assertFalse(dup_path.exists())
        self.assertTrue(outside_path.exists())
        self.assertEqual(self._activity_count(), 1)


def assert_response_envelope(testcase, res, ok):
    testcase.assertEqual(res["ok"], ok)
    testcase.assertIn("code", res)
    testcase.assertIn("msg", res)
    testcase.assertIn("data", res)
    testcase.assertIn("traceId", res)
    testcase.assertIsInstance(res["data"], dict)
    testcase.assertTrue(res["traceId"])

    def test_partial_overlap_duplicate(self):
        # Test a track with same start time, slightly different distance and duration, but same points
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.53, # diff is 0.03 < 0.05
            duration_sec=3604, # diff is 4 < 5
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        
        # Test a track with same start time, slightly larger diffs, no points match
        res2 = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.6, # diff is 0.1 < 0.5
            duration_sec=3620, # diff is 20 < 60
            points_json=[]
        )
        self.assertFalse(res2["is_duplicate"])

    def test_missing_start_time(self):
        # If start time is missing, it should rely on dist and duration and points
        # 由于我们优化了时区和时间解析逻辑，现在它能从 points_json 中提取时间并获得时间匹配分
        res = profile_backend.check_duplicate_activity(
            start_time=None,
            dist_km=10.51, # close to 10.5
            duration_sec=3602, # close to 3600
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)

    def test_spatial_match_duplicate(self):
        # Test a track with similar time but completely matching spatial points
        # time diff is 2 mins (120s), dist diff < 5%, dur diff < 5%, spatial match 100%
        # Score = 15 (time) + 20 (dist) + 20 (dur) + 30 (spatial) = 85 >= 80
        points_same_space = [
            {"lat": 30.0001, "lon": 104.0001, "time": "2023-01-01T10:02:00Z"},
            {"lat": 30.0002, "lon": 104.0002, "time": "2023-01-01T10:02:10Z"},
            {"lat": 30.0003, "lon": 104.0003, "time": "2023-01-01T10:02:20Z"}
        ]
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:02:00Z",
            dist_km=10.51,
            duration_sec=3600,
            points_json=points_same_space
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")


class TestDeleteActivitiesGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "delete_guard.sqlite"
        self.tracks_dir = Path(self.temp_dir.name) / "tracks"
        self.outside_dir = Path(self.temp_dir.name) / "outside"
        self.tracks_dir.mkdir()
        self.outside_dir.mkdir()
        self.original_db_path = profile_backend.DB_PATH
        self.original_tracks_dir = main.TRACKS_DIR
        profile_backend.DB_PATH = self.temp_db_path
        main.TRACKS_DIR = str(self.tracks_dir)
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        main.TRACKS_DIR = self.original_tracks_dir
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        self.temp_dir.cleanup()

    def _save_activity_with_file(self, file_path) -> int:
        return profile_backend.save_activity({
            "filename": "delete-test.fit",
            "dist_km": 1.0,
            "duration_sec": 60,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": str(file_path) if file_path else "",
            "points_json": [],
        })

    def _activity_exists(self, activity_id: int) -> bool:
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT id FROM activities WHERE id = ?", (activity_id,)).fetchone()
            return row is not None
        finally:
            conn.close()

    def _insert_activity_row_with_file(self, filename: str, file_path: Path) -> int:
        conn = profile_backend._conn()
        try:
            profile_backend._init_schema(conn)
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, file_name, sport_type, sub_sport_type, dist_km, duration_sec,
                     start_time, file_path, points_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    filename,
                    "running",
                    "unknown",
                    10.5,
                    3600,
                    "2023-01-01T10:00:00Z",
                    str(file_path),
                    "[]",
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def test_delete_activities_rejects_empty_ids(self):
        res = main.Api().delete_activities([], "DELETE:0")
        assert_response_envelope(self, res, False)
        self.assertEqual(res["code"], main.API_CODE_VALIDATION)
        self.assertEqual(res["data"]["file_errors"], [])
        self.assertEqual(res["data"]["skipped_unsafe_paths"], [])

    def test_delete_activities_requires_confirm_token(self):
        fit_path = self.tracks_dir / "inside.fit"
        fit_path.write_text("fit", encoding="utf-8")
        activity_id = self._save_activity_with_file(fit_path)

        res = main.Api().delete_activities([activity_id], "WRONG")

        assert_response_envelope(self, res, False)
        self.assertEqual(res["code"], main.API_CODE_AUTH_REQUIRED)
        self.assertEqual(res["error"], "删除确认参数无效")
        self.assertTrue(fit_path.exists())
        self.assertTrue(self._activity_exists(activity_id))

    def test_delete_activities_deletes_controlled_file_and_db_row(self):
        fit_path = self.tracks_dir / "inside.fit"
        fit_path.write_text("fit", encoding="utf-8")
        activity_id = self._save_activity_with_file(fit_path)

        res = main.Api().delete_activities([activity_id], "DELETE:1")
        data = res.get("data") or {}

        assert_response_envelope(self, res, True)
        self.assertEqual(res["code"], main.API_CODE_OK)
        self.assertEqual(data["deleted"], 1)
        self.assertEqual(data["files_deleted"], 1)
        self.assertFalse(fit_path.exists())
        self.assertFalse(self._activity_exists(activity_id))

    def test_delete_activities_rejects_outside_tracks_dir(self):
        fit_path = self.outside_dir / "outside.fit"
        fit_path.write_text("fit", encoding="utf-8")
        activity_id = self._save_activity_with_file(fit_path)

        res = main.Api().delete_activities([activity_id], "DELETE:1")
        data = res.get("data") or {}

        assert_response_envelope(self, res, True)
        self.assertEqual(data["deleted"], 0)
        self.assertEqual(len(data["skipped_unsafe_paths"]), 1)
        self.assertTrue(fit_path.exists())
        self.assertTrue(self._activity_exists(activity_id))

    def test_delete_activities_deletes_db_row_for_missing_controlled_file(self):
        missing_path = self.tracks_dir / "missing.fit"
        activity_id = self._save_activity_with_file(missing_path)

        res = main.Api().delete_activities([activity_id, 999999], "DELETE:2")
        data = res.get("data") or {}

        assert_response_envelope(self, res, True)
        self.assertEqual(data["deleted"], 1)
        self.assertEqual(data["missing_ids"], [999999])
        self.assertEqual(len(data["missing_file_paths"]), 1)
        self.assertFalse(self._activity_exists(activity_id))

    def test_delete_activities_deletes_hidden_semantic_duplicates(self):
        fit_path_a = self.tracks_dir / "dup-a.fit"
        fit_path_b = self.tracks_dir / "dup-b.fit"
        fit_path_a.write_text("fit-a", encoding="utf-8")
        fit_path_b.write_text("fit-b", encoding="utf-8")
        activity_a = self._insert_activity_row_with_file("dup-a.fit", fit_path_a)
        activity_b = self._insert_activity_row_with_file("dup-b.fit", fit_path_b)

        res = main.Api().delete_activities([activity_a], "DELETE:1")
        data = res.get("data") or {}

        self.assertTrue(res["ok"])
        self.assertEqual(data["deleted"], 2)
        self.assertEqual(data["files_deleted"], 2)
        self.assertEqual(data["expanded_duplicate_ids"], [activity_b])
        self.assertFalse(fit_path_a.exists())
        self.assertFalse(fit_path_b.exists())
        self.assertFalse(self._activity_exists(activity_a))
        self.assertFalse(self._activity_exists(activity_b))

if __name__ == '__main__':
    unittest.main()
