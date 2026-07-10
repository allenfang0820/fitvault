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


class TestCareerOverviewRepresentativeAchievements(unittest.TestCase):
    def test_empty_overview_representative_achievements_shape_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["representative_achievements"], [])
            self.assertEqual(result["summary"]["achievement_count"], 0)
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_active_achievements_enter_overview_representative_achievements(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(
                conn,
                id="achievement:max_ascent:2",
                activity_id="2",
                achievement_type="max_ascent",
                title="最大累计爬升",
                description="最大累计爬升：1200 m",
                score=85,
                icon="mountain",
                event_date="2026-06-01",
            )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["achievement_count"], 1)
            self.assertTrue(result["status"]["data_ready"])
            achievements = result["representative_achievements"]
            self.assertEqual(len(achievements), 1)
            achievement = achievements[0]
            self.assertEqual(achievement["id"], "achievement:max_ascent:2")
            self.assertEqual(achievement["activity_id"], "2")
            self.assertEqual(achievement["achievement_type"], "max_ascent")
            self.assertEqual(achievement["title"], "最大累计爬升")
            self.assertEqual(achievement["event_date"], "2026-06-01")
            self.assertEqual(achievement["score"], 85)
            self.assertEqual(achievement["icon"], "mountain")
            self.assertEqual(achievement["description"], "最大累计爬升：1200 m")
            self.assertEqual(achievement["confidence"], 1.0)
            self.assertEqual(achievement["source"], "resolver")
            self.assertEqual(achievement["detail_link"], {"activity_id": "2", "source": "career"})
            self.assertEqual(achievement["display_metadata"], {"resolver": "achievement", "nested": {"safe": True}})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_inactive_achievements_are_excluded_from_overview(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:active:1", activity_id="1", status="active", score=70)
            _insert_achievement(conn, id="achievement:superseded:2", activity_id="2", status="superseded", score=100)

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["achievement_count"], 1)
            self.assertEqual(
                [achievement["id"] for achievement in result["representative_achievements"]],
                ["achievement:active:1"],
            )
        finally:
            conn.close()

    def test_representative_achievements_sort_by_score_date_and_id_desc_and_limit_to_four(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:a", activity_id="1", score=70, event_date="2026-05-19")
            _insert_achievement(conn, id="achievement:b", activity_id="2", score=90, event_date="2026-05-18")
            _insert_achievement(conn, id="achievement:c", activity_id="3", score=90, event_date="2026-05-20")
            _insert_achievement(conn, id="achievement:d", activity_id="4", score=90, event_date="2026-05-20")
            _insert_achievement(conn, id="achievement:e", activity_id="5", score=80, event_date="2026-06-01")
            _insert_achievement(conn, id="achievement:f", activity_id="6", score=60, event_date="2026-07-01")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["achievement_count"], 6)
            self.assertEqual(
                [achievement["id"] for achievement in result["representative_achievements"]],
                ["achievement:d", "achievement:c", "achievement:b", "achievement:e"],
            )
        finally:
            conn.close()

    def test_representative_achievements_are_safe_when_overview_has_only_pb_or_race(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            conn.execute(
                """
                INSERT INTO career_pb_records
                    (id, activity_id, sport, pb_type, value, value_unit, event_date, confidence, source, status)
                VALUES
                    ('pb:running_5k:1', '1', 'running', 'running_5k', '1500', 'seconds', '2026-05-19', 1.0, 'resolver', 'active')
                """
            )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["pb_count"], 1)
            self.assertEqual(result["summary"]["achievement_count"], 0)
            self.assertEqual(result["representative_achievements"], [])
            self.assertTrue(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
