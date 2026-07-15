# RCV2-08 测试矩阵、真实数据与发布门禁契约

完成时间：2026-07-14

本文冻结 Records Center V2 后续开发、真实数据 dry-run、平台验收和发布前的测试/门禁策略。后续每个任务应优先从本文选择定向测试；若触发高风险条件，必须升级到更宽回归。

## 1. 全局门禁

- Activity 是唯一事实源。
- Resolver/状态迁移服务是正式纪录唯一写入口。
- 前端不计算纪录事实、Scope、置信度、improvement、history summary 或轴方向。
- Fixture 通过不等于真实数据 Verified。
- `RCV2-40` 前真实数据只允许备份、staging 和 dry-run。
- 没有用户明确批准，不得 apply 真实库。
- 用户当前仍要求“暂时不要打包”；`RCV2-44` 前不得生成、签名、公证或替换发布包。
- macOS、Windows、打包是独立门禁；自动化测试通过不等于发布完成。

## 2. 阶段测试矩阵

| 阶段 | 任务 | 定向验证 | 升级回归条件 |
| --- | --- | --- | --- |
| Registry/Catalog | `RCV2-09` | Registry key 唯一、白名单、V1 跑步兼容、Catalog 状态 | 改动 `RecordDefinition` 字段、V1 key、availability |
| Schema/Cache | `RCV2-10` | 空库/V1 库 migration、重复 migration、dry-run mtime、失败回滚、索引 | 改表、唯一键、真实库路径、事务 |
| Evidence | `RCV2-11` | source_mode、range、scope_hash、quality summary、安全 payload | 改 evidence key、range_json、quality_json |
| 状态迁移 | `RCV2-12` | confidence 边界、candidate/active/rejected/invalidated、幂等 | 写接口、候选确认、状态机 |
| 增量/重建 | `RCV2-13` | 删除回退、rebuild dry-run、run_id、旧 active 保留 | rebuild apply、失效回退、批处理 |
| API | `RCV2-14` | V2 API snapshots、V1 wrapper snapshots、安全黑名单 | 修改 `docs/js_api_contract.json`、旧 API shape |
| 骑行功率 | `RCV2-15`-`RCV2-19` | power fixtures、0W、gap、spike、e-bike 排除、curve cache | 功率流、curve、W/kg、机械功 |
| 徒步 | `RCV2-20`-`RCV2-22` | hiking/walking/mountaineering 隔离、海拔尖峰、连续爬升 range | 运动分类、海拔去噪 |
| 游泳 | `RCV2-23`-`RCV2-26` | pool length、stroke、rest break、open water `±5%`、GPS 降级 | pool schema、公开水域标准距离 |
| 越野 | `RCV2-27`-`RCV2-31` | trail 分类、route same/reverse/low overlap、segment range、candidate-only | route signature、segment PR、Pace/GAP |
| 前端 | `RCV2-32`-`RCV2-35` | Catalog 驱动、无 CDN、无表现指数、截图、a11y、响应式 | 修改 `track.html`、图表、候选操作 |
| 集成 | `RCV2-36`-`RCV2-37` | Overview/Timeline/Achievement/Snapshot/AI 边界 | 跨模块读取 Records |
| 安全性能 | `RCV2-38` | 禁止字段扫描、日志摘要、性能预算、错误观测 | 日志、cache、批处理 |
| 全量回归 | `RCV2-39` | V2 自动化矩阵和宽回归 | Milestone C/D/E 完成 |
| 真实数据 | `RCV2-40`-`RCV2-41` | 备份、staging dry-run、人工抽样、用户决策 | 真实库 apply |
| 平台发布 | `RCV2-42`-`RCV2-44` | macOS、Windows、最终文档、显式打包授权 | pywebview、打包、签名、公证 |

## 3. Golden fixture 策略

当前 fixture：

```text
tests/fixtures/records_center_v2/golden_manifest.json
tests/test_records_center_v2_golden_fixtures.py
```

当前覆盖：

- `cycling_power_clean_non_1hz`
- `cycling_power_gap_missing_spike`
- `cycling_power_ebike_excluded`
- `hiking_elevation_spike_single_climb`
- `pool_swim_25m_freestyle_with_rest`
- `pool_swim_missing_pool_length_unknown_stroke`
- `open_water_750m_boundary_and_gps_jump`
- `trail_route_same_reverse_low_overlap`

使用规则：

- Resolver 任务必须复用相关 fixture。
- 可为已冻结规则新增 synthetic case。
- 语义变化必须 bump `manifest_version`。
- 不得从真实库复制 raw track、功率流、文件名、路径、设备标识或体重历史。
- Fixture 全绿只能证明算法输入和边界可复算，不能把泳池、公开水域或越野标记为真实数据 Verified。

## 4. 真实数据验收计划

真实库现状只读审计：

- 普通骑行 94 条。
- 电助力 2 条，必须排除普通骑行纪录。
- 普通骑行 67 条有正的汇总功率/NP 和逐点功率流，27 条无可用功率流。
- 徒步 7 条、登山 5 条、步行 38 条，必须分离。
- 游泳 2 条且均为公开水域。
- 越野跑 0 条。
- 无 canonical pool length Activity 字段。
- 有日期级体重快照，但无活动日期级历史体重事实表。

`RCV2-40` 前：

- 不对真实库 apply migration。
- 不写 V2 active/candidate。
- 不跑 `dry_run=false` rebuild。
- 不改变用户现有 V1 staged/候选决策。

`RCV2-40` 必须：

1. 备份真实库。
2. 复制到 staging。
3. 在 staging 上运行 schema migration dry-run。
4. 在 staging 上运行 Records rebuild dry-run。
5. 输出每个运动的 candidate/ignored/available 计数。
6. 抽样检查 activity_id、record_key、scope、metric、reason codes、detail_link。
7. 用户明确决定哪些运动/纪录允许写入、哪些继续保持候选。

人工抽样最低要求：

| 运动 | 抽样 |
| --- | --- |
| 跑步 | V1 四项各至少 1 条 active 或空态解释。 |
| 骑行 | 功率锚点 5s/20m/60m 各至少 1 条；e-bike 排除至少 1 条。 |
| 徒步 | 距离、爬升、最高海拔、连续爬升候选各至少 1 条或空态。 |
| 游泳 | 公开水域至少 2 条；泳池 validation-required 状态。 |
| 越野 | 无真实样本 candidate-only/empty 状态。 |

## 5. Candidate-only 验收规则

以下场景即使算法可计算，也不得自动 active：

- Registry `candidate_only`。
- 真实样本缺失。
- 公开水域 GPS 质量不可靠。
- 越野 route/segment 只有 fixture，无真实样本。
- 徒步最大连续爬升未经范围人工复核。
- 用户要求“先全部保持候选”的真实数据评估阶段。

候选可以被展示为待确认/待验收，但：

- 不触发 Achievement。
- 不触发 Timeline 正式新纪录。
- 不进入 Overview current record。
- 不触发庆祝动效。

## 6. 安全扫描

所有 Records API、候选 evidence、event payload、snapshot、日志和前端 mock 必须递归扫描禁止字段：

```text
points
points_json
track_json
raw_records
fit_records
power_points
power_stream
cadence_points
elevation_points
gps_points
file_path
storage_ref
path
thumbnail_url
file://
/Users/
\\Users\\
sqlite_master
CREATE TABLE
device_serial
serial_number
email
token
api_key
password
weight_history
real_lat
real_lon
```

允许输出：

- 聚合计数。
- 安全 reason codes。
- 安全文案 key。
- 裁剪 offset/range。
- scope hash 和后端生成 labels。
- 降采样后的绘图点。

## 7. 性能目标

| 场景 | 目标 |
| --- | --- |
| Catalog API | < 100ms 本地库常规规模。 |
| Current Records API | < 200ms，允许缓存。 |
| Detail/History API | < 200ms。 |
| Curve API cache hit | < 150ms。 |
| Curve API cache miss | 可后台生成；前端显示 partial/loading。 |
| 单活动增量 evaluation | < 500ms，不含 heavy curve build。 |
| 全量 rebuild dry-run | 输出进度，避免 UI 阻塞；保留旧数据。 |

性能测试不应牺牲正确性：

- 不得用旧 cache 伪造 active。
- 不得跳过质量评分。
- 不得因性能省略安全扫描。

## 8. 日志和观测证据

允许日志：

- `run_id`
- `resolver_version`
- `record_key`
- `sport`
- `source_mode`
- `decision`
- `reason_code_counts`
- `processed_count`
- `candidate_count`
- `ignored_count`
- `elapsed_ms`
- `cache_hit/cache_miss`

禁止日志：

- raw FIT。
- 完整轨迹、真实 GPS 点。
- 功率/海拔/泳段原始采样数组。
- 本地路径。
- 设备序列号、账号、token。
- SQLite schema dump。
- 体重历史明细。

观测证据：

- 每个 rebuild/dry-run 生成安全 summary。
- 每个 migration dry-run 生成新增表/列/索引与冲突摘要。
- 每个平台验收记录系统、Python、pywebview、SQLite 版本。

## 9. 前端截图验收

`RCV2-35` 必须产出截图或等价视觉验收证据：

- 跑步 available。
- 骑行功率曲线。
- 徒步连续爬升 candidate。
- 游泳 validation-required。
- 越野 candidate-only。
- 候选确认/拒绝。
- Rebuilding 保留旧数据。
- Error 局部错误。
- 1440px、1100px、980px、720px、<520px。

截图检查：

- 无“表现指数”。
- 无外部 CDN 依赖。
- 无伪年度数据。
- 无 raw path/schema/GPS。
- 运动页签由 Catalog 返回。

## 10. 平台门禁

macOS `RCV2-42`：

- 当前开发环境运行。
- pywebview 页面可打开。
- 记录中心视觉可交互。
- JS Bridge API 可用。
- 截图状态通过。
- 不打包，除非用户解除限制。

Windows `RCV2-43`：

- Windows 真机或等价环境运行。
- SQLite partial index 或 fallback 行为验证。
- pywebview 页面可打开。
- JS Bridge API 可用。
- 视觉和响应式状态可用。
- 不打包，除非用户解除限制。

## 11. 发布/打包门禁

`RCV2-44` 前置条件：

- `RCV2-39` 自动化全量回归通过。
- `RCV2-40` staging dry-run 和人工抽样完成。
- `RCV2-41` 用户完成真实数据决策。
- `RCV2-42` macOS 验收通过。
- `RCV2-43` Windows 验收通过。
- 用户明确说可以打包。

未满足任一项：

- 不生成发布包。
- 不签名。
- 不公证。
- 不替换现有安装包。
- 只允许输出状态报告和下一步清单。

## 12. 后续任务默认验证选择

默认顺序：

1. 当前任务新增/修改的最小单元测试。
2. 相关契约测试。
3. V1 兼容测试。
4. Golden fixture 测试。
5. 安全黑名单扫描。
6. 前端截图/DOM 测试。
7. 宽回归。

升级到宽回归条件：

- 改 schema、migration、唯一键。
- 改状态机或候选确认。
- 改 V1 API shape。
- 改 Activity 事实源。
- 改前端记录中心主入口。
- validation 曾失败后修复。
- diff 超过 5 个高风险文件。

## 13. Milestone A 完成条件

`RCV2-00` 至 `RCV2-08` 全部 Done 后，允许进入 `RCV2-09` 代码化阶段。

进入代码化前必须确认：

- Registry、质量、schema、API、视觉和测试门禁均已冻结。
- 用户“不写真实库”“暂不打包”的边界仍有效。
- V1 跑步兼容和旧 PB API 仍是回归保护对象。
- V2 冗余清理只在具体实现任务中进行，不在契约任务中泛化删除。
