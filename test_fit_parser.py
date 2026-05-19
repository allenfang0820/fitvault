import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest import mock

import fit_engine
import llm_backend
import track_backend


def _first_existing(paths: list[str]) -> Optional[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            return path
    return None


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
        mountaineering_prompt = llm_backend.build_report_user_prompt_personalized("mountaineering", "openai")
        cycling_prompt = llm_backend.build_report_user_prompt_personalized("cycling", "openai")

        self.assertIn("用户活动类型：【驾车】", driving_block)
        self.assertIn("登山预测报告", mountaineering_prompt)
        self.assertIn("骑行预测报告", cycling_prompt)
        self.assertNotIn("徒步预测报告", cycling_prompt)

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

    @mock.patch("fit_engine.FitFile", FakeFitFile)
    def test_swimming_fit_metadata_with_mock(self):
        with tempfile.NamedTemporaryFile(suffix=".fit") as temp_fit:
            data = track_backend.parse_track_file(temp_fit.name)
        self.assertEqual(data.get("sport_type"), "swimming")
        self.assertEqual(data.get("title"), "游泳")
        self.assertEqual(data.get("title_source"), "sport_name")
        self.assertEqual(data.get("avg_hr"), 120)
        self.assertEqual(data.get("max_hr"), 130)
        self.assertEqual(data.get("start_time_utc"), "2026-05-20T11:30:00Z")
        self.assertEqual(data.get("start_time"), "2026-05-20T19:30:00+08:00")

    def test_malformed_fit_raises_clear_error(self):
        with tempfile.NamedTemporaryFile(suffix=".fit") as temp_fit:
            with mock.patch("fit_engine.FitFile", side_effect=fit_engine.FitParseError("header corrupt")):
                with self.assertRaisesRegex(ValueError, "FIT 文件损坏或已截断"):
                    track_backend.parse_track_file(temp_fit.name)

        self.assertTrue(fit_engine.FIT_PARSE_LOG_PATH.exists())
        log_text = fit_engine.FIT_PARSE_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("FIT 文件初始化失败", log_text)


if __name__ == "__main__":
    unittest.main()
