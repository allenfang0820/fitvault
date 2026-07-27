---
title: 活动同步性能与重复解析修复 Coding Agent 交接说明
version: v0.8.0
status: Implementation In Progress / Tasks 0-7 Completed
type: Coding Agent Handoff
updated: 2026-07-23
workspace: /Users/fanglei/应用开发/AI track
source:
  - docs/activity_sync_performance_fix_delivery_manual.md
  - docs/activity_sync_performance_fix_task_list.md
---

# 活动同步性能与重复解析修复 Coding Agent 交接说明

## 1. 当前结论

本次修复已完成基线审计、provider 候选契约、来源账本、候选导入、账本幂等、查重日志降噪、ACS 刷新收敛及手动 FIT/ZIP 来源账本接入。

已经完成：

- 根因诊断与当前代码基线复核。
- 修复范围、目标架构、数据契约和验收标准落盘。
- 将实施内容拆成任务 0-8 的有序清单。
- 之前一次未经清单确认的尝试性修改已经复原；当前来源账本和候选导入代码均来自后续已确认的任务 2、3。
- 任务 0 已完成：相关 dirty diff 已冻结，`tests/test_fit_sync.py` 基线 137 passed。
- 任务 1 已完成：Garmin/COROS 均提供向后兼容的统一 `candidates[]`。
- 任务 2 已完成：新增 `activity_source_files` schema、索引、查询和状态 upsert helper，5 个账本回归测试通过。
- 任务 3 已完成：Garmin/COROS 只导入本次 `candidates[]`，不再调用全目录同步。
- 任务 4 已完成：provider id/sha256 可在 parser 前跳过完成来源，pending/failed/孤儿来源可重试。
- 任务 5 已完成：查重 INFO 固定为开始/结果两条，逐候选详情降为 DEBUG；SQL 粗筛因兼容风险暂缓。
- 任务 6 已完成：仅真实 inserted/updated ids 触发一次批量 V3/ACS 刷新，零变化不刷新。
- 任务 7 已完成：手动 FIT/ZIP 保留原解析、过滤、标题与查重链路，新增 local sha256 解析前幂等和删除恢复。

尚未完成：

- 没有执行任务清单中的实现后测试和性能验收。

任务 0、1、2、3、4、5、6、7 为 `Completed`；任务 8 仍为 `Not Started`。新 agent 不得把手动导入回归完成误报为全部同步修复完成。

## 2. 必读文档

按以下顺序阅读：

1. `docs/activity_sync_performance_fix_delivery_manual.md`
2. `docs/activity_sync_performance_fix_task_list.md`
3. 本交接说明
4. 当前 `git status --short`
5. 待修改文件的现有 diff

交付手册是设计与验收基线；任务清单是唯一执行顺序。本交接说明只负责说明当前工作区状态和启动方式，不替代前两份文档。

## 3. 用户工作方式要求

本任务必须遵守以下协作要求：

- 不新开分支，直接使用当前本地项目环境。
- 当前 worktree 是 dirty 的，先保护已有修改。
- 未列出清晰任务清单并获得用户确认前，不开始业务代码修改。
- 实施时按任务 0、1、2……顺序推进，不跨任务大范围写代码。
- 每个任务开始前说明本任务目标、修改文件、明确不修改的范围和验证命令。
- 每个任务完成后立即运行聚焦测试并报告结果，再进入下一任务。
- 发现需要扩大文件范围、改变公开 API 或修改前端时，先暂停并向用户说明原因。
- 不回退、不覆盖、不格式化与本任务无关的现有修改。

## 4. 当前 dirty worktree 快照

以下是 2026-07-18 的初始交接快照；2026-07-22 已新增 provider 候选契约修改，承接时必须重新执行 `git status --short`：

```text
 M career_backend.py
 M docs/js_api_contract.json
 M docs/records_center_v3_series_02_metric_result_design.md
 M main.py
 M metrics_resolver.py
 M profile_backend.py
 M tests/test_career_record_metric_series_running_5k.py
 M tests/test_career_records_v2_chart_frontend.py
 M tests/test_career_records_v2_cycling_frontend_semantics.py
 M tests/test_device_name_resolver.py
 M tests/test_fit_sync.py
 M track.html
?? docs/activity_sync_performance_fix_delivery_manual.md
?? docs/activity_sync_performance_fix_task_list.md
?? docs/activity_sync_performance_fix_agent_handoff.md
```

注意：

- 上述已修改业务文件并不等于本次同步性能修复已经实施。
- `main.py`、`profile_backend.py`、`tests/test_fit_sync.py` 中存在承接前的其他功能修改，主要涉及设备产品映射等工作。
- 新 agent 必须阅读这些文件的现有 diff，并在其上做最小增量修改。
- 禁止使用 `git checkout --`、`git reset --hard` 或整文件替换来“清理”工作区。
- 本快照可能随用户后续工作变化，开始实施时必须重新执行 `git status --short`。

## 5. 用户可见问题

点击“同步活动”后，按钮长时间显示“同步活动中...”。同步期间：

- CPU 和数据库持续活跃。
- `duplicate_check.log` 大量增长。
- `fit_parse.log` 出现大量历史 FIT 解析。
- 历史 `activities.updated_at` 持续变化。

历史规模约为：

- tracks 目录约 1746 个 FIT。
- active activities 约 982 条。

这些数量是诊断时快照，只用于说明问题规模，不应作为测试中的固定断言。

## 6. 已确认的当前根因

当前调用链：

```text
track.html::syncRemoteSportHubActivities()
  -> await pywebview.api.sync_remote_fit_activities(startDate, endDate)
  -> Garmin/COROS 下载 FIT
  -> 只要 downloaded > 0 或 skipped > 0
  -> self.sync_local_fit_files()
  -> _sync_local_fit_files_impl()
  -> _walk_fit_files(base) 扫描整个 tracks 目录
  -> mtime 漂移的历史 FIT 重新解析
  -> check_duplicate_activity() 遍历全部 active activities
  -> 每条排除/得分写 INFO
```

关键事实：

- 下载摘要无候选时，当前代码已经会跳过全目录扫描。
- 下载摘要存在候选时，Garmin 和 COROS 仍调用 `self.sync_local_fit_files()`。
- `_sync_single_fit_file(file_path, refresh_career=False)` 已经是可复用的单文件解析入口。
- `batch_import_tracks()` 是手动 FIT/ZIP 导入的现有主路径，不应另写一套导入逻辑。
- `check_duplicate_activity()` 当前仍是全量 SELECT + Python 循环 + 逐候选 INFO 日志。

交接时关键代码锚点：

- `main.py:8172`：`_sync_single_fit_file()`
- `main.py:10706`：`Api.sync_remote_fit_activities()`
- `main.py:10787`：COROS 分支调用 `self.sync_local_fit_files()`
- `main.py:10853`：Garmin 分支调用 `self.sync_local_fit_files()`
- `main.py:12016`：`batch_import_tracks()`
- `profile_backend.py:4355`：`check_duplicate_activity()`
- `track.html:20115` 附近：`syncRemoteSportHubActivities()`

行号可能随工作区变动，实施时使用 `rg -n` 重新定位。

## 7. 已冻结的设计方向

### 7.1 必须实施

- 远程同步只处理本次 download summary 中的 FIT 候选。
- 不再从远程同步路径调用全目录 `sync_local_fit_files()`。
- 增加轻量来源账本 `activity_source_files`，用于来源追踪和解析前幂等判断。
- 幂等优先级：`provider + provider_activity_id`、sha256、现有严格键、现有语义查重。
- 保留语义查重，不能为了性能关闭重复活动保护。
- 逐候选排除和得分日志从 INFO 降到 DEBUG 或移除。
- INFO 只保留查重开始和最终结果摘要。
- ACS 刷新只由实际 inserted/updated activity id 触发；skipped/failed 不刷新。
- 手动 FIT/ZIP 导入继续复用现有路径，并有回归测试保护。

### 7.2 明确不做

- 不做 AI 知识库、embedding、摘要、向量库或索引状态。
- 不在第一阶段实现完整后台 job + 进度轮询。
- 不改变同步日期范围、provider 选择和授权流程。
- 不重构 FIT parser、Activity schema 或整个数据库层。
- 不批量清理用户真实 FIT 或真实数据库。

## 8. 来源账本概要

交付手册建议表名：`activity_source_files`。

核心字段：

```text
id
provider
provider_activity_id
file_path
filename
sha256
file_size
file_mtime
activity_id
ingest_status: pending / parsed / skipped / failed
error
created_at
updated_at
```

关键边界：

- 账本不是 Activity 副本，也不是 AI 索引表。
- `file_mtime` 只用于诊断，不能作为内容唯一身份。
- provider activity id 取得到时使用；取不到时允许为空。
- sha256 用于相同文件内容的解析前幂等。
- 账本命中但关联 Activity 已删除或不存在时，不能永久跳过。
- failed/pending 状态必须允许后续重试。
- 账本不能替代现有严格键和语义查重。

完整字段、索引和状态转换以交付手册第 7 节为准。

## 9. 推荐实施顺序

必须按照任务清单执行：

1. 任务 0：已完成，只读保护 dirty worktree，冻结 Garmin/COROS 真实下载摘要字段，运行修改前基线测试。
2. 任务 1：已完成，标准化下载候选契约。
3. 任务 2：新增轻量来源账本 schema 和仓储 helper。
4. 任务 3：远程同步改为本次候选导入，断言不调用全目录扫描。
5. 任务 4：接入 provider id/sha256 幂等和失败恢复。
6. 任务 5：查重 INFO 日志降噪；SQL 时间窗口粗筛仅在兼容测试充分时实施。
7. 任务 6：ACS 刷新范围收敛。
8. 任务 7：已完成，验证手动 FIT/ZIP 导入兼容并记录 local 来源账本。
9. 任务 8：运行完整聚焦回归、性能验收和最终 diff review。

下一项是任务 8。开始前仍须刷新 dirty diff，并以临时目录完成性能验收，不访问真实用户数据库或批量扫描真实 FIT。

## 10. 测试要求

项目惯例环境：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest ...
```

最终至少执行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
PYTHONPATH=. .venv312/bin/python -m py_compile main.py profile_backend.py garmin_sync.py coros_sync.py
git diff --check -- main.py profile_backend.py garmin_sync.py coros_sync.py tests/test_fit_sync.py docs/activity_sync_performance_fix_delivery_manual.md docs/activity_sync_performance_fix_task_list.md docs/activity_sync_performance_fix_agent_handoff.md
git status --short
```

若新增独立 schema 或查重测试文件，必须显式加入 pytest 和 diff check 命令。

必须锁定的行为：

- Garmin/COROS 各下载 1 个候选时，`sync_local_fit_files()` 均不调用。
- 只调用下载摘要列出的单文件路径。
- 相同 provider activity id 第二次同步不调用 parser。
- provider id 缺失但 sha256 相同时不调用 parser。
- 语义查重仍能命中重复活动。
- INFO 不再包含逐候选排除和得分。
- 零 inserted/updated 不触发 ACS 刷新。
- 手动 FIT/ZIP 导入原有测试继续通过。

## 11. 风险提醒

### 11.1 Garmin 下载摘要兼容边界

Garmin 旧 `files[]` 仍是 downloaded 路径字符串；新 `candidates[]` 才是统一契约。旧摘要没有 skipped 详情时不得伪造 skipped 候选。

### 11.2 `skipped` 不等于无需导入

provider 返回 `skipped: exists` 只说明文件已经存在于 tracks 目录，不说明数据库已经成功解析。该文件仍应进入候选检查，由账本决定是否跳过 parser。

### 11.3 不要逐 activity id 执行全量 ACS 刷新

`_refresh_career_derived_events_safe(reason, activity_id)` 虽然接受单 activity id，但内部仍会调用共享派生刷新。批量导入时不能简单循环该 helper，否则可能把一次偏全量刷新变成 N 次。

### 11.4 SQL 查重粗筛不是第一优先级

历史数据可能混合 `start_time_utc`、local time、空值和时区格式。若兼容性无法用测试封闭，先完成远程候选收敛和日志降噪，不要冒险改变重复命中语义。

### 11.5 不要把前端任务化混入第一阶段

当前前端直接 await 是 UX 放大因素，但后端全目录扫描才是主根因。后台 job 和进度轮询可以后续独立实施，避免本次扩大到 `track.html` 和 API contract。

## 12. 新 Agent 首次汇报模板

新 agent 在任何业务代码修改前，应先向用户提交类似以下内容：

```text
我已阅读：
1. activity_sync_performance_fix_delivery_manual.md
2. activity_sync_performance_fix_task_list.md
3. activity_sync_performance_fix_agent_handoff.md

当前只执行任务 8：聚焦回归、性能验收与最终 diff review，不新增业务功能。

任务 8 输出将包括：
- 完整聚焦 pytest、py_compile 和 diff check
- 临时目录中的 1000+ 历史 FIT 与单候选处理量证据
- 重复候选 parser 调用为 0 与 INFO 日志常数级证据
- 独立 completion report 和最终 dirty diff review

完成任务 8 后我会汇报最终结果和残余风险。
```

## 13. 可直接交给新 Agent 的启动提示词

```text
请在本地项目 `/Users/fanglei/应用开发/AI track` 承接“活动同步性能与重复解析修复”。不要新开分支，不要清理 dirty worktree，不要回退任何你无法确认属于本任务的修改。

开始前必须完整阅读：
- `docs/activity_sync_performance_fix_delivery_manual.md`
- `docs/activity_sync_performance_fix_task_list.md`
- `docs/activity_sync_performance_fix_agent_handoff.md`

任务 0、1、2、3、4、5、6、7 已完成，任务 8 尚未开始。先且只执行任务 8：按照交付手册运行聚焦回归、临时目录性能验收和最终 diff review，并新增独立 completion report。本任务不得新增业务功能、修改前端 job envelope 或访问真实用户数据库。

完成任务 8 后，请清晰汇报：
1. 当前 dirty worktree 中与本任务相关和无关的文件边界；
2. 账本 schema、唯一性与状态转换；
3. 测试命令与结果；
4. 任务 8 的精确修改文件、测试和风险。

等待我的确认后，再严格按照任务清单逐项实施。每个任务开始前说明目标、修改范围、非目标和验证命令；每个任务完成后立即测试并汇报。不得跳过语义查重，不得把远程同步继续接到全目录 `sync_local_fit_files()`，不得引入 AI/embedding/vector 工作，也不得擅自扩大到前端后台 job 改造。
```

## 14. 最终完成交付要求

新 agent 最终应交付：

- 与任务清单状态一致的代码和测试。
- 一份独立 completion report，记录每个任务的完成状态。
- 实际运行的测试命令和结果。
- 性能验收证据：单候选处理量不随历史 FIT 数量增长，重复候选 parser 调用为 0。
- 最终 diff review 结论，明确没有覆盖承接前 dirty worktree 的无关修改。
- 延后事项列表：后台 job UX、AI 索引、历史全量 sha256 回填等。
