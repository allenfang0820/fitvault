import json
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"


class TestRegionAdmin1Backfill(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        self.temp_dir_obj.cleanup()

    def _insert_legacy_hainan_rows(self) -> int:
        conn = profile_backend._conn()
        try:
            conn.execute(
                """
                INSERT INTO geocode_cache
                    (cache_key, lat_round, lon_round, city, country, display, provider, status, created_at, updated_at, last_used_at)
                VALUES
                    ('19.87,110.28', 19.87, 110.28, '秀英区', '中国', '秀英区/中国', 'nominatim', 'success', datetime('now'), datetime('now'), datetime('now'))
                """
            )
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, title, sport_type, start_time, start_lat, start_lon,
                     region, region_city, region_country, region_display, region_status)
                VALUES
                    ('haikou.fit', '20260205_0056_海口市 操场跑步', 'running', '2026-02-05T08:56:17+08:00',
                     19.87292043864727, 110.27732438407838,
                     '秀英区/中国', '秀英区', '中国', '秀英区/中国', 'success')
                """
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def test_dry_run_reports_hainan_without_writing(self):
        activity_id = self._insert_legacy_hainan_rows()

        result = profile_backend.region_admin1_backfill_dry_run(limit=None, country_scope="CN")

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["updated_cache_count"], 1)
        self.assertEqual(result["updated_activity_count"], 1)
        conn = profile_backend._conn()
        try:
            cache = conn.execute("SELECT admin1, admin1_code FROM geocode_cache WHERE cache_key = '19.87,110.28'").fetchone()
            row = conn.execute("SELECT region_admin1, region_admin1_code FROM activities WHERE id = ?", (activity_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNone(cache["admin1"])
        self.assertIsNone(cache["admin1_code"])
        self.assertIsNone(row["region_admin1"])
        self.assertIsNone(row["region_admin1_code"])

    def test_backfill_updates_only_admin1_fields_and_lights_hainan(self):
        activity_id = self._insert_legacy_hainan_rows()

        result = profile_backend.run_region_admin1_backfill_once(limit=None, country_scope="CN")

        self.assertTrue(result["ok"])
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["version_marked"])
        self.assertEqual(result["updated_cache_count"], 1)
        self.assertEqual(result["updated_activity_count"], 1)
        conn = profile_backend._conn()
        try:
            cache = conn.execute("SELECT city, display, admin1, admin1_code FROM geocode_cache WHERE cache_key = '19.87,110.28'").fetchone()
            row = conn.execute(
                """
                SELECT title, region, region_city, region_display, region_status, region_admin1, region_admin1_code
                FROM activities WHERE id = ?
                """,
                (activity_id,),
            ).fetchone()
            footprint = career_backend.get_career_footprint(conn=conn)
            migration = conn.execute(
                "SELECT status FROM app_migrations WHERE key = ?",
                (profile_backend.REGION_ADMIN1_BACKFILL_VERSION_KEY,),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(cache["city"], "秀英区")
        self.assertEqual(cache["display"], "秀英区/中国")
        self.assertEqual(cache["admin1"], "海南省")
        self.assertEqual(cache["admin1_code"], "CN-HI")
        self.assertEqual(row["title"], "20260205_0056_海口市 操场跑步")
        self.assertEqual(row["region"], "秀英区/中国")
        self.assertEqual(row["region_city"], "秀英区")
        self.assertEqual(row["region_display"], "秀英区/中国")
        self.assertEqual(row["region_status"], "success")
        self.assertEqual(row["region_admin1"], "海南省")
        self.assertEqual(row["region_admin1_code"], "CN-HI")
        regions = {item["region_key"]: item for item in footprint["regions"]}
        self.assertIn("CN-HI", regions)
        self.assertEqual(migration["status"], "done")

    def test_backfill_is_idempotent_and_does_not_overwrite_existing_admin1(self):
        self._insert_legacy_hainan_rows()
        first = profile_backend.run_region_admin1_backfill_once(limit=None, country_scope="CN")
        second = profile_backend.run_region_admin1_backfill_once(limit=None, country_scope="CN")

        self.assertEqual(first["updated_activity_count"], 1)
        self.assertEqual(second["updated_cache_count"], 0)
        self.assertEqual(second["updated_activity_count"], 0)

        conn = profile_backend._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO activities
                    (filename, title, sport_type, start_time, start_lat, start_lon,
                     region, region_city, region_country, region_display, region_status,
                     region_admin1, region_admin1_code)
                VALUES
                    ('protected.fit', '已有省份', 'running', '2026-02-06T08:00:00+08:00',
                     19.8729, 110.2773,
                     '秀英区/中国', '秀英区', '中国', '秀英区/中国', 'success',
                     '广东省', 'CN-GD')
                """
            )
            protected_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()

        profile_backend.run_region_admin1_backfill_once(limit=None, country_scope="CN")
        conn = profile_backend._conn()
        try:
            row = conn.execute(
                "SELECT region_admin1, region_admin1_code FROM activities WHERE id = ?",
                (protected_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["region_admin1"], "广东省")
        self.assertEqual(row["region_admin1_code"], "CN-GD")

    def test_api_contract_registers_admin1_backfill_methods(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_region_admin1_backfill_dry_run", methods)
        self.assertTrue(methods["get_region_admin1_backfill_dry_run"]["readonly"])
        self.assertIn("run_region_admin1_backfill_once", methods)
        self.assertFalse(methods["run_region_admin1_backfill_once"]["readonly"])
        for name in ("get_region_admin1_backfill_dry_run", "run_region_admin1_backfill_once"):
            description = methods[name]["description"]
            self.assertIn("不调用网络", description)
            self.assertIn("不修改 region_city", description)
            self.assertIn("不返回 raw FIT", description)


if __name__ == "__main__":
    unittest.main()
