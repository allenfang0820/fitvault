import json
import sqlite3
import unittest

import career_backend


FORBIDDEN = (
    "track_points",
    "points_xy",
    "raw_points",
    "gps_points",
    "track_json",
    "polyline",
    "file_path",
    "storage_ref",
    "device_serial",
    "serial_number",
    "weight_history",
    "route_signature",
    "/Users/",
    "file://",
)


def assert_safe(testcase: unittest.TestCase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN:
        testcase.assertNotIn(forbidden, text)


def _activity(activity_id: str, elapsed=5400):
    return {
        "activity_id": activity_id,
        "sport_type": "trail_running",
        "distance_m": 10_000,
        "ascent_m": 720,
        "duration_sec": elapsed,
        "max_altitude_m": 1800,
        "event_date": "2026-07-14",
    }


def _elevation_points(items):
    return json.dumps([
        {"distance_m": distance, "t_sec": elapsed, "alt_m": altitude}
        for distance, elapsed, altitude in items
    ])


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            gain_m REAL,
            ascent_m REAL,
            max_alt_m REAL,
            max_altitude_m REAL,
            points_json TEXT,
            track_json TEXT,
            deleted_at TEXT,
            is_mock INTEGER,
            file_path TEXT
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _insert_trail_activity(
    conn: sqlite3.Connection,
    *,
    activity_id: str,
    start_time: str,
    distance_km: float,
    duration_sec: int,
    ascent_m: int,
    max_altitude_m: int,
    climb_points: list[tuple[int, int, int]],
) -> None:
    _create_activity_table(conn)
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, sub_sport_type, start_time, dist_km, distance,
            duration_sec, gain_m, ascent_m, max_alt_m, max_altitude_m,
            points_json, track_json, deleted_at, is_mock, file_path
        )
        VALUES (?, 'trail_running', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?)
        """,
        (
            activity_id,
            start_time,
            distance_km,
            distance_km * 1000,
            duration_sec,
            ascent_m,
            ascent_m,
            max_altitude_m,
            max_altitude_m,
            _elevation_points(climb_points),
            f"/tmp/{activity_id}.fit",
        ),
    )


class CareerRecordsTrailApiSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.activity = _activity("trail-api-target")
        career_backend.apply_trail_activity_total_records(
            self.conn,
            activity=self.activity,
            track_points=[
                {"distance_m": 0, "altitude_m": 1000, "t_sec": 0},
                {"distance_m": 5000, "altitude_m": 1300, "t_sec": 2500},
                {"distance_m": 10000, "altitude_m": 1200, "t_sec": 5400},
            ],
            dry_run=False,
            run_id="trail:activity",
        )

    def tearDown(self):
        self.conn.close()

    def test_trail_catalog_only_exposes_non_route_records(self):
        catalog = career_backend.get_career_record_catalog({"sport": "trail_running", "include_unavailable": True})
        sport = catalog["sports"][0]
        groups = {group["group_key"]: group for group in sport["groups"]}

        self.assertIn("trail_activity_total", groups)
        self.assertNotIn("trail_route_segment", groups)
        self.assertEqual(sport["capabilities"]["activity_total_records"]["state"], "available")
        self.assertNotIn("route_segment_pr", sport["capabilities"])
        self.assertNotIn("pace_gap_curve", sport["capabilities"])
        record_keys = {
            record["record_key"]
            for group in sport["groups"]
            for record in group["records"]
        }
        self.assertEqual(
            record_keys,
            {
                "trail_longest_distance",
                "trail_max_ascent",
                "trail_longest_elapsed_time",
                "trail_max_altitude",
                "trail_max_single_climb",
            },
        )
        assert_safe(self, catalog)

    def test_trail_candidate_compat_path_only_includes_activity_total_records(self):
        records = career_backend.get_career_records({"sport": "trail_running"}, conn=self.conn)
        candidates = career_backend.get_career_record_candidates({"sport": "trail_running"}, conn=self.conn)

        self.assertEqual(records["records"], [])
        self.assertGreaterEqual(len(candidates["candidates"]), 5)
        candidate_keys = {candidate["record_key"] for candidate in candidates["candidates"]}
        self.assertIn("trail_longest_distance", candidate_keys)
        self.assertNotIn("trail_route_best_time", candidate_keys)
        self.assertNotIn("trail_segment_best_time", candidate_keys)
        self.assertNotIn("trail_climb_segment_best_time", candidate_keys)
        assert_safe(self, records)
        assert_safe(self, candidates)

    def test_trail_records_list_reads_five_materialized_current_best_records(self):
        _insert_trail_activity(
            self.conn,
            activity_id="trail-api-first",
            start_time="2026-06-01T08:00:00Z",
            distance_km=18.0,
            duration_sec=7200,
            ascent_m=900,
            max_altitude_m=1500,
            climb_points=[(0, 0, 100), (1000, 600, 180), (2500, 1500, 310), (4000, 2300, 300)],
        )
        _insert_trail_activity(
            self.conn,
            activity_id="trail-api-best",
            start_time="2026-07-01T08:00:00Z",
            distance_km=26.0,
            duration_sec=9200,
            ascent_m=1600,
            max_altitude_m=2300,
            climb_points=[(0, 0, 500), (1200, 700, 650), (2600, 1500, 850), (4200, 2400, 980)],
        )
        before = career_backend.get_career_records({"sport": "trail_running"}, conn=self.conn)
        before_version = before["source_version"]

        career_backend.rebuild_career_record_metric_results(
            self.conn,
            sport="trail_running",
            dry_run=False,
        )
        after = career_backend.get_career_records({"sport": "trail_running"}, conn=self.conn)

        expected_keys = {
            "trail_longest_distance",
            "trail_max_ascent",
            "trail_longest_elapsed_time",
            "trail_max_altitude",
            "trail_max_single_climb",
        }
        by_key = {record["record_key"]: record for record in after["records"]}
        self.assertEqual(set(by_key), expected_keys)
        self.assertEqual({record["activity_id"] for record in after["records"]}, {"trail-api-best"})
        self.assertEqual(
            {record["scope"]["dimensions"]["sport_scope"] for record in after["records"]},
            {"trail_running"},
        )
        self.assertEqual(by_key["trail_max_single_climb"]["source_mode"], "elevation_track")
        self.assertNotEqual(before_version, after["source_version"])
        self.assertFalse(after["metrics"]["derived_provider_cache_hit"])
        assert_safe(self, after)

    def test_trail_records_empty_activity_table_does_not_fabricate_current_best(self):
        _create_activity_table(self.conn)

        records = career_backend.get_career_records({"sport": "trail_running"}, conn=self.conn)
        series = career_backend.get_career_record_metric_series(
            "trail_max_single_climb",
            {"sport": "trail_running"},
            conn=self.conn,
        )

        self.assertEqual(records["records"], [])
        self.assertEqual(records["status"]["data_ready"], False)
        self.assertEqual(series["points"], [])
        self.assertIsNone(series["current_best"])
        self.assertEqual(series["status"]["state"], "sample_missing")
        self.assertNotEqual(series["status"]["state"], "unsupported")
        assert_safe(self, records)
        assert_safe(self, series)

    def test_contract_excludes_trail_route_comparison_api(self):
        contract = json.loads(open("docs/js_api_contract.json", encoding="utf-8").read())
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertNotIn("get_trail_route_comparison", methods)
        self.assertIn("不属于当前记录中心", methods["get_career_record_catalog"]["description"])
        self.assertNotIn("Pace/GAP analysis-only", methods["get_career_record_catalog"]["description"])


if __name__ == "__main__":
    unittest.main()
