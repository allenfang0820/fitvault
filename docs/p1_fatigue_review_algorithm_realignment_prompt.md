# P1 运动复盘算法链路回正提示词

> 任务类型：P1 算法链路回正
> 核心目标：废弃伪 records，改用真实 FIT / DB canonical 数据构建复盘算法输入
> 前置条件：P0 数据契约回正已完成，`get_fatigue_review(activity_id)` 已声明后端权威 `curves.distance/time/altitude` 等字段
> 不包含：前端草图还原、AI 洞察接入、DB schema 大迁移

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p0_fatigue_review_contract_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review` 契约
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 脉图是本地 AI 运动外挂，不引入 SaaS、微服务、消息队列、Feature Store、云计算节点。
- 数据流必须遵循 FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- Resolver 是唯一语义翻译层，复盘算法必须优先收敛到 Resolver 或专用算法层。
- `main.py` 只做 API 编排、快照白名单、错误降级，不承载核心复盘算法。
- 前端只展示，不生成事实指标。本任务不得修改 `track.html` 来补算法。
- AI 洞察留到 P6，本任务不得接入或修复 `__FATIGUE_REVIEW_INSIGHT__`。
- `shadow_diff`、`shadow_diff_json`、`diff`、原始 records、全量 points 禁止进入 API data 与 AI 输入。
- canonical DB 只读，不写入 synthetic / mock / AI 生成指标。

---

## 一、任务背景

当前复盘链路中 `_build_resolved_payload_v81()` 使用 `hr_curve/speed_curve` 构造 minimal `record_mesgs`，存在以下偏离：

- 固定 `altitude=100.0`，导致坡度 `grade_curve` 基本退化为 0，GAP 无法体现真实爬升/下降。
- 固定 `dt=1s`，用 `sum(speed * dt)` 伪造距离，无法保证与 FIT / DB canonical 距离一致。
- `session_mesgs=[{}]` 不含真实 calories，导致 bonk 事件系统性漏判。
- 没有真实 `distance_curve / altitude_curve / timestamp/time / calories` 输入，fatigue_zones 和 collapse_events 难以与 P0 契约中的 `curves.distance` 同源。

P1 的目标是先把算法输入链路回正，让复盘算法消费真实 FIT / DB canonical 数据，而不是继续依赖伪 records。

---

## 二、任务目标

完成 P1 算法链路回正：

1. 梳理当前 DB / `track_json` / Resolver 中真实可用的 canonical 数据来源。
2. 定义复盘算法使用的 canonical curve bundle。
3. 废弃 `_build_resolved_payload_v81()` 中伪造 altitude、固定 dt、空 session 的方案。
4. 让 GAP、grade、efficiency、fatigue_zones、bonk_events 使用真实或可追溯的输入。
5. 确保 `_detect_bonk_event()` 接收真实 calories，并显式传入 `sport_type`。
6. 确保 fatigue_zones 的距离坐标与后端 `curves.distance` 同源。
7. 新增 P1 算法链路契约测试。

---

## 三、必须先调查的数据来源

正式改代码前，先完成数据来源调查，不得跳过：

### 1. activities 表字段

检查是否已有：

- `hr_curve`
- `speed_curve`
- `cadence_curve`
- `altitude_curve`
- `distance_curve`
- `track_json`
- `points_json`
- `merged_track_json`
- `duration` / `duration_sec`
- `distance` / `dist_km`
- `calories`
- `sport_type`

### 2. track_json 点结构

抽样确认每个点是否含：

- `timestamp` 或可推导的时间序列
- `distance` / `distance_m` / `dist_m`
- `altitude` / `altitude_m` / `ele`
- `speed` / `speed_mps`
- `heart_rate` / `hr`
- `cadence`
- 经纬度字段

### 3. Resolver / GapCalculator 已有输出

确认：

- `MetricsResolver.resolve()` 是否已输出 `distance_curve`、`altitude_curve`、`hr_curve`、`speed_curve`、`gap_curve`、`efficiency_curve`、`fatigue_zones`。
- `GapCalculator.calculate(records)` 是否可基于真实 records 输出 `grade_curve`、`gap_curve`、`efficiency_curve`。
- `MetricsResolver._calculate_fatigue_zones()` 是否已经只依赖 `distance_curve + efficiency_curve + sport_type`。
- `MetricsResolver._detect_bonk_event()` 当前是否缺少 `sport_type` 调用传参。

调查输出必须写入完成报告。

---

## 四、目标 canonical curve bundle

P1 需要构造一个后端内部使用的 canonical curve bundle，字段建议如下：

```python
{
    "distance_curve_m": [],
    "time_curve_sec": [],
    "hr_curve": [],
    "speed_curve_mps": [],
    "altitude_curve_m": [],
    "cadence_curve": [],
    "calories": 0.0,
    "duration_sec": 0,
    "total_distance_m": 0.0,
    "sport_type": "running",
    "source": "fit_sdk|canonical_db|track_json",
}
```

要求：

- `distance_curve_m` 必须来自 FIT / DB canonical 或 `track_json` 中真实累计距离。
- 若某 FIT 不含逐点 distance，但有经纬度，可在后端算法层明确标记为降级来源；P1 不得让前端补算。
- `time_curve_sec` 必须来自 timestamp 差值或后端统一采样策略。
- `altitude_curve_m` 必须来自真实海拔字段；缺失时返回空数组，不得固定 `100.0`。
- `calories` 必须来自活动主表 / FIT session，缺失则标记 unavailable，不得默认为可触发 bonk 的 synthetic 值。
- `sport_type` 必须全链路传入 sport-aware 算法。

---

## 五、允许修改的文件

优先修改：

- `main.py`
- `metrics_resolver.py`
- `tests/test_fatigue_review_resolver_realignment.py`

必要时修改：

- `gap_calculator.py`
- `tests/test_fatigue_zones_resolver.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `docs/fatigue_review_realignment_plan_v1.md`

禁止或暂缓修改：

- `track.html`：P1 不做前端展示回正。
- `llm_backend.py`：P1 不做 AI 洞察。
- DB schema migration：除非调查证明现有 canonical 数据完全不足，并需单独提出迁移方案。

---

## 六、实施步骤

### Step 1：数据来源调查

执行静态和最小运行时调查：

- 查找 activities 表读取逻辑和 `_fetch_activity_row()` 返回字段。
- 查找 `track_json` 解码函数和点结构。
- 查找 Resolver 中曲线构建函数。
- 输出“可用字段矩阵”：字段、来源、单位、是否可信、缺失策略。

### Step 2：新增 canonical bundle 构建函数

建议新增后端内部函数，命名可按现有风格调整：

```python
def _build_fatigue_review_curve_bundle(row: dict) -> dict:
    ...
```

职责：

- 从 DB canonical 字段或 `track_json` 提取真实曲线。
- 统一曲线长度。
- 输出 `distance_curve_m / time_curve_sec / hr_curve / speed_curve_mps / altitude_curve_m / cadence_curve / calories / duration_sec / total_distance_m / sport_type`。
- 不写 DB。
- 不返回原始 records 到 API data。

### Step 3：替换伪 records 链路

替换或废弃 `_build_resolved_payload_v81()` 的伪造逻辑：

- 禁止固定 `altitude=100.0`。
- 禁止固定 `dt=1s` 作为真实时间来源。
- 禁止 `session_mesgs=[{}]` 导致 calories 缺失。
- 禁止通过 `speed * dt` 伪造 canonical 距离。

可选做法：

- 新增 `_build_resolved_payload_from_bundle(bundle)`。
- 将真实 bundle 转成 Resolver / GapCalculator 需要的内部 records。
- records 仅作为后端内部算法适配结构，不暴露给 API data。

### Step 4：修正 sport-aware bonk 调用

确保 `MetricsResolver.resolve()` 或新链路中调用：

```python
MetricsResolver._detect_bonk_event(
    distance_curve=distance_curve,
    ei_curve=efficiency_curve,
    total_calories=total_calories,
    sport_type=sport_type,
)
```

验收重点：

- bonk 不再因为空 session calories 系统性漏判。
- 不同运动类型走 `_GLYCOGEN_RISK_ZONES` 阈值。

### Step 5：输出后端权威曲线

让 `_build_fatigue_review_snapshot(row)` 的 `curves` 至少能从 P1 链路拿到：

- `distance`：由 `distance_curve_m` 转 km。
- `time`：由 `time_curve_sec` 输出秒。
- `altitude`：真实海拔曲线。
- `grade`：真实 altitude + distance 计算结果。
- `gap`：真实坡度修正结果。
- `efficiency`：真实 HR + speed/GAP 结果。

如某字段缺失：

- 返回空数组。
- 保留 `total_distance_m`。
- 不用 synthetic 默认值冒充真实曲线。

### Step 6：新增测试

新增 `tests/test_fatigue_review_resolver_realignment.py`，至少覆盖：

- 源码中 `_build_resolved_payload_v81` 不再包含 `altitude": 100.0` 或 `altitude': 100.0`。
- 源码中不再包含 `session_mesgs": [{}]` 或 `session_mesgs': [{}]` 作为复盘算法主路径。
- bundle 空态不包含 forbidden 字段。
- 真实 altitude 输入时 `grade_curve` 不应系统性全 0。
- 真实 calories 输入时 bonk 检测能收到非 0 calories。
- `_detect_bonk_event()` 调用显式传入 `sport_type`。
- `fatigue_zones` 的距离来源与 `curves.distance` 同源。

可继续运行既有测试：

```bash
python -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py tests/test_fatigue_zones_resolver.py
```

---

## 七、验收标准

完成后必须满足：

- 已出具真实数据来源调查矩阵。
- `_build_resolved_payload_v81()` 的伪 records 主路径被废弃或替换。
- 源码不再固定 `altitude=100.0` 作为复盘坡度/GAP 输入。
- 源码不再固定 `dt=1s` 冒充真实采样时间。
- bonk 检测接收真实 calories，并显式传入 `sport_type`。
- `curves.distance` 与 `fatigue_zones.start_km/end_km` 同源。
- `main.py` 不新增复杂疲劳算法，只做编排和白名单快照。
- 不修改前端，不接 AI。
- 契约测试通过，或完成报告中明确失败原因与阻塞点。

---

## 八、完成报告模板

完成后必须输出：

```text
P1 运动复盘算法链路回正完成报告

1. 本次目标
- ...

2. 数据来源调查矩阵
| 字段 | 来源 | 单位 | 可信级别 | 缺失策略 |
|---|---|---|---|---|

3. 修改文件
- ...

4. 算法链路变更
- ...

5. 废弃伪 records 说明
- ...

6. 验证结果
- 命令：...
- 结果：...

7. 未处理事项
- 前端展示：P3/P4
- AI 洞察：P6

8. 下一步建议
- ...
```
*** Add File: /Users/fanglei/应用开发/AI track/docs/p1_fatigue_review_algorithm_realignment_prompt_completion_report.md
# P1 运动复盘算法链路回正提示词构建完成报告

## 1. 本次目标

- 编写“P1：算法链路回正，废弃伪 records，改用真实 FIT / DB canonical 数据”的执行提示词。
- 提示词必须遵循 `fit-arch-contrac`、运动复盘功能设计文档、P0 数据契约回正结果。
- 提示词必须明确 P1 只处理算法输入链路，不做前端草图还原，不接 AI 洞察。

## 2. 新增文件

- `docs/p1_fatigue_review_algorithm_realignment_prompt.md`
- `docs/p1_fatigue_review_algorithm_realignment_prompt_completion_report.md`

## 3. 提示词覆盖范围

- 架构契约核对：FIT / DB canonical 为事实源、Resolver 为语义层、main.py 只编排、前端零推断、AI 留到 P6。
- 当前偏离说明：固定 `altitude=100.0`、固定 `dt=1s`、空 session、伪距离、bonk calories 漏传。
- 数据来源调查：activities 表字段、track_json 点结构、Resolver / GapCalculator 现有输出。
- canonical curve bundle 设计：`distance_curve_m`、`time_curve_sec`、`hr_curve`、`speed_curve_mps`、`altitude_curve_m`、`cadence_curve`、`calories`、`duration_sec`、`total_distance_m`、`sport_type`、`source`。
- 实施步骤：调查 → bundle 构建 → 替换伪 records → sport-aware bonk → 输出权威曲线 → 新增测试。
- 验收标准：不再固定 altitude/dt，不再空 session 漏 calories，fatigue_zones 与 curves.distance 同源。

## 4. 对齐依据

- `docs/fatigue_review_realignment_plan_v1.md` 的 P1 任务定义。
- `docs/p0_fatigue_review_contract_completion_report.md` 的 P0 契约结果。
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md` 中数据输入契约、Gradient、GAP、Efficiency、HR Drift 等算法规格。
- `main.py` 当前 `_build_resolved_payload_v81()` 的伪 records 实现位置。

## 5. 未处理事项

- P1 的实际代码实现尚未执行。
- P2 后端快照封装留到 P1 输出稳定后。
- P3/P4 前端展示和草图还原留到数据链路稳定后。
- P6 AI 洞察留到复盘功能跑通后。

## 6. 下一步建议

- 使用 `docs/p1_fatigue_review_algorithm_realignment_prompt.md` 正式执行 P1。
- 执行 P1 时先做数据来源调查矩阵，再动代码废弃伪 records。
