import json
import sqlite3
import unittest

import career_backend


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            sport TEXT,
            activity_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration INTEGER,
            duration_sec INTEGER,
            total_ascent REAL,
            ascent REAL,
            elev_gain REAL,
            gain_m REAL,
            max_alt_m REAL,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            deleted_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "晨跑",
        "sport_type": "running",
        "sub_sport_type": "",
        "sport": "",
        "activity_type": "",
        "start_time": "2026-01-01T08:00:00+08:00",
        "start_time_utc": "",
        "dist_km": 5.0,
        "distance": None,
        "duration": None,
        "duration_sec": 1800,
        "total_ascent": 0,
        "ascent": None,
        "elev_gain": None,
        "gain_m": None,
        "max_alt_m": None,
        "region_city": "成都",
        "region": "",
        "region_display": "",
        "deleted_at": None,
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-01-01",
        "location_json": json.dumps({"city": "成都"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:first_running_5k:1",
        "activity_id": "1",
        "achievement_type": "first_running_5k",
        "title": "首次跑完 5K",
        "event_date": "2026-01-01",
        "score": 70,
        "icon": "flag",
        "description": "首次跑完 5K：5.0 km",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(columns)}) VALUES ({placeholders})",
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
        "event_date": "2026-01-01",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerTimelineMilestoneNodes(unittest.TestCase):
    def test_timeline_milestones_filter_out_first_city_and_pb(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_city:1", achievement_type="first_city", title="首次点亮城市")
            _insert_achievement(conn, id="achievement:first_running_5k:2", activity_id="2", event_date="2026-02-01")
            _insert_pb(conn, id="pb:running_5k:3", activity_id="3")

            result = career_backend.get_career_timeline({"type": "milestone"}, conn)

            nodes = _flatten_nodes(result)
            self.assertEqual([node["subtype"] for node in nodes], ["first_running_5k"])
            self.assertTrue(all(node["type"] == "milestone" and node["track"] == "milestone" for node in nodes))
            self.assertTrue(all(node["detail_link"]["activity_id"] for node in nodes))
        finally:
            conn.close()

    def test_timeline_derives_first_activity_first_sport_and_first_race(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, title="第一次跑步", sport_type="running", start_time="2025-01-01T08:00:00+08:00", dist_km=5.0)
            _insert_activity(conn, id=2, title="第一次骑行", sport_type="cycling", start_time="2025-01-02T08:00:00+08:00", dist_km=50.0)
            _insert_race(conn, id="race:2", activity_id="2", event_date="2025-01-02", name="首场骑行赛")

            result = career_backend.get_career_timeline({"type": "milestone"}, conn)

            by_subtype = {node["subtype"]: node for node in _flatten_nodes(result)}
            sport_firsts = [node for node in _flatten_nodes(result) if node["subtype"] == "first_sport_activity"]
            self.assertEqual(by_subtype["first_activity"]["activity_id"], "1")
            self.assertEqual({node["title"] for node in sport_firsts}, {"第一次跑步", "第一次骑行"})
            self.assertEqual(by_subtype["first_race"]["activity_id"], "2")
            self.assertEqual(by_subtype["first_race"]["value"], "半程马拉松")
        finally:
            conn.close()

    def test_first_max_altitude_5000_covers_same_activity_3000(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(
                conn,
                id=1,
                title="高海拔徒步",
                sport_type="hiking",
                start_time="2026-06-01T08:00:00+08:00",
                dist_km=12.0,
                max_alt_m=5200,
            )

            result = career_backend.get_career_timeline({"type": "milestone"}, conn)

            subtypes = [node["subtype"] for node in _flatten_nodes(result)]
            self.assertIn("first_max_altitude_5000m", subtypes)
            self.assertNotIn("first_max_altitude_3000m", subtypes)
            altitude_node = next(node for node in _flatten_nodes(result) if node["subtype"] == "first_max_altitude_5000m")
            self.assertEqual(altitude_node["value"], "5200 m")
            self.assertEqual(altitude_node["activity_id"], "1")
        finally:
            conn.close()

    def test_cumulative_distance_milestone_binds_crossing_activity(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, title="长骑 A", sport_type="cycling", start_time="2026-01-01T08:00:00+08:00", dist_km=499.0)
            _insert_activity(conn, id=2, title="长骑 B", sport_type="cycling", start_time="2026-01-02T08:00:00+08:00", dist_km=2.0)

            result = career_backend.get_career_timeline({"type": "milestone"}, conn)

            total_distance = next(node for node in _flatten_nodes(result) if node["subtype"] == "total_distance_milestone")
            self.assertEqual(total_distance["activity_id"], "2")
            self.assertEqual(total_distance["value"], "500 km")
            self.assertEqual(total_distance["badge"], "累计")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
