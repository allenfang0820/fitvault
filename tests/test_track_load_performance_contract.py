import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML = PROJECT_ROOT / "track.html"


def extract_function(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function: {signature}")
    brace = source.find("{", start + len(signature))
    depth = 1
    index = brace + 1
    while depth:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    return source[start:index]


class TestTrackLoadPerformanceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TRACK_HTML.read_text(encoding="utf-8")

    def test_canonical_bridge_has_one_measured_load_without_reserialization(self):
        body = extract_function(self.html, "async function loadCanonicalActivityTrackWithPerformance(")
        self.assertEqual(body.count("window.pywebview.api.load_activity_track(activityId)"), 1)
        self.assertIn("bridgeAndDecodeMs", body)
        self.assertIn("response.data.points.length", body)
        self.assertNotIn("JSON.stringify", body)
        self.assertEqual(self.html.count("window.pywebview.api.load_activity_track("), 1)

    def test_track_snapshot_covers_critical_and_deferred_stages(self):
        self.assertIn("lastTrackLoadPerformance: null", self.html)
        self.assertIn("function getLastTrackLoadPerformance()", self.html)
        apply_body = extract_function(self.html, "function applyDataAndRender(")
        for token in (
            "statsAndMarkersMs",
            "boundsAndMetricsMs",
            "cesiumSceneMs",
            "profileCanvasMs",
            "cpListMs",
            "cameraLaunchMs",
            "synchronousApplyMs",
            "firstScreenReadyMs",
            "firstPostPaintMs",
            "deferredSettledMs",
            "publishTrackLoadPerformance(performanceRecord, 'complete'",
        ):
            self.assertIn(token, apply_body)
        self.assertIn("scheduleTrackPostPaintWork(renderRevision", apply_body)

    def test_low_risk_performance_contracts_remain_active(self):
        haversine = extract_function(self.html, "function haversine(")
        self.assertNotIn("console.warn", haversine)
        canonical = extract_function(self.html, "function _buildStatsFromCanonical(")
        self.assertIn("if (pointDist == null)", canonical)
        peak = extract_function(self.html, "function _detectPeakMarkers(")
        self.assertNotIn("haversine(", peak)
        sync = extract_function(self.html, "function syncCurrentTrackContextForActivityAdvice(")
        self.assertIn("if (!isCanonicalActivity) payload.points = appState.points", sync)
        self.assertNotIn("points: appState.points", sync)

    def test_first_screen_queue_and_camera_are_revision_guarded(self):
        scheduler = extract_function(self.html, "function scheduleTrackPostPaintWork(")
        self.assertIn("isTrackRenderRevisionCurrent(renderRevision)", scheduler)
        self.assertIn("window.requestIdleCallback", scheduler)
        flight = extract_function(self.html, "function startInitialTrackCameraFlight(")
        self.assertIn("duration: 0.8", flight)
        claim = extract_function(self.html, "function claimCameraOwnership(")
        self.assertIn("cancelInitialTrackCameraFlight()", claim)

    def test_no_display_simplification_and_terrain_cost_is_user_triggered(self):
        for forbidden in ("DouglasPeucker", "douglasPeucker", "simplifiedPositions", "displayTrackPoints"):
            self.assertNotIn(forbidden, self.html)
        select = extract_function(self.html, "async function selectTerrainLayer(")
        load_real = extract_function(self.html, "async function loadRealTerrainLayerForCurrentTrack(")
        standard_branch = select[:select.index("updateTerrainLayerControl('real', 'loading'")]
        self.assertNotIn("loadRealTerrainLayerForCurrentTrack", standard_branch)
        self.assertIn("providerMetadataMs", load_real)
        self.assertIn("firstTerrainTileMs", select)
        self.assertIn("tilesSettledMs", select)
        self.assertIn("hillshadeSetupMs", select)
        self.assertIn("markerRebuildMs", select)

    def test_semantic_marker_progress_and_profile_contracts_remain(self):
        update_scene = extract_function(self.html, "function updateScene(")
        self.assertIn("appState.kmMarkers.forEach", update_scene)
        self.assertIn("appState.peakMarkers.forEach", update_scene)
        self.assertIn("appState.fullPositions.slice(Math.floor", update_scene)
        self.assertIn("renderCpMapLayer(exaggeration)", update_scene)
        self.assertIn("function drawProfileChart()", self.html)
        self.assertIn("openEditModal(entityId", self.html)
        self.assertIn("id=\"progress-slider\"", self.html)


if __name__ == "__main__":
    unittest.main()
