import os
import sqlite3
import tempfile
import threading
import time
import types
import unittest
import json
import zipfile
from pathlib import Path
from unittest import mock

import main
import llm_backend
import profile_backend
import track_backend
from utils.weather_api import fetch_historical_weather


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

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.TRACKS_DIR = str(self.temp_dir / "tracks")
        main.IMPORTS_DIR = str(self.temp_dir / "imports")
        profile_backend.SYNC_STATE_DIR = str(self.temp_dir / "sync_state")
        profile_backend.SYNC_STATE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "sync_state.json")
        profile_backend.PROFILE_CACHE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "user_profile_cache.json")
        Path(main.TRACKS_DIR).mkdir(parents=True, exist_ok=True)
        Path(main.IMPORTS_DIR).mkdir(parents=True, exist_ok=True)
        Path(profile_backend.SYNC_STATE_DIR).mkdir(parents=True, exist_ok=True)
        self.api = main.Api()

    def tearDown(self):
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
            "track_json": "[]",
            "points_json": "[]",
            "file_path": resolved,
            "gain_m": 120.0,
            "max_alt_m": 60.0,
            "start_lat": 30.67,
            "start_lon": 104.06,
            "region": "成都市",
        }

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
        fit_path.write_bytes(b"fit")
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
            path.write_bytes(b"fit")
            fit_files.append(path)

        def parse_side_effect(path_obj):
            time.sleep(0.08)
            return self._activity(Path(path_obj).name)

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
            path.write_bytes(b"fit")
            fit_files.append(path)

        def parse_side_effect(path_obj):
            time.sleep(0.25)
            return self._activity(Path(path_obj).name)

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
        fit_path.write_bytes(b"fit")

        with mock.patch.object(main, "resolve_workspace_track_dir", return_value=self._workspace_config()), \
             mock.patch.object(main, "_walk_fit_files", return_value=[fit_path]), \
             mock.patch.object(main, "_parse_fit_activity_for_sync", return_value=self._activity("single.fit")):
            result = self.api.sync_local_fit_files()

        self.assertTrue(result["ok"], result)
        self.assertLess(result.get("elapsed_sec", 99), 1.0)

    def test_remote_fit_sync_sends_date_range_prompt_to_openclaw(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
        }), mock.patch.object(llm_backend, "chat_completions", return_value="下载完成") as chat_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertTrue(result["ok"], result)
        kwargs = chat_mock.call_args.kwargs
        self.assertEqual(kwargs["model"], "openclaw")
        prompt_text = "\n".join(message["content"] for message in kwargs["messages"])
        self.assertIn("2026-05-01 至 2026-05-31", prompt_text)
        self.assertIn(main.TRACKS_DIR, prompt_text)
        self.assertIn("FIT 文件", prompt_text)

    def test_remote_fit_sync_rejects_invalid_date_range(self):
        api = object.__new__(main.Api)
        result = api.sync_remote_fit_activities("2026-06-01", "2026-05-01")
        self.assertFalse(result["ok"], result)
        self.assertIn("开始日期不能晚于结束日期", result["error"])

    def test_remote_fit_sync_rejects_coros_without_calling_openclaw(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
        }), mock.patch.object(llm_backend, "chat_completions") as chat_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertIn("暂不支持按时间同步活动", result["error"])
        chat_mock.assert_not_called()

    def test_remote_fit_sync_rejects_empty_brand_without_calling_openclaw(self):
        api = object.__new__(main.Api)
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "",
        }), mock.patch.object(llm_backend, "chat_completions") as chat_mock:
            result = api.sync_remote_fit_activities("2026-05-01", "2026-05-31")

        self.assertFalse(result["ok"], result)
        self.assertIn("暂不支持按时间同步活动", result["error"])
        chat_mock.assert_not_called()

    def test_pick_and_import_fit_files_uses_batch_import_tracks(self):
        selected = [str(self.temp_dir / "manual.fit")]
        fake_window = mock.Mock()
        fake_window.create_file_dialog.return_value = selected
        fake_file_dialog = types.SimpleNamespace(OPEN="open")
        fake_webview = types.SimpleNamespace(windows=[fake_window], FileDialog=fake_file_dialog)

        with mock.patch.dict("sys.modules", {
            "webview": fake_webview,
        }), mock.patch.object(self.api, "batch_import_tracks", return_value={"ok": True, "imported": selected, "errors": None}) as import_mock, \
             mock.patch.object(llm_backend, "chat_completions") as chat_mock:
            result = self.api.pick_and_import_fit_files()

        self.assertTrue(result["ok"], result)
        import_mock.assert_called_once_with(selected)
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
            activity_id = snapshot["records"][0]["id"]
            detail = self.api.get_activity_detail(activity_id)

        self.assertIn(activity_res.get("op"), {"inserted", "updated"})
        self.assertTrue(snapshot["ok"], snapshot)
        self.assertEqual(snapshot["records"][0]["region"], "成都市")
        self.assertTrue(detail["ok"], detail)
        self.assertEqual(detail["record"]["region"], "成都市")
        self.assertIn("display_metrics", detail["record"]["detail"])
        self.assertIn("layout", detail["record"]["detail"])
        self.assertIn("capabilities", detail["record"]["detail"])

    def test_shadow_diff_json_persists_updates_and_returns(self):
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
        self.assertEqual(list_res["records"][0]["shadow_diff"], updated_diff)
        self.assertTrue(detail["ok"], detail)
        self.assertEqual(detail["record"]["shadow_diff"], updated_diff)

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
        self.assertEqual(kwargs["params"]["end_date"], "2024-03-01")
        self.assertEqual(kwargs["params"]["timezone"], "auto")

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

    def test_batch_import_tracks_imports_normal_zip_fit_only(self):
        zip_path = self.temp_dir / "normal.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("normal.fit", b"fit")

        with mock.patch.object(main, "_sync_single_fit_file", return_value={"ok": True}):
            res = self.api.batch_import_tracks([str(zip_path)])

        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["imported"]), 1)
        self.assertTrue(Path(res["imported"][0]).is_file())
        self.assertEqual(Path(res["imported"][0]).parent, Path(main.TRACKS_DIR))

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
        self.assertEqual(report["errors"][0]["error"], "ZIP 成员数量超过上限")

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
                "weather_json", "file_mtime", "file_size", "deleted_at",
                "avg_pace", "calories", "normalized_power", "swolf",
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
