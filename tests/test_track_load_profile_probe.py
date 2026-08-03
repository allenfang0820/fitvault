import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML = PROJECT_ROOT / "track.html"
PROFILE_SCRIPT = PROJECT_ROOT / "scripts" / "profile_track_load.py"


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace_start = source.index("{", start + len(signature))
    depth = 1
    index = brace_start + 1
    while depth:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    return source[start:index]


class TestTrackLoadProfileProbe(unittest.TestCase):
    def test_probe_is_read_only_and_uses_current_frontend_functions(self):
        source = PROFILE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("api.load_activity_track(activity_id)", source)
        self.assertIn('function haversine(', source)
        self.assertIn('function _buildPeakMarkerMetricPoints(', source)
        self.assertIn('function _peakMarkerChordDistanceSquared(', source)
        self.assertIn('function _detectPeakMarkers(', source)
        self.assertIn('function _buildStatsFromCanonical(', source)
        self.assertNotIn("commit", source.lower())
        self.assertNotIn("write_text(", source)

    def test_hot_path_contract_avoids_per_point_logs_and_redundant_distance(self):
        html = TRACK_HTML.read_text(encoding="utf-8")
        haversine_start = html.index("function haversine(")
        haversine_end = html.index("// LEGACY UI CALCULATION", haversine_start)
        self.assertNotIn("console.warn", html[haversine_start:haversine_end])
        canonical_start = html.index("function _buildStatsFromCanonical(")
        canonical_end = html.index("function _previewStatsOnly(", canonical_start)
        canonical_body = html[canonical_start:canonical_end]
        self.assertIn("Number.isFinite(distKmValue)", canonical_body)
        self.assertIn("if (pointDist == null)", canonical_body)
        self.assertIn("fallbackDist += haversine", canonical_body)

    def test_peak_detection_uses_precomputed_spherical_chords(self):
        html = TRACK_HTML.read_text(encoding="utf-8")
        self.assertIn("function _buildPeakMarkerMetricPoints(", html)
        self.assertIn("function _peakMarkerChordThresholdSquared(", html)
        self.assertIn("function _peakMarkerChordDistanceSquared(", html)
        peak_start = html.index("function _detectPeakMarkers(")
        peak_end = html.index("// ═", peak_start)
        peak_body = html[peak_start:peak_end]
        self.assertNotIn("haversine(", peak_body)
        self.assertIn("_peakMarkerChordThresholdSquared(250)", peak_body)
        self.assertIn("_peakMarkerChordThresholdSquared(300)", peak_body)
        self.assertIn("(points[i].alt - localMin) >= 12", peak_body)

    def test_probe_still_captures_render_and_sync_markers(self):
        html = TRACK_HTML.read_text(encoding="utf-8")
        self.assertIn("appState.fullPositions.push(Cesium.Cartesian3.fromDegrees", html)
        self.assertNotIn("duration: 2.5", html)
        self.assertIn("duration: 0.8", html)
        self.assertIn("scheduleTrackPostPaintWork(renderRevision", html)
        self.assertNotIn("points: appState.points", html)
        self.assertIn("payload.points = appState.points", html)

    def test_post_paint_queue_drops_stale_route_work(self):
        html = TRACK_HTML.read_text(encoding="utf-8")
        functions = "\n".join((
            _extract_function(html, "function isTrackRenderRevisionCurrent("),
            _extract_function(html, "function scheduleTrackPostPaintWork("),
        ))
        script = f"""
const raf = [];
const idle = [];
const executed = [];
const window = {{
  requestAnimationFrame: (callback) => raf.push(callback),
  requestIdleCallback: (callback) => idle.push(callback)
}};
const setTimeout = (callback) => callback();
let trackRenderRevision = 2;
{functions}
scheduleTrackPostPaintWork(1, [() => executed.push('stale')]);
while (raf.length) raf.shift()();
while (idle.length) idle.shift()();
scheduleTrackPostPaintWork(2, [() => executed.push('chart'), () => executed.push('sync')]);
while (raf.length) raf.shift()();
while (idle.length) idle.shift()();
process.stdout.write(JSON.stringify(executed));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout), ["chart", "sync"])

    def test_first_screen_keeps_critical_work_and_defers_secondary_work(self):
        html = TRACK_HTML.read_text(encoding="utf-8")
        apply_body = _extract_function(html, "function applyDataAndRender(")
        schedule_index = apply_body.index("scheduleTrackPostPaintWork(renderRevision")
        critical_region = apply_body[:schedule_index]
        deferred_region = apply_body[schedule_index:]

        for token in ("updateScene();", "drawProfileChart();", "renderCpList();", "startInitialTrackCameraFlight("):
            self.assertIn(token, critical_region)
        for token in (
            "renderProfileAnalysisChart(appState.activityMetrics)",
            "syncCurrentTrackContextForActivityAdvice('track_loaded')",
            "renderTrackReport({ silent: true })",
            "resolvePreviewRegionInBackground(appState.activityMetrics || appState.previewRegionMetrics)",
            "renderPerformanceRadar()",
        ):
            self.assertIn(token, deferred_region)

        claim_body = _extract_function(html, "function claimCameraOwnership(")
        self.assertIn("flyto: 5", html)
        self.assertIn("activeCameraController === 'flyto'", claim_body)
        self.assertIn("cancelInitialTrackCameraFlight()", claim_body)


if __name__ == "__main__":
    unittest.main()
