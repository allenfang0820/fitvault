import json
import sqlite3
import unittest

import career_backend


FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "evidence_json",
    "payload_json",
    "sqlite_schema",
    "schema",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


def _insert_record(conn: sqlite3.Connection, **overrides) -> None:
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "record:running_5k:1",
        "activity_id": "activity-1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-20",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
        "record_key": "running_5k",
        "record_family": "distance_time_pb",
        "source_mode": "activity_total",
        "scope_hash": "scope:v2:running",
        "scope_key": "default",
        "scope_json": json.dumps({"sport_scope": "default"}, ensure_ascii=False),
        "catalog_state": "available",
        "metric_value_num": 1500,
        "metric_name": "elapsed_time_sec",
        "rule_version": "records-v2-test",
    }
    data.update(overrides)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_pb_records)").fetchall()}
    payload = {key: value for key, value in data.items() if key in columns}
    placeholders = ", ".join("?" for _ in payload)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(payload)}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def _insert_record_event(conn: sqlite3.Connection, **overrides) -> None:
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "record_event:activated:1",
        "record_id": "record:running_5k:1",
        "activity_id": "activity-1",
        "pb_type": "running_5k",
        "event_type": "activated",
        "event_at": "2026-05-21 08:30:00",
        "evidence_key": "evidence:1",
        "resolver_version": "records-v2-test",
        "source": "resolver",
        "record_key": "running_5k",
        "scope_hash": "scope:v2:running",
        "scope_key": "default",
        "run_id": "run:1",
        "decision": "activate",
        "reason_codes_json": "[]",
        "payload_json": json.dumps(
            {
                "evidence_json": {"file_path": "/tmp/hidden.fit"},
                "points_json": "[forbidden]",
            },
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_record_events)").fetchall()}
    payload = {key: value for key, value in data.items() if key in columns}
    placeholders = ", ".join("?" for _ in payload)
    conn.execute(
        f"INSERT INTO career_record_events ({', '.join(payload)}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def _insert_candidate(conn: sqlite3.Connection, **overrides) -> None:
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "race_candidate:1",
        "activity_id": "activity-candidate",
        "candidate_type": "race",
        "title": "疑似赛事",
        "evidence_json": json.dumps({"reason": "title"}, ensure_ascii=False),
        "confidence": 0.5,
        "status": "candidate",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_event_candidates ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _distance_points(items):
    return json.dumps([{"distance_m": distance, "t_sec": elapsed} for distance, elapsed in items])


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


def _insert_running_activity_row(conn: sqlite3.Connection, *, activity_id: str, start_time: str, elapsed_5k: int, distance_km: float = 5.0) -> None:
    _create_activity_table(conn)
    conn.execute(
        """
        INSERT INTO activities (
            id, sport_type, start_time, dist_km, duration_sec, points_json, deleted_at, is_mock, file_path
        )
        VALUES (?, 'running', ?, ?, ?, ?, NULL, 0, ?)
        """,
        (
            activity_id,
            start_time,
            distance_km,
            elapsed_5k,
            _distance_points([(0, 0), (distance_km * 1000, elapsed_5k)]),
            f"/tmp/{activity_id}.fit",
        ),
    )


def _insert_trail_activity_row(
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


def _insert_metric_series_rows(conn: sqlite3.Connection) -> None:
    _insert_running_activity_row(conn, activity_id="run-1", start_time="2026-07-18T08:00:00Z", elapsed_5k=1800)
    _insert_running_activity_row(conn, activity_id="run-2", start_time="2026-07-19T08:00:00Z", elapsed_5k=1700)
    _insert_running_activity_row(conn, activity_id="run-3", start_time="2026-07-20T08:00:00Z", elapsed_5k=1900)
    career_backend.rebuild_career_record_metric_results(
        conn,
        sport="running",
        record_keys=["running_5k"],
        dry_run=False,
    )


class TestCareerTimelineRecordEventNodes(unittest.TestCase):
    def test_type_record_returns_only_record_breaking_and_current_best_nodes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_record(conn)
            _insert_record_event(conn)
            _insert_record_event(
                conn,
                id="record_event:user_confirmed:1",
                event_type="user_confirmed",
                decision="confirm",
                event_at="2026-05-21 08:31:00",
            )
            _insert_record_event(
                conn,
                id="record_event:detected:1",
                event_type="detected",
                event_at="2026-05-21 08:32:00",
            )
            _insert_record_event(
                conn,
                id="record_event:record_breaking:1",
                record_id=None,
                activity_id="run-2",
                pb_type="running_5k",
                event_type="record_breaking",
                event_at="2026-07-19",
                source="metric_series",
                record_key="running_5k",
                scope_hash="scope:default",
                scope_key="default",
                decision="record_breaking",
                payload_json=json.dumps(
                    {
                        "metric": {"value": 1700.0, "unit": "seconds", "display": "28:20"},
                        "previous_best_metric": {"value": 1800.0, "unit": "seconds", "display": "30:00"},
                        "detail_link": {"activity_id": "run-2", "source": "career"},
                    },
                    ensure_ascii=False,
                ),
            )
            _insert_metric_series_rows(conn)
            conn.execute("DELETE FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,))

            result = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(result["filters"], {"year": None, "type": "record"})
            self.assertEqual(result["available_years"], [2026])
            self.assertEqual(len(nodes), 1)
            self.assertEqual({node["type"] for node in nodes}, {"record"})
            self.assertEqual({node["event_type"] for node in nodes}, {"current_best"})
            for node in nodes:
                self.assertEqual(node["track"], "milestone")
                self.assertEqual(node["record_key"], "running_5k")
                self.assertEqual(node["sport"], "running")
                self.assertEqual(node["family"], "distance_time_pb")
                self.assertEqual(node["detail_link"], {
                    "activity_id": "run-2",
                    "source": "career",
                    "record_id": "",
                })
                self.assertEqual(node["value"], "28:20")
            self.assertNotIn("activated", {node["event_type"] for node in nodes})
            self.assertNotIn("user_confirmed", {node["event_type"] for node in nodes})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_all_includes_record_milestone_nodes_without_reintroducing_pb_nodes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_metric_series_rows(conn)
            conn.execute("DELETE FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,))

            result = career_backend.get_career_timeline({"type": "all"}, conn)
            nodes = _flatten_nodes(result)
            record_nodes = [node for node in nodes if node["type"] == "record"]

            self.assertIn("record", {node["type"] for node in nodes})
            self.assertNotIn("pb", {node["type"] for node in nodes})
            self.assertEqual({node["event_type"] for node in record_nodes}, {"current_best"})
            self.assertEqual({node["track"] for node in record_nodes}, {"milestone"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_current_best_record_node_replaces_same_activity_record_breaking_node(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_running_activity_row(conn, activity_id="run-1", start_time="2026-07-18T08:00:00Z", elapsed_5k=1800)
            _insert_running_activity_row(conn, activity_id="run-2", start_time="2026-07-19T08:00:00Z", elapsed_5k=1700)
            _insert_running_activity_row(conn, activity_id="run-3", start_time="2026-07-20T08:00:00Z", elapsed_5k=1600)
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )

            result = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(result)
            by_activity = {node["activity_id"]: node["event_type"] for node in nodes}

            self.assertEqual(by_activity["run-2"], "record_breaking")
            self.assertEqual(by_activity["run-3"], "current_best")
            self.assertNotIn(
                ("run-3", "record_breaking"),
                {(node["activity_id"], node["event_type"]) for node in nodes},
            )
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_running_10k_current_best_is_materialized_into_record_timeline(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_running_activity_row(
                conn,
                activity_id="run-10k-best",
                start_time="2026-05-31T08:00:00Z",
                elapsed_5k=3200,
                distance_km=10.0,
            )
            records = career_backend.get_career_records(
                {"sport": "running", "record_key": "running_10k"},
                conn=conn,
            )
            before_timeline = career_backend.get_career_timeline({"type": "record"}, conn)
            before_nodes = _flatten_nodes(before_timeline)

            self.assertIn(
                ("running_10k", "run-10k-best"),
                {(record["record_key"], record["activity_id"]) for record in records["records"]},
            )
            self.assertEqual(before_nodes, [])

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_10k"],
                dry_run=False,
            )

            event_rows = conn.execute(
                """
                SELECT activity_id, record_key, event_type
                FROM career_record_events
                WHERE event_type = ?
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchall()
            result = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(
                [(row["activity_id"], row["record_key"], row["event_type"]) for row in event_rows],
                [("run-10k-best", "running_10k", "current_best")],
            )
            self.assertIn(
                ("current_best", "running_10k", "run-10k-best"),
                {(node["event_type"], node["record_key"], node["activity_id"]) for node in nodes},
            )
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_trail_activity_total_records_materialize_current_best_into_record_timeline(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_trail_activity_row(
                conn,
                activity_id="trail-first",
                start_time="2026-06-01T08:00:00Z",
                distance_km=18.0,
                duration_sec=7200,
                ascent_m=900,
                max_altitude_m=1500,
                climb_points=[(0, 0, 100), (1000, 600, 180), (2500, 1500, 310), (4000, 2300, 300)],
            )
            _insert_trail_activity_row(
                conn,
                activity_id="trail-best",
                start_time="2026-07-01T08:00:00Z",
                distance_km=26.0,
                duration_sec=9200,
                ascent_m=1600,
                max_altitude_m=2300,
                climb_points=[(0, 0, 500), (1200, 700, 650), (2600, 1500, 850), (4200, 2400, 980)],
            )

            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="trail_running",
                dry_run=False,
            )

            expected_keys = {
                "trail_longest_distance",
                "trail_max_ascent",
                "trail_longest_elapsed_time",
                "trail_max_altitude",
                "trail_max_single_climb",
            }
            metric_rows = conn.execute(
                """
                SELECT DISTINCT record_key
                FROM career_record_metric_results
                WHERE sport = 'trail_running' AND status = 'available'
                """
            ).fetchall()
            current_best_rows = conn.execute(
                """
                SELECT activity_id, record_key, event_type
                FROM career_record_events
                WHERE source = 'metric_series'
                  AND event_type = ?
                  AND record_key LIKE 'trail_%'
                ORDER BY record_key
                """,
                (career_backend.RECORD_CURRENT_BEST_EVENT_TYPE,),
            ).fetchall()
            timeline = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(timeline)
            current_best_nodes = [
                node for node in nodes
                if node["event_type"] == "current_best" and str(node.get("record_key") or "").startswith("trail_")
            ]

            self.assertEqual({row["record_key"] for row in metric_rows}, expected_keys)
            self.assertEqual({row["record_key"] for row in current_best_rows}, expected_keys)
            self.assertEqual({row["activity_id"] for row in current_best_rows}, {"trail-best"})
            self.assertEqual({node["record_key"] for node in current_best_nodes}, expected_keys)
            self.assertEqual({node["activity_id"] for node in current_best_nodes}, {"trail-best"})
            self.assertFalse(any(
                node["event_type"] == "record_breaking"
                and node["activity_id"] == "trail-best"
                and node["record_key"] in expected_keys
                for node in nodes
            ))
            _assert_forbidden_keys_absent(self, timeline)
        finally:
            conn.close()

    def test_trail_deleted_current_best_promotes_next_best_in_records_and_timeline(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_trail_activity_row(
                conn,
                activity_id="trail-first",
                start_time="2026-06-01T08:00:00Z",
                distance_km=18.0,
                duration_sec=7200,
                ascent_m=900,
                max_altitude_m=1500,
                climb_points=[(0, 0, 100), (1000, 600, 180), (2500, 1500, 310), (4000, 2300, 300)],
            )
            _insert_trail_activity_row(
                conn,
                activity_id="trail-best",
                start_time="2026-07-01T08:00:00Z",
                distance_km=26.0,
                duration_sec=9200,
                ascent_m=1600,
                max_altitude_m=2300,
                climb_points=[(0, 0, 500), (1200, 700, 650), (2600, 1500, 850), (4200, 2400, 980)],
            )
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="trail_running",
                record_keys=["trail_max_single_climb"],
                dry_run=False,
            )
            before_records = career_backend.get_career_records(
                {"sport": "trail_running", "record_key": "trail_max_single_climb"},
                conn=conn,
            )
            self.assertEqual(before_records["records"][0]["activity_id"], "trail-best")

            conn.execute("UPDATE activities SET deleted_at = '2026-08-02T00:00:00Z' WHERE id = 'trail-best'")
            career_backend.invalidate_career_record_metric_results_for_activity(
                conn,
                "trail-best",
                reason="delete_activities",
                dry_run=False,
            )

            after_records = career_backend.get_career_records(
                {"sport": "trail_running", "record_key": "trail_max_single_climb"},
                conn=conn,
            )
            timeline = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(timeline)
            current_best_nodes = [
                node for node in nodes
                if node["event_type"] == "current_best"
                and node["record_key"] == "trail_max_single_climb"
            ]

            self.assertEqual(after_records["records"][0]["activity_id"], "trail-first")
            self.assertEqual(len(current_best_nodes), 1)
            self.assertEqual(current_best_nodes[0]["activity_id"], "trail-first")
            self.assertFalse(any(
                node["activity_id"] == "trail-best"
                and node["record_key"] == "trail_max_single_climb"
                for node in nodes
            ))
            _assert_forbidden_keys_absent(self, after_records)
            _assert_forbidden_keys_absent(self, timeline)
        finally:
            conn.close()

    def test_type_record_includes_metric_series_record_breaking_event_without_record_id(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record_event(
                conn,
                id="record_event:record_breaking:1",
                record_id=None,
                activity_id="run-2",
                pb_type="running_5k",
                event_type="record_breaking",
                event_at="2026-07-19",
                source="metric_series",
                record_key="running_5k",
                scope_hash="scope:default",
                scope_key="default",
                decision="record_breaking",
                payload_json=json.dumps(
                    {
                        "metric": {"value": 1700.0, "unit": "seconds", "display": "28:20"},
                        "detail_link": {"activity_id": "run-2", "source": "career"},
                    },
                    ensure_ascii=False,
                ),
            )

            result = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["event_type"], "record_breaking")
            self.assertEqual(nodes[0]["activity_id"], "run-2")
            self.assertEqual(nodes[0]["record_id"], "")
            self.assertEqual(nodes[0]["value"], "28:20")
            self.assertEqual(nodes[0]["detail_link"], {
                "activity_id": "run-2",
                "source": "career",
                "record_id": "",
            })
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_milestone_filter_includes_only_record_breaking_record_events(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            _insert_record_event(conn)
            _insert_record_event(
                conn,
                id="record_event:record_breaking:1",
                record_id=None,
                activity_id="run-2",
                pb_type="running_5k",
                event_type="record_breaking",
                event_at="2026-07-19",
                source="metric_series",
                record_key="running_5k",
                scope_hash="scope:default",
                scope_key="default",
                decision="record_breaking",
                payload_json=json.dumps(
                    {
                        "metric": {"value": 1700.0, "unit": "seconds", "display": "28:20"},
                        "detail_link": {"activity_id": "run-2", "source": "career"},
                    },
                    ensure_ascii=False,
                ),
            )

            result = career_backend.get_career_timeline({"type": "milestone"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(result["filters"], {"year": None, "type": "milestone"})
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["event_type"], "record_breaking")
            self.assertEqual(nodes[0]["activity_id"], "run-2")
            self.assertEqual(nodes[0]["track"], "milestone")
            self.assertNotIn("activated", {node["event_type"] for node in nodes})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_non_formal_events_and_race_candidates_do_not_enter_record_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            for event_type in ("detected", "candidate_created", "ignored", "recalculated", "user_rejected"):
                _insert_record_event(
                    conn,
                    id=f"record_event:{event_type}:1",
                    event_type=event_type,
                )
            _insert_candidate(conn)

            result = career_backend.get_career_timeline({"type": "record"}, conn)

            self.assertEqual(result["candidates_count"], 1)
            self.assertEqual(_flatten_nodes(result), [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_year_filter_applies_to_record_nodes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            _insert_running_activity_row(conn, activity_id="run-2025-a", start_time="2025-05-20T08:00:00Z", elapsed_5k=1800)
            _insert_running_activity_row(conn, activity_id="run-2025-b", start_time="2025-05-21T08:00:00Z", elapsed_5k=1700)
            _insert_running_activity_row(conn, activity_id="run-2026-a", start_time="2026-05-20T08:00:00Z", elapsed_5k=1600)
            career_backend.rebuild_career_record_metric_results(
                conn,
                sport="running",
                record_keys=["running_5k"],
                dry_run=False,
            )
            conn.execute("DELETE FROM career_record_events WHERE event_type = ?", (career_backend.RECORD_BREAKING_EVENT_TYPE,))

            result = career_backend.get_career_timeline({"type": "record", "year": "2026"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2026])
            self.assertEqual({node["event_type"] for node in nodes}, {"current_best"})
            self.assertEqual({node["activity_id"] for node in nodes}, {"run-2026-a"})
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
