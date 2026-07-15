import os
import sqlite3
import tempfile
import threading
import time
import types
import unittest
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import main
import coros_sync
import garmin_sync
import llm_backend
import profile_backend
import track_backend
from utils.weather_api import fetch_historical_weather


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"


class TestFitSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        self.original_busy_timeout_ms = profile_backend.SQLITE_BUSY_TIMEOUT_MS
        self.original_connect_timeout_sec = profile_backend.SQLITE_CONNECT_TIMEOUT_SEC
        self.original_tracks_dir = main.TRACKS_DIR
        self.original_imports_dir = main.IMPORTS_DIR
        self.original_sync_state_dir = profile_backend.SYNC_STATE_DIR
        self.original_sync_state_path = profile_backend.SYNC_STATE_PATH
        self.original_profile_cache_path = profile_backend.PROFILE_CACHE_PATH
        self.original_np_backfill_status = dict(main._NP_BACKFILL_STATUS)
        self.original_weather_backfill_status = dict(main._WEATHER_BACKFILL_STATUS)
        self.original_region_cooldown = profile_backend.REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.TRACKS_DIR = str(self.temp_dir / "tracks")
        main.IMPORTS_DIR = str(self.temp_dir / "imports")
        profile_backend.SYNC_STATE_DIR = str(self.temp_dir / "sync_state")
        profile_backend.SYNC_STATE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "sync_state.json")
        profile_backend.PROFILE_CACHE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "user_profile_cache.json")
        profile_backend.REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL = None
        Path(main.TRACKS_DIR).mkdir(parents=True, exist_ok=True)
        Path(main.IMPORTS_DIR).mkdir(parents=True, exist_ok=True)
        Path(profile_backend.SYNC_STATE_DIR).mkdir(parents=True, exist_ok=True)
        self.api = main.Api()

    def tearDown(self):
        thread = getattr(main, "_NP_BACKFILL_THREAD", None)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        main._NP_BACKFILL_THREAD = None
        timer = getattr(main, "_NP_BACKFILL_TIMER", None)
        if timer and timer.is_alive():
            timer.cancel()
        main._NP_BACKFILL_TIMER = None
        weather_thread = getattr(main, "_WEATHER_BACKFILL_THREAD", None)
        if weather_thread and weather_thread.is_alive():
            weather_thread.join(timeout=2.0)
        main._WEATHER_BACKFILL_THREAD = None
        weather_timer = getattr(main, "_WEATHER_BACKFILL_TIMER", None)
        if weather_timer and weather_timer.is_alive():
            weather_timer.cancel()
        main._WEATHER_BACKFILL_TIMER = None
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        profile_backend.SQLITE_BUSY_TIMEOUT_MS = self.original_busy_timeout_ms
        profile_backend.SQLITE_CONNECT_TIMEOUT_SEC = self.original_connect_timeout_sec
        main.TRACKS_DIR = self.original_tracks_dir
        main.IMPORTS_DIR = self.original_imports_dir
        profile_backend.SYNC_STATE_DIR = self.original_sync_state_dir
        profile_backend.SYNC_STATE_PATH = self.original_sync_state_path
        profile_backend.PROFILE_CACHE_PATH = self.original_profile_cache_path
        profile_backend.REGION_ENRICH_PROVIDER_COOLDOWN_UNTIL = self.original_region_cooldown
        with main._NP_BACKFILL_LOCK:
            main._NP_BACKFILL_STATUS.clear()
            main._NP_BACKFILL_STATUS.update(self.original_np_backfill_status)
        with main._WEATHER_BACKFILL_LOCK:
            main._WEATHER_BACKFILL_STATUS.clear()
            main._WEATHER_BACKFILL_STATUS.update(self.original_weather_backfill_status)
        self.temp_dir_obj.cleanup()

    def _workspace_config(self) -> dict:
        return {
            "workspace_track_abs_path": str(self.temp_dir),
            "workspace_track_status": {
                "exists": True,
                "is_dir": True,
                "readable": True,
                "writable": True,
            },
            "workspace_track_recovered": False,
        }

    def _activity(self, file_name: str) -> dict:
        resolved = str((self.temp_dir / file_name).resolve())
        points = [
            {"time": f"2026-05-19T08:00:{idx:02d}Z", "distance": float(idx) * 10.0}
            for idx in range(35)
        ]
        return {
            "file_name": file_name,
            "filename": file_name,
            "title": file_name,
            "title_source": "filename",
            "start_time": "2026-05-19T08:00:00Z",
            "start_time_utc": "2026-05-19T08:00:00Z",
            "sport_type": "running",
            "sub_sport_type": "unknown",
            "distance": 10.0,
            "dist_km": 10.0,
            "duration": 3600,
            "duration_sec": 3600,
            "avg_pace": 360.0,
            "avg_hr": 150,
            "max_hr": 170,
            "calories": 620,
            "track_json": json.dumps(points),
            "points_json": json.dumps(points),
            "file_path": resolved,
            "gain_m": 120.0,
            "max_alt_m": 60.0,
            "start_lat": 30.67,
            "start_lon": 104.06,
            "region": "成都市",
        }

    def _set_activity_start(self, activity: dict, start_time: str) -> None:
        activity["start_time"] = start_time
        activity["start_time_utc"] = start_time

    def _duplicate_points(self, start_minute: int = 0) -> list[dict]:
        return [
            {"time": f"2026-05-19T08:{start_minute:02d}:00Z", "lat": 30.6700, "lon": 104.0600, "alt": 500},
            {"time": f"2026-05-19T08:{start_minute + 1:02d}:00Z", "lat": 30.6705, "lon": 104.0605, "alt": 510},
            {"time": f"2026-05-19T08:{start_minute + 2:02d}:00Z", "lat": 30.6710, "lon": 104.0610, "alt": 505},
        ]

    def _wait_job_done(self, job_id: str, timeout_sec: float = 5.0) -> dict:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            status = self.api.get_sync_local_fit_files_status(job_id)
            if status.get("state") == "done":
                return status
            time.sleep(0.05)
        self.fail(f"同步任务未在 {timeout_sec} 秒内结束: {job_id}")

    def test_sync_local_fit_files_recovers_after_temporary_db_lock(self):
        fit_path = self.temp_dir / "locked.fit"
        fit_path.write_bytes(b"x" * 8192)
        main.ensure_activity_sync_schema()

        profile_backend.SQLITE_BUSY_TIMEOUT_MS = 100
        profile_backend.SQLITE_CONNECT_TIMEOUT_SEC = 0.1

        lock_ready = threading.Event()

        def hold_write_lock():
            conn = sqlite3.connect(str(profile_backend.DB_PATH), timeout=0.1)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("BEGIN EXCLUSIVE")
                conn.execute("INSERT INTO activities (filename) VALUES ('locker.fit')")
                lock_ready.set()
                time.sleep(0.45)
                conn.commit()
            finally:
                conn.close()

        lock_thread = threading.Thread(target=hold_write_lock, daemon=True)
        lock_thread.start()
        self.assertTrue(lock_ready.wait(timeout=1.0))

        start = time.perf_counter()
        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("locked.fit")):
            result = self.api.sync_local_fit_files()
        elapsed = time.perf_counter() - start
        lock_thread.join(timeout=1.0)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["inserted"], 1)
        self.assertGreater(elapsed, 0.2)

    def test_background_sync_reports_progress_for_batch_files(self):
        fit_files = []
        for name in ("batch_a.fit", "batch_b.fit", "batch_c.fit"):
            path = self.temp_dir / name
            path.write_bytes(b"x" * 8192)
            fit_files.append(path)

        def parse_side_effect(path_obj):
            time.sleep(0.08)
            activity = self._activity(Path(path_obj).name)
            minute = {"batch_a.fit": 0, "batch_b.fit": 10, "batch_c.fit": 20}[Path(path_obj).name]
            self._set_activity_start(activity, f"2026-05-19T08:{minute:02d}:00Z")
            return activity

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=fit_files), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", side_effect=parse_side_effect):
            start_res = self.api.start_sync_local_fit_files()
            self.assertTrue(start_res["ok"], start_res)
            status_mid = self.api.get_sync_local_fit_files_status(start_res["job_id"])
            self.assertIn(status_mid.get("state"), {"queued", "running", "done"})
            final_status = self._wait_job_done(start_res["job_id"])

        self.assertTrue(final_status["ok"], final_status)
        self.assertEqual(final_status["result"]["scanned"], 3)
        self.assertEqual(final_status["result"]["inserted"], 3)
        self.assertEqual(final_status["total"], 3)
        self.assertEqual(final_status["progress"], 100.0)

    def test_get_activity_list_remains_available_during_background_sync(self):
        fit_files = []
        for name in ("concurrent_a.fit", "concurrent_b.fit"):
            path = self.temp_dir / name
            path.write_bytes(b"x" * 8192)
            fit_files.append(path)

        def parse_side_effect(path_obj):
            time.sleep(0.25)
            activity = self._activity(Path(path_obj).name)
            minute = {"concurrent_a.fit": 0, "concurrent_b.fit": 10}[Path(path_obj).name]
            self._set_activity_start(activity, f"2026-05-19T09:{minute:02d}:00Z")
            return activity

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=fit_files), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", side_effect=parse_side_effect):
            start_res = self.api.start_sync_local_fit_files()
            self.assertTrue(start_res["ok"], start_res)
            time.sleep(0.05)
            list_started = time.perf_counter()
            list_res = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")
            list_elapsed = time.perf_counter() - list_started
            final_status = self._wait_job_done(start_res["job_id"])

        self.assertTrue(list_res["ok"], list_res)
        self.assertLess(list_elapsed, 0.5)
        self.assertTrue(final_status["ok"], final_status)
        self.assertEqual(final_status["result"]["inserted"], 2)

    def test_single_file_sync_finishes_quickly_with_mock_parser(self):
        fit_path = self.temp_dir / "single.fit"
        fit_path.write_bytes(b"x" * 8192)

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("single.fit")):
            result = self.api.sync_local_fit_files()

        self.assertTrue(result["ok"], result)
        self.assertLess(result.get("elapsed_sec", 99), 1.0)

    def test_local_fit_sync_filters_tiny_health_fit_before_parse(self):
        fit_path = self.temp_dir / "health.fit"
        fit_path.write_bytes(b"fit")

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync") as parse_mock, \
             mock.patch.object(main, "_persist_sync_activity") as persist_mock:
            result = self.api.sync_local_fit_files()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        parse_mock.assert_not_called()
        persist_mock.assert_not_called()

    def test_local_fit_sync_filters_zero_activity_after_parse(self):
        fit_path = self.temp_dir / "8618600673630.fit"
        fit_path.write_bytes(b"x" * 8192)
        activity = self._activity(fit_path.name)
        activity.update({
            "title": "8618600673630",
            "sport_type": "unknown",
            "distance": 0,
            "dist_km": 0,
            "duration": 0,
            "duration_sec": 0,
            "track_json": "[]",
            "points_json": "[]",
        })

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=activity) as parse_mock, \
             mock.patch.object(main, "_persist_sync_activity") as persist_mock:
            result = self.api.sync_local_fit_files()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)
        parse_mock.assert_called_once()
        persist_mock.assert_not_called()

    def test_single_fit_sync_refreshes_career_derived_events_after_write(self):
        fit_path = self.temp_dir / "career-refresh.fit"
        fit_path.write_bytes(b"x" * 8192)

        with mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("career-refresh.fit")), \
             mock.patch.object(main.career_backend, "refresh_career_derived_events", return_value={"ok": True}) as refresh_mock:
            result = main._sync_single_fit_file(fit_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["op"], "inserted")
        self.assertEqual(result["career_refresh"]["ok"], True)
        refresh_mock.assert_called_once_with(include_pb=False)

    def test_single_fit_sync_keeps_import_success_when_career_refresh_fails(self):
        fit_path = self.temp_dir / "career-refresh-warning.fit"
        fit_path.write_bytes(b"x" * 8192)

        with mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("career-refresh-warning.fit")), \
             mock.patch.object(main.career_backend, "refresh_career_derived_events", side_effect=RuntimeError("acs boom")):
            result = main._sync_single_fit_file(fit_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["op"], "inserted")
        self.assertFalse(result["career_refresh"]["ok"])
        self.assertIn("活动导入已保留", result["career_refresh"]["message"])

    def test_batch_import_tracks_refreshes_career_once_after_imports(self):
        fit_path = self.temp_dir / "manual-import.fit"
        fit_path.write_bytes(b"x" * 8192)

        with mock.patch.object(main, "_sync_single_fit_file", return_value={"ok": True, "op": "inserted", "activity_id": 88}) as sync_mock, \
             mock.patch.object(main, "_refresh_career_derived_events_safe", return_value={"ok": True, "reason": "batch_import_tracks"}) as refresh_mock:
            result = self.api.batch_import_tracks([str(fit_path)])

        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["data"]["imported"]), 1)
        sync_mock.assert_called_once()
        self.assertEqual(sync_mock.call_args.kwargs.get("refresh_career"), False)
        refresh_mock.assert_called_once_with("batch_import_tracks")
        self.assertEqual(result["data"]["career_refresh"]["ok"], True)

    def test_local_fit_sync_refreshes_career_once_after_activity_changes(self):
        fit_path = self.temp_dir / "local-career-refresh.fit"
        fit_path.write_bytes(b"x" * 8192)

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("local-career-refresh.fit")), \
             mock.patch.object(main, "_refresh_career_derived_events_safe", return_value={"ok": True, "reason": "local_fit_sync"}) as refresh_mock:
            result = self.api.sync_local_fit_files()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["inserted"], 1)
        refresh_mock.assert_called_once_with("local_fit_sync")
        self.assertEqual(result["career_refresh"]["ok"], True)

    def test_remote_fit_sync_downloads_garmin_fit_and_imports_without_openclaw(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": True,
            "region": "cn",
            "output_dir": main.TRACKS_DIR,
            "mode": "date_range",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "searched": 2,
            "downloaded": 1,
            "skipped": 1,
            "failed": 0,
            "files": [{"activity_id": "100", "status": "downloaded"}],
            "errors": [],
        }
        import_result = {"ok": True, "inserted": 1, "updated": 0, "skipped": 1, "errors": []}
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
            "garmin_region": "global",
        }), mock.patch.object(garmin_sync, "download_fit_json", return_value=download_summary) as download_mock, \
             mock.patch.object(api, "sync_local_fit_files", return_value=import_result) as import_mock, \
             mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("Garmin activity sync must not call LLM")):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertTrue(result["ok"], result)
        download_mock.assert_called_once_with(
            start_date="2026-05-01",
            end_date="2026-05-31",
            output_dir=main.TRACKS_DIR,
            region="global",
        )
        import_mock.assert_called_once_with()
        self.assertEqual(result["data"]["download"], download_summary)
        self.assertEqual(result["data"]["import"], import_result)
        self.assertEqual(result["data"]["start_date"], "2026-05-01")
        self.assertEqual(result["data"]["end_date"], "2026-05-31")
        self.assertEqual(result["data"]["target_dir"], main.TRACKS_DIR)

    def test_remote_fit_sync_rejects_invalid_date_range(self):
        api = object.__new__(main.Api)
        with mock.patch.object(garmin_sync, "download_fit_json") as download_mock:
            result = api.sync_remote_fit_activities("2026-06-01", "2026-05-01")
        self.assertFalse(result["ok"], result)
        self.assertIn("开始日期不能晚于结束日期", result["error"])
        download_mock.assert_not_called()

    def test_remote_fit_sync_returns_provider_failure_as_external_service(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(garmin_sync, "download_fit_json", side_effect=garmin_sync.GarminScriptFailed("下载失败")) as download_mock, \
             mock.patch.object(api, "sync_local_fit_files") as import_mock, \
             mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("Garmin activity sync must not call LLM")):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], main.API_CODE_EXTERNAL_SERVICE)
        self.assertIn("下载失败", result["error"])
        self.assertEqual(result["data"]["provider"], "garmin")
        self.assertEqual(result["data"]["provider_error_code"], "garmin_script_failed")
        self.assertIn("action_hint", result["data"])
        download_mock.assert_called_once()
        import_mock.assert_not_called()

    def test_remote_fit_sync_returns_auth_required_code_and_action_hint(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
            "garmin_region": "global",
        }), mock.patch.object(garmin_sync, "download_fit_json", side_effect=garmin_sync.GarminAuthRequiredError("Garmin 授权不可用或已失效")) as download_mock, \
             mock.patch.object(api, "sync_local_fit_files") as import_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], main.API_CODE_EXTERNAL_SERVICE)
        self.assertEqual(result["data"]["provider"], "garmin")
        self.assertEqual(result["data"]["provider_error_code"], "garmin_auth_required")
        self.assertIn("重新启动", result["data"]["action_hint"])
        download_mock.assert_called_once()
        import_mock.assert_not_called()

    def test_remote_fit_sync_returns_skill_missing_code_and_action_hint(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(garmin_sync, "download_fit_json", side_effect=garmin_sync.GarminSkillNotFoundError("未找到 Garmin skill 脚本")):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], main.API_CODE_EXTERNAL_SERVICE)
        self.assertEqual(result["data"]["provider"], "garmin")
        self.assertEqual(result["data"]["provider_error_code"], "garmin_skill_not_found")
        self.assertIn("garmin-stats", result["data"]["action_hint"])
        self.assertEqual(result["data"]["start_date"], "2026-05-01")
        self.assertEqual(result["data"]["end_date"], "2026-05-31")

    def test_remote_fit_sync_returns_json_parse_code(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(garmin_sync, "download_fit_json", side_effect=garmin_sync.GarminJsonParseError("Garmin JSON 解析失败")):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["data"]["provider_error_code"], "garmin_json_parse_error")
        self.assertIn("返回格式异常", result["data"]["action_hint"])

    def test_remote_fit_sync_fails_when_local_import_fails_but_preserves_download_summary(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": True,
            "downloaded": 1,
            "skipped": 0,
            "failed": 0,
            "files": [{"activity_id": "100", "status": "downloaded"}],
            "errors": [],
        }
        import_result = {"ok": False, "error": "数据库写入失败", "inserted": 0, "errors": [{"file": "a.fit"}]}
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(garmin_sync, "download_fit_json", return_value=download_summary), \
             mock.patch.object(api, "sync_local_fit_files", return_value=import_result):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["data"]["provider_error_code"], "garmin_import_failed")
        self.assertEqual(result["data"]["download"], download_summary)
        self.assertEqual(result["data"]["import"], import_result)
        self.assertIn("下载", result["error"])
        self.assertIn("导入", result["data"]["action_hint"])

    def test_remote_fit_sync_unknown_exception_has_stable_provider_code(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(garmin_sync, "download_fit_json", side_effect=RuntimeError("boom")):
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["data"]["provider"], "garmin")
        self.assertEqual(result["data"]["provider_error_code"], "unknown")
        self.assertIn("未知异常", result["data"]["action_hint"])

    def test_remote_fit_sync_downloads_coros_fit_and_imports_without_openclaw(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": True,
            "provider": "coros",
            "region": "cn",
            "output_dir": main.TRACKS_DIR,
            "mode": "date_range",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "searched": 1,
            "downloaded": 1,
            "skipped": 0,
            "failed": 0,
            "limit": 10,
            "files": [{"file": "coros.fit", "status": "downloaded"}],
            "errors": [],
        }
        import_result = {"ok": True, "inserted": 1, "updated": 0, "skipped": 0, "errors": []}
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
            "coros_region": "cn",
        }), mock.patch.object(llm_backend, "chat_completions") as chat_mock, \
             mock.patch.object(garmin_sync, "download_fit_json") as garmin_download_mock, \
             mock.patch.object(coros_sync, "download_fit_json", return_value=download_summary) as coros_download_mock, \
             mock.patch.object(api, "sync_local_fit_files", return_value=import_result) as import_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertTrue(result["ok"], result)
        coros_download_mock.assert_called_once_with(
            start_date="2026-05-01",
            end_date="2026-05-31",
            output_dir=main.TRACKS_DIR,
            region="cn",
            limit=10,
        )
        import_mock.assert_called_once_with()
        chat_mock.assert_not_called()
        garmin_download_mock.assert_not_called()
        self.assertEqual(result["data"]["download"], download_summary)
        self.assertEqual(result["data"]["import"], import_result)

    def test_remote_fit_sync_skips_local_scan_when_coros_returns_no_fit_files(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": True,
            "provider": "coros",
            "region": "cn",
            "output_dir": main.TRACKS_DIR,
            "mode": "date_range",
            "start_date": "2026-06-25",
            "end_date": "2026-06-25",
            "searched": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "limit": 10,
            "files": [],
            "errors": [{"status": "failed", "error": "COROS MCP 未返回可下载的 FIT 文件或 URL"}],
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
            "coros_region": "cn",
        }), mock.patch.object(coros_sync, "download_fit_json", return_value=download_summary) as coros_download_mock, \
             mock.patch.object(api, "sync_local_fit_files") as import_mock:
            result = api.sync_remote_fit_activities("2026-06-25", "2026-06-25")

        self.assertTrue(result["ok"], result)
        coros_download_mock.assert_called_once()
        import_mock.assert_not_called()
        self.assertEqual(result["data"]["download"], download_summary)
        self.assertTrue(result["data"]["import"]["remote_import_skipped"])
        self.assertEqual(result["data"]["import"]["scanned"], 0)
        self.assertIn("未返回可下载", result["data"]["import"]["message"])

    def test_remote_fit_sync_returns_failure_when_coros_records_exist_but_fit_download_fails(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": False,
            "provider": "coros",
            "region": "cn",
            "output_dir": main.TRACKS_DIR,
            "mode": "date_range",
            "strategy": "sport_records_url",
            "start_date": "2026-06-22",
            "end_date": "2026-07-02",
            "searched": 1,
            "downloaded": 0,
            "skipped": 0,
            "failed": 1,
            "limit": 10,
            "files": [],
            "errors": [{"status": "failed", "labelId": "478587344962748420", "error": "未返回 FIT blob 或下载 URL"}],
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
            "coros_region": "cn",
        }), mock.patch.object(coros_sync, "download_fit_json", return_value=download_summary), \
             mock.patch.object(api, "sync_local_fit_files") as import_mock:
            result = api.sync_remote_fit_activities("2026-06-22", "2026-07-02")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], main.API_CODE_EXTERNAL_SERVICE)
        self.assertEqual(result["data"]["provider"], "coros")
        self.assertEqual(result["data"]["provider_error_code"], "coros_fit_download_failed")
        self.assertEqual(result["data"]["download"], download_summary)
        import_mock.assert_not_called()

    def test_remote_fit_sync_surfaces_coros_daily_fit_download_limit(self):
        api = object.__new__(main.Api)
        download_summary = {
            "ok": False,
            "provider": "coros",
            "region": "cn",
            "output_dir": main.TRACKS_DIR,
            "mode": "date_range",
            "strategy": "sport_records_url",
            "start_date": "2026-06-22",
            "end_date": "2026-07-02",
            "searched": 2,
            "downloaded": 0,
            "skipped": 0,
            "failed": 2,
            "limit": 10,
            "files": [],
            "errors": [{"status": "failed", "error": "Daily FIT download limit reached"}],
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
            "coros_region": "cn",
        }), mock.patch.object(coros_sync, "download_fit_json", return_value=download_summary), \
             mock.patch.object(api, "sync_local_fit_files") as import_mock:
            result = api.sync_remote_fit_activities("2026-06-22", "2026-07-02")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["code"], main.API_CODE_EXTERNAL_SERVICE)
        self.assertEqual(result["data"]["provider"], "coros")
        self.assertEqual(result["data"]["provider_error_code"], "coros_fit_daily_download_limit")
        self.assertIn("Daily FIT download limit reached", result["data"]["provider_detail"])
        self.assertIn("Daily FIT download limit reached", result["data"]["message"])
        self.assertIn("Daily FIT download limit reached", result["msg"])
        self.assertEqual(result["data"]["download"], download_summary)
        import_mock.assert_not_called()

    def test_remote_fit_sync_rejects_empty_brand_without_calling_openclaw(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "",
        }), mock.patch.object(llm_backend, "chat_completions") as chat_mock, \
             mock.patch.object(garmin_sync, "download_fit_json") as download_mock, \
             mock.patch.object(coros_sync, "download_fit_json") as coros_download_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertIn("暂不支持按时间同步活动", result["error"])
        chat_mock.assert_not_called()
        download_mock.assert_not_called()
        coros_download_mock.assert_not_called()

    def _fetch_coros_persona_with_payload(self, payload):
        return self._fetch_persona_with_payload("coros", payload)

    def _metric_array_from_dict(self, payload):
        if isinstance(payload, list):
            return payload
        return [{"metric": key, "value": value} for key, value in payload.items()]

    def _fetch_persona_with_payload(self, platform, payload):
        profile_backend.write_sync_state({})
        if platform == "garmin":
            with mock.patch.object(garmin_sync, "sync_profile_json", return_value=payload) as sync_mock, \
                 mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "global"}), \
                 mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("Garmin profile sync must not call LLM")):
                result = profile_backend.fetch_mcp_persona(platform)
            sync_mock.assert_called_once_with(region="global")
            return result
        payload_array = self._metric_array_from_dict(payload)
        with mock.patch.object(coros_sync, "sync_profile_json", return_value=payload_array) as sync_mock, \
             mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "eu"}), \
             mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("COROS profile sync must not call LLM")), \
             mock.patch.object(llm_backend, "test_llm_connection", side_effect=AssertionError("COROS profile sync must not test LLM connection")):
            result = profile_backend.fetch_mcp_persona(platform)
        sync_mock.assert_called_once_with(region="eu")
        return result

    def test_garmin_persona_maps_7d_recovery_fields(self):
        payload = [
            {"metric": "username", "value": "garmin-user"},
            {"metric": "resting_heart_rate", "value": 52},
            {"metric": "hrv", "value": 56.4},
            {"metric": "avg_sleep_hours", "value": 6.7},
        ]

        result = self._fetch_persona_with_payload("garmin", payload)

        self.assertTrue(result["ok"], result)
        profile = profile_backend.get_profile().to_dict()
        self.assertEqual(profile["hrv_baseline"], 56.4)
        self.assertEqual(profile["recent_hrv"], 56.4)
        self.assertEqual(profile["hrv_7d_avg"], 56.4)
        self.assertEqual(profile["resting_hr"], 52)
        self.assertEqual(profile["recent_resting_hr"], 52)
        self.assertEqual(profile["resting_hr_7d_avg"], 52)

    def test_garmin_persona_provider_failure_marks_sync_failed(self):
        profile_backend.write_sync_state({})
        with mock.patch.object(garmin_sync, "sync_profile_json", side_effect=garmin_sync.GarminSyncError("请先登录 Garmin")), \
             mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("Garmin profile sync must not call LLM")):
            result = profile_backend.fetch_mcp_persona("garmin")

        self.assertFalse(result["ok"], result)
        self.assertIn("请先登录 Garmin", result["error"])
        state = profile_backend.read_sync_state()
        self.assertEqual(state.get("last_attempt_status"), "failed_retryable")
        self.assertIn("请先登录 Garmin", state.get("last_error") or "")

    def test_coros_persona_provider_auth_failure_marks_sync_failed_without_llm(self):
        profile_backend.write_sync_state({})
        with mock.patch.object(coros_sync, "sync_profile_json", side_effect=coros_sync.CorosAuthRequiredError("missing_token")), \
             mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "cn"}), \
             mock.patch.object(llm_backend, "chat_completions", side_effect=AssertionError("COROS profile sync must not call LLM")):
            result = profile_backend.fetch_mcp_persona("coros")

        self.assertFalse(result["ok"], result)
        self.assertIn("配置页完成授权", result["error"])
        state = profile_backend.read_sync_state()
        self.assertEqual(state.get("last_attempt_status"), "auth_required")
        self.assertIn("配置页完成授权", state.get("last_error") or "")
        self.assertEqual(result["provider"], "coros")
        self.assertEqual(result["provider_error_code"], "coros_auth_required")
        self.assertIn("action_hint", result)

    def test_garmin_persona_provider_auth_failure_marks_auth_required(self):
        profile_backend.write_sync_state({})
        with mock.patch.object(garmin_sync, "sync_profile_json", side_effect=garmin_sync.GarminAuthRequiredError("missing_token")), \
             mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}):
            result = profile_backend.fetch_mcp_persona("garmin")

        self.assertFalse(result["ok"], result)
        state = profile_backend.read_sync_state()
        self.assertEqual(state.get("last_attempt_status"), "auth_required")
        self.assertEqual(result["provider_error_code"], "garmin_auth_required")

    def test_profile_sync_retryable_failure_retries_after_cooldown(self):
        old_attempt = (datetime.now() - profile_backend.timedelta(seconds=profile_backend.PROFILE_SYNC_RETRY_COOLDOWN_SEC + 5)).isoformat()
        profile_backend.write_sync_state({
            "last_attempt_status": "failed_retryable",
            "last_attempt_at": old_attempt,
            "last_error": "temporary timeout",
        })

        self.assertFalse(profile_backend.should_skip_profile_sync_for_cooldown())

    def test_api_fetch_coros_persona_failure_preserves_provider_code(self):
        profile_backend.write_sync_state({})
        with mock.patch.object(coros_sync, "sync_profile_json", side_effect=coros_sync.CorosAuthRequiredError("missing_token")), \
             mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "eu"}):
            result = self.api.fetch_mcp_persona("coros")

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["provider"], "coros")
        self.assertEqual(result["provider_error_code"], "coros_auth_required")
        self.assertIn("profile_sync_summary", result)

    def test_persona_dict_maps_7d_recovery_fields(self):
        payload = {
            "username": "persona-user",
            "resting_heart_rate": 51,
            "hrv": 58.2,
            "avg_sleep_hours": 7.1,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        profile = profile_backend.get_profile().to_dict()
        self.assertEqual(profile["hrv_baseline"], 58.2)
        self.assertEqual(profile["recent_hrv"], 58.2)
        self.assertEqual(profile["hrv_7d_avg"], 58.2)
        self.assertEqual(profile["resting_hr"], 51)
        self.assertEqual(profile["recent_resting_hr"], 51)
        self.assertEqual(profile["resting_hr_7d_avg"], 51)

    def test_recovery_detail_consumes_synced_recent_fields(self):
        from utils.metrics_calc import RadarScoreEngine

        payload = [
            {"metric": "username", "value": "garmin-user"},
            {"metric": "resting_heart_rate", "value": 52},
            {"metric": "hrv", "value": 56.4},
            {"metric": "avg_sleep_hours", "value": 6.7},
        ]
        result = self._fetch_persona_with_payload("garmin", payload)
        self.assertTrue(result["ok"], result)

        detail = RadarScoreEngine.score_recovery_detail(
            profile_backend.get_profile().to_dict(),
            {"tsb": -5, "atl": 40},
        )

        self.assertEqual(detail["source"], "hrv_trend")
        self.assertNotIn("缺少近期 HRV", "；".join(detail["reasons"]))
        self.assertNotIn("缺少近期静息心率对比", "；".join(detail["reasons"]))

    def test_upsert_profile_persists_recent_recovery_fields(self):
        profile_backend.upsert_profile({
            "name": "db-user",
            "resting_hr": 50,
            "recent_resting_hr": 53,
            "resting_hr_7d_avg": 53,
            "hrv_baseline": 60.0,
            "recent_hrv": 55.5,
            "hrv_7d_avg": 55.5,
            "avg_sleep_hours": 7.2,
        })

        profile = profile_backend.get_profile().to_dict()

        self.assertEqual(profile["resting_hr"], 50)
        self.assertEqual(profile["recent_resting_hr"], 53)
        self.assertEqual(profile["resting_hr_7d_avg"], 53)
        self.assertEqual(profile["hrv_baseline"], 60.0)
        self.assertEqual(profile["recent_hrv"], 55.5)
        self.assertEqual(profile["hrv_7d_avg"], 55.5)

    def test_coros_persona_maps_full_training_hub_payload(self):
        payload = {
            "username": "户外大叔MrFang",
            "age": 46,
            "gender": "男",
            "height_cm": 170.0,
            "weight_kg": 73.8,
            "body_fat_percent": None,
            "body_water_percent": None,
            "bone_mass_kg": None,
            "muscle_mass_kg": None,
            "resting_heart_rate": 52,
            "max_heart_rate": 187,
            "hrv": None,
            "avg_sleep_hours": None,
            "avg_bedtime": None,
            "vo2_max": 45,
            "lactate_threshold_hr": 166,
            "lactate_threshold_pace": "05'12\"",
            "ftp_watts": None,
            "1km_pb": "00:04:18",
            "5km_pb": "00:27:18",
            "10km_pb": "01:04:00",
            "half_marathon_pb": None,
            "full_marathon_pb": None,
            "longest_run_km": 21.46,
            "total_run_km": 33.92,
            "race_predict_5k": "00:24:59",
            "race_predict_10k": "00:52:17",
            "race_predict_half": "01:57:51",
            "race_predict_full": "04:10:05",
            "longest_hike_km": None,
            "total_hike_km": None,
            "longest_ride_time": None,
            "cycling_40km_time": None,
            "cycling_80km_time": None,
            "longest_cycle_km": 29.98,
            "total_cycle_km": None,
            "longest_swim_distance_m": None,
            "total_swim_km": None,
            "swimming_100m_pb": None,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        persona = result["persona"]
        self.assertEqual(persona["name"], "户外大叔MrFang")
        self.assertEqual(persona["age"], 46)
        self.assertEqual(persona["gender"], "男")
        self.assertEqual(persona["height_cm"], 170.0)
        self.assertEqual(persona["weight"], 73.8)
        self.assertEqual(persona["resting_hr"], 52)
        self.assertEqual(persona["max_hr"], 187)
        self.assertEqual(persona["vo2max"], 45)
        self.assertEqual(persona["lactate_threshold_hr"], 166)
        self.assertEqual(persona["lactate_threshold_pace"], "05'12\"")
        self.assertEqual(persona["pb_1km"], "00:04:18")
        self.assertEqual(persona["pb_5km"], "🏆 00:27:18｜📈 00:24:59")
        self.assertEqual(persona["pb_10km"], "🏆 01:04:00｜📈 00:52:17")
        self.assertEqual(persona["pb_half_marathon"], "📈 01:57:51")
        self.assertEqual(persona["pb_full_marathon"], "📈 04:10:05")
        self.assertEqual(persona["longest_run_km"], 21.46)
        self.assertEqual(persona["total_run_km"], 33.92)
        self.assertEqual(persona["longest_cycle_km"], 29.98)

    def test_coros_persona_maps_supported_alias_fields_to_canonical_profile(self):
        payload = [
            {"metric": "name", "value": "alias-user"},
            {"metric": "nickname", "value": "ignored-when-name-present"},
            {"metric": "gender", "value": "男"},
            {"metric": "age", "value": 46},
            {"metric": "height_cm", "value": 170},
            {"metric": "weight", "value": 73.8},
            {"metric": "resting_hr", "value": 52},
            {"metric": "maximum_heart_rate", "value": 187},
            {"metric": "vo2max", "value": 45},
            {"metric": "lactate_threshold_hr", "value": 166},
            {"metric": "body_fat_pct", "value": 18.5},
            {"metric": "body_water_pct", "value": 55.0},
            {"metric": "bone_mass", "value": 3.1},
            {"metric": "muscle_mass", "value": 54.2},
            {"metric": "pb_1km", "value": "00:04:18"},
            {"metric": "pb_5km", "value": "00:27:18"},
            {"metric": "pb_10km", "value": "01:04:00"},
            {"metric": "pb_half_marathon", "value": "01:57:51"},
            {"metric": "pb_full_marathon", "value": "04:10:05"},
            {"metric": "ftp", "value": 230},
        ]

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        persona = result["persona"]
        self.assertEqual(persona["name"], "alias-user")
        self.assertEqual(persona["weight"], 73.8)
        self.assertEqual(persona["resting_hr"], 52)
        self.assertEqual(persona["max_hr"], 187)
        self.assertEqual(persona["vo2max"], 45)
        self.assertEqual(persona["lactate_threshold_hr"], 166)
        self.assertEqual(persona["body_fat_pct"], 18.5)
        self.assertEqual(persona["body_water_pct"], 55.0)
        self.assertEqual(persona["bone_mass"], 3.1)
        self.assertEqual(persona["muscle_mass"], 54.2)
        self.assertEqual(persona["pb_1km"], "00:04:18")
        self.assertEqual(persona["pb_5km"], "🏆 00:27:18")
        self.assertEqual(persona["pb_10km"], "🏆 01:04:00")
        self.assertEqual(persona["pb_half_marathon"], "🏆 01:57:51")
        self.assertEqual(persona["pb_full_marathon"], "🏆 04:10:05")
        self.assertEqual(persona["ftp"], 230)
        self.assertEqual(persona["ftp_watts"], 230)
        self.assertEqual(result["profile_sync_summary"]["data_quality"], "complete_for_analysis")

    def test_coros_persona_preserves_existing_max_hr_when_missing(self):
        profile_backend.upsert_profile({
            "name": "old",
            "gender": "男",
            "age": 45,
            "weight": 72.0,
            "resting_hr": 55,
            "max_hr": 191,
            "vo2max": 44,
        })
        payload = {
            "username": "new",
            "age": 46,
            "gender": "男",
            "weight_kg": 73.8,
            "resting_heart_rate": 52,
            "vo2_max": 45,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["persona"]["max_hr"], 191)
        summary = result["profile_sync_summary"]
        self.assertIn("max_hr", summary["preserved_fields"])
        self.assertNotIn("max_hr", summary["updated_fields"])

    def test_coros_persona_reports_synced_max_hr_as_updated_not_preserved(self):
        profile_backend.upsert_profile({
            "name": "old",
            "gender": "男",
            "age": 45,
            "weight": 72.0,
            "resting_hr": 55,
            "max_hr": 191,
            "vo2max": 44,
            "lactate_threshold_hr": 165,
        })
        payload = {
            "username": "new",
            "age": 46,
            "gender": "男",
            "weight_kg": 73.8,
            "resting_heart_rate": 52,
            "max_heart_rate": 187,
            "vo2_max": 45,
            "lactate_threshold_hr": 166,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["persona"]["max_hr"], 187)
        summary = result["profile_sync_summary"]
        self.assertIn("max_hr", summary["updated_fields"])
        self.assertNotIn("max_hr", summary["preserved_fields"])

    def test_coros_persona_does_not_null_supported_fields(self):
        payload = {
            "username": "coros",
            "height_cm": 170,
            "5km_pb": "00:27:18",
            "10km_pb": "01:04:00",
            "lactate_threshold_hr": 166,
            "ftp_watts": 230,
            "cycling_40km_time": "01:20:00",
            "cycling_80km_time": "02:50:00",
            "body_fat_percent": 18.5,
            "body_water_percent": 55.0,
            "bone_mass_kg": 3.1,
            "muscle_mass_kg": 54.2,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        persona = result["persona"]
        self.assertEqual(persona["height_cm"], 170)
        self.assertEqual(persona["pb_5km"], "🏆 00:27:18")
        self.assertEqual(persona["pb_10km"], "🏆 01:04:00")
        self.assertEqual(persona["lactate_threshold_hr"], 166)
        self.assertEqual(persona["ftp"], 230)
        self.assertEqual(persona["ftp_watts"], 230)
        self.assertEqual(persona["cycling_40km_time"], "01:20:00")
        self.assertEqual(persona["cycling_80km_time"], "02:50:00")
        self.assertEqual(persona["body_fat_pct"], 18.5)
        self.assertEqual(persona["body_water_pct"], 55.0)
        self.assertEqual(persona["bone_mass"], 3.1)
        self.assertEqual(persona["muscle_mass"], 54.2)

    def test_coros_persona_tolerates_partial_payload(self):
        result = self._fetch_coros_persona_with_payload({"username": "partial"})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["persona"]["name"], "partial")
        self.assertIsNone(result["persona"]["resting_hr"])
        self.assertIsNone(result["persona"]["max_hr"])

    def test_profile_sync_uses_single_profile_and_preserves_missing_fields_across_brand_switch(self):
        profile_backend.upsert_profile({
            "name": "garmin-user",
            "gender": "男",
            "age": 45,
            "height_cm": 169,
            "weight": 72.0,
            "resting_hr": 55,
            "max_hr": 186,
            "vo2max": 44,
            "lactate_threshold_hr": 165,
            "pb_5km": "🏆 00:28:00",
            "hrv_baseline": 62,
        })
        payload = {
            "username": "coros-user",
            "age": 46,
            "weight_kg": 73.8,
            "max_heart_rate": None,
            "resting_heart_rate": None,
            "vo2_max": 45,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        profile = profile_backend.get_profile().to_dict()
        self.assertEqual(profile["name"], "coros-user")
        self.assertEqual(profile["age"], 46)
        self.assertEqual(profile["weight"], 73.8)
        self.assertEqual(profile["vo2max"], 45)
        self.assertEqual(profile["max_hr"], 186)
        self.assertEqual(profile["resting_hr"], 55)
        self.assertEqual(profile["height_cm"], 169)
        self.assertEqual(profile["lactate_threshold_hr"], 165)
        self.assertEqual(profile["pb_5km"], "🏆 00:28:00")
        self.assertEqual(profile["hrv_baseline"], 62)
        conn = profile_backend._conn()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM user_profile").fetchone()["c"]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_profile_snapshot_history_is_field_continuous_across_platforms(self):
        garmin_payload = [
            {"metric": "username", "value": "garmin-user"},
            {"metric": "age", "value": 45},
            {"metric": "gender", "value": "男"},
            {"metric": "weight_kg", "value": 72.0},
            {"metric": "resting_heart_rate", "value": 55},
            {"metric": "max_hr", "value": 186},
            {"metric": "vo2_max", "value": 44},
        ]
        coros_payload = {
            "username": "coros-user",
            "weight_kg": 73.8,
            "resting_heart_rate": 52,
            "max_heart_rate": 187,
            "vo2_max": 45,
        }

        first = self._fetch_persona_with_payload("garmin", garmin_payload)
        second = self._fetch_persona_with_payload("coros", coros_payload)

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        conn = profile_backend._conn()
        try:
            rows = conn.execute(
                """
                SELECT source_platform, normalized_json
                FROM user_profile_snapshots
                ORDER BY id ASC
                """
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual([row["source_platform"] for row in rows], ["garmin", "coros"])
        max_hr_history = [json.loads(row["normalized_json"])["max_hr"] for row in rows]
        self.assertEqual(max_hr_history, [186, 187])

    def test_profile_data_quality_complete_for_analysis_without_hrv_sleep_or_body_composition(self):
        quality, missing = profile_backend._profile_data_quality({
            "name": "coros",
            "resting_hr": 52,
            "max_hr": 187,
            "weight": 73.8,
            "vo2max": 45,
            "lactate_threshold_hr": 166,
            "hrv_baseline": None,
            "avg_sleep_hours": None,
            "body_fat_pct": None,
            "ftp_watts": None,
        })

        self.assertEqual(quality, "complete_for_analysis")
        self.assertEqual(missing, [])

    def test_profile_data_quality_display_only_for_identity_payload(self):
        quality, missing = profile_backend._profile_data_quality({
            "name": "coros-display",
            "age": 46,
            "gender": "男",
            "height_cm": 170,
            "resting_hr": None,
            "max_hr": None,
            "weight": None,
            "vo2max": None,
            "lactate_threshold_hr": None,
        })

        self.assertEqual(quality, "display_only")
        self.assertEqual(missing, ["resting_hr", "max_hr", "weight", "vo2max", "lactate_threshold_hr"])

    def test_profile_sync_summary_reports_updated_and_preserved_fields(self):
        profile_backend.upsert_profile({
            "name": "garmin-user",
            "gender": "男",
            "age": 45,
            "height_cm": 169,
            "weight": 72.0,
            "resting_hr": 55,
            "max_hr": 186,
            "vo2max": 44,
            "lactate_threshold_hr": 165,
            "hrv_baseline": 62,
        })
        payload = {
            "username": "coros-user",
            "weight_kg": 73.8,
            "vo2_max": 45,
            "max_heart_rate": None,
            "resting_heart_rate": None,
            "lactate_threshold_hr": None,
        }

        result = self._fetch_coros_persona_with_payload(payload)

        self.assertTrue(result["ok"], result)
        summary = result["profile_sync_summary"]
        self.assertIn("weight", summary["updated_fields"])
        self.assertIn("vo2max", summary["updated_fields"])
        self.assertIn("max_hr", summary["preserved_fields"])
        self.assertIn("resting_hr", summary["preserved_fields"])
        self.assertIn("lactate_threshold_hr", summary["preserved_fields"])
        self.assertEqual(summary["data_quality"], "complete_for_analysis")
        self.assertFalse(summary["supports_remote_activity_sync"])

    def test_user_profile_api_returns_coros_sync_summary_without_dual_profile(self):
        profile_backend.upsert_profile({
            "name": "garmin-user",
            "gender": "男",
            "age": 45,
            "weight": 72.0,
            "resting_hr": 55,
            "max_hr": 186,
            "vo2max": 44,
            "lactate_threshold_hr": 165,
        })
        payload = {
            "username": "coros-user",
            "weight_kg": 73.8,
            "vo2_max": 45,
            "resting_heart_rate": None,
            "max_heart_rate": None,
        }
        self._fetch_coros_persona_with_payload(payload)

        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "watch_brand": "coros",
        }):
            response = self.api.get_user_profile()

        self.assertTrue(response["ok"], response)
        self.assertEqual(response["current_watch_brand"], "coros")
        self.assertEqual(response["current_profile_source_platform"], "coros")
        self.assertFalse(response["supports_remote_activity_sync"])
        self.assertIn("本地 FIT", response["activity_sync_hint"])
        self.assertIn("max_hr", response["preserved_fields"])
        self.assertIn("resting_hr", response["preserved_fields"])
        self.assertIn("weight", response["updated_fields"])
        self.assertEqual(response["data_quality"], "complete_for_analysis")
        self.assertNotIn("hrv_baseline", response["missing_fields"])
        conn = profile_backend._conn()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM user_profile").fetchone()["c"]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_energy_risk_consumes_unified_profile_fields(self):
        from metrics_resolver import MetricsResolver
        distance_curve = [i * 350.0 for i in range(121)]
        result = MetricsResolver._energy_reserve_risk_layer(
            distance_curve=distance_curve,
            time_curve=[i * 180.0 for i in range(121)],
            total_calories=2600.0,
            sport_type="running",
            weight_kg=73.8,
            avg_hr=158,
            profile_max_hr=187,
            profile_resting_hr=52,
            lactate_threshold_hr=166,
            vo2max=45,
        )

        self.assertNotEqual(result["confidence"], "unavailable")
        factors = result["factors"]
        self.assertTrue(any(str(f).startswith("kcal_per_kg=") for f in factors))
        self.assertTrue(any(str(f).startswith("hrr_ratio=") for f in factors))
        self.assertTrue(any(str(f).startswith("threshold_ratio=") for f in factors))
        self.assertTrue(any(str(f).startswith("vo2max=") for f in factors))

    def test_training_load_uses_unified_profile_hrr(self):
        from metrics_resolver import MetricsResolver
        result = MetricsResolver._compute_training_load(
            avg_hr=158,
            duration_sec=3600,
            profile_max_hr=187,
            profile_resting_hr=52,
        )

        self.assertIsNotNone(result["load"])
        self.assertIsNotNone(result["zone_used"])
        self.assertNotEqual(result["confidence"], "unavailable")

    def test_trimp_uses_unified_user_profile_not_default_path(self):
        from datetime import datetime, timedelta
        from utils.metrics_calc import AdvancedMetricsCalc
        start = datetime(2026, 5, 19, 8, 0, 0)
        records = [
            {"timestamp": start + timedelta(minutes=i), "heart_rate": 150 + (i % 4)}
            for i in range(60)
        ]

        coros_profile = {"gender": "男", "age": 46, "resting_hr": 52, "max_hr": 187}
        trimp = AdvancedMetricsCalc.calculate_trimp(records, coros_profile)
        default_trimp = AdvancedMetricsCalc.calculate_trimp(records, {})

        self.assertGreater(trimp, 0)
        self.assertNotEqual(trimp, default_trimp)

    def test_algorithm_records_prefer_fit_record_distance(self):
        from metrics_resolver import MetricsResolver
        from utils.metrics_calc import AdvancedMetricsCalc

        track_data = [
            {"lat": 30.0, "lon": 104.0, "alt": 100.0, "time": "2026-05-19T00:00:00Z", "distance": 0.0},
            {"lat": 30.0, "lon": 104.0, "alt": 105.0, "time": "2026-05-19T00:00:30Z", "distance": 75.0},
            {"lat": 30.0, "lon": 104.0, "alt": 110.0, "time": "2026-05-19T00:01:00Z", "distance": 150.0},
            {"lat": 30.0, "lon": 104.0, "alt": 115.0, "time": "2026-05-19T00:01:30Z", "distance": 225.0},
            {"lat": 30.0, "lon": 104.0, "alt": 120.0, "time": "2026-05-19T00:02:00Z", "distance": 300.0},
        ]

        records = MetricsResolver._convert_track_to_algorithm_records(track_data)

        self.assertEqual(records[-1]["distance"], 300.0)
        self.assertGreater(AdvancedMetricsCalc.calculate_vam(records), 0)

    def test_algorithm_records_without_distance_keep_legacy_zero_vam_behavior(self):
        from metrics_resolver import MetricsResolver
        from utils.metrics_calc import AdvancedMetricsCalc

        track_data = [
            {"lat": 30.0, "lon": 104.0, "alt": 100.0, "time": "2026-05-19T00:00:00Z"},
            {"lat": 30.0, "lon": 104.0, "alt": 105.0, "time": "2026-05-19T00:00:30Z"},
            {"lat": 30.0, "lon": 104.0, "alt": 110.0, "time": "2026-05-19T00:01:00Z"},
            {"lat": 30.0, "lon": 104.0, "alt": 115.0, "time": "2026-05-19T00:01:30Z"},
            {"lat": 30.0, "lon": 104.0, "alt": 120.0, "time": "2026-05-19T00:02:00Z"},
        ]

        records = MetricsResolver._convert_track_to_algorithm_records(track_data)

        self.assertEqual(AdvancedMetricsCalc.calculate_vam(records), 0.0)

    def test_pick_and_import_fit_files_starts_background_import_job(self):
        selected = [str(self.temp_dir / "manual.fit")]
        fake_window = mock.Mock()
        fake_window.create_file_dialog.return_value = selected
        fake_file_dialog = types.SimpleNamespace(OPEN="open")
        fake_webview = types.SimpleNamespace(windows=[fake_window], FileDialog=fake_file_dialog)
        start_result = {
            "ok": True,
            "job_id": "import-job-1",
            "already_running": False,
            "status": {"state": "running"},
        }

        with mock.patch.dict("sys.modules", {
            "webview": fake_webview,
        }), mock.patch.object(self.api, "start_import_fit_files", return_value=start_result) as import_mock, \
             mock.patch.object(llm_backend, "chat_completions") as chat_mock:
            result = self.api.pick_and_import_fit_files()

        self.assertTrue(result["ok"], result)
        import_mock.assert_called_once_with(selected)
        self.assertEqual(result["data"]["job_id"], "import-job-1")
        self.assertEqual(result["data"]["status"], {"state": "running"})
        chat_mock.assert_not_called()

    def test_parse_fit_activity_for_sync_defers_region_enrichment(self):
        fit_path = self.temp_dir / "region.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "晨跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "unknown",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 8.5,
                "total_timer_time": 3000,
                "total_calories": 520,
                "total_ascent": 50.0,
                "max_altitude": 22.0,
                "avg_hr": 149,
                "max_hr": 171,
            },
            "track_data": [
                {"lat": 30.67, "lon": 104.06, "alt": 10.0, "time": "2026-05-19T00:00:00Z", "hr": 140},
                {"lat": 30.68, "lon": 104.07, "alt": 12.0, "time": "2026-05-19T00:05:00Z", "hr": 150},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(profile_backend, "resolve_activity_region", side_effect=AssertionError("地区查询不应阻塞 FIT 入库")):
            activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(activity["region"], "")
        self.assertEqual(activity["region_status"], "pending")
        self.assertEqual(activity["start_lat"], 30.67)
        self.assertEqual(activity["start_lon"], 104.06)
        self.assertEqual(activity["sport_type"], "running")

    def test_parse_fit_activity_for_sync_marks_no_gps_as_none(self):
        fit_path = self.temp_dir / "indoor.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "室内骑行",
                "title_source": "sport_name",
                "sport": "cycling",
                "sub_sport": "indoor_cycling",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 20.0,
                "total_timer_time": 3600,
            },
            "track_data": [
                {"time": "2026-05-19T00:00:00Z", "hr": 120},
                {"time": "2026-05-19T00:05:00Z", "hr": 130},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(profile_backend, "resolve_activity_region", side_effect=AssertionError("无 GPS 不应查询地区")):
            activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(activity["region_status"], "none")
        self.assertEqual(activity["region_display"], "室内运动")
        self.assertEqual(activity["region"], "室内运动（无GPS）")

    def test_parse_fit_activity_for_sync_replaces_coros_technical_filename_title(self):
        fit_path = self.temp_dir / "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "sport": "running",
                "sub_sport": "generic",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 5.5,
                "total_timer_time": 2100,
            },
            "track_data": [
                {"lat": 39.90, "lon": 116.40, "alt": 40.0, "time": "2026-05-19T00:00:00Z", "hr": 130},
                {"lat": 39.91, "lon": 116.41, "alt": 42.0, "time": "2026-05-19T00:05:00Z", "hr": 135},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core):
            activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(activity["title"], "跑步")
        self.assertEqual(activity["title_source"], "auto_sport")

    def test_parse_fit_activity_for_sync_persists_canonical_normalized_power(self):
        fit_path = self.temp_dir / "np.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "功率跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "generic",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 7.0,
                "total_timer_time": 2946,
                "total_calories": 552,
                "total_ascent": 10.0,
                "max_altitude": 72.0,
                "avg_hr": 157,
                "max_hr": 174,
                "avg_power": 239,
                "max_power": 402,
                "normalized_power": 254,
            },
            "track_data": [
                {"lat": 39.9, "lon": 116.3, "alt": 70.0, "time": "2026-05-19T00:00:00Z", "hr": 150, "power": 220},
                {"lat": 39.91, "lon": 116.31, "alt": 71.0, "time": "2026-05-19T00:00:01Z", "hr": 152, "power": 260},
            ],
            "lap_data": [{"normalized_power": 250, "total_timer_time": 600}],
        }
        fake_resolved_without_storage_model = {
            "hr_curve": [150, 152],
            "speed_curve": [2.4, 2.5],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(main.FITCoreEngine, "parse_fit_file_raw", return_value={"raw": {}, "meta": {}}), \
             mock.patch.object(main.MetricsResolver, "resolve", return_value=fake_resolved_without_storage_model), \
             mock.patch.object(profile_backend, "resolve_activity_region", return_value=""):
            activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(activity["normalized_power"], 254)
        self.assertEqual(activity["avg_power"], 239)
        self.assertEqual(activity["max_power"], 402)

    def test_parse_fit_activity_for_sync_computes_vam_from_fit_distance(self):
        fit_path = self.temp_dir / "climb.fit"
        fit_path.write_bytes(b"fit")
        climb_points = [
            {"lat": 30.0, "lon": 104.0, "alt": 100.0, "time": "2026-05-19T00:00:00Z", "hr": 140, "distance": 0.0},
            {"lat": 30.0, "lon": 104.0, "alt": 105.0, "time": "2026-05-19T00:00:30Z", "hr": 145, "distance": 75.0},
            {"lat": 30.0, "lon": 104.0, "alt": 110.0, "time": "2026-05-19T00:01:00Z", "hr": 150, "distance": 150.0},
            {"lat": 30.0, "lon": 104.0, "alt": 115.0, "time": "2026-05-19T00:01:30Z", "hr": 155, "distance": 225.0},
            {"lat": 30.0, "lon": 104.0, "alt": 120.0, "time": "2026-05-19T00:02:00Z", "hr": 160, "distance": 300.0},
        ]
        fake_core = {
            "basic_info": {
                "title": "爬坡骑行",
                "title_source": "sport_name",
                "sport": "cycling",
                "sub_sport": "generic",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 0.3,
                "total_timer_time": 120,
                "total_calories": 50,
                "total_ascent": 20.0,
                "max_altitude": 120.0,
                "avg_hr": 150,
                "max_hr": 160,
            },
            "track_data": climb_points,
            "lap_data": [],
        }

        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(main.FITCoreEngine, "parse_fit_file_raw", return_value={"raw": {}, "meta": {}}), \
             mock.patch.object(main.MetricsResolver, "resolve", return_value={"storage_model": {}}), \
             mock.patch.object(profile_backend, "resolve_activity_region", return_value=""), \
             mock.patch.object(main, "fetch_historical_weather", return_value=None):
            activity = main._parse_fit_activity_for_sync(fit_path)

        advanced_metrics = json.loads(activity["advanced_metrics"])
        stored_points = json.loads(activity["track_json"])

        self.assertGreater(advanced_metrics["vam"], 0)
        self.assertEqual(stored_points[-1]["distance"], 300.0)

    def test_new_fit_sync_persists_canonical_power_and_stroke_distance_contract(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("canonical_metrics.fit")
        activity.update(
            {
                "sport_type": "stand_up_paddleboarding",
                "sub_sport_type": "generic",
                "avg_power": 116,
                "max_power": 302,
                "normalized_power": 128,
                "avg_stroke_distance": 2.35,
                "swolf": 2.35,
            }
        )

        persisted = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                """
                SELECT avg_power, max_power, normalized_power, avg_stroke_distance, swolf
                FROM activities
                WHERE id = ?
                """,
                (persisted["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["avg_power"], 116)
        self.assertEqual(row["max_power"], 302)
        self.assertEqual(row["normalized_power"], 128)
        self.assertAlmostEqual(row["avg_stroke_distance"], 2.35)
        self.assertAlmostEqual(row["swolf"], 2.35)
        detail = self.api.get_activity_detail(persisted["id"])
        self.assertTrue(detail["ok"], detail)
        record = detail["data"]["record"]
        self.assertTrue(record["detail"]["capabilities"]["has_power"])

    def test_persist_sync_activity_reuses_semantic_duplicate_with_different_file_identity(self):
        main.ensure_activity_sync_schema()
        points = self._duplicate_points()
        first = self._activity("2023-04-22_四姑娘山二峰登顶_mountaineering_8.34km.fit")
        first.update({
            "title": "2023-04-22_四姑娘山二峰登顶_mountaineering_8.34km",
            "sport_type": "mountaineering",
            "dist_km": 8.34,
            "distance": 8340.0,
            "duration": 26054,
            "duration_sec": 26054,
            "points": points,
            "points_json": json.dumps(points),
            "track_json": json.dumps(points),
        })
        second = self._activity("四姑娘山二峰登顶.fit")
        second.update({
            "title": "四姑娘山二峰登顶",
            "sport_type": "mountaineering",
            "dist_km": 8.34,
            "distance": 8340.0,
            "duration": 26054,
            "duration_sec": 26054,
            "points": list(points),
            "points_json": json.dumps(points),
            "track_json": json.dumps(points),
        })

        inserted = main._persist_sync_activity(first)
        updated = main._persist_sync_activity(second)

        conn = profile_backend._conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            row = conn.execute("SELECT id, title, file_name, filename FROM activities").fetchone()
        finally:
            conn.close()

        self.assertEqual(inserted["op"], "inserted")
        self.assertEqual(updated["op"], "updated")
        self.assertEqual(updated.get("dedupe"), "semantic")
        self.assertEqual(updated["id"], inserted["id"])
        self.assertEqual(count, 1)
        self.assertEqual(row["id"], inserted["id"])
        self.assertEqual(row["title"], "四姑娘山二峰登顶")

    def test_persist_sync_activity_allows_same_distance_at_different_start_time(self):
        main.ensure_activity_sync_schema()
        first_points = self._duplicate_points()
        second_points = [
            {**point, "time": point["time"].replace("08:", "10:")}
            for point in first_points
        ]
        first = self._activity("morning.fit")
        first.update({
            "start_time": "2026-05-19T08:00:00Z",
            "start_time_utc": "2026-05-19T08:00:00Z",
            "dist_km": 10.0,
            "distance": 10000.0,
            "duration": 3600,
            "duration_sec": 3600,
            "points": first_points,
            "points_json": json.dumps(first_points),
            "track_json": json.dumps(first_points),
        })
        second = self._activity("later.fit")
        second.update({
            "start_time": "2026-05-19T10:00:00Z",
            "start_time_utc": "2026-05-19T10:00:00Z",
            "dist_km": 10.0,
            "distance": 10000.0,
            "duration": 3600,
            "duration_sec": 3600,
            "points": second_points,
            "points_json": json.dumps(second_points),
            "track_json": json.dumps(second_points),
        })

        first_res = main._persist_sync_activity(first)
        second_res = main._persist_sync_activity(second)

        conn = profile_backend._conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(first_res["op"], "inserted")
        self.assertEqual(second_res["op"], "inserted")
        self.assertNotEqual(first_res["id"], second_res["id"])
        self.assertEqual(count, 2)

    def test_activity_list_item_does_not_parse_fit_for_missing_normalized_power(self):
        row = {
            "id": 1,
            "sport_type": "running",
            "sub_sport_type": "generic",
            "distance": 7000,
            "dist_km": 7.0,
            "duration": 2946,
            "duration_sec": 2946,
            "avg_pace": 420,
            "avg_hr": 157,
            "max_hr": 174,
            "calories": 552,
            "normalized_power": None,
            "file_path": str(self.temp_dir / "np.fit"),
            "filename": "np.fit",
            "file_name": "np.fit",
            "start_time": "2026-05-19T08:00:00+08:00",
            "region_status": "none",
        }
        api = main.Api()
        with mock.patch.object(
            main.FITCoreEngine,
            "parse_fit_file",
            side_effect=AssertionError("活动列表不应同步解析 FIT 文件"),
        ):
            item = api._build_activity_list_item(row)

        self.assertIsNone(item["normalized_power"])
        self.assertEqual(item["normalized_power_display"], "/")

    def test_activity_list_item_prefers_persisted_title_over_coros_technical_filename(self):
        row = {
            "id": 1,
            "title": "跑步",
            "title_source": "auto_sport",
            "sport_type": "running",
            "sub_sport_type": "generic",
            "distance": 5550,
            "dist_km": 5.55,
            "duration": 2283,
            "duration_sec": 2283,
            "avg_pace": 411,
            "avg_hr": 133,
            "max_hr": 148,
            "calories": 396,
            "normalized_power": 260,
            "file_path": str(self.temp_dir / "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit"),
            "filename": "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit",
            "file_name": "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit",
            "start_time": "2026-07-01T07:55:06+08:00",
            "region_status": "pending",
        }

        item = main.Api()._build_activity_list_item(row)

        self.assertEqual(item["title"], "跑步")
        self.assertEqual(item["title_source"], "auto_sport")
        self.assertEqual(item["file_name"], "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit")
        self.assertEqual(item["filename"], "coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit")

    def test_update_activity_title_marks_user_source_and_updates_detail(self):
        activity = self._activity("2026_chengdu_half_candidate.fit")
        activity["title"] = "成都市 跑步"
        activity["title_source"] = "auto_region_sport"
        persisted = main._persist_sync_activity(activity)

        res = self.api.update_activity_title(persisted["id"], "2026 成都半程马拉松")

        self.assertEqual(res["code"], 0, res)
        record = res["data"]["record"]
        self.assertEqual(record["title"], "2026 成都半程马拉松")
        self.assertEqual(record["title_source"], "user")

        detail = self.api.get_activity_detail(persisted["id"])
        self.assertEqual(detail["code"], 0, detail)
        self.assertEqual(detail["data"]["record"]["title"], "2026 成都半程马拉松")
        self.assertEqual(detail["data"]["record"]["title_source"], "user")

    def test_activity_list_and_detail_include_race_flag_fields(self):
        activity = self._activity("race_flag_visible.fit")
        activity["is_race"] = 1
        persisted = main._persist_sync_activity(activity)

        list_res = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")
        detail = self.api.get_activity_detail(persisted["id"])

        self.assertEqual(list_res["code"], 0, list_res)
        record = next(item for item in list_res["data"]["records"] if item["id"] == persisted["id"])
        self.assertTrue(record["is_race"])
        self.assertEqual(record["race_source"], "fit_sport_event")
        self.assertEqual(record["race_confidence"], "high")
        self.assertEqual(detail["code"], 0, detail)
        self.assertTrue(detail["data"]["record"]["is_race"])

    def test_js_api_contract_registers_refresh_activity_region(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("refresh_activity_region", methods)
        method = methods["refresh_activity_region"]
        self.assertEqual(method["category"], "activity")
        self.assertFalse(method["high_risk"])
        self.assertEqual(method["parameters"], [
            {"name": "activity_id", "type": "int", "required": True},
        ])
        for forbidden_surface in ("raw FIT", "points", "track_json", "file_path", "SQLite schema"):
            self.assertIn(forbidden_surface, method["description"])

    def test_js_api_contract_registers_region_enrichment_dry_run_as_readonly(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_region_enrichment_dry_run", methods)
        method = methods["get_region_enrichment_dry_run"]
        self.assertEqual(method["category"], "activity")
        self.assertTrue(method["readonly"])
        self.assertFalse(method["high_risk"])
        self.assertIn("不写 activities", method["description"])
        self.assertIn("不调用 Nominatim", method["description"])
        self.assertIn("不生成或刷新年度 AI 报告", method["description"])

    def test_activity_sync_schema_includes_device_mapping_registry(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            activity_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(activities)").fetchall()
            }
            mapping = conn.execute(
                "SELECT display_name FROM device_product_mappings WHERE vendor = 'garmin' AND product_key = 'garmin:3515'"
            ).fetchone()
        finally:
            conn.close()

        self.assertIn("device_product_mappings", tables)
        for col in ("device_vendor", "device_product_key", "device_product_id", "device_serial", "device_mapping_status"):
            self.assertIn(col, activity_cols)
        self.assertEqual(mapping["display_name"], "Fenix6 Asia")

    def test_persist_refreshes_unchanged_file_when_existing_device_is_fallback(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "device_refresh.fit"
        fit_path.write_bytes(b"x" * 32)
        stat = fit_path.stat()

        activity = self._activity(fit_path.name)
        activity["file_path"] = str(fit_path.resolve())
        activity["file_mtime"] = stat.st_mtime
        activity["file_size"] = stat.st_size
        activity["device_name"] = "Garmin Product 3515"
        activity["device_vendor"] = "garmin"
        activity["device_product_key"] = ""
        activity["device_product_id"] = "3515"
        activity["device_mapping_status"] = "unresolved"
        inserted = main._persist_sync_activity(activity)
        self.assertEqual(inserted["op"], "inserted")

        refreshed = dict(activity)
        refreshed["device_name"] = "Fenix6 Asia"
        refreshed["device_product_key"] = "garmin:3515"
        refreshed["device_mapping_status"] = "resolved"
        updated = main._persist_sync_activity(refreshed)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT device_name, device_product_key, device_mapping_status FROM activities WHERE id = ?",
                (inserted["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(updated["op"], "updated")
        self.assertEqual(row["device_name"], "Fenix6 Asia")
        self.assertEqual(row["device_product_key"], "garmin:3515")
        self.assertEqual(row["device_mapping_status"], "resolved")

    def test_persist_skips_unchanged_file_when_device_is_already_resolved(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "device_skip.fit"
        fit_path.write_bytes(b"x" * 32)
        stat = fit_path.stat()

        activity = self._activity(fit_path.name)
        activity["file_path"] = str(fit_path.resolve())
        activity["file_mtime"] = stat.st_mtime
        activity["file_size"] = stat.st_size
        activity["device_name"] = "Fenix6 Asia"
        activity["device_vendor"] = "garmin"
        activity["device_product_key"] = "garmin:3515"
        activity["device_product_id"] = "3515"
        activity["device_mapping_status"] = "resolved"
        inserted = main._persist_sync_activity(activity)

        skipped = main._persist_sync_activity(dict(activity))

        self.assertEqual(inserted["op"], "inserted")
        self.assertEqual(skipped["op"], "skipped")
        self.assertEqual(skipped["id"], inserted["id"])

    def test_device_product_mapping_dry_run_and_contract_are_readonly(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_device_product_mapping_dry_run", methods)
        method = methods["get_device_product_mapping_dry_run"]
        self.assertEqual(method["category"], "activity")
        self.assertTrue(method["readonly"])
        self.assertFalse(method["high_risk"])
        self.assertIn("不解析 FIT", method["description"])
        self.assertIn("不联网", method["description"])
        self.assertIn("不写 activities", method["description"])
        self.assertIn("Garmin SDK profile", method["description"])

        main.ensure_activity_sync_schema()
        activity = self._activity("dry_run_device.fit")
        activity["device_name"] = "Garmin Product 3515"
        activity["device_vendor"] = "garmin"
        activity["device_product_key"] = ""
        activity["device_product_id"] = "3515"
        activity["device_mapping_status"] = "unresolved"
        persisted = main._persist_sync_activity(activity)

        api_res = self.api.get_device_product_mapping_dry_run({"limit": 5})
        self.assertEqual(api_res["code"], 0, api_res)
        data = api_res["data"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["garmin_product_fallback_count"], 1)
        self.assertEqual(data["refreshable_count"], 1)
        self.assertEqual(data["samples"][0]["id"], persisted["id"])
        self.assertEqual(data["samples"][0]["mapped_display_name"], "Fenix6 Asia")

    def test_device_product_dry_run_and_backfill_use_sdk_profile_without_mapping_row(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM device_product_mappings WHERE vendor = 'garmin' AND product_key = 'garmin:4587'"
                ).fetchone()
            )
        finally:
            conn.close()

        activity = self._activity("sdk_profile_device.fit")
        activity["device_name"] = "Garmin Product 4587"
        activity["device_vendor"] = ""
        activity["device_product_key"] = ""
        activity["device_product_id"] = ""
        activity["device_mapping_status"] = ""
        persisted = main._persist_sync_activity(activity)

        dry_run = main.device_product_mapping_dry_run(limit=5)
        sample = next(item for item in dry_run["samples"] if item["id"] == persisted["id"])
        self.assertEqual(sample["mapped_display_name"], "Instinct3 Amoled 50mm")
        self.assertEqual(sample["resolution_source"], "profile")
        self.assertTrue(sample["refreshable"])

        preview = main.backfill_device_product_mappings(dry_run=True)
        self.assertEqual(preview["updated"], 0)
        self.assertGreaterEqual(preview["refreshable"], 1)

        result = main.backfill_device_product_mappings()
        self.assertGreaterEqual(result["updated"], 1)
        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT device_name, device_vendor, device_product_key, device_product_id, device_mapping_status FROM activities WHERE id = ?",
                (persisted["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["device_name"], "Instinct3 Amoled 50mm")
        self.assertEqual(row["device_vendor"], "garmin")
        self.assertEqual(row["device_product_key"], "garmin:4587")
        self.assertEqual(row["device_product_id"], "4587")
        self.assertEqual(row["device_mapping_status"], "resolved")

    def test_activity_list_item_falls_back_to_clean_filename_when_title_missing(self):
        row = {
            "id": 1,
            "title": "",
            "title_source": "filename",
            "sport_type": "running",
            "sub_sport_type": "generic",
            "distance": 8490,
            "dist_km": 8.49,
            "duration": 3349,
            "duration_sec": 3349,
            "avg_pace": 394,
            "avg_hr": 141,
            "max_hr": 169,
            "calories": 599,
            "normalized_power": 283,
            "file_path": str(self.temp_dir / "西城区 跑步_611638502.fit"),
            "filename": "西城区 跑步_611638502.fit",
            "file_name": "西城区 跑步_611638502.fit",
            "start_time": "2026-06-30T08:00:00+08:00",
            "region_status": "success",
            "region_display": "北京市/中国",
        }

        item = main.Api()._build_activity_list_item(row)

        self.assertEqual(item["title"], "西城区 跑步")
        self.assertEqual(item["file_name"], "西城区 跑步_611638502.fit")

    def test_activity_detail_does_not_parse_fit_on_display_path(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("detail_display.fit")
        activity["normalized_power"] = 254
        activity["swolf"] = 42
        activity["laps_json"] = json.dumps([
            {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 145, "avg_power": 245}
        ])
        persisted = main._persist_sync_activity(activity)

        with mock.patch.object(
            main.FITCoreEngine,
            "parse_fit_file",
            side_effect=AssertionError("详情展示路径不应同步解析 FIT 文件"),
        ), mock.patch.object(
            main.FITCoreEngine,
            "parse_fit_file_raw",
            side_effect=AssertionError("详情展示路径不应同步解析 FIT raw 文件"),
        ):
            detail = self.api.get_activity_detail(persisted["id"])

        self.assertTrue(detail["ok"], detail)
        record = detail["data"]["record"]
        self.assertEqual(record["detail"]["capabilities"]["has_power"], True)
        self.assertEqual(record["detail"]["laps"][0]["power_w"], 245)

    def test_activity_detail_prefers_laps_json_over_synthetic_laps(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("real_laps.fit")
        activity["laps_json"] = json.dumps([
            {"distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 145, "avg_power": 245}
        ])
        persisted = main._persist_sync_activity(activity)

        with mock.patch.object(
            main.Api,
            "_build_lap_rows",
            side_effect=AssertionError("有 laps_json 时详情不应生成模拟圈速"),
        ):
            detail = self.api.get_activity_detail(persisted["id"])

        self.assertTrue(detail["ok"], detail)
        laps = detail["data"]["record"]["detail"]["laps"]
        self.assertEqual(len(laps), 1)
        self.assertEqual(laps[0]["pace_sec"], 300)
        self.assertEqual(laps[0]["power_w"], 245)

    def test_normalized_power_backfill_worker_updates_existing_db_rows(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "legacy_np.fit"
        fit_path.write_bytes(b"fit")
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.execute(
                """
                INSERT INTO activities (
                    filename, file_name, file_path, sport_type, sub_sport_type,
                    dist_km, distance, duration_sec, duration, start_time,
                    normalized_power
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy_np.fit", "legacy_np.fit", str(fit_path),
                    "running", "generic", 7.0, 7000.0, 2946, 2946,
                    "2026-05-19T08:00:00+08:00", None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main,
            "_read_activity_metrics_fast_from_fit",
            return_value={"avg_power": 239, "max_power": 402, "normalized_power": 254},
        ):
            main._run_normalized_power_backfill_worker(str(profile_backend.DB_PATH))

        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            row = conn.execute(
                "SELECT avg_power, max_power, normalized_power FROM activities WHERE filename = ?",
                ("legacy_np.fit",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (239.0, 402.0, 254.0))

    def test_list_metric_backfill_marks_attempt_even_when_fit_has_no_metric(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "legacy_empty_metrics.fit"
        fit_path.write_bytes(b"fit")
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.execute(
                """
                INSERT INTO activities (
                    filename, file_name, file_path, sport_type, sub_sport_type,
                    dist_km, distance, duration_sec, duration, start_time,
                    avg_power, max_power, normalized_power
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy_empty_metrics.fit", "legacy_empty_metrics.fit", str(fit_path),
                    "running", "generic", 7.0, 7000.0, 2946, 2946,
                    "2026-05-19T08:00:00+08:00", None, None, None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main,
            "_read_activity_metrics_fast_from_fit",
            return_value={"avg_power": None, "max_power": None, "normalized_power": None},
        ):
            main._run_normalized_power_backfill_worker(str(profile_backend.DB_PATH))

        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            row = conn.execute(
                """
                SELECT avg_power, max_power, normalized_power, list_metric_backfill_version
                FROM activities
                WHERE filename = ?
                """,
                ("legacy_empty_metrics.fit",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (None, None, None, main.LIST_METRIC_BACKFILL_VERSION))

        with main._NP_BACKFILL_LOCK:
            main._NP_BACKFILL_STATUS["finished_at"] = 0.0
            main._NP_BACKFILL_STATUS["total"] = 999
        status = main._start_normalized_power_backfill_if_needed()
        self.assertFalse(status["running"])
        self.assertEqual(status["total"], 0)

    def test_activity_list_schedules_metric_backfill_without_immediate_worker(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "deferred_np.fit"
        fit_path.write_bytes(b"fit")
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.execute(
                """
                INSERT INTO activities (
                    filename, file_name, file_path, sport_type, sub_sport_type,
                    dist_km, distance, duration_sec, duration, start_time,
                    avg_power, max_power, normalized_power
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "deferred_np.fit", "deferred_np.fit", str(fit_path),
                    "running", "generic", 7.0, 7000.0, 2946, 2946,
                    "2026-05-19T08:00:00+08:00", None, None, None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(main, "_run_normalized_power_backfill_worker") as worker:
            res1 = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")
            res2 = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")

        self.assertTrue(res1["ok"], res1)
        self.assertTrue(res2["ok"], res2)
        status = res1["data"]["list_metric_backfill"]
        self.assertTrue(status.get("scheduled"))
        self.assertFalse(status.get("running"))
        worker.assert_not_called()
        timer = getattr(main, "_NP_BACKFILL_TIMER", None)
        self.assertIsNotNone(timer)
        self.assertTrue(timer.is_alive())

    def test_water_metric_backfill_worker_updates_existing_db_rows(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "legacy_water.fit"
        fit_path.write_bytes(b"fit")
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.execute(
                """
                INSERT INTO activities (
                    filename, file_name, file_path, sport_type, sub_sport_type,
                    dist_km, distance, duration_sec, duration, start_time,
                    swolf, avg_stroke_distance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy_water.fit", "legacy_water.fit", str(fit_path),
                    "stand_up_paddleboarding", "generic", 3.0, 3000.0, 1800, 1800,
                    "2026-05-19T08:00:00+08:00", None, None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main,
            "_read_activity_metrics_fast_from_fit",
            return_value={"swolf": 57.0, "avg_stroke_distance": 1.8},
        ):
            main._run_normalized_power_backfill_worker(str(profile_backend.DB_PATH))

        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            row = conn.execute(
                "SELECT swolf, avg_stroke_distance FROM activities WHERE filename = ?",
                ("legacy_water.fit",),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (1.8, 1.8))

    def test_list_metric_backfill_worker_is_batch_limited(self):
        main.ensure_activity_sync_schema()
        rows = []
        for idx in range(main.LIST_METRIC_BACKFILL_BATCH_LIMIT + 5):
            fit_path = self.temp_dir / f"batch_{idx}.fit"
            fit_path.write_bytes(b"fit")
            rows.append(
                (
                    f"batch_{idx}.fit", f"batch_{idx}.fit", str(fit_path),
                    "running", "generic", 5.0, 5000.0, 1500, 1500,
                    f"2026-05-19T08:{idx % 60:02d}:00+08:00", None, None, None,
                )
            )
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.executemany(
                """
                INSERT INTO activities (
                    filename, file_name, file_path, sport_type, sub_sport_type,
                    dist_km, distance, duration_sec, duration, start_time,
                    avg_power, max_power, normalized_power
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(
            main,
            "_read_activity_metrics_fast_from_fit",
            return_value={"avg_power": 200, "max_power": 350, "normalized_power": 215},
        ) as read_metrics:
            main._run_normalized_power_backfill_worker(str(profile_backend.DB_PATH))

        self.assertEqual(read_metrics.call_count, main.LIST_METRIC_BACKFILL_BATCH_LIMIT)
        status = main._normalized_power_backfill_status()
        self.assertTrue(status["limited"])
        self.assertEqual(status["processed"], main.LIST_METRIC_BACKFILL_BATCH_LIMIT)

    def test_activity_inserts_with_pending_region_even_when_nominatim_down(self):
        main.ensure_activity_sync_schema()
        fit_path = self.temp_dir / "nom_fail.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "越野跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "trail",
                "start_time": "2026-05-19T08:00:00+08:00",
                "start_time_utc": "2026-05-19T00:00:00Z",
                "total_distance_km": 15.0,
                "total_timer_time": 5400,
                "total_calories": 900,
                "total_ascent": 300.0,
                "max_altitude": 800.0,
                "avg_hr": 160,
                "max_hr": 182,
            },
            "track_data": [
                {"lat": 30.57, "lon": 104.04, "alt": 500.0, "time": "2026-05-19T00:00:00Z", "hr": 150},
                {"lat": 30.58, "lon": 104.05, "alt": 520.0, "time": "2026-05-19T00:30:00Z", "hr": 165},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(profile_backend, "resolve_activity_region", return_value=""):
            activity = main._parse_fit_activity_for_sync(fit_path)

        result = main._persist_sync_activity(activity)
        self.assertIn(result["op"], {"inserted", "updated"})

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT region, region_status, region_error, region_attempt_count FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["region"], "")
        self.assertEqual(row["region_status"], "pending")
        self.assertIsNone(row["region_error"])
        self.assertEqual(row["region_attempt_count"], 0)

    def test_region_enrichment_background_fills_region_after_cache_populated(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("cache_fill.fit")
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 30.67
        activity["start_lon"] = 104.06
        result = main._persist_sync_activity(activity)

        display = "成都市，中国"
        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))",
                ("30.67,104.06", 30.67, 104.06, "成都市", "中国", display),
            )
            conn.commit()
        finally:
            conn.close()

        enrichment = profile_backend.run_region_enrichment_once(limit=5)
        self.assertTrue(enrichment["ok"])
        self.assertEqual(enrichment["success"], 1)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT region, region_status, region_error FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["region"], display)
        self.assertEqual(row["region_status"], "success")
        self.assertIsNone(row["region_error"])

    def test_region_enrichment_background_uses_offline_fallback_after_nominatim_failure(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("background_offline.fit")
        activity["title"] = "跑步"
        activity["title_source"] = "auto_sport"
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 34.89
        activity["start_lon"] = 135.81
        result = main._persist_sync_activity(activity)

        def offline(lat, lon):
            return {"city": "宇治市", "country": "日本", "display_name": "宇治市, 日本"}

        done = threading.Event()
        completed: list[dict] = []

        def on_complete(payload):
            completed.append(payload)
            done.set()

        with mock.patch.object(profile_backend, "reverse_geocode", side_effect=ConnectionError("Nominatim 不可达")), \
             mock.patch.object(profile_backend, "resolve_region_offline", side_effect=offline):
            profile_backend.start_region_enrichment_background(limit=5, on_complete=on_complete)
            self.assertTrue(done.wait(timeout=2.0), "后台地区回填未完成")

        self.assertEqual(completed[0]["inferred"], 1)
        conn = profile_backend._conn()
        try:
            row = conn.execute(
                """
                SELECT title, title_source, region_city, region_status, region_source, region_confidence
                FROM activities WHERE id = ?
                """,
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["title"], "跑步")
        self.assertEqual(row["title_source"], "auto_sport")
        self.assertEqual(row["region_city"], "宇治市")
        self.assertEqual(row["region_status"], "inferred")
        self.assertEqual(row["region_source"], "offline_geocoder")
        self.assertEqual(row["region_confidence"], "medium")

    def test_resync_preserves_success_region_and_auto_region_title_when_new_parse_is_pending(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("resync_success_region.fit")
        activity["title"] = "跑步"
        activity["title_source"] = "auto_sport"
        activity["region"] = ""
        activity["region_status"] = "pending"
        inserted = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        try:
            conn.execute(
                """
                UPDATE activities
                SET title = '成都市 跑步',
                    title_source = 'auto_region_sport',
                    region = '成都市/中国',
                    region_city = '成都市',
                    region_country = '中国',
                    region_display = '成都市/中国',
                    region_status = 'success',
                    region_source = 'nominatim',
                    region_confidence = 'high',
                    region_error = NULL,
                    region_updated_at = '2026-07-15T08:00:00',
                    region_attempt_count = 2
                WHERE id = ?
                """,
                (inserted["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        reparsed = dict(activity)
        reparsed.update({
            "title": "跑步",
            "title_source": "auto_sport",
            "region": "",
            "region_city": None,
            "region_country": None,
            "region_display": None,
            "region_status": "pending",
            "region_error": None,
            "region_updated_at": None,
            "region_attempt_count": 0,
        })
        updated = main._persist_sync_activity(reparsed)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                """
                SELECT title, title_source, region, region_city, region_status,
                       region_source, region_confidence, region_attempt_count
                FROM activities WHERE id = ?
                """,
                (inserted["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(updated["op"], "updated")
        self.assertEqual(row["title"], "成都市 跑步")
        self.assertEqual(row["title_source"], "auto_region_sport")
        self.assertEqual(row["region"], "成都市/中国")
        self.assertEqual(row["region_city"], "成都市")
        self.assertEqual(row["region_status"], "success")
        self.assertEqual(row["region_source"], "nominatim")
        self.assertEqual(row["region_confidence"], "high")
        self.assertEqual(row["region_attempt_count"], 2)

    def test_resync_preserves_inferred_region_when_new_parse_is_pending(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("resync_inferred_region.fit")
        activity["region"] = ""
        activity["region_status"] = "pending"
        inserted = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        try:
            conn.execute(
                """
                UPDATE activities
                SET region = '宇治市/日本',
                    region_city = '宇治市',
                    region_country = '日本',
                    region_display = '宇治市/日本',
                    region_status = 'inferred',
                    region_source = 'offline_geocoder',
                    region_confidence = 'medium',
                    region_error = NULL,
                    region_updated_at = '2026-07-15T08:00:00',
                    region_attempt_count = 1
                WHERE id = ?
                """,
                (inserted["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        reparsed = dict(activity)
        reparsed.update({
            "region": "",
            "region_city": None,
            "region_country": None,
            "region_display": None,
            "region_status": "pending",
            "region_error": None,
            "region_updated_at": None,
            "region_attempt_count": 0,
        })
        updated = main._persist_sync_activity(reparsed)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                """
                SELECT region, region_city, region_status, region_source,
                       region_confidence, region_attempt_count
                FROM activities WHERE id = ?
                """,
                (inserted["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(updated["op"], "updated")
        self.assertEqual(row["region"], "宇治市/日本")
        self.assertEqual(row["region_city"], "宇治市")
        self.assertEqual(row["region_status"], "inferred")
        self.assertEqual(row["region_source"], "offline_geocoder")
        self.assertEqual(row["region_confidence"], "medium")
        self.assertEqual(row["region_attempt_count"], 1)

    def test_resync_preserves_user_title(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("resync_user_title.fit")
        inserted = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        try:
            conn.execute(
                "UPDATE activities SET title = '2026 成都半程马拉松', title_source = 'user' WHERE id = ?",
                (inserted["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        reparsed = dict(activity)
        reparsed["title"] = "跑步"
        reparsed["title_source"] = "auto_sport"
        updated = main._persist_sync_activity(reparsed)

        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT title, title_source FROM activities WHERE id = ?", (inserted["id"],)).fetchone()
        finally:
            conn.close()

        self.assertEqual(updated["op"], "updated")
        self.assertEqual(row["title"], "2026 成都半程马拉松")
        self.assertEqual(row["title_source"], "user")

    def test_region_enrichment_cache_hit_bulk_writes_same_coordinate_without_nominatim(self):
        main.ensure_activity_sync_schema()
        first = self._activity("cache_bulk_1.fit")
        second = self._activity("cache_bulk_2.fit")
        for activity in (first, second):
            activity["region"] = ""
            activity["region_status"] = "pending"
            activity["start_lat"] = 30.671
            activity["start_lon"] = 104.061
            activity["title_source"] = "auto_sport"
        self._set_activity_start(second, "2026-05-20T08:00:00Z")
        r1 = main._persist_sync_activity(first)
        r2 = main._persist_sync_activity(second)

        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))",
                ("30.67,104.06", 30.67, 104.06, "成都市", "中国", "成都市/中国"),
            )
            conn.commit()
        finally:
            conn.close()

        with mock.patch.object(profile_backend, "reverse_geocode", side_effect=AssertionError("不应访问 Nominatim")):
            enrichment = profile_backend.run_region_enrichment_once(limit=5)

        self.assertTrue(enrichment["ok"])
        self.assertEqual(enrichment["cache_hits"], 2)
        self.assertEqual(enrichment["requests"], 0)
        conn = profile_backend._conn()
        try:
            rows = conn.execute(
                "SELECT id, title, title_source, region_city, region_status FROM activities WHERE id IN (?, ?) ORDER BY id",
                (r1["id"], r2["id"]),
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual([row["region_city"] for row in rows], ["成都市", "成都市"])
        self.assertEqual([row["region_status"] for row in rows], ["success", "success"])
        self.assertEqual([row["title"] for row in rows], ["成都市 跑步", "成都市 跑步"])

    def test_region_enrichment_requests_unique_coordinate_once_and_bulk_writes(self):
        main.ensure_activity_sync_schema()
        first = self._activity("unique_coord_1.fit")
        second = self._activity("unique_coord_2.fit")
        for activity in (first, second):
            activity["region"] = ""
            activity["region_status"] = "pending"
            activity["start_lat"] = 31.230
            activity["start_lon"] = 121.470
            activity["title_source"] = "auto_sport"
        self._set_activity_start(second, "2026-05-20T08:00:00Z")
        main._persist_sync_activity(first)
        main._persist_sync_activity(second)

        calls = []
        def fake_reverse(lat, lon):
            calls.append((lat, lon))
            return {"city": "上海市", "country": "中国", "display_name": "上海市, 中国"}

        with mock.patch.object(profile_backend, "reverse_geocode", side_effect=fake_reverse):
            enrichment = profile_backend.run_region_enrichment_once(limit=5)

        self.assertEqual(calls, [(31.23, 121.47)])
        self.assertEqual(enrichment["requests"], 1)
        self.assertEqual(enrichment["success"], 2)

        conn = profile_backend._conn()
        try:
            rows = conn.execute("SELECT region_city, region_status FROM activities ORDER BY id").fetchall()
        finally:
            conn.close()
        self.assertEqual([row["region_city"] for row in rows], ["上海市", "上海市"])
        self.assertEqual([row["region_status"] for row in rows], ["success", "success"])

    def test_region_enrichment_upgrades_auto_coros_title_after_cache_populated(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("coros___activity-fit-files_3a4c7694c39941c98ef78f4fe33feae2.fit")
        activity["title"] = "coros activity-fit-files 3a4c7694c39941c98ef78f4fe33feae2"
        activity["title_source"] = "filename"
        activity["sport_type"] = "running"
        activity["sub_sport_type"] = "generic"
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 39.90
        activity["start_lon"] = 116.40
        result = main._persist_sync_activity(activity)

        display = "北京市/中国"
        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))",
                ("39.90,116.40", 39.90, 116.40, "北京市", "中国", display),
            )
            conn.commit()
        finally:
            conn.close()

        enrichment = profile_backend.run_region_enrichment_once(limit=5)
        self.assertTrue(enrichment["ok"])
        self.assertEqual(enrichment["success"], 1)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT title, title_source, region, region_status FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["title"], "北京市 跑步")
        self.assertEqual(row["title_source"], "auto_region_sport")
        self.assertEqual(row["region"], display)
        self.assertEqual(row["region_status"], "success")

    def test_region_enrichment_preserves_manual_title_on_success(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("manual_title_region.fit")
        activity["title"] = "我的自定义标题"
        activity["title_source"] = "user"
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 39.90
        activity["start_lon"] = 116.40
        result = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))",
                ("39.90,116.40", 39.90, 116.40, "北京市", "中国", "北京市/中国"),
            )
            conn.commit()
        finally:
            conn.close()

        enrichment = profile_backend.run_region_enrichment_once(limit=5)
        self.assertEqual(enrichment["success"], 1)
        self.assertEqual(enrichment["title_updated"], 0)

        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT title, title_source, region_city, region_status FROM activities WHERE id = ?", (result["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["title"], "我的自定义标题")
        self.assertEqual(row["title_source"], "user")
        self.assertEqual(row["region_city"], "北京市")
        self.assertEqual(row["region_status"], "success")

    def test_region_enrichment_inferred_does_not_rename_and_later_success_overrides(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("offline_fallback.fit")
        activity["title"] = "跑步"
        activity["title_source"] = "auto_sport"
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 34.89
        activity["start_lon"] = 135.81
        result = main._persist_sync_activity(activity)

        def offline(lat, lon):
            return {"city": "宇治市", "country": "日本", "display_name": "宇治市, 日本"}

        with mock.patch.object(profile_backend, "reverse_geocode", side_effect=ConnectionError("Nominatim 不可达")):
            enrichment = profile_backend.run_region_enrichment_once(limit=5, offline_resolver=offline)
        self.assertEqual(enrichment["inferred"], 1)
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT title, title_source, region_city, region_status, region_source FROM activities WHERE id = ?", (result["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["title"], "跑步")
        self.assertEqual(row["title_source"], "auto_sport")
        self.assertEqual(row["region_city"], "宇治市")
        self.assertEqual(row["region_status"], "inferred")
        self.assertEqual(row["region_source"], "offline_geocoder")

        with mock.patch.object(profile_backend, "reverse_geocode", return_value={"city": "京都府", "country": "日本", "display_name": "京都府, 日本"}):
            enrichment = profile_backend.run_region_enrichment_once(limit=5)
        self.assertEqual(enrichment["success"], 1)
        self.assertEqual(enrichment["requests"], 1)
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT title, region_city, region_status, region_source FROM activities WHERE id = ?", (result["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["title"], "京都府 跑步")
        self.assertEqual(row["region_city"], "京都府")
        self.assertEqual(row["region_status"], "success")
        self.assertEqual(row["region_source"], "nominatim")

    def test_region_enrichment_dry_run_reports_cache_and_title_counts_by_year(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("dry_run_region.fit")
        activity["start_time"] = "2024-03-01T08:00:00+08:00"
        activity["start_time_utc"] = "2024-03-01T00:00:00Z"
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 30.67
        activity["start_lon"] = 104.06
        activity["title_source"] = "auto_sport"
        main._persist_sync_activity(activity)
        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO geocode_cache (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))",
                ("30.67,104.06", 30.67, 104.06, "成都市", "中国", "成都市/中国"),
            )
            conn.commit()
            dry_run = profile_backend.region_enrichment_dry_run([2024], conn=conn)
        finally:
            conn.close()

        self.assertTrue(dry_run["ok"])
        self.assertEqual(dry_run["years"][0]["year"], 2024)
        self.assertEqual(dry_run["years"][0]["pending_gps_activity_count"], 1)
        self.assertEqual(dry_run["years"][0]["cache_hit_activity_count"], 1)
        self.assertEqual(dry_run["years"][0]["auto_title_update_candidate_count"], 1)

    def test_backfill_auto_activity_titles_updates_existing_coros_title(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("coros___activity-fit-files_0794a4410dba433ba0b7e4c605f4fd8e.fit")
        activity["title"] = "coros activity-fit-files 0794a4410dba433ba0b7e4c605f4fd8e"
        activity["title_source"] = "filename"
        activity["sport_type"] = "running"
        activity["sub_sport_type"] = "generic"
        activity["region"] = "北京市/中国"
        activity["region_display"] = "北京市/中国"
        activity["region_status"] = "success"
        result = main._persist_sync_activity(activity)

        updated = profile_backend.backfill_auto_activity_titles()
        self.assertEqual(updated, 1)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT title, title_source FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["title"], "北京市 跑步")
        self.assertEqual(row["title_source"], "auto_region_sport")

    def test_backfill_auto_activity_titles_strips_provider_id_and_collision_suffix(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("雅安市 骑行_23535321841-1-1.fit")
        activity["title"] = "雅安市 骑行_23535321841-1-1"
        activity["title_source"] = "filename"
        activity["sport_type"] = "cycling"
        activity["sub_sport_type"] = "generic"
        activity["region"] = "雅安市/中国"
        activity["region_display"] = "雅安市/中国"
        activity["region_status"] = "success"
        result = main._persist_sync_activity(activity)

        updated = profile_backend.backfill_auto_activity_titles()
        self.assertEqual(updated, 1)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT title, title_source FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["title"], "雅安市 骑行")
        self.assertEqual(row["title_source"], "filename")

    def test_filename_title_cleaner_preserves_real_numbers_outside_provider_suffix(self):
        self.assertEqual(
            profile_backend.clean_activity_filename_title("雅安市 骑行_23535321841-1-1.fit"),
            "雅安市 骑行",
        )
        self.assertEqual(profile_backend.clean_activity_filename_title("2026都江堰半程马拉松.fit"), "2026都江堰半程马拉松")
        self.assertEqual(profile_backend.clean_activity_filename_title("环法第21赛段.fit"), "环法第21赛段")

    def test_backfill_auto_activity_titles_preserves_garmin_event_filename_title(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("都江堰半程马拉松.fit")
        activity["title"] = "都江堰半程马拉松"
        activity["title_source"] = "filename"
        activity["sport_type"] = "running"
        activity["sub_sport_type"] = "generic"
        activity["region"] = "成都市/中国"
        activity["region_display"] = "成都市/中国"
        activity["region_status"] = "success"
        result = main._persist_sync_activity(activity)

        updated = profile_backend.backfill_auto_activity_titles()
        self.assertEqual(updated, 0)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT title, title_source FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["title"], "都江堰半程马拉松")
        self.assertEqual(row["title_source"], "filename")

    def test_region_enrichment_marks_failure_and_increments_attempt_count(self):
        main.ensure_activity_sync_schema()
        activity = self._activity("nom_retry.fit")
        activity["region"] = ""
        activity["region_status"] = "pending"
        activity["start_lat"] = 31.23
        activity["start_lon"] = 121.47
        result = main._persist_sync_activity(activity)

        with mock.patch.object(profile_backend, "reverse_geocode", side_effect=ConnectionError("Nominatim 不可达")):
            enrichment = profile_backend.run_region_enrichment_once(limit=5)

        self.assertTrue(enrichment["ok"])
        self.assertEqual(enrichment["failed"], 1)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT region, region_status, region_error, region_attempt_count FROM activities WHERE id = ?",
                (result["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["region_status"], "failed")
        self.assertIn("Nominatim", str(row["region_error"] or ""))
        self.assertEqual(row["region_attempt_count"], 1)

    def test_activity_list_snapshot_returns_region_field(self):
        main.ensure_activity_sync_schema()
        activity_res = main._persist_sync_activity(self._activity("with_region.fit"))
        config = self._workspace_config()
        config["workspace_track_abs_path"] = ""
        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=config):
            snapshot = self.api.get_activity_list_snapshot("all")
            activity_id = snapshot["data"]["records"][0]["id"]
            detail = self.api.get_activity_detail(activity_id)

        self.assertIn(activity_res.get("op"), {"inserted", "updated"})
        self.assertTrue(snapshot["ok"], snapshot)
        self.assertEqual(snapshot["data"]["records"][0]["region"], "成都市")
        self.assertTrue(detail["ok"], detail)
        self.assertEqual(detail["data"]["record"]["region"], "成都市")
        self.assertIn("display_metrics", detail["data"]["record"]["detail"])
        self.assertIn("layout", detail["data"]["record"]["detail"])
        self.assertIn("capabilities", detail["data"]["record"]["detail"])

    def test_activity_type_filter_matches_swim_sub_sports(self):
        main.ensure_activity_sync_schema()
        pool = self._activity("pool_swim.fit")
        pool.update({
            "sport_type": "swimming",
            "sub_sport_type": "lap_swimming",
            "start_time": "2026-05-19T08:00:00Z",
            "start_time_utc": "2026-05-19T08:00:00Z",
            "swolf": 42,
        })
        open_water = self._activity("open_water.fit")
        open_water.update({
            "sport_type": "swimming",
            "sub_sport_type": "open_water",
            "start_time": "2026-05-19T09:00:00Z",
            "start_time_utc": "2026-05-19T09:00:00Z",
            "swolf": 2.1,
        })
        main._persist_sync_activity(pool)
        main._persist_sync_activity(open_water)

        pool_res = self.api.get_activity_list(page=1, page_size=10, sport_filter="lap_swimming")
        open_water_res = self.api.get_activity_list(page=1, page_size=10, sport_filter="open_water")

        self.assertTrue(pool_res["ok"], pool_res)
        self.assertTrue(open_water_res["ok"], open_water_res)
        self.assertEqual(pool_res["data"]["total"], 1)
        self.assertEqual(open_water_res["data"]["total"], 1)
        self.assertEqual(pool_res["data"]["records"][0]["sub_sport_type"], "lap_swimming")
        self.assertEqual(open_water_res["data"]["records"][0]["sub_sport_type"], "open_water")

    def test_activity_list_dynamic_columns_follow_current_page_records(self):
        main.ensure_activity_sync_schema()
        for idx in range(10):
            run = self._activity(f"page_run_{idx}.fit")
            run.update({
                "sport_type": "running",
                "sub_sport_type": "generic",
                "start_time": f"2026-05-19T{10 + idx:02d}:00:00+08:00",
                "start_time_utc": f"2026-05-19T{10 + idx:02d}:00:00+08:00",
                "gain_m": 80,
                "normalized_power": 230,
            })
            main._persist_sync_activity(run)
        swim = self._activity("page_swim.fit")
        swim.update({
            "sport_type": "swimming",
            "sub_sport_type": "lap_swimming",
            "start_time": "2026-05-19T08:00:00+08:00",
            "start_time_utc": "2026-05-19T08:00:00+08:00",
            "swolf": 42,
        })
        main._persist_sync_activity(swim)

        page1 = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")
        page2 = self.api.get_activity_list(page=2, page_size=10, sport_filter="all")

        self.assertTrue(page1["ok"], page1)
        self.assertTrue(page2["ok"], page2)
        self.assertTrue(all(record["sport_type"] == "running" for record in page1["data"]["records"]))
        self.assertEqual(page1["data"]["dynamic_columns"], ["gain", "np"])
        self.assertEqual(page2["data"]["records"][0]["sub_sport_type"], "lap_swimming")
        self.assertEqual(page2["data"]["dynamic_columns"], ["swolf"])

    def test_activity_list_indexes_exist_after_schema_init(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            indexes = {
                str(row["name"])
                for row in conn.execute("PRAGMA index_list(activities)").fetchall()
            }
        finally:
            conn.close()

        expected = {
            "idx_activities_list_sort_expr",
            "idx_activities_list_type",
            "idx_activities_location_display",
            "idx_activities_file_path",
        }
        self.assertTrue(expected.issubset(indexes), f"缺少索引: {sorted(expected - indexes)}")

    def test_activity_list_source_and_mock_filter_semantics(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            rows = [
                ("null_defaults.fit", None, None),
                ("fit_sdk.fit", "fit_sdk", 0),
                ("manual.fit", "manual", 0),
                ("mock.fit", "fit_sdk", 1),
            ]
            for idx, (filename, source_type, is_mock) in enumerate(rows):
                conn.execute(
                    """
                    INSERT INTO activities (
                        filename, file_name, title, sport_type, sub_sport_type,
                        start_time, updated_at, source_type, is_mock, deleted_at
                    ) VALUES (?, ?, ?, 'running', 'unknown', ?, ?, ?, ?, NULL)
                    """,
                    (
                        filename,
                        filename,
                        filename,
                        f"2026-05-19T08:0{idx}:00Z",
                        f"2026-05-19 08:0{idx}:00",
                        source_type,
                        is_mock,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        records, total = profile_backend.get_activity_list_filtered(0, 20, "all")
        filenames = {row["filename"] for row in records}

        self.assertEqual(total, 2)
        self.assertEqual(filenames, {"null_defaults.fit", "fit_sdk.fit"})

    def test_activity_list_sort_order_matches_coalesced_time_then_id(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            seed = [
                ("older.fit", "2026-05-18T08:00:00Z", "2026-05-20 09:00:00"),
                ("fallback_newer.fit", None, "2026-05-21 09:00:00"),
                ("same_a.fit", "2026-05-22T08:00:00Z", "2026-05-22 07:00:00"),
                ("same_b.fit", "2026-05-22T08:00:00Z", "2026-05-22 07:00:00"),
            ]
            for filename, start_time, updated_at in seed:
                conn.execute(
                    """
                    INSERT INTO activities (
                        filename, file_name, title, sport_type, sub_sport_type,
                        start_time, updated_at, source_type, is_mock, deleted_at
                    ) VALUES (?, ?, ?, 'running', 'unknown', ?, ?, 'fit_sdk', 0, NULL)
                    """,
                    (filename, filename, filename, start_time, updated_at),
                )
            conn.commit()
        finally:
            conn.close()

        records, total = profile_backend.get_activity_list_filtered(0, 20, "all")
        filenames = [row["filename"] for row in records]

        self.assertEqual(total, 4)
        self.assertEqual(filenames[:4], ["same_b.fit", "same_a.fit", "fallback_newer.fit", "older.fit"])

    def test_shadow_diff_json_persists_updates_and_detail_returns(self):
        main.ensure_activity_sync_schema()
        shadow_diff = {
            "pace": {"legacy": 360, "resolved": 358, "match": False},
            "_meta": {"generated_by": "MetricsResolver Shadow Layer", "trusted": False},
        }
        activity = self._activity("shadow.fit")
        activity["shadow_diff_json"] = json.dumps(shadow_diff, ensure_ascii=False)
        activity_res = main._persist_sync_activity(activity)

        conn = profile_backend._conn()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()}
            row = conn.execute(
                "SELECT shadow_diff_json FROM activities WHERE id = ?",
                (activity_res["id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertIn("shadow_diff_json", columns)
        self.assertEqual(json.loads(row["shadow_diff_json"]), shadow_diff)

        updated_diff = {
            "pace": {"legacy": 360, "resolved": 360, "match": True},
            "_meta": {"generated_by": "MetricsResolver Shadow Layer", "trusted": False},
        }
        activity["shadow_diff_json"] = json.dumps(updated_diff, ensure_ascii=False)
        update_res = main._persist_sync_activity(activity)
        self.assertEqual(update_res["op"], "updated")

        list_res = self.api.get_activity_list(page=1, page_size=10, sport_filter="all")
        detail = self.api.get_activity_detail(activity_res["id"])

        self.assertTrue(list_res["ok"], list_res)
        record = list_res["data"]["records"][0]
        for forbidden in (
            "hr_curve",
            "speed_curve",
            "shadow_diff",
            "shadow_diff_json",
            "track_json",
            "points_json",
        ):
            self.assertNotIn(forbidden, record)
        for required in (
            "id",
            "title",
            "filename",
            "sport_type",
            "distance_km",
            "duration_sec",
            "start_time",
            "has_track",
        ):
            self.assertIn(required, record)
        self.assertTrue(detail["ok"], detail)
        self.assertEqual(detail["data"]["record"]["shadow_diff"], updated_diff)

    def test_fetch_historical_weather_uses_archive_api_and_hour_index(self):
        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "hourly": {
                "time": [f"2024-03-01T{str(h).zfill(2)}:00" for h in range(24)],
                "temperature_2m": list(range(24)),
                "relative_humidity_2m": [60 + h for h in range(24)],
                "wind_speed_10m": [5 + h for h in range(24)],
                "weathercode": [0] * 24,
            }
        }
        with mock.patch("utils.weather_api.requests.get", return_value=fake_response) as mocked_get:
            weather = fetch_historical_weather(30.67, 104.06, "2024-03-01T14:30:00+08:00")

        self.assertIsNotNone(weather)
        self.assertEqual(weather["temperature_c"], 14)
        self.assertEqual(weather["humidity"], 74)
        self.assertEqual(weather["wind_speed_kmh"], 19)
        self.assertEqual(weather["weather_label"], "晴")
        _, kwargs = mocked_get.call_args
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["params"]["start_date"], "2024-03-01")
        self.assertEqual(kwargs["params"]["end_date"], "2024-03-02")
        self.assertEqual(kwargs["params"]["timezone"], "auto")

    def test_fetch_historical_weather_uses_forecast_api_for_recent_activity(self):
        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "hourly": {
                "time": [f"2026-06-20T{str(h).zfill(2)}:00" for h in range(24)],
                "temperature_2m": list(range(24)),
                "relative_humidity_2m": [50 + h for h in range(24)],
                "wind_speed_10m": [3 + h for h in range(24)],
                "weather_code": [3] * 24,
            }
        }
        with mock.patch("utils.weather_api._now_utc", return_value=datetime(2026, 6, 20, 5, 0, tzinfo=timezone.utc)), \
             mock.patch("utils.weather_api.requests.get", return_value=fake_response) as mocked_get:
            weather = fetch_historical_weather(39.95, 116.38, "2026-06-20T09:17:58+08:00")

        self.assertIsNotNone(weather)
        self.assertEqual(weather["temperature_c"], 9)
        self.assertEqual(weather["humidity"], 59)
        self.assertEqual(weather["wind_speed_kmh"], 12)
        self.assertEqual(weather["weather_label"], "阴")
        self.assertEqual(weather["source"], "forecast")
        _, kwargs = mocked_get.call_args
        self.assertEqual(kwargs["params"]["past_days"], 3)
        self.assertEqual(kwargs["params"]["forecast_days"], 1)
        self.assertIn("weather_code", kwargs["params"]["hourly"])

    def test_fetch_historical_weather_matches_utc_start_to_local_api_hour(self):
        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "utc_offset_seconds": 8 * 3600,
            "hourly": {
                "time": [f"2026-06-20T{str(h).zfill(2)}:00" for h in range(24)],
                "temperature_2m": list(range(24)),
                "relative_humidity_2m": [40 + h for h in range(24)],
                "wind_speed_10m": [2 + h for h in range(24)],
                "weather_code": [1] * 24,
            }
        }
        with mock.patch("utils.weather_api._now_utc", return_value=datetime(2026, 6, 20, 5, 0, tzinfo=timezone.utc)), \
             mock.patch("utils.weather_api.requests.get", return_value=fake_response):
            weather = fetch_historical_weather(39.95, 116.38, "2026-06-20T01:17:58Z")

        self.assertIsNotNone(weather)
        self.assertEqual(weather["temperature_c"], 9)
        self.assertEqual(weather["observed_hour"], 9)
        self.assertEqual(weather["observed_date"], "2026-06-20")

    def test_build_activity_payload_persists_weather_dict_from_track_backend(self):
        data = {
            "points": [{"lat": 39.95, "lon": 116.38, "time": "2026-06-20T01:17:58Z"}],
            "distance_km": 5.0,
            "duration_sec": 1800,
            "weather": {"temperature_c": 29, "weather_label": "晴"},
        }
        activity = profile_backend.build_activity_payload("legacy_weather.fit", data, str(self.temp_dir / "legacy_weather.fit"))

        self.assertIn('"temperature_c": 29', activity["weather_json"])
        self.assertEqual(activity["weather_status"], "success")
        self.assertEqual(activity["weather_attempt_count"], 1)
        self.assertIsNone(activity["weather_error"])

    def test_parse_fit_activity_for_sync_persists_weather_json(self):
        fit_path = self.temp_dir / "weather.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "雨战节奏跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "unknown",
                "start_time": "2024-03-01T14:30:00+08:00",
                "start_time_utc": "2024-03-01T06:30:00Z",
                "total_distance_km": 10.0,
                "total_timer_time": 3600,
                "total_calories": 650,
                "total_ascent": 88.0,
                "max_altitude": 32.0,
                "avg_hr": 152,
                "max_hr": 174,
            },
            "track_data": [
                {"lat": 30.67, "lon": 104.06, "alt": 10.0, "time": "2024-03-01T06:30:00Z", "hr": 145},
                {"lat": 30.68, "lon": 104.07, "alt": 12.0, "time": "2024-03-01T06:35:00Z", "hr": 150},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(profile_backend, "resolve_activity_region", side_effect=AssertionError("地区查询不应阻塞 FIT 入库")), \
             mock.patch("main.fetch_historical_weather", return_value={
                 "temperature_c": 28,
                 "humidity": 85,
                 "wind_speed_kmh": 11,
                 "weather_code": 3,
                 "weather_label": "阴",
                 "observed_hour": 14,
                 "observed_date": "2024-03-01",
             }):
            activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertIn('"temperature_c": 28', activity["weather_json"])
        self.assertIn('"weather_label": "阴"', activity["weather_json"])
        self.assertEqual(activity["weather_status"], "success")
        self.assertEqual(activity["weather_attempt_count"], 1)
        self.assertIsNone(activity["weather_error"])

    def test_parse_fit_activity_for_sync_prefers_local_start_time_for_weather(self):
        fit_path = self.temp_dir / "weather_local.fit"
        fit_path.write_bytes(b"fit")
        fake_core = {
            "basic_info": {
                "title": "夜跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "unknown",
                "start_time": "2024-03-01T23:30:00+08:00",
                "start_time_utc": "2024-03-01T15:30:00Z",
                "total_distance_km": 5.0,
                "total_timer_time": 1800,
                "total_calories": 300,
                "total_ascent": 20.0,
                "max_altitude": 30.0,
            },
            "track_data": [
                {"lat": 30.67, "lon": 104.06, "alt": 10.0, "time": "2024-03-01T15:30:00Z"},
            ],
        }
        with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch.object(profile_backend, "resolve_activity_region", side_effect=AssertionError("地区查询不应阻塞 FIT 入库")), \
             mock.patch("main.fetch_historical_weather", return_value=None) as mocked_weather:
            main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(mocked_weather.call_args.args[2], "2024-03-01T23:30:00+08:00")

    def test_weather_backfill_worker_updates_missing_weather_rows(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count)
                VALUES (?, 'running', ?, ?, ?, 'pending', 0)
                """,
                ("missing_weather.fit", "2026-06-20T09:17:58+08:00", 39.95, 116.38),
            )
            activity_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with mock.patch("main.fetch_historical_weather", return_value={
            "temperature_c": 29,
            "humidity": 68,
            "wind_speed_kmh": 9,
            "weather_code": 1,
            "weather_label": "少云",
            "observed_hour": 9,
            "observed_date": "2026-06-20",
            "source": "forecast",
        }) as mocked_weather:
            main._run_weather_backfill_worker(str(profile_backend.DB_PATH), limit=10)

        mocked_weather.assert_called_once_with(39.95, 116.38, "2026-06-20T09:17:58+08:00")
        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT weather_json, weather_status, weather_attempt_count, weather_error FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIn('"temperature_c": 29', row["weather_json"])
        self.assertEqual(row["weather_status"], "success")
        self.assertEqual(row["weather_attempt_count"], 1)
        self.assertIsNone(row["weather_error"])

    def test_activity_weather_backfill_updates_only_current_row(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count)
                VALUES (?, 'running', ?, ?, ?, 'pending', 0)
                """,
                ("single_weather.fit", "2026-06-20T09:17:58+08:00", 39.95, 116.38),
            )
            activity_id = int(cur.lastrowid)
            other_cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count)
                VALUES (?, 'running', ?, ?, ?, 'pending', 0)
                """,
                ("other_missing_weather.fit", "2026-06-20T10:17:58+08:00", 39.95, 116.38),
            )
            other_id = int(other_cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        weather = {
            "temperature_c": 29,
            "humidity": 68,
            "wind_speed_kmh": 9,
            "weather_code": 1,
            "weather_label": "少云",
            "observed_hour": 9,
            "observed_date": "2026-06-20",
            "source": "forecast",
        }
        with mock.patch("main.fetch_historical_weather", return_value=weather) as mocked_weather:
            res = self.api.backfill_activity_weather(activity_id)

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["weather"], weather)
        mocked_weather.assert_called_once_with(39.95, 116.38, "2026-06-20T09:17:58+08:00")

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT weather_json, weather_status, weather_attempt_count FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            other = conn.execute(
                "SELECT weather_json, weather_status, weather_attempt_count FROM activities WHERE id = ?",
                (other_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIn('"temperature_c": 29', row["weather_json"])
        self.assertEqual(row["weather_status"], "success")
        self.assertEqual(row["weather_attempt_count"], 1)
        self.assertIsNone(other["weather_json"])
        self.assertEqual(other["weather_status"], "pending")
        self.assertEqual(other["weather_attempt_count"], 0)

    def test_weather_backfill_worker_records_failed_attempt(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count)
                VALUES (?, 'running', ?, ?, ?, 'pending', 2)
                """,
                ("failed_weather.fit", "2026-06-20T09:17:58+08:00", 39.95, 116.38),
            )
            activity_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with mock.patch("main.fetch_historical_weather", return_value=None):
            main._run_weather_backfill_worker(str(profile_backend.DB_PATH), limit=10)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT weather_json, weather_status, weather_attempt_count, weather_error FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(row["weather_json"])
        self.assertEqual(row["weather_status"], "failed")
        self.assertEqual(row["weather_attempt_count"], 3)
        self.assertEqual(row["weather_error"], "weather unavailable")

    def test_weather_backfill_marks_unavailable_after_max_attempts(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count)
                VALUES (?, 'running', ?, ?, ?, 'failed', ?)
                """,
                ("unavailable_weather.fit", "2026-06-20T09:17:58+08:00", 39.95, 116.38, main.WEATHER_BACKFILL_MAX_ATTEMPTS - 1),
            )
            activity_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with mock.patch("main.fetch_historical_weather", return_value=None):
            main._run_weather_backfill_worker(str(profile_backend.DB_PATH), limit=10)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT weather_status, weather_attempt_count FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["weather_status"], "unavailable")
        self.assertEqual(row["weather_attempt_count"], main.WEATHER_BACKFILL_MAX_ATTEMPTS)

    def test_weather_backfill_force_retries_unavailable_and_ignores_cooldown(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count, weather_updated_at)
                VALUES (?, 'running', ?, ?, ?, 'unavailable', ?, ?)
                """,
                (
                    "force_weather.fit",
                    "2026-06-20T09:17:58+08:00",
                    39.95,
                    116.38,
                    main.WEATHER_BACKFILL_MAX_ATTEMPTS,
                    datetime.now().isoformat(),
                ),
            )
            activity_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        with mock.patch("main.fetch_historical_weather", return_value={"temperature_c": 30, "weather_label": "晴"}):
            main._run_weather_backfill_worker(str(profile_backend.DB_PATH), limit=10, force=True)

        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT weather_json, weather_status, weather_attempt_count FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIn('"temperature_c": 30', row["weather_json"])
        self.assertEqual(row["weather_status"], "success")
        self.assertEqual(row["weather_attempt_count"], main.WEATHER_BACKFILL_MAX_ATTEMPTS + 1)

    def test_manual_weather_backfill_start_uses_force(self):
        main.ensure_activity_sync_schema()
        conn = profile_backend._conn()
        try:
            conn.execute(
                """
                INSERT INTO activities
                    (filename, sport_type, start_time, start_lat, start_lon, weather_status, weather_attempt_count, weather_updated_at)
                VALUES (?, 'running', ?, ?, ?, 'unavailable', ?, ?)
                """,
                (
                    "manual_force_weather.fit",
                    "2026-06-20T09:17:58+08:00",
                    39.95,
                    116.38,
                    main.WEATHER_BACKFILL_MAX_ATTEMPTS,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        with main._WEATHER_BACKFILL_LOCK:
            main._WEATHER_BACKFILL_STATUS["finished_at"] = time.time()
            main._WEATHER_BACKFILL_STATUS["running"] = False
        with mock.patch.object(main, "_run_weather_backfill_worker") as worker:
            status = main._start_weather_backfill_if_needed(limit=10, force=True)
            thread = getattr(main, "_WEATHER_BACKFILL_THREAD", None)
            if thread and thread.is_alive():
                thread.join(timeout=2.0)

        self.assertTrue(status["running"])
        worker.assert_called_once()

    def test_track_html_exposes_detail_weather_backfill_button_only(self):
        html = Path("track.html").read_text(encoding="utf-8")
        self.assertNotIn("backfillSportHubWeather()", html)
        self.assertNotIn("sport-records-weather-btn", html)
        self.assertIn("backfillActivityWeather", html)
        self.assertIn("backfill_activity_weather", html)
        self.assertIn("activity-weather-backfill-btn", html)

    def test_batch_import_tracks_imports_normal_zip_fit_only(self):
        zip_path = self.temp_dir / "normal.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("normal.fit", b"fit")

        with mock.patch.object(main, "_sync_single_fit_file", return_value={"ok": True}):
            res = self.api.batch_import_tracks([str(zip_path)])

        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["data"]["imported"]), 1)
        self.assertTrue(Path(res["data"]["imported"][0]).is_file())
        self.assertEqual(Path(res["data"]["imported"][0]).parent, Path(main.TRACKS_DIR))

    def test_safe_extract_zip_rejects_path_traversal(self):
        zip_path = self.temp_dir / "traversal.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.fit", b"fit")

        with zipfile.ZipFile(zip_path, "r") as zf:
            report = self.api.safe_extract_zip(zf, main.IMPORTS_DIR)

        self.assertFalse((self.temp_dir / "evil.fit").exists())
        self.assertEqual(report["extracted"], [])
        self.assertTrue(report["errors"])

    def test_safe_extract_zip_rejects_too_many_members(self):
        zip_path = self.temp_dir / "many.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.fit", b"fit")
            zf.writestr("b.fit", b"fit")

        with mock.patch.object(main, "ZIP_MAX_MEMBERS", 1):
            with zipfile.ZipFile(zip_path, "r") as zf:
                report = self.api.safe_extract_zip(zf, main.IMPORTS_DIR)

        self.assertEqual(report["extracted"], [])
        self.assertEqual(report["errors"][0]["error"], "ZIP 成员数量超过单次上传上限")

    def test_safe_extract_zip_rejects_oversized_member(self):
        zip_path = self.temp_dir / "large.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("large.fit", b"abcdef")

        with mock.patch.object(main, "ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES", 3):
            with zipfile.ZipFile(zip_path, "r") as zf:
                report = self.api.safe_extract_zip(zf, main.IMPORTS_DIR)

        self.assertEqual(report["extracted"], [])
        self.assertEqual(report["errors"][0]["error"], "ZIP 成员解压大小超过上限")

    def test_safe_extract_zip_skips_non_fit_members(self):
        zip_path = self.temp_dir / "mixed.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("note.txt", b"text")
            zf.writestr("ok.fit", b"fit")

        with zipfile.ZipFile(zip_path, "r") as zf:
            report = self.api.safe_extract_zip(zf, main.IMPORTS_DIR)

        self.assertEqual(len(report["extracted"]), 1)
        self.assertEqual(report["skipped"][0]["reason"], "unsupported_extension")
        self.assertFalse((Path(main.IMPORTS_DIR) / "note.txt").exists())

    def test_track_backend_parse_fit_file_prefers_local_start_time_for_weather(self):
        fake_core = {
            "basic_info": {
                "title": "晨跑",
                "title_source": "sport_name",
                "sport": "running",
                "sub_sport": "unknown",
                "start_time": "2024-03-01T06:30:00+08:00",
                "start_time_utc": "2024-02-29T22:30:00Z",
                "total_distance_km": 10.0,
                "total_timer_time": 3600,
                "total_calories": 650,
                "total_ascent": 88.0,
                "max_altitude": 32.0,
            },
            "track_data": [
                {"lat": 30.67, "lon": 104.06, "alt": 10.0, "time": "2024-02-29T22:30:00Z", "hr": 145},
            ],
        }
        with mock.patch.object(track_backend.FITCoreEngine, "parse_fit_file", return_value=fake_core), \
             mock.patch("track_backend.fetch_historical_weather", return_value=None) as mocked_weather:
            track_backend.parse_fit_file(self.temp_dir / "track_backend.fit")

        self.assertEqual(mocked_weather.call_args.args[2], "2024-03-01T06:30:00+08:00")

    def test_build_base_system_block_includes_weather_context(self):
        prompt = llm_backend.build_base_system_block(
            sport_type="running",
            provider="local_mcp",
            track_filename="sample.fit",
            points=[{"lat": 30.67, "lon": 104.06, "alt": 10.0, "time": "2024-03-01T06:30:00Z", "dist": 0}],
            placemarks=[],
            weather_context={
                "temperature_c": 28,
                "humidity": 85,
                "wind_speed_kmh": 11,
                "weather_label": "阴",
            },
        )
        self.assertIn("本次运动时的环境为", prompt)
        self.assertIn("温度 28°C", prompt)
        self.assertIn("湿度 85%", prompt)

    def test_check_daily_sync_status_basic(self):
        api = main.Api()
        profile_backend.mark_sync_done()
        status = api.check_daily_sync_status()
        self.assertFalse(status["needs_sync"])

    # 验证画像同步状态指示器元数据：覆盖 pending / syncing / synced_today / failed 四种状态
    def test_sync_metadata_initial_state_is_pending(self):
        profile_backend.write_sync_state({})
        conn = profile_backend._conn()
        try:
            conn.execute("DELETE FROM user_profile")
            conn.commit()
        finally:
            conn.close()
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "idle",
            "无任何同步记录时 sync_status 应为 idle，前端会显示'待同步'")
        self.assertEqual(meta["last_sync_ago"], "从未同步")
        self.assertEqual(meta["connection_status"], "unknown")

    def test_sync_metadata_active_job_is_syncing(self):
        profile_backend.write_sync_state({
            "active_job_id": "abc123",
            "last_attempt_at": "2024-01-01T00:00:00",
            "last_attempt_status": "syncing",
            "connection_status": "connected",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "syncing",
            "active_job_id 存在时 sync_status 应为 syncing，前端显示'同步中...'动画")
        self.assertEqual(meta["connection_status"], "connected")

    def test_sync_metadata_today_success_is_synced(self):
        import datetime as _dt
        today = _dt.date.today().isoformat()
        now_iso = _dt.datetime.now().isoformat()
        profile_backend.write_sync_state({
            "last_sync_date": today,
            "last_sync_time": now_iso,
            "last_attempt_status": "success",
            "synced_today": True,
            "connection_status": "connected",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "success_today",
            "last_sync_date 为今天时 sync_status 应为 success_today，前端显示'今日已同步'")
        self.assertIn("今天", meta["last_sync_ago"])

    def test_sync_metadata_yesterday_success_is_not_synced_today(self):
        import datetime as _dt
        from datetime import timedelta
        yesterday_date = _dt.date.today() - timedelta(days=1)
        yesterday = yesterday_date.isoformat()
        yesterday_dt = _dt.datetime.combine(yesterday_date, _dt.time(7, 0))
        profile_backend.write_sync_state({
            "last_sync_date": yesterday,
            "last_sync_time": yesterday_dt.isoformat(),
            "last_attempt_status": "success",
            "synced_today": False,
            "connection_status": "connected",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertNotEqual(meta["sync_status"], "success_today",
            "昨天同步过但今天没同步时 sync_status 不应为 success_today，"
            "前端会落到'待同步'分支（connection=connected 且 sync_status 非 success_today/failed）")
        self.assertIn("昨天", meta["last_sync_ago"])

    def test_sync_metadata_failed_is_failed_retryable(self):
        import datetime as _dt
        profile_backend.write_sync_state({
            "last_attempt_at": _dt.datetime.now().isoformat(),
            "last_attempt_status": "failed_retryable",
            "last_error": "MCP 同步失败: timeout",
            "connection_status": "connected",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "failed_retryable",
            "上次同步失败时 sync_status 应为 failed_retryable，前端显示'同步失败，等待重试'")
        self.assertEqual(meta["last_error"], "MCP 同步失败: timeout")

    def test_sync_metadata_active_job_overrides_today_success(self):
        today = profile_backend.date.today().isoformat()
        profile_backend.write_sync_state({
            "active_job_id": "running",
            "last_sync_date": today,
            "last_attempt_status": "success",
            "synced_today": True,
            "connection_status": "connected",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "syncing",
            "active_job_id 存在时应优先于 success_today，前端显示'同步中...'动画")

    def test_sync_metadata_disconnected_when_blocked(self):
        import datetime as _dt
        profile_backend.write_sync_state({
            "last_attempt_at": _dt.datetime.now().isoformat(),
            "last_attempt_status": "blocked",
            "connection_status": "disconnected",
            "last_error": "LLM 网关未配置",
        })
        meta = profile_backend.get_profile_sync_metadata()
        self.assertEqual(meta["sync_status"], "blocked")
        self.assertEqual(meta["connection_status"], "disconnected")

    # 验证增量同步预检机制：已入库未变更文件被跳过，新增文件被解析
    def test_incremental_sync_skips_unchanged_files_and_parses_new_only(self):
        main.ensure_activity_sync_schema()

        fit_files = []
        for name in ("old_a.fit", "old_b.fit", "new_c.fit"):
            path = self.temp_dir / name
            path.write_bytes(b"fit")
            fit_files.append(path)

        for f in fit_files[:2]:
            stat = f.stat()
            conn = profile_backend._conn()
            try:
                conn.execute(
                    "INSERT INTO activities "
                    "(file_name, filename, file_path, title, sport_type, sub_sport_type, "
                    "dist_km, duration_sec, avg_hr, file_mtime, file_size, points_json, "
                    "start_time, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                    (f.name, f.name, str(f.resolve()), f.name, "running", "unknown",
                     5.0, 1800, 140, stat.st_mtime, stat.st_size, "[]"),
                )
                conn.commit()
            finally:
                conn.close()

        conn = profile_backend._conn()
        try:
            index = main._load_existing_file_index(conn)
        finally:
            conn.close()

        self.assertEqual(len(index), 2)
        for f in fit_files[:2]:
            resolved = str(f.resolve())
            self.assertIn(resolved, index)
            self.assertTrue(main._is_file_unchanged(f, index[resolved]))
        self.assertNotIn(str(fit_files[2].resolve()), index)

        pending_files = []
        pre_skipped = 0
        for fit_path in fit_files:
            resolved = str(fit_path.resolve())
            existing = index.get(resolved)
            if existing and main._is_file_unchanged(fit_path, existing):
                pre_skipped += 1
            else:
                pending_files.append(fit_path)

        self.assertEqual(pre_skipped, 2)
        self.assertEqual(len(pending_files), 1)
        self.assertEqual(pending_files[0].name, "new_c.fit")

    def test_incremental_sync_detects_changed_files(self):
        main.ensure_activity_sync_schema()

        f = self.temp_dir / "changed.fit"
        f.write_bytes(b"old_content")
        stat = f.stat()

        conn = profile_backend._conn()
        try:
            conn.execute(
                "INSERT INTO activities "
                "(file_name, filename, file_path, title, sport_type, sub_sport_type, "
                "dist_km, duration_sec, avg_hr, file_mtime, file_size, points_json, "
                "start_time, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (f.name, f.name, str(f.resolve()), f.name, "running", "unknown",
                 5.0, 1800, 140, stat.st_mtime, stat.st_size, "[]"),
            )
            conn.commit()
        finally:
            conn.close()

        conn = profile_backend._conn()
        try:
            index = main._load_existing_file_index(conn)
        finally:
            conn.close()
        resolved = str(f.resolve())
        self.assertIn(resolved, index)
        self.assertTrue(main._is_file_unchanged(f, index[resolved]))

        import time as _time
        _time.sleep(0.05)
        f.write_bytes(b"new_content_that_changes_file_size_and_mtime")
        self.assertFalse(main._is_file_unchanged(f, index[resolved]))

    def test_migration_creates_all_activity_columns_on_old_schema(self):
        old_db = self.temp_dir / "old_user_profile.db"
        old_conn = sqlite3.connect(str(old_db))
        old_conn.execute("""
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                sport_type TEXT,
                dist_km REAL,
                duration_sec INTEGER,
                avg_hr INTEGER,
                start_time TEXT
            )
        """)
        old_conn.execute("""
            CREATE TABLE user_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT
            )
        """)
        old_conn.commit()
        old_conn.close()

        with mock.patch.object(profile_backend, "DB_PATH", old_db):
            profile_backend._SCHEMA_READY_FOR = None
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
            main.ensure_activity_sync_schema()

        conn = sqlite3.connect(str(old_db))
        conn.row_factory = sqlite3.Row
        try:
            existing = set()
            for row in conn.execute("PRAGMA table_info(activities)").fetchall():
                existing.add(str(row["name"]))

            expected = {
                "id", "filename", "sport_type", "dist_km", "duration_sec", "avg_hr", "start_time",
                "file_name", "distance", "duration", "track_json",
                "advanced_metrics",
                "title", "title_source",
                "sub_sport_type", "file_path",
                "start_time_utc", "start_lat", "start_lon",
                "region", "region_city", "region_country", "region_display",
                "region_status", "region_error", "region_updated_at", "region_attempt_count",
                "weather_json", "weather_status", "weather_updated_at",
                "weather_attempt_count", "weather_error",
                "file_mtime", "file_size", "deleted_at",
                "avg_pace", "calories", "avg_power", "max_power", "normalized_power",
                "avg_stroke_distance", "swolf", "list_metric_backfill_version",
                "device_name", "source_type", "is_mock", "shadow_diff_json",
                "hr_curve", "speed_curve",
                "gain_m", "max_alt_m", "max_hr", "avg_cadence",
                "hr_decoupling", "tss", "points_json", "updated_at",
            }
            missing = expected - existing
            self.assertEqual(missing, set(), f"缺少列: {sorted(missing)}")
        finally:
            conn.close()

    def test_migration_is_idempotent(self):
        db = self.temp_dir / "idem_user_profile.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE activities (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, sport_type TEXT)
        """)
        conn.execute("CREATE TABLE user_profile (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
        conn.close()

        with mock.patch.object(profile_backend, "DB_PATH", db):
            profile_backend._SCHEMA_READY_FOR = None
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

            for _ in range(3):
                main.ensure_activity_sync_schema()

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            col_count = len(conn.execute("PRAGMA table_info(activities)").fetchall())
            self.assertGreater(col_count, 20)
            conn.execute("SELECT file_name FROM activities")
            conn.execute("SELECT shadow_diff_json FROM activities")
        finally:
            conn.close()

    def test_user_profile_snapshots_table_exists(self):
        db = self.temp_dir / "snap_profile.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE user_profile (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
        conn.close()

        with mock.patch.object(profile_backend, "DB_PATH", db):
            profile_backend._SCHEMA_READY_FOR = None
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
            main.ensure_activity_sync_schema()

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("PRAGMA table_info(user_profile_snapshots)").fetchall()
            self.assertGreater(len(rows), 0)
            snapshot_cols = {str(r["name"]) for r in rows}
            required = {"id", "source_platform", "trigger_type", "status",
                        "synced_at", "sync_date", "raw_payload_json", "normalized_json"}
            self.assertTrue(required.issubset(snapshot_cols),
                            f"user_profile_snapshots 缺少列: {required - snapshot_cols}")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
