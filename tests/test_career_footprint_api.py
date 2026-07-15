import unittest
import json
import sqlite3
import tempfile
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

FORBIDDEN_SERIALIZED_TOKENS = (
    "points_json",
    "track_json",
    "file_path",
    "storage_ref",
    "raw FIT",
    "/Users/",
    "/tmp/",
    "SQLite",
)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            sport_type TEXT,
            sub_sport_type TEXT,
            region TEXT,
            region_city TEXT,
            region_country TEXT,
            region_display TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT,
            storage_ref TEXT
        )
        """
    )


def _insert_activity(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": 1,
        "title": "成都晨跑",
        "start_time": "2026-07-01T07:00:00+08:00",
        "start_time_utc": "",
        "sport_type": "running",
        "sub_sport_type": "",
        "region": "",
        "region_city": "成都市",
        "region_country": "中国",
        "region_display": "成都市/中国",
        "deleted_at": None,
        "points_json": "[forbidden]",
        "track_json": "[forbidden]",
        "file_path": "/Users/private/activity.fit",
        "storage_ref": "/tmp/private.jpg",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO activities ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _insert_race(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "race:1",
        "activity_id": "1",
        "name": "成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-07-01",
        "location_json": json.dumps({"city": "成都"}, ensure_ascii=False),
        "performance_summary_json": "{}",
        "achievement_ids_json": "[]",
        "confidence": 1.0,
        "source": "user",
        "status": "active",
        "display_metadata_json": "{}",
    }
    data.update(overrides)
    columns = list(data)
    conn.execute(
        f"INSERT INTO career_race_events ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [data[column] for column in columns],
    )


def _assert_forbidden_tokens_absent(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in FORBIDDEN_SERIALIZED_TOKENS:
        testcase.assertNotIn(token, serialized)


class TestCareerFootprintRegionResolver(unittest.TestCase):
    def test_resolves_china_city_to_province_region(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "中国",
            "region_city": "成都市",
            "region_display": "成都市/中国",
        })

        self.assertEqual(region["region_key"], "CN-SC")
        self.assertEqual(region["name"], "四川")
        self.assertEqual(region["country"], "中国")
        self.assertEqual(region["level"], "province")
        self.assertEqual(region["map_mode"], "china")

    def test_resolves_taiwan_as_china_map_region(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "中国",
            "region_city": "台北市",
            "region_display": "台北市/中国",
        })

        self.assertEqual(region["region_key"], "CN-TW")
        self.assertEqual(region["name"], "台湾")
        self.assertEqual(region["country_code"], "CN")
        self.assertEqual(region["map_mode"], "china")

    def test_resolves_taiwan_country_alias_as_china_map_region(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "Taiwan",
            "region_city": "Taipei",
            "region_display": "Taipei/Taiwan",
        })

        self.assertEqual(region["region_key"], "CN-TW")
        self.assertEqual(region["country_code"], "CN")
        self.assertEqual(region["map_mode"], "china")

    def test_resolves_taiwan_country_alias_without_city(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "Taiwan",
        })

        self.assertEqual(region["region_key"], "CN-TW")
        self.assertEqual(region["map_mode"], "china")

    def test_resolves_overseas_country_to_world_region(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "United States",
            "region_display": "United States",
        })

        self.assertEqual(region["region_key"], "US")
        self.assertEqual(region["name"], "美国")
        self.assertEqual(region["country_code"], "US")
        self.assertEqual(region["level"], "country")
        self.assertEqual(region["map_mode"], "world")

    def test_resolves_us_state_and_city_when_country_is_us(self):
        cases = (
            ({"region_country": "United States", "region_state": "California", "region_city": "San Francisco"}, "US-CA", "加利福尼亚州"),
            ({"region_country": "US", "province": "NY", "region_city": "New York"}, "US-NY", "纽约州"),
            ({"region_country": "美国", "region_city": "Boston"}, "US-MA", "马萨诸塞州"),
            ({"region_country": "USA", "region_city": "Washington D.C."}, "US-DC", "华盛顿哥伦比亚特区"),
        )
        for row, expected_key, expected_name in cases:
            with self.subTest(row=row):
                region = career_backend._resolve_career_footprint_region(row)

                self.assertEqual(region["region_key"], expected_key)
                self.assertEqual(region["name"], expected_name)
                self.assertEqual(region["country_code"], "US")
                self.assertEqual(region["map_mode"], "us")

    def test_resolves_expanded_marathon_and_southeast_asia_country_aliases(self):
        cases = {
            "Italy": ("IT", "意大利"),
            "Netherlands": ("NL", "荷兰"),
            "Thailand": ("TH", "泰国"),
            "Vietnam": ("VN", "越南"),
            "马来西亚": ("MY", "马来西亚"),
            "印尼": ("ID", "印度尼西亚"),
            "Cambodia": ("KH", "柬埔寨"),
        }
        for country, (expected_key, expected_name) in cases.items():
            with self.subTest(country=country):
                region = career_backend._resolve_career_footprint_region({
                    "region_country": country,
                    "region_display": country,
                })

                self.assertEqual(region["region_key"], expected_key)
                self.assertEqual(region["name"], expected_name)
                self.assertEqual(region["country_code"], expected_key)
                self.assertEqual(region["map_mode"], "world")

    def test_resolves_composite_multilingual_country_field_to_iso_code(self):
        cases = {
            "泰国;泰國": ("TH", "泰国"),
            "Thailand;ประเทศไทย": ("TH", "泰国"),
            "JP/日本": ("JP", "日本"),
            "United States；美国": ("US", "美国"),
            "马来西亚，馬來西亞": ("MY", "马来西亚"),
        }
        for country, (expected_key, expected_name) in cases.items():
            with self.subTest(country=country):
                region = career_backend._resolve_career_footprint_region({
                    "region_country": country,
                    "region_display": f"Somewhere/{country}",
                })

                self.assertEqual(region["region_key"], expected_key)
                self.assertEqual(region["name"], expected_name)
                self.assertEqual(region["country_code"], expected_key)
                self.assertEqual(region["map_mode"], "world")

    def test_composite_unknown_country_keeps_unmapped_fallback_without_guessing(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "未知国家;未知國家",
            "region_display": "Somewhere/未知国家;未知國家",
        })

        self.assertEqual(region["region_key"], "未知国家")
        self.assertEqual(region["country_code"], "未知国家")
        self.assertEqual(region["map_mode"], "world")

    def test_resolves_japan_prefecture_when_country_is_japan(self):
        region = career_backend._resolve_career_footprint_region({
            "region_country": "Japan",
            "region_city": "Tokyo",
            "region_display": "Tokyo/Japan",
        })

        self.assertEqual(region["region_key"], "JP-13")
        self.assertEqual(region["name"], "东京")
        self.assertEqual(region["country_code"], "JP")
        self.assertEqual(region["level"], "prefecture")
        self.assertEqual(region["map_mode"], "japan")

    def test_resolves_japan_prefecture_aliases(self):
        cases = {
            "大阪府": "JP-27",
            "Kyoto": "JP-26",
            "神户市": "JP-28",
            "Okinawa": "JP-47",
        }
        for province, expected_key in cases.items():
            with self.subTest(province=province):
                region = career_backend._resolve_career_footprint_region({
                    "region_country": "JP",
                    "province": province,
                    "region_display": f"{province}/JP",
                })

                self.assertEqual(region["region_key"], expected_key)
                self.assertEqual(region["country_code"], "JP")
                self.assertEqual(region["map_mode"], "japan")

    def test_missing_region_returns_reason_without_guessing_from_title(self):
        row = {
            "title": "成都晨跑",
            "points_json": "[forbidden]",
            "track_json": "[forbidden]",
            "file_path": "/Users/private/activity.fit",
        }

        self.assertIsNone(career_backend._resolve_career_footprint_region(row))
        self.assertEqual(career_backend._career_footprint_missing_reason(row), "missing_region")

    def test_unmapped_structured_region_is_not_forced(self):
        row = {
            "region_country": "中国",
            "region_city": "未知城市",
            "region_display": "未知城市/中国",
        }

        self.assertIsNone(career_backend._resolve_career_footprint_region(row))
        self.assertEqual(career_backend._career_footprint_missing_reason(row), "unmapped_region")


class TestCareerFootprintApi(unittest.TestCase):
    def test_empty_state_is_stable_without_activities_table(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_footprint(conn=conn)

            self.assertEqual(result["map_mode"], "china")
            self.assertEqual(result["regions"], [])
            self.assertEqual(result["without_region"], [])
            self.assertEqual(result["summary"]["activity_count"], 0)
            self.assertFalse(result["status"]["data_ready"])
        finally:
            conn.close()

    def test_china_only_activities_return_china_map_regions(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, region_city="成都市", start_time="2026-07-01T07:00:00+08:00")
            _insert_activity(conn, id=2, region_city="苏州市", region_display="苏州市/中国", start_time="2026-07-02T07:00:00+08:00")
            _insert_race(conn, activity_id="1")

            result = career_backend.get_career_footprint(conn=conn)

            self.assertEqual(result["map_mode"], "china")
            self.assertEqual(result["summary"]["activity_count"], 2)
            self.assertEqual(result["summary"]["region_count"], 2)
            self.assertEqual(result["summary"]["china_region_count"], 2)
            self.assertEqual(result["summary"]["overseas_region_count"], 0)
            regions = {item["region_key"]: item for item in result["regions"]}
            self.assertEqual(regions["CN-SC"]["race_count"], 1)
            self.assertEqual(regions["CN-JS"]["activity_count"], 1)
            self.assertEqual(regions["CN-SC"]["detail_link"], {"activity_id": "1", "source": "career"})
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_overseas_activity_triggers_world_map(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, region_city="成都市")
            _insert_activity(
                conn,
                id=2,
                start_time="2026-07-03T07:00:00+08:00",
                region_country="United States",
                region_city="San Francisco",
                region_display="San Francisco/United States",
            )

            result = career_backend.get_career_footprint(conn=conn)

            self.assertEqual(result["map_mode"], "world")
            regions = {item["region_key"]: item for item in result["regions"]}
            self.assertIn("US-CA", regions)
            self.assertEqual(regions["US-CA"]["level"], "state")
            self.assertEqual(regions["US-CA"]["map_mode"], "us")
            self.assertEqual(result["summary"]["overseas_region_count"], 1)
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_filters_deleted_and_missing_regions(self):
        conn = sqlite3.connect(":memory:")
        try:
            _create_activities_table(conn)
            career_backend.ensure_career_schema(conn)
            _insert_activity(conn, id=1, region_city="成都市", sport_type="running")
            _insert_activity(conn, id=2, region_city="杭州市", sport_type="cycling", deleted_at="2026-01-01")
            _insert_activity(conn, id=3, title="杭州骑行", region_city="", region_country="", region_display="", sport_type="cycling")

            result = career_backend.get_career_footprint({"sport": "cycling"}, conn=conn)

            self.assertEqual(result["filters"], {"sport": "cycling", "year": None})
            self.assertEqual(result["regions"], [])
            self.assertEqual(result["summary"]["activity_count"], 1)
            self.assertEqual(result["summary"]["without_region_count"], 1)
            self.assertEqual(result["without_region"][0]["activity_id"], "3")
            self.assertEqual(result["without_region"][0]["reason"], "missing_region")
            _assert_forbidden_tokens_absent(self, result)
        finally:
            conn.close()

    def test_main_api_get_career_footprint_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-footprint.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _create_activities_table(conn)
                    career_backend.ensure_career_schema(conn)
                    _insert_activity(conn, id=10, region_city="台北市", region_country="Taiwan")
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_footprint({"sport": "running"})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertEqual(response["data"]["map_mode"], "china")
                self.assertEqual(response["data"]["regions"][0]["region_key"], "CN-TW")
                _assert_forbidden_tokens_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_get_career_footprint(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_footprint", methods)
        method = methods["get_career_footprint"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("map_mode", method["returns"])
        self.assertIn("without_region", method["returns"])


if __name__ == "__main__":
    unittest.main()
