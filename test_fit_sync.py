import sqlite3
import tempfile
import threading
import time
import unittest
import json
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

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        self.api = main.Api()

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        profile_backend.SQLITE_BUSY_TIMEOUT_MS = self.original_busy_timeout_ms
        profile_backend.SQLITE_CONNECT_TIMEOUT_SEC = self.original_connect_timeout_sec
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

    def test_bypass_daily_sync_limit_via_api_endpoints(self):
        api = main.Api()
        # 默认关闭
        res = api.get_test_bypass_daily_sync_limit()
        self.assertTrue(res["ok"])
        self.assertFalse(res["enabled"])

        # 开启
        res = api.set_test_bypass_daily_sync_limit(True)
        self.assertTrue(res["ok"])
        self.assertTrue(res["enabled"])
        self.assertTrue(profile_backend.get_test_bypass_daily_sync_limit())

        # 关闭
        res = api.set_test_bypass_daily_sync_limit(False)
        self.assertTrue(res["ok"])
        self.assertFalse(res["enabled"])
        self.assertFalse(profile_backend.get_test_bypass_daily_sync_limit())

    def test_bypass_makes_sync_needed_even_after_mark_done(self):
        profile_backend.set_test_bypass_daily_sync_limit(True)
        try:
            profile_backend.mark_sync_done()
            self.assertTrue(profile_backend.is_sync_needed_today(),
                "绕过开启时，即使标记为已同步，is_sync_needed_today 也应返回 True")
        finally:
            profile_backend.set_test_bypass_daily_sync_limit(False)

    def test_bypass_off_restores_sync_limit(self):
        profile_backend.set_test_bypass_daily_sync_limit(True)
        profile_backend.mark_sync_done()
        profile_backend.set_test_bypass_daily_sync_limit(False)
        self.assertFalse(profile_backend.is_sync_needed_today(),
            "绕过关闭后，已同步状态应恢复限制")

    def test_bypass_check_daily_sync_status_reflects_switch(self):
        api = main.Api()
        profile_backend.mark_sync_done()
        profile_backend.set_test_bypass_daily_sync_limit(True)
        try:
            status = api.check_daily_sync_status()
            self.assertTrue(status["needs_sync"],
                "API check_daily_sync_status 应反映绕过开关状态")
            self.assertTrue(status["ok"])
        finally:
            profile_backend.set_test_bypass_daily_sync_limit(False)

    def test_bypass_silent_fetch_respects_switch(self):
        profile_backend.mark_sync_done()
        profile_backend.set_test_bypass_daily_sync_limit(True)
        try:
            result = main.Api().silent_fetch_mcp_persona("garmin")
            self.assertFalse(result.get("already_synced", True),
                "绕过开启时 silent_fetch_mcp_persona 不应标记 already_synced")
        finally:
            profile_backend.set_test_bypass_daily_sync_limit(False)

    def test_bypass_off_silent_fetch_returns_already_synced(self):
        profile_backend.mark_sync_done()
        profile_backend.set_test_bypass_daily_sync_limit(False)
        result = main.Api().silent_fetch_mcp_persona("garmin")
        self.assertTrue(result.get("already_synced", False),
            "绕过关闭时 silent_fetch_mcp_persona 应返回 already_synced=True")

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


if __name__ == "__main__":
    unittest.main()
