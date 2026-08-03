#!/usr/bin/env python3
"""Read-only baseline probe for dense track loading.

The probe deliberately executes the current pure JavaScript functions from
track.html instead of maintaining a second copy of their algorithms. It does
not write the database or mutate production source files.
"""

from __future__ import annotations

import argparse
import json
import sys
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML = PROJECT_ROOT / "track.html"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


def _extract_function(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise ValueError(f"missing function signature: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise ValueError(f"missing function body: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    if depth:
        raise ValueError(f"unclosed function body: {signature}")
    return source[start:index]


def _run_js_probe(html: str, points: list[dict], metrics: dict) -> dict:
    peak_constant = "const PEAK_MARKER_EARTH_RADIUS_M = 6371000;"
    functions = [
        _extract_function(html, "function haversine("),
    ]
    if peak_constant in html:
        functions.extend([
            peak_constant,
            _extract_function(html, "function _buildPeakMarkerMetricPoints("),
            _extract_function(html, "function _peakMarkerChordThresholdSquared("),
            _extract_function(html, "function _peakMarkerChordDistanceSquared("),
        ])
    functions.extend([
        _extract_function(html, "function _detectPeakMarkers("),
        _extract_function(html, "function _buildStatsFromCanonical("),
    ])
    payload = json.dumps({"points": points, "metrics": metrics}, ensure_ascii=False)
    js = r'''
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = %s;
let appState = {};
const functions = new Function(
  "var appState = {};\n" + source.join("\n") +
  "\nreturn {haversine, _detectPeakMarkers, _buildStatsFromCanonical};"
)();
let warnCount = 0;
const originalWarn = console.warn;
console.warn = function() { warnCount += 1; };
const points = input.points;
const stringifyStart = performance.now();
const serialized = JSON.stringify(points);
const stringifyMs = performance.now() - stringifyStart;
const statsStart = performance.now();
const stats = functions._buildStatsFromCanonical(points, input.metrics || {});
const statsMs = performance.now() - statsStart;
console.warn = originalWarn;
process.stdout.write(JSON.stringify({
  pointCount: points.length,
  serializedBytes: Buffer.byteLength(serialized, "utf8"),
  stringifyMs,
  statsMs,
  warnCount,
  kmMarkerCount: (stats.kmMarkers || []).length,
  peakMarkerCount: (stats.peakMarkers || []).length,
  peakMarkers: (stats.peakMarkers || []).map(function(marker) {
    return {
      lon: marker.lon,
      lat: marker.lat,
      alt: marker.alt,
      isHighest: !!marker.isHighest
    };
  })
}));
''' % json.dumps(functions)
    completed = subprocess.run(
        ["node", "-e", js],
        cwd=PROJECT_ROOT,
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def profile_activity(api: main.Api, activity_id: int, html: str) -> dict:
    started = time.perf_counter()
    response = api.load_activity_track(activity_id)
    load_ms = (time.perf_counter() - started) * 1000
    if not response.get("ok"):
        raise RuntimeError(f"activity {activity_id}: {response}")

    started = time.perf_counter()
    response_json = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    encode_ms = (time.perf_counter() - started) * 1000
    points = response["data"]["points"]
    metrics = response.get("activity") or {}
    js_result = _run_js_probe(html, points, metrics)
    sync_source = _extract_function(html, "function syncCurrentTrackContextForActivityAdvice(")
    route_facts = {
        "activity_id": activity_id,
        "distance_km": metrics.get("dist_km"),
        "elevation_gain_m": metrics.get("gain_m"),
        "max_alt_m": metrics.get("max_alt_m"),
        "source": "overview_canonical_metrics",
    }
    context_payload = {
        "placemarks": response["data"].get("placemarks") or [],
        "filename": response.get("filename") or "轨迹",
        "weather": response["data"].get("weather"),
        "activityId": activity_id,
        "activityAdviceRouteFacts": route_facts,
    }
    lightweight_context_bytes = len(json.dumps(context_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    full_context_payload = dict(context_payload)
    full_context_payload["points"] = points
    full_context_bytes = len(json.dumps(full_context_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return {
        "activity_id": activity_id,
        "filename": response.get("filename"),
        "point_count": len(points),
        "database_response_bytes": len(response_json.encode("utf-8")),
        "backend_load_ms": round(load_ms, 3),
        "python_json_encode_ms": round(encode_ms, 3),
        "frontend_probe": {
            key: round(value, 3) if isinstance(value, float) else value
            for key, value in js_result.items()
        },
        "context_payload": {
            "full_points_bytes": full_context_bytes,
            "canonical_lightweight_bytes": lightweight_context_bytes,
            "bytes_saved": full_context_bytes - lightweight_context_bytes,
            "reduction_pct": round((full_context_bytes - lightweight_context_bytes) * 100 / full_context_bytes, 3),
        },
        "static_markers": {
            "has_fixed_2_5s_fly_to": "duration: 2.5" in html,
            "has_short_interruptible_initial_flight": (
                "function startInitialTrackCameraFlight(" in html
                and "duration: 0.8" in html
                and "cancelInitialTrackCameraFlight();" in html
            ),
            "has_revision_guarded_post_paint_work": (
                "function scheduleTrackPostPaintWork(" in html
                and "isTrackRenderRevisionCurrent(renderRevision)" in html
                and "scheduleTrackPostPaintWork(renderRevision" in html
            ),
            "has_full_cartesian_positions": "appState.fullPositions.push(Cesium.Cartesian3.fromDegrees" in html,
            "has_unconditional_context_points": "points: appState.points" in sync_source,
            "has_conditional_temporary_context_points": "payload.points = appState.points" in sync_source,
        },
    }


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activity-id", type=int, action="append", required=True)
    parser.add_argument("--track-html", type=Path, default=TRACK_HTML)
    args = parser.parse_args()
    track_html = args.track_html.expanduser().resolve()
    html = track_html.read_text(encoding="utf-8")
    api = main.Api()
    results = [profile_activity(api, activity_id, html) for activity_id in args.activity_id]
    print(json.dumps({"track_html": str(track_html), "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
