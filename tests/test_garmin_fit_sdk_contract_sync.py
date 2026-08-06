from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import packaging_diagnostics as diag


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "sync_garmin_fit_sdk_contract.py"


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_garmin_fit_sdk_contract", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_garmin_fit_sdk_contract_files_match_single_version_source():
    sync = _load_sync_module()

    result = sync.sync_contract(ROOT, write=False)

    assert result["ok"] is True
    assert result["expected_version"] == diag.GARMIN_FIT_SDK_EXPECTED_VERSION
    assert {item["path"] for item in result["files"]} == {
        "requirements.txt",
        "constraints.txt",
        "docs/打包前必读.md",
        "docs/V2.0_macOS打包契约摘要.md",
        "docs/V2.0_Windows打包继续审查清单.md",
    }


def test_garmin_fit_sdk_contract_sync_can_rewrite_temp_tree(tmp_path):
    sync = _load_sync_module()
    for target in sync.TARGETS:
        source = ROOT / target.path
        destination = tmp_path / target.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8").replace(diag.GARMIN_FIT_SDK_EXPECTED_VERSION, "0.0.1"), encoding="utf-8")

    before = sync.sync_contract(tmp_path, write=False)
    after = sync.sync_contract(tmp_path, write=True)

    assert before["ok"] is False
    assert after["ok"] is True
    for target in sync.TARGETS:
        text = (tmp_path / target.path).read_text(encoding="utf-8")
        assert diag.GARMIN_FIT_SDK_EXPECTED_VERSION in text


def test_garmin_fit_sdk_contract_sync_cli_json():
    completed = subprocess.run(
        [str(ROOT / ".venv312" / "bin" / "python"), str(SCRIPT_PATH), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["expected_version"] == diag.GARMIN_FIT_SDK_EXPECTED_VERSION


def test_garmin_fit_sdk_contract_bump_rewrites_single_source_and_targets(tmp_path):
    for relative in (
        "packaging_diagnostics.py",
        "requirements.txt",
        "constraints.txt",
        "docs/打包前必读.md",
        "docs/V2.0_macOS打包契约摘要.md",
        "docs/V2.0_Windows打包继续审查清单.md",
    ):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    completed = subprocess.run(
        [
            str(ROOT / ".venv312" / "bin" / "python"),
            str(ROOT / "scripts" / "bump_garmin_fit_sdk_contract.py"),
            "--root",
            str(tmp_path),
            "--version",
            "21.999.0",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert 'GARMIN_FIT_SDK_EXPECTED_VERSION = "21.999.0"' in (tmp_path / "packaging_diagnostics.py").read_text(encoding="utf-8")
    assert "garmin-fit-sdk==21.999.0" in (tmp_path / "requirements.txt").read_text(encoding="utf-8")
