---
title: Task 02 Prompt - 活动列表轻量分页修复
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 02 Prompt - 活动列表轻量分页修复

## 1. 启动要求

在开始任何代码修改前，必须完成以下动作：

1. 执行 `git status --short`，确认当前 dirty worktree，禁止清理、revert、覆盖无关改动。
2. 阅读 `docs/personal_sport_data_performance_optimization_plan.md`。
3. 阅读 `docs/personal_sport_data_performance_task_list.md` 中 Task 02 段落。
4. 阅读 `docs/personal_sport_data_performance_contract_summary.md`，并刷新其中“最近刷新记录”。
5. 阅读当前任务直接相关代码与测试：
   - `profile_backend.py::get_activity_list_filtered()`
   - `profile_backend.py::_activity_list_semantic_identity()`
   - `profile_backend.py::_dedupe_activity_list_rows()`
   - `main.py::get_activity_list()`
   - `main.py::get_sport_hub_activity_page()`
   - 活动列表分页、去重、筛选相关测试

如果执行中发现返回 shape、字段语义、去重身份、分页 total、过滤契约、API envelope 或前端零推断规则存在重要偏离，必须暂停当前修改，重新全文阅读相关原始契约文档，再继续。

## 2. 目标

将个人运动数据活动列表改为真正 SQL 层轻字段分页，避免列表查询读取 `track_json` / `points_json` 大字段，同时保持排序、过滤、分页 total、去重和返回字段契约稳定。

目标性能：

- 列表第一页轻字段 SQL 接近 3-10ms 级别。
- API 热态小于 150ms。
- 冷态不再由列表 SQL 全量扫描和大 JSON 字段主导。

## 3. 允许改动文件

- `profile_backend.py`
- `main.py`
- `track.html`，仅限必要的列表返回字段或埋点适配
- 列表相关测试，例如 `tests/test_fit_sync.py`、`tests/test_response_envelope_contract.py`、`tests/test_duplicate_check.py`、`tests/test_trace_activity_history_filters.py`，或新增聚焦测试
- `docs/personal_sport_data_performance_optimization_plan.md`，仅限记录实测结果
- `docs/personal_sport_data_performance_contract_summary.md`，仅限刷新本任务摘要
- `docs/personal_sport_data_performance_task_list.md`，仅限记录 Task 02 完成证据
- `docs/personal_sport_data_performance_task_02_prompt.md`

## 4. 硬性约束

- 不新建分支，不新建 worktree。
- 不修改 Garmin/COROS 同步、AI、Records Center、打包流程。
- 不处理详情轨迹解析、复盘计算、schema ensure 冷路径治理。
- 不做数据库轨迹拆表。
- 不改变活动事实字段语义，不改变 API envelope。
- 不读取或返回 `track_json` / `points_json` 作为列表首屏字段。
- 不把前端改成从 DOM、ECharts、points、records、标题、设备或天气卡推导事实。

## 5. 实现要点

- 将 `profile_backend.get_activity_list_filtered()` 改为 SQL 层筛选、去重、排序、`LIMIT/OFFSET`。
- total 必须统计去重后的筛选总数，而不是当前页容量，也不是未去重总行数。
- 去重语义必须等效于现有 `_activity_list_semantic_identity()`：
  - 有可靠 start time、distance、duration 且轻量判断有轨迹来源时使用运动类型 + 时间 + 距离 + 时长语义身份。
  - 无可靠语义身份时回退文件身份或 id。
- `has_track` 改用轻量来源，例如 `file_path`、经纬度或既有处理状态；不得触碰 `track_json` / `points_json`。
- 保持 `sport_filter`、`gps_only`、`time_filter`、`location_filter`、`title_keyword` 参数化绑定和现有行为。

## 6. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_response_envelope_contract.py tests/test_personal_sport_data_performance_contract.py -q
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_duplicate_check.py::TestDuplicateCheck::test_activity_list_filtered_dedupes_semantic_duplicates_before_paging tests/test_trace_activity_history_filters.py -q
.venv312/bin/python -m py_compile profile_backend.py main.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 7. 完成定义

- Task 02 提示词已落盘。
- 契约摘要已刷新到 Task 02。
- 列表 SQL 不再读取 `track_json` / `points_json`。
- 分页、过滤、排序、去重 total 有测试覆盖。
- 微基准记录到优化方案。
- 任务清单 Task 02 标为 completed 并记录验证结果。

## 8. 下一任务建议

Task 03 进入 `schema ensure` 冷路径治理。开始 Task 03 前必须再次刷新契约摘要；如果 Task 02 为列表性能引入了 schema、索引或迁移相关偏离，Task 03 必须先全文回读 schema/migration 相关契约与实现。
