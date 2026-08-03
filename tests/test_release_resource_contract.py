"""Release-source contracts for V2.0 strength and Cesium resources."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strength_release_modules_and_vendored_assets_exist():
    for name in (
        "strength_fit_parser.py",
        "strength_muscle_map_v1.py",
        "strength_muscle_resolver.py",
    ):
        assert (ROOT / name).is_file(), name

    muscles = ROOT / "lib" / "body-muscles"
    for name in (
        "body-muscles.umd.min.js",
        "LICENSE",
        "NOTICE",
        "VENDORED.md",
    ):
        assert (muscles / name).is_file(), name


def test_cesium_release_resource_shape_is_complete():
    cesium = ROOT / "lib" / "Cesium"
    main_bundle = cesium / "Cesium.js"
    assert main_bundle.is_file()
    assert "Version 1.143.0" in main_bundle.read_text(encoding="utf-8", errors="replace")

    required = (
        cesium / "Widgets" / "widgets.css",
        cesium / "Assets" / "approximateTerrainHeights.json",
        cesium / "Workers" / "createVerticesFromHeightmap.js",
        cesium / "Workers" / "createVerticesFromQuantizedTerrainMesh.js",
        cesium / "ThirdParty" / "basis_transcoder.wasm",
        cesium / "ThirdParty" / "draco_decoder.wasm",
    )
    for path in required:
        assert path.is_file(), str(path.relative_to(ROOT))

    # A partial replacement of the worker tree is not a valid release source.
    assert len([path for path in cesium.rglob("*") if path.is_file()]) >= 390


def test_spec_collects_release_resources_and_local_modules():
    spec = (ROOT / "HikingTrackAnalyzer.spec").read_text(encoding="utf-8")
    assert '("lib", "lib")' in spec
    assert '("track.html", ".")' in spec
    assert '("assets", "assets")' in spec
    assert 'collect_submodules("garmin_fit_sdk")' in spec
