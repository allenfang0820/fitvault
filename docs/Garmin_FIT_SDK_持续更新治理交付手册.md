---
title: Garmin FIT SDK 持续更新治理交付手册
version: v0.1
status: Active
type: Development Delivery Manual
updated: 2026-08-06
scope: Garmin FIT SDK 依赖更新治理、版本同步、自动发现、回归门禁与回滚策略
source:
  - docs/Garmin_FIT_SDK_持续更新治理契约摘要.md
  - docs/Garmin_FIT_SDK_持续更新治理任务清单.md
  - requirements.txt
  - constraints.txt
  - packaging_diagnostics.py
  - scripts/check_python312_runtime.py
  - scripts/install_packaging_deps.sh
  - scripts/install_packaging_deps.ps1
  - tests/test_python312_runtime_check.py
  - tests/test_packaging_diagnostics.py
  - docs/打包前必读.md
  - docs/V2.0_macOS打包契约摘要.md
---

# Garmin FIT SDK 持续更新治理交付手册

## 0. 文档用途

本文冻结 `garmin-fit-sdk` 的成熟更新路径，目标不是放开版本，而是让版本更新可发现、可审查、可回滚、可验证。

本文用于后续改造、自动化和发布门禁设计。具体实施顺序以
`docs/Garmin_FIT_SDK_持续更新治理任务清单.md` 为准。

## 1. 问题定义

当前仓库对 `garmin-fit-sdk` 采用精确锁定，但版本值分散在多处，容易出现以下问题：

- 新版本已发布，但仓库长期停留在旧版本。
- 版本更新需要人手同时改多个文件，容易遗漏。
- 测试、打包诊断、运行时闸门、文档之间可能短暂不一致。
- 一旦新版本有兼容性变化，缺少统一的升级入口和回滚策略。

## 2. 成熟路径

成熟做法不是“永远自动升”，而是“自动发现更新，人工批准合并，发布仍然受控”。

核心原则只有四条：

- 生产/打包环境仍然锁定精确版本。
- 版本源只保留一处，其他文件同步生成或校验。
- 新版本通过独立 PR 进入，不直接在主干上漂移。
- 每次升级都必须跑同一组回归门禁。

## 3. 目标架构

### 3.1 单一版本源

建议把 `garmin-fit-sdk` 的目标版本收敛为单一事实源，其他文件都从它同步。

可选实现方式有两种：

1. 继续以 `packaging_diagnostics.py` 中的版本常量作为唯一写入点。
2. 另建一个极小的版本契约文件，再由诊断脚本和测试读取。

无论选哪种，都要满足“版本只改一处，其他文件跟着同步”的要求。

### 3.2 自动发现

增加一个定时检查入口，定期查询 PyPI 上 `garmin-fit-sdk` 的最新稳定版本。

检测只负责回答三件事：

- 当前仓库锁定版本是什么。
- PyPI 最新稳定版本是什么。
- 两者是否一致。

检测不负责自动提交主干，也不负责绕过测试。

### 3.3 自动提 PR

检测到新版本后，由自动化生成一个小而专的升级 PR。

这个 PR 只能包含：

- 版本源更新。
- requirements / constraints 同步。
- 诊断脚本和运行时闸门同步。
- 必要的测试断言和文档同步。

不允许把其他无关依赖、UI 修正、FIT 解析逻辑一起塞进同一个升级 PR。

### 3.4 强制回归

升级 PR 必跑以下门禁：

- `scripts/check_python312_runtime.py`
- `python -m packaging_diagnostics`
- 现有依赖契约测试
- 基础 import smoke

如果 `garmin-fit-sdk` 影响 FIT 解析结果，再补一组最小 FIT 样本回归。

### 3.5 人工合并

自动化只负责发现和提出变更，最终合并仍需人工审核。

审核重点只有三个：

- 新版本是否真的比当前版本更新。
- 回归是否全绿。
- 版本更新是否没有外溢到无关模块。

## 4. 推荐实现面

如果进入实施阶段，建议改动面控制在以下文件：

- `requirements.txt`
- `constraints.txt`
- `packaging_diagnostics.py`
- `scripts/check_python312_runtime.py`
- `tests/test_python312_runtime_check.py`
- `tests/test_packaging_diagnostics.py`
- `docs/打包前必读.md`
- `docs/V2.0_macOS打包契约摘要.md`
- 新增一个 GitHub Actions 定时检查工作流
- 必要时新增一个很小的版本检查脚本

## 5. 更新流程

建议流程如下：

1. 定时任务查询 PyPI 最新稳定版。
2. 与仓库当前锁定版本比较。
3. 若有更新，自动创建升级 PR。
4. PR 内同步版本源、锁文件、诊断和文档。
5. 跑回归测试与运行时闸门。
6. 通过后合并。
7. 发布时继续沿用 tag 打包流程，不额外放开依赖。

## 6. 非目标

本手册不主张以下做法：

- 不把 `garmin-fit-sdk` 改成宽松范围依赖。
- 不在生产环境自动无审查升级。
- 不同时把 `garminconnect`、`curl_cffi` 等其他依赖一起混升，除非它们确实是同一个兼容修复。
- 不为了“能更新”而取消 runtime gate。
- 不在没有测试证据时把新版本直接写进发布基线。

## 7. 回滚策略

如果新版本出现解析异常、安装异常或打包异常，回滚方式必须简单明确：

- 退回到上一个稳定版本。
- 保留失败版本的诊断记录。
- 记录兼容性差异和触发场景。
- 新开修复 PR，而不是反复在主干上试错。

### 7.1 最后稳定版本的记录位置

最后稳定版本不靠临时记忆或手工翻历史确定，按以下顺序读取：

1. 当前发布基线中的 `packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION`。
2. 自动升级 PR 正文里的 `Current` 字段。
3. 最近一次成功 tag 打包产物对应的 `build_dependency_manifest.json`。

自动升级 PR 的 `Current` 字段就是该 PR 的回滚锚点；`Latest stable` 是候选版本，不得在门禁失败时进入发布基线。

### 7.2 回滚操作

如果候选版本失败，用上一稳定版本执行：

```bash
python scripts/bump_garmin_fit_sdk_contract.py --version "<last-stable-version>" --json
python scripts/sync_garmin_fit_sdk_contract.py --json
```

然后必须重新安装/校验打包环境，并至少运行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_garmin_fit_sdk_contract_sync.py \
  tests/test_garmin_fit_sdk_update_check.py \
  tests/test_garmin_fit_sdk_update_workflow.py \
  tests/test_python312_runtime_check.py \
  tests/test_packaging_diagnostics.py \
  tests/test_fit_parser.py \
  tests/test_fit_sync.py
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

回滚 PR 只能恢复 `garmin-fit-sdk` 版本源和受控同步目标，不得顺带调整 FIT 解析逻辑、活动命名、UI 文案或其他依赖。

### 7.3 失败记录模板

升级失败时，在升级 PR 或后续回滚 PR 中记录：

- 候选版本：
- 最后稳定版本：
- 失败类型：安装失败 / import 失败 / 解析回归 / runtime gate 失败 / 打包失败
- 触发门禁：
- 失败命令：
- 关键错误摘要：
- 是否影响真实用户数据：不得上传真实 FIT、账号、token、Cookie 或本机隐私路径
- 后续处理：回滚 / 新开 FIT 解析兼容任务 / 等待上游修复

## 8. 验收标准

这套治理方案算成熟，至少要满足：

- 新版本发布后，仓库能在固定周期内发现它。
- 发现后能自动生成升级 PR。
- 升级 PR 只改受控文件，不混入无关改动。
- 所有 runtime gate 和包装诊断保持绿色。
- 发布流程仍然可复现、可回滚。

## 9. 已落地链路

当前实现已按以下顺序落地：

1. 版本源收敛到 `packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION`。
2. `scripts/sync_garmin_fit_sdk_contract.py` 校验或同步锁文件与打包文档。
3. `scripts/check_garmin_fit_sdk_update.py` 只读检查 PyPI 最新稳定版本。
4. `.github/workflows/garmin-fit-sdk-update.yml` 定时发现新版本并创建独立升级 PR。
5. 升级 PR 运行版本契约、runtime、packaging diagnostics、FIT parser 和 FIT sync 门禁。
6. 自动升级 PR 正文写入 `Current` 回滚锚点和回滚命令。

## 10. 执行记录

- 文档创建时间：2026-08-06
- 当前状态：`Active`
- 2026-08-06：已完成 GFSDK-00 至 GFSDK-05，当前仓库仍锁定
  `garmin-fit-sdk==21.208.0`；PyPI 最新稳定版本检查到 `21.212.0`，自动升级机制会通过
  独立 PR 处理该候选版本。
