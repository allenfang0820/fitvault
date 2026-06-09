# P0 运动复盘数据契约回正提示词

> 任务类型：P0 数据契约回正
> 适用范围：运动复盘功能 `get_fatigue_review(activity_id)` API 契约、测试契约与文档契约
> 不包含：算法实现、前端草图还原、AI 洞察接入

---

## 零、架构契约核对

执行本任务前必须先阅读并遵守：

- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/design/运动复盘系统_页面设计草图_v1.png`
- 全局架构契约 `fit-arch-contrac`

硬性约束：

- 脉图是本地 AI 运动外挂，不引入 SaaS、微服务、事件总线、Feature Store、云计算节点。
- 数据流必须遵循 FIT / GPX → fit_engine → resolver → SQLite canonical DB → API snapshot → UI。
- Resolver 是唯一语义翻译层，前端只展示，不生成事实指标。
- 本任务只固化契约，不实现复杂算法，不接 AI。
- AI 洞察放到最后阶段，当前不得修改 `__FATIGUE_REVIEW_INSIGHT__` 业务逻辑，除非只是文档标注“暂不处理”。
- `shadow_diff`、`shadow_diff_json`、`diff`、原始 records、全量 points 禁止进入复盘 API data。
- 所有新增或变更 API 契约必须更新 `docs/js_api_contract.json`。
- 所有 API 响应必须使用统一 envelope：`{code,msg,data,traceId}`。

---

## 一、任务背景

当前运动复盘功能已有部分实现，但方向偏离：

- 后端复盘快照缺少权威 `curves.distance`，导致前端 `_distanceFromSpeedTime()` 自行推导距离轴。
- `get_fatigue_review` 的契约文档滞后，未明确距离轴、曲线来源、空态行为和 forbidden 字段。
- 前端和后端后续开发缺少一个稳定、可测试、可追溯的数据契约。

本任务是整个复盘功能回正的第一步：先把 API 输出契约固定下来，为 P1 算法链路回正和 P3 前端最小展示提供唯一依据。

---

## 二、任务目标

完成 P0 数据契约回正：

1. 固化 `get_fatigue_review(activity_id)` 的目标响应结构。
2. 更新 `docs/js_api_contract.json` 中 `get_fatigue_review` 的契约描述。
3. 新增或更新契约测试，明确 forbidden 字段不得出现。
4. 明确 `curves.distance` 必须由后端权威输出，前端不得重建。
5. 明确 `fatigue_zones.start_km/end_km` 必须与 `curves.distance` 同源。
6. 明确当前 P0 不实现算法，不修 AI 洞察，不还原草图 UI。

---

## 三、必须修改的文件

优先修改：

- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md` 如需补充 P0 细节

建议新增或更新测试：

- `tests/test_fatigue_review_e2e_contract.py`
- 或新增 `tests/test_fatigue_review_contract_realignment.py`

只有在测试需要最小占位字段时，才允许轻微修改：

- `main.py`

禁止在本任务中大规模改动：

- `track.html`
- `metrics_resolver.py`
- `gap_calculator.py`
- `llm_backend.py`

---

## 四、目标 API 契约

`get_fatigue_review(activity_id)` 成功响应必须面向以下目标结构收敛：

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
    "fatigue_zones": [
      {
        "start_km": 0.0,
        "end_km": 0.0,
        "level": "medium"
      }
    ],
    "collapse_events": [
      {
        "event_id": "ce_00",
        "type": "BONK_WARNING",
        "trigger_km": 0.0,
        "trigger_time_sec": null,
        "value_y": null,
        "description": ""
      }
    ],
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

字段要求：

- `curves.distance`：后端权威距离轴，单位建议为 km 或在契约中明确单位，禁止前端重建。
- `curves.time`：后端权威时间轴，单位建议为秒，可为空数组。
- `curves.total_distance_m`：活动总距离，单位米。
- `fatigue_zones`：使用与 `curves.distance` 同源的距离坐标。
- `collapse_events.trigger_km`：使用与 `curves.distance` 同源的距离坐标。
- `metrics`：只表达后端权威指标，不允许前端 DOM 或 points 反推。
- `ai_insight`：P0 保持 `null`，AI 洞察后续 P6 处理。

---

## 五、明确禁止

本任务中禁止：

- 禁止让前端继续补算 `distance_curve` 作为契约的一部分。
- 禁止把 `_distanceFromSpeedTime()` 的结果声明为权威字段。
- 禁止把 `shadow_diff`、`shadow_diff_json`、`diff` 暴露到 `data`。
- 禁止返回原始 records、全量 track points、全量 FIT 原始字段。
- 禁止 AI 参与数据契约设计。
- 禁止修改 DB schema，除非另开任务并说明迁移策略。
- 禁止引入新依赖。
- 禁止为通过测试而写入 mock / synthetic 指标到 canonical DB。

---

## 六、实施步骤

### Step 1：更新 API 契约文档

修改 `docs/js_api_contract.json` 中 `get_fatigue_review`：

- 修正 `line` 为当前 `main.py` 中 `get_fatigue_review` 的实际行号。
- 扩展 `returns`，明确 `curves.distance/time/altitude/total_distance_m`。
- 在 `contract` 中写明：
  - 统一 envelope。
  - `shadow_diff` 隔离。
  - 前端零推断。
  - `curves.distance` 后端权威输出。
  - `fatigue_zones` 与 `curves.distance` 同源。
- 在 `description` 中标注：P0 仅固化契约，AI 洞察 P6 处理。

### Step 2：补充契约测试

新增或更新测试，至少覆盖：

- `get_fatigue_review` 契约中包含目标字段声明。
- `docs/js_api_contract.json` 的 `returns` 包含 `curves.distance`。
- `docs/js_api_contract.json` 的 `contract` 包含前端零推断 / 后端权威距离轴描述。
- forbidden 字段列表包含并校验 `shadow_diff`、`shadow_diff_json`、`diff`、`records`。
- P0 不要求实际算法输出非空，但要求空态字段结构完整。

### Step 3：必要时补后端空态字段

如果现有 `_empty_fatigue_review_snapshot()` 缺少 `curves.distance` 或 `curves.time`，允许补齐空数组字段。

要求：

- 不实现算法。
- 不改 Resolver。
- 不改前端图表逻辑。
- 只让空态结构与 P0 契约一致。

### Step 4：运行验证

运行与契约相关的最小测试：

```bash
python -m pytest tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py
```

如果新增了独立测试文件，也一并运行：

```bash
python -m pytest tests/test_fatigue_review_contract_realignment.py
```

---

## 七、验收标准

完成后必须满足：

- `docs/js_api_contract.json` 已明确 P0 目标响应结构。
- `curves.distance` 被定义为后端权威输出。
- `fatigue_zones` 与 `curves.distance` 同源关系写入契约。
- `shadow_diff`、`shadow_diff_json`、`diff`、`records` 被明确禁止。
- 空态快照字段完整。
- 测试通过或给出明确失败原因。
- 完成报告说明修改文件、验证命令、剩余风险和下一步 P1 算法链路回正入口。

---

## 八、完成报告模板

完成后输出报告，必须包含：

```text
P0 运动复盘数据契约回正完成报告

1. 本次目标
- ...

2. 修改文件
- ...

3. 契约变更
- ...

4. 验证结果
- 命令：...
- 结果：...

5. 未处理事项
- 算法链路回正：留到 P1
- 前端最小展示：留到 P3
- AI 洞察：留到 P6

6. 下一步建议
- ...
```
*** Add File: /Users/fanglei/应用开发/AI track/docs/p0_fatigue_review_contract_prompt_completion_report.md
# P0 运动复盘数据契约回正提示词构建完成报告

## 1. 本次目标

- 根据 `docs/fatigue_review_realignment_plan_v1.md` 的第一任务 P0，构建一份可交给后续开发执行的提示词。
- 提示词必须遵循全局架构契约 `fit-arch-contrac` 与运动复盘功能设计文档。
- 提示词必须明确本阶段只做数据契约回正，不做算法实现、不做前端草图还原、不接 AI 洞察。

## 2. 新增文件

- `docs/p0_fatigue_review_contract_prompt.md`
- `docs/p0_fatigue_review_contract_prompt_completion_report.md`

## 3. 提示词覆盖范围

- 架构契约核对：FIT 为事实源、Resolver 为语义层、前端零推断、AI 最后接入、shadow_diff 隔离。
- P0 任务边界：更新 `get_fatigue_review(activity_id)` API 契约与相关契约测试。
- 目标响应结构：明确 `metrics`、`fatigue_zones`、`collapse_events`、`curves.distance/time/hr/speed/altitude/grade/gap/efficiency/total_distance_m`、`context_tags`、`ai_insight`、`advice`、`disclaimer`。
- 禁止事项：禁止前端重建距离轴、禁止暴露 shadow_diff、禁止原始 records / 全量 points 进入 API data、禁止 AI 参与本阶段。
- 验收标准：契约文档更新、测试覆盖、空态字段完整、完成报告要求。

## 4. 设计文档对齐

- 对齐 `docs/脉图运动复盘系统_开发团队交付手册_v1.md` 的 Part II 架构契约。
- 对齐 `docs/fatigue_review_realignment_plan_v1.md` 的 P0 数据契约回正任务。
- 保留 `docs/design/运动复盘系统_页面设计草图_v1.png` 作为后续 P4 UI 参考，但 P0 不实现 UI。

## 5. 未处理事项

- P1 算法链路回正：留到下一任务。
- P2 后端快照实际算法封装：留到后续任务。
- P3/P4 前端最小展示与草图还原：留到数据链路稳定后。
- P6 AI 洞察：等复盘功能跑通后再处理。

## 6. 下一步建议

- 使用 `docs/p0_fatigue_review_contract_prompt.md` 执行 P0 数据契约回正。
- P0 完成后再进入 P1，重点梳理真实 `distance_curve / altitude_curve / time / calories / sport_type` 来源。
