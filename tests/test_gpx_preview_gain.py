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


class TestGpxPreviewGain(unittest.TestCase):
    def test_dense_gpx_fallback_gain_accumulates_small_steps(self):
        points = _dense_climb_points()

        gain_m = profile_backend._compute_gpx_fallback_gain_m(points)

        self.assertEqual(gain_m, 20)

    def test_parse_gpx_for_preview_uses_gpx_gain_without_persistence(self):
        points = _dense_climb_points()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dense_climb.gpx"
            path.write_text(_gpx_text(points), encoding="utf-8")

            with patch.object(profile_backend, "resolve_activity_region", return_value=""):
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

            with patch.object(profile_backend, "resolve_activity_region", return_value=""):
                result = profile_backend.parse_gpx_for_preview(str(path))

        self.assertTrue(result["ok"])
        activity = result["activity"]
        self.assertEqual(activity["sport_type"], "hiking")
        self.assertGreaterEqual(activity["mtdi_level"], 4)


if __name__ == "__main__":
    unittest.main()
