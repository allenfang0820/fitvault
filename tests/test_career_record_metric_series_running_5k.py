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


def _elevation_points(items):
    return json.dumps([
        {"distance_m": distance, "t_sec": elapsed, "alt_m": altitude}
        for distance, elapsed, altitude in items
    ])


def _time_only_points(count=4):
    return json.dumps([{"lat": 30.0 + index * 0.001, "lon": 104.0, "time": f"2026-01-01T08:{index:02d}:00Z"} for index in range(count)])


def _power_points(power_w, *, duration_sec=1200, step_sec=5):
    return json.dumps([{"t": t, "power_w": power_w} for t in range(0, duration_sec + step_sec, step_sec)])


def _pool_lengths(seconds, *, stroke="freestyle"):
    return json.dumps([
        {"index": index, "elapsed_sec": elapsed, "stroke": stroke}
        for index, elapsed in enumerate(seconds)
    ])


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
            gain_m REAL,
            ascent_m REAL,
            max_alt_m REAL,
            max_altitude_m REAL,
            points_json TEXT,
            track_json TEXT,
            power_points TEXT,
            laps_json TEXT,
            lengths_json TEXT,
            pool_length_m REAL,
            pool_length REAL,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )
    career_backend.ensure_career_schema(conn)


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


def _insert_total_activity(
    conn,
    activity_id,
    date,
    *,
    sport,
    distance_m=None,
    duration_sec=None,
    ascent_m=None,
    max_altitude_m=None,
    sub_sport_type=None,
    points_json=None,
):
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, sub_sport_type, start_time, dist_km, duration_sec,
            gain_m, ascent_m, max_alt_m, max_altitude_m, points_json, is_mock
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            sport,
            sub_sport_type,
            f"{date}T08:00:00Z",
            None if distance_m is None else distance_m / 1000.0,
            duration_sec,
            ascent_m,
            ascent_m,
            max_altitude_m,
            max_altitude_m,
            points_json,
        ),
    )


def _insert_cycling_power_activity(conn, activity_id, date, power_w, *, duration_sec=1200, distance_m=30000):
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, power_points, is_mock
        )
        VALUES (?, 'cycling', ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            f"{date}T08:00:00Z",
            distance_m / 1000.0,
            duration_sec,
            _power_points(power_w, duration_sec=duration_sec),
        ),
    )


def _insert_cycling_distance_activity(conn, activity_id, date, elapsed_at_target, *, target_distance_m=10000, total_distance_m=None):
    total_distance = total_distance_m or target_distance_m + 5000
    points = [(0, 0), (target_distance_m, elapsed_at_target), (total_distance, elapsed_at_target + 600)]
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock
        )
        VALUES (?, 'cycling', ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            f"{date}T08:00:00Z",
            total_distance / 1000.0,
            elapsed_at_target + 600,
            _distance_points(points),
        ),
    )


def _insert_cycling_long_distance_activity(conn, activity_id, date, *, total_distance_m=181000, duration_sec=10800):
    steps = 24
    points = [
        (round(total_distance_m * index / steps, 3), round(duration_sec * index / steps, 3))
        for index in range(steps + 1)
    ]
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock
        )
        VALUES (?, 'cycling', ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            f"{date}T08:00:00Z",
            total_distance_m / 1000.0,
            duration_sec,
            _distance_points(points),
        ),
    )


def _insert_pool_swim_activity(conn, activity_id, date, lengths_sec, *, pool_length_m=25.0, sub_sport_type="lap_swimming"):
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, sub_sport_type, start_time, dist_km, duration_sec,
            pool_length_m, pool_length, lengths_json, is_mock
        )
        VALUES (?, 'swimming', ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            activity_id,
            sub_sport_type,
            f"{date}T08:00:00Z",
            len(lengths_sec) * pool_length_m / 1000.0,
            sum(lengths_sec),
            pool_length_m,
            pool_length_m,
            _pool_lengths(lengths_sec),
        ),
    )


def _assert_no_forbidden_payload(testcase, payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for token in (
        "points_json",
        "track_json",
        "power_points",
        "laps_json",
        "lengths_json",
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
        career_backend._RECORD_METRIC_SERIES_CACHE.clear()
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

    def test_records_list_running_5k_current_best_is_derived_from_metric_series(self):
        career_backend._RECORD_METRIC_SERIES_CACHE.clear()
        _insert_activity(self.conn, "run-slower-old", "2026-01-01", 1500)
        _insert_activity(self.conn, "run-series-best", "2026-02-01", 1300)
        _insert_activity(self.conn, "run-slower-latest", "2026-03-01", 1600)
        before = _counts(self.conn)

        series = career_backend.get_career_record_metric_series(
            "running_5k",
            {"limit": 20},
            conn=self.conn,
        )
        records = career_backend.get_career_records({"sport": "running"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        self.assertEqual(series["current_best"]["activity_id"], "run-series-best")
        running_5k = next(record for record in records["records"] if record["record_key"] == "running_5k")
        self.assertEqual(running_5k["activity_id"], series["current_best"]["activity_id"])
        self.assertEqual(running_5k["metric"]["value"], series["current_best"]["metric"]["value"])
        self.assertEqual(running_5k["metric"]["display"], series["current_best"]["metric"]["display"])
        self.assertEqual(running_5k["source_mode"], "best_effort_distance")
        self.assertEqual(running_5k["resolver_version"], career_backend.RECORD_METRIC_SERIES_RESOLVER_VERSION)
        self.assertEqual(running_5k["status"], "active")
        self.assertEqual(running_5k["id"], "catalog:running_5k")
        self.assertEqual(records["summary"]["by_record_key"]["running_5k"], 1)
        chart_series = career_backend.get_career_record_metric_series(
            {
                "record_key": running_5k["record_key"],
                "sport": running_5k["sport"],
                "scope_hash": running_5k["scope"]["scope_hash"],
                "status": "available",
                "limit": 1000,
            },
            conn=self.conn,
        )
        self.assertEqual(chart_series["record_key"], running_5k["record_key"])
        self.assertEqual(chart_series["summary"]["current_best_activity_id"], running_5k["activity_id"])
        self.assertEqual(chart_series["current_best"]["activity_id"], running_5k["activity_id"])
        self.assertEqual(chart_series["current_best"]["metric"]["value"], running_5k["metric"]["value"])
        self.assertEqual(chart_series["current_best"]["metric"]["display"], running_5k["metric"]["display"])
        self.assertTrue(chart_series["metrics"]["cache_hit"])
        _assert_no_forbidden_payload(self, records)
        _assert_no_forbidden_payload(self, chart_series)

    def test_running_5k_metric_series_cache_hit_preserves_result_and_remains_readonly(self):
        career_backend._RECORD_METRIC_SERIES_CACHE.clear()
        _insert_activity(self.conn, "run-cache-1", "2026-01-01", 1500)
        _insert_activity(self.conn, "run-cache-best", "2026-02-01", 1300)
        before = _counts(self.conn)

        first = career_backend.get_career_record_metric_series(
            "running_5k",
            {"limit": 20},
            conn=self.conn,
        )
        second = career_backend.get_career_record_metric_series(
            "running_5k",
            {"limit": 20},
            conn=self.conn,
        )
        after = _counts(self.conn)

        self.assertEqual(before, after)
        self.assertFalse(first["metrics"]["cache_hit"])
        self.assertTrue(second["metrics"]["cache_hit"])
        self.assertEqual(second["summary"], first["summary"])
        self.assertEqual(second["current_best"], first["current_best"])
        self.assertEqual(second["points"], first["points"])
        _assert_no_forbidden_payload(self, second)

    def test_records_list_running_5k_series_current_best_overrides_legacy_default_scope_pb(self):
        _insert_activity(self.conn, "legacy-fast-total", "2026-01-01", 1500)
        _insert_activity(self.conn, "series-window-best", "2026-02-01", 1300)
        legacy_scope = {"sport_scope": "default"}
        self.conn.execute(
            """
            INSERT INTO career_pb_records (
                id, activity_id, sport, pb_type, value, value_unit, improvement,
                event_date, confidence, source, status, source_mode, sport_scope,
                resolver_version, record_key, record_family, scope_json, scope_key,
                scope_hash, range_json, quality_json, metric_value_num, metric_name,
                catalog_state, rule_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pb:running_5k:legacy-fast-total",
                "legacy-fast-total",
                "running",
                "running_5k",
                "999",
                "seconds",
                None,
                "2026-01-01",
                1.0,
                "resolver",
                "active",
                "activity_total",
                "default",
                "legacy",
                "running_5k",
                "standard_distance",
                json.dumps(legacy_scope),
                "default",
                career_backend._record_scope_hash(legacy_scope),
                "{}",
                "{}",
                999,
                "elapsed_time_sec",
                "available",
                "legacy",
            ),
        )
        before = _counts(self.conn)

        records = career_backend.get_career_records({"sport": "running"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        running_5k_records = [record for record in records["records"] if record["record_key"] == "running_5k"]
        self.assertEqual(len(running_5k_records), 1)
        running_5k = running_5k_records[0]
        self.assertEqual(running_5k["id"], "catalog:running_5k")
        self.assertEqual(running_5k["activity_id"], "series-window-best")
        self.assertEqual(running_5k["metric"]["value"], 1300)
        self.assertEqual(running_5k["source_mode"], "best_effort_distance")
        self.assertEqual(running_5k["resolver_version"], career_backend.RECORD_METRIC_SERIES_RESOLVER_VERSION)
        _assert_no_forbidden_payload(self, records)

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

    def test_half_marathon_uses_activity_total_when_stream_has_no_distance_samples(self):
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock)
            VALUES ('half-total-1', 'running', '2026-01-01T08:00:00Z', 21.43, 7768, ?, 0)
            """,
            (_time_only_points(8),),
        )
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock)
            VALUES ('half-total-best', 'running', '2026-02-01T08:00:00Z', 21.45, 7642, ?, 0)
            """,
            (_time_only_points(8),),
        )
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series("running_half_marathon", {}, conn=self.conn)
        records = career_backend.get_career_records({"sport": "running"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "half-total-best")
        self.assertEqual(result["current_best"]["metric"]["display"], "2:07:22")
        self.assertTrue(all(point["source_mode"] == "activity_total" for point in result["points"]))
        self.assertTrue(all("activity_total_standard_distance_fallback" in point["quality"]["reason_codes"] for point in result["points"]))
        half_record = next(record for record in records["records"] if record["record_key"] == "running_half_marathon")
        self.assertEqual(half_record["activity_id"], "half-total-best")
        self.assertEqual(half_record["metric"]["display"], "2:07:22")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, records)

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

    def test_multisport_activity_total_metric_series_derives_current_best_and_progression(self):
        scenarios = [
            ("cycling_longest_distance", "cycling", "distance_m", 60000, 72000, "ride-best"),
            ("cycling_longest_elapsed_time", "cycling", "elapsed_time_sec", 3600, 4500, "ride-best"),
            ("cycling_max_ascent", "cycling", "ascent_m", 800, 1200, "ride-best"),
            ("hiking_longest_distance", "hiking", "distance_m", 12000, 18000, "hike-best"),
            ("hiking_longest_elapsed_time", "hiking", "elapsed_time_sec", 4000, 7200, "hike-best"),
            ("hiking_max_ascent", "hiking", "ascent_m", 500, 900, "hike-best"),
            ("hiking_max_altitude", "hiking", "max_altitude_m", 1800, 2300, "hike-best"),
            ("open_water_longest_distance", "swimming", "distance_m", 1500, 2200, "open-water-best"),
            ("open_water_longest_elapsed_time", "swimming", "elapsed_time_sec", 1800, 2400, "open-water-best"),
            ("trail_longest_distance", "trail_running", "distance_m", 15000, 26000, "trail-best"),
            ("trail_longest_elapsed_time", "trail_running", "elapsed_time_sec", 5000, 8600, "trail-best"),
            ("trail_max_ascent", "trail_running", "ascent_m", 900, 1600, "trail-best"),
            ("trail_max_altitude", "trail_running", "max_altitude_m", 2100, 2600, "trail-best"),
        ]
        for record_key, sport_type, metric_name, first_value, best_value, best_prefix in scenarios:
            definition = career_backend.get_record_definition(record_key)
            self.assertIsNotNone(definition)
            sub_sport = "open_water" if definition.sport == "open_water_swimming" else None
            kwargs1 = {
                "sport": sport_type,
                "distance_m": 10000,
                "duration_sec": 1000,
                "ascent_m": 100,
                "max_altitude_m": 1000,
                "sub_sport_type": sub_sport,
            }
            kwargs2 = dict(kwargs1)
            if metric_name == "distance_m":
                kwargs1["distance_m"] = first_value
                kwargs2["distance_m"] = best_value
            elif metric_name == "elapsed_time_sec":
                kwargs1["duration_sec"] = first_value
                kwargs2["duration_sec"] = best_value
            elif metric_name == "ascent_m":
                kwargs1["ascent_m"] = first_value
                kwargs2["ascent_m"] = best_value
            elif metric_name == "max_altitude_m":
                kwargs1["max_altitude_m"] = first_value
                kwargs2["max_altitude_m"] = best_value
            _insert_total_activity(self.conn, f"{record_key}-first", "2026-01-01", **kwargs1)
            _insert_total_activity(self.conn, f"{best_prefix}-{record_key}", "2026-02-01", **kwargs2)

            before = _counts(self.conn)
            result = career_backend.get_career_record_metric_series(record_key, {"sport": definition.sport}, conn=self.conn)
            records = career_backend.get_career_records({"sport": definition.sport, "record_key": record_key}, conn=self.conn)
            after = _counts(self.conn)

            self.assertEqual(before, after)
            _assert_metric_series_contract(self, result)
            self.assertEqual(result["record_key"], record_key)
            self.assertEqual(result["sport"], definition.sport)
            self.assertEqual(result["comparison"], "higher_is_better")
            self.assertEqual(result["axis_direction"], "higher")
            self.assertGreaterEqual(result["summary"]["point_count"], 2)
            self.assertEqual(result["current_best"]["activity_id"], f"{best_prefix}-{record_key}")
            self.assertEqual(result["current_best"]["metric"]["value"], best_value)
            self.assertEqual(result["current_best"]["source_mode"], "activity_total")
            self.assertEqual(
                [item["activity_id"] for item in result["record_progression"][-2:]],
                [f"{record_key}-first", f"{best_prefix}-{record_key}"],
            )
            self.assertTrue(records["records"])
            self.assertEqual(records["records"][0]["activity_id"], result["current_best"]["activity_id"])
            _assert_no_forbidden_payload(self, result)
            _assert_no_forbidden_payload(self, records)

    def test_trail_single_climb_metric_series_uses_elevation_range_not_total_ascent(self):
        self.assertIn("trail_max_single_climb", career_backend.RECORD_METRIC_SERIES_SUPPORTED_KEYS)
        _insert_total_activity(
            self.conn,
            "trail-climb-first",
            "2026-03-01",
            sport="trail_running",
            distance_m=16000,
            duration_sec=7200,
            ascent_m=2000,
            max_altitude_m=1500,
            points_json=_elevation_points([
                (0, 0, 100),
                (1000, 600, 160),
                (2000, 1200, 260),
                (3500, 2100, 250),
            ]),
        )
        _insert_total_activity(
            self.conn,
            "trail-climb-best",
            "2026-04-01",
            sport="trail_running",
            distance_m=18000,
            duration_sec=7600,
            ascent_m=1200,
            max_altitude_m=1800,
            points_json=_elevation_points([
                (0, 0, 300),
                (800, 500, 380),
                (1800, 1200, 540),
                (2600, 1800, 720),
                (3600, 2500, 690),
            ]),
        )

        result = career_backend.get_career_record_metric_series(
            "trail_max_single_climb",
            {"sport": "trail_running"},
            conn=self.conn,
        )
        records = career_backend.get_career_records(
            {"sport": "trail_running", "record_key": "trail_max_single_climb"},
            conn=self.conn,
        )

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["status"]["state"], "ready")
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "trail-climb-best")
        self.assertEqual(result["current_best"]["metric"]["value"], 420)
        self.assertEqual(result["current_best"]["source_mode"], "elevation_track")
        self.assertEqual(result["current_best"]["scope"]["dimensions"]["sport_scope"], "trail_running")
        self.assertEqual(result["current_best"]["range"]["start_sec"], 0)
        self.assertEqual(result["current_best"]["range"]["end_sec"], 1800)
        self.assertEqual(result["current_best"]["range"]["start_distance_m"], 0)
        self.assertEqual(result["current_best"]["range"]["end_distance_m"], 2600)
        self.assertEqual(result["record_progression"][-1]["activity_id"], "trail-climb-best")
        self.assertEqual(records["records"][0]["activity_id"], "trail-climb-best")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, records)

    def test_trail_single_climb_missing_track_is_sample_missing_with_reason_code(self):
        _insert_total_activity(
            self.conn,
            "trail-no-track",
            "2026-05-01",
            sport="trail_running",
            distance_m=18000,
            duration_sec=7600,
            ascent_m=1400,
            max_altitude_m=1800,
        )

        series = career_backend.get_career_record_metric_series(
            "trail_max_single_climb",
            {"sport": "trail_running"},
            conn=self.conn,
        )
        plan = career_backend.compute_record_metric_results_for_activity(
            {
                "id": "trail-no-track",
                "sport_type": "trail_running",
                "start_time": "2026-05-01T08:00:00Z",
                "dist_km": 18.0,
                "duration_sec": 7600,
                "gain_m": 1400,
                "max_alt_m": 1800,
            },
            record_keys=["trail_max_single_climb"],
            conn=self.conn,
        )

        _assert_metric_series_contract(self, series)
        self.assertEqual(series["points"], [])
        self.assertIsNone(series["current_best"])
        self.assertEqual(series["status"]["state"], "sample_missing")
        self.assertIn("trail_max_single_climb", plan["summary"]["would_skip"])
        self.assertIn("single_climb_range_missing", plan["summary"]["skip_reasons"]["trail_max_single_climb"])
        self.assertIn("single_climb_range_missing", plan["status"]["reason_codes"])
        _assert_no_forbidden_payload(self, series)
        _assert_no_forbidden_payload(self, plan)

    def test_activity_total_metric_series_respects_year_status_scope_and_sport_filters(self):
        _insert_total_activity(self.conn, "ride-2025", "2025-12-01", sport="cycling", distance_m=50000, duration_sec=4000, ascent_m=500)
        _insert_total_activity(self.conn, "ride-2026", "2026-01-01", sport="cycling", distance_m=70000, duration_sec=5000, ascent_m=700)

        result = career_backend.get_career_record_metric_series(
            "cycling_longest_distance",
            {"sport": "cycling", "year": 2026, "limit": 10},
            conn=self.conn,
        )
        self.assertEqual(result["summary"]["point_count"], 1)
        self.assertEqual(result["current_best"]["activity_id"], "ride-2026")
        self.assertEqual(result["filters"]["year"], 2026)

        limited = career_backend.get_career_record_metric_series(
            "cycling_longest_distance",
            {"sport": "cycling", "limit": 1},
            conn=self.conn,
        )
        self.assertEqual(limited["metrics"]["scanned"], 1)
        self.assertEqual(limited["summary"]["point_count"], 1)

        status_filtered = career_backend.get_career_record_metric_series(
            "cycling_longest_distance",
            {"sport": "cycling", "status": "validation_required"},
            conn=self.conn,
        )
        self.assertEqual(status_filtered["points"], [])
        self.assertEqual(status_filtered["status"]["state"], "sample_missing")

        mismatch = career_backend.get_career_record_metric_series(
            "cycling_longest_distance",
            {"sport": "running"},
            conn=self.conn,
        )
        self.assertEqual(mismatch["points"], [])
        self.assertEqual(mismatch["metrics"]["scanned"], 0)

        scope_hash = result["current_best"]["scope"]["scope_hash"]
        scoped = career_backend.get_career_record_metric_series(
            "cycling_longest_distance",
            {"sport": "cycling", "scope_hash": scope_hash},
            conn=self.conn,
        )
        self.assertGreaterEqual(scoped["summary"]["point_count"], 1)
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, limited)
        _assert_no_forbidden_payload(self, status_filtered)
        _assert_no_forbidden_payload(self, mismatch)
        _assert_no_forbidden_payload(self, scoped)

    def test_cycling_power_metric_series_uses_power_duration_curve_without_writing_state(self):
        _insert_cycling_power_activity(self.conn, "power-old", "2026-01-01", 240, duration_sec=1300)
        _insert_cycling_power_activity(self.conn, "power-best", "2026-02-01", 280, duration_sec=1300)
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec, is_mock)
            VALUES ('power-missing', 'cycling', '2026-03-01T08:00:00Z', 30, 1300, 0)
            """
        )
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series("cycling_power_20m", {"sport": "cycling"}, conn=self.conn)
        records = career_backend.get_career_records({"sport": "cycling", "record_key": "cycling_power_20m"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "cycling_power_20m")
        self.assertEqual(result["comparison"], "higher_is_better")
        self.assertEqual(result["axis_direction"], "higher")
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "power-best")
        self.assertEqual(result["current_best"]["metric"]["value"], 280)
        self.assertTrue(all(point["source_mode"] == "best_effort_duration" for point in result["points"]))
        self.assertEqual([item["activity_id"] for item in result["record_progression"]], ["power-old", "power-best"])
        self.assertEqual(records["records"][0]["activity_id"], "power-best")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, records)

    def test_cycling_standard_distance_metric_series_uses_distance_time_window_and_preserves_catalog_state(self):
        _insert_cycling_distance_activity(self.conn, "ride-window-old", "2026-01-01", 1600, target_distance_m=10000, total_distance_m=10000)
        _insert_cycling_distance_activity(self.conn, "ride-window-best", "2026-02-01", 1400, target_distance_m=10000, total_distance_m=10000)
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, start_time, dist_km, duration_sec, points_json, is_mock)
            VALUES ('ride-no-distance-samples', 'cycling', '2026-03-01T08:00:00Z', 40, 3000, ?, 0)
            """,
            (_time_only_points(8),),
        )
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series("cycling_fastest_10k", {"sport": "cycling"}, conn=self.conn)
        records = career_backend.get_career_records({"sport": "cycling", "record_key": "cycling_fastest_10k"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "cycling_fastest_10k")
        self.assertEqual(result["comparison"], "lower_is_better")
        self.assertEqual(result["axis_direction"], "lower")
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "ride-window-best")
        self.assertEqual(result["current_best"]["metric"]["value"], 1400)
        self.assertTrue(all(point["source_mode"] == "best_effort_distance" for point in result["points"]))
        self.assertEqual([item["activity_id"] for item in result["record_progression"]], ["ride-window-old", "ride-window-best"])
        self.assertEqual(records["records"][0]["catalog_state"], "validation_required")
        self.assertEqual(records["records"][0]["activity_id"], "ride-window-best")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, records)

    def test_all_cycling_power_and_standard_distance_keys_return_series_viewmodels(self):
        _insert_cycling_power_activity(self.conn, "power-long", "2026-01-01", 220, duration_sec=7300)
        _insert_cycling_long_distance_activity(self.conn, "ride-long", "2026-01-02")
        keys = [
            "cycling_power_5s",
            "cycling_power_30s",
            "cycling_power_1m",
            "cycling_power_5m",
            "cycling_power_10m",
            "cycling_power_20m",
            "cycling_power_30m",
            "cycling_power_60m",
            "cycling_power_2h",
            "cycling_fastest_10k",
            "cycling_fastest_20k",
            "cycling_fastest_40k",
            "cycling_fastest_50k",
            "cycling_fastest_100k",
            "cycling_fastest_180k",
        ]

        for key in keys:
            result = career_backend.get_career_record_metric_series(key, {"sport": "cycling"}, conn=self.conn)
            _assert_metric_series_contract(self, result)
            self.assertNotEqual(result["status"]["state"], "unsupported", key)
            self.assertGreaterEqual(result["summary"]["point_count"], 1, key)
            _assert_no_forbidden_payload(self, result)

    def test_pool_swim_metric_series_uses_lengths_without_writing_state(self):
        _insert_pool_swim_activity(self.conn, "pool-old", "2026-01-01", [30, 31, 32, 33])
        _insert_pool_swim_activity(self.conn, "pool-best", "2026-02-01", [25, 26, 27, 28])
        self.conn.execute(
            """
            INSERT INTO activities (id, sport_type, sub_sport_type, start_time, dist_km, duration_sec, pool_length_m, is_mock)
            VALUES ('pool-missing-lengths', 'swimming', 'lap_swimming', '2026-03-01T08:00:00Z', 0.1, 120, 25, 0)
            """
        )
        before = _counts(self.conn)

        result = career_backend.get_career_record_metric_series("pool_swim_100m", {"sport": "pool_swimming"}, conn=self.conn)
        records = career_backend.get_career_records({"sport": "pool_swimming", "record_key": "pool_swim_100m"}, conn=self.conn)
        after = _counts(self.conn)

        self.assertEqual(before, after)
        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "pool_swim_100m")
        self.assertEqual(result["comparison"], "lower_is_better")
        self.assertEqual(result["axis_direction"], "lower")
        self.assertEqual(result["summary"]["point_count"], 2)
        self.assertEqual(result["current_best"]["activity_id"], "pool-best")
        self.assertEqual(result["current_best"]["metric"]["value"], 106)
        self.assertTrue(all(point["source_mode"] == "best_effort_distance" for point in result["points"]))
        self.assertEqual([item["activity_id"] for item in result["record_progression"]], ["pool-old", "pool-best"])
        self.assertTrue(records["records"])
        self.assertEqual(records["records"][0]["activity_id"], "pool-best")
        self.assertEqual(records["records"][0]["catalog_state"], "validation_required")
        _assert_no_forbidden_payload(self, result)
        _assert_no_forbidden_payload(self, records)

    def test_pool_swim_missing_pool_length_returns_empty_viewmodel(self):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, dist_km, duration_sec, lengths_json, is_mock
            )
            VALUES ('pool-no-length', 'swimming', 'lap_swimming', '2026-01-01T08:00:00Z', 0.1, 120, ?, 0)
            """,
            (_pool_lengths([30, 31, 32, 33]),),
        )

        result = career_backend.get_career_record_metric_series("pool_swim_100m", {"sport": "pool_swimming"}, conn=self.conn)

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["points"], [])
        self.assertEqual(result["status"]["state"], "sample_missing")
        _assert_no_forbidden_payload(self, result)

    def test_all_pool_swim_keys_return_series_viewmodels(self):
        _insert_pool_swim_activity(self.conn, "pool-long", "2026-01-01", [25] * 60)
        for key in [
            "pool_swim_50m",
            "pool_swim_100m",
            "pool_swim_200m",
            "pool_swim_400m",
            "pool_swim_800m",
            "pool_swim_1500m",
        ]:
            result = career_backend.get_career_record_metric_series(key, {"sport": "pool_swimming"}, conn=self.conn)
            _assert_metric_series_contract(self, result)
            self.assertNotEqual(result["status"]["state"], "unsupported", key)
            self.assertEqual(result["summary"]["point_count"], 1, key)
            _assert_no_forbidden_payload(self, result)

    def test_unsupported_record_key_returns_controlled_empty_viewmodel(self):
        result = career_backend.get_career_record_metric_series("unknown_record_key", {}, conn=self.conn)

        _assert_metric_series_contract(self, result)
        self.assertEqual(result["record_key"], "unknown_record_key")
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
