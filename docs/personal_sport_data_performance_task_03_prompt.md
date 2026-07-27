---
title: Task 03 Prompt - schema ensure 冷路径治理
version: v0.1.0
status: Ready
type: Engineering Execution Prompt
updated: 2026-07-23
source:
  - docs/personal_sport_data_performance_optimization_plan.md
  - docs/personal_sport_data_performance_task_list.md
  - docs/personal_sport_data_performance_contract_summary.md
---

# Task 03 Prompt - schema ensure 冷路径治理

## 1. 启动要求

在开始任何代码修改前，必须：

1. 执行 `git status --short`，保护当前 dirty worktree。
2. 阅读优化方案、任务清单 Task 03 段落和契约摘要。
3. 刷新 `docs/personal_sport_data_performance_contract_summary.md` 的最近刷新记录。
4. 阅读 `profile_backend._ensure_schema_initialized()`、`profile_backend._init_schema()`、`profile_backend._conn()`、`main.ensure_activity_sync_schema()` 和 schema/migration 相关测试。

如果执行中需要删除历史迁移、改变活动事实字段、改变 API 返回 shape、改变导入/同步语义，必须暂停并重新全文阅读相关契约与实现，再继续。

## 2. 目标

把昂贵 schema ensure 和兼容性大表修复从列表、详情、复盘的用户首屏动作路径移走。历史迁移仍然保留，但首次完成后用 sentinel/version 记录，后续进程启动不再重复同步扫大表。

## 3. 允许改动文件

- `profile_backend.py`
- `main.py`
- schema/migration 相关测试，或新增聚焦测试
- `docs/personal_sport_data_performance_optimization_plan.md`
- `docs/personal_sport_data_performance_contract_summary.md`
- `docs/personal_sport_data_performance_task_list.md`
- `docs/personal_sport_data_performance_task_03_prompt.md`

## 4. 硬性约束

- 不新建分支，不新建 worktree。
- 不删除历史迁移逻辑。
- 不全量重建数据库。
- 不改变活动事实字段语义。
- 不触碰 Garmin/COROS 同步性能、AI、Records Center、UI 大改、详情 summary 或复盘缓存。
- sentinel 命中只能表示“当前版本的 schema/兼容修复已完成”，不能掩盖新版本迁移。

## 5. 实现要点

- 为 `profile_backend._init_schema()` 增加版本化 sentinel，命中时 `_conn()` 不再重复执行完整建表、补列、seed 和索引逻辑。
- 为 `main.ensure_activity_sync_schema()` 增加版本化 sentinel，命中时不再执行兼容性 `UPDATE activities ...` 和重复索引/补列。
- sentinel 使用已有 `app_migrations` 或等价轻量 meta 表，读取必须便宜，写入必须幂等。
- sentinel miss 时仍执行旧迁移逻辑，并在成功 commit 后写入 sentinel。
- 测试覆盖：sentinel 命中时不执行大表 `UPDATE activities`；sentinel 缺失时迁移仍幂等。

## 6. 验证命令

```bash
git status --short
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py tests/test_personal_sport_data_performance_contract.py -q
.venv312/bin/python -m py_compile main.py profile_backend.py
git diff --check
.venv312/bin/python scripts/benchmark_personal_sport_data.py --warm-runs 3
```

## 7. 完成定义

- Task 03 提示词已落盘。
- 契约摘要已刷新到 Task 03。
- schema sentinel 逻辑已实现并测试。
- 列表、详情、复盘冷态不再由重复大表 schema ensure 主导。
- 实测结果记录到优化方案和任务清单。

## 8. 下一任务建议

Task 04 进入活动概览轻量首屏。开始 Task 04 前必须再次刷新契约摘要；如果详情 API shape 或前端打开详情流程与摘要不一致，必须回读 `docs/js_api_contract.json` 和详情相关交付手册。
