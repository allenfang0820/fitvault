---
title: FIT 活动日期解析与旧库修复任务清单
version: v0.2.0
status: Implemented
type: Ordered Remediation Task List
updated: 2026-08-08
scope:
  - Zwift / 第三方 FIT 的活动日期解析根因修复
  - 已入库错误 start_time 的升级自动修复
  - 活动列表、详情、复盘、天气、运动生涯等后端事实消费一致性
non_goals:
  - 不要求用户删除数据库或重新导入 FIT
  - 不以前端显示兜底替代数据库事实修复
  - 不重写活动去重、标题、地区、天气或记录中心算法
  - 不对 Zwift 文件名或单个 activity id 写特例
---

# FIT 活动日期解析与旧库修复任务清单

## 0. 背景与目标

用户发现一条来自 Zwift 的活动被显示为 `1989-12-31`。对真实 FIT 与当前库探查后，已确认该活动的 `activity.local_timestamp` 是 FIT epoch 占位值 `1989-12-31 00:00:00`，但同一个 FIT 里的 `session.start_time`、首个 `event.timestamp`、首个 `record.timestamp` 都是正确时间 `2026-08-01 11:11:57Z`。

当前解析链路把 `activity.local_timestamp` 作为 `activities.start_time` 的优先展示时间写入数据库，导致 `start_time='1989-12-31T00:00:00'`；同时 `start_time_utc='2026-08-01T11:11:57Z'` 已经保存了正确事实。这个问题不能只靠前端显示兜底，因为活动列表排序、时间窗口、天气回填、运动生涯统计和复盘等后端链路都可能读取 `start_time`。

本次目标：

- 从 FIT 解析根因上拒绝明显无效的 FIT 本地时间占位。
- 对已经使用旧版本软件的用户，在升级后自动修复已入库错误日期。
- 修复必须幂等、可重试、可审计，不要求用户重新导入 FIT。

## 1. 已确认根因

- FIT `date_time` / `local_date_time` 以 `1989-12-31 00:00 UTC` 为 epoch；第三方导出可能把缺失或错误 local timestamp 解码成这个边界日期。
- `FITCoreEngine._read_session_info()` 已能读取正确的 `session.start_time`。
- `FITCoreEngine._resolve_start_times()` 当前在存在 `local_timestamp` 时，会返回 `local_timestamp.isoformat()` 作为 `start_time`，即使该值是 `1989-12-31`。
- 入库后 `activities.start_time_utc` 保留了正确 UTC 时间，但 `activities.start_time` 变成错误日期。

## 2. 修复原则

- `start_time_utc` 是更可信的 canonical 时间锚点；`start_time` 只能保存可信本地展示时间或 canonical UTC 兜底。
- 明显无效的 `local_timestamp` 不得覆盖 `session.start_time`。
- 旧库修复只更新时间字段，不触发导入生命周期副作用：
  - 不重新判重。
  - 不改标题。
  - 不改地区。
  - 不改文件 ledger。
  - 不重新解析全量 FIT 文件作为默认手段。
- 升级修复使用 `app_migrations` 独立 key；成功后写 done，失败不写 done，下一次启动可重试。
- 前端只消费后端修复后的事实；可以保留 defensive fallback，但不能作为本轮主修复。
- 修复逻辑必须是泛化的 FIT 时间有效性规则，不写 Zwift 专属 activity id 或文件名特例。

## 3. 允许修改范围

- `fit_engine.py`
  - 新增 FIT 时间有效性判断。
  - 修复 `_resolve_start_times()` 对无效 `local_timestamp` 的选择策略。
- `profile_backend.py`
  - 新增旧库 `activities.start_time` 修复函数。
  - 复用现有 `app_migrations`。
- `main.py`
  - 在启动 schema 确认后调用一次性旧库修复。
  - 新增独立 migration key。
- `tests/`
  - 增加解析单元测试和旧库迁移测试。
- `docs/`
  - 本任务清单与执行记录。

## 4. 非目标

- 不修改 FIT 文件本身。
- 不新增用户手动修复按钮作为主要方案。
- 不扩大到活动日期之外的 Zwift 功率、设备、路线或标题问题。
- 不修改天气 API、运动生涯记录算法或复盘算法。
- 不通过 SQL 全库重写所有历史日期，只修复明确异常值。

## 5. 任务总览

| 顺序 | 任务 | 类型 | 状态 | 发布门槛 |
| --- | --- | --- | --- | --- |
| 1 | FIT-DATE-01 冻结根因与样本证据 | 诊断/契约 | Done | 明确 `local_timestamp` 坏、`start_time_utc` 好 |
| 2 | FIT-DATE-02 修复 FIT 起始时间解析 | 后端解析 | Done | 新导入不再把 `1989-12-31` 写入 `start_time` |
| 3 | FIT-DATE-03 实现旧库一次性日期修复 | 后端迁移 | Done | 旧版本已入库异常活动升级后自动修复 |
| 4 | FIT-DATE-04 启动入口接入与幂等哨兵 | 启动/迁移 | Done | 已完成迁移的库不重复执行 |
| 5 | FIT-DATE-05 聚焦测试与真实库验证 | 测试/验收 | Done | 解析、迁移、幂等、当前真实样本均通过 |

## 6. FIT-DATE-02：修复 FIT 起始时间解析

### 目标

`FITCoreEngine._resolve_start_times()` 必须忽略明显无效的 FIT local timestamp，例如 `1989-12-31` epoch 占位。

### 执行项

- [x] 新增 `_is_plausible_activity_datetime()` 或等价 helper。
- [x] `local_timestamp` 为 `None` 或年份早于合理阈值时，不得作为 `start_time`。
- [x] 当 `session.start_time` 有效时：
  - `start_time_utc` 输出 UTC ISO。
  - `start_time` 优先输出可信本地时间；本地时间不可信时输出 UTC ISO。
- [x] 当 `session.start_time` 缺失时：
  - 优先使用首个轨迹点时间。
  - 再考虑可信 `local_timestamp`。

### 验收

- [x] `start_time=2026-08-01 11:11:57` 且 `local_timestamp=1989-12-31 00:00:00` 时，输出 `start_time='2026-08-01T11:11:57Z'`。
- [x] 合理的带 offset 本地时间仍可保留。
- [x] 无 session 时间但有首点时间时仍可恢复。

## 7. FIT-DATE-03：实现旧库一次性日期修复

### 目标

对已经入库的异常日期做自动修复，覆盖旧版本用户升级场景。

### 修复候选

只处理明确异常的 `activities.start_time`：

- `1989-12-31%`
- 或解析后年份早于合理阈值。

候选时间优先级：

1. 有效 `start_time_utc`
2. `track_json[0].time`
3. `points_json[0].time`

### 更新范围

- `activities.start_time`
- 必要时补 `activities.start_time_utc`
- `updated_at` 保持原值或只做无业务含义触碰；本轮不要求改变活动更新时间排序语义。

### 验收

- [x] 旧库 bad `start_time` + good `start_time_utc` 被修复。
- [x] 旧库 bad `start_time` + missing UTC + good first point 被修复。
- [x] 无可信候选时跳过并统计 skipped。
- [x] 重复执行不会再次修改已修复记录。
- [x] 不改标题、地区、运动类型、距离、时长、文件路径。

## 8. FIT-DATE-04：启动入口接入与幂等哨兵

### 目标

新增独立迁移 key：

```text
activity_start_time_epoch_repair_v1
```

启动时在 `ensure_activity_sync_schema()` 中执行该修复。注意：该修复必须独立于既有粗粒度 `ACTIVITY_SYNC_SCHEMA_SENTINEL_KEY`，否则已经完成旧 schema sentinel 的用户升级后不会跑到本修复。

### 验收

- [x] 新装空库执行无异常。
- [x] 旧库首次升级自动执行。
- [x] 完成后写入 `app_migrations` done。
- [x] 已 done 后再次启动不执行扫描。
- [x] 失败时不写 done，允许下次重试。

## 9. FIT-DATE-05：测试与验收命令

推荐命令：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fit_parser.py \
  tests/test_fit_sync.py -k 'start_time_epoch_repair or zwift_epoch' -q

PYTHONPATH=. .venv312/bin/python -m py_compile \
  fit_engine.py profile_backend.py main.py

git diff --check
```

### 发布验收

- [x] 新导入同类 Zwift FIT 不再出现 `1989-12-31`。
- [x] 当前真实库中的 `23811652091_ACTIVITY.fit` 可被修复为 `2026-08-01T11:11:57Z`。
- [x] 旧版本用户升级后无需手工重导即可更新老数据。
- [x] 修复日志 / migration details 不输出本机 FIT 原始绝对路径或用户隐私。

## 10. 执行记录

- 文档创建时间：2026-08-08
- 当前状态：`Implemented`
- 实现文件：
  - `fit_engine.py`
  - `profile_backend.py`
  - `main.py`
  - `tests/test_fit_parser.py`
  - `tests/test_fit_sync.py`
- 新增迁移 key：`activity_start_time_epoch_repair_v1`
- 真实 Zwift FIT 只读验证：
  - 修复后 `basic_info.start_time = 2026-08-01T11:11:57Z`
  - 修复后 `basic_info.start_time_utc = 2026-08-01T11:11:57Z`
  - 首个轨迹点时间 `2026-08-01T11:11:57Z`
- 当前真实库 dry-run：
  - `scanned=1`
  - `fixed=1`
  - `source_counts={"start_time_utc": 1}`
- 测试结果：
  - `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_parser.py -q`：16 passed，3 skipped，13 subtests passed
  - `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q`：172 passed，4 subtests passed
  - `PYTHONPATH=. .venv312/bin/python -m py_compile fit_engine.py profile_backend.py main.py`：通过
  - `git diff --check`：通过
