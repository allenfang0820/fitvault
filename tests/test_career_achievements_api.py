import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

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
FORBIDDEN_METADATA_KEYS = FORBIDDEN_RESPONSE_KEYS | {
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _assert_forbidden_metadata_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_METADATA_KEYS)
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


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
                "achievement_type": "first_running_5k",
                "distance_km": 5.0,
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


class TestCareerAchievementsApi(unittest.TestCase):
    def test_backend_empty_state_returns_stable_shape(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_achievements(conn=conn)

            self.assertEqual(result["achievements"], [])
            self.assertEqual(result["summary"], {
                "total": 0,
                "by_type": {},
                "by_category": {},
                "by_year": {},
                "by_source": {},
                "max_score": None,
            })
            self.assertEqual(result["filters"], {
                "achievement_type": "all",
                "category": "all",
                "year": None,
                "source": "all",
                "min_score": None,
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_returns_only_active_achievements(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", activity_id="1", status="active")
            _insert_achievement(conn, id="achievement:first_running_5k:2", activity_id="2", status="superseded")

            result = career_backend.get_career_achievements(conn=conn)

            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(len(result["achievements"]), 1)
            achievement = result["achievements"][0]
            self.assertEqual(achievement["id"], "achievement:first_running_5k:1")
            self.assertEqual(achievement["activity_id"], "1")
            self.assertEqual(achievement["achievement_title"], "首次跑完 5K")
            self.assertEqual(achievement["achievement_type_label"], "首次跑完 5K")
            self.assertEqual(achievement["category"], "first_distance")
            self.assertEqual(achievement["category_label"], "首次突破")
            self.assertEqual(achievement["sport"], "running")
            self.assertEqual(achievement["sport_label"], "跑步")
            self.assertEqual(achievement["year"], 2026)
            self.assertEqual(achievement["month"], 5)
            self.assertEqual(achievement["display_date"], "2026-05-19")
            self.assertEqual(achievement["score_label"], "70 分")
            self.assertEqual(achievement["source_label"], "规则识别")
            self.assertEqual(achievement["confidence_label"], "高置信度")
            self.assertEqual(achievement["detail_link"], {"activity_id": "1", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_filters_by_type_year_source_and_min_score(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", achievement_type="first_running_5k", source="resolver", event_date="2026-05-19", score=70)
            _insert_achievement(conn, id="achievement:max_ascent:2", activity_id="2", achievement_type="max_ascent", title="最大累计爬升", source="resolver", event_date="2026-06-01", score=85)
            _insert_achievement(conn, id="achievement:first_city:beijing:3", activity_id="3", achievement_type="first_city", title="首次点亮城市", source="manual", event_date="2025-04-01", score=60)

            result = career_backend.get_career_achievements(
                {"type": "max_ascent", "year": "2026", "source": "resolver", "min_score": "80"},
                conn=conn,
            )

            self.assertEqual(result["filters"], {
                "achievement_type": "max_ascent",
                "category": "all",
                "year": 2026,
                "source": "resolver",
                "min_score": 80,
            })
            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(result["achievements"][0]["id"], "achievement:max_ascent:2")
        finally:
            conn.close()

    def test_backend_filters_by_category(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", achievement_type="first_running_5k", event_date="2026-05-19", score=70)
            _insert_achievement(conn, id="achievement:max_ascent:2", activity_id="2", achievement_type="max_ascent", title="最大累计爬升", event_date="2026-06-01", score=85)

            result = career_backend.get_career_achievements({"category": "record"}, conn=conn)

            self.assertEqual(result["filters"]["category"], "record")
            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(result["achievements"][0]["achievement_type"], "max_ascent")
            self.assertEqual(result["achievements"][0]["category_label"], "个人纪录")
        finally:
            conn.close()

    def test_invalid_year_and_min_score_are_normalized_to_null(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_achievements(
                {"year": "bad", "min_score": "nope"},
                conn=conn,
            )

            self.assertEqual(result["filters"]["year"], None)
            self.assertEqual(result["filters"]["min_score"], None)
        finally:
            conn.close()

    def test_backend_summary_counts_returned_achievements(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:first_running_5k:1", achievement_type="first_running_5k", source="resolver", event_date="2026-05-19", score=70)
            _insert_achievement(conn, id="achievement:max_ascent:2", activity_id="2", achievement_type="max_ascent", title="最大累计爬升", source="resolver", event_date="2026-06-01", score=85)
            _insert_achievement(conn, id="achievement:first_city:beijing:3", activity_id="3", achievement_type="first_city", title="首次点亮城市", source="manual", event_date="2025-04-01", score=60)

            result = career_backend.get_career_achievements(conn=conn)

            self.assertEqual(result["summary"]["total"], 3)
            self.assertEqual(result["summary"]["by_type"], {
                "max_ascent": 1,
                "first_running_5k": 1,
                "first_city": 1,
            })
            self.assertEqual(result["summary"]["by_category"], {
                "record": 1,
                "first_distance": 1,
                "location": 1,
            })
            self.assertEqual(result["summary"]["by_year"], {"2026": 2, "2025": 1})
            self.assertEqual(result["summary"]["by_source"], {"resolver": 2, "manual": 1})
            self.assertEqual(result["summary"]["max_score"], 85)
        finally:
            conn.close()

    def test_backend_sorts_by_score_date_and_id_desc(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(conn, id="achievement:a", activity_id="1", score=70, event_date="2026-05-19")
            _insert_achievement(conn, id="achievement:b", activity_id="2", score=90, event_date="2026-05-18")
            _insert_achievement(conn, id="achievement:c", activity_id="3", score=90, event_date="2026-05-20")
            _insert_achievement(conn, id="achievement:d", activity_id="4", score=90, event_date="2026-05-20")

            result = career_backend.get_career_achievements(conn=conn)

            self.assertEqual(
                [item["id"] for item in result["achievements"]],
                ["achievement:d", "achievement:c", "achievement:b", "achievement:a"],
            )
        finally:
            conn.close()

    def test_backend_sanitizes_forbidden_metadata_keys(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_achievement(
                conn,
                display_metadata_json=json.dumps(
                    {
                        "resolver": "achievement",
                        "track_json": "[forbidden]",
                        "storage_ref": "/Users/private/achievement.jpg",
                        "path": "/tmp/private.fit",
                        "thumbnail_url": "file:///Users/private/thumb.jpg",
                        "detail_link": {"activity_id": "999", "source": "leak"},
                        "nested": {
                            "file_path": "/tmp/a.fit",
                            "city": "北京",
                            "items": [
                                {"thumbnail_url": "file:///Users/private/item.jpg"},
                                {"safe": "kept"},
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
            )

            result = career_backend.get_career_achievements(conn=conn)

            metadata = result["achievements"][0]["display_metadata"]
            self.assertEqual(
                metadata,
                {
                    "resolver": "achievement",
                    "nested": {
                        "city": "北京",
                        "items": [{}, {"safe": "kept"}],
                    },
                },
            )
            _assert_forbidden_metadata_absent(self, metadata)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_main_api_get_career_achievements_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-achievements-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                    _insert_achievement(conn, id="achievement:max_ascent:10", activity_id="10", achievement_type="max_ascent", title="最大累计爬升", score=85)
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_achievements({"achievement_type": "max_ascent"})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertIsInstance(response["traceId"], str)
                self.assertEqual(response["data"]["summary"]["total"], 1)
                self.assertEqual(response["data"]["achievements"][0]["activity_id"], "10")
                _assert_forbidden_keys_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_get_career_achievements(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_achievements", methods)
        method = methods["get_career_achievements"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("achievements", method["returns"])


if __name__ == "__main__":
    unittest.main()
