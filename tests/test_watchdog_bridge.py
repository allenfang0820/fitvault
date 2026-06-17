import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import main
import profile_backend


class FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script: str):
        self.calls.append(script)


class TestWatchdogBridge(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main._APP_SHUTTING_DOWN.clear()
        self.api = main.Api()

    def tearDown(self):
        if self.api._profile_sync_timer is not None:
            self.api._profile_sync_timer.cancel()
        if self.api._region_enrichment_timer is not None:
            self.api._region_enrichment_timer.cancel()
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        self.temp_dir_obj.cleanup()

    def test_new_track_notification_is_queued_until_frontend_ready(self):
        window = FakeWindow()
        self.api.bind_window(window)

        target_path = self.temp_dir / "queued.fit"
        self.api.notify_new_track_detected(str(target_path), 42)
        self.assertEqual(window.calls, [])

        self.api.notify_frontend_ready()
        self.assertEqual(len(window.calls), 1)
        self.assertIn("window.onNewTrackDetected", window.calls[0])
        self.assertIn(json.dumps(str(target_path.resolve())), window.calls[0])
        self.assertIn("42", window.calls[0])

    def test_notify_frontend_ready_only_schedules_background_tasks(self):
        created_timers = []

        class FakeTimer:
            def __init__(self, delay, callback):
                self.delay = delay
                self.callback = callback
                self.daemon = False
                self.started = False
                created_timers.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.started = False

        with mock.patch.object(self.api, "startup_sync_check") as startup_check, \
             mock.patch.object(profile_backend, "start_region_enrichment_background") as region_start, \
             mock.patch.object(main.threading, "Timer", FakeTimer):
            res = self.api.notify_frontend_ready()
            self.api.notify_frontend_ready()

        self.assertEqual(res, {"ok": True})
        startup_check.assert_not_called()
        region_start.assert_not_called()
        self.assertEqual(len(created_timers), 2)
        self.assertEqual(created_timers[0].delay, main.PROFILE_STARTUP_SYNC_DELAY_SEC)
        self.assertEqual(created_timers[1].delay, main.REGION_ENRICH_STARTUP_DELAY_SEC)
        self.assertTrue(all(timer.started for timer in created_timers))

    def test_load_activity_track_by_file_path_prefers_sqlite_record(self):
        file_path = self.temp_dir / "replay.fit"
        file_path.write_bytes(b"fit")
        main.ensure_activity_sync_schema()

        activity_id = profile_backend.save_activity(
            {
                "filename": file_path.name,
                "title": "回放样本",
                "title_source": "filename",
                "sport_type": "running",
                "sub_sport_type": "unknown",
                "dist_km": 5.0,
                "duration_sec": 1500,
                "gain_m": 32.0,
                "max_alt_m": 18.0,
                "avg_hr": 148,
                "max_hr": 172,
                "points_json": [
                    {"lat": 30.1, "lon": 104.1, "time": "2026-05-19T08:00:00Z"},
                    {"lat": 30.2, "lon": 104.2, "time": "2026-05-19T08:10:00Z"},
                ],
                "file_path": str(file_path.resolve()),
                "start_time": "2026-05-19T08:00:00Z",
                "start_time_utc": "2026-05-19T08:00:00Z",
            }
        )

        res = self.api.load_activity_track_by_file_path(str(file_path))
        self.assertTrue(res["ok"], res)
        self.assertEqual((res.get("activity") or {}).get("id"), activity_id)
        self.assertEqual(len((res.get("data") or {}).get("points") or []), 2)

    def test_watch_service_batches_new_fit_files_and_deduplicates_same_file(self):
        file_a = self.temp_dir / "batch_a.fit"
        file_b = self.temp_dir / "batch_b.fit"
        file_a.write_bytes(b"a-fit")
        file_b.write_bytes(b"b-fit")

        fake_api = mock.Mock()
        fake_api.start_sync_local_fit_files.return_value = {"ok": True, "job_id": "job-1"}
        fake_api.get_sync_local_fit_files_status.return_value = {
            "ok": True,
            "job_id": "job-1",
            "state": "done",
            "result": {"ok": True},
        }
        fake_api.get_activity_by_file_path.side_effect = lambda file_path: {
            "ok": True,
            "activity": {
                "id": 101 if str(file_a.resolve()) == file_path else 202
            },
        }

        service = main.FITFolderWatchService(fake_api, debounce_sec=0.05, stable_wait_sec=0.01)
        try:
            service._enqueue_created_file(str(file_a))
            service._enqueue_created_file(str(file_a))
            service._enqueue_created_file(str(file_b))
            self._wait_until(lambda: fake_api.notify_new_track_detected.call_count == 2)

            self.assertEqual(fake_api.start_sync_local_fit_files.call_count, 1)
            self.assertEqual(fake_api.notify_new_track_detected.call_count, 2)

            fake_api.notify_new_track_detected.reset_mock()
            service._enqueue_created_file(str(file_a))
            time.sleep(0.15)
            self.assertEqual(fake_api.start_sync_local_fit_files.call_count, 1)
            self.assertEqual(fake_api.notify_new_track_detected.call_count, 0)
        finally:
            service.stop()

    def _wait_until(self, predicate, timeout_sec: float = 1.5):
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail(f"条件未在 {timeout_sec} 秒内满足")


if __name__ == "__main__":
    unittest.main()
