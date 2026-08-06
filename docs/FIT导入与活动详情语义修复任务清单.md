# FIT 导入与活动详情语义修复任务清单

---
title: FIT 导入与活动详情语义修复任务清单
version: v0.1.0
status: Planning
type: Ordered Engineering Task List
updated: 2026-08-05
---

本文档把本轮已确认的问题落盘为可执行任务。当前只记录任务范围，不直接修改业务代码。

## 1. 已确认根因

- 百锐腾 FIT 本身包含心率和功率事实：session 有平均心率 `129 bpm`、平均功率 `189 W`、最大功率 `637 W`；lap 也包含心率和功率。
- 百锐腾部分 record 只有传感器字段、没有 GPS。当前 FIT 轨迹解析只保留带经纬度的 record，导致部分心率/功率点没有进入轨迹曲线。
- 详情骑行圈表读取 `avg_power`、`avg_speed_mps` 等新字段，但真实圈转换结果仍主要输出 `power_w` 等旧字段，造成圈表显示 `--`。
- 外部影响卡片把后端内部的运动类型解释校准句直接作为用户可见 comment 输出，产生“结论应比跑步同温场景更保守”等工程语言。
- FIT 导入完成后的 `_apply_title_override()` 无条件把活动标题改成文件名，绕过了既有的标题来源保护，可能覆盖前面已经生成的运动类型/地区标题、真实文件名/赛事名，甚至已有用户标题；第 4 项不能通过简单删除覆盖步骤或统一改成自动标题来修复。
- `Unknown Device` 是设备产品映射未命中的独立问题，不是本轮指标丢失或标题覆盖的根因。

## 2. 总原则

- 前端只能消费后端和 FIT 中真实存在的事实，不从截图、DOM、曲线形状或缺失值推断心率、功率、设备和标题。
- 不为百锐腾增加一条设备专属例外；按 FIT 标准字段和记录能力修复，迈金、百锐腾、佳明等设备共用同一套契约。
- 不为没有 GPS 的传感器记录伪造经纬度。轨迹点和传感器采样可分离保存或进入明确的曲线数据结构。
- 保留旧字段兼容读取，但新增字段必须有明确生产者、消费者和测试覆盖。
- 自动标题、用户手动标题和原始文件名必须区分；用户手动标题不得被导入或地区回填覆盖。
- 标题解析候选、持久化标题和列表/详情展示标题必须区分；展示层优先消费持久化 `activities.title`，文件名只能在标题为空时兜底。
- 用户可见文案不得暴露内部阈值、跨运动校准、置信度推理过程或实现策略。
- 每个任务开始前执行 `git status --short`，保留现有脏工作区改动；每个任务结束运行聚焦测试和 `git diff --check`。

## 3. 任务总览

| 顺序 | 任务 | 状态 | 主要交付物 |
| --- | --- | --- | --- |
| 1 | FIT 传感器事实保留 | `Planned` | 百锐腾无 GPS 传感器数据不再静默丢失 |
| 2 | 骑行圈字段契约对齐 | `Planned` | 平均速度、平均/最大功率、NP、爬升正确展示 |
| 3 | 外部影响用户文案修正 | `Planned` | 用户可理解、事实边界清晰的骑行热环境文案 |
| 4 | 导入标题覆盖逻辑修正 | `Planned` | 有效活动标题不再被导入末尾的原始文件名无条件覆盖 |
| 5 | 全链路回归与设备样本验收 | `Planned` | 百锐腾、迈金、佳明兼容性回归证据 |

## 4. Task 1：FIT 传感器事实保留

优先级：P0  
性质：FIT 解析契约 / 数据完整性  
前置：无

### 目标

保留没有 GPS 坐标但包含心率、功率、踏频、时间等有效传感器事实的 FIT record，同时不制造虚假轨迹点。

### 允许改动文件

- `fit_engine.py`
- `main.py`，仅限导入结果组装和曲线/传感器事实透传
- `docs/js_api_contract.json`
- 新增或更新 `tests/test_fit_parser.py`、`tests/test_detail_api_columns.py` 或等价聚焦测试

### 执行项

- [ ] 明确轨迹点字段与传感器采样字段的分离契约。
- [ ] 对没有经纬度但有有效 timestamp + HR/power/cadence 的 record，保留可追溯的传感器事实。
- [ ] 不为缺少 GPS 的 record 补写 `lat`、`lon`，不改变轨迹地图的坐标有效性规则。
- [ ] 确保 session/lap 汇总值仍优先使用 FIT 原生字段。
- [ ] 处理空值、无效值和暂停/停止期间的零功率，避免把无效值当成丢失或异常功率。
- [ ] 同时验证百锐腾和迈金：迈金原有逐点曲线不能回归，百锐腾传感器点数量应明显增加或有明确降级状态。

### 验收

- [ ] 百锐腾原始 FIT 的 session/lap 汇总值与当前已确认值一致。
- [ ] 百锐腾的有效心率/功率采样不因缺 GPS 被静默丢弃。
- [ ] 轨迹点仍全部具备合法经纬度。
- [ ] 迈金样本的 HR、功率、踏频和曲线长度不回归。
- [ ] 测试能区分“无 GPS 的有效传感器采样”和“没有任何有效训练事实”。

## 5. Task 2：骑行圈字段契约对齐

优先级：P0  
性质：后端 view model / 前端展示契约  
前置：Task 1 可并行，但必须先冻结字段名

### 目标

让 FIT lap 的真实字段完整进入详情页骑行圈表，解决截图中的平均速度、平均功率、最大功率和爬升显示 `--`。

### 允许改动文件

- `metrics_resolver.py`
- `track.html`
- `main.py`，仅限详情 API 字段组装
- `docs/js_api_contract.json`
- 新增或更新 `tests/test_activity_detail_multi_sport_capabilities.py`、`tests/test_detail_api_columns.py` 及 FIT 圈数据聚焦测试

### 执行项

- [ ] 在真实圈 view model 中输出前端读取的 `elapsed_sec`、`avg_speed_mps`、`avg_power`、`max_power`、`normalized_power`、`total_ascent` 等字段。
- [ ] 保留 `power_w` 等旧字段的兼容读取，避免历史数据或 mock 夹具断裂。
- [ ] 平均速度使用 FIT lap 的 `enhanced_avg_speed` / `avg_speed`，不得从错误单位字段重复换算。
- [ ] NP 明确区分 session 级和 lap 级：没有 lap 原生 NP 时，圈表显示缺失；不得把 session NP 伪装成每圈 NP。
- [ ] 验证骑行 Hero 或摘要区域使用数据库真实的 `avg_power=189 W`、`normalized_power=230 W`，不因圈表修复重复计算或覆盖。
- [ ] 真实 FIT 圈、自动切圈和 mock fallback 的 `source_type` 规则保持不变。

### 验收

- [ ] 百锐腾 8 个真实 lap 显示圈用时、平均速度、平均心率、平均功率、最大功率和累计爬升。
- [ ] 百锐腾 lap 没有原生 NP 时，NP 显示 `--`，但顶部/摘要仍可显示 session 级 `230 W`。
- [ ] 迈金单圈样本显示其真实平均速度、心率、平均/最大功率和爬升。
- [ ] 不以 DOM 或曲线推导功率；无功率数据时仍显示缺失状态。
- [ ] 前端字段名与后端 view model 有单一映射测试。

## 6. Task 3：外部影响用户文案修正

优先级：P1  
性质：后端 canonical 文案 / 用户语义  
前置：无

### 目标

保留骑行 `30.4°C` 的热环境事实判断，但将工程化的跨运动校准说明改成用户可直接理解的中文。

### 允许改动文件

- `main.py`
- `tests/test_fatigue_review_environment_factors_contract.py`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_quality_gate.py`
- 必要时更新 `docs/js_api_contract.json` 中 comment 语义约束

### 执行项

- [ ] 删除或改写“结论应比跑步同温场景更保守”等内部工程表达。
- [ ] 文案只说明事实支持的影响：气温较高、骑行需关注散热和补水；不暗示未观测到的实际热应激结果。
- [ ] 保留骑行与跑步的运动语义差异，但通过用户语言表达，不展示阈值校准过程。
- [ ] 明确 `environment_context` 是事实层，`environment_factors.comment` 是用户解释层。
- [ ] 无环境因素时保留已有天气但未识别明显压力的清晰空态。

### 验收

- [ ] 当前骑行记录不再出现“比跑步同温场景更保守”或同义工程句式。
- [ ] 文案能回答“为什么提示热环境压力”，并能追溯到温度事实。
- [ ] 不凭温度单独输出“已经发生热应激”“心率一定上浮”等结论。
- [ ] 跑步、骑行、高湿和无天气场景的语义测试均通过。

## 7. Task 4：标题规则冻结与导入覆盖逻辑修正

优先级：P0  
性质：标题来源契约 / 导入生命周期 / 回填保护  
前置：无

### 目标

在不破坏既有复杂命名规则的前提下，阻止导入末尾的无条件文件名覆盖，并确认百锐腾、迈金、Garmin、COROS、手动 FIT/ZIP 导入共用正确的标题来源优先级。

### 必须先冻结的标题规则

实现前必须用现有代码和测试确认下列来源矩阵，不得凭本任务标题问题重新发明命名策略：

现有链路的语义边界也必须保留：FIT 解析器先从清洗后的文件名、FIT 运动类型名、session label 和文件名兜底中产生候选；`build_activity_display_title()` 再判断候选是否为技术标题并决定运动类型/地区自动标题；地区回填只允许更新自动标题或已确认的技术标题；列表和详情优先读取已持久化标题。导入末尾的修复步骤不得绕过这条链路。

| 标题来源 | 含义 | 是否允许导入覆盖 | 是否允许地区回填覆盖 |
| --- | --- | --- | --- |
| `user` / `manual` / `edited` | 用户明确编辑的标题 | 否 | 否 |
| `auto_region_sport` | 后端根据地区和运动类型生成 | 仅在新解析仍是低信息自动标题时保留旧值 | 是，仅限自动标题链路 |
| `auto_sport` | 后端根据运动类型生成 | 允许在规则明确需要补地区时升级，不得降级为文件名 | 是 |
| `filename` | 文件名派生标题，可能是真实赛事/路线名，也可能是技术文件名 | 只有确认是技术文件名时才可修复 | 只有确认是技术文件名时才可修复 |
| `sport_name` / `session_label` / `file_name` / `fit` | FIT 原始标题候选或历史兼容来源，不能仅凭 source 名称判断其最终语义 | 必须先经过 `build_activity_display_title()` 判定 | 不得直接覆盖真实可读标题 |

特别约束：`title_source='filename'` 不是“可以覆盖”的同义词。真实文件名如赛事名、路线名或用户有意保留的文件名，必须优先于地区+运动自动标题；技术性 provider 文件名、纯 ID、哈希名和 `activity-fit-files...` 才能进入修复候选。

特别验收约束：不能把“删除 `_apply_title_override()`”当作完整修复。必须单独验证 `file_name` 兜底、纯数字文件名、provider 设备名 + ID + 时间文件名和带 `.fit` 的技术候选如何进入最终标题；不能因为文件名清洗成功，就把清洗结果自动等同于最终活动标题，也不能仅凭 `title_source='file_name'` 或 `title_source='filename'` 做一刀切判断。

### 允许改动文件

- `main.py`
- `profile_backend.py`，仅限标题来源和技术文件名清洗逻辑
- `tests/test_fit_sync.py`
- 必要时更新标题字段合同文档

### 执行项

- [ ] 先阅读并以现有测试为基线：`build_activity_display_title()`、`backfill_auto_activity_titles()`、`_can_region_update_activity_title()`、`_persist_sync_activity()`、`_build_activity_list_item()`、`update_activity_title()` 及 FIT/ZIP 两条导入分支。
- [ ] 移除或收紧 `_apply_title_override()` 的无条件覆盖行为；不得直接把 `activities.title` 写成文件名。
- [ ] 若保留导入后修复步骤，必须读取当前 `title` 与 `title_source`，只对空标题、已判定技术性标题或确认编码损坏的标题调用既有标题构建逻辑。
- [ ] 不得把所有数字标题、所有 provider 文件名或所有 `title_source='filename'` 都粗暴判为技术标题；需用最小分类函数和测试矩阵证明判定。
- [ ] 保留 `user`、`manual`、`edited` 标题，任何重新导入或地区回填都不得覆盖。
- [ ] 保留有效的 `auto_sport` / `auto_region_sport` 标题，不将其降级为 `filename`。
- [ ] 对 `260805055744.fit` 和 `Magene_C706...fit` 验证：最终标题由冻结后的规则决定，且导入末尾不再把已有自动标题无条件改成 `filename`。
- [ ] 对文件名中的 provider activity id 保留清洗规则，但不把清洗后的文件名自动等同于最终活动标题。
- [ ] 记录并测试真实样本的“解析候选 -> `build_activity_display_title()` -> 入库标题 -> 列表/详情标题”链路；百锐腾当前解析候选为 `260805055744.fit` / `file_name`，迈金当前解析候选包含设备名、时间和 ID 片段，最终标题不得由覆盖步骤直接决定。
- [ ] 验证直接 FIT 导入、ZIP 内 FIT 导入、远程 provider 同步、地区回填、活动列表展示和详情展示的标题来源保持一致。
- [ ] 验证语义去重/重新导入路径不会因为标题修复改变查重键、Activity 归属或用户标题。

### 验收

- [ ] 百锐腾导入后不再被无条件写成 `260805055744`；最终显示值符合已冻结的技术名/真实文件名/自动标题矩阵。
- [ ] 迈金导入后不再被无条件写成 `Magene_C706`；最终显示值符合已冻结的技术名/真实文件名/自动标题矩阵。
- [ ] 用户手动改名后再次同步，标题保持用户版本。
- [ ] 技术性文件名仍能被清洗或回退到合理的运动标题。
- [ ] 真实赛事名、路线名和用户可读文件名不被回退成地区+运动标题。
- [ ] 历史记录回填只修复技术性标题，不批量覆盖真实用户标题或真实文件名标题。
- [ ] 列表和详情均优先读取持久化 `activities.title`，仅在标题为空时使用清洗后的文件名兜底。

## 8. Task 5：全链路回归与设备样本验收

优先级：P0  
性质：集成回归 / 发布门禁  
前置：Task 1、Task 2、Task 3、Task 4

### 允许改动文件

- 聚焦 FIT、详情、复盘和标题测试文件
- 必要的 fixture 文件
- 本任务清单执行记录

### 验收样本

- [ ] `/Users/fanglei/Desktop/260805055744.fit`：百锐腾骑行。
- [ ] `/Users/fanglei/Desktop/tracks/MAGENE_C706_2026-06-28_154456_196852.fit`：迈金骑行。
- [ ] 至少一个 Garmin Fenix 8 骑行或跑步样本，确认既有标题、功率和设备显示不回归。

### 推荐验证命令

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fit_parser.py \
  tests/test_activity_detail_multi_sport_capabilities.py \
  tests/test_detail_api_columns.py \
  tests/test_fatigue_review_environment_factors_contract.py \
  tests/test_fatigue_review_snapshot_realignment.py \
  tests/test_fatigue_review_quality_gate.py \
  tests/test_fit_sync.py -k 'title or filename or region' -q

PYTHONPATH=. .venv312/bin/python -m py_compile \
  fit_engine.py metrics_resolver.py main.py profile_backend.py

git diff --check
```

### 完成标准

- [ ] 三类设备的 FIT 汇总、圈数据、曲线和标题均有证据。
- [ ] 百锐腾传感器事实不因 GPS 缺失静默丢弃。
- [ ] 骑行详情页不再把已有的平均速度/功率显示成 `--`。
- [ ] 外部影响文案不出现工程解释句。
- [ ] 有效活动标题不被导入末尾的文件名无条件覆盖。
- [ ] `Unknown Device` 若仍存在，作为独立设备映射任务记录，不阻塞本清单其余验收。

## 9. 非目标与独立遗留

- 不在本清单内修复 `Unknown Device` 的完整产品映射表；该问题另立设备识别任务。
- 不修改 FIT 文件本身，不回写第三方设备数据。
- 不通过单独判断 `bryton` 或 `magene` 增加厂商特例。
- 不重构完整轨迹存储模型，不改变地图坐标合法性。
- 不扩展 AI 自由推理；AI 继续只解释后端已确认的环境因素。

## 10. 执行记录

- 文档创建时间：2026-08-05
- 当前状态：`Planning`
- 代码修改：本轮未修改业务代码
- 待开始：Task 1
