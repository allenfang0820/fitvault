from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DELIVERY_MANUAL = ROOT / "docs" / "Garmin_FIT_SDK_持续更新治理交付手册.md"
CONTRACT = ROOT / "docs" / "Garmin_FIT_SDK_持续更新治理契约摘要.md"
UPDATE_WORKFLOW = ROOT / ".github" / "workflows" / "garmin-fit-sdk-update.yml"


def test_garmin_fit_sdk_rollback_docs_define_last_stable_anchor_and_commands():
    manual = DELIVERY_MANUAL.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    workflow = UPDATE_WORKFLOW.read_text(encoding="utf-8")

    assert "最后稳定版本的记录位置" in manual
    assert "packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION" in manual
    assert "自动升级 PR 正文里的 `Current` 字段" in manual
    assert 'python scripts/bump_garmin_fit_sdk_contract.py --version "<last-stable-version>" --json' in manual
    assert "安装失败 / import 失败 / 解析回归 / runtime gate 失败 / 打包失败" in manual
    assert "不得上传真实 FIT、账号、token、Cookie 或本机隐私路径" in manual

    assert "Current` 字段作为该 PR 的回滚锚点" in contract
    assert "不得在回滚 PR 中混入 FIT 解析逻辑、活动命名、UI 文案或其他依赖变更" in contract

    assert "Rollback anchor" in workflow
    assert 'python scripts/bump_garmin_fit_sdk_contract.py --version "${{ steps.check.outputs.current }}" --json' in workflow
