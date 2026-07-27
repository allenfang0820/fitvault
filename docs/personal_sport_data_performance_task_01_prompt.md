---
title: Task 01 工程级提示词 - 个人运动数据性能基线与契约摘要
version: v0.1.0
status: Ready
type: Engineering Task Prompt
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
---

# Task 01 工程级提示词：性能基线与埋点补齐

你在本地项目 `/Users/fanglei/应用开发/AI track` 执行“个人运动数据性能优化”的 Task 01：性能基线与埋点补齐。

不要创建新分支，不要创建 worktree。当前 worktree 很脏，必须保护已有改动，不得 revert、覆盖、格式化无关文件。除本任务允许文件外，不改业务代码。

## 1. 任务目标

本任务不是直接做性能优化，而是为后续优化建立工程基线：

1. 深度阅读交付手册、任务清单和项目契约，形成可复用契约摘要。
2. 补齐活动列表、活动概览、运动复盘三段路径的 API 与前端分段耗时埋点。
3. 建立可重复的 API 微基准或测试入口，记录冷态、热态、payload 大小、后端耗时、pywebview 往返和前端渲染耗时。
4. 不改变当前业务语义，不优化 SQL，不拆 API，不做缓存，不降采样曲线。

## 2. 启动前硬门禁

先执行并记录：

```bash
git status --short
```

然后阅读当前任务允许涉及文件的已有 diff：

```bash
git diff -- main.py track.html docs/personal_sport_data_performance_optimization_plan.md docs/personal_sport_data_performance_task_list.md docs/js_api_contract.json docs/field_contract_matrix.md
```

如果发现待修改区域已有用户或其他 agent 的未提交改动，必须先理解这些改动，再以最小增量叠加；不能回退、重排或格式化它们。

## 3. 必须全文深度阅读的文档

首次执行 Task 01 时必须全文阅读以下文档，不允许只读摘要：

- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/js_api_contract.json`
- `docs/field_contract_matrix.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/运动详情页多运动升级开发交付手册.md`
- `docs/fatigue_review_environment_factors_contract_summary.md`

阅读目标不是背诵文档，而是抽取本任务必须遵守的契约：

- pywebview API 统一 envelope：`{ok, code, msg, data, traceId}` 及兼容字段。
- `get_activity_list` / `get_sport_hub_activity_page` 的分页、过滤、排序、列表字段契约。
- `get_activity_detail` 的活动详情字段、字段可追溯、后端真理源和前端消费边界。
- `get_fatigue_review` 的 snapshot 白名单、曲线权威来源、前端零推断、AI/前端只消费后端事实的边界。
- 复盘曲线、事件、环境、骑行解释信号等字段不得由前端从 DOM/ECharts/points/raw records 补算。
- `docs/js_api_contract.json` 新增或变更 API 字段时必须同步更新。
- UI 字段必须满足 `UI -> DB -> Resolver -> FIT SDK` 可追溯原则。
- 性能埋点不得把大 payload、原始轨迹点、raw records、敏感配置或调试 diff 暴露给前端/AI/日志。

## 4. 必须产出的契约摘要

新增或更新：

```text
docs/personal_sport_data_performance_contract_summary.md
```

摘要必须包含：

- 本轮阅读清单和阅读时间。
- 当前任务编号：Task 01。
- 个人运动数据性能优化的总边界。
- API envelope 契约。
- 活动列表契约。
- 活动概览契约。
- 运动复盘契约。
- 前端零推断与数据真实性契约。
- 埋点与日志安全契约。
- dirty worktree 保护规则。
- Task 01 允许修改文件和禁止修改文件。
- 后续 Task 02-08 的摘要刷新规则。
- 重要偏离触发条件。
- 最近刷新记录。

后续任务的摘要刷新规则必须写清楚：

```text
从 Task 02 开始，每个任务开始前必须先阅读 docs/personal_sport_data_performance_contract_summary.md、任务清单中的当前任务段落，以及当前任务直接相关的代码/测试/契约文件，并更新“最近刷新记录”。

如果执行中遇到重要偏离，必须暂停当前修改，重新全文阅读相关原始契约文档，再继续。
```

重要偏离至少包括：

- `docs/js_api_contract.json` 与优化方案、任务清单、契约摘要不一致。
- 当前代码字段名、返回 shape、snapshot 白名单或测试期望与摘要不一致。
- 需要新增、删除或重命名 pywebview API。
- 需要改变 `get_activity_list`、`get_activity_detail`、`get_fatigue_review` 的业务字段语义。
- 前端需要从 DOM、ECharts、points、raw records、curves 或标题/设备/天气卡补算事实。
- 埋点需要记录大轨迹、原始 points、raw records、敏感配置或用户隐私数据。
- 为了埋点必须触碰 Garmin/COROS 导入、AI 质量、Records Center、打包或其他非目标链路。
- 测试失败显示不是断言同步问题，而是合同与实现边界冲突。

## 5. 允许修改文件

本任务允许修改：

- `main.py`
- `track.html`
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- 可新增聚焦测试或测量脚本，例如：
  - `tests/test_personal_sport_data_performance_contract.py`
  - `scripts/benchmark_personal_sport_data.py`

仅当实际新增或变更 API 字段契约时，允许同步修改：

- `docs/js_api_contract.json`
- `tests/test_response_envelope_contract.py`

## 6. 禁止修改范围

本任务禁止：

- 优化 `profile_backend.get_activity_list_filtered()` 的 SQL。
- 拆分 `get_activity_detail` 或新增 summary API。
- 为复盘增加缓存。
- 为复盘曲线做降采样或新增全量曲线 API。
- 改 Garmin/COROS 同步、导入、去重、来源账本。
- 改 AI prompt、LLM 配置、embedding、Records Center、打包流程。
- 修改活动事实字段、轨迹原始数据、训练指标含义。
- 清理、压缩、迁移真实用户数据库。

如果发现必须触碰禁止范围，停止实现并更新契约摘要的“偏离记录”，不要擅自扩大任务。

## 7. 实现要求

### 7.1 后端 API 埋点

为以下 API 增加后端耗时记录或返回字段：

- `get_sport_hub_activity_page(page, page_size, filter_type, title_keyword)`
- `get_activity_list(page, page_size, filter_type, title_keyword)`
- `get_activity_detail(activity_id)`
- `get_fatigue_review(activity_id)`

要求：

- 优先把耗时放在 `data.api_elapsed_ms` 或等价非破坏性诊断字段中。
- 保持统一 envelope，不改变 `ok/code/msg/traceId`。
- 异常返回也要保留原错误语义。
- 不把大对象复制到日志里，不输出轨迹 points/raw records。
- 如果字段加入 `docs/js_api_contract.json`，同步补测试。

### 7.2 前端分段埋点

在 `track.html` 中为三段用户路径加入 `performance.now()` 分段：

- 活动列表：发起请求、API 返回、列表数据整理、DOM 渲染完成。
- 活动概览：打开弹窗、详情 API roundtrip、数据整理、首屏渲染完成、照片/缩略图相关耗时。
- 运动复盘：tab 切换、复盘 API roundtrip、数据整理、面板渲染、ECharts setOption 完成。

要求：

- 埋点日志可控，避免高频噪音。
- 日志只记录耗时、数量、payload 字节数、活动 id 等最小诊断字段。
- 不把完整 curves、points、records、AI snapshot 打进 console。
- 不改变 UI 文案、布局和交互。

### 7.3 微基准

新增可重复运行的 API 微基准脚本或测试入口，至少覆盖：

```text
get_sport_hub_activity_page(1, 10, 'all', '')
get_activity_list(1, 20, 'all', '')
get_activity_detail(activity_id)
get_fatigue_review(activity_id)
```

要求：

- 支持记录冷态首次耗时和热态连续 3 次耗时。
- 记录 payload 字节数。
- 允许用当前数据库里的最近活动和一条长活动做样本。
- 基准脚本不得修改数据库。

## 8. 验证命令

至少运行：

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_response_envelope_contract.py -q
.venv312/bin/python -m py_compile main.py
git diff --check
```

如果新增测试或脚本，补充运行对应命令，例如：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python scripts/benchmark_personal_sport_data.py
```

如果因为当前 dirty worktree 或既有失败无法完整运行，必须在最终报告中说明具体命令、失败位置和是否与本任务改动相关。

## 9. 完成门槛

本任务完成时必须满足：

- 已生成 `docs/personal_sport_data_performance_contract_summary.md`。
- 契约摘要包含后续 Task 02-08 的刷新规则和重要偏离触发条件。
- 后端 API 埋点不破坏 envelope。
- 前端分段埋点不改变 UI 业务行为。
- 已记录列表、概览、复盘的冷态/热态基线或说明无法测量的具体原因。
- 已记录 payload 大小。
- 已运行验证命令或清楚说明未运行原因。
- 最终回复列出修改文件、验证结果、残余风险和 Task 02 建议启动点。

## 10. Task 02 交接提示

Task 02 是“活动列表轻量分页修复”。启动 Task 02 前必须：

1. 阅读并刷新 `docs/personal_sport_data_performance_contract_summary.md`。
2. 阅读任务清单中 Task 02 段落。
3. 阅读 `profile_backend.get_activity_list_filtered()`、`main.py::get_activity_list()`、`main.py::get_sport_hub_activity_page()`、`track.html::loadSportHubActivityList()` 的当前实现和 diff。
4. 如果列表字段、分页、排序、`has_track`、去重或 API envelope 与摘要不一致，重新全文阅读相关契约后再改代码。
