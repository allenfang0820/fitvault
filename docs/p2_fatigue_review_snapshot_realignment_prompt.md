# P2 运动复盘后端快照回正提示词

> 任务类型：P2 后端快照回正
> 核心目标：让 `get_fatigue_review(activity_id)` 成为前端复盘页面唯一数据源
> 前置条件：P0 数据契约已固化，P1 算法链路已改为真实 FIT / DB canonical 数据
> 不包含：前端页面改造、草图视觉还原、AI 洞察接入、DB schema 大迁移

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p0_fatigue_review_contract_completion_report.md`
- `docs/p1_fatigue_review_algorithm_realignment_completion_report.md`
- `docs/js_api_contract.json` 中 `get_fatigue_review` 契约
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 数据流必须遵循 FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- `get_fatigue_review(activity_id)` 是复盘页面唯一权威数据源。
- 前端不得通过 `points[]`、DOM、speed/time、total_distance_m 自行补算事实字段。
- 后端快照可以做白名单封装、单位转换、长度对齐、空态表达，不写 DB。
- records、全量 points、`shadow_diff`、`shadow_diff_json`、`diff` 禁止进入 API data。
- AI 洞察留到 P6，本任务不得接入或修复 `__FATIGUE_REVIEW_INSIGHT__`。
- 本任务不得修改 `track.html` 来绕过后端缺字段问题。

---

## 一、任务背景

P0 已固定 API 契约，要求 `get_fatigue_review(activity_id)` 返回完整白名单：

- `metrics`
- `collapse_events`
- `fatigue_zones`
- `curves`
- `context_tags`
- `ai_insight`
- `advice`
- `disclaimer`

P1 已把复盘算法输入改为真实数据链路：

- `_build_fatigue_review_curve_bundle(row)` 从 `track_json / points_json / merged_track_json` 构造内部 canonical curve bundle。
- `_build_resolved_payload_v81()` 改为消费 bundle，不再构造伪 records。
- `curves.distance/time/altitude/grade/gap/efficiency` 已具备后端输出基础。
- `MetricsResolver.resolve()` 已显式向 bonk 检测传入 `sport_type`，并透出 `grade_curve`。

P2 要解决的是：把 P1 算法输出整理为稳定、完整、可直接被前端消费的 API snapshot，让前端 P3/P4 不再需要任何事实推导。

---

## 二、任务目标

完成 P2 后端快照回正：

1. 让 `_build_fatigue_review_snapshot(row)` 始终返回 P0 定义的完整白名单字段。
2. 让 `get_fatigue_review(activity_id)` 成功、空态、降级、异常路径都返回统一 envelope。
3. 将 P1 bundle / resolver 输出整理成前端可直接绘图的数据结构。
4. 统一曲线长度、单位、空态、同源距离轴。
5. 明确不同数据形态下的缺失策略：有 GPS、有海拔、室内无 GPS、缺 calories、短轨迹、轨迹点字段不完整。
6. 更新 `docs/js_api_contract.json` 中 P2 状态描述。
7. 新增或更新后端快照契约测试。

---

## 三、目标 API 快照结构

`get_fatigue_review(activity_id)` 必须返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "sport_type": "running",
    "metrics": {
      "hr_drift": {},
      "decoupling": {},
      "efficiency": {},
      "durability": {},
      "cadence_stability": {},
      "training_load": {},
      "bonk_risk": {},
      "events": {}
    },
    "collapse_events": [],
    "fatigue_zones": [],
    "curves": {
      "distance": [],
      "time": [],
      "hr": [],
      "speed": [],
      "altitude": [],
      "grade": [],
      "gap": [],
      "efficiency": [],
      "total_distance_m": 0
    },
    "context_tags": {},
    "ai_insight": null,
    "advice": "",
    "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法"
  },
  "traceId": "hex12"
}
```

要求：

- `curves.distance` 单位 km。
- `curves.time` 单位 sec。
- `curves.total_distance_m` 单位 m。
- `fatigue_zones.start_km/end_km` 与 `curves.distance` 同源。
- `collapse_events.trigger_km` 与 `curves.distance` 同源。
- `curves.*` 中可绘图曲线应长度一致；无法对齐时必须采用后端统一策略，不让前端补齐。
- `data` 不得出现 `records`、`points`、`raw_records`、`track_points`、`shadow_diff`、`shadow_diff_json`、`diff`。

---

## 四、曲线长度与单位策略

P2 必须新增或整理一个快照级规范化函数，命名可按现有风格调整，例如：

```python
def _normalize_fatigue_review_curves(bundle: dict, resolved: dict) -> dict:
    ...
```

职责：

- 统一输出 `distance/time/hr/speed/altitude/grade/gap/efficiency/total_distance_m`。
- 将 `distance_curve_m` 转换为 km。
- 保留 `time_curve_sec` 秒单位。
- 对同源算法曲线进行长度对齐。
- 不做前端式插值，不补 synthetic 事实值。
- 缺失曲线返回空数组，而不是返回错误长度数组。

推荐策略：

- 以 `distance_curve_m` 作为主轴。
- 对由同一 records / bundle 产生的曲线，如果长度与 distance 相同，则直接输出。
- 如果某曲线长度不等，返回空数组或截断到共同最短长度；策略必须写入完成报告和测试。
- `total_distance_m` 优先使用 P1 bundle 的 `total_distance_m`。
- `fatigue_zones` 与 `collapse_events` 不得在 P2 重新计算距离，只透传 P1 同源结果。

---

## 五、数据形态覆盖要求

P2 至少要明确并测试以下场景：

### 1. 有 GPS / 有海拔 / 有 calories

- 应返回非空 `curves.distance/time/altitude/grade/gap/efficiency`。
- 有条件触发 `fatigue_zones` 或 `collapse_events`。

### 2. 有轨迹点但缺 calories

- `curves` 正常返回。
- `bonk_risk.is_at_risk` 为 false 或 low confidence。
- 不抛异常。

### 3. 室内或短轨迹

- 允许 `distance/time/altitude/grade/gap/efficiency` 部分为空。
- `metrics` 结构必须完整。
- `advice` 或 `context_tags` 应能表达数据不足，不要求前端推断原因。

### 4. 轨迹点字段不完整

- 不抛异常。
- 缺字段对应曲线为空。
- envelope 仍为 `{code,msg,data,traceId}`。

### 5. 活动不存在或参数错误

- 参数错误返回 `1001`。
- 活动不存在返回 `1004`。
- DB / 构建异常返回 `5001` 或 `9001`。

---

## 六、允许修改的文件

优先修改：

- `main.py`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_fatigue_review_envelope.py`

必要时修改：

- `tests/test_fatigue_review_resolver_realignment.py`
- `docs/fatigue_review_realignment_plan_v1.md`

禁止或暂缓修改：

- `track.html`：P2 不做前端消费改造。
- `llm_backend.py`：P2 不做 AI 洞察。
- DB schema migration：P2 不做结构迁移。

---

## 七、实施步骤

### Step 1：审查当前 get_fatigue_review 全路径

必须先阅读：

- `Api.get_fatigue_review()`
- `Api._build_fatigue_review_snapshot()`
- `Api._empty_fatigue_review_snapshot()`
- `_build_fatigue_review_curve_bundle()`
- `_build_resolved_payload_v81()`

确认所有返回路径是否统一 envelope，是否存在裸 `ok/error` 或字段缺失。

### Step 2：抽取快照标准化层

建议新增后端内部函数：

```python
def _build_fatigue_review_curves_snapshot(bundle: dict, resolved: dict) -> dict:
    ...
```

或等价命名。

职责：

- 输出 P0/P2 契约中的 `curves`。
- 处理单位转换。
- 处理长度对齐。
- 保证 forbidden 字段不进入。

### Step 3：统一 metrics / events / zones 白名单

确保 `data.metrics` 始终包含：

- `hr_drift`
- `decoupling`
- `efficiency`
- `durability`
- `cadence_stability`
- `training_load`
- `bonk_risk`
- `events`

确保 `collapse_events` 每项只包含：

- `event_id`
- `type`
- `trigger_km`
- `trigger_time_sec`
- `value_y`
- `description`

确保 `fatigue_zones` 每项只包含：

- `start_km`
- `end_km`
- `level`

### Step 4：统一空态与降级策略

`_empty_fatigue_review_snapshot()` 必须与正常 snapshot 字段完全同构。

要求：

- 降级也返回完整 `metrics / curves / fatigue_zones / collapse_events / context_tags / advice / disclaimer`。
- 曲线缺失返回空数组。
- advice 中可以说明数据不足或后端构建失败。
- 不把 Python 异常堆栈、文件路径、secret 写入返回值。

### Step 5：更新 API 契约文档

更新 `docs/js_api_contract.json`：

- `line` 修正为当前 `get_fatigue_review` 实际行号。
- `returns` 补充 P2 快照同构、长度对齐、空态策略。
- `contract` 强化“前端唯一数据源”和 forbidden 字段。
- `description` 从 P0 状态更新为 P2 后端快照已回正，P3/P4/P6 仍未执行。

### Step 6：新增测试

新增 `tests/test_fatigue_review_snapshot_realignment.py`，至少覆盖：

- 正常 snapshot 字段完整。
- 空态 snapshot 字段完整且与正常结构同构。
- `curves.distance/time/altitude/hr/speed/grade/gap/efficiency` key 必然存在。
- forbidden 字段不出现在 `data` 任意层级。
- 曲线长度策略符合 P2 约定。
- `fatigue_zones` 与 `curves.distance` 坐标同源。
- 缺 calories 不触发 bonk，但不影响 envelope。
- 缺轨迹或短轨迹不抛异常。

继续运行：

```bash
python -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py tests/test_fatigue_zones_resolver.py
```

---

## 八、验收标准

完成后必须满足：

- `get_fatigue_review(activity_id)` 是前端复盘唯一数据源。
- 所有成功和降级路径均返回统一 envelope。
- 正常快照与空态快照字段同构。
- `curves.distance` 由后端输出，且与 zones / events 同源。
- 前端不需要任何业务推导即可画图或展示空态。
- API data 不含 records、points、raw_records、track_points、shadow_diff、shadow_diff_json、diff。
- P2 不修改 `track.html`，不接 AI。
- 测试通过，或完成报告明确失败原因与阻塞点。

---

## 九、完成报告模板

完成后必须输出：

```text
P2 运动复盘后端快照回正完成报告

1. 本次目标
- ...

2. 修改文件
- ...

3. 快照结构变更
- ...

4. 曲线长度与单位策略
- ...

5. 空态 / 降级策略
- ...

6. Forbidden 字段隔离
- ...

7. 验证结果
- 命令：...
- 结果：...

8. 未处理事项
- 前端展示：P3/P4
- AI 洞察：P6

9. 下一步建议
- ...
```
