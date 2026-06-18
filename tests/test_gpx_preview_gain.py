from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import profile_backend
import track_backend
import main


def _dense_climb_points(count: int = 101, step_gain_m: float = 0.2) -> list[dict]:
    return [
        {
            "lat": 30.0,
            "lon": 104.0 + i * 0.00001,
            "alt": 1000.0 + i * step_gain_m,
            "time": f"2026-06-10T00:{i // 60:02d}:{i % 60:02d}Z",
            "hr": None,
        }
        for i in range(count)
    ]


def _gpx_text(points: list[dict], track_type: str | None = None) -> str:
    type_tag = f"    <type>{track_type}</type>\n" if track_type else ""
    trkpts = "\n".join(
        (
            f'      <trkpt lat="{point["lat"]}" lon="{point["lon"]}">'
            f'<ele>{point["alt"]}</ele><time>{point["time"]}</time></trkpt>'
        )
        for point in points
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="unit-test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>dense climb</name>
{type_tag}    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>
"""


def _kml_text(points: list[dict]) -> str:
    coords = " ".join(f'{point["lon"]},{point["lat"]},{point["alt"]}' for point in points)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>补给点 A</name>
      <Point><coordinates>104.123456,30.123456,888</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>主路线</name>
      <LineString><coordinates>{coords}</coordinates></LineString>
    </Placemark>
  </Document>
</kml>
"""


def _kml_gx_track_text(points: list[dict]) -> str:
    coords = "\n".join(f'        <gx:coord>{point["lon"]} {point["lat"]} {point["alt"]}</gx:coord>' for point in points)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <Placemark>
      <name>gx route</name>
      <gx:Track>
{coords}
      </gx:Track>
    </Placemark>
  </Document>
</kml>
"""


class TestGpxPreviewGain(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._region_cache_backup = dict(profile_backend._REGION_CACHE)
        profile_backend._REGION_CACHE.clear()

    def tearDown(self):
        profile_backend._REGION_CACHE.clear()
        profile_backend._REGION_CACHE.update(self._region_cache_backup)
        super().tearDown()

    def test_dense_gpx_fallback_gain_accumulates_small_steps(self):
        points = _dense_climb_points()

        gain_m = profile_backend._compute_gpx_fallback_gain_m(points)

        self.assertEqual(gain_m, 20)

    def test_parse_gpx_for_preview_uses_gpx_gain_without_persistence(self):
        points = _dense_climb_points()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dense_climb.gpx"
            path.write_text(_gpx_text(points), encoding="utf-8")

            with patch.object(profile_backend, "resolve_preview_region", return_value={
                "region": "",
                "region_city": None,
                "region_country": None,
                "region_display": "",
                "region_status": "pending",
                "region_error": None,
            }):
                result = profile_backend.parse_gpx_for_preview(str(path))

        self.assertTrue(result["ok"])
        activity = result["activity"]
        self.assertIsNone(activity["id"])
        self.assertEqual(activity["gain_m"], 20.0)
        self.assertIsNotNone(activity["mtdi_score"])
        self.assertIsNotNone(activity["mtdi_level"])

    def test_parse_gpx_for_preview_reclassifies_generic_running_hike(self):
        points = _dense_climb_points(count=101, step_gain_m=20.0)
        start = datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)
        for i, point in enumerate(points):
            point["alt"] = 3200.0 + i * 20.0
            point["time"] = (start + timedelta(seconds=i * 180)).isoformat().replace("+00:00", "Z")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "high_altitude_running_tag.gpx"
            path.write_text(_gpx_text(points, track_type="running"), encoding="utf-8")

            with patch.object(profile_backend, "resolve_preview_region", return_value={
                "region": "",
                "region_city": None,
                "region_country": None,
                "region_display": "",
                "region_status": "pending",
                "region_error": None,
            }):
                result = profile_backend.parse_gpx_for_preview(str(path))

        self.assertTrue(result["ok"])
        activity = result["activity"]
        self.assertEqual(activity["sport_type"], "hiking")
        self.assertGreaterEqual(activity["mtdi_level"], 4)

    def test_parse_gpx_for_preview_attaches_region_fields_without_activity_id(self):
        points = _dense_climb_points()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "chengdu_preview.gpx"
            path.write_text(_gpx_text(points), encoding="utf-8")

            with patch.object(profile_backend, "resolve_preview_region", return_value={
                "region": "成都市/中国",
                "region_city": "成都市",
                "region_country": "中国",
                "region_display": "成都市/中国",
                "region_status": "success",
                "region_error": None,
            }):
                result = profile_backend.parse_gpx_for_preview(str(path))

        self.assertTrue(result["ok"])
        activity = result["activity"]
        self.assertIsNone(activity["id"])
        self.assertEqual(activity["region"], "成都市/中国")
        self.assertEqual(activity["region_city"], "成都市")
        self.assertEqual(activity["region_country"], "中国")
        self.assertEqual(activity["region_display"], "成都市/中国")
        self.assertEqual(activity["region_status"], "success")

    def test_parse_route_for_preview_can_defer_region_resolution(self):
        points = _dense_climb_points()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "defer_region.gpx"
            path.write_text(_gpx_text(points), encoding="utf-8")

            with patch.object(profile_backend, "resolve_preview_region") as resolver:
                result = profile_backend.parse_route_for_preview(str(path), resolve_region=False)

        resolver.assert_not_called()
        self.assertTrue(result["ok"])
        activity = result["activity"]
        self.assertIsNone(activity["id"])
        self.assertEqual(activity["region_status"], "pending")
        self.assertEqual(activity["region_display"], "")
        self.assertIsNotNone(activity["start_lat"])
        self.assertIsNotNone(activity["start_lon"])

    def test_parse_route_for_preview_supports_kml_without_persistence(self):
        points = _dense_climb_points()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "kml_preview.sqlite"
            path = Path(tmpdir) / "dense_climb.kml"
            path.write_text(_kml_text(points), encoding="utf-8")

            with patch.object(profile_backend, "DB_PATH", db_path):
                conn = profile_backend._conn()
                try:
                    before_count = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()["c"]
                finally:
                    conn.close()

                with patch.object(profile_backend, "resolve_preview_region", return_value={
                    "region": "成都市/中国",
                    "region_city": "成都市",
                    "region_country": "中国",
                    "region_display": "成都市/中国",
                    "region_status": "success",
                    "region_error": None,
                }):
                    result = profile_backend.parse_route_for_preview(str(path))

                conn = profile_backend._conn()
                try:
                    after_count = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()["c"]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(before_count, after_count)
        self.assertEqual(result["filename"], "dense_climb.kml")
        self.assertEqual(len(result["data"]["points"]), len(points))
        self.assertEqual(len(result["data"]["placemarks"]), 1)
        self.assertEqual(result["data"]["placemarks"][0]["name"], "补给点 A")
        activity = result["activity"]
        self.assertIsNone(activity["id"])
        self.assertEqual(activity["region_display"], "成都市/中国")
        self.assertIsNotNone(activity["mtdi_score"])

    def test_parse_gpx_for_preview_wrapper_accepts_kml_for_compatibility(self):
        points = _dense_climb_points(count=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "compat_route.kml"
            path.write_text(_kml_text(points), encoding="utf-8")

            with patch.object(profile_backend, "resolve_preview_region", return_value={
                "region": "",
                "region_city": None,
                "region_country": None,
                "region_display": "",
                "region_status": "pending",
                "region_error": None,
            }):
                result = profile_backend.parse_gpx_for_preview(str(path))

        self.assertTrue(result["ok"])
        self.assertIsNone(result["activity"]["id"])
        self.assertEqual(len(result["data"]["points"]), 3)

    def test_parse_kml_file_extracts_point_placemarks_without_mixing_track(self):
        points = _dense_climb_points(count=4)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "with_cp.kml"
            path.write_text(_kml_text(points), encoding="utf-8")

            data = track_backend.parse_track_file(str(path))

        self.assertEqual(len(data["points"]), 4)
        self.assertEqual(len(data["placemarks"]), 1)
        self.assertEqual(data["placemarks"][0]["name"], "补给点 A")
        self.assertAlmostEqual(data["placemarks"][0]["lat"], 30.123456)
        self.assertAlmostEqual(data["placemarks"][0]["lon"], 104.123456)
        self.assertEqual(data["placemarks"][0]["alt"], 888.0)

    def test_parse_kml_file_supports_gx_track_multiple_coords(self):
        points = _dense_climb_points(count=5)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "gx_track.kml"
            path.write_text(_kml_gx_track_text(points), encoding="utf-8")

            data = track_backend.parse_track_file(str(path))

        self.assertEqual(len(data["points"]), 5)
        self.assertAlmostEqual(data["points"][0]["lat"], points[0]["lat"])
        self.assertAlmostEqual(data["points"][-1]["lon"], points[-1]["lon"])

    def test_resolve_preview_region_cache_miss_writes_only_geocode_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "preview_region.sqlite"
            with patch.object(profile_backend, "DB_PATH", db_path):
                conn = profile_backend._conn()
                try:
                    before_count = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()["c"]
                finally:
                    conn.close()

                with patch.object(profile_backend, "reverse_geocode", return_value={"city": "成都市", "country": "中国"}) as geocode:
                    result = profile_backend.resolve_preview_region(30.1234, 104.5678)

                conn = profile_backend._conn()
                try:
                    after_count = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()["c"]
                    cache_row = conn.execute(
                        "SELECT city, country, display, status FROM geocode_cache WHERE cache_key = ?",
                        ("30.12,104.57",),
                    ).fetchone()
                finally:
                    conn.close()

        geocode.assert_called_once_with(30.12, 104.57)
        self.assertEqual(before_count, after_count)
        self.assertEqual(result["region_status"], "success")
        self.assertEqual(result["region_display"], "成都市/中国")
        self.assertIsNotNone(cache_row)
        self.assertEqual(cache_row["status"], "success")
        self.assertEqual(cache_row["display"], "成都市/中国")

    def test_region_extraction_falls_back_to_state(self):
        city, country, display = profile_backend._extract_city_country({
            "state": "Bagmati Province",
            "country": "Nepal",
        })

        self.assertEqual(city, "Bagmati Province")
        self.assertEqual(country, "Nepal")
        self.assertEqual(display, "Bagmati Province/Nepal")

    def test_region_extraction_falls_back_to_natural_name(self):
        city, country, display = profile_backend._extract_city_country({
            "mountain": "珠穆朗玛峰国家自然保护区",
            "country": "中国",
        })

        self.assertEqual(city, "珠穆朗玛峰国家自然保护区")
        self.assertEqual(country, "中国")
        self.assertEqual(display, "珠穆朗玛峰国家自然保护区/中国")

    def test_region_extraction_falls_back_to_display_name(self):
        city, country, display = profile_backend._extract_city_country({
            "display_name": "Lobuche, Khumbu Pasanglhamu, Solukhumbu, Koshi Province, Nepal",
            "country": "Nepal",
        })

        self.assertEqual(city, "Lobuche")
        self.assertEqual(country, "Nepal")
        self.assertEqual(display, "Lobuche/Nepal")

    def test_api_resolve_preview_region_returns_region_payload(self):
        api = main.Api.__new__(main.Api)
        with patch.object(profile_backend, "resolve_preview_region", return_value={
            "region": "聂拉木县/中国",
            "region_city": "聂拉木县",
            "region_country": "中国",
            "region_display": "聂拉木县/中国",
            "region_status": "success",
            "region_error": None,
        }):
            result = api.resolve_preview_region(28.75, 85.6)

        self.assertTrue(result["ok"])
        self.assertEqual(result["region"]["region_display"], "聂拉木县/中国")

    def test_resolve_preview_region_failure_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "preview_region_failure.sqlite"
            with patch.object(profile_backend, "DB_PATH", db_path):
                with patch.object(profile_backend, "reverse_geocode", side_effect=RuntimeError("boom")):
                    result = profile_backend.resolve_preview_region(31.1234, 105.5678)

                conn = profile_backend._conn()
                try:
                    cache_row = conn.execute(
                        "SELECT status, error FROM geocode_cache WHERE cache_key = ?",
                        ("31.12,105.57",),
                    ).fetchone()
                finally:
                    conn.close()

        self.assertEqual(result["region_status"], "failed")
        self.assertIn("boom", result["region_error"])
        self.assertIsNotNone(cache_row)
        self.assertEqual(cache_row["status"], "failed")
        self.assertIn("boom", cache_row["error"])

    def test_resolve_preview_region_cache_failure_keeps_successful_geocode(self):
        with patch.object(profile_backend, "_conn", side_effect=RuntimeError("db unavailable")):
            with patch.object(profile_backend, "reverse_geocode", return_value={"city": "成都市", "country": "中国"}):
                result = profile_backend.resolve_preview_region(32.1234, 106.5678)

        self.assertEqual(result["region_status"], "success")
        self.assertEqual(result["region_display"], "成都市/中国")
        self.assertIsNone(result["region_error"])

    def test_resolve_preview_region_without_coordinates_does_not_geocode(self):
        with patch.object(profile_backend, "reverse_geocode") as geocode:
            result = profile_backend.resolve_preview_region(None, None)

        geocode.assert_not_called()
        self.assertEqual(result["region_status"], "none")
        self.assertEqual(result["region_display"], "室内运动")


if __name__ == "__main__":
    unittest.main()
