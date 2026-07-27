---
title: 活动同步性能与重复解析修复交付手册
version: v0.8.0
status: Implementation In Progress
type: Engineering Delivery Manual
updated: 2026-07-23
scope: Garmin/COROS 远程 FIT 同步、本地 FIT 导入幂等、活动语义查重日志与 ACS 刷新边界
source:
  - 2026-07-18 运行日志与数据库只读诊断
  - main.py 当前远程同步与 FIT 导入实现
  - profile_backend.py 当前活动查重实现
  - garmin_sync.py / coros_sync.py 当前下载摘要契约
---

# 活动同步性能与重复解析修复交付手册

## 0. 文档用途

本文冻结本次修复的真实问题、目标架构、修改边界、数据契约和验收标准。

在任何业务代码修改开始前，实施者必须先阅读本文和对应任务清单：

- `docs/activity_sync_performance_fix_task_list.md`
- 当前工作区 `git status --short`
- 待修改文件的现有 diff

当前工作区已有未提交修改。本修复不得回退、覆盖或格式化无关改动，不得新开分支。

## 1. 问题定义

### 1.1 用户可见现象

用户点击“同步活动”后，按钮长时间显示“同步活动中...”。同步期间后台 CPU、数据库和日志持续活跃，活动列表迟迟不能刷新。

### 1.2 已观察证据

- 应用进程 `.venv312/bin/python main.py` 在同步期间持续活跃。
- `~/.fitvault/logs/duplicate_check.log` 大量写入逐活动排除日志，例如开始时间差超过 300 秒。
- `~/.fitvault/logs/fit_parse.log` 出现大量历史 FIT 文件重新解析日志。
- `activities.updated_at` 在单次同步期间持续推进，说明历史活动被重复更新。
- `~/.fitvault/workspace/tracks/` 约有 1746 个 FIT，active activities 约 982 条；一次远程同步的实际新增候选通常远小于全目录规模。

### 1.3 当前代码基线

截至 2026-07-18，当前代码行为已重新核对：

1. `track.html::syncRemoteSportHubActivities()` 直接 `await window.pywebview.api.sync_remote_fit_activities(...)`，因此后端未返回前按钮一直处于同步状态。
2. `main.py::sync_remote_fit_activities()` 在下载摘要没有候选时已经跳过本地扫描。
3. 只要下载摘要的 `downloaded > 0` 或 `skipped > 0`，Garmin 和 COROS 分支仍调用 `self.sync_local_fit_files()`。
4. `_sync_local_fit_files_impl()` 扫描整个工作目录，并用 `file_path + file_mtime + file_size` 判断文件是否未变化。mtime 漂移会使历史文件重新进入解析和写入路径。
5. `_sync_single_fit_file()` 已是可复用的单文件解析、过滤、持久化入口，并支持 `refresh_career=False`。
6. `profile_backend.py::check_duplicate_activity()` 当前读取全部 active activities，在 Python 中逐条粗筛和轨迹评分，并以 INFO 记录每条排除与得分。
7. `batch_import_tracks()` 在批量导入成功后只调用一次 ACS 刷新，但没有传入实际 activity id，刷新范围偏大。
8. Garmin/COROS 均已增加统一 `candidates[]`；provider 原始 `files` 字段继续保留兼容，后续导入只消费 `candidates[]`。

## 2. 根因与责任边界

### 2.1 主根因

远程同步把“本次下载的少量 FIT”错误地转换为“重新检查整个 tracks 目录”。目录越大，mtime 漂移造成的重复解析越严重。

```text
远程下载少量活动
  -> sync_local_fit_files()
  -> 遍历全部历史 FIT
  -> mtime 漂移文件重新解析
  -> 全量语义查重循环
  -> 活动更新与 ACS 刷新
  -> 同步调用迟迟不返回
```

### 2.2 放大因素

- 语义查重逐候选 INFO 日志产生大量磁盘写入。
- 查重候选从全量 active activities 开始，单文件成本随数据库规模增长。
- 历史活动被更新后触发额外派生数据刷新。
- 前端同步等待让后端耗时直接表现为按钮长时间锁定。

### 2.3 不是本次主根因的事项

- normalized power backfill 不是本次日志爆炸的主因。
- AI 知识库、embedding、摘要生成和向量检索与本次 FIT 幂等导入无关。
- 前端按钮本身不是计算热点；它只是同步等待后端重型调用。

## 3. 本次目标

本次修复必须同时满足以下目标：

1. 远程同步只处理本次下载摘要明确列出的 FIT 候选，不再默认扫描整个 tracks 目录。
2. 同一个 provider activity 或相同文件内容重复同步时，不重复解析、不重复插入活动。
3. 保留现有严格键查重和语义查重，不以性能为由削弱重复活动防护。
4. 把逐活动排除和逐活动得分日志移出 INFO；INFO 只保留一次查重的开始与结果摘要。
5. ACS 派生刷新只由实际 inserted/updated 的活动触发，并避免因 skipped/failed 项重复刷新。
6. 手动 FIT/ZIP 导入继续复用现有 `batch_import_tracks()` 和 `_sync_single_fit_file()` 主路径，现有格式、安全和去重行为保持兼容。
7. 用确定性测试锁住“不调用全目录扫描”和“重复候选不重复解析”。

## 4. 非目标

以下内容明确不进入本次第一阶段实现：

- 不做 embedding、AI 摘要、向量库或知识库索引。
- 不改变 Activity 事实字段、FIT 解析语义或轨迹数据结构。
- 不关闭、不绕过现有语义查重。
- 不重新设计 Garmin/COROS 授权流程。
- 不修改同步日期范围和 provider 选择交互。
- 不把远程同步改造成完整后台 job + 进度轮询；该 UX 优化单独立项。
- 不因本修复重构整个数据库连接层、文件监听服务或导入 UI。
- 不清理用户历史 FIT 文件，不批量改写真实数据库。

## 5. 目标数据流

```text
Garmin/COROS 下载
  -> 标准化 download_summary.candidates[]
  -> 提取本次 downloaded/skipped-existing FIT 路径
  -> 校验路径位于受控 tracks 目录且文件存在
  -> 来源账本幂等判断
       -> 已解析且活动仍有效：直接 skipped
       -> 新候选：记录 pending
  -> _sync_single_fit_file(path, refresh_career=False)
  -> 来源账本更新 parsed/skipped/failed
  -> 汇总本次 inserted/updated activity_ids
  -> 一次有界 ACS 刷新
  -> 返回 download + import 摘要
```

本地手动导入继续走：

```text
选择 FIT/ZIP
  -> batch_import_tracks()
  -> 受控复制/解压
  -> _sync_single_fit_file(..., refresh_career=False)
  -> 现有严格键 + 语义查重
  -> 汇总真实变更
  -> 一次有界 ACS 刷新
```

## 6. 下载候选契约

### 6.1 标准候选字段

Garmin 与 COROS 下载适配层应提供一致的 `candidates[]`。provider 原始 `files` 字段保持兼容，不作为后续导入契约。每个候选项至少支持：

```json
{
  "provider": "garmin",
  "file": "/absolute/path/to/activity.fit",
  "filename": "activity.fit",
  "status": "downloaded",
  "provider_activity_id": "optional-provider-id",
  "reason": "optional",
  "bytes": 12345
}
```

约束：

- 非空 `file` 必须是可解析为绝对路径的 FIT 文件路径；failed 项允许为空。
- `status` 至少支持 `downloaded`、`skipped`、`failed`。
- `skipped` 且原因为目标文件已存在时，仍属于本次导入候选；因为文件存在不代表数据库已成功解析。
- `failed` 项不进入解析，仅进入错误摘要。
- `provider_activity_id` 在 provider 能可靠提供时写入；COROS 直接日期范围模式允许为空。
- 候选原因必须净化 token、密码、Authorization 等敏感内容。
- 候选必须位于本次指定的受控 `TRACKS_DIR` 下；越界路径拒绝导入并记录错误。
- Garmin 脚本保留旧 `files[]` 路径字符串，同时用 `candidates[]` 保存 downloaded/skipped/failed 的结构化结果。
- COROS 保留旧 `files[]` 对象，同时从 records/errors 派生 `candidates[]`。

### 6.2 空摘要行为

当下载摘要没有任何有效 FIT 候选时：

- 不调用 `sync_local_fit_files()`。
- 不调用 `_sync_single_fit_file()`。
- 返回成功的空 import 摘要，保留 provider 下载摘要和错误信息。

## 7. 轻量来源账本

### 7.1 定位

新增 `activity_source_files` 只用于来源追踪和幂等导入，不是 Activity 副本，也不是 AI 索引表。

建议字段：

| 字段 | 类型/约束 | 用途 |
| --- | --- | --- |
| `id` | INTEGER PRIMARY KEY | 账本主键 |
| `provider` | TEXT NOT NULL | `garmin` / `coros` / `local` |
| `provider_activity_id` | TEXT NULL | provider 活动标识，取得到时写入 |
| `file_path` | TEXT NOT NULL | 规范化绝对路径 |
| `filename` | TEXT NOT NULL | 文件名 |
| `sha256` | TEXT NULL | 文件内容幂等键 |
| `file_size` | INTEGER NULL | 诊断与快速比较 |
| `file_mtime` | REAL NULL | 诊断字段，不作为唯一内容身份 |
| `activity_id` | INTEGER NULL | 成功关联的 Activity id |
| `ingest_status` | TEXT NOT NULL | `pending` / `parsed` / `skipped` / `failed` |
| `error` | TEXT NULL | 失败摘要，禁止写入敏感凭据 |
| `created_at` | TEXT NOT NULL | 首次创建时间 |
| `updated_at` | TEXT NOT NULL | 最近状态更新时间 |

### 7.2 索引与唯一性

- 对 `(provider, provider_activity_id)` 建立 provider_activity_id 非空时的唯一索引。
- 对 `sha256` 建立非空索引；是否设为全局唯一必须由测试确认跨 provider 同一 FIT 的预期行为。第一阶段允许以查询命中实现内容去重，避免迁移时因历史脏数据失败。
- 对 `activity_id`、`file_path` 建立普通索引，支持追踪和诊断。
- `file_mtime` 不得作为内容唯一键。

任务 2 已完成 schema 与仓储 helper 落地。helper 使用调用方传入的 SQLite connection，
不自行 commit/close；远程同步和 sha256 计算仍留在后续任务。

### 7.3 状态转换

```text
新候选 -> pending
pending -> parsed   解析并 inserted/updated
pending -> skipped  已由 provider id、sha256、严格键或语义查重确认重复，或被健康数据过滤
pending -> failed   文件校验、解析或写入失败
```

状态写入失败不得掩盖活动导入的真实结果；但必须记录 WARNING 摘要，便于后续修复账本。

### 7.4 幂等优先级

1. `provider + provider_activity_id` 命中已解析来源。
2. `sha256` 命中已解析来源。
3. 现有 `_persist_sync_activity()` 严格键查重。
4. 现有语义查重。

账本只负责提前避免无意义重复解析，不能替代第 3、4 层防护。

任务 4 已完成该幂等链路：完成来源在 parser 前跳过，pending、failed、孤儿关联及
sha256 内容变化允许重试；账本查询或写入故障不会回滚已成功的 Activity。

## 8. 远程候选导入边界

任务 3 已完成该边界落地：Garmin/COROS 远程同步只消费本次 `candidates[]`，
不再调用全目录 `sync_local_fit_files()`；任务 4 已在该 helper 中接入来源账本幂等。

应新增一个小型内部 helper，职责仅限：

- 接收 provider、download summary 和受控目录。
- 提取并验证本次候选路径。
- 执行账本幂等判断和状态更新。
- 对需要解析的文件调用 `_sync_single_fit_file(..., refresh_career=False)`。
- 返回与现有页面兼容的 import 摘要，并附加 `activity_ids` 或内部等价信息供刷新使用。

该 helper 不得：

- 调用 `_walk_fit_files()`。
- 扫描下载摘要以外的历史文件。
- 自己实现新的 FIT parser 或新的语义查重算法。
- 修改前端公开 API 的顶层 envelope：仍返回 `code/msg/data`，`data` 中保留 `download` 与 `import`。

## 9. 查重性能与日志契约

任务 5 已完成日志降噪：每次查重 INFO 固定为开始与结果两条，逐候选排除、评分和
空间异常详情降为 DEBUG。SQL 时间窗口粗筛暂缓，因为 points_json 时间兜底及
UTC/local 交叉比较尚无法由 SQLite 安全等价表达。

### 9.1 必做日志降噪

INFO 保留：

- 一次查重开始摘要：目标时间、距离、时长、候选数量。
- 最终结果摘要：是否重复、最高分、匹配 activity id/filename。

DEBUG 或移除：

- 每条“开始时间相差 > 300s”。
- 每条时长/距离排除。
- 每条候选查重得分。

WARNING 保留真正异常，例如 points JSON 损坏或空间匹配异常；同类异常应避免无界刷屏。

### 9.2 SQL 候选粗筛

SQL 时间窗口粗筛属于第二层优化，只有在混合时区和历史时间格式测试覆盖后才能启用。

要求：

- 优先用 `start_time_utc`，必要时兼容 `start_time`。
- 时间窗口只缩小候选集合，不改变最终 80 分语义查重阈值。
- 无法解析时间的目标或历史记录必须有明确兼容回退，不能静默漏掉重复活动。
- 若风险无法在本次测试中封闭，第一阶段只做日志降噪和远程候选收敛，不强行修改 SQL 候选语义。

## 10. ACS 刷新契约

任务 6 已完成该契约：真实 inserted/updated ids 稳定去重后逐 id 增量评估，批次末
只执行一次共享派生刷新；零变化不刷新。removed/missing-file 继续保留原有单次
全量刷新，以清理删除活动对应的派生事实。

- 只有 `op in {inserted, updated}` 且 activity id 有效的结果进入刷新集合。
- `skipped`、健康数据过滤、严格键重复、语义重复和 failed 不触发刷新。
- 一个批次应避免对每个 activity id 分别执行一次全量 `refresh_career_derived_events()`。
- 实现前需用测试冻结“多 activity id 的增量记录评估 + 一次共享派生刷新”行为；若现有 career API 不支持安全批量化，先维持每批一次刷新，但不得由零变更批次触发。
- ACS 刷新失败不回滚已经成功写入的 Activity，返回结果必须保留 `career_refresh` 错误摘要。

## 11. 手动 FIT/ZIP 导入兼容

本次不重写手动导入流程。必须保留：

- ZIP 安全检查、受控解压目录和文件类型限制。
- Watchdog 暂停/恢复边界。
- 健康数据 FIT 过滤。
- 文件名标题覆盖逻辑。
- 严格键查重与二次语义查重。
- 当前 `code/msg/data` 返回 envelope 和前端轮询流程。

账本接入手动导入时，只能包裹现有 `_sync_single_fit_file()` 结果进行状态记录，不能形成第二套解析路径。

实施状态（任务 7）：

- FIT 复制或 ZIP 安全解压归集后，以 `provider=local` 和文件 sha256 在 parser 前查询来源账本；local 不要求 `provider_activity_id`。
- 完整来源命中时删除本次临时归集副本并返回既有 `code/msg/data` envelope 中的 skipped 项，parser 调用为 0。
- 来源关联 Activity 已软删除或不存在，以及 `pending`、`failed` 来源，均继续走原 `_sync_single_fit_file()`、严格键和语义查重路径。
- 健康过滤、严格键重复、语义重复、成功解析和异常分别写入 `skipped`、`parsed`、`failed` 终态；账本失败不改变 Activity 导入结果。
- 任务 7 完整 `tests/test_fit_sync.py` 回归为 159 passed，另有 4 个 subtests passed；前端 job + polling 代码未修改。

## 12. 失败与恢复语义

- provider 下载失败：保持现有 provider error code、action hint 和 download 摘要。
- 单候选失败：其他候选继续处理，错误汇总到 import result。
- 全部候选失败：远程 API 返回失败，且同时保留 download 与 import 诊断。
- 账本已有 `pending`：应允许重试，并以当前文件 sha256/状态判断，不永久卡死。
- 账本关联的 Activity 已删除或不存在：不得仅凭旧 activity_id 永久跳过；必须继续经过现有重复保护或重新导入策略。
- 文件路径存在但内容变化：sha256 不同则视为新候选，继续现有解析/查重流程。

## 13. 预期修改范围

第一阶段预期只涉及：

- `main.py`
- `profile_backend.py`
- `garmin_sync.py`（仅当需要标准化候选路径）
- `coros_sync.py`（仅当需要补齐统一字段，不改下载策略）
- `tests/test_fit_sync.py`
- 查重相关现有或新增聚焦测试
- `docs/activity_sync_performance_fix_delivery_manual.md`
- `docs/activity_sync_performance_fix_task_list.md`

默认不修改：

- `track.html`
- `docs/js_api_contract.json`
- ACS 前端页面和其他记录中心代码

只有公开 API envelope 或前端行为确实变化时，才能扩大到上述默认不修改文件，并先更新本文边界。

## 14. 测试与验收

### 14.1 必需自动化测试

1. Garmin 下载 1 个候选时，不调用 `sync_local_fit_files()`，只解析下载摘要中的单文件。
2. COROS 下载 1 个候选时，同样不调用全目录扫描。
3. 下载摘要为空时不解析文件，维持当前成功空结果。
4. `skipped: exists` 且文件存在时仍作为候选检查；账本已解析时不重复解析。
5. 相同 `(provider, provider_activity_id)` 第二次同步不重复调用 parser。
6. provider id 缺失但 sha256 相同时不重复调用 parser。
7. 账本命中但关联 Activity 不存在时，不错误地永久跳过。
8. 单文件失败不阻止同批其他文件导入，账本状态为 failed。
9. 语义查重仍能命中重复活动，80 分阈值和返回结构不变。
10. 逐候选排除/得分不写 INFO，开始与结果摘要仍写 INFO。
11. 零 inserted/updated 的批次不触发 ACS 刷新。
12. 手动 FIT 和 ZIP 导入现有测试继续通过。

### 14.2 聚焦验证命令

实施后至少运行：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q
PYTHONPATH=. .venv312/bin/python -m py_compile main.py profile_backend.py garmin_sync.py coros_sync.py
git diff --check -- main.py profile_backend.py garmin_sync.py coros_sync.py tests/test_fit_sync.py docs/activity_sync_performance_fix_delivery_manual.md docs/activity_sync_performance_fix_task_list.md
```

若新增独立查重测试文件，必须加入 pytest 命令。

### 14.3 行为验收

- 远程同步 1 个候选 FIT 时，日志中不得出现全目录 1700+ 文件扫描。
- 已成功同步的同一候选再次同步时，不重新解析 FIT。
- `duplicate_check.log` 不再按数据库活动数量线性写入 INFO 排除日志。
- 同步结果中的 inserted/updated/skipped/errors 与实际处理文件一致。
- 手动 FIT/ZIP 导入、删除活动恢复、标题覆盖和健康数据过滤没有回归。

### 14.4 性能验收

性能验收使用临时目录或真实目录的只读/可回滚副本，不直接批量改写用户真实数据库。

- 单候选远程同步的待解析文件数应为 0 或 1，不随历史 tracks 总量增长。
- 重复同步已入账候选时 parser 调用次数为 0。
- 查重 INFO 日志条数为常数级摘要，不随候选活动数线性增长。

## 15. 完成定义

只有同时满足以下条件，本次修复才可标记完成：

- 远程 Garmin/COROS 路径不再调用全目录 `sync_local_fit_files()`。
- 来源账本 schema、幂等查询和状态转换有自动化覆盖。
- provider id、sha256、严格键和语义查重四层防护关系清晰且未削弱。
- 查重逐候选 INFO 日志已收敛。
- ACS 刷新只由真实活动变更触发。
- 手动 FIT/ZIP 导入回归测试通过。
- 聚焦 pytest、py_compile、diff check 全部通过。
- 最终 diff review 确认没有覆盖当前 dirty worktree 中的无关修改。
