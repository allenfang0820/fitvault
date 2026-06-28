import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

import fit_engine
import llm_backend
import track_backend
from metrics_resolver import MetricsResolver


def _first_existing(paths: list[str]) -> Optional[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            return path
    return None


def _write_minimal_fit_header(path: str) -> None:
    Path(path).write_bytes(bytes([14]) + b"\x00" * 7 + b".FIT" + b"\x00" * 2)


class FakeField:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FakeMessage:
    def __init__(self, **kwargs):
        self._data = dict(kwargs)
        self.fields = [FakeField(k, v) for k, v in self._data.items()]

    def get_value(self, key):
        return self._data.get(key)


class FakeFitFile:
    def __init__(self, _path, check_crc=True):
        self.check_crc = check_crc

    def get_messages(self, kind):
        if kind == "session":
            return iter(
                [
                    FakeMessage(
                        sport="swimming",
                        sub_sport="lap_swimming",
                        start_time=datetime(2026, 5, 20, 11, 30, 0),
                        avg_heart_rate=None,
                        max_heart_rate=None,
                        total_distance=1500.0,
                        total_timer_time=1800.0,
                        total_calories=320,
                        total_ascent=0,
                        max_altitude=12.0,
                    )
                ]
            )
        if kind == "sport":
            return iter([FakeMessage(name="游泳", sport="swimming", sub_sport="lap_swimming")])
        if kind == "activity":
            return iter([FakeMessage(local_timestamp=datetime(2026, 5, 20, 19, 30, 0))])
        if kind == "record":
            return iter(
                [
                    FakeMessage(timestamp=datetime(2026, 5, 20, 11, 30, 0), position_lat=30.0, position_long=104.0, altitude=10.0, heart_rate=110),
                    FakeMessage(timestamp=datetime(2026, 5, 20, 11, 45, 0), position_lat=30.0005, position_long=104.0005, altitude=10.0, heart_rate=130),
                ]
            )
        return iter([])


class TestFitParser(unittest.TestCase):
    def test_filename_like_gpx_name_is_not_preserved_as_sport_type(self):
        self.assertIsNone(track_backend.normalize_sport_type("COURSE_443798.gpx"))

    def test_structured_climbing_sports_do_not_collapse_to_hiking(self):
        cases = {
            "stair_climbing": "stair_climbing",
            "floor_climbing": "stair_climbing",
            "爬楼": "stair_climbing",
            "indoor_climbing": "indoor_climbing",
            "rock_climbing": "rock_climbing",
            "elliptical": "elliptical",
            "gravel_cycling": "gravel_cycling",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(track_backend.normalize_sport_type(raw), expected)

    def test_fit_activity_type_prefers_structured_sub_sport(self):
        cases = [
            ("fitness_equipment", "stair_climbing", "stair_climbing"),
            ("floor_climbing", "unknown", "stair_climbing"),
            ("fitness_equipment", "indoor_climbing", "indoor_climbing"),
            ("rock_climbing", "unknown", "rock_climbing"),
            ("cycling", "gravel_cycling", "gravel_cycling"),
            ("fitness_equipment", "elliptical", "elliptical"),
        ]
        for sport, sub_sport, expected in cases:
            with self.subTest(sport=sport, sub_sport=sub_sport):
                self.assertEqual(fit_engine.FITCoreEngine._resolve_activity_type(sport, sub_sport), expected)

    def test_gpx_activity_type_metadata_is_preserved_for_mountaineering(self):
        gpx_text = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="unit-test">
  <trk>
    <name>mountaineering</name>
    <type>mountaineering</type>
    <trkseg>
      <trkpt lat="30.1" lon="103.1"><ele>1500</ele><time>2026-05-20T00:00:00Z</time></trkpt>
      <trkpt lat="30.101" lon="103.101"><ele>1680</ele><time>2026-05-20T00:20:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", encoding="utf-8", delete=False) as temp_gpx:
            temp_gpx.write(gpx_text)
            temp_path = temp_gpx.name
        try:
            data = track_backend.parse_track_file(temp_path)
            self.assertEqual(data.get("sport_type"), "mountaineering")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_point_inference_supports_driving_and_mountaineering(self):
        driving_points = [
            {"lat": 30.0, "lon": 104.0, "alt": 500, "time": "2026-05-20T00:00:00Z"},
            {"lat": 30.05, "lon": 104.0, "alt": 505, "time": "2026-05-20T00:05:00Z"},
        ]
        mountaineering_points = [
            {"lat": 30.0, "lon": 104.0, "alt": 1200, "time": "2026-05-20T00:00:00Z"},
            {"lat": 30.001, "lon": 104.001, "alt": 1480, "time": "2026-05-20T00:30:00Z"},
        ]
        self.assertEqual(track_backend.infer_sport_type_from_points(driving_points), "driving")
        self.assertEqual(track_backend.infer_sport_type_from_points(mountaineering_points), "mountaineering")

    def test_llm_prompt_uses_actual_sport_type_labels(self):
        driving_block = llm_backend.build_base_system_block(
            sport_type="driving",
            provider="openai",
            track_filename="drive.gpx",
            points=[{"lat": 30.0, "lon": 104.0, "time": "2026-05-20T00:00:00Z"}],
            placemarks=[],
        )
        self.assertIn("用户活动类型：【驾车】", driving_block)

    def test_running_fit_metadata(self):
        path = _first_existing(
            [
                "/Users/fanglei/应用开发/AI track/local_tracks/594207408_ACTIVITY.fit",
                "/Users/fanglei/Downloads/Garmin fit/594207408_ACTIVITY.fit",
            ]
        )
        if not path:
            self.skipTest("未找到跑步 FIT 样本")

        data = track_backend.parse_track_file(path)
        self.assertEqual(data.get("sport_type"), "running")
        self.assertEqual(data.get("title"), "跑步")
        self.assertEqual(data.get("avg_hr"), 135)
        self.assertEqual(data.get("start_time_utc"), "2026-05-13T00:07:24Z")
        self.assertEqual(data.get("start_time"), "2026-05-13T08:07:24+08:00")
        core = fit_engine.FITCoreEngine.parse_fit_file(path)
        self.assertIn("basic_info", core)
        self.assertIn("track_data", core)
        self.assertEqual(core["basic_info"].get("title"), "跑步")
        self.assertIsInstance(core["track_data"], list)

    def test_cycling_fit_metadata(self):
        path = _first_existing(
            [
                "/Users/fanglei/Downloads/Garmin fit/594356100_ACTIVITY.fit",
                "/Users/fanglei/sync-watch/data/garmin_export/594356100.fit",
            ]
        )
        if not path:
            self.skipTest("未找到骑行 FIT 样本")

        data = track_backend.parse_track_file(path)
        self.assertEqual(data.get("sport_type"), "cycling")
        self.assertEqual(data.get("title"), "骑行")
        self.assertEqual(data.get("avg_hr"), 80)
        self.assertEqual(data.get("start_time_utc"), "2026-05-13T11:07:02Z")
        self.assertEqual(data.get("start_time"), "2026-05-13T19:07:02+08:00")

    def test_fit_track_data_preserves_record_distance_meters(self):
        class DistanceFitFile:
            def get_messages(self, kind):
                if kind != "record":
                    return iter([])
                return iter(
                    [
                        FakeMessage(
                            timestamp=datetime(2026, 5, 20, 0, 0, 0),
                            position_lat=30.0,
                            position_long=104.0,
                            altitude=10.0,
                            distance=0.0,
                        ),
                        FakeMessage(
                            timestamp=datetime(2026, 5, 20, 0, 1, 0),
                            position_lat=31.0,
                            position_long=105.0,
                            altitude=12.0,
                            distance=1234.5,
                        ),
                    ]
                )

        track_data = fit_engine.FITCoreEngine._read_track_data(DistanceFitFile())

        self.assertEqual(track_data[0]["distance"], 0.0)
        self.assertEqual(track_data[1]["distance"], 1234.5)
        for key in ("lat", "lon", "alt", "time", "hr", "pace", "cadence", "power"):
            self.assertIn(key, track_data[0])

    def test_hiking_fit_prefers_human_filename_title(self):
        path = _first_existing(
            [
                "/Users/fanglei/应用开发/AI track/local_tracks/门头沟徒步.fit",
                "/Users/fanglei/Desktop/门头沟徒步.fit",
            ]
        )
        if not path:
            self.skipTest("未找到徒步 FIT 样本")

        data = track_backend.parse_track_file(path)
        self.assertEqual(data.get("sport_type"), "hiking")
        self.assertEqual(data.get("title"), "门头沟徒步")
        self.assertEqual(data.get("title_source"), "filename")
        self.assertEqual(data.get("avg_hr"), 114)
        self.assertEqual(data.get("start_time"), "2026-04-11T09:11:19+08:00")

    def test_swimming_fit_metadata_with_mock(self):
        old_deps = fit_engine._FITPARSE_DEPS
        fit_engine._FITPARSE_DEPS = (FakeFitFile, Exception)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_fit = Path(temp_dir) / "泳.fit"
                _write_minimal_fit_header(str(temp_fit))
                data = track_backend.parse_track_file(temp_fit)
        finally:
            fit_engine._FITPARSE_DEPS = old_deps
        self.assertEqual(data.get("sport_type"), "swimming")
        self.assertEqual(data.get("title"), "游泳")
        self.assertEqual(data.get("title_source"), "sport_name")
        self.assertEqual(data.get("avg_hr"), 120)
        self.assertEqual(data.get("max_hr"), 130)
        self.assertEqual(data.get("start_time_utc"), "2026-05-20T11:30:00Z")
        self.assertEqual(data.get("start_time"), "2026-05-20T19:30:00+08:00")

    def test_malformed_fit_raises_clear_error(self):
        class FakeFitParseError(Exception):
            pass

        with tempfile.NamedTemporaryFile(suffix=".fit") as temp_fit:
            _write_minimal_fit_header(temp_fit.name)

            def _raise_fit_error(*_args, **_kwargs):
                raise FakeFitParseError("header corrupt")

            old_deps = fit_engine._FITPARSE_DEPS
            fit_engine._FITPARSE_DEPS = (_raise_fit_error, FakeFitParseError)
            try:
                with self.assertRaisesRegex(ValueError, "FIT 文件损坏或已截断"):
                    track_backend.parse_track_file(temp_fit.name)
            finally:
                fit_engine._FITPARSE_DEPS = old_deps

        self.assertTrue(fit_engine.FIT_PARSE_LOG_PATH.exists())
        log_text = fit_engine.FIT_PARSE_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("FIT 文件初始化失败", log_text)

    def test_metrics_resolver_supports_flat_record_curves(self):
        resolver = MetricsResolver()
        pack = resolver._build_analysis_pack(
            [],
            [
                {"heart_rate": 120, "speed": 2.5, "altitude": 10.2, "distance": 100.0, "lat": 30.1, "lon": 104.1},
                {"hr": 130, "speed": 3.0, "alt": 12.7, "dist": 180.0, "position_lat": 30.2, "position_long": 104.2},
            ],
        )

        self.assertEqual(pack["hr_curve"], [120.0, 130.0])
        self.assertEqual(pack["speed_curve"], [2.5, 3.0])
        self.assertEqual(pack["altitude_curve"], [10.2, 12.7])
        self.assertEqual(pack["distance_curve"], [100.0, 180.0])
        self.assertEqual(pack["lat_curve"], [30.1, 30.2])
        self.assertEqual(pack["lon_curve"], [104.1, 104.2])

    def test_metrics_resolver_supports_nested_record_curves_and_ai_context(self):
        resolver = MetricsResolver()
        records = [
            {"raw": {"heart_rate": 120, "speed": 2.5, "altitude": 10.2, "distance": 100.0}, "geo": {"lat": 30.1, "lon": 104.1}},
            {"raw": {"heart_rate": 130, "speed": 3.0, "altitude": 12.7, "distance": 180.0}, "geo": {"lat": 30.2, "lon": 104.2}},
        ]
        pack = resolver._build_analysis_pack([], records)
        context = resolver._build_ai_context({"avg_hr": 125, "max_hr": 150, "avg_pace": 360, "elevation_gain_m": 20, "distance_km": 1.0}, {}, records)

        self.assertEqual(pack["hr_curve"], [120.0, 130.0])
        self.assertEqual(pack["speed_curve"], [2.5, 3.0])
        self.assertEqual(pack["lat_curve"], [30.1, 30.2])
        self.assertEqual(pack["lon_curve"], [104.1, 104.2])
        self.assertIsNotNone(context["structured_metrics"]["pace_variance"])


if __name__ == "__main__":
    unittest.main()
