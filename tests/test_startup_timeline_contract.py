import unittest
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


if __name__ == "__main__":
    unittest.main()
