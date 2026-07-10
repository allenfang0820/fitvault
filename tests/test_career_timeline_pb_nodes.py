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
    "advanced_metrics",
    "shadow_diff_json",
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


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "2026 成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-19",
        "location_json": json.dumps({"city": "成都"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "user",
        "status": "active",
        "display_metadata_json": json.dumps({"confidence_level": "high"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_pb(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "pb:running_5k:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-19",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "resolver": "pb",
                "pb_type": "running_5k",
                "distance_km": 5.0,
                "track_json": "[forbidden]",
                "nested": {"file_path": "/tmp/a.fit", "safe": True},
            },
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


class TestCareerTimelinePbNodes(unittest.TestCase):
    def test_empty_pb_timeline_state_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_timeline({"type": "pb"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "pb"})
            self.assertEqual(result["available_years"], [])
            self.assertEqual(result["years"], [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_pb_returns_stable_empty_timeline_even_when_pb_records_exist(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", pb_type="running_5k", status="active")
            _insert_pb(conn, id="pb:running_10k:2", activity_id="2", pb_type="running_10k", status="superseded")
            _insert_race(conn, id="race:1", activity_id="3", event_date="2026-05-20")

            result = career_backend.get_career_timeline({"type": "pb"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "pb"})
            self.assertEqual(result["available_years"], [])
            self.assertEqual(_flatten_nodes(result), [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_all_excludes_pb_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", event_date="2026-05-19")
            _insert_pb(
                conn,
                id="pb:running_half_marathon:2",
                activity_id="2",
                pb_type="running_half_marathon",
                event_date="2026-05-20",
                improvement="120",
            )

            result = career_backend.get_career_timeline({"type": "all"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual([node["type"] for node in nodes], ["race", "milestone"])
            self.assertEqual(nodes[1]["subtype"], "first_race")
            self.assertNotIn("pb", [node["type"] for node in nodes])
            self.assertEqual(result["years"][0]["year"], 2026)
            self.assertEqual(result["years"][0]["months"][0]["month"], 5)
            self.assertNotIn("pb_type", nodes[0])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_race_excludes_pb_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", event_date="2026-05-19")
            _insert_pb(conn, id="pb:running_5k:2", activity_id="2", event_date="2026-05-20")

            result = career_backend.get_career_timeline({"type": "race"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual([node["type"] for node in nodes], ["race"])
        finally:
            conn.close()

    def test_sport_and_year_filters_do_not_reintroduce_pb_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_10k:1", activity_id="1", sport="running", pb_type="running_10k", event_date="2026-06-01")
            _insert_pb(conn, id="pb:cycling_distance:2", activity_id="2", sport="cycling", pb_type="cycling_distance", event_date="2026-06-02")
            _insert_pb(conn, id="pb:running_5k:3", activity_id="3", sport="running", pb_type="running_5k", event_date="2025-05-19")

            result = career_backend.get_career_timeline({"type": "pb", "sport": "running", "year": "2026"}, conn)

            self.assertEqual(_flatten_nodes(result), [])
            self.assertEqual(result["available_years"], [])
            self.assertEqual(result["filters"], {"year": 2026, "type": "pb"})
        finally:
            conn.close()

    def test_unknown_pb_type_stays_out_of_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:custom:1", activity_id="1", pb_type="custom_pb", event_date="2026-07-01")

            result = career_backend.get_career_timeline({"type": "pb"}, conn)

            self.assertEqual(_flatten_nodes(result), [])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
