from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "garmin-fit-sdk-update.yml"
PACKAGE_WORKFLOW = ROOT / ".github" / "workflows" / "package-on-tag.yml"


def test_garmin_fit_sdk_update_workflow_is_scoped_and_gated():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "scripts/check_garmin_fit_sdk_update.py --json" in text
    assert "scripts/bump_garmin_fit_sdk_contract.py" in text
    assert "scripts/sync_garmin_fit_sdk_contract.py --json" in text
    assert "scripts/check_python312_runtime.py" in text
    assert "python -m packaging_diagnostics" in text
    assert "tests/test_fit_parser.py" in text
    assert "tests/test_fit_sync.py" in text
    assert "peter-evans/create-pull-request@v6" in text
    assert "codex/garmin-fit-sdk-" in text


def test_release_packaging_workflow_keeps_cross_platform_runtime_gates():
    text = PACKAGE_WORKFLOW.read_text(encoding="utf-8")

    assert "package-macos:" in text
    assert "package-windows:" in text
    assert ".venv312/bin/python scripts/check_python312_runtime.py" in text
    assert ".venv312/bin/python -m packaging_diagnostics" in text
    assert r".\.venv312\Scripts\python.exe scripts\check_python312_runtime.py" in text
    assert r".\.venv312\Scripts\python.exe -m packaging_diagnostics" in text
