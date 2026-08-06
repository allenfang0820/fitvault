from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import packaging_diagnostics as diag


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_garmin_fit_sdk_update.py"


def _load_update_module():
    spec = importlib.util.spec_from_file_location("check_garmin_fit_sdk_update", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_update_report_detects_newer_stable_version_and_ignores_prerelease():
    update = _load_update_module()

    report = update.build_update_report(
        current_version="21.208.0",
        fetcher=lambda: {"releases": {"21.208.0": [], "21.212.0rc1": [], "21.212.0": []}},
        checked_at="2026-08-06T00:00:00Z",
    )

    assert report == {
        "ok": True,
        "package": "garmin-fit-sdk",
        "current_version": "21.208.0",
        "latest_stable_version": "21.212.0",
        "update_available": True,
        "source": "pypi",
        "checked_at": "2026-08-06T00:00:00Z",
    }


def test_update_report_marks_current_version_up_to_date():
    update = _load_update_module()

    report = update.build_update_report(
        current_version=diag.GARMIN_FIT_SDK_EXPECTED_VERSION,
        fetcher=lambda: {"releases": {diag.GARMIN_FIT_SDK_EXPECTED_VERSION: [], "21.0.0": []}},
        checked_at="2026-08-06T00:00:00Z",
    )

    assert report["ok"] is True
    assert report["latest_stable_version"] == diag.GARMIN_FIT_SDK_EXPECTED_VERSION
    assert report["update_available"] is False


def test_update_report_does_not_treat_network_failure_as_no_update():
    update = _load_update_module()

    def failing_fetcher():
        raise update.UpdateCheckError("network_error", "timeout")

    report = update.build_update_report(fetcher=failing_fetcher, checked_at="2026-08-06T00:00:00Z")

    assert report["ok"] is False
    assert report["latest_stable_version"] is None
    assert report["update_available"] is None
    assert report["error_code"] == "network_error"


def test_update_report_rejects_bad_pypi_payload():
    update = _load_update_module()

    report = update.build_update_report(fetcher=lambda: {"info": {}}, checked_at="2026-08-06T00:00:00Z")

    assert report["ok"] is False
    assert report["error_code"] == "bad_response"


def test_update_cli_json_with_mocked_fetcher(monkeypatch, capsys):
    update = _load_update_module()

    monkeypatch.setattr(
        update,
        "build_update_report",
        lambda: {
            "ok": True,
            "package": "garmin-fit-sdk",
            "current_version": "21.208.0",
            "latest_stable_version": "21.212.0",
            "update_available": True,
            "source": "pypi",
            "checked_at": "2026-08-06T00:00:00Z",
        },
    )

    assert update.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["update_available"] is True
