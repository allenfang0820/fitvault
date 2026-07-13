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


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


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
        "display_metadata_json": json.dumps(
            {
                "confidence_level": "high",
                "track_json": "[forbidden]",
                "storage_ref": "/Users/private/race.jpg",
                "detail_link": {"activity_id": "999"},
            },
            ensure_ascii=False,
        ),
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
        "event_date": "2026-05-20",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "resolver": "pb",
                "file_path": "/tmp/hidden.fit",
                "path": "/tmp/private.fit",
                "thumbnail_url": "file:///Users/private/thumb.jpg",
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


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:first_running_5k:1",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-05-19",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K：5.0 km",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "resolver": "achievement",
                "points_json": "[forbidden]",
                "detail_link": {"activity_id": "999"},
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


def _insert_candidate(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race_candidate:1",
        "activity_id": "9",
        "candidate_type": "race",
        "title": "低置信度疑似赛事",
        "evidence_json": json.dumps({"reason": "distance_only"}, ensure_ascii=False),
        "confidence": 0.35,
        "status": "candidate",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_event_candidates ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            start_time TEXT,
            dist_km REAL,
            duration_sec INTEGER,
            sport_type TEXT,
            region_city TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "start_time": "2026-05-01T08:00:00+08:00",
        "dist_km": 10.0,
        "duration_sec": 3600,
        "sport_type": "running",
        "region_city": "成都",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/tmp/forbidden.fit",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerTimelineEngineClosure(unittest.TestCase):
    def test_all_timeline_groups_race_and_milestone_by_year_month(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, start_time="2026-05-01T08:00:00+08:00", dist_km=10.0, duration_sec=3600, sport_type="running", region_city="成都")
            _insert_activity(conn, id=2, start_time="2026-05-02T08:00:00+08:00", dist_km=20.0, duration_sec=5400, sport_type="cycling", region_city="上海")
            _insert_activity(conn, id=3, start_time="2025-11-01T08:00:00+08:00", dist_km=5.0, duration_sec=1800, sport_type="running", region_city="杭州")
            _insert_activity(conn, id=4, start_time="2024-01-01T08:00:00+08:00", dist_km=99.0, duration_sec=9999, sport_type="running", region_city="广州", deleted_at="2026-01-01")
            _insert_race(conn, id="race:2026:5", activity_id="1", event_date="2026-05-21")
            _insert_pb(conn, id="pb:2026:5", activity_id="2", event_date="2026-05-20")
            _insert_achievement(
                conn,
                id="achievement:2026:5",
                activity_id="3",
                achievement_type="regular_training_4_weeks",
                title="连续 4 周规律运动",
                event_date="2026-05-19",
            )
            _insert_race(
                conn,
                id="race:2025:12",
                activity_id="4",
                name="2025 上海马拉松",
                event_date="2025-12-01",
            )
            _insert_pb(
                conn,
                id="pb:2025:11",
                activity_id="5",
                pb_type="running_10k",
                event_date="2025-11-30",
            )

            result = career_backend.get_career_timeline({"type": "all"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "all"})
            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2026, 2025])
            self.assertNotIn("season", result["years"][0])
            self.assertEqual([month["month"] for month in result["years"][0]["months"]], [5])
            self.assertEqual(result["years"][0]["months"][0]["year"], 2026)
            self.assertEqual(result["years"][0]["months"][0]["days_in_month"], 31)
            self.assertEqual([month["month"] for month in result["years"][1]["months"]], [12, 11])
            node_ids = [node["id"] for node in _flatten_nodes(result)]
            self.assertIn("race:2026:5", node_ids)
            self.assertIn("achievement:2026:5", node_ids)
            self.assertIn("race:2025:12", node_ids)
            self.assertIn("timeline:milestone:first_activity:3", node_ids)
            self.assertNotIn("pb:2026:5", node_ids)
            self.assertNotIn("pb:2025:11", node_ids)
            self.assertTrue({node["type"] for node in _flatten_nodes(result)} <= {"race", "milestone"})
            for node in _flatten_nodes(result):
                self.assertEqual(node["detail_link"], {"activity_id": node["activity_id"], "source": "career"})
                self.assertIn(node["track"], {"race", "milestone"})
                self.assertIsInstance(node["year"], int)
                self.assertIsInstance(node["month"], int)
                self.assertIsInstance(node["day"], int)
                self.assertIsInstance(node["priority"], int)
                self.assertNotIn("display_metadata", node)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_filters_are_exclusive_and_achievement_aliases_are_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1")
            _insert_pb(conn, id="pb:1", activity_id="2")
            _insert_achievement(conn, id="achievement:1", activity_id="3")

            race_result = career_backend.get_career_timeline({"type": "race"}, conn)
            pb_result = career_backend.get_career_timeline({"type": "pb"}, conn)
            achievement_result = career_backend.get_career_timeline({"type": "achievement"}, conn)
            achievements_result = career_backend.get_career_timeline({"type": "achievements"}, conn)
            milestone_result = career_backend.get_career_timeline({"type": "milestone"}, conn)

            self.assertEqual([node["type"] for node in _flatten_nodes(race_result)], ["race"])
            self.assertEqual(_flatten_nodes(pb_result), [])
            self.assertTrue(all(node["type"] == "milestone" for node in _flatten_nodes(achievement_result)))
            self.assertTrue(all(node["type"] == "milestone" for node in _flatten_nodes(achievements_result)))
            self.assertTrue(all(node["type"] == "milestone" for node in _flatten_nodes(milestone_result)))
            self.assertEqual(achievement_result["filters"]["type"], "milestone")
            self.assertEqual(achievements_result["filters"]["type"], "milestone")
        finally:
            conn.close()

    def test_year_filter_applies_to_all_node_families(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:2026", activity_id="1", event_date="2026-05-21")
            _insert_pb(conn, id="pb:2026", activity_id="2", event_date="2026-05-20")
            _insert_achievement(
                conn,
                id="achievement:2026",
                activity_id="3",
                achievement_type="first_running_10k",
                title="首次跑完 10K",
                event_date="2026-05-19",
            )
            _insert_race(conn, id="race:2025", activity_id="4", event_date="2025-05-21")
            _insert_pb(conn, id="pb:2025", activity_id="5", pb_type="running_10k", event_date="2025-05-20")
            _insert_achievement(conn, id="achievement:2025", activity_id="6", event_date="2025-05-19")

            result = career_backend.get_career_timeline({"type": "all", "year": "2026"}, conn)

            self.assertEqual(result["filters"], {"year": 2026, "type": "all"})
            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2026])
            self.assertEqual([node["id"] for node in _flatten_nodes(result)], ["race:2026", "achievement:2026"])
        finally:
            conn.close()

    def test_sport_filter_is_ignored_by_06b_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:running", activity_id="1", sport="running")
            _insert_race(conn, id="race:cycling", activity_id="2", sport="cycling")
            _insert_pb(conn, id="pb:running", activity_id="3", sport="running")
            _insert_pb(conn, id="pb:cycling", activity_id="4", sport="cycling", pb_type="running_10k")
            _insert_achievement(conn, id="achievement:running", activity_id="5")

            result = career_backend.get_career_timeline({"type": "all", "sport": "cycling"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "all"})
            self.assertEqual(
                {node["id"] for node in _flatten_nodes(result)},
                {"race:running", "race:cycling", "achievement:running", "timeline:milestone:first_race:2"},
            )
        finally:
            conn.close()

    def test_candidates_are_counted_but_never_enter_formal_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_candidate(conn, id="race_candidate:1", status="candidate")
            _insert_candidate(conn, id="race_candidate:2", status="candidate")
            _insert_candidate(conn, id="race_candidate:3", status="dismissed")

            result = career_backend.get_career_timeline({"type": "all"}, conn)

            self.assertEqual(result["candidates_count"], 2)
            self.assertEqual(result["years"], [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_unknown_type_is_stable_empty_state(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_race(conn, id="race:1", activity_id="1")
            _insert_pb(conn, id="pb:1", activity_id="2")
            _insert_achievement(conn, id="achievement:1", activity_id="3")

            result = career_backend.get_career_timeline({"type": "memory"}, conn)

            self.assertEqual(result["filters"], {"year": None, "type": "memory"})
            self.assertEqual(result["years"], [])
            self.assertEqual(result["available_years"], [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
