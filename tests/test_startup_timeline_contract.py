import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import main


class TestStartupTimelineContract(unittest.TestCase):
    def setUp(self):
        with main._STARTUP_TIMELINE_LOCK:
            main._STARTUP_TIMELINE.clear()

    def test_record_startup_event_and_api_snapshot_are_read_only(self):
        api = main.Api()
        main._record_startup_event("unit_test_event", value=42)

        res = api.get_startup_timeline()

        self.assertTrue(res["ok"], res)
        data = res["data"]
        self.assertIsInstance(data["process_elapsed_ms"], float)
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["name"], "unit_test_event")
        self.assertEqual(data["events"][0]["value"], 42)

    def test_activity_list_response_exposes_startup_trace_without_running_backfill(self):
        api = main.Api()
        with mock.patch.object(main.profile_backend, "get_activity_list_filtered", return_value=([], 0)), \
             mock.patch.object(main.profile_backend, "_conn") as conn_factory, \
             mock.patch.object(main, "_schedule_normalized_power_backfill_if_needed", return_value={"scheduled": True}):
            conn = mock.Mock()
            conn.execute.return_value.fetchall.return_value = []
            conn_factory.return_value = conn
            res = api.get_activity_list(page=1, page_size=10, sport_filter="all")

        self.assertTrue(res["ok"], res)
        trace = res["data"]["startup_trace"]
        self.assertIsInstance(trace["api_elapsed_ms"], float)
        self.assertIsInstance(trace["process_elapsed_ms"], float)
        events = main._startup_timeline_snapshot()
        self.assertEqual(events[-1]["name"], "activity_list_api")

    def test_windows_packaged_startup_log_writes_utf8_jsonl(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(main, "_windows_packaged_startup_log_enabled", return_value=True), \
                 mock.patch.dict(main.os.environ, {"USERPROFILE": temp}, clear=False):
                main._record_startup_event("window_show", message="脉图")

            log_path = Path(temp) / ".fitvault" / "logs" / "startup.log"
            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])

        self.assertEqual(payload["name"], "window_show")
        self.assertEqual(payload["message"], "脉图")

    def test_main_window_visibility_is_windows_visible_macos_hidden(self):
        class FakeEvents:
            def __init__(self):
                self.loaded = mock.Mock()

        class FakeWindow:
            def __init__(self):
                self.events = FakeEvents()

            def show(self):
                raise AssertionError("Windows visible-on-create path should not call show during startup")

        def run_for_platform(platform_name):
            fake_window = FakeWindow()
            fake_webview = types.SimpleNamespace(
                create_window=mock.Mock(return_value=fake_window),
                start=mock.Mock(),
            )
            fake_watch = mock.Mock()
            fake_watch_cls = mock.Mock(return_value=fake_watch)
            with mock.patch.dict(sys.modules, {"webview": fake_webview}), \
                 mock.patch.object(main.sys, "platform", platform_name), \
                 mock.patch.object(main, "set_runtime_app_icon"), \
                 mock.patch.object(main, "_get_schema_version", return_value=main.CURRENT_SCHEMA_VERSION), \
                 mock.patch.object(main, "html_file", return_value=Path("/tmp/track.html")), \
                 mock.patch.object(main, "FITFolderWatchService", fake_watch_cls):
                main.main()
            return fake_webview.create_window.call_args.kwargs

        windows_kwargs = run_for_platform("win32")
        macos_kwargs = run_for_platform("darwin")

        self.assertFalse(windows_kwargs["hidden"])
        self.assertFalse(windows_kwargs["frameless"])
        self.assertTrue(macos_kwargs["hidden"])
        self.assertTrue(macos_kwargs["frameless"])


if __name__ == "__main__":
    unittest.main()
