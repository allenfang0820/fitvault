from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_python312_runtime.py"


def _load_runtime_check_module():
    spec = importlib.util.spec_from_file_location("check_python312_runtime", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_python312_runtime_check_script_contains_release_contracts():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "garminconnect" in source
    assert "garmin-fit-sdk" in source
    assert "garmin_fit_sdk" in source
    assert "GARMIN_FIT_SDK_EXPECTED_VERSION" in source
    assert "curl_cffi" in source
    assert "fitparse" in source
    assert "webview" in source
    assert "startup_lazy_import_ok" in source
    assert "import main" in source
    assert "pip install" not in source


def test_runtime_report_accepts_mocked_healthy_python312_environment():
    runtime_check = _load_runtime_check_module()
    versions = {
        "garminconnect": "0.3.6",
        "garmin-fit-sdk": "21.208.0",
        "curl_cffi": "0.6.1",
        "requests": "2.34.2",
        "urllib3": "2.7.0",
        "certifi": "2026.6.17",
    }
    imported: list[str] = []

    def fake_import(name):
        imported.append(name)
        return object()

    report = runtime_check.build_runtime_report(
        version_lookup=lambda name: versions.get(name),
        import_module=fake_import,
        startup_checker=lambda: ({"ok": True, "loaded": {"garmin_fit_sdk": False, "fitparse": False}}, []),
    )

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["startup_lazy_import_ok"] is True
    assert set(imported) == set(runtime_check.REQUIRED_IMPORTS)
    assert report["checked_distributions"]["garmin-fit-sdk"]["version"] == "21.208.0"


def test_runtime_report_fails_missing_distribution_and_startup_lazy_violation():
    runtime_check = _load_runtime_check_module()
    versions = {
        "garminconnect": "0.3.6",
        "curl_cffi": "0.6.1",
        "requests": "2.34.2",
        "urllib3": "2.7.0",
        "certifi": "2026.6.17",
    }

    report = runtime_check.build_runtime_report(
        version_lookup=lambda name: versions.get(name),
        import_module=lambda name: object(),
        startup_checker=lambda: (
            {"ok": False, "loaded": {"garmin_fit_sdk": True, "fitparse": False}},
            ["Startup import loaded garmin_fit_sdk; expected lazy import"],
        ),
    )

    assert report["ok"] is False
    assert report["startup_lazy_import_ok"] is False
    assert any("garmin-fit-sdk" in error for error in report["errors"])
    assert any("Startup import loaded garmin_fit_sdk" in error for error in report["errors"])


def test_runtime_report_fails_import_error_without_real_environment_dependency():
    runtime_check = _load_runtime_check_module()
    versions = {
        "garminconnect": "0.3.6",
        "garmin-fit-sdk": "21.208.0",
        "curl_cffi": "0.6.1",
        "requests": "2.34.2",
        "urllib3": "2.7.0",
        "certifi": "2026.6.17",
    }

    def fake_import(name):
        if name == "garmin_fit_sdk":
            raise ModuleNotFoundError("No module named 'garmin_fit_sdk'")
        return object()

    report = runtime_check.build_runtime_report(
        version_lookup=lambda name: versions.get(name),
        import_module=fake_import,
        startup_checker=lambda: ({"ok": True, "loaded": {"garmin_fit_sdk": False, "fitparse": False}}, []),
    )

    assert report["ok"] is False
    assert any("Cannot import garmin_fit_sdk" in error for error in report["errors"])
