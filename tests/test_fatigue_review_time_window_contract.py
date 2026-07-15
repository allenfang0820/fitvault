from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestFatigueReviewTimeWindowContract(unittest.TestCase):
    def _tmp_db(self, schema: str) -> str:
        fd, path = tempfile.mkstemp(prefix="fr_time_window_", suffix=".sqlite")
        os.close(fd)
        conn = sqlite3.connect(path)
        try:
            conn.execute(schema)
            conn.commit()
        finally:
            conn.close()
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_durability_trend_uses_activity_21d_window_and_excludes_future(self):
        from main import Api
        import profile_backend

        db_path = self._tmp_db(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                speed_curve TEXT,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        as_of = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
        rows = []
        for idx, days_before in enumerate((3, 7, 14), start=1):
            rows.append(
                (
                    idx,
                    "running",
                    (as_of - timedelta(days=days_before)).isoformat(),
                    json.dumps([3.0] * 100),
                    3600,
                    None,
                )
            )
        rows.extend(
            [
                (
                    20,
                    "running",
                    (as_of - timedelta(days=28)).isoformat(),
                    json.dumps([2.0] * 100),
                    3600,
                    None,
                ),
                (
                    21,
                    "running",
                    (as_of + timedelta(days=1)).isoformat(),
                    json.dumps([5.0] * 100),
                    3600,
                    None,
                ),
            ]
        )
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany("INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        with patch.object(profile_backend, "DB_PATH", db_path):
            trend = Api.__new__(Api)._fetch_durability_trend(
                {
                    "id": 99,
                    "sport_type": "running",
                    "start_time": as_of.isoformat(),
                    "duration_sec": 3600,
                }
            )

        self.assertEqual(trend["compared_count"], 3)
        self.assertEqual(trend["baseline_ratio"], 1.0)

    def test_durability_trend_rebuilds_baseline_from_canonical_track_json(self):
        from main import Api
        import profile_backend

        db_path = self._tmp_db(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                track_json TEXT,
                speed_curve TEXT,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        as_of = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
        points = json.dumps([{"speed": 3.0} for _ in range(100)])
        rows = [
            (idx, "running", (as_of - timedelta(days=idx)).isoformat(), points, None, 3600, None)
            for idx in (1, 2, 3)
        ]
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany("INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        with patch.object(profile_backend, "DB_PATH", db_path):
            trend = Api.__new__(Api)._fetch_durability_trend(
                {
                    "id": 99,
                    "sport_type": "running",
                    "start_time": as_of.isoformat(),
                    "duration_sec": 3600,
                }
            )

        self.assertEqual(trend["compared_count"], 3)
        self.assertEqual(trend["baseline_ratio"], 1.0)
        self.assertEqual(trend["basis"], "speed_tail_head_ratio")
        self.assertEqual(trend["version"], "fr_core_10_canonical_curve_v1")
        self.assertEqual(trend["source_quality"], "canonical_track_json")

    def test_durability_trend_falls_back_when_canonical_field_missing(self):
        from main import Api
        import profile_backend

        db_path = self._tmp_db(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                track_json TEXT,
                speed_curve TEXT,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        as_of = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
        canonical_without_speed = json.dumps([{"heart_rate": 140} for _ in range(100)])
        legacy_speed_curve = json.dumps([3.0] * 100)
        rows = [
            (
                idx,
                "running",
                (as_of - timedelta(days=idx)).isoformat(),
                canonical_without_speed,
                legacy_speed_curve,
                3600,
                None,
            )
            for idx in (1, 2, 3)
        ]
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany("INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        with patch.object(profile_backend, "DB_PATH", db_path):
            trend = Api.__new__(Api)._fetch_durability_trend(
                {
                    "id": 99,
                    "sport_type": "running",
                    "start_time": as_of.isoformat(),
                    "duration_sec": 3600,
                }
            )

        self.assertEqual(trend["compared_count"], 3)
        self.assertEqual(trend["baseline_ratio"], 1.0)
        self.assertEqual(trend["source_quality"], "mixed_with_legacy_derivative")

    def test_cadence_trend_rebuilds_baseline_from_canonical_track_json(self):
        from main import Api
        import profile_backend

        db_path = self._tmp_db(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                track_json TEXT,
                cadence_curve TEXT,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        as_of = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
        points = json.dumps([{"cadence": 170 + (idx % 2)} for idx in range(100)])
        rows = [
            (idx, "running", (as_of - timedelta(days=idx)).isoformat(), points, None, 1800, None)
            for idx in (1, 2, 3)
        ]
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany("INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        with patch.object(profile_backend, "DB_PATH", db_path):
            trend = Api.__new__(Api)._fetch_cadence_stability_trend(
                {
                    "id": 99,
                    "sport_type": "running",
                    "start_time": as_of.isoformat(),
                    "duration_sec": 1800,
                }
            )

        self.assertEqual(trend["compared_count"], 3)
        self.assertIsNotNone(trend["baseline_cv"])
        self.assertEqual(trend["basis"], "cadence_cv")
        self.assertEqual(trend["version"], "fr_core_10_canonical_curve_v1")
        self.assertEqual(trend["source_quality"], "canonical_track_json")

    def test_load_ratio_7d_42d_uses_activity_as_of_and_excludes_future(self):
        from main import Api
        import profile_backend

        db_path = self._tmp_db(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                avg_hr REAL,
                max_hr REAL,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        as_of = datetime(2025, 3, 1, 8, 0, tzinfo=timezone.utc)
        rows = []
        for idx, days_before in enumerate((3, 10, 17, 24, 31, 38), start=1):
            rows.append(
                (
                    idx,
                    "running",
                    (as_of - timedelta(days=days_before)).isoformat(),
                    150,
                    200,
                    3600,
                    None,
                )
            )
        rows.append(
            (
                50,
                "running",
                (as_of + timedelta(days=2)).isoformat(),
                180,
                200,
                3600,
                None,
            )
        )
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany("INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        with patch.object(profile_backend, "DB_PATH", db_path), patch.object(
            profile_backend,
            "get_profile",
            return_value=MagicMock(max_hr=200, resting_hr=50),
        ):
            ratio = Api.__new__(Api)._fetch_load_ratio_7d_42d(
                {
                    "id": 99,
                    "sport_type": "running",
                    "start_time": as_of.isoformat(),
                    "avg_hr": 150,
                    "max_hr": 200,
                    "duration_sec": 3600,
                }
            )

        self.assertEqual(ratio["compared_count"], 6)
        self.assertEqual(ratio["acute_7d"], 240.0)
        self.assertEqual(ratio["chronic_42d"], 840.0)
        self.assertEqual(ratio["ratio"], 1.71)


if __name__ == "__main__":
    unittest.main()
