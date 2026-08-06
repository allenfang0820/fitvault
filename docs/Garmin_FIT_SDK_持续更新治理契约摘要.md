---
title: Garmin FIT SDK 持续更新治理契约摘要
version: v0.1
status: Active
type: Contract Summary
updated: 2026-08-06
source:
  - docs/Garmin_FIT_SDK_持续更新治理交付手册.md
  - docs/Garmin_FIT_SDK_持续更新治理任务清单.md
---

# Garmin FIT SDK 持续更新治理契约摘要

## 1. 目标

建立 `garmin-fit-sdk` 的持续更新治理机制：自动发现新版本，受控生成升级变更，经过回归和人工审核后进入发布基线。

本契约不改变 FIT 解析业务语义。

## 2. 不可改变的契约

1. 发布和打包环境继续使用精确锁版本。
2. 不使用 `>=`、无上限范围或运行时自动安装替代版本治理。
3. 新版本只能通过独立升级 PR 进入主干。
4. 自动化只负责发现、同步和验证，不直接绕过审核发布。
5. 每次升级只处理 `garmin-fit-sdk`，不得混入其他依赖升级。
6. 不读取、上传或提交真实用户 FIT、账号、token、Cookie 或本机隐私路径。
7. 不修改 `fit_engine.py`、`main.py`、`metrics_resolver.py` 的运动业务语义；如新 SDK 暴露解析差异，另立 FIT 解析兼容任务。

## 3. 版本源契约

当前推荐的唯一版本源是 `packaging_diagnostics.py` 中的
`GARMIN_FIT_SDK_EXPECTED_VERSION`。

`requirements.txt`、`constraints.txt`、runtime gate、打包诊断、测试和文档必须与唯一版本源一致。任一锁点漂移都应被测试或诊断发现。

当前同步脚本为 `scripts/sync_garmin_fit_sdk_contract.py`，受控同步目标为：

- `requirements.txt`
- `constraints.txt`
- `docs/打包前必读.md`
- `docs/V2.0_macOS打包契约摘要.md`
- `docs/V2.0_Windows打包继续审查清单.md`

## 4. 更新流程契约

目标流程：

```text
PyPI stable release
  -> read-only update check
  -> isolated garmin-fit-sdk upgrade PR
  -> version contract sync
  -> dependency / FIT / runtime / packaging gates
  -> human review
  -> merge into release baseline
```

网络检查失败不得被解释为“没有更新”。

当前只读发现脚本为 `scripts/check_garmin_fit_sdk_update.py`。它只访问 PyPI
公共 JSON 元数据，输出 `current_version`、`latest_stable_version`、
`update_available`、`checked_at` 和错误状态。

## 5. 回归契约

升级 PR 至少必须验证：

- `garmin-fit-sdk` 版本契约同步。
- `garmin_fit_sdk` 可 import。
- `scripts/check_python312_runtime.py` 通过。
- `python -m packaging_diagnostics` 通过。
- `import main` 后 `garmin_fit_sdk` 与 `fitparse` 仍保持懒加载。
- FIT parser / sync 聚焦测试没有未经记录的行为变化。

## 6. 回滚契约

升级失败时退回最后稳定版本，并记录失败类型：

- 最后稳定版本优先读取当前发布基线的
  `packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION`，自动升级 PR 正文的
  `Current` 字段作为该 PR 的回滚锚点。
- 安装失败。
- import 失败。
- 解析回归。
- runtime gate 失败。
- 打包失败。

失败版本不得进入发布基线。

回滚只能通过 `scripts/bump_garmin_fit_sdk_contract.py --version <last-stable-version>`
恢复版本源和受控同步目标；不得在回滚 PR 中混入 FIT 解析逻辑、活动命名、UI 文案或其他依赖变更。

## 7. 执行门禁

每个任务开始前必须确认：

- 当前交付手册、任务清单和本契约摘要一致。
- 当前工作区脏改动已识别且不会被覆盖。
- 当前任务的允许改动文件与实际改动一致。
- 聚焦验证和 diff review 通过后才进入下一任务。
