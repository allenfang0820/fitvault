---
title: Garmin FIT SDK 持续更新治理基线审计报告
version: v0.1
status: Baseline
type: Audit Report
updated: 2026-08-06
source:
  - docs/Garmin_FIT_SDK_持续更新治理交付手册.md
  - docs/Garmin_FIT_SDK_持续更新治理任务清单.md
  - docs/Garmin_FIT_SDK_持续更新治理契约摘要.md
---

# Garmin FIT SDK 持续更新治理基线审计报告

## 1. 当前工作区

审计开始时工作区已有多处并行改动，主要集中在 FIT 导入、活动详情、复盘和测试文件。本治理任务不得覆盖、回退、格式化或提交这些无关改动。

本轮新增治理文档属于当前任务范围。

## 2. 当前锁定版本

当前仓库和本地 `.venv312` 均锁定：

| 依赖 | 当前版本 |
| --- | --- |
| `garmin-fit-sdk` | `21.208.0` |
| `garminconnect` | `0.3.6` |
| `curl_cffi` | `0.15.0`，满足 `>=0.6` |

## 3. 版本引用矩阵

| 文件 | 当前引用 | 角色 |
| --- | --- | --- |
| `requirements.txt` | `garmin-fit-sdk==21.208.0` | 安装需求 |
| `constraints.txt` | `garmin-fit-sdk==21.208.0` | 打包约束 |
| `packaging_diagnostics.py` | `GARMIN_FIT_SDK_EXPECTED_VERSION = "21.208.0"` | 当前最佳唯一版本源候选 |
| `scripts/check_python312_runtime.py` | 读取 `GARMIN_FIT_SDK_EXPECTED_VERSION` | runtime gate |
| `tests/test_python312_runtime_check.py` | 读取 `GARMIN_FIT_SDK_EXPECTED_VERSION` | 测试断言已收敛 |
| `tests/test_packaging_diagnostics.py` | 读取 `GARMIN_FIT_SDK_EXPECTED_VERSION` | 测试断言已收敛 |
| `docs/打包前必读.md` | `garmin-fit-sdk == 21.208.0` | 打包文档 |
| `docs/V2.0_macOS打包契约摘要.md` | `garmin-fit-sdk==21.208.0` | 发布契约 |
| `.github/workflows/package-on-tag.yml` | 通过安装脚本和 runtime gate 间接消费锁定版本 | tag 打包入口 |

## 4. 当前自动化边界

当前 `.github/workflows` 仅发现 tag 打包 workflow。未发现 Dependabot、Renovate、定时 PyPI 检查或 `garmin-fit-sdk` 自动升级 PR 机制。

## 5. 唯一版本源候选

建议继续使用 `packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION` 作为唯一版本源，并在后续任务中让锁文件、测试和文档围绕该值进行同步校验。

若后续实现证明独立版本契约模块更清晰，必须先更新任务清单和交付手册。

## 6. 基线验证

本报告创建后，GFSDK-00 需运行：

```bash
git status --short
rg -n "garmin-fit-sdk|GARMIN_FIT_SDK_EXPECTED_VERSION|garmin_fit_sdk" \
  requirements.txt constraints.txt packaging_diagnostics.py scripts tests docs .github
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

验证结果记录在任务清单执行记录中。
