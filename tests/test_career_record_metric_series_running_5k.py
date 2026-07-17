import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


def _distance_points(items):
    return json.dumps([{"distance_m": distance, "t_sec": elapsed} for distance, elapsed in items])


def _create_schema(conn):
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            duration REAL,
            points_json TEXT,
            track_json TEXT,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )
    for table in (
        "career_pb_records",
        "career_event_candidates",
        "career_record_events",
        "career_ai_insights",
    ):
        conn.execute(f"CREATE TABLE {table} (id TEXT)")


def _counts(conn):
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "career_pb_records",
            "career_event_candidates",
            "career_record_events",
            "career_ai_insights",
        )
    }


def _insert_activity(conn, activity_id, date, elapsed_at_target, *, target_distance_m=5000, total_distance_m=None, sport="running"):
    total_distance = total_distance_m or target_distance_m + 1000
    points = [(0, 0)]
    # Keep synthetic streams dense enough to pass the resolver's max-gap quality guard.
    splits = max(1, int(elapsed_at_target // 1200) + 1)
    for index in range(1, splits + 1):
        fraction = index / splits
        points.append((round(target_distance_m * fraction, 3), round(elapsed_at_target * fraction, 3)))
    points.append((total_distance, elapsed_at_target + 400))
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock
        )
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            sport,
            f"{date}T08:00:00Z",
            total_distance / 1000.0,
            elapsed_at_target + 400,
            _distance_points(points),
        ),
    )


def _assert_no_forbidden_payload(testcase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for token in (
        "points_json",
        "track_json",
        "raw_fit",
        "raw_points",
        "file_path",
        "/Users/",
        "\\Users\\",
        "sqlite_master",
        "CREATE TABLE",
    ):
        testcase.assertNotIn(token, text)


def _assert_metric_series_contract(testcase, result):
    testcase.assertEqual(
        set(result),
        {
            "record_key",
            "sport",
            "display_name",
            "comparison",
            "axis_direction",
            "points",
            "current_best",
            "record_progression",
            "summary",
            "filters",
            "metrics",
            "status",
        },
    )
    testcase.assertEqual(
        set(result["summary"]),
        {
            "point_count",
            "eligible_count",
            "record_breaking_count",
            "current_best_activity_id",
            "first_point_date",
            "last_point_date",
            "status_counts",
        },
    )
    testcase.assertTrue(
        {
            "elapsed_ms",
            "scanned",
            "returned_count",
            "performance_target_ms",
            "readonly",
        }.issubset(result["metrics"])
    )
    testcase.assertTrue(result["metrics"]["readonly"])
    testcase.assertEqual(
        set(result["status"]),
        {"schema_ready", "data_ready", "state", "message", "resolver_version"},
    )
    testcase.assertIsInstance(result["points"], list)
    testcase.assertIsInstance(result["record_progression"], list)
    for point in result["points"]:
        testcase.assertTrue(
            {
                "id",
                "activity_id",
                "record_key",
                "sport",
                "event_date",
                "metric",
                "range",
                "quality",
                "scope",
                "detail_link",
                "source_mode",
                "resolver_version",
                "rule_version",
                "status",
                "eligible_for_current_best",
                "is_current_best",
                "is_record_breaking",
                "result_fingerprint",
            }.issubset(point)
        )
        testcase.assertTrue({"name", "value", "unit", "display"}.issubset(point["metric"]))
        testcase.assertTrue({"scope_hash", "scope_key", "labels", "dimensions"}.issubset(point["scope"]))


class CareerRecordMetricSeriesRunningStandardDistanceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_running_5k_series_returns_one_point_per_computable_activity(self):
        _insert_activity(self.conn, "run-1", "2026-01-01", 1500)
        _insert_activity(self.conn, "run-2", "2026-02-01", 1600)
        _insert_activity(self.conn, "run-3", "2026-03-01", 1400)
        _insert_activity(self.conn, "run-4", "2026-04-01", 1200)
        _insert_activity(self.conn, "ride-1", "2026-05-01", 1100, sport="cycling")
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series(
            "running_5k",
            {"limit": 20},
            conn=self.conn,
        )
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "running_5k")
        self.assertEqual(result["comparison"], "lower_is_better")
        self.assertEqual(result["axis_direction"], "lower")
        self.assertEqual(result["summary"]["point_count"], 4)
        self.assertEqual(len(result["points"]), 4)
        self.assertEqual(result["current_best"]["activity_id"], "run-4")
        self.assertEqual(result["current_best"]["metric"]["value"], 1200)
        self.assertTrue(result["current_best"]["is_current_best"])
        self.assertEqual(
            [item["activity_id"] for item in result["record_progression"]],
            ["run-1", "run-3", "run-4"],
        )
        self.assertEqual(result["summary"]["record_breaking_count"], 3)
        self.assertTrue(all(point["source_mode"] == "best_effort_distance" for point in result["points"]))
        self.assertTrue(all(point["detail_link"]["source"] == "career" for point in result["points"]))
        _assert_no_forbidden_payload(self, result)

    def test_running_5k_viewmodel_filters_year_status_scope_and_limit(self):
        _insert_activity(self.conn, "run-2025", "2025-12-30", 1500)
        _insert_activity(self.conn, "run-2026-a", "2026-01-01", 1400)
        _insert_activity(self.conn, "run-2026-b", "2026-02-01", 1300)

        result = career_backend.get_career_record_metric_series(
            {"record_key": "running_5k", "year": 2026, "limit": 10},
            conn=self.conn,
        )
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["filters"]["year"], 2026)
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual([point["activity_id"] for point in result["points"]], ["run-2026-a", "run-2026-b"])
        self.assertEqual(result["current_best"]["activity_id"], "run-2026-b")

        limited = career_backend.get_career_record_metric_series(
            "running_5k",
            {"limit": 1},
            conn=self.conn,
        )
        _assert_metric_series_contract(self, limited)
        self.assertEqual(limited["metrics"]["scanned"], 1)
        self.assertEqual(limited["summary"]["point_count"], 1)
        self.assertEqual(limited["points"][0]["activity_id"], "run-2026-b")

        status_filtered = career_backend.get_career_record_metric_series(
            "running_5k",
            {"status": "validation_required"},
            conn=self.conn,
        )
        _assert_metric_series_contract(self, status_filtered)
        self.assertEqual(status_filtered["points"], [])
        self.assertEqual(status_filtered["summary"]["point_count"], 0)
        self.assertEqual(status_filtered["filters"]["status"], "validation_required")
        self.assertEqual(status_filtered["status"]["state"], "sample_missing")

        scope_filtered = career_backend.get_career_record_metric_series(
            "running_5k",
            {"scope_hash": "scope:not-current-series"},
            conn=self.conn,
        )
        _assert_metric_series_contract(self, scope_filtered)
        self.assertEqual(scope_filtered["points"], [])
        self.assertEqual(scope_filtered["filters"]["scope_hash"], "scope:not-current-series")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, limited)
        _assert_no_forbidden_payload(self, status_filtered)
        _assert_no_forbidden_payload(self, scope_filtered)

    def test_running_10k_series_uses_complete_activity_points_and_progression(self):
        _insert_activity(self.conn, "run-10k-1", "2026-01-01", 3100, target_distance_m=10000)
        _insert_activity(self.conn, "run-10k-2", "2026-02-01", 3300, target_distance_m=10000)
        _insert_activity(self.conn, "run-10k-3", "2026-03-01", 3000, target_distance_m=10000)
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series(
            "running_10k",
            {"limit": 20},
            conn=self.conn,
        )
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "running_10k")
        self.assertEqual(result["summary"]["point_count"], 3)
        self.assertEqual(result["current_best"]["activity_id"], "run-10k-3")
        self.assertEqual(result["current_best"]["metric"]["value"], 3000)
        self.assertEqual(
            [item["activity_id"] for item in result["record_progression"]],
            ["run-10k-1", "run-10k-3"],
        )
        self.assertTrue(all(point["range"]["distance_m"] == 10000 for point in result["points"]))
        _assert_no_forbidden_payload(self, result)

    def test_half_and_marathon_shorter_activity_return_empty_series(self):
        _insert_activity(self.conn, "run-short", "2026-01-01", 1800, target_distance_m=10000, total_distance_m=12000)

        half = career_backend.get_career_record_metric_series("running_half_marathon", {}, conn=self.conn)
        marathon = career_backend.get_career_record_metric_series("running_marathon", {}, conn=self.conn)

        _assert_metric_series_contract(self, half)
        _assert_metric_series_contract(self, marathon)
        self.assertEqual(half["points"], [])
        self.assertEqual(half["status"]["state"], "sample_missing")
        self.assertEqual(marathon["points"], [])
        self.assertEqual(marathon["status"]["state"], "sample_missing")
        _assert_no_forbidden_payload(self, half)
        _assert_no_forbidden_payload(self, marathon)

    def test_half_marathon_current_best_is_derived_from_all_points(self):
        _insert_activity(self.conn, "run-half-1", "2026-01-01", 7200, target_distance_m=21097.5, total_distance_m=22000)
        _insert_activity(self.conn, "run-half-2", "2026-02-01", 7000, target_distance_m=21097.5, total_distance_m=22000)

        result = career_backend.get_career_record_metric_series("running_half_marathon", {}, conn=self.conn)

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "run-half-2")
        self.assertEqual(result["current_best"]["metric"]["value"], 7000)
        self.assertEqual([item["activity_id"] for item in result["record_progression"]], ["run-half-1", "run-half-2"])
        _assert_no_forbidden_payload(self, result)

    def test_running_5k_series_ignores_non_computable_and_reports_sample_missing(self):
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock)
            VALUES ('short-run', 'running', '2026-01-01T08:00:00Z', 4.0, 1300, ?, 0)
            """,
            (_distance_points([(0, 0), (4000, 1300)]),),
        )

        result = career_backend.get_career_record_metric_series("running_5k", {}, conn=self.conn)

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["points"], [])
        self.assertIsNone(result["current_best"])
        self.assertEqual(result["record_progression"], [])
        self.assertEqual(result["status"]["state"], "sample_missing")
        _assert_no_forbidden_payload(self, result)

    def test_unsupported_record_key_returns_controlled_empty_viewmodel(self):
        result = career_backend.get_career_record_metric_series("cycling_fastest_10k", {}, conn=self.conn)

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "cycling_fastest_10k")
        self.assertEqual(result["points"], [])
        self.assertEqual(result["status"]["state"], "unsupported")
        self.assertEqual(result["metrics"]["scanned"], 0)
        self.assertTrue(result["metrics"]["readonly"])
        _assert_no_forbidden_payload(self, result)

    def test_sport_mismatch_returns_controlled_empty_viewmodel(self):
        _insert_activity(self.conn, "run-1", "2026-01-01", 1500)

        result = career_backend.get_career_record_metric_series(
            "running_5k",
            {"sport": "cycling"},
            conn=self.conn,
        )

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["points"], [])
        self.assertEqual(result["filters"]["sport"], "cycling")
        self.assertEqual(result["status"]["state"], "sample_missing")
        self.assertEqual(result["metrics"]["scanned"], 0)
        _assert_no_forbidden_payload(self, result)

    def test_pywebview_bridge_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="maitu-record-series-") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "records.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                conn.row_factory = sqlite3.Row
                try:
                    _create_schema(conn)
                    _insert_activity(conn, "run-bridge", "2026-06-01", 1234)
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_record_metric_series({"record_key": "running_5k"})
            finally:
                profile_backend.DB_PATH = original_db_path

        self.assertTrue(response["ok"])
        self.assertEqual(response["code"], main.API_CODE_OK)
        _assert_metric_series_contract(self, response["data"])
        self.assertEqual(response["data"]["current_best"]["activity_id"], "run-bridge")
        _assert_no_forbidden_payload(self, response)


if __name__ == "__main__":
    unittest.main()
