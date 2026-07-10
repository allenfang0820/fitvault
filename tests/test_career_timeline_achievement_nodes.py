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
        "event_date": "2026-05-21",
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
        "display_metadata_json": json.dumps({"resolver": "pb"}, ensure_ascii=False),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:first_running_5k:1",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-05-20",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K：5.0 km",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "resolver": "achievement",
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
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


class TestCareerTimelineAchievementNodes(unittest.TestCase):
    def test_empty_achievement_timeline_state_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_timeline({"type": "achievement"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "milestone"})
            self.assertEqual(result["available_years"], [])
            self.assertEqual(result["years"], [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_achievement_returns_only_active_achievement_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", activity_id="1", status="active")
            _insert_achievement(conn, id="achievement:first_running_10k:2", activity_id="2", status="superseded")
            _insert_race(conn, id="race:1", activity_id="3")
            _insert_pb(conn, id="pb:running_5k:1", activity_id="4")

            result = career_backend.get_career_timeline({"type": "achievement"}, conn)

            nodes = _flatten_nodes(result)
            node = next(item for item in nodes if item["id"] == "achievement:first_running_5k:1")
            self.assertEqual(node["id"], "achievement:first_running_5k:1")
            self.assertEqual(node["type"], "milestone")
            self.assertEqual(node["track"], "milestone")
            self.assertEqual(node["subtype"], "first_running_5k")
            self.assertEqual(node["activity_id"], "1")
            self.assertEqual(node["title"], "首次跑完 5K")
            self.assertEqual(node["badge"], "首次")
            self.assertEqual(node["achievement_type"], "first_running_5k")
            self.assertEqual(node["date"], "2026-05-20")
            self.assertEqual(node["year"], 2026)
            self.assertEqual(node["month"], 5)
            self.assertEqual(node["day"], 20)
            self.assertEqual(node["score"], 70)
            self.assertEqual(node["value"], "70")
            self.assertEqual(node["icon"], "flag")
            self.assertEqual(node["description"], "首次跑完 5K：5.0 km")
            self.assertEqual(node["confidence"], 1.0)
            self.assertEqual(node["source"], "resolver")
            self.assertEqual(node["detail_link"], {"activity_id": "1", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_achievement_type_aliases_return_achievement_nodes(self):
        for node_type in ("achievements", "milestone"):
            conn = sqlite3.connect(":memory:")
            try:
                career_backend.ensure_career_schema(conn)
                _insert_achievement(conn, id=f"achievement:{node_type}:1")

                result = career_backend.get_career_timeline({"type": node_type}, conn)

                nodes = _flatten_nodes(result)
                self.assertEqual([node["type"] for node in nodes], ["milestone"])
                self.assertEqual(result["filters"]["type"], "milestone")
                _assert_forbidden_keys_absent(self, result)
            finally:
                conn.close()

    def test_type_all_returns_race_and_milestone_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1", event_date="2026-05-21")
            _insert_achievement(conn, id="achievement:first_running_5k:2", activity_id="2", event_date="2026-05-20")
            _insert_pb(conn, id="pb:running_5k:3", activity_id="3", event_date="2026-05-19")

            result = career_backend.get_career_timeline({"type": "all"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual([node["type"] for node in nodes], ["race", "milestone", "milestone"])
            self.assertIn("first_race", [node["subtype"] for node in nodes if node["type"] == "milestone"])
            self.assertEqual(result["years"][0]["year"], 2026)
            self.assertEqual(result["years"][0]["months"][0]["month"], 5)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_race_and_pb_exclude_achievement_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1")
            _insert_pb(conn, id="pb:running_5k:2", activity_id="2")
            _insert_achievement(conn, id="achievement:first_running_5k:3", activity_id="3")

            race_result = career_backend.get_career_timeline({"type": "race"}, conn)
            pb_result = career_backend.get_career_timeline({"type": "pb"}, conn)

            self.assertEqual([node["type"] for node in _flatten_nodes(race_result)], ["race"])
            self.assertEqual(_flatten_nodes(pb_result), [])
        finally:
            conn.close()

    def test_sport_filter_does_not_filter_milestone_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", event_date="2026-05-20")

            result = career_backend.get_career_timeline({"type": "achievement", "sport": "cycling"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["id"], "achievement:first_running_5k:1")
            self.assertEqual(result["filters"], {"year": None, "type": "milestone"})
        finally:
            conn.close()

    def test_year_filter_applies_to_achievement_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", event_date="2026-05-20")
            _insert_achievement(
                conn,
                id="achievement:first_city:2",
                activity_id="2",
                achievement_type="first_city",
                title="首次点亮城市",
                event_date="2025-04-01",
            )

            result = career_backend.get_career_timeline({"type": "achievement", "year": "2025"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual(nodes, [])
            self.assertEqual(result["filters"], {"year": 2025, "type": "milestone"})
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
