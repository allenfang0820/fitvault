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


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            total_ascent REAL,
            ascent REAL,
            elev_gain REAL,
            gain_m REAL,
            region_city TEXT,
            region TEXT,
            region_display TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            raw_records TEXT,
            fit_records TEXT,
            file_path TEXT,
            advanced_metrics TEXT,
            shadow_diff_json TEXT,
            updated_at TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "sport_type": "running",
        "sub_sport_type": "generic",
        "start_time": "2026-01-01T08:00:00+08:00",
        "start_time_utc": "2026-01-01T00:00:00Z",
        "dist_km": 5.0,
        "distance": None,
        "total_ascent": None,
        "ascent": None,
        "elev_gain": None,
        "gain_m": None,
        "region_city": "",
        "region": "",
        "region_display": "",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "raw_records": "{}",
        "fit_records": "{}",
        "file_path": "/tmp/forbidden.fit",
        "advanced_metrics": "{}",
        "shadow_diff_json": "{}",
        "updated_at": "2026-01-01T08:00:00+08:00",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({placeholders})",
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
        "display_metadata_json": "{}",
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


def _assert_detail_links(testcase, items):
    for item in items:
        testcase.assertEqual(
            item.get("detail_link"),
            {"activity_id": str(item.get("activity_id") or ""), "source": "career"},
        )


class TestCareerAchievementPhase3Integration(unittest.TestCase):
    def test_resolver_api_timeline_and_overview_chain_is_consistent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=5.0, total_ascent=120, region_city="北京", start_time="2025-12-30T08:00:00+08:00", start_time_utc="2025-12-30T00:00:00Z")
            _insert_activity(conn, id=2, sport_type="running", dist_km=10.0, total_ascent=220, region_city="上海", start_time="2026-01-10T08:00:00+08:00", start_time_utc="2026-01-10T00:00:00Z")
            _insert_activity(conn, id=3, sport_type="running", dist_km=21.1, total_ascent=300, region_city="成都", start_time="2026-02-10T08:00:00+08:00", start_time_utc="2026-02-10T00:00:00Z")
            _insert_activity(conn, id=4, sport_type="running", dist_km=42.2, total_ascent=500, region_city="广州", start_time="2026-03-10T08:00:00+08:00", start_time_utc="2026-03-10T00:00:00Z")
            _insert_activity(conn, id=5, sport_type="cycling", dist_km=50.0, total_ascent=200, region_city="深圳", start_time="2026-04-10T08:00:00+08:00", start_time_utc="2026-04-10T00:00:00Z")
            _insert_activity(conn, id=6, sport_type="cycling", dist_km=100.0, total_ascent=900, region_city="杭州", start_time="2026-05-10T08:00:00+08:00", start_time_utc="2026-05-10T00:00:00Z")

            career_backend.ensure_career_schema(conn)
            resolver_result = career_backend.resolve_achievement_events(conn)
            achievements_payload = career_backend.get_career_achievements(conn=conn)
            timeline_achievement = career_backend.get_career_timeline({"type": "achievement"}, conn)
            timeline_all = career_backend.get_career_timeline({"type": "all"}, conn)
            overview = career_backend.get_career_overview(conn)

            achievements = achievements_payload["achievements"]
            achievement_nodes = _flatten_nodes(timeline_achievement)
            all_nodes = _flatten_nodes(timeline_all)

            self.assertTrue(resolver_result["ok"])
            self.assertGreater(len(achievements), 0)
            self.assertEqual(overview["summary"]["achievement_count"], len(achievements))
            self.assertEqual(
                [item["id"] for item in overview["representative_achievements"]],
                [item["id"] for item in achievements[:4]],
            )
            self.assertTrue(all(node["type"] == "milestone" for node in achievement_nodes))
            self.assertLess(len(achievement_nodes), len(achievements))
            self.assertNotIn("first_city", {node["subtype"] for node in achievement_nodes})
            self.assertNotIn("longest_running", {node["subtype"] for node in achievement_nodes})
            self.assertNotIn("max_ascent", {node["subtype"] for node in achievement_nodes})
            self.assertIn("first_activity", {node["subtype"] for node in achievement_nodes})
            self.assertTrue({node["id"] for node in achievement_nodes}.issubset({node["id"] for node in all_nodes}))
            _assert_detail_links(self, achievements)
            _assert_detail_links(self, achievement_nodes)
            _assert_detail_links(self, overview["representative_achievements"])
            _assert_forbidden_keys_absent(self, achievements_payload)
            _assert_forbidden_keys_absent(self, timeline_achievement)
            _assert_forbidden_keys_absent(self, timeline_all)
            _assert_forbidden_keys_absent(self, overview)
        finally:
            conn.close()

    def test_year_filter_sorting_min_score_and_overview_representatives_are_consistent(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activity_table(conn)
            _insert_activity(conn, id=1, sport_type="running", dist_km=5.0, total_ascent=120, region_city="北京", start_time="2025-12-30T08:00:00+08:00", start_time_utc="2025-12-30T00:00:00Z")
            _insert_activity(conn, id=2, sport_type="running", dist_km=10.0, total_ascent=220, region_city="上海", start_time="2026-01-10T08:00:00+08:00", start_time_utc="2026-01-10T00:00:00Z")
            _insert_activity(conn, id=3, sport_type="running", dist_km=21.1, total_ascent=300, region_city="成都", start_time="2026-02-10T08:00:00+08:00", start_time_utc="2026-02-10T00:00:00Z")
            _insert_activity(conn, id=4, sport_type="running", dist_km=42.2, total_ascent=500, region_city="广州", start_time="2026-03-10T08:00:00+08:00", start_time_utc="2026-03-10T00:00:00Z")
            _insert_activity(conn, id=5, sport_type="cycling", dist_km=50.0, total_ascent=200, region_city="深圳", start_time="2026-04-10T08:00:00+08:00", start_time_utc="2026-04-10T00:00:00Z")
            _insert_activity(conn, id=6, sport_type="cycling", dist_km=100.0, total_ascent=900, region_city="杭州", start_time="2026-05-10T08:00:00+08:00", start_time_utc="2026-05-10T00:00:00Z")

            career_backend.resolve_achievement_events(conn)

            all_payload = career_backend.get_career_achievements(conn=conn)
            year_payload = career_backend.get_career_achievements({"year": "2026"}, conn=conn)
            min_score_payload = career_backend.get_career_achievements({"min_score": "90"}, conn=conn)
            year_timeline = career_backend.get_career_timeline({"type": "achievement", "year": "2026"}, conn)
            overview = career_backend.get_career_overview(conn)

            all_ids = [item["id"] for item in all_payload["achievements"]]
            self.assertEqual(
                all_ids,
                [
                    item["id"]
                    for item in sorted(
                        all_payload["achievements"],
                        key=lambda item: (item["score"], item["event_date"], item["id"]),
                        reverse=True,
                    )
                ],
            )
            self.assertTrue(all(item["event_date"].startswith("2026") for item in year_payload["achievements"]))
            year_nodes = _flatten_nodes(year_timeline)
            self.assertTrue(all(node["year"] == 2026 for node in year_nodes))
            self.assertTrue(all(node["type"] == "milestone" for node in year_nodes))
            self.assertNotIn("first_city", {node["subtype"] for node in year_nodes})
            self.assertNotIn("longest_running", {node["subtype"] for node in year_nodes})
            self.assertNotIn("max_ascent", {node["subtype"] for node in year_nodes})
            self.assertTrue(all(item["score"] >= 90 for item in min_score_payload["achievements"]))
            self.assertLess(len(min_score_payload["achievements"]), len(all_payload["achievements"]))
            self.assertEqual(overview["summary"]["achievement_count"], len(all_payload["achievements"]))
            self.assertEqual(
                [item["id"] for item in overview["representative_achievements"]],
                all_ids[:4],
            )
            _assert_forbidden_keys_absent(self, year_payload)
            _assert_forbidden_keys_absent(self, min_score_payload)
            _assert_forbidden_keys_absent(self, year_timeline)
            _assert_forbidden_keys_absent(self, overview)
        finally:
            conn.close()

    def test_empty_state_without_activities_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.resolve_achievement_events(conn)
            achievements = career_backend.get_career_achievements(conn=conn)
            timeline = career_backend.get_career_timeline({"type": "achievement"}, conn)
            overview = career_backend.get_career_overview(conn)

            self.assertTrue(result["ok"])
            self.assertEqual(result["processed"], 0)
            self.assertEqual(achievements["achievements"], [])
            self.assertEqual(timeline["years"], [])
            self.assertEqual(overview["summary"]["achievement_count"], 0)
            self.assertEqual(overview["representative_achievements"], [])
            self.assertFalse(achievements["status"]["data_ready"])
            self.assertFalse(timeline["status"]["data_ready"])
            self.assertFalse(overview["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, achievements)
            _assert_forbidden_keys_absent(self, timeline)
            _assert_forbidden_keys_absent(self, overview)
        finally:
            conn.close()

    def test_inactive_achievements_do_not_enter_api_timeline_or_overview_representatives(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:superseded:1", activity_id="1", status="superseded", score=95)
            _insert_achievement(conn, id="achievement:inactive:2", activity_id="2", status="inactive", score=90)

            achievements = career_backend.get_career_achievements(conn=conn)
            timeline = career_backend.get_career_timeline({"type": "achievement"}, conn)
            overview = career_backend.get_career_overview(conn)

            self.assertEqual(achievements["achievements"], [])
            self.assertEqual(timeline["years"], [])
            self.assertEqual(overview["summary"]["achievement_count"], 0)
            self.assertEqual(overview["representative_achievements"], [])
            self.assertFalse(achievements["status"]["data_ready"])
            self.assertFalse(timeline["status"]["data_ready"])
            self.assertFalse(overview["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, achievements)
            _assert_forbidden_keys_absent(self, timeline)
            _assert_forbidden_keys_absent(self, overview)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
