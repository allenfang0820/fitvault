from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP2SnapshotRealignment(unittest.TestCase):
    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_historical_metrics_avg = MagicMock(return_value={
            "sample_size": 0,
            "hr_drift_pct": None,
            "decoupling_pct": None,
            "bonk_count": 0,
        })
        api._fetch_efficiency_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_ratio": None,
        })
        api._fetch_durability_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_ratio": None,
        })
        api._fetch_cadence_stability_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_cv": None,
        })
        api._fetch_load_ratio_7d_42d = MagicMock(return_value={
            "ratio": None,
            "level": "unknown",
            "acute_7d": None,
            "chronic_42d": None,
            "compared_count": 0,
        })
        api._fetch_training_load_trend = MagicMock(return_value={
            "level": "flat",
            "compared_count": 0,
            "baseline_load": None,
        })
        return api

    def _row(self, *, calories=1800, include_altitude=True, point_count=80) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(point_count):
            point = {
                "lat": 31.0 + i * 0.00008,
                "lon": 121.0,
                "time": (base + timedelta(seconds=i * 20)).isoformat(),
                "hr": 135 + min(i, 35),
                "speed": 3.2,
                "cadence": 84,
            }
            if include_altitude:
                point["alt"] = 1500.0 + i * 1.4
            points.append(point)
        return {
            "id": 42,
            "sport_type": "running",
            "dist_km": 7.5,
            "distance": 7500.0,
            "duration_sec": point_count * 20,
            "calories": calories,
            "track_json": json.dumps(points),
            "points_json": None,
            "merged_track_json": None,
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": json.dumps([p["speed"] for p in points]),
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
            "avg_hr": 156,
            "max_hr": 184,
            "gain_m": 420,
            "max_alt_m": 1600 if include_altitude else None,
            "avg_power": 235,
            "normalized_power": 252,
            "weather_json": json.dumps({"temperature_c": 27.5}),
        }

    def test_snapshot_curves_are_authoritative_and_length_aligned(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        curves = snapshot["curves"]
        axis_len = len(curves["distance"])

        self.assertGreater(axis_len, 0)
        self.assertEqual(curves["total_distance_m"], 7500.0)
        for key in ("time", "hr", "speed", "altitude", "grade", "gap", "efficiency", "terrain_load"):
            if curves[key]:
                self.assertEqual(len(curves[key]), axis_len, key)
        self.assertGreater(curves["distance"][-1], 0)
        self.assertLessEqual(curves["distance"][-1], curves["total_distance_m"] / 1000.0)

    def test_snapshot_builds_backend_terrain_load_from_grade_speed_time(self):
        from main import _build_fatigue_review_terrain_load_curve

        terrain_load = _build_fatigue_review_terrain_load_curve(
            grade_curve=[0.0, 5.0, -4.0, 2.0],
            speed_curve=[3.0, 3.0, 2.5, 2.0],
            time_curve=[0.0, 10.0, 20.0, 35.0],
            axis_len=4,
        )

        self.assertEqual(terrain_load, [0.0, 1.5, 1.0, 0.6])

    def test_review_fatigue_zones_merge_adjacent_same_level_only(self):
        from main import _merge_fatigue_zones_for_review

        zones = _merge_fatigue_zones_for_review([
            {"start_km": 0.0, "end_km": 0.4, "level": "high"},
            {"start_km": 0.4, "end_km": 0.9, "level": "high"},
            {"start_km": 1.2, "end_km": 1.5, "level": "high"},
            {"start_km": 1.5, "end_km": 2.0, "level": "medium"},
            {"start_km": 2.02, "end_km": 2.4, "level": "medium"},
            {"start_km": 2.5, "end_km": 2.4, "level": "medium"},
            {"start_km": "bad", "end_km": 3.0, "level": "high"},
        ])

        self.assertEqual(zones, [
            {"start_km": 0.0, "end_km": 0.9, "level": "high"},
            {"start_km": 1.2, "end_km": 1.5, "level": "high"},
            {"start_km": 1.5, "end_km": 2.4, "level": "medium"},
        ])

    def test_startup_guard_filters_running_warmup_zone(self):
        from main import _filter_fatigue_zones_after_startup

        zones = _filter_fatigue_zones_after_startup(
            [{"start_km": 0.0, "end_km": 0.15, "level": "medium"}],
            sport_type="running",
            total_distance_m=6326.0,
        )

        self.assertEqual(zones, [])

    def test_startup_guard_trims_zone_crossing_running_guard(self):
        from main import _filter_fatigue_zones_after_startup

        zones = _filter_fatigue_zones_after_startup(
            [{"start_km": 0.0, "end_km": 0.5, "level": "high", "reason": "drop"}],
            sport_type="running",
            total_distance_m=6326.0,
        )

        self.assertEqual(zones, [
            {"start_km": 0.3, "end_km": 0.5, "level": "high", "reason": "drop", "startup_trimmed": True},
        ])

    def test_startup_guard_keeps_mid_run_zone(self):
        from main import _filter_fatigue_zones_after_startup

        zones = _filter_fatigue_zones_after_startup(
            [{"start_km": 1.0, "end_km": 2.0, "level": "high"}],
            sport_type="running",
            total_distance_m=6326.0,
        )

        self.assertEqual(zones, [{"start_km": 1.0, "end_km": 2.0, "level": "high"}])

    def test_startup_trimmed_zone_is_not_user_visible_pressure_zone(self):
        from main import _filter_trusted_fatigue_zones_for_review

        zones = _filter_trusted_fatigue_zones_for_review(
            [{"start_km": 0.3, "end_km": 3.0, "level": "high", "startup_trimmed": True}],
            sport_type="running",
            total_distance_m=10000.0,
        )

        self.assertEqual(zones, [])

    def test_mid_run_zone_is_user_visible_pressure_zone(self):
        from main import _filter_trusted_fatigue_zones_for_review

        zones = _filter_trusted_fatigue_zones_for_review(
            [{"start_km": 3.0, "end_km": 4.0, "level": "high"}],
            sport_type="running",
            total_distance_m=10000.0,
        )

        self.assertEqual(zones, [{"start_km": 3.0, "end_km": 4.0, "level": "high"}])

    def test_startup_guard_does_not_trim_raw_curves(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())

        distance = snapshot["curves"]["distance"]
        self.assertGreater(len(distance), 0)
        self.assertEqual(distance[0], 0.0)

    def test_trim_review_series_after_startup_running_guard(self):
        from main import _trim_review_series_after_startup

        trimmed = _trim_review_series_after_startup(
            [1, 2, 3, 4],
            [0.0, 0.1, 0.3, 0.4],
            sport_type="running",
            total_distance_m=4000.0,
        )

        self.assertEqual(trimmed, [3, 4])

    def test_trim_review_series_keeps_original_when_axis_missing_or_mismatch(self):
        from main import _trim_review_series_after_startup

        self.assertEqual(
            _trim_review_series_after_startup([1, 2, 3], [], "running", 3000.0),
            [1, 2, 3],
        )
        self.assertEqual(
            _trim_review_series_after_startup([1, 2, 3], [0.0, 0.3], "running", 3000.0),
            [1, 2, 3],
        )

    def test_trim_review_series_uses_sport_specific_guard(self):
        from main import _trim_review_series_after_startup

        hiking = _trim_review_series_after_startup(
            [1, 2, 3, 4],
            [0.0, 0.3, 0.5, 0.8],
            sport_type="hiking",
            total_distance_m=8000.0,
        )
        cycling = _trim_review_series_after_startup(
            [1, 2, 3, 4],
            [0.0, 0.5, 1.0, 1.5],
            sport_type="cycling",
            total_distance_m=20000.0,
        )

        self.assertEqual(hiking, [3, 4])
        self.assertEqual(cycling, [3, 4])

    def test_review_input_window_caps_guard_for_short_activity(self):
        from main import _build_review_input_window

        window = _build_review_input_window(
            [0.0, 0.05, 0.1, 0.2, 0.3],
            sport_type="running",
            total_distance_m=1000.0,
        )

        self.assertEqual(window["guard_km"], 0.1)
        self.assertEqual(window["start_idx"], 2)
        self.assertTrue(window["has_aligned_axis"])

    def test_decoupling_uses_startup_trimmed_efficiency_curve(self):
        api = self._api()
        row = self._row(point_count=6)
        resolved = {
            "distance_curve": [0.0, 100.0, 300.0, 400.0, 500.0, 600.0],
            "time_curve": [0, 20, 40, 60, 80, 100],
            "altitude_curve": [100, 101, 102, 103, 104, 105],
            "gap_curve": [3, 3, 3, 3, 3, 3],
            "grade_curve": [0, 0, 0, 0, 0, 0],
            "efficiency_curve": [100, 1, 10, 10, 10, 10],
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._build_review_decoupling", return_value={"pct": 0.0, "level": "excellent"}) as decoupling_mock:
            api._build_fatigue_review_snapshot(row)

        self.assertEqual(decoupling_mock.call_args.args[0], [10, 10, 10, 10])

    def test_durability_uses_startup_trimmed_speed_curve(self):
        api = self._api()
        row = self._row(point_count=6)
        row["speed_curve"] = json.dumps([0.2, 0.4, 3.0, 3.1, 3.2, 3.3])
        resolved = {
            "distance_curve": [0.0, 100.0, 300.0, 400.0, 500.0, 600.0],
            "time_curve": [0, 20, 40, 60, 80, 100],
            "altitude_curve": [100, 101, 102, 103, 104, 105],
            "gap_curve": [3, 3, 3, 3, 3, 3],
            "grade_curve": [0, 0, 0, 0, 0, 0],
            "speed_curve": [0.2, 0.4, 3.0, 3.1, 3.2, 3.3],
            "efficiency_curve": [10, 10, 10, 10, 10, 10],
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._compute_durability_index", return_value={"score": 100, "level": "excellent"}) as durability_mock:
            api._build_fatigue_review_snapshot(row)

        self.assertEqual(durability_mock.call_args.kwargs["speed_stream"], [3.0, 3.1, 3.2, 3.3])

    def test_cadence_stability_uses_startup_trimmed_cadence_curve(self):
        api = self._api()
        row = self._row(point_count=6)
        row["cadence_curve"] = json.dumps([40, 60, 84, 85, 86, 87])
        resolved = {
            "distance_curve": [0.0, 100.0, 300.0, 400.0, 500.0, 600.0],
            "time_curve": [0, 20, 40, 60, 80, 100],
            "altitude_curve": [100, 101, 102, 103, 104, 105],
            "gap_curve": [3, 3, 3, 3, 3, 3],
            "grade_curve": [0, 0, 0, 0, 0, 0],
            "efficiency_curve": [10, 10, 10, 10, 10, 10],
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._compute_cadence_stability", return_value={"score": 95, "level": "excellent"}) as cadence_mock:
            api._build_fatigue_review_snapshot(row)

        self.assertEqual(cadence_mock.call_args.kwargs["cadence_stream"], [84, 85, 86, 87])

    def test_cadence_stability_falls_back_to_track_json_when_db_curve_missing(self):
        api = self._api()
        row = self._row(point_count=80)
        points = json.loads(row["track_json"])
        for idx, point in enumerate(points):
            point["distance"] = float(idx * 100)
            point["cadence"] = 88 + (idx % 4)
        row["track_json"] = json.dumps(points)
        row["points_json"] = json.dumps(points)
        row["cadence_curve"] = ""
        resolved = {
            "distance_curve": [float(i * 100) for i in range(80)],
            "time_curve": [i * 20 for i in range(80)],
            "altitude_curve": [100 + i for i in range(80)],
            "gap_curve": [3.0] * 80,
            "grade_curve": [0.0] * 80,
            "efficiency_curve": [10.0] * 80,
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._compute_cadence_stability", return_value={"score": 95, "level": "excellent"}) as cadence_mock:
            api._build_fatigue_review_snapshot(row)

        cadence_stream = cadence_mock.call_args.kwargs["cadence_stream"]
        self.assertGreaterEqual(len(cadence_stream), 20)
        self.assertEqual(cadence_stream[:4], [91, 88, 89, 90])

    def test_cadence_stability_prefers_db_curve_over_track_json_fallback(self):
        api = self._api()
        row = self._row(point_count=80)
        points = json.loads(row["track_json"])
        for idx, point in enumerate(points):
            point["distance"] = float(idx * 100)
            point["cadence"] = 88 + (idx % 4)
        row["track_json"] = json.dumps(points)
        row["points_json"] = json.dumps(points)
        row["cadence_curve"] = json.dumps([170 + (idx % 3) for idx in range(80)])
        resolved = {
            "distance_curve": [float(i * 100) for i in range(80)],
            "time_curve": [i * 20 for i in range(80)],
            "altitude_curve": [100 + i for i in range(80)],
            "gap_curve": [3.0] * 80,
            "grade_curve": [0.0] * 80,
            "efficiency_curve": [10.0] * 80,
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._compute_cadence_stability", return_value={"score": 95, "level": "excellent"}) as cadence_mock:
            api._build_fatigue_review_snapshot(row)

        cadence_stream = cadence_mock.call_args.kwargs["cadence_stream"]
        self.assertGreaterEqual(len(cadence_stream), 20)
        self.assertEqual(cadence_stream[:4], [170, 171, 172, 170])

    def test_review_hr_drift_records_use_real_speed_after_startup(self):
        from main import _build_review_hr_drift_records

        records = _build_review_hr_drift_records(
            hr_curve=[100, 110, 120, 130],
            speed_curve=[0.2, 0.4, 2.8, 3.1],
            distance_curve_km=[0.0, 0.1, 0.3, 0.4],
            sport_type="running",
            total_distance_m=4000.0,
        )

        self.assertEqual(
            [r["raw"] for r in records],
            [
                {"heart_rate": 120.0, "speed": 2.8, "timestamp": 2},
                {"heart_rate": 130.0, "speed": 3.1, "timestamp": 3},
            ],
        )

    def test_review_hr_drift_records_return_empty_when_lengths_mismatch(self):
        from main import _build_review_hr_drift_records

        records = _build_review_hr_drift_records(
            hr_curve=[100, 110, 120],
            speed_curve=[2.8, 3.1],
            distance_curve_km=[0.0, 0.3, 0.4],
            sport_type="running",
            total_distance_m=4000.0,
        )

        self.assertEqual(records, [])

    def test_review_hr_drift_records_use_sport_specific_startup_guard(self):
        from main import _build_review_hr_drift_records

        hiking = _build_review_hr_drift_records(
            hr_curve=[100, 110, 120, 130],
            speed_curve=[1.0, 1.1, 1.2, 1.3],
            distance_curve_km=[0.0, 0.3, 0.5, 0.8],
            sport_type="hiking",
            total_distance_m=8000.0,
        )
        cycling = _build_review_hr_drift_records(
            hr_curve=[100, 110, 120, 130],
            speed_curve=[5.0, 5.5, 6.0, 6.5],
            distance_curve_km=[0.0, 0.5, 1.0, 1.5],
            sport_type="cycling",
            total_distance_m=20000.0,
        )

        self.assertEqual([r["raw"]["heart_rate"] for r in hiking], [120.0, 130.0])
        self.assertEqual([r["raw"]["heart_rate"] for r in cycling], [120.0, 130.0])

    def test_snapshot_hr_drift_uses_real_speed_records_after_startup(self):
        api = self._api()
        row = self._row(point_count=6)
        resolved = {
            "distance_curve": [0.0, 100.0, 300.0, 400.0, 500.0, 600.0],
            "time_curve": [0, 20, 40, 60, 80, 100],
            "altitude_curve": [100, 101, 102, 103, 104, 105],
            "gap_curve": [3, 3, 3, 3, 3, 3],
            "grade_curve": [0, 0, 0, 0, 0, 0],
            "efficiency_curve": [10, 10, 10, 10, 10, 10],
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main.MetricsResolver._compute_hr_drift", return_value={"drift_pct": None, "level": "unknown", "confidence": "unavailable"}) as drift_mock:
            api._build_fatigue_review_snapshot(row)

        records = drift_mock.call_args.kwargs["records"]
        self.assertEqual([r["raw"]["heart_rate"] for r in records], [137.0, 138.0, 139.0, 140.0])
        self.assertEqual([r["raw"]["speed"] for r in records], [3.2, 3.2, 3.2, 3.2])
        self.assertNotIn(3.0, [r["raw"]["speed"] for r in records])

    def test_snapshot_metrics_share_single_review_input_window(self):
        import main

        api = self._api()
        row = self._row(point_count=6)
        row["speed_curve"] = json.dumps([0.2, 0.4, 3.0, 3.1, 3.2, 3.3])
        row["cadence_curve"] = json.dumps([40, 60, 84, 85, 86, 87])
        resolved = {
            "distance_curve": [0.0, 100.0, 300.0, 400.0, 500.0, 600.0],
            "time_curve": [0, 20, 40, 60, 80, 100],
            "altitude_curve": [100, 101, 102, 103, 104, 105],
            "gap_curve": [3, 3, 3, 3, 3, 3],
            "grade_curve": [0, 0, 0, 0, 0, 0],
            "speed_curve": [0.2, 0.4, 3.0, 3.1, 3.2, 3.3],
            "efficiency_curve": [100, 1, 10, 10, 10, 10],
            "insight_events": [],
            "fatigue_zones": [],
            "context_tags": {},
        }

        with patch("main._build_resolved_payload_v81", return_value=resolved), \
             patch("main._build_review_input_window", wraps=main._build_review_input_window) as window_mock, \
             patch("main.MetricsResolver._build_review_decoupling", return_value={"pct": 0.0, "level": "excellent"}) as decoupling_mock, \
             patch("main.MetricsResolver._compute_hr_drift", return_value={"drift_pct": None, "level": "unknown", "confidence": "unavailable"}) as drift_mock, \
             patch("main.MetricsResolver._compute_durability_index", return_value={"score": 100, "level": "excellent"}) as durability_mock, \
             patch("main.MetricsResolver._compute_cadence_stability", return_value={"score": 95, "level": "excellent"}) as cadence_mock:
            api._build_fatigue_review_snapshot(row)

        self.assertEqual(window_mock.call_count, 1)
        self.assertEqual(decoupling_mock.call_args.args[0], [10, 10, 10, 10])
        self.assertEqual(durability_mock.call_args.kwargs["speed_stream"], [3.0, 3.1, 3.2, 3.3])
        self.assertEqual(cadence_mock.call_args.kwargs["cadence_stream"], [84, 85, 86, 87])
        self.assertEqual([r["raw"]["heart_rate"] for r in drift_mock.call_args.kwargs["records"]], [137.0, 138.0, 139.0, 140.0])

    def test_snapshot_missing_calories_keeps_curves_and_disables_bonk_risk(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row(calories=None))

        self.assertGreater(len(snapshot["curves"]["distance"]), 0)
        self.assertFalse(snapshot["metrics"]["bonk_risk"]["is_at_risk"])

    def test_snapshot_incomplete_points_uses_empty_missing_curves(self):
        snapshot = self._api()._build_fatigue_review_snapshot(
            self._row(include_altitude=False, point_count=10)
        )

        curves = snapshot["curves"]
        self.assertIn("distance", curves)
        self.assertIn("altitude", curves)
        self.assertIsInstance(curves["altitude"], list)
        for key in ("metrics", "collapse_events", "fatigue_zones", "context_tags", "advice"):
            self.assertIn(key, snapshot)

    def test_snapshot_environment_context_keeps_neutral_weather_facts(self):
        row = self._row(calories=393, include_altitude=False)
        row["avg_hr"] = 151
        row["max_hr"] = 180
        row["gain_m"] = 6
        row["max_alt_m"] = 51.6
        row["weather_json"] = json.dumps({
            "temperature_c": 17.1,
            "humidity": 77,
            "wind_speed_kmh": 0.8,
            "weather_label": "阴",
            "observed_date": "2025-09-19",
            "observed_hour": 6,
        })

        profile = MagicMock(max_hr=186, resting_hr=51, lactate_threshold_hr=166)
        with patch("profile_backend.get_profile", return_value=profile):
            snapshot = self._api()._build_fatigue_review_snapshot(row)

        env = snapshot["environment_context"]
        self.assertTrue(env["has_weather"])
        self.assertEqual(env["temperature_c"], 17.1)
        self.assertEqual(env["humidity"], 77.0)
        self.assertEqual(env["weather_label"], "阴")
        self.assertEqual(env["pressure_level"], "none")
        self.assertIn("未识别到明显外部环境压力", env["summary"])
        self.assertNotIn("热应激", json.dumps(snapshot["context_tags"], ensure_ascii=False))

    def test_snapshot_context_tags_use_backend_session_and_weather_fields(self):
        profile = MagicMock(max_hr=184, resting_hr=52, lactate_threshold_hr=166)
        row = self._row()
        row["avg_hr"] = 172
        with patch("profile_backend.get_profile", return_value=profile):
            snapshot = self._api()._build_fatigue_review_snapshot(row)

        tags = snapshot["context_tags"]
        self.assertTrue(tags)
        encoded = json.dumps(tags, ensure_ascii=False)
        self.assertIn("热应激", encoded)
        self.assertIn("心肺负荷", encoded)
        self.assertIn("HRR=91%", encoded)
        self.assertIn("海拔缺氧", encoded)
        self.assertTrue(snapshot["environment_context"]["has_weather"])
        self.assertEqual(snapshot["environment_context"]["temperature_c"], 27.5)

    def test_snapshot_context_tags_skip_moderate_cardio_load(self):
        row = self._row(calories=600, include_altitude=False)
        row["avg_hr"] = 150
        row["max_hr"] = 200
        row["weather_json"] = json.dumps({"temperature_c": 12.0})

        profile = MagicMock(max_hr=200, resting_hr=52, lactate_threshold_hr=166)
        with patch("profile_backend.get_profile", return_value=profile):
            snapshot = self._api()._build_fatigue_review_snapshot(row)
        encoded = json.dumps(snapshot["context_tags"], ensure_ascii=False)

        self.assertNotIn("心肺负荷", encoded)

    def test_snapshot_context_tags_skip_cardio_load_without_profile_max_hr(self):
        row = self._row(calories=600, include_altitude=False)
        row["avg_hr"] = 150
        row["max_hr"] = 150
        row["weather_json"] = json.dumps({"temperature_c": 12.0})

        profile = MagicMock(max_hr=None, resting_hr=52, lactate_threshold_hr=166)
        with patch("profile_backend.get_profile", return_value=profile):
            snapshot = self._api()._build_fatigue_review_snapshot(row)
        encoded = json.dumps(snapshot["context_tags"], ensure_ascii=False)

        self.assertNotIn("心肺负荷", encoded)

    def test_resolved_payload_short_records_returns_safe_fallback(self):
        from main import _build_resolved_payload_v81

        payload = _build_resolved_payload_v81(
            bundle={
                "records": [{"distance": 0.0, "heart_rate": 120}],
                "distance_curve_m": [0.0],
                "time_curve_sec": [0.0],
                "altitude_curve_m": [100.0],
            },
            sport_type="running",
        )

        self.assertEqual(payload["distance_curve"], [0.0])
        self.assertEqual(payload["time_curve"], [0.0])
        self.assertEqual(payload["altitude_curve"], [100.0])
        self.assertEqual(payload["context_tags"], {})

    def test_snapshot_recursively_strips_forbidden_fields(self):
        from main import _strip_fatigue_review_forbidden_keys

        cleaned = _strip_fatigue_review_forbidden_keys({
            "curves": {"distance": [0], "records": [{"x": 1}]},
            "context_tags": {"shadow_diff": "debug", "ok": "yes"},
            "events": [{"diff": "debug", "type": "x"}],
        })
        encoded = json.dumps(cleaned, ensure_ascii=False)

        for forbidden in ("records", "shadow_diff", '"diff"'):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(cleaned["context_tags"]["ok"], "yes")

    def test_get_fatigue_review_error_envelope_paths(self):
        from main import API_CODE_NOT_FOUND, API_CODE_VALIDATION, Api

        api = Api()
        invalid = api.get_fatigue_review(0)
        self.assertEqual(invalid["code"], API_CODE_VALIDATION)
        self.assertIn("traceId", invalid)
        self.assertEqual(invalid["data"], {})

        api._fetch_activity_row = MagicMock(return_value=None)
        not_found = api.get_fatigue_review(999999999)
        self.assertEqual(not_found["code"], API_CODE_NOT_FOUND)
        self.assertIn("traceId", not_found)
        self.assertEqual(not_found["data"], {})


if __name__ == "__main__":
    unittest.main()
