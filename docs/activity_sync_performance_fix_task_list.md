---
title: 活动同步性能与重复解析修复任务清单
version: v0.8.0
status: In Progress
type: Ordered Engineering Task List
updated: 2026-07-23
source:
  - docs/activity_sync_performance_fix_delivery_manual.md
---

# 活动同步性能与重复解析修复任务清单

## 0. 执行规则

- 本清单的唯一设计基线是 `docs/activity_sync_performance_fix_delivery_manual.md`。
- 未经用户确认，不开始业务代码修改。
- 不新开分支，直接在当前本地项目工作区实施。
- 每个任务开始前先执行 `git status --short`，并阅读待修改文件的现有 diff。
- 每个任务只改清单列出的范围；发现需要扩大范围时先暂停并更新文档。
- 每个任务完成后立即运行该任务的聚焦测试和 `git diff --check`，不能等全部代码写完再统一验证。
- 不回退、不覆盖、不格式化当前 dirty worktree 中的无关修改。

## 1. 总体状态

| 顺序 | 任务 | 状态 | 主要交付物 |
| --- | --- | --- | --- |
| 0 | 基线保护与契约冻结 | `Completed` | diff 基线、候选摘要样例、测试边界 |
| 1 | 标准化 Garmin/COROS 下载候选契约 | `Completed` | 向后兼容的 `candidates[].file/status/provider_activity_id` |
| 2 | 新增轻量来源账本 | `Completed` | schema、索引、仓储 helper、迁移测试 |
| 3 | 远程同步改为本次候选导入 | `Completed` | candidate-only batch helper、无全目录扫描 |
| 4 | 来源账本幂等与失败恢复 | `Completed` | provider id/sha256 跳过、状态转换 |
| 5 | 查重日志降噪与候选范围评估 | `Completed` | INFO 摘要化、语义查重保持 |
| 6 | ACS 刷新范围收敛 | `Completed` | 仅真实变更刷新、零变更不刷新 |
| 7 | 手动 FIT/ZIP 导入兼容与账本接入 | `Completed` | 原路径回归、local 来源记录、sha256 幂等 |
| 8 | 聚焦回归、性能验收与 diff review | `Not Started` | 测试结果、性能证据、完成报告 |

## 任务 0：基线保护与契约冻结

状态：`Completed`

完成证据：

- 相关 dirty diff 已分类，记录中心 V3 成绩物化与设备映射改动被标记为必须保护。
- Garmin/COROS 真实下载摘要字段已从当前脚本与 provider 实现核对。
- `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q`：137 passed。

### 目标

在修改业务代码前，冻结当前 dirty worktree、远程下载摘要真实形态和现有测试行为，避免把无关改动混入本修复。

### 执行项

- [x] 记录 `git status --short`。
- [x] 分别检查 `main.py`、`profile_backend.py`、`garmin_sync.py`、`coros_sync.py`、`tests/test_fit_sync.py` 的当前 diff。
- [x] 确认当前远程同步在有候选时调用 `sync_local_fit_files()`，无候选时跳过扫描。
- [x] 核对 Garmin 外部脚本真实 `download_summary` 字段，确认旧 `files[]` 只有 downloaded 路径字符串。
- [x] 确认 COROS `files[]` 的 `file/status/labelId` 实际字段。
- [x] 运行现有 `tests/test_fit_sync.py` 并记录修改前基线。
- [x] 确认第一阶段不修改 `track.html` 和公开 API envelope。

### 允许修改

- 本任务原则上只读。
- 若真实下载契约与交付手册不一致，只更新两份修复文档，不改业务代码。

### 验证

```bash
git status --short
git diff -- main.py profile_backend.py garmin_sync.py coros_sync.py tests/test_fit_sync.py track.html
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
```

### 完成门槛

- 当前 diff 和基线测试结果已记录。
- Garmin/COROS 候选字段不再依靠猜测。
- 精确文件范围已确认。

## 任务 1：标准化 Garmin/COROS 下载候选契约

状态：`Completed`

完成证据：

- Garmin 脚本和适配层新增向后兼容 `candidates[]`，保留旧 `files[]` 路径字符串。
- Garmin skipped-existing 候选保留真实 activity id、绝对 FIT 路径与原因。
- COROS 从原 records/errors 派生同构 `candidates[]`，fallback `labelId` 映射为 provider activity id。
- provider 候选原因已做敏感字段净化。
- provider + FIT 同步聚焦回归：272 passed。

### 目标

让 `main.py` 能从两个 provider 的下载摘要中可靠取得本次候选 FIT 的绝对路径、状态和可选 provider activity id。

### 执行项

- [x] 为下载摘要定义兼容 `candidates[]` 标准化 helper。
- [x] 保留 provider 原始 `files/errors/counts` 字段，不破坏现有错误诊断。
- [x] Garmin downloaded/skipped 候选提供绝对 FIT 路径。
- [x] COROS 保留原始 `files[]`，统一可选 `provider_activity_id`。
- [x] 保留 downloaded/skipped/failed 状态；后续导入只处理前两者。
- [x] 非空候选路径规范为绝对 `.fit` 路径。
- [x] 候选稳定去重并保持 provider 返回顺序。

### 预期文件

- `skills/garmin-stats/scripts/download_fit.py`
- `garmin_sync.py`
- `coros_sync.py`
- `tests/test_garmin_sync_provider.py`
- `tests/test_coros_sync_provider.py`
- `tests/test_fit_sync.py`

### 必需测试

- [x] Garmin downloaded 文件可提取绝对路径。
- [x] COROS downloaded 文件可提取绝对路径。
- [x] skipped-existing 文件仍进入候选。
- [x] failed 候选允许空路径且敏感原因被净化。
- [x] 旧 Garmin 摘要没有 skipped 详情时不伪造候选。

### 完成门槛

- 两个 provider 输出同一内部候选结构。
- 现有 provider error code、download 摘要和授权错误测试保持通过。

## 任务 2：新增轻量来源账本

状态：`Completed`

完成证据：

- `profile_backend.py` 新增幂等 `activity_source_files` schema、provider activity id 部分唯一索引，以及 sha256/activity_id/file_path 查询索引。
- 新增按 provider activity id 查询、按 sha256 查询和不接管事务的 upsert helper。
- 状态约束为 `pending` / `parsed` / `skipped` / `failed`；失败摘要会脱敏并限制长度。
- `tests/test_activity_source_files.py`：5 passed；`git diff --check` 通过；模块编译通过。
- 本任务未接入远程同步、未扫描 tracks、未计算 sha256、未修改 activities 事实字段。

### 目标

增加 `activity_source_files`，提供 provider id 和 sha256 级别的解析前幂等判断，不复制 Activity 事实。

### 执行项

- [x] 在 `profile_backend.py` 的既有 schema ensure/migration 风格中创建表。
- [x] 增加 provider activity id 非空唯一索引。
- [x] 增加 sha256、activity_id、file_path 查询索引。
- [x] 实现按 provider id 查询、按 sha256 查询和 upsert 状态 helper。
- [x] 明确 `pending/parsed/skipped/failed` 状态约束。
- [x] 错误字段只保存净化后的短摘要，不保存 token、密码或授权内容。
- [x] 保证旧数据库升级幂等，多次 ensure 不报错、不重复迁移。
- [x] helper 不提交或关闭调用方连接，账本事务边界由调用方控制。

### 预期文件

- `profile_backend.py`
- 新增或现有 schema 测试文件

### 必需测试

- [x] 空数据库可创建账本与索引。
- [x] 旧数据库重复 ensure 幂等。
- [x] 同一非空 `(provider, provider_activity_id)` 不产生两条来源记录。
- [x] sha256 可查询命中。
- [x] pending 可更新为 parsed/skipped/failed。
- [x] activity_id 允许为空，失败记录可保存并重试。

### 完成门槛

- schema 迁移和仓储 helper 有确定性测试。
- 未修改 `activities` 的事实字段语义。

## 任务 3：远程同步改为本次候选导入

状态：`Completed`

完成证据：

- 新增 provider 无关 `_import_remote_fit_candidates()`，只消费标准化 `candidates[]`。
- 候选路径必须为受控 tracks 目录内存在的绝对 `.fit` 文件；重复候选稳定跳过。
- Garmin/COROS 远程路径均已移除 `self.sync_local_fit_files()`，逐候选调用 `_sync_single_fit_file(..., refresh_career=False)`。
- 单候选错误隔离，摘要保留 `activity_ids`、逐候选结果和 download/import envelope。
- `tests/test_fit_sync.py`：139 passed；Garmin/COROS provider 测试：135 passed。

### 目标

Garmin/COROS 下载后只导入本次摘要中的候选文件，彻底移除远程路径对全目录 `sync_local_fit_files()` 的调用。

### 执行项

- [x] 新增 provider 无关的小型 candidate batch helper。
- [x] helper 接收 provider、download summary 和受控目录。
- [x] 每个需解析候选调用 `_sync_single_fit_file(path, refresh_career=False)`。
- [x] 汇总 `scanned/inserted/updated/skipped/errors/elapsed_sec`。
- [x] 保留每个候选的最小结果，供诊断和账本更新。
- [x] Garmin 分支替换 `self.sync_local_fit_files()`。
- [x] COROS 分支替换 `self.sync_local_fit_files()`。
- [x] 保留下载失败、授权失败和导入失败的现有 API envelope。
- [x] 确认 helper 内没有 `_walk_fit_files()` 或目录遍历。

### 预期文件

- `main.py`
- `tests/test_fit_sync.py`

### 必需测试

- [x] Garmin 1 个候选只调用一次 `_sync_single_fit_file()`。
- [x] COROS 1 个候选只调用一次 `_sync_single_fit_file()`。
- [x] 两条路径均断言 `sync_local_fit_files()` 未调用。
- [x] 只处理 download summary 列出的文件，不处理同目录其他 FIT。
- [x] 单候选失败时继续处理后续候选并汇总错误。
- [x] 全部候选失败时返回稳定错误并保留 download/import 摘要。

### 完成门槛

- 远程同步代码不再调用全目录同步。
- 单次处理规模只与本次候选数量相关。

## 任务 4：来源账本幂等与失败恢复

状态：`Completed`

完成证据：

- 候选通过路径校验后流式计算 sha256，并按 provider activity id、sha256 顺序查询完成来源。
- 已完成且关联 Activity 有效的来源在 parser 前跳过；pending、failed、孤儿和内容变化来源均可重试。
- 新候选执行 `pending -> parsed/skipped/failed` 状态转换，错误摘要会脱敏限长。
- 账本使用独立短事务；查询/写入故障只返回固定 warning，不回滚或掩盖 Activity 导入结果。
- 任务 4 聚焦测试：17 passed，另有 4 个重试子场景通过。
- `tests/test_fit_sync.py tests/test_activity_source_files.py`：154 passed，另有 4 个子场景通过；provider 测试：135 passed。

### 目标

在 FIT parser 前阻止已经成功处理的同一来源或同一内容重复解析，同时允许失败、孤儿关联和内容变化安全重试。

### 执行项

- [x] 候选校验后计算文件 size、mtime 和 sha256。
- [x] 先查 `(provider, provider_activity_id)`，再查 sha256。
- [x] 命中 parsed 且关联 Activity 仍有效时直接 skipped，不调用 parser。
- [x] 命中记录但 Activity 已删除/不存在时进入兼容重试，不永久跳过。
- [x] 新候选解析前写 pending。
- [x] `_sync_single_fit_file()` 成功后按 op 写 parsed 或 skipped，并关联 activity id。
- [x] 健康数据过滤、严格键重复和语义重复写 skipped，并记录非敏感结果。
- [x] 异常写 failed，下一次同步允许重试。
- [x] 相同路径但 sha256 改变时继续解析。

### 预期文件

- `main.py`
- `profile_backend.py`
- `tests/test_fit_sync.py`

### 必需测试

- [x] provider activity id 重复时 parser 调用为 0。
- [x] provider id 缺失、sha256 重复时 parser 调用为 0。
- [x] pending/failed 记录可再次尝试。
- [x] 账本 activity id 指向不存在或 deleted Activity 时不会错误跳过。
- [x] 内容变化时不被旧 mtime/path 误判为相同内容。
- [x] 现有严格键和语义查重仍作为后置防线执行。

### 完成门槛

- 重复远程同步已解析候选时不进入 FIT parser。
- 失败恢复和孤儿关联行为有测试锁定。

## 任务 5：查重日志降噪与候选范围评估

状态：`Completed`

完成证据：

- 每次语义查重固定写一条开始 INFO 和一条结果 INFO，包含候选/排除/评分计数与耗时。
- 逐候选时间、时长、距离排除、空间异常和综合得分均移到 DEBUG。
- 新增隔离日志测试：候选从 2 增至 20 时 INFO 始终为 2 条；精确重复、points 时间兜底和 300 秒阈值保持。
- SQL 时间窗口粗筛暂缓：历史记录可仅从 points_json 取得时间，且现有 UTC/local 交叉兜底无法由 SQLite 安全等价表达。
- `tests/test_duplicate_activity_logging.py`：3 passed；现有语义查重切片：5 passed。
- 同步/账本/日志组合：157 passed，另有 4 个子场景通过；provider 测试：135 passed。
- 完整旧 `tests/test_duplicate_check.py` 修改前后均为 13 passed / 5 failed，没有新增失败；既有失败不属于本任务。

### 目标

消除按全库活动数量增长的 INFO 日志，同时保持当前语义查重结果和阈值。

### 执行项

- [x] INFO 开始摘要增加实际候选数量。
- [x] 每条时间、时长、距离排除日志降为 DEBUG 或移除。
- [x] 每条候选得分日志降为 DEBUG。
- [x] INFO 保留最终命中/未命中摘要。
- [x] 空间匹配异常逐条详情降为 DEBUG，并在最终 INFO 聚合异常数量。
- [x] 增加日志级别回归测试。
- [x] 评估 SQL 时间窗口粗筛是否能兼容 UTC、local 和历史空时间。
- [x] 兼容证据不足，记录为后续优化，不在本任务实施 SQL 粗筛。

### 预期文件

- `profile_backend.py`
- 查重相关测试文件

### 必需测试

- [x] 原有重复样例仍返回 `is_duplicate=True`。
- [x] 原有非重复样例仍不命中。
- [x] INFO 不包含逐文件“排除”或“查重得分”。
- [x] INFO 包含一次开始摘要和一次最终结果摘要。
- [x] 未实施 SQL 粗筛，points/空时间兼容回退保持原 Python 逻辑。

### 完成门槛

- 重复保护不变。
- INFO 日志条数不再随全库候选数量线性增长。

## 任务 6：ACS 刷新范围收敛

状态：`Completed`

完成证据：

- 新增批量 ACS helper：activity id 清洗去重、逐 id 增量评估、批次末只执行一次派生刷新。
- 单个增量评估失败时继续其他 id，并用同一次最终刷新回退 `include_pb=True`。
- 远程 Garmin/COROS 仅对 import 摘要中的 inserted/updated ids 调用一次 V3 物化和一次 ACS 刷新。
- 手动 FIT/ZIP 只在 `op=inserted/updated` 时收集刷新 id；skipped/filtered/failed 和零变化不刷新。
- 本地扫描新增/更新走批量增量刷新；removed 保留原有单次全量刷新和失效语义。
- FIT + ACS 变更测试：160 passed，另有 4 个子场景通过；账本/日志/V3：23 passed；provider：135 passed。

### 目标

让 ACS 刷新只响应真实 inserted/updated 活动，并避免零变更批次和重复活动触发刷新。

### 执行项

- [x] 从 candidate batch 结果收集去重后的 inserted/updated activity ids。
- [x] skipped/failed/filtered 不进入刷新集合。
- [x] 零变更批次不调用 ACS 或 V3 刷新入口。
- [x] 使用现有单活动增量评估并隔离单 id 失败，批次末只刷新一次。
- [x] 保证一个批次不对每个 id 重复执行一次全量派生刷新。
- [x] 手动 batch import 只在真实导入成功时刷新，保持导入成功不被 ACS 失败回滚。

### 预期文件

- `main.py`
- `tests/test_fit_sync.py`

### 必需测试

- [x] 远程零变更不刷新 ACS。
- [x] 只有 skipped/failed 时不刷新 ACS。
- [x] 多个真实变更活动按冻结的批量策略刷新，不发生 N 次全量刷新。
- [x] ACS 刷新失败时 Activity 导入结果仍保留，返回错误摘要。

### 完成门槛

- 刷新次数和触发条件有确定性断言。
- 不改变 ACS 事实语义和 Activity 写入事务结果。

## 任务 7：手动 FIT/ZIP 导入兼容与账本接入

状态：`Completed`

完成证据：

- FIT 与 ZIP 均继续走 `batch_import_tracks()`、安全文件搬运和 `_sync_single_fit_file(..., refresh_career=False)`。
- `provider=local` 不使用 `provider_activity_id`，按 sha256 在 parser 前判断幂等。
- 完整来源命中但关联 Activity 已软删除或不存在时继续解析；`pending`、`failed` 仍可重试。
- `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q`：159 passed，另有 4 个 subtests passed。

### 目标

保证本次远程同步优化不破坏手动导入；在不形成第二套解析路径的前提下，为手动来源补充轻量账本记录。

### 执行项

- [x] 继续复用 `batch_import_tracks()` 和 `_sync_single_fit_file()`。
- [x] 保持 FIT 复制、ZIP 解压、路径校验和 Watchdog 暂停/恢复行为。
- [x] 保持健康数据过滤、标题覆盖、严格键查重和二次语义查重。
- [x] 仅在现有单文件结果外层记录 `provider=local` 来源状态。
- [x] 不要求 local 来源提供 provider_activity_id。
- [x] 用 sha256 支持重复手动选择时的幂等判断，但不得绕过现有删除恢复语义。
- [x] 确认现有前端 job + polling envelope 不变。

### 预期文件

- `main.py`
- `profile_backend.py`，仅复用任务 2 helper 时涉及。
- `tests/test_fit_sync.py`

### 必需测试

- [x] 单 FIT 导入成功。
- [x] ZIP 内 FIT 导入成功。
- [x] 重复 FIT/ZIP 仍被正确跳过。
- [x] 健康数据过滤结果保持。
- [x] 标题覆盖保持。
- [x] Watchdog 在成功和异常后都恢复。
- [x] 前端无需修改即可消费原返回结构。

### 完成门槛

- 手动导入既有测试全绿。
- 账本接入没有复制解析、查重或文件搬运逻辑。

## 任务 8：聚焦回归、性能验收与 diff review

状态：`Not Started`

### 目标

证明修复解决了全目录扫描、重复解析和日志爆炸，同时没有覆盖 dirty worktree 或削弱重复防护。

### 执行项

- [ ] 运行所有新增和现有 FIT 同步测试。
- [ ] 运行 schema、查重和手动导入聚焦测试。
- [ ] 运行 Python 编译检查。
- [ ] 运行 `git diff --check`。
- [ ] 使用临时目录构造“历史 1000+ FIT + 本次 1 个候选”，断言 parser 只处理本次候选。
- [ ] 重复执行同一候选，断言第二次 parser 调用为 0。
- [ ] 捕获 INFO 日志，断言不随候选活动数线性增长。
- [ ] 检查最终 diff，只包含本任务相关增量，没有回退已有 device mapping、ACS 或前端改动。
- [ ] 新增独立 completion report，记录命令、结果、残余风险和延后事项。

### 最终验证命令

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
PYTHONPATH=. .venv312/bin/python -m py_compile main.py profile_backend.py garmin_sync.py coros_sync.py
git diff --check -- main.py profile_backend.py garmin_sync.py coros_sync.py tests/test_fit_sync.py docs/activity_sync_performance_fix_delivery_manual.md docs/activity_sync_performance_fix_task_list.md
git status --short
```

若新增测试文件，应显式加入 pytest 与 diff check 命令。

### 完成门槛

- [ ] Garmin/COROS 远程同步均不调用 `sync_local_fit_files()`。
- [ ] 单候选处理量不随历史 FIT 总量增长。
- [ ] 重复候选不重复解析。
- [ ] 语义查重仍命中，INFO 日志已摘要化。
- [ ] 零变更不触发 ACS 刷新。
- [ ] 手动 FIT/ZIP 导入无回归。
- [ ] 所有聚焦检查通过。
- [ ] completion report 已落盘。

## 2. 延后任务

以下事项不属于本清单的完成条件：

- 将“同步活动”改造成后台 job + 进度轮询。
- AI 知识库、embedding、摘要、向量索引。
- 历史 tracks 全量 sha256 回填。
- 全库活动查重算法重构。
- 对真实用户数据库做批量历史修复或清理。
