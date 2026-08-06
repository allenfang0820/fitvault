---
title: Garmin FIT SDK 持续更新治理任务清单
version: v0.1
status: Complete
type: Ordered Engineering Task List
updated: 2026-08-06
source:
  - docs/Garmin_FIT_SDK_持续更新治理交付手册.md
  - docs/Garmin_FIT_SDK_持续更新治理契约摘要.md
  - requirements.txt
  - constraints.txt
  - packaging_diagnostics.py
  - scripts/check_python312_runtime.py
  - tests/test_python312_runtime_check.py
  - tests/test_packaging_diagnostics.py
---

# Garmin FIT SDK 持续更新治理任务清单

本文档把 `docs/Garmin_FIT_SDK_持续更新治理交付手册.md` 拆为可独立执行、可验证、可回滚的工程任务。

本轮目标是建立 `garmin-fit-sdk` 的持续更新治理机制，不是把依赖改成运行时自动漂移版本。

## 0. 执行规则

- 唯一上位基线是 `docs/Garmin_FIT_SDK_持续更新治理交付手册.md`。
- 每个任务开始前执行 `git status --short`，阅读将要修改文件的当前 diff。
- 不得 stash、reset、clean、覆盖、格式化或提交无关改动。
- 每个任务只修改“允许改动文件”列出的范围；必须扩大范围时，先更新本清单和交付手册。
- 每个任务完成后运行聚焦测试、`git diff --check`，并记录未能自动验证的项目。
- 生产/打包环境继续使用精确锁版本，不使用 `>=` 或无上限范围替代版本治理。
- 每次升级只处理 `garmin-fit-sdk`，不得顺带升级 `garminconnect`、`curl_cffi` 或其他无关依赖。
- 不把真实用户 FIT、账号信息、token、Cookie 或本机绝对路径上传到 CI、PR 或测试 fixture。
- 不修改 `fit_engine.py`、`main.py`、`metrics_resolver.py` 的运动业务语义；SDK 升级导致解析行为变化时，另立 FIT 解析修复任务。

## 1. 任务总览

| 顺序 | 任务 | 性质 | 优先级 | 前置 | 状态 | 主要交付物 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | GFSDK-00 基线审计与版本契约冻结 | 审计 / 契约 | P0 | 无 | `Done` | 版本来源矩阵、当前门禁基线 |
| 1 | GFSDK-01 单一版本源与锁文件同步 | 依赖治理 | P0 | GFSDK-00 | `Done` | 单点版本源、同步校验 |
| 2 | GFSDK-02 PyPI 新版本发现脚本 | 自动化诊断 | P0 | GFSDK-01 | `Done` | 可测试的版本检查脚本 |
| 3 | GFSDK-03 定时检查与自动升级 PR | CI / 维护流程 | P1 | GFSDK-02 | `Done` | GitHub Actions 定时工作流 |
| 4 | GFSDK-04 升级 PR 回归与跨平台门禁 | 测试 / 发布 | P0 | GFSDK-01, GFSDK-02 | `Done` | 依赖、解析、打包回归矩阵 |
| 5 | GFSDK-05 回滚、失败记录与文档收口 | 运维 / 发布 | P1 | GFSDK-04 | `Done` | 回滚流程、失败报告、最终文档 |

依赖关系：

```text
GFSDK-00
   |
   v
GFSDK-01 ---> GFSDK-02 ---> GFSDK-03
   |             |
   +-----------> GFSDK-04 ---> GFSDK-05
```

## 2. 全局非目标

- 不在应用启动时联网检查或安装 SDK。
- 不允许用户运行应用时自动替换 FIT 解析依赖。
- 不把最新版本直接写入主干后再补测试。
- 不为了通过旧测试而回退既有 FIT 字段、设备识别或活动标题语义。
- 不将真实用户数据作为自动升级 PR 的测试输入。
- 不把依赖升级机制扩展成全量 Python 依赖升级机器人。

---

## 3. GFSDK-00：基线审计与版本契约冻结

优先级：P0  
性质：审计 / 契约 / 不改生产行为  
前置：无

### 目标

冻结当前 `garmin-fit-sdk` 的版本来源、安装方式、运行时闸门、测试断言、打包文档和 GitHub Actions 边界，确认后续升级不会遗漏锁点。

### 允许改动文件

- 本任务清单。
- 必要时新增基线审计报告。
- 不修改业务代码和依赖版本。

### 必做

- 记录当前工作区状态和当前锁定版本。
- 建立版本引用矩阵，至少覆盖：
  `requirements.txt`、`constraints.txt`、`packaging_diagnostics.py`、
  `scripts/check_python312_runtime.py`、相关测试和打包文档。
- 确认当前 tag 打包 workflow 的依赖安装和 runtime gate 入口。
- 确认当前是否存在定时依赖检查、Dependabot 或 Renovate。
- 记录当前基线测试结果，不把“已安装”误认为“已验证兼容”。

### 验证

```bash
git status --short
rg -n "garmin-fit-sdk|GARMIN_FIT_SDK_EXPECTED_VERSION|garmin_fit_sdk" \
  requirements.txt constraints.txt packaging_diagnostics.py scripts tests docs .github
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

### 完成标准

- 版本引用矩阵完整。
- 已明确唯一版本源候选和所有同步目标。
- 已确认当前没有现成的定时依赖更新机制。
- 本任务不改变现有运行行为。

### 完成记录

- 2026-08-06：创建并冻结 `docs/Garmin_FIT_SDK_持续更新治理契约摘要.md`、
  `docs/Garmin_FIT_SDK_持续更新治理基线审计报告.md`。
- 2026-08-06：验证 `git status --short`、`rg -n`、`.venv312/bin/python scripts/check_python312_runtime.py`、
  `.venv312/bin/python -m packaging_diagnostics`、`git diff --check` 通过。
- 2026-08-06：确认当前仓库未发现 Dependabot、Renovate 或定时 PyPI 检查机制；当前锁定
  `garmin-fit-sdk==21.208.0`。

---

## 4. GFSDK-01：单一版本源与锁文件同步

优先级：P0  
性质：依赖契约 / 静态同步  
前置：GFSDK-00

### 目标

让 `garmin-fit-sdk` 的版本只需要修改一个版本源，其余锁文件、诊断、测试和文档可以被同步或确定性校验。

### 允许改动文件

- `packaging_diagnostics.py`，或新增极小的版本契约模块。
- `requirements.txt`
- `constraints.txt`
- `scripts/check_python312_runtime.py`
- `tests/test_python312_runtime_check.py`
- `tests/test_packaging_diagnostics.py`
- `docs/打包前必读.md`
- `docs/V2.0_macOS打包契约摘要.md`
- `docs/V2.0_Windows打包继续审查清单.md`
- 必要的版本同步脚本。

### 设计决定

- 优先复用现有 `packaging_diagnostics.py` 的
  `GARMIN_FIT_SDK_EXPECTED_VERSION` 作为唯一版本源。
- 只有当跨脚本、CI 和静态文件同步确实无法清晰实现时，才新增独立版本契约模块。
- 测试不得再把某个具体 SDK 版本作为散落的硬编码事实；应读取同一版本源并验证锁文件一致。
- `requirements.txt` 和 `constraints.txt` 仍然保留精确版本锁定。

### 必做

- 定义版本源的读取方式。
- 增加锁文件一致性检查。
- 检查版本源、requirements、constraints、runtime gate 和打包文档是否一致。
- 保持现有 `garminconnect`、`curl_cffi` 等依赖契约不变。

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_python312_runtime_check.py \
  tests/test_packaging_diagnostics.py
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

### 完成标准

- 版本升级不再需要人工猜测遗漏文件。
- 任意一个锁点漂移都会被测试或诊断明确指出。
- 发布前仍能阻断未安装、错版本和无法 import 的环境。

### 完成记录

- 2026-08-06：新增 `scripts/sync_garmin_fit_sdk_contract.py`，以
  `packaging_diagnostics.py::GARMIN_FIT_SDK_EXPECTED_VERSION` 为唯一版本源检查
  `requirements.txt`、`constraints.txt`、`docs/打包前必读.md`、
  `docs/V2.0_macOS打包契约摘要.md`、`docs/V2.0_Windows打包继续审查清单.md`。
- 2026-08-06：新增 `tests/test_garmin_fit_sdk_contract_sync.py`，并将
  `tests/test_python312_runtime_check.py`、`tests/test_packaging_diagnostics.py`
  中的 `garmin-fit-sdk` 版本断言收敛到同一版本源。
- 2026-08-06：验证 `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_garmin_fit_sdk_contract_sync.py tests/test_python312_runtime_check.py tests/test_packaging_diagnostics.py`
  为 `26 passed`；`.venv312/bin/python scripts/sync_garmin_fit_sdk_contract.py --json`、
  `.venv312/bin/python scripts/check_python312_runtime.py`、`.venv312/bin/python -m packaging_diagnostics`、
  `git diff --check` 通过。

---

## 5. GFSDK-02：PyPI 新版本发现脚本

优先级：P0  
性质：自动化诊断 / 网络边界  
前置：GFSDK-01

### 目标

增加一个可在本地和 CI 使用的只读检查脚本，判断 PyPI 是否存在比当前锁定版本更新的稳定版本。

### 允许改动文件

- 新增 `scripts/check_garmin_fit_sdk_update.py`。
- 新增对应测试。
- 必要时更新本任务清单和交付手册。

### 输出契约

脚本至少输出：

```json
{
  "ok": true,
  "package": "garmin-fit-sdk",
  "current_version": "x.y.z",
  "latest_stable_version": "x.y.z",
  "update_available": false,
  "source": "pypi",
  "checked_at": "ISO-8601 timestamp"
}
```

### 必做

- 只读取 PyPI 公共元数据，不读取账号、token 或本机用户数据。
- 忽略 pre-release、dev release 和无法解析的版本。
- 正确区分“没有更新”“有更新”“网络失败”“响应格式异常”。
- 支持机器可读 JSON 输出。
- 测试不得依赖实时网络；通过注入响应或本地 fixture 验证解析。
- 网络失败时返回明确的失败状态，不把失败误报为“没有更新”。

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_garmin_fit_sdk_update_check.py
.venv312/bin/python scripts/check_garmin_fit_sdk_update.py --json
git diff --check
```

### 完成标准

- 本地可以执行只读版本检查。
- 测试覆盖无更新、有更新、pre-release、网络失败和坏响应。
- 检查脚本不会修改依赖文件、数据库或用户数据。

### 完成记录

- 2026-08-06：新增 `scripts/check_garmin_fit_sdk_update.py`，输出机器可读 JSON，
  网络失败或坏响应返回 `ok: false`，不会被解释为“没有更新”。
- 2026-08-06：新增 `tests/test_garmin_fit_sdk_update_check.py`，覆盖有更新、无更新、
  pre-release 忽略、网络失败、坏响应和 CLI JSON 输出。
- 2026-08-06：验证 `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_garmin_fit_sdk_update_check.py`
  为 `5 passed`；`.venv312/bin/python scripts/check_garmin_fit_sdk_update.py --json`
  成功返回 `current_version=21.208.0`、`latest_stable_version=21.212.0`、
  `update_available=true`；`git diff --check` 通过。

---

## 6. GFSDK-03：定时检查与自动升级 PR

优先级：P1  
性质：GitHub Actions / 维护自动化  
前置：GFSDK-02

### 目标

让新版本在固定周期内被发现，并以独立、可审查、可回滚的 PR 进入仓库。

### 允许改动文件

- 新增 `.github/workflows/garmin-fit-sdk-update.yml`。
- 必要的版本同步脚本。
- 必要的 PR 模板或维护说明。
- 不修改现有 tag 打包 workflow 的产品发布语义。

### 必做

- 定时执行版本检查，建议每周一次。
- 支持手工 `workflow_dispatch`，便于发现版本后立即复查。
- 检测到新版本时才创建 PR；没有更新时不得制造空 PR。
- PR 标题、正文和变更范围明确标注 `garmin-fit-sdk` 版本变化。
- 每个 PR 只升级一个直接依赖。
- PR 必须自动触发现有测试和 runtime gate。
- 工作流权限遵循最小权限原则，不读取或输出任何敏感凭据。

### 完成标准

- 新版本出现后，在固定周期内能自动发现。
- 自动 PR 不混入无关文件和无关依赖。
- 工作流失败时能区分网络失败、同步失败和测试失败。
- 现有 tag 打包工作流保持原有触发和发布边界。

### 完成记录

- 2026-08-06：新增 `.github/workflows/garmin-fit-sdk-update.yml`，每周一执行，也支持
  `workflow_dispatch`；检测到 PyPI 稳定新版本时才 bump 合同文件并创建
  `codex/garmin-fit-sdk-<version>` 分支的独立 PR。
- 2026-08-06：新增 `scripts/bump_garmin_fit_sdk_contract.py`，只接受稳定数字版本，
  只更新 `packaging_diagnostics.py` 的版本源和受控同步目标。
- 2026-08-06：新增 `tests/test_garmin_fit_sdk_update_workflow.py`，验证定时检查、手动触发、
  最小权限、同步脚本、runtime gate、packaging diagnostics、FIT parser/sync 聚焦测试和
  PR 分支范围。
- 2026-08-06：验证 `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_garmin_fit_sdk_contract_sync.py tests/test_garmin_fit_sdk_update_check.py tests/test_garmin_fit_sdk_update_workflow.py tests/test_python312_runtime_check.py tests/test_packaging_diagnostics.py`
  为 `33 passed`；`scripts/sync_garmin_fit_sdk_contract.py --json`、
  `scripts/check_garmin_fit_sdk_update.py --json`、`git diff --check` 通过。

---

## 7. GFSDK-04：升级 PR 回归与跨平台门禁

优先级：P0  
性质：兼容性测试 / 发布门禁  
前置：GFSDK-01、GFSDK-02

### 目标

证明新 SDK 版本不仅能安装，而且不会破坏 FIT 导入、懒加载、设备解析和打包诊断。

### 允许改动文件

- `tests/test_python312_runtime_check.py`
- `tests/test_packaging_diagnostics.py`
- 新增或更新 FIT SDK 兼容性聚焦测试。
- 必要的脱敏 FIT fixture。
- CI workflow 中的测试步骤。

### 必做门禁

- 版本契约同步测试。
- `garmin_fit_sdk` import smoke。
- `scripts/check_python312_runtime.py`。
- `python -m packaging_diagnostics`。
- `import main` 后 `garmin_fit_sdk` 和 `fitparse` 仍保持懒加载。
- 现有 FIT parser / FIT sync 聚焦回归。
- macOS 和 Windows 的 Python 3.12 runtime gate。
- 至少一次真实发布流程的打包前诊断。

### FIT 样本边界

- 优先使用已有脱敏 fixture。
- 如必须使用真实设备 FIT，只在本地临时副本验证，不提交原始文件。
- 至少覆盖一个 Garmin FIT 解析样本和一个非 Garmin 设备 FIT 样本。
- 若升级改变了字段解析结果，必须把变化归类为兼容性变化，不能静默更新测试期望。

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_python312_runtime_check.py \
  tests/test_packaging_diagnostics.py \
  tests/test_fit_parser.py \
  tests/test_fit_sync.py
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

### 完成标准

- 新版本安装、import、runtime gate 和打包诊断全部通过。
- 既有 FIT 导入行为没有未经记录的变化。
- 跨平台门禁结果已记录，不能只凭单机测试标记完成。

### 完成记录

- 2026-08-06：确认 `.github/workflows/package-on-tag.yml` 中 macOS arm64、macOS x86_64
  和 Windows x64 打包流程均在构建前运行 Python 3.12 runtime gate 和
  `packaging_diagnostics`。
- 2026-08-06：扩展 `tests/test_garmin_fit_sdk_update_workflow.py`，防止后续移除 macOS /
  Windows 发布打包 workflow 中的 runtime gate 和 packaging diagnostics。
- 2026-08-06：验证 `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_python312_runtime_check.py tests/test_packaging_diagnostics.py tests/test_fit_parser.py tests/test_fit_sync.py`
  为 `204 passed, 3 skipped, 17 subtests passed`。
- 2026-08-06：验证补充断言后
  `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_garmin_fit_sdk_update_workflow.py tests/test_python312_runtime_check.py tests/test_packaging_diagnostics.py tests/test_fit_parser.py tests/test_fit_sync.py`
  为 `206 passed, 3 skipped, 17 subtests passed`。
- 2026-08-06：`.venv312/bin/python scripts/check_python312_runtime.py` 通过，确认
  `garmin-fit-sdk==21.208.0` 已安装且 `garmin_fit_sdk`、`fitparse` 在 `import main`
  后仍保持懒加载；`.venv312/bin/python -m packaging_diagnostics` 和 `git diff --check` 通过。

---

## 8. GFSDK-05：回滚、失败记录与文档收口

优先级：P1  
性质：可靠性 / 发布流程 / 文档  
前置：GFSDK-04

### 目标

确保升级失败时可以快速退回最后一个稳定版本，并让下一次升级拥有可追溯的失败证据。

### 允许改动文件

- `docs/Garmin_FIT_SDK_持续更新治理交付手册.md`
- 本任务清单。
- 打包前依赖文档。
- 必要的升级失败报告。

### 必做

- 明确“最后稳定版本”的记录位置。
- 明确回滚只需恢复哪些文件和版本源。
- 记录升级失败类型：安装失败、import 失败、解析回归、runtime gate 失败、打包失败。
- 规定失败版本不得进入发布基线。
- 文档说明升级 PR、测试证据和回滚记录之间的对应关系。

### 验证

- 人工演练一次从候选版本退回上一个稳定版本。
- 验证回滚后：
  `scripts/check_python312_runtime.py`、`packaging_diagnostics` 和聚焦 FIT 测试恢复通过。
- `git diff --check` 通过。

### 完成标准

- 回滚步骤不依赖重新猜测版本或手工搜索历史提交。
- 失败版本、失败原因和最后稳定版本都有记录。
- 文档、任务清单和实际工作流一致。

### 完成记录

- 2026-08-06：更新 `docs/Garmin_FIT_SDK_持续更新治理交付手册.md`，明确最后稳定版本读取顺序、
  回滚命令、回滚后必跑门禁和失败记录模板。
- 2026-08-06：更新 `docs/Garmin_FIT_SDK_持续更新治理契约摘要.md`，明确自动升级 PR
  正文 `Current` 字段是该 PR 的回滚锚点，且回滚不得混入 FIT 解析逻辑、活动命名、UI 文案或其他依赖变更。
- 2026-08-06：更新 `.github/workflows/garmin-fit-sdk-update.yml`，在自动升级 PR 正文中写入
  `Rollback anchor` 和可直接执行的回滚命令。
- 2026-08-06：新增 `tests/test_garmin_fit_sdk_rollback_docs.py`，锁定回滚文档、契约摘要和
  PR 正文中的回滚锚点。
- 2026-08-06：在临时目录 `/tmp/fitvault-gfsdk-rollback-71355` 演练
  `21.999.0 -> 21.208.0` 回滚，回滚后
  `scripts/sync_garmin_fit_sdk_contract.py --root <temp> --json` 返回 `ok: true`。
- 2026-08-06：验证 `PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_garmin_fit_sdk_rollback_docs.py tests/test_garmin_fit_sdk_update_workflow.py tests/test_garmin_fit_sdk_contract_sync.py`
  为 `7 passed`；`git diff --check` 通过。

---

## 9. 最终验收

最终验收必须证明以下完整链路：

```text
PyPI 发布新版本
  -> 定时任务发现
  -> 自动生成独立升级 PR
  -> 版本契约同步
  -> 依赖 / FIT / runtime / 打包回归
  -> 人工审核合并
  -> tag 发布继续使用精确锁版本
  -> 失败时可回滚
```

推荐命令：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_garmin_fit_sdk_update_check.py \
  tests/test_python312_runtime_check.py \
  tests/test_packaging_diagnostics.py \
  tests/test_fit_parser.py \
  tests/test_fit_sync.py
.venv312/bin/python scripts/check_python312_runtime.py
.venv312/bin/python -m packaging_diagnostics
git diff --check
```

最终完成标准：

- 所有任务状态均为 `Done` 或有明确的 `Blocked` 原因。
- 版本更新机制可在没有人工盯守的情况下发现新版本。
- 生产发布仍然可复现，不依赖实时 PyPI 状态。
- 升级和回滚均有自动化证据与文档记录。

## 10. 执行记录

- 文档创建时间：2026-08-06
- 当前状态：`Complete`
