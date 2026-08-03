"""Cesium / DEM POC static contract tests.

These tests freeze the Cesium / DEM POC contracts. Later POC tasks should
update assertions when a task intentionally changes the contract.
"""

import json
import re
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML = PROJECT_ROOT / "track.html"
CESIUM_DIR = PROJECT_ROOT / "lib" / "Cesium"


def extract_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function signature: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise AssertionError(f"missing function body: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"unclosed function body: {signature}")
    return source[brace_start + 1:index - 1]


class TestTrackCesiumDemBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TRACK_HTML.read_text(encoding="utf-8")

    def test_cesium_loads_from_local_base_with_current_legacy_fallback(self):
        self.assertIn("window.CESIUM_BASE_URL = 'lib/Cesium/';", self.html)
        self.assertIn('href="lib/Cesium/Widgets/widgets.css"', self.html)
        self.assertIn('src="lib/Cesium/Cesium.js"', self.html)
        self.assertIn("cesium@1.143.0/Build/Cesium/Widgets/widgets.css", self.html)
        self.assertIn("cesium@1.143.0/Build/Cesium/Cesium.js", self.html)
        self.assertNotIn("cesium@1.105.1", self.html)

    def test_local_cesium_143_resource_shape_exists(self):
        required_paths = [
            CESIUM_DIR / "Cesium.js",
            CESIUM_DIR / "index.cjs",
            CESIUM_DIR / "index.js",
            CESIUM_DIR / "Widgets" / "widgets.css",
            CESIUM_DIR / "Assets" / "approximateTerrainHeights.json",
            CESIUM_DIR / "Workers" / "createTaskProcessorWorker.js",
        ]
        for path in required_paths:
            self.assertTrue(path.exists(), f"missing Cesium resource: {path}")

        self.assertIn("Version 1.143.0", (CESIUM_DIR / "index.cjs").read_text(encoding="utf-8", errors="ignore")[:120])

    def test_viewer_initialization_uses_current_standard_terrain(self):
        body = extract_function_body(self.html, "function initCesiumViewer()")
        self.assertIn("new Cesium.Viewer('cesiumContainer'", body)
        self.assertIn("var standardBaseLayer = new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider", body)
        self.assertIn("new Cesium.UrlTemplateImageryProvider", body)
        self.assertIn("basemaps.cartocdn.com/rastertiles/voyager", body)
        self.assertIn("baseLayer: standardBaseLayer", body)
        self.assertIn("var compatibleGlobe = createCesiumWebviewCompatibleGlobe()", body)
        self.assertIn("globe: compatibleGlobe", body)
        self.assertNotIn("imageryProvider:", body)
        self.assertIn("terrainProvider: new Cesium.EllipsoidTerrainProvider()", body)
        self.assertIn("orderIndependentTranslucency: false", body)
        self.assertIn("shadows: false", body)
        self.assertIn("terrainShadows: Cesium.ShadowMode.DISABLED", body)
        self.assertIn("msaaSamples: 1", body)
        self.assertIn("showRenderLoopErrors: false", body)
        self.assertIn("skyAtmosphere: false", body)
        self.assertIn("skyBox: false", body)
        self.assertIn("baseLayerPicker: false", body)
        self.assertIn("applyCesiumWebviewShaderCompatibility();", body)
        self.assertIn("viewer.scene.globe.depthTestAgainstTerrain = true", body)
        self.assertIn("setupViewerInteractions();", body)

    def test_webview_shader_compatibility_disables_atmosphere_paths(self):
        body = extract_function_body(self.html, "function applyCesiumWebviewShaderCompatibility()")
        self.assertIn("scene.highDynamicRange = false", body)
        self.assertIn("scene.sunBloom = false", body)
        self.assertIn("scene.fxaa = false", body)
        self.assertIn("scene.skyAtmosphere.show = false", body)
        self.assertIn("scene.sun.show = false", body)
        self.assertIn("scene.fog.enabled = false", body)
        self.assertIn("scene.shadowMap.enabled = false", body)
        self.assertIn("scene.postProcessStages.fxaa.enabled = false", body)
        self.assertIn("scene.postProcessStages.bloom.enabled = false", body)
        self.assertIn("scene.postProcessStages.ambientOcclusion.enabled = false", body)
        self.assertIn("scene.globe.showGroundAtmosphere = false", body)
        self.assertIn("scene.globe.enableLighting = false", body)
        self.assertIn("scene.globe.dynamicAtmosphereLighting = false", body)
        self.assertIn("scene.globe.dynamicAtmosphereLightingFromSun = false", body)
        self.assertIn("scene.globe.shadows = Cesium.ShadowMode.DISABLED", body)
        self.assertIn("scene.globe.showWaterEffect = false", body)

        globe_body = extract_function_body(self.html, "function createCesiumWebviewCompatibleGlobe()")
        self.assertIn("new Cesium.Globe(Cesium.Ellipsoid.WGS84)", globe_body)
        self.assertIn("globe.showGroundAtmosphere = false", globe_body)
        self.assertIn("globe.enableLighting = false", globe_body)
        self.assertIn("globe.dynamicAtmosphereLighting = false", globe_body)
        self.assertIn("globe.dynamicAtmosphereLightingFromSun = false", globe_body)
        self.assertIn("globe.shadows = Cesium.ShadowMode.DISABLED", globe_body)
        self.assertIn("globe.showWaterEffect = false", globe_body)

    def test_required_trace_panel_controls_exist(self):
        required = [
            'id="cesiumContainer"',
            'id="map-compass-btn"',
            'id="map-view-slider"',
            'id="btn-auto-rotate"',
            'id="toggle-cp"',
            'id="toggle-km"',
            'id="toggle-peak"',
            'id="progress-slider"',
            'id="profile-canvas"',
            'id="terrain-layer-standard"',
            'id="terrain-layer-real"',
        ]
        for token in required:
            self.assertIn(token, self.html)

    def test_topbar_is_semantically_grouped_and_never_relies_on_hidden_horizontal_scroll(self):
        required_groups = [
            'class="topbar-stats"',
            'class="topbar-view-controls"',
            'class="topbar-terrain-control"',
            'class="topbar-actions"',
            'class="topbar-secondary-actions"',
            'class="topbar-visibility"',
            'class="topbar-progress"',
        ]
        for token in required_groups:
            self.assertIn(token, self.html)

        self.assertIn('aria-controls="topbar-secondary-menu" aria-expanded="false"', self.html)
        self.assertIn('id="topbar-secondary-menu" aria-label="次级轨迹工具"', self.html)
        panel_start = self.html.find('.panel-inner {')
        panel_end = self.html.find('.mini-stat {', panel_start)
        self.assertGreater(panel_start, 0)
        self.assertGreater(panel_end, panel_start)
        panel_css = self.html[panel_start:panel_end]
        self.assertIn('flex-wrap: wrap', panel_css)
        self.assertNotIn('overflow-x: auto', panel_css)
        self.assertNotIn('scrollbar-width: none', panel_css)
        self.assertIn('.topbar-more.is-open .topbar-secondary-actions {', self.html)
        self.assertIn('function bindTopbarMoreMenu()', self.html)
        self.assertIn("event.key === 'Escape'", self.html)
        self.assertIn("secondaryActions.addEventListener('click', closeMenu)", self.html)
        self.assertIn('.topbar-stats .stat-gain', self.html)
        self.assertIn('.topbar-stats .stat-max', self.html)
        self.assertIn('class="mini-stat stat-time"', self.html)
        stats_start = self.html.find('.topbar-stats {')
        stats_end = self.html.find('.topbar-actions {', stats_start)
        self.assertGreater(stats_start, 0)
        self.assertGreater(stats_end, stats_start)
        stats_css = self.html[stats_start:stats_end]
        self.assertIn('flex: 1 0 auto', stats_css)
        self.assertIn('min-width: max-content', stats_css)

        for token in [
            'id="map-compass-btn"',
            'id="map-view-slider"',
            'id="terrain-layer-standard"',
            'id="terrain-layer-real"',
            'id="btn-auto-rotate"',
            'id="toggle-cp"',
            'id="toggle-km"',
            'id="toggle-peak"',
            'id="progress-slider"',
            'onclick="triggerTrackImport()"',
            'onclick="setViewProfile()"',
            'onclick="exportGPX()"',
        ]:
            self.assertIn(token, self.html)

    def test_terrain_layer_control_is_independent_from_view_slider(self):
        self.assertIn('aria-label="地形图层控制"', self.html)
        self.assertIn('data-terrain-layer="standard"', self.html)
        self.assertIn('data-terrain-layer="real"', self.html)
        self.assertIn(">标准地形</button>", self.html)
        self.assertIn(">真实地形</button>", self.html)
        self.assertIn("terrainLayerMode: 'standard'", self.html)
        self.assertIn("terrainLayerStatus: 'idle'", self.html)
        self.assertIn("ARCGIS_WORLD_ELEVATION_TERRAIN_URL", self.html)
        self.assertIn("WorldElevation3D/Terrain3D/ImageServer", self.html)

        init_body = extract_function_body(self.html, "function initCesiumViewer()")
        self.assertIn("updateTerrainLayerControl('standard', 'idle', '')", init_body)

        standard_body = extract_function_body(self.html, "function applyStandardTerrainLayer(")
        self.assertIn("viewer.scene.terrainProvider = new Cesium.EllipsoidTerrainProvider()", standard_body)
        self.assertIn("updateTerrainLayerControl('standard'", standard_body)
        self.assertIn("refreshTerrainSensitiveScene()", standard_body)

        real_body = extract_function_body(self.html, "async function loadRealTerrainLayerForCurrentTrack(")
        self.assertIn("prepare_dem_session_cache", real_body)
        self.assertIn("JSON.stringify(appState.points)", real_body)
        self.assertIn("Cesium.ArcGISTiledElevationTerrainProvider.fromUrl", real_body)
        self.assertIn("ARCGIS_WORLD_ELEVATION_TERRAIN_URL", real_body)
        self.assertNotIn("fetch(", real_body)
        self.assertNotIn("CesiumTerrainProvider", real_body)
        self.assertNotIn("sampleTerrain", real_body)

        select_body = extract_function_body(self.html, "async function selectTerrainLayer(")
        self.assertIn("updateTerrainLayerControl('real', 'loading'", select_body)
        self.assertIn("viewer.scene.terrainProvider = provider", select_body)
        self.assertIn("updateTerrainLayerControl('real', 'ready'", select_body)
        self.assertIn("refreshTerrainSensitiveScene()", select_body)
        self.assertIn("applyStandardTerrainLayer('真实地形暂不可用')", select_body)

        slider_idx = self.html.find("const mapViewSlider = document.getElementById('map-view-slider')")
        self.assertGreater(slider_idx, 0)
        terrain_binding_idx = self.html.find("document.getElementById('terrain-layer-standard')", slider_idx)
        self.assertGreater(terrain_binding_idx, slider_idx)
        slider_block = self.html[slider_idx:terrain_binding_idx]
        self.assertNotIn("selectTerrainLayer", slider_block)
        self.assertNotIn("applyStandardTerrainLayer", slider_block)
        self.assertNotIn("loadRealTerrainLayerForCurrentTrack", slider_block)

    def test_real_terrain_keeps_semantic_track_and_marker_layers(self):
        update_scene = extract_function_body(self.html, "function updateScene()")
        self.assertIn("const useRealTerrain = isRealTerrainLayerReady()", update_scene)
        self.assertIn("clampToGround: useRealTerrain", update_scene)
        self.assertIn("buildTrackPolylineMaterial(TRACK_VISUAL_STYLE.remainingColor", update_scene)
        self.assertIn("buildTrackPolylineMaterial(TRACK_VISUAL_STYLE.completedColor", update_scene)
        self.assertIn("appState.fullPositions.slice(Math.floor", update_scene)
        self.assertIn("getTerrainVisualAlt(km.alt, exaggeration, 35, REAL_TERRAIN_MARKER_VISUAL.kmOffset)", update_scene)
        self.assertIn("getTerrainVisualAlt(peak.alt, exaggeration, 35, getPeakRealTerrainOffset(peak))", update_scene)

        cp_body = extract_function_body(self.html, "function renderCpMapLayer(")
        self.assertIn("const heightReference = getTerrainMarkerHeightReference()", cp_body)
        self.assertIn("buildCpBillboardVisual(pm, heightReference)", cp_body)
        self.assertIn("buildCpLabelVisual(pm, heightReference)", cp_body)

        marker_reference = extract_function_body(self.html, "function getTerrainMarkerHeightReference()")
        self.assertIn("Cesium.HeightReference.RELATIVE_TO_GROUND", marker_reference)
        self.assertIn("Cesium.HeightReference.NONE", marker_reference)

    def test_real_terrain_marker_declutter_contract(self):
        self.assertIn("const REAL_TERRAIN_MARKER_VISUAL = {", self.html)
        self.assertIn("depthDisableDistance: 24000", self.html)
        self.assertIn("kmEveryOneMaxDistance", self.html)
        self.assertIn("kmEveryFiveMaxDistance", self.html)
        self.assertIn("kmEveryTenMaxDistance", self.html)
        self.assertIn("highestPeakLabelMaxDistance", self.html)

        cp_body = extract_function_body(self.html, "function renderCpMapLayer(")
        self.assertIn("const entityOptions = {", cp_body)
        self.assertIn("billboard: buildCpBillboardVisual(pm, heightReference)", cp_body)
        self.assertIn("label: buildCpLabelVisual(pm, heightReference)", cp_body)
        self.assertIn("const cpPointVisual = buildCpPointVisual(pm, pointColor, heightReference)", cp_body)
        self.assertIn("if (cpPointVisual) entityOptions.point = cpPointVisual", cp_body)

        cp_point_body = extract_function_body(self.html, "function buildCpPointVisual(")
        self.assertIn("if (isRealTerrainLayerReady()) return null", cp_point_body)
        self.assertIn("disableDepthTestDistance: getTerrainMarkerDepthDisableDistance()", cp_point_body)

        cp_billboard_body = extract_function_body(self.html, "function buildCpBillboardVisual(")
        self.assertIn("distanceDisplayCondition: getCpBillboardDistanceDisplayCondition(pm)", cp_billboard_body)
        self.assertIn("scaleByDistance: new Cesium.NearFarScalar(500, 1.14, 65000, 0.72)", cp_billboard_body)

        km_body = extract_function_body(self.html, "function getKmDistanceDisplayCondition(")
        self.assertIn("kmNumber % 10 === 0", km_body)
        self.assertIn("kmNumber % 5 === 0", km_body)
        self.assertIn("REAL_TERRAIN_MARKER_VISUAL.kmEveryOneMaxDistance", km_body)

        peak_body = extract_function_body(self.html, "function getPeakDistanceDisplayCondition(")
        self.assertIn("peak && peak.isHighest", peak_body)
        self.assertIn("REAL_TERRAIN_MARKER_VISUAL.highestPeakLabelMaxDistance", peak_body)
        self.assertIn("REAL_TERRAIN_MARKER_VISUAL.peakLabelMaxDistance", peak_body)

    def test_real_terrain_visual_mode_is_display_only_and_tile_settled(self):
        self.assertIn("const REAL_TERRAIN_VISUAL_MODE = {", self.html)
        self.assertIn("verticalExaggeration: 1.6", self.html)

        visual_body = extract_function_body(self.html, "function applyRealTerrainVisualMode()")
        self.assertIn("Visual only: never feed DEM exaggeration back into FIT altitude", visual_body)
        self.assertIn("viewer.scene.verticalExaggeration = REAL_TERRAIN_VISUAL_MODE.verticalExaggeration", visual_body)
        self.assertIn("viewer.scene.verticalExaggerationRelativeHeight = appState.minAltitude || 0", visual_body)
        self.assertNotIn("appState.points", visual_body)
        self.assertNotIn("activityMetrics", visual_body)

        standard_body = extract_function_body(self.html, "function applyStandardTerrainVisualMode()")
        self.assertIn("viewer.scene.verticalExaggeration = 1.0", standard_body)
        self.assertIn("viewer.scene.verticalExaggerationRelativeHeight = 0.0", standard_body)

        wait_body = extract_function_body(self.html, "function waitForRealTerrainTiles(")
        self.assertIn("viewer.scene.globe.tilesLoaded", wait_body)
        self.assertIn("viewer.scene.postRender.addEventListener", wait_body)
        self.assertIn("viewer.scene.globe.tileLoadProgressEvent.addEventListener", wait_body)
        self.assertIn("observedPendingTerrainTiles", wait_body)
        self.assertIn("firstTerrainTileMs", wait_body)
        self.assertIn("timeoutId = setTimeout", wait_body)
        self.assertIn("clearTimeout(timeoutId)", wait_body)
        self.assertIn("removePostRenderListener()", wait_body)
        self.assertIn("removeProgressListener()", wait_body)

        select_body = extract_function_body(self.html, "async function selectTerrainLayer(")
        self.assertIn("applyRealTerrainVisualMode()", select_body)
        self.assertIn("await waitForRealTerrainTiles", select_body)
        self.assertIn("refreshTerrainSensitiveScene()", select_body)
        self.assertNotIn("frameRealTerrainRoute()", select_body)
        self.assertNotIn("viewer.camera", select_body)
        self.assertNotIn("map-view-slider", select_body)
        self.assertNotIn("function frameRealTerrainRoute(", self.html)

    def test_terrain_performance_is_isolated_and_stage_based(self):
        self.assertIn("lastTerrainLoadPerformance: null", self.html)
        self.assertIn("function createTerrainLoadPerformance(", self.html)
        self.assertIn("function finalizeTerrainLoadPerformance(", self.html)
        self.assertIn("function getLastTerrainLoadPerformance(", self.html)

        load_body = extract_function_body(self.html, "async function loadRealTerrainLayerForCurrentTrack(")
        self.assertIn("record.stage = 'dem_session_prepare'", load_body)
        self.assertIn("record.demSessionPrepareMs", load_body)
        self.assertIn("record.stage = 'provider_metadata'", load_body)
        self.assertIn("record.providerMetadataMs", load_body)

        select_body = extract_function_body(self.html, "async function selectTerrainLayer(")
        for token in (
            "providerAssignMs",
            "hillshadeSetupMs",
            "observedPendingTerrainTiles",
            "firstTerrainTileMs",
            "tilesSettledMs",
            "markerRebuildMs",
            "finalizeTerrainLoadPerformance(performanceRecord, 'ready'",
            "finalizeTerrainLoadPerformance(performanceRecord, 'failed'",
        ):
            self.assertIn(token, select_body)
        standard_branch = select_body[:select_body.index("updateTerrainLayerControl('real', 'loading'")]
        self.assertNotIn("loadRealTerrainLayerForCurrentTrack", standard_branch)
        self.assertNotIn("waitForRealTerrainTiles", standard_branch)
        self.assertNotIn("applyRealTerrainVisualMode", standard_branch)

    def test_terrain_tile_timing_releases_runtime_listeners(self):
        helper_sources = []
        for signature, declaration in (
            ("function terrainPerformanceNow()", "function terrainPerformanceNow()"),
            ("function roundTerrainPerformanceMs(", "function roundTerrainPerformanceMs(value)"),
            ("function waitForRealTerrainTiles(", "function waitForRealTerrainTiles(maxWaitMs, minStableFrames)"),
        ):
            helper_sources.append(declaration + "{" + extract_function_body(self.html, signature) + "}")
        script = "\n".join(helper_sources) + r"""
let now = 0;
let progressCallback = null;
let postRenderCallback = null;
let progressRemoved = false;
let postRenderRemoved = false;
const window = { performance: { now: () => now } };
const globe = {
  tilesLoaded: false,
  tileLoadProgressEvent: {
    addEventListener: (callback) => { progressCallback = callback; return () => { progressRemoved = true; }; }
  }
};
const viewer = { scene: {
  globe,
  postRender: {
    addEventListener: (callback) => { postRenderCallback = callback; return () => { postRenderRemoved = true; }; }
  }
} };
const requestSceneRender = () => {};
const timeoutCallbacks = [];
const setTimeout = (callback) => { timeoutCallbacks.push(callback); return timeoutCallbacks.length; };
const clearTimeout = () => {};
(async function() {
  const pending = waitForRealTerrainTiles(1200, 3);
  now = 20; progressCallback(4);
  now = 80; progressCallback(0);
  globe.tilesLoaded = true;
  now = 90; postRenderCallback();
  now = 100; postRenderCallback();
  now = 110; postRenderCallback();
  const result = await pending;
  process.stdout.write(JSON.stringify({ result, progressRemoved, postRenderRemoved }));
})();
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["result"]["settled"])
        self.assertTrue(payload["result"]["observedPendingTerrainTiles"])
        self.assertEqual(payload["result"]["firstTerrainTileMs"], 80)
        self.assertEqual(payload["result"]["tilesSettledMs"], 110)
        self.assertTrue(payload["progressRemoved"])
        self.assertTrue(payload["postRenderRemoved"])

    def test_legacy_vertical_relief_entity_is_retired(self):
        update_scene = extract_function_body(self.html, "function updateScene()")
        self.assertNotIn("wall" + "Entity", self.html)
        self.assertNotIn("fullMax" + "Heights", self.html)
        self.assertNotIn("fullMin" + "Heights", self.html)
        self.assertNotIn("maximum" + "Heights", update_scene)
        self.assertNotIn("minimum" + "Heights", update_scene)
        self.assertNotIn("wall" + "Color", update_scene)
        self.assertNotIn("海拔" + "剖面堆积墙", self.html)
        self.assertIn("id=\"profile-canvas\"", self.html)
        self.assertIn("function drawProfileChart()", self.html)

    def test_progress_sliced_completed_and_remaining_tracks_are_callback_based(self):
        update_scene = extract_function_body(self.html, "function updateScene()")
        self.assertIn("appState.remainingTrackEntity = viewer.entities.add", update_scene)
        self.assertIn("appState.completedTrackEntity = viewer.entities.add", update_scene)
        self.assertIn("name: '未完成轨迹'", update_scene)
        self.assertIn("name: '已完成轨迹'", update_scene)
        self.assertGreaterEqual(update_scene.count("new Cesium.CallbackProperty"), 4)
        self.assertIn("appState.fullPositions.slice(Math.floor", update_scene)
        self.assertIn("appState.progress / 100", update_scene)

    def test_cp_create_edit_delete_and_profile_click_linkage_exist(self):
        for signature in [
            "function renderCpMapLayer(",
            "function refreshCpViews()",
            "function openEditModal(",
            "function openAddModal(",
            "function saveCp()",
            "function deleteCp()",
            "function deleteCpFromList(",
            "function syncPlacemarksToBackend(",
        ]:
            self.assertIn(signature, self.html)

        interactions = extract_function_body(self.html, "function setupViewerInteractions()")
        self.assertIn("entityId.startsWith('cp_')", interactions)
        self.assertIn("openEditModal(entityId", interactions)
        self.assertIn("openAddModal(nearestPoint.lon, nearestPoint.lat, nearestPoint.alt)", interactions)
        self.assertIn("document.getElementById('profile-canvas').addEventListener('click'", self.html)

    def test_km_peak_toggles_and_scene_refresh_are_bound(self):
        body = extract_function_body(self.html, "function bindTopBarToggles()")
        self.assertIn("const cpToggle = document.getElementById('toggle-cp')", body)
        self.assertIn("const kmToggle = document.getElementById('toggle-km')", body)
        self.assertIn("const peakToggle = document.getElementById('toggle-peak')", body)
        self.assertIn("appState.showCP = cpToggle.checked", body)
        self.assertIn("appState.showKM = kmToggle.checked", body)
        self.assertIn("appState.showPeak = peakToggle.checked", body)
        self.assertIn("updateScene();", body)
        self.assertIn("appState.progress = val", body)
        self.assertIn("requestSceneRender();", body)

        update_scene = extract_function_body(self.html, "function updateScene()")
        self.assertIn("appState.kmMarkers.forEach", update_scene)
        self.assertIn("appState.peakMarkers.forEach", update_scene)
        self.assertIn("buildPeakLabelVisual(peak", update_scene)
        self.assertIn("buildPeakPointVisual(peak", update_scene)
        self.assertIn("buildPeakBillboardVisual(peak", update_scene)
        peak_label_body = extract_function_body(self.html, "function buildPeakLabelVisual(")
        self.assertIn("peak.isHighest", peak_label_body)

    def test_real_terrain_uses_canvas_billboards_and_hillshade_overlay(self):
        self.assertIn("ARCGIS_WORLD_SHADED_RELIEF_URL", self.html)
        self.assertIn("World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}", self.html)

        pin_body = extract_function_body(self.html, "function buildMapPinCanvasImage(")
        self.assertIn("document.createElement('canvas')", pin_body)
        self.assertIn("canvas.toDataURL('image/png')", pin_body)
        self.assertNotIn("data:image/svg+xml", pin_body)
        self.assertNotIn("<text", pin_body)
        self.assertNotIn("feDropShadow", pin_body)
        self.assertNotIn("<filter", pin_body)

        cp_pin_body = extract_function_body(self.html, "function getCpPinImage(")
        self.assertIn("buildMapPinCanvasImage(color", cp_pin_body)
        self.assertNotIn("emoji", cp_pin_body)

        peak_billboard_body = extract_function_body(self.html, "function buildPeakBillboardVisual(")
        self.assertIn("if (!isRealTerrainLayerReady()) return null", peak_billboard_body)
        self.assertIn("image: getPeakPinImage(peak)", peak_billboard_body)

        peak_point_body = extract_function_body(self.html, "function buildPeakPointVisual(")
        self.assertIn("if (isRealTerrainLayerReady()) return null", peak_point_body)

        cp_label_body = extract_function_body(self.html, "function buildCpLabelVisual(")
        self.assertIn("stripMapLabelEmoji(pm.name)", cp_label_body)
        peak_label_body = extract_function_body(self.html, "function buildPeakLabelVisual(")
        self.assertIn("stripMapLabelEmoji(peak.name)", peak_label_body)

        relief_body = extract_function_body(self.html, "function applyRealTerrainReliefOverlay()")
        self.assertIn("new Cesium.UrlTemplateImageryProvider", relief_body)
        self.assertIn("ARCGIS_WORLD_SHADED_RELIEF_URL", relief_body)
        self.assertIn("viewer.scene.imageryLayers.addImageryProvider(provider)", relief_body)
        self.assertIn("realTerrainReliefLayer.alpha = 0.36", relief_body)
        self.assertIn("realTerrainReliefLayer.contrast = 1.28", relief_body)

        remove_body = extract_function_body(self.html, "function removeRealTerrainReliefOverlay()")
        self.assertIn("viewer.scene.imageryLayers.remove(realTerrainReliefLayer, true)", remove_body)

        real_visual_body = extract_function_body(self.html, "function applyRealTerrainVisualMode()")
        self.assertIn("applyRealTerrainReliefOverlay()", real_visual_body)
        standard_visual_body = extract_function_body(self.html, "function applyStandardTerrainVisualMode()")
        self.assertIn("removeRealTerrainReliefOverlay()", standard_visual_body)

    def test_2d_3d_slider_releases_lookat_transform(self):
        self.assertIn("function resetCameraTransformSafely()", self.html)
        self.assertIn("viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY)", self.html)
        self.assertIn("function beginMapViewSliderDrag(event)", self.html)
        self.assertIn("function endMapViewSliderDrag()", self.html)
        slider_idx = self.html.find("const mapViewSlider = document.getElementById('map-view-slider')")
        self.assertGreater(slider_idx, 0)
        slider_block = self.html[slider_idx:slider_idx + 1800]
        self.assertIn("viewer.camera.lookAt(dragTarget", slider_block)
        self.assertIn("window.addEventListener('mouseup', endMapViewSliderDrag)", slider_block)
        self.assertIn("window.addEventListener('touchend', endMapViewSliderDrag)", slider_block)
        self.assertIn("resetMapNorth", self.html)

    def test_maplibre_deckgl_route_diagnosis_is_not_in_current_poc_surface(self):
        forbidden = [
            "maplibregl",
            "MapLibre",
            "deck.gl",
            "DeckGL",
            "路线诊断",
        ]
        for token in forbidden:
            self.assertNotIn(token, self.html)

    def test_activity_altitude_truth_remains_distinct_from_future_dem_layer(self):
        update_scene = extract_function_body(self.html, "function updateScene()")
        terrain_alt = extract_function_body(self.html, "function getTerrainVisualAlt(")
        self.assertIn("return (Number(rawAlt || 0) - appState.minAltitude) * exaggeration + standardOffset", terrain_alt)
        self.assertIn("getTerrainVisualAlt(p.alt, exaggeration, 30, 0)", update_scene)
        self.assertIn("drawProfileChart", self.html)
        self.assertNotIn("CesiumTerrainProvider", self.html)
        self.assertNotIn("Cesium.sampleTerrain", self.html)
        self.assertNotIn("sampleTerrainMostDetailed", self.html)
        self.assertNotIn("sampleTerrain(", self.html)
