import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import profile_backend


class TestDuplicateActivityLogging(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = profile_backend.DB_PATH
        self.original_schema_ready = profile_backend._SCHEMA_READY_FOR
        profile_backend.DB_PATH = Path(self.temp_dir.name) / "duplicate.sqlite"
        profile_backend._SCHEMA_READY_FOR = None
        conn = profile_backend._conn()
        conn.close()

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_schema_ready
        self.temp_dir.cleanup()

    def _insert_activity(
        self,
        *,
        filename: str,
        start_time: str | None,
        dist_km: float = 10.0,
        duration_sec: int = 3600,
        points: list[dict] | None = None,
    ) -> int:
        conn = profile_backend._conn()
        try:
            cursor = conn.execute(
                """
                INSERT INTO activities
                    (filename, start_time, dist_km, duration_sec, points_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filename, start_time, dist_km, duration_sec, json.dumps(points or [])),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _clear_activities(self) -> None:
        conn = profile_backend._conn()
        try:
            conn.execute("DELETE FROM activities")
            conn.commit()
        finally:
            conn.close()

    def test_info_log_count_is_constant_and_exclusions_are_debug_only(self):
        def run_with_candidates(count: int):
            self._clear_activities()
            for index in range(count):
                self._insert_activity(
                    filename=f"history-{index}.fit",
                    start_time=f"2023-01-{index + 2:02d}T10:00:00Z",
                )
            test_logger = mock.Mock()
            with mock.patch.object(profile_backend, "_duplicate_check_logger", return_value=test_logger):
                result = profile_backend.check_duplicate_activity(
                    start_time="2023-01-01T10:00:00Z",
                    dist_km=10.0,
                    duration_sec=3600,
                    points_json=[],
                )
            return result, test_logger

        small_result, small_logger = run_with_candidates(2)
        large_result, large_logger = run_with_candidates(20)

        self.assertFalse(small_result["is_duplicate"])
        self.assertFalse(large_result["is_duplicate"])
        self.assertEqual(small_logger.info.call_count, 2)
        self.assertEqual(large_logger.info.call_count, 2)
        info_templates = " ".join(call.args[0] for call in large_logger.info.call_args_list)
        debug_templates = " ".join(call.args[0] for call in large_logger.debug.call_args_list)
        self.assertNotIn("排除", info_templates)
        self.assertNotIn("查重得分", info_templates)
        self.assertIn("排除", debug_templates)

    def test_duplicate_result_and_best_match_are_unchanged(self):
        points = [
            {"lat": 30.0001, "lon": 104.0001, "time": "2023-01-01T10:00:00Z"},
            {"lat": 30.0002, "lon": 104.0002, "time": "2023-01-01T10:00:10Z"},
        ]
        expected_id = self._insert_activity(
            filename="exact.fit",
            start_time="2023-01-01T10:00:00Z",
            points=points,
        )
        test_logger = mock.Mock()
        with mock.patch.object(profile_backend, "_duplicate_check_logger", return_value=test_logger):
            result = profile_backend.check_duplicate_activity(
                start_time="2023-01-01T10:00:00Z",
                dist_km=10.0,
                duration_sec=3600,
                points_json=points,
            )

        self.assertTrue(result["is_duplicate"])
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["duplicate_record"]["id"], expected_id)
        self.assertNotIn("points_json", result["duplicate_record"])
        self.assertEqual(test_logger.info.call_count, 2)
        self.assertTrue(any("查重得分" in call.args[0] for call in test_logger.debug.call_args_list))

    def test_points_time_fallback_and_300_second_threshold_remain_intact(self):
        points = [
            {"lat": 30.0, "lon": 104.0, "time": "2023-01-01T10:00:00Z"},
            {"lat": 30.001, "lon": 104.001, "time": "2023-01-01T10:00:10Z"},
        ]
        boundary_points = [
            {**point, "time": time_value}
            for point, time_value in zip(
                points,
                ("2023-01-01T10:05:00Z", "2023-01-01T10:05:10Z"),
            )
        ]
        outside_points = [
            {**point, "time": time_value}
            for point, time_value in zip(
                points,
                ("2023-01-01T10:05:01Z", "2023-01-01T10:05:11Z"),
            )
        ]
        self._insert_activity(filename="points-time.fit", start_time=None, points=points)
        with mock.patch.object(profile_backend, "_duplicate_check_logger", return_value=mock.Mock()):
            fallback = profile_backend.check_duplicate_activity(
                start_time=None,
                dist_km=10.0,
                duration_sec=3600,
                points_json=points,
            )
            at_boundary = profile_backend.check_duplicate_activity(
                start_time="2023-01-01T10:05:00Z",
                dist_km=10.0,
                duration_sec=3600,
                points_json=boundary_points,
            )
            outside_boundary = profile_backend.check_duplicate_activity(
                start_time="2023-01-01T10:05:01Z",
                dist_km=10.0,
                duration_sec=3600,
                points_json=outside_points,
            )

        self.assertTrue(fallback["is_duplicate"])
        self.assertTrue(at_boundary["is_duplicate"])
        self.assertFalse(outside_boundary["is_duplicate"])


if __name__ == "__main__":
    unittest.main()
