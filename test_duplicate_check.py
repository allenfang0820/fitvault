import unittest
import os
import sqlite3
from pathlib import Path
import profile_backend
import tempfile
import json

class TestDuplicateCheck(unittest.TestCase):
    def setUp(self):
        # Setup a temporary database for testing
        self.temp_db_path = "temp_test_db.sqlite"
        profile_backend.DB_PATH = Path(self.temp_db_path)
        
        # Initialize schema
        conn = profile_backend._conn()
        
        # Mock some points for spatial matching tests
        self.points_test1 = [
            {"lat": 30.0001, "lon": 104.0001, "time": "2023-01-01T10:00:00Z"},
            {"lat": 30.0002, "lon": 104.0002, "time": "2023-01-01T10:00:10Z"},
            {"lat": 30.0003, "lon": 104.0003, "time": "2023-01-01T10:00:20Z"}
        ]
        
        self.points_test2 = [
            {"lat": 31.0001, "lon": 105.0001, "time": "2023-01-02T10:00:00Z"},
            {"lat": 31.0002, "lon": 105.0002, "time": "2023-01-02T10:00:10Z"}
        ]

        # Insert some test data
        profile_backend.save_activity({
            "filename": "test1.fit",
            "dist_km": 10.5,
            "duration_sec": 3600,
            "start_time": "2023-01-01T10:00:00Z",
            "file_path": "/mock/path/test1.fit",
            "points_json": self.points_test1
        })
        
        profile_backend.save_activity({
            "filename": "test2.fit",
            "dist_km": 5.2,
            "duration_sec": 1800,
            "start_time": "2023-01-02T10:00:00Z",
            "file_path": "/mock/path/test2.fit",
            "points_json": self.points_test2
        })
        
    def tearDown(self):
        # Clean up temporary database
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)

    def test_no_duplicate(self):
        # Test a completely different track
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-03T10:00:00Z",
            dist_km=20.0,
            duration_sec=7200,
            points_json=[]
        )
        self.assertFalse(res["is_duplicate"])
        self.assertTrue(res["score"] < 80.0)

    def test_exact_duplicate(self):
        # Test an exact duplicate of test1
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.5,
            duration_sec=3600,
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")

    def test_partial_overlap_duplicate(self):
        # Test a track with same start time, slightly different distance and duration, but same points
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.53, # diff is 0.03 < 0.05
            duration_sec=3604, # diff is 4 < 5
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        
        # Test a track with same start time, slightly larger diffs, no points match
        res2 = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:00:00Z",
            dist_km=10.6, # diff is 0.1 < 0.5
            duration_sec=3620, # diff is 20 < 60
            points_json=[]
        )
        self.assertFalse(res2["is_duplicate"])

    def test_missing_start_time(self):
        # If start time is missing, it should rely on dist and duration and points
        # 由于我们优化了时区和时间解析逻辑，现在它能从 points_json 中提取时间并获得时间匹配分
        res = profile_backend.check_duplicate_activity(
            start_time=None,
            dist_km=10.51, # close to 10.5
            duration_sec=3602, # close to 3600
            points_json=self.points_test1
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)

    def test_spatial_match_duplicate(self):
        # Test a track with similar time but completely matching spatial points
        # time diff is 2 mins (120s), dist diff < 5%, dur diff < 5%, spatial match 100%
        # Score = 15 (time) + 20 (dist) + 20 (dur) + 30 (spatial) = 85 >= 80
        points_same_space = [
            {"lat": 30.0001, "lon": 104.0001, "time": "2023-01-01T10:02:00Z"},
            {"lat": 30.0002, "lon": 104.0002, "time": "2023-01-01T10:02:10Z"},
            {"lat": 30.0003, "lon": 104.0003, "time": "2023-01-01T10:02:20Z"}
        ]
        res = profile_backend.check_duplicate_activity(
            start_time="2023-01-01T10:02:00Z",
            dist_km=10.51,
            duration_sec=3600,
            points_json=points_same_space
        )
        self.assertTrue(res["is_duplicate"])
        self.assertTrue(res["score"] >= 80.0)
        self.assertEqual(res["duplicate_record"]["filename"], "test1.fit")

if __name__ == '__main__':
    unittest.main()
