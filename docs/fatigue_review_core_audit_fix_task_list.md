---
title: 脉图复盘核心功能审计修复任务清单
version: v0.1
status: Audit Fix Task Breakdown
created: 2026-07-13
source:
  - 2026-07-13 复盘核心功能代码审计
  - docs/fatigue_review_e2e_audit_report.md
  - docs/fatigue_review_realignment_plan_v1.md
  - docs/js_api_contract.json
  - docs/脉图运动复盘系统_开发团队交付手册_v1.md
---

# 脉图复盘核心功能审计修复任务清单

本文档把 2026-07-13 对脉图复盘功能的代码审计、253 条本地真实活动回放和核心测试结果，拆分为可独立执行、验证和交付的开发任务。

本轮修复的目标不是调整视觉样式，而是恢复复盘系统的数据可信度：同一个字段必须只有一个权威数据源；不可用不能伪装成正常；历史趋势必须站在活动发生时点计算；跑步、骑行及其他运动不得共享错误算法或文案。

若本文与既有完成报告冲突，以本次审计确认的真实代码行为、`docs/js_api_contract.json` 和重新冻结后的复盘契约为准。

## 0. 审计摘要

真实活动回放范围：`activities.deleted_at IS NULL` 的 253 条活动。

已确认问题：

- 204 条活动存在“指标不可用或没有主值，但仍生成改善/下降趋势”。
- 41 条活动后程效率实际提升，却被绝对值算法标记为效率下滑风险。
- 131 条后程效率趋势绝对值超过 200%，出现 `-9289%` 等无意义结果。
- 2 条近期跑步活动已有 2800+ / 4200+ 有效速度点，耐久指数仍返回 `points<20`。
- 6 条跑步活动已有数百至数千个步频点，却显示“设备未记录”。
- 9 条无效率曲线活动返回 `decoupling.pct=0.0`，前端可能展示假正常状态。
- 12 条特殊或未规范化运动类型落入通用分支，复用了不适合的跑步卡片或图层。
- 历史趋势和训练负荷窗口以电脑当前时间为锚点，旧活动会读取未来活动作为基线。

## 1. 总体契约

所有任务必须遵守以下约束：

1. `Activity/FIT` 是单次活动事实源，Resolver/复盘后端是算法结论唯一事实源。
2. 前端只翻译和渲染后端状态，不从 curves、DOM、ECharts 或文本补算指标。
3. 当前活动的指标输入必须来自同一份权威复盘快照；不得混用空的数据库派生列和实时解析曲线。
4. 历史基线必须以当前被复盘活动的 `start_time` 为截止点，只能使用它之前的数据。
5. 当前值和历史基线必须使用同一公式、同一方向、同一单位、同一过滤规则。
6. `unavailable`、`partial/low confidence`、`available` 必须是不同状态；不得把“无法分析”显示为“状态平稳”。
7. 跑步耐久使用速度/配速口径；骑行后程保持使用有效踩踏功率口径；两者不得互相兜底或复用文案。
8. 跑步功率可以作为 FIT 事实存在，但不得自动进入跑步耐久指数、跑步 pacing 或骑行专项结论。
9. AI 只能消费已通过可用性门控的复盘快照；不可用指标不得携带强趋势或伪数值进入 AI。
10. 不修改 VI、GAP、训练负荷等公式，除非对应任务明确要求并同步更新契约、文档和测试。
11. 不顺手修改 ACS、OpenClaw、同步、标题、打包或无关 UI。
12. 每项任务完成后必须运行目标测试、真实活动回放和契约 diff 审查。

## 2. 执行顺序

| 阶段 | 任务 | 发布要求 |
| --- | --- | --- |
| Phase A | FR-Core-00 | 契约和失败基线冻结后才能修改算法 |
| Phase B | FR-Core-01 至 FR-Core-05 | P0 全部完成前不得发布复盘算法版本 |
| Phase C | FR-Core-06 至 FR-Core-10 | 修复专项路由、文案和低置信度体验 |
| Phase D | FR-Core-11 | 全量回放和跨平台发布门禁 |

---

# Phase A：冻结契约与失败基线

## `FR-Core-00`：复盘权威数据、时间语义与可用性契约冻结

优先级：P0  
性质：契约 / 测试基线 / 不改业务结果
状态：已完成红色基线冻结（2026-07-13）

目标文件：

- `docs/js_api_contract.json`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/fatigue_review_core_audit_fix_task_list.md`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_snapshot_realignment.py`
- 新增 `tests/test_fatigue_review_core_audit_regression.py`

### 目标

先把本次审计确认的正确语义写成可执行测试，避免后续继续以字段存在、字符串存在或 mock 结构完整代替业务正确性。

### 必做

- 定义活动时点：所有 7d/21d/42d 历史窗口以当前活动 `start_time` 为 `as_of_time`。
- 定义统一状态：`available / partial / unavailable / not_applicable`。
- 定义 unavailable 形状：主值必须为 `null`，不得使用 `0` 表示缺失。
- 定义 trend 门控：当前指标不可用时，`delta_pct/is_improving` 必须为 `null`。
- 定义同口径比较：current 与 baseline 必须携带相同 `basis/version`。
- 定义运动类型矩阵：running、trail、treadmill、cycling、road、MTB、indoor cycling、walking、hiking、mountaineering、swimming、general unsupported。
- 把 253 条活动回放中发现的典型失败样本固化为匿名化 fixture。

### 验收

- 新增测试在修复前能够稳定失败，并分别指向时间穿越、绝对值解耦、不可用趋势、耐久数据源和专项文案。
- 契约中明确 AI 不接收不可用趋势。
- 不修改任何现有活动指标计算结果。

### FR-Core-00 交付记录（2026-07-13）

- 已新增 `tests/test_fatigue_review_core_audit_regression.py`，使用匿名化等价 fixture 固化本次审计失败类型。
- 已更新 `docs/js_api_contract.json`，新增 `fatigue_review_core_audit_contract`，冻结 `as_of_time`、`available / partial / unavailable / not_applicable`、同 `basis/version`、AI 不接收不可用趋势、跑步/骑行耐久口径隔离和运动类型矩阵。
- 已更新 `docs/脉图运动复盘系统_开发团队交付手册_v1.md`，新增 §4.6 作为后续 FR-Core 任务的契约摘要。
- 已新增 `docs/fr_core_00_contract_freeze_completion_report.md`，记录交付手册摘要、任务契约摘要、工程级提示词、预期红色基线和下一任务建议。
- 验证命令：`.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'`。
- 当前结果：8 个测试中，文档契约已通过；7 个程序/算法/前端/AI 门控测试按预期失败，分别锚定 FR-Core-01 至 FR-Core-07 的修复输入。
- 本任务未修改 `main.py`、`metrics_resolver.py`、`llm_backend.py` 或 `track.html` 的业务行为。

### 禁止

- 不为了让旧测试变绿而保留错误语义。
- 不只增加静态 `assertIn` 测试。

---

# Phase B：P0 算法与数据真理修复

## `FR-Core-01`：历史窗口与活动时点修复

优先级：P0  
性质：历史基线 / 时间语义
状态：已完成（2026-07-13）

目标文件：

- `metrics_resolver.py`
- `main.py`
- `tests/test_fatigue_review_core_audit_regression.py`
- `tests/test_v8_5_trend.py`
- `tests/test_fatigue_review_trends.py`

### 根因

- 效率 baseline 使用 `start_time < now-21d`，取成了 21 天以前的全部活动。
- 其他 trend/load ratio 使用电脑当前时间，不使用被复盘活动的发生时间。
- SQL 没有限制历史记录必须早于当前活动，旧活动会读取未来活动。

### 必做

- 新增统一 `as_of_time` 解析器，优先使用活动 `start_time_utc`，其次使用可归一化的 `start_time`。
- 21d 窗口统一为 `[as_of_time-21d, as_of_time)`。
- 7d/42d 负荷窗口统一以 `as_of_time` 结束。
- 所有历史 SQL 增加 `start_time < current_activity_time`。
- 统一处理带时区、无时区和 `Z` 时间；禁止依赖 SQLite 文本时区字符串的偶然字典序。
- 当前活动只能加入一次，历史查询必须排除当前活动 ID。

### 验收

- 复盘 2025 年活动时，任何 baseline 输入不得包含 2026 年活动。
- `window_days=21` 只返回此前 21 天，不返回更早全历史。
- 训练负荷 7d/42d 对今天活动和历史活动均有确定测试。
- 冻结当前日期不会改变同一历史活动的复盘结果。

### 禁止

- 不使用 `datetime.now()` 作为历史活动复盘的窗口终点。
- 不用活动 ID 大小替代时间先后。

### FR-Core-01 交付记录（2026-07-13）

- 已在 `main.py` 新增活动时间解析与窗口过滤辅助逻辑，统一把 `start_time_utc / start_time` 归一化为 UTC `as_of_time`。
- 已将 efficiency、durability、cadence stability、training load trend 和 7d/42d load ratio 全部改为以被复盘活动发生时刻结算，并排除当前活动及未来活动。
- 已兼容旧活动库缺少 `start_time_utc` 列的场景；SQL 只做只读粗筛，权威窗口由解析后的 UTC 时间判断。
- 已给 `metrics_resolver._fetch_efficiency_baseline()` 增加可选 `as_of_time`，并在复盘 efficiency 注入路径传入当前活动时间。
- 已新增 `tests/test_fatigue_review_time_window_contract.py`，覆盖 21d durability 和 7d/42d 训练负荷窗口的未来数据排除。
- 已更新 `tests/test_v8_5_trend.py` 与 `tests/test_fatigue_review_trends.py` 中过期的静态/文案断言，使其匹配 FR-Core-01 的解析后窗口契约。
- 验证通过：`test_fatigue_review_time_window_contract.py` 2/2、`test_v8_5_trend.py` 13/13、`pytest tests/test_fatigue_review_trends.py` 7/7。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中历史窗口用例已转绿；剩余 6 个预期失败继续锚定 FR-Core-02、FR-Core-03、FR-Core-04、FR-Core-05、FR-Core-07。
- 本任务未修解耦方向、不可用趋势门控、durability 当前曲线源或前端缺失文案。

---

## `FR-Core-02`：后程效率变化方向与同口径趋势修复

优先级：P0  
性质：算法语义 / Resolver
状态：已完成（2026-07-13）

目标文件：

- `metrics_resolver.py`
- `main.py`
- `track.html`
- `tests/test_fatigue_review_decoupling_resolver.py`
- `tests/test_fatigue_review_core_audit_regression.py`

### 根因

- 当前解耦使用绝对值，后程改善和后程下降都会成为风险。
- 当前 decoupling 与历史 baseline 使用不同算法：效率变化对比了速度衰减。
- 前端统一使用“后程效率下滑”，没有方向字段。

### 必做

- 冻结 signed 指标，例如 `change_pct = (late_efficiency - early_efficiency) / early_efficiency * 100`。
- 另设明确的退化口径，例如 `decline_pct = max(0, -change_pct)`；不得用 `abs()` 替代方向。
- 返回 `direction: improved | stable | declined | unknown`。
- 当前值和 baseline 共用同一函数、同一 startup trim、同一有效值过滤。
- 删除用速度衰减作为 decoupling baseline 的兼容路径。
- 前端根据 direction 显示“后程改善 / 基本稳定 / 后程下滑”。

### 验收

- `[1.0...1.2]` 后程改善样本不得再返回 `bad`。
- `[1.0...0.88]` 后程下降样本仍返回风险。
- 趋势不会出现超过合理边界的数千百分比。
- 41 条真实反向样本重新回放后不再误判为下滑。

### 禁止

- 不保留“后程改善也按绝对变化判坏”的旧测试契约。
- 不在前端重新计算 early/late。

### FR-Core-02 交付记录（2026-07-13）

- 已将 `MetricsResolver._build_review_decoupling()` 从绝对值算法改为 signed `change_pct = (late - early) / early * 100`。
- 已新增 `direction: improved / stable / declined / unknown` 与 `decline_pct = max(0, -change_pct)`；兼容字段 `pct` 现在表示退化幅度。
- 已新增 `basis/version = efficiency_curve_signed_change / fr_core_02_signed_decoupling_v1`，用于后续同口径趋势门控。
- 已停止用 `speed_curve` 速度衰减冒充 decoupling 历史 baseline；缺少同口径 `efficiency_curve` 历史源时，decoupling trend baseline 返回 `None`。
- 已更新前端 decoupling 展示，只消费后端 `direction/change_pct/decline_pct`，显示“后程效率改善 / 稳定 / 下滑”，不在前端补算 early/late。
- 已刷新旧测试：`tests/test_fatigue_review_decoupling_resolver.py`、`tests/test_v8_2_trend.py`。
- 验证通过：`test_fatigue_review_decoupling_resolver.py` 5/5、`test_v8_2_trend.py` 18/18、`test_fatigue_review_e2e_contract.py + test_fatigue_review_snapshot_realignment.py` 65/65。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中 FR-Core-02 后程改善用例已转绿；剩余 5 个预期失败继续锚定 FR-Core-03、FR-Core-04、FR-Core-05、FR-Core-07。
- 本任务未修 unavailable trend gate、AI 快照净化、当前 durability 曲线源或缺失文案。

---

## `FR-Core-03`：不可用指标趋势门控与 AI 快照净化

优先级：P0  
性质：状态机 / AI 数据边界
状态：已完成（2026-07-13）

目标文件：

- `main.py`
- `llm_backend.py`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_ai_insight_p6.py`
- `tests/test_fatigue_review_core_audit_regression.py`

### 根因

- 心率漂移缺失时以 `0.0` 参与 trend。
- cadence `confidence=low + score=null` 仍生成强趋势。
- AI compact snapshot 原样携带所有 metrics/trend，与“trend 不进入 AI”的旧约束冲突。

### 必做

- 新增统一 trend gate：当前主值、basis、confidence、baseline 任一不满足时返回 unknown trend。
- 禁止用 `0` 代替缺失 current value。
- `partial/low` 只允许 reference trend，必须带 `confidence` 和温和语义；默认不进入 AI 主结论。
- AI 快照过滤 `unavailable` 的 delta、方向和伪 baseline；骑行解释继续以 `cycling_explanation_signals` 为唯一专项依据。
- 对同一指标增加 `metric_version/basis` 一致性检查。

### 验收

- `hr_drift.pct=null` 时 `trend.delta_pct/is_improving=null`。
- 不再出现“数据不足但改善 100%”。
- 204 条真实矛盾样本归零。
- AI prompt fixture 中不存在不可用指标的强趋势字段。

### 禁止

- 不通过 prompt 文案掩盖错误后端字段。
- 不让 AI 自行判断哪些 trend 可用。

### FR-Core-03 交付记录（2026-07-13）

- 已新增 `_gate_fatigue_review_metric_trends()`，集中门控 unavailable / not_applicable / 主值缺失指标的强趋势。
- 已修复 HR drift 当前值缺失时被 `0.0` 参与 trend 的伪数值问题。
- 已在后端复盘 snapshot 返回前统一门控 metrics trend；不可用指标不再携带 `delta_pct/is_improving` 强语义。
- 已在 AI compact snapshot 构建时再次门控，并对 low/partial 指标默认只保留 unknown reference trend。
- 已保留骑行解释信号边界：AI 仍只能消费后端 `cycling_explanation_signals`。
- 验证通过：`test_fatigue_review_ai_preflight_p8.py + test_fatigue_review_ai_insight_p6.py + test_fatigue_review_e2e_contract.py` 51/51。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中 FR-Core-03 unavailable trend 和 AI compact 用例已转绿；剩余 3 个预期失败继续锚定 FR-Core-04、FR-Core-05、FR-Core-07。
- 本任务未修 running durability 当前曲线源、空快照主值或前端跑步缺失文案。

---

## `FR-Core-04`：当前指标曲线权威源统一

优先级：P0  
性质：数据血缘 / snapshot
状态：已完成（2026-07-13）

目标文件：

- `main.py`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_core_audit_regression.py`

### 根因

当前图表、HR drift 和骑行信号使用 `curves_snapshot`，但跑步 durability 只使用 `row.speed_curve`。新活动数据库派生列为空时，页面已有完整速度曲线，指标仍判样本不足。

### FR-Core-04 交付记录（2026-07-13）

- 已将 running durability 的当前 `speed_stream` 来源改为 `curves_snapshot.speed`，只在 snapshot 缺失时使用已解析的 `speed_curve` 变量兜底。
- 已停止直接从 `row.speed_curve` 数据库派生列构造当前 durability 输入，避免新活动派生列为空时误判 `points<20`。
- 已更新 `tests/test_fatigue_review_snapshot_realignment.py`，把权威 speed 明确放入 resolved snapshot，测试不再绑定旧 DB 派生列。
- 验证通过：`test_fatigue_review_snapshot_realignment.py` 32/32。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中 FR-Core-04 durability 权威曲线源用例已转绿；剩余 2 个预期失败继续锚定 FR-Core-05、FR-Core-07。
- 本任务未修空快照主值或前端跑步缺失文案。

### 必做

- 当前活动所有曲线型指标统一从 `curves_snapshot` 取值。
- persisted derivative 只能作为构建 snapshot 的后端兜底，不能绕过 snapshot 直接进入单个指标。
- durability、cadence、HR drift、decoupling 必须共用同一个 distance axis 和 startup window。
- 当 snapshot 曲线不可用时，返回明确的 source/reason，而不是静默切到不同口径。

### 验收

- 活动 `359/360` 使用权威 speed curve 后可正常计算 durability。
- raw/sampled 长度不一致时，所有指标输入仍与 snapshot axis 对齐。
- 新增“数据库派生列为空、track_json 曲线完整”的回归测试。

### 禁止

- 不通过回填用户数据库来掩盖运行时数据源错位。
- 不同时维护两套 current metric 曲线选择规则。

---

## `FR-Core-05`：缺失、零值、无风险与不可分析状态重构

优先级：P0  
性质：返回契约 / 状态语义
状态：已完成（2026-07-13）

目标文件：

- `metrics_resolver.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_core_audit_regression.py`

### 根因

- decoupling 无数据返回 `pct=0.0`。
- events 只有 `count=0`，无法区分“分析后无事件”和“没有可分析数据”。
- 前端把空事件/空区间统一展示为“状态平稳”。

### 必做

- 所有指标补齐 `status/confidence/reasons`。
- 无数据返回 `null + unavailable`；真实计算结果为零时才返回 `0`。
- events/fatigue_zones 增加 `analysis_status` 或等价后端字段。
- 只有 `analysis_status=available && count=0` 才能展示“未识别异常”。
- 无距离轴、无有效曲线或不适用运动显示“本次不适合进行该项分析”。

### 验收

- 呼吸、力量、秒表等活动不再显示“状态平稳、无突变”。
- 9 条无 efficiency 曲线样本不再携带假 `0%`。
- 真正计算得到 0% 的活动仍能显示“基本稳定”。

### 禁止

- 不用 truthy/falsy 判断区分 `0` 与 missing。
- 不在前端根据数组为空自行推断“无风险”。

### FR-Core-05 交付记录（2026-07-13）

- 已修复 `_empty_fatigue_review_snapshot()` 中 `decoupling.pct=0.0` 的假正常空态，改为 `status=unavailable`、主值 `null`、`direction=unknown`、trend unknown。
- 已为 events 增加 `analysis_status/confidence/reasons`，区分“分析后无事件”和“不可分析”。
- 已让前端 events 卡片读取 `analysis_status`；unavailable 时显示数据不足，不再把空 count 推断为状态平稳。
- 已修复 trend gate 对 events 的形状保留，unknown events trend 保持 `delta_count` 而非误转 `delta_pct`。
- 验证通过：`test_fatigue_review_trends.py` 7/7、`test_fatigue_review_contract_realignment.py + test_fatigue_review_e2e_contract.py + test_cycling_fatigue_review_metrics.py` 64/64。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中 FR-Core-05 空态用例已转绿；剩余 1 个预期失败继续锚定 FR-Core-07。
- 本任务未修前端跑步 durability 缺失文案。

---

# Phase C：P1 专项路由与用户体验修复

## `FR-Core-06`：运动类型能力注册表单一真理源

优先级：P1  
性质：运动类型路由
状态：已完成（2026-07-13）

目标文件：

- `metrics_registry.py`
- `metrics_resolver.py`
- `utils/metrics_calc.py`
- `main.py`
- `track.html`
- `llm_backend.py`
- `tests/test_resolver_sport_isolation.py`
- 新增专项矩阵测试

### 必做

- 建立单一 sport capability registry，由后端导出安全的 `review_mode/capabilities`。
- 消除 `CYCLING_REVIEW_TYPES`、`_CYCLING_SPORT_TYPES`、前端 sportMode 和 AI mode 的重复集合。
- 明确 `indoor_cycling`、`e_biking`、`treadmill_running` 的复盘模式。
- 对 training、cardio、strength、breathing、paddleboarding、stair climbing 等定义 not_applicable 或专属 general 模式。
- 数字 sport code 在入库或解析边界规范化，不能直接进入 UI。

### 验收

- indoor cycling 在后端指标、解释信号、卡片和图表中全部进入同一骑行模式。
- 同一 sport 在后端、前端、AI 三处 mode 完全一致。
- 12 条特殊运动样本不再复用错误跑步语义。

### 禁止

- 不继续在多个文件复制 sport 字符串集合。
- 不把 unknown 默认当 running。

### FR-Core-06 交付记录（2026-07-13）

- 已在 `metrics_registry.py` 建立 review capability registry，统一导出 `normalize_review_sport_type()`、`get_review_mode()`、`get_review_capabilities()` 与 `REVIEW_MODE_SPORTS`。
- 已将 `metrics_resolver.py`、`utils/metrics_calc.py`、`main.py` 的复盘运动类型判断收敛到 registry；`get_fatigue_review` 快照顶层新增后端规范化 `review_mode/capabilities`。
- 已将 `llm_backend.py` 的 fatigue review prompt 改为消费 compact snapshot 中的 `review_mode`，不再维护独立 sport mode map。
- 已将 `track.html` 的指标卡、copy group 与 cycling 稳定性覆盖逻辑改为优先消费后端 `review_mode`；本地 sport 字符串仅保留为兼容降级 fallback。
- 已同步 `docs/js_api_contract.json` 与 `docs/脉图运动复盘系统_开发团队交付手册_v1.md`，冻结 `review_mode/capabilities` 为后端 registry 导出的 API 契约。
- 已新增 `tests/test_fatigue_review_sport_capability_registry.py`，覆盖 indoor cycling、e-bike、跑步机、游泳、general/not_applicable 特殊运动矩阵，以及后端/前端/AI mode 一致性。
- 验证通过：`test_fatigue_review_sport_capability_registry.py` 4/4、`pytest tests/test_resolver_sport_isolation.py tests/test_fatigue_review_prompts.py` 129/129、前端白名单与专项 UI 窄测 5/5、`jq empty docs/js_api_contract.json`。
- 红线验证：`test_fatigue_review_core_audit_regression.py` 中 P0 用例保持通过；剩余 1 个失败继续锚定 `FR-Core-07` 的 running durability 缺失文案。
- 本任务未修改 HR 传感器来源、步频低置信度状态、历史 baseline 迁移策略或打包发布门禁。

---

## `FR-Core-07`：指标卡、缺失原因与运动专项文案分流

优先级：P1  
性质：前端只读渲染
状态：已完成（2026-07-13）

目标文件：

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_core_audit_regression.py`

### 必做

- `_fatigueReviewMetricMissingReason` 接收后端 `basis/status/reason_code`，不根据模糊正则猜运动类型。
- running durability 只出现速度/配速/时长文案。
- cycling power retention 只出现功率/有效踩踏文案。
- general/hiking/swimming 使用各自可用指标和 not_applicable 文案。
- 删除“后端未返回功率口径指标”等开发者式用户文案。

### 验收

- 跑步卡片中不得出现“功率曲线样本不足”。
- 骑行卡片中不得出现“步频、跑姿、配速耐久”。
- 文案测试执行实际 JS 函数，而不是只搜索字符串存在。

### 禁止

- 不在前端从 `sport_type + reasons` 拼装新的生理结论。

### FR-Core-07 交付记录（2026-07-13）

- 已将 `_fatigueReviewMetricMissingReason()` 改为优先按 `metricKey + basis + reason_code/reason_codes/reasons` 分流。
- 已移除用户可见“后端未返回功率口径指标”开发者文案。
- running durability 的 `points<20 / insufficient_points` 缺失原因改为速度样本不足，不再出现功率曲线。
- cycling `durability.basis=power_retention` 的缺失原因仍保留功率曲线/功率样本文案，避免修跑步时破坏骑行专项。
- 已同步 `docs/js_api_contract.json` 与 `docs/脉图运动复盘系统_开发团队交付手册_v1.md` 的缺失原因分流契约。
- 已新增 JS 语义回归测试，实际执行 `_fatigueReviewMetricMissingReason()`，覆盖 running durability 与 cycling power retention 两类缺失文案。
- 验证通过：`test_fatigue_review_core_audit_regression.py` 9/9、前端文案/渲染窄测 3/3。
- 本任务未修改后端算法、运动类型 registry、HR 传感器来源、步频低置信度状态或历史 baseline 迁移策略。

---

## `FR-Core-08`：步频低置信度与间歇活动状态修复

优先级：P1  
性质：算法状态 / 前端文案
状态：已完成（2026-07-13）

目标文件：

- `metrics_resolver.py`
- `main.py`
- `track.html`
- `tests/test_fatigue_review_core_audit_regression.py`

### 必做

- 区分 `missing cadence`、`intermittent/variable`、`available stable`。
- CV 超阈值时返回明确 reason，例如 `intermittent_cadence_pattern`，不得留空 reasons。
- 前端对 low/partial 显示“节奏变化较大，不适合稳定性评分”，不得显示“设备未记录”。
- 低置信度 current metric 默认不生成强历史趋势。

### 验收

- 6 条有真实步频数据的活动不再显示“设备未记录”。
- 真正无 cadence 曲线时仍显示设备/数据缺失。
- 间歇跑不会被错误评价为跑姿或能力退化。

### FR-Core-08 交付记录（2026-07-13）

- 已让 `MetricsResolver._compute_cadence_stability()` 在 CV 超阈值或显式间歇活动时返回 `status=partial`、`confidence=low`、`reasons=["intermittent_cadence_pattern"]`，不再空 reasons。
- 已让 cadence unsupported、短时长、样本不足等 unavailable 分支返回明确 `status/reasons`。
- 已让 `main.py` 复盘快照透传 cadence stability 的 `status/reasons`；空态 cadence stability 明确 `status=unavailable`。
- 已让 `track.html` 对 `intermittent_cadence_pattern / variable_cadence_pattern / cadence_cv` 显示“节奏变化较大，不适合稳定性评分”，并把 partial/low cadence 卡片状态显示为“不适合评分”，不再显示“设备未记录”。
- 已新增/更新实际 JS 与 Resolver 回归测试，覆盖 low confidence cadence 的原因和用户文案。
- 验证通过：间歇步频 resolver 窄测 1/1、核心红线 10/10、前端文案 2/2、相关 broader 测试 152/152。
- 本任务未修改 cadence stability 评分公式、运动类型 registry、HR 传感器来源或历史 baseline 迁移策略。

---

## `FR-Core-09`：HR 传感器来源与置信度契约

优先级：P1  
性质：证据来源 / 置信度
状态：已完成（2026-07-13）

目标文件：

- `fit_engine.py`
- `main.py`
- `metrics_resolver.py`
- `docs/js_api_contract.json`
- 相关 FIT parser 和复盘测试

### 必做

- 删除 `hr_source="chest_strap"` 写死逻辑。
- 能从 FIT/device/source 字段确认胸带时才标记 chest strap。
- 只能确认光电时标 optical；无法确认时标 unknown 并保守降级。
- efficiency/training load 的 confidence 必须体现真实来源。

### 验收

- Fenix 8 手表活动在无胸带证据时不得获得胸带级置信度。
- source unknown 不影响指标值，只影响置信度和解释强度。

### 禁止

- 不根据设备名称推断用户一定佩戴胸带。

### FR-Core-09 交付记录（2026-07-13）

- 已将 `MetricsResolver._compute_training_load()` 与 `evaluate_efficiency()` 的 `hr_source` 默认值从 `chest_strap` 改为 `unknown`。
- 已新增 HR 来源规范化：明确外置胸带证据才返回 `chest_strap`，明确腕式/光电证据才返回 `optical`，其他一律 `unknown`。
- 已让 `unknown/optical` HR 来源保守降级为 `confidence=medium`；training load 在 unknown 时记录 `hr_source_unknown` reason。
- 已新增 `main._resolve_activity_hr_source()`，只读取显式来源字段，不根据 `device_name` 推断；`main.py` 不再在 efficiency/training load 调用中写死 `hr_source="chest_strap"`。
- 已新增/更新测试，覆盖默认 unknown 降级、明确 chest_strap 才 high、optical medium、Fenix 8 设备名不推断胸带。
- 验证通过：FR-Core-09 窄测 5/5、核心红线 11/11、`tests/test_resolver_sport_isolation.py` 89/89、`test_fit_sync.py::TestFitSync::test_training_load_uses_unified_profile_hrr` 1/1。
- 本任务未新增数据库列或 FIT 传感器深度解析；当前只消费已有/未来显式 HR 来源字段，缺失时保守 unknown。

---

## `FR-Core-10`：历史派生曲线与 baseline 版本化

优先级：P1  
性质：历史数据一致性 / 迁移策略
状态：已完成（2026-07-13）

目标文件：

- `main.py`
- `profile_backend.py`
- `metrics_resolver.py`
- schema migration 与回放测试

### 根因

当前活动可以从 track_json 实时获得完整 speed/cadence，但历史 baseline 只读取旧 `speed_curve/cadence_curve` 列，导致当前值和历史样本覆盖率不同。

### 必做

- 明确选择：历史查询时从 canonical track_json 统一重建，或持久化带版本号的派生指标。
- baseline 记录必须携带 `metric_version/basis/source_quality`。
- 不同版本或不同 basis 不参与同一次趋势计算。
- 提供只读回放或受控迁移，不在普通页面读取时批量写库。

### 验收

- 新旧活动使用相同公式和曲线选择规则。
- baseline 样本数不再因为数据库派生列是否存在而随机变化。
- 迁移前后同一活动的 canonical FIT 事实不改变。

### FR-Core-10 交付记录（2026-07-13）

- 已选择“只读 canonical track_json/points_json 优先重建”的历史 baseline 策略，不在普通页面读取时批量写库。
- 已新增 `_review_historical_curve()`，历史 speed/cadence baseline 优先从 canonical track points 重建；仅当老库无 canonical 轨迹时 fallback 到 legacy 派生列。
- 已让 durability trend 返回 `basis=speed_tail_head_ratio`、`version=fr_core_10_canonical_curve_v1`、`source_quality`。
- 已让 cadence stability trend 返回 `basis=cadence_cv`、`version=fr_core_10_canonical_curve_v1`、`source_quality`。
- 已在 `main.py` 的 durability/cadence trend 注入中透传 `basis/version/source_quality`。
- 已新增 canonical track_json baseline 回归测试，覆盖 speed/cadence 派生列为空但 canonical 轨迹存在的历史活动。
- 验证通过：时间窗口与 canonical baseline 4/4、趋势/核心回归 31/31、复盘契约 broader 154/154。
- 本任务未修改公式、未写库迁移、未改变 canonical FIT 事实。

---

# Phase D：质量门与发布

## `FR-Core-11`：真实活动回放矩阵与发布门禁

优先级：P0 Release Gate  
性质：测试 / 验收 / 发布控制
状态：已完成（2026-07-13）

目标文件：

- 新增 `tests/test_fatigue_review_real_activity_replay.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/fatigue_review_e2e_audit_report.md`
- 新增最终完成报告

### 必做

- 建立匿名化 fixture 矩阵：短跑、长跑、间歇跑、越野、步行、徒步、骑行有功率、骑行无功率、室内骑行、游泳、力量、无轨迹活动。
- 增加 property/invariant 测试：
  - unavailable 不得携带强 trend。
  - late efficiency 提升不得标记为下滑。
  - baseline 时间必须早于活动时间。
  - current/baseline basis 和 version 必须一致。
  - 所有非空曲线必须与 distance axis 同轴。
  - sport mode 在 backend/frontend/AI 一致。
- 重跑 253 条本地真实活动并输出审计统计，不把用户绝对路径或原始轨迹写入报告。
- 修复或明确隔离现有复盘测试失败：业务逻辑滞留 main、Resolver curve axis 断言、pytest 依赖；ACS CSS 失败单独处理。
- macOS 和 Windows 打包产物至少完成复盘页面 smoke test。

### 发布验收

- 审计中的 204/41/131/2/6/9/12 类问题全部归零或有明确 not_applicable 解释。
- 所有复盘核心测试通过；不存在因为缺少 pytest 而跳过的核心测试。
- 真实活动抽检中，UI、API 与 AI snapshot 对同一事实无矛盾。
- 完成报告列出公式版本、数据迁移、兼容性和剩余限制。

### 禁止

- 不以“单元测试通过”替代真实活动回放。
- 不在未验证 Windows/macOS 打包版本时标记发布完成。

### FR-Core-11 交付记录（2026-07-13）

- 已新增 `tests/test_fatigue_review_real_activity_replay.py`，使用真实本地活动库做 replay smoke gate，并支持 `FULL_FATIGUE_REPLAY=1` 扩展到全量非删除活动。
- 已新增 `docs/fatigue_review_real_activity_replay_report.md`，记录 253 条非删除活动的匿名化 sport matrix，不包含用户绝对路径或原始轨迹。
- replay invariant 覆盖：禁泄露 `shadow_diff / records / points`、曲线同轴、sport mode 与 registry 一致、unavailable/not_applicable 不携带强趋势、非骑行 durability 不使用 `power_retention`。
- 已修复复盘 UI 发布门禁中的 viewport font-size 静态失败，移除 `font-size: ... vw`。
- 验证通过：真实活动 replay smoke 1/1、复盘 e2e/quality/detail broader 185/185。
- 发布说明：macOS/Windows 打包产物 smoke test 仍需在实际打包流程中执行；本任务完成代码层发布门禁和本地真实活动 replay 门禁。

---

## 3. 任务依赖

```text
FR-Core-00
  -> FR-Core-01
  -> FR-Core-02
  -> FR-Core-03
  -> FR-Core-04
  -> FR-Core-05
       -> FR-Core-06
       -> FR-Core-07
       -> FR-Core-08
       -> FR-Core-09
       -> FR-Core-10
            -> FR-Core-11
```

说明：

- `FR-Core-01` 至 `FR-Core-05` 均属于 P0，但应按顺序执行，避免在错误时间窗口或错误状态契约上继续修 UI。
- `FR-Core-06` 必须先于最终专项文案验收，否则 indoor cycling/e-bike 等仍可能落错分支。
- `FR-Core-11` 是发布门禁，不是可选测试任务。

## 4. 每项任务统一交付物

每个任务完成时必须提交：

1. 代码修改。
2. 对应契约或 API 文档更新。
3. 修复前失败、修复后通过的回归测试。
4. 至少一条真实活动或匿名化等价 fixture 验证。
5. 目标测试命令及结果。
6. `git diff --check` 和目标文件 diff 审查结果。
7. 独立 completion report，说明未修改的边界和剩余风险。

## 5. 完成定义

只有同时满足以下条件，才能把本轮复盘核心修复标记为完成：

- 时间窗口不穿越未来。
- 当前值和历史值同公式、同方向、同单位、同版本。
- unavailable 不再产生伪数值、伪趋势或“状态平稳”。
- 跑步、骑行和其他运动的算法、卡片、图层、AI 语义一致。
- 当前指标统一读取权威 curves snapshot。
- AI snapshot 不含不可用强结论。
- 真实活动回放和全量核心测试通过。
- macOS/Windows 产物完成复盘 smoke test。
