from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import profile_backend  # noqa: E402

TRACK_HTML = os.path.join(PROJECT_ROOT, "track.html")


class TestUserProfileTotalDistanceBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = profile_backend.DB_PATH
        self.original_schema_ready = profile_backend._SCHEMA_READY_FOR
        profile_backend.DB_PATH = Path(self.tmp.name) / "user_profile.db"
        profile_backend._SCHEMA_READY_FOR = None

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_schema_ready
        self.tmp.cleanup()

    def test_schema_adds_total_distance_columns_to_old_profile_table(self):
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        try:
            conn.execute("CREATE TABLE user_profile (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
            conn.commit()
        finally:
            conn.close()

        conn = profile_backend._conn()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(user_profile)").fetchall()}
        finally:
            conn.close()

        for field in ("total_run_km", "total_hike_km", "total_cycle_km", "total_swim_km"):
            self.assertIn(field, columns)

    def test_upsert_and_get_profile_round_trip_total_distance_fields(self):
        profile_backend.upsert_profile(
            {
                "name": "athlete",
                "total_run_km": 1234.5,
                "total_hike_km": 222.2,
                "total_cycle_km": 3456.7,
                "total_swim_km": 88.8,
            }
        )

        profile = profile_backend.get_profile().to_dict()

        self.assertEqual(profile["total_run_km"], 1234.5)
        self.assertEqual(profile["total_hike_km"], 222.2)
        self.assertEqual(profile["total_cycle_km"], 3456.7)
        self.assertEqual(profile["total_swim_km"], 88.8)


class TestUserProfileTotalDistanceFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TRACK_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_total_distance_fields_are_placed_under_sport_tabs(self):
        self.assertIn('id="pf-total-run"', self.html)
        self.assertIn('id="pf-total-hike"', self.html)
        self.assertIn('id="pf-total-cycle"', self.html)
        self.assertIn('id="pf-total-swim"', self.html)

    def test_update_profile_panel_writes_total_distance_fields(self):
        self.assertIn("profile.total_run_km", self.html)
        self.assertIn("profile.total_hike_km", self.html)
        self.assertIn("profile.total_cycle_km", self.html)
        self.assertIn("profile.total_swim_km", self.html)


if __name__ == "__main__":
    unittest.main()
