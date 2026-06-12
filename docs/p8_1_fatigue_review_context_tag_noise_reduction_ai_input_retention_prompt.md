# P8.1 复盘上下文标签降噪与 AI 输入保留提示词

> 任务类型：P8.1 复盘 UI 降噪与 AI 输入契约保留
> 来源对话：`019eb025-7a1d-7612-9e7b-2f9b48f6703e`
> 适用范围：复盘 Tab 右侧关键摘要、上下文标签展示、`context_tags` 后端契约、复盘 AI compact snapshot、相关测试与验收清单
> 前置条件：P8.0 已完成复盘 AI 洞察开放前契约复核；本任务不默认开放 AI 洞察按钮
> 核心目标：删除独立“上下文标签”卡片及无价值空态，有标签时并入右侧“关键摘要”作为“影响因素”，同时继续保留 `context_tags` 作为后端契约字段和 AI 洞察输入白名单字段。

---

## 零、执行前必须先读

执行本任务前必须阅读并遵守：

- `ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p7_6_fatigue_review_context_advice_completion_report.md`
- `docs/p7_16_fatigue_review_side_summary_completion_report.md`
- `docs/p7_20_fatigue_review_ui_contract_label_cleanup_completion_report.md`
- `docs/p8_0_fatigue_review_ai_preflight_contract_review_completion_report.md`
- `docs/js_api_contract.json`
- `docs/detail_tab_review_manual_test_checklist.md`
- `main.py`
- `track.html`
- `llm_backend.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_snapshot_realignment.py`

必须重新确认：

- 复盘 Tab 事实源仍为 `get_fatigue_review(activity_id)` 后端 snapshot。
- `context_tags` 只能来自后端 `data.context_tags`。
- 前端不得从活动标题、设备、路线、DOM、ECharts、截图、曲线走势或 points 推导上下文标签。
- `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 继续包含 `context_tags`。
- 本任务不写 DB，不新增 DB 字段，不让 AI 输出参与指标、曲线、事件或疲劳区间计算。

---

## 一、任务背景

来源对话明确同意以下产品定位：

```text
有标签时：合并进右侧「关键摘要」里，作为“影响因素”。
无标签时：不显示整张卡。
不要显示“本次活动未携带上下文标签”这种空态，因为这对用户没有帮助。
可以作为 AI 洞察的信息输入。
```

现状中，复盘右侧存在独立 `fr-context-panel`：

- 标题为“上下文标签”。
- 无标签时显示“本次活动未携带上下文标签”/“暂无上下文”。
- `openFatigueReview()` 会调用 `_renderFatigueReviewContextTags(data.context_tags || {})`。

这个展示对用户价值偏弱，会把“缺数据”作为独立信息卡暴露出来，造成侧栏噪音。但 `context_tags` 对解释复盘和 AI 洞察仍有价值，不能从后端契约或 AI 输入中删除。

因此本任务的核心不是删除 `context_tags`，而是调整其用户可见呈现位置：

- UI 降噪：独立上下文卡片消失。
- 有值呈现：并入关键摘要的“影响因素”。
- 空值静默：无标签时不展示上下文区域、不展示空态。
- AI 保留：继续进入 `__FATIGUE_REVIEW_INSIGHT__` compact snapshot。

---

## 二、执行目标

### 2.1 后端 `context_tags` 生成链路补强

修正后端 `context_tags` 生成链路，使真实活动中有足够背景信息时能稳定产生标签。

重点检查 `_build_resolved_payload_v81()` 或同等 Resolver 输入构造路径，必要时补齐：

- `avg_heart_rate`
- `max_heart_rate`
- `total_ascent`
- `max_altitude`
- `avg_power`
- `normalized_power`
- `avg_temperature`

要求：

- `avg_temperature` 可优先从 `weather_json.temperature_c` 读取。
- 修复无 records 分支中 `fallback` 未定义或等价风险。
- `get_fatigue_review().data.context_tags` 在存在温度、心率、热量、海拔或功率背景时可返回非空标签。
- 普通无标签活动继续返回 `context_tags = {}`，这仍是合法状态。

### 2.2 保留 `context_tags` 后端契约字段

必须保留：

- `get_fatigue_review(activity_id)` 返回 `context_tags`。
- `docs/js_api_contract.json` 中 `get_fatigue_review` 响应契约包含 `context_tags`。
- `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 包含 `context_tags`。
- P8 AI 白名单仍包含 `context_tags`。

不得：

- 把 `context_tags` 写入 DB。
- 从前端补算 `context_tags`。
- 从 DOM、ECharts、截图、活动标题、设备、路线、points 或前端曲线 payload 推导 `context_tags`。

### 2.3 删除右侧独立“上下文标签”卡片

移除或隐藏复盘右侧独立上下文区域：

- 删除或停用 `fr-context-panel` 独立卡片。
- 删除用户可见标题“上下文标签”。
- 删除用户可见空态：
  - “本次活动未携带上下文标签”
  - “暂无上下文”
- 无 `context_tags` 时不显示任何上下文区域。

要求：

- 不为了兼容旧测试保留用户可见空卡片。
- 如必须保留旧 DOM id 供兼容测试，应确保其不可见且不占布局，不出现用户可见标题和空态。

### 2.4 将有值的 `context_tags` 并入右侧“关键摘要”

在右侧 `fr-side-summary-panel` 中新增“影响因素”展示组。

展示规则：

- 仅当 `data.context_tags` 非空时显示。
- 只读 `data.context_tags`。
- 不从 metrics、curves、collapse_events、fatigue_zones 或 DOM 反向推导标签。
- 标签文案转成用户语言，避免工程字段裸露。

建议映射示例：

| 后端标签含义 | 用户可见文案示例 |
|---|---|
| 热应激 | 温度偏高，心率更容易上浮 |
| 糖原耗竭风险 | 能量消耗偏高，后程可能更吃补给 |
| 心肺负荷 | 本次心肺压力偏高 |
| 海拔缺氧 | 海拔压力会抬高心率 |
| 功率压力 | 输出压力偏高，需要结合恢复观察 |

未知标签处理：

- 可以显示后端标签 key 的安全中文化结果。
- 不得显示 JSON、字段路径、`data.context_tags`、`Resolver` 等工程词。

### 2.5 调整前端渲染职责

调整以下职责边界：

- `_renderFatigueReviewContextTags()` 不再渲染独立卡片。
- 可以删除该函数，或改为内部 helper，例如 `_renderFatigueReviewContextFactors(contextTags)`。
- `_renderFatigueReviewSideSummary(data)` 负责消费 `data.context_tags` 并生成“影响因素”。
- `openFatigueReview()` 不再调用独立上下文卡片渲染。

必须保持：

- 前端只读 `data.context_tags`。
- 无标签时关键摘要不出现“影响因素”组。
- 切换活动、关闭详情、空数据初始化时不残留上一活动的影响因素。

---

## 三、允许修改范围

允许修改：

- `main.py`
- `track.html`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_ai_preflight_p8.py`
- `tests/test_fatigue_review_snapshot_realignment.py`
- 必要时新增针对本任务的测试文件，例如：
  - `tests/test_fatigue_review_context_tags_p8_1.py`
- 必要时新增完成报告：
  - `docs/p8_1_fatigue_review_context_tag_noise_reduction_ai_input_retention_completion_report.md`

如必须修改 Resolver 或指标解析相关文件，只允许在证明 `context_tags` 生成链路确实缺少输入字段时最小范围修改：

- `metrics_resolver.py`
- `metrics_registry.py`
- 相关 resolver 测试文件

---

## 四、禁止事项

本任务严禁：

- 不开放 AI 洞察按钮，除非任务执行时已有单独明确授权。
- 不新增 LLM 调用。
- 不修改 AI prompt 正文，除非只为保留 `context_tags` 白名单做契约描述同步。
- 不把 `context_tags` 写入 DB。
- 不新增 DB 字段。
- 不写 `localStorage` / `sessionStorage` 持久化 AI 事实。
- 不从前端曲线、DOM、ECharts、截图、活动标题、设备、路线或 points 推导 `context_tags`。
- 不在 UI 层补算后端没给的上下文标签。
- 不显示“本次活动未携带上下文标签”或“暂无上下文”。
- 不保留独立“上下文标签”用户可见卡片。
- 不让 AI 输出参与 `metrics / curves / fatigue_zones / collapse_events / context_tags` 计算。

---

## 五、测试要求

### 5.1 后端测试

至少覆盖：

- 有 `weather_json.temperature_c` 且活动类型为 running / trail_running 时，能生成热应激或等价温度背景标签。
- 有 `avg_heart_rate / max_heart_rate` 时，能生成心肺负荷或等价背景标签。
- 有海拔、爬升、功率或能量消耗背景时，能生成对应上下文标签。
- 普通无标签活动返回 `context_tags = {}`，且不报错。
- 无 records 分支不触发 `fallback` 未定义或等价异常。

### 5.2 AI 输入契约测试

至少覆盖：

- `_build_fatigue_review_insight_snapshot()` 继续输出 `context_tags`。
- compact snapshot 仍只包含白名单字段：
  - `activity_id`
  - `sport_type`
  - `metrics`
  - `fatigue_zones`
  - `collapse_events`
  - `curves_summary`
  - `context_tags`
  - `advice`
  - `disclaimer`
- forbidden keys 仍被递归剥离：
  - `points`
  - `records`
  - `raw_records`
  - `track_points`
  - `fit_records`
  - `gpx_points`
  - `shadow_diff`
  - `shadow_diff_json`
  - `diff`
- 前端调用复盘 AI 仍只允许 sentinel + `sportType`，不传 `context_tags` 或任何事实 payload。

### 5.3 前端静态测试

至少覆盖：

- HTML 中不再存在用户可见“本次活动未携带上下文标签”。
- HTML 中不再存在用户可见“暂无上下文”。
- 右侧不再存在独立可见“上下文标签”卡片。
- `openFatigueReview()` 不再调用 `_renderFatigueReviewContextTags(data.context_tags || {})` 渲染独立面板。
- `_renderFatigueReviewSideSummary(data)` 或等价函数只读 `data.context_tags` 并渲染“影响因素”。
- `context_tags = {}` 时不渲染“影响因素”。
- `context_tags` 非空时渲染“影响因素”。

### 5.4 推荐测试命令

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_snapshot_realignment.py
python3 -m pytest tests/test_e2e_fatigue_review.py tests/test_fatigue_review_e2e_contract.py
python3 -m json.tool docs/js_api_contract.json
```

如新增专项测试文件，应同步运行：

```bash
python3 -m pytest tests/test_fatigue_review_context_tags_p8_1.py
```

---

## 六、文档更新要求

必须同步更新：

- `docs/detail_tab_review_manual_test_checklist.md`
  - 删除“上下文标签卡片”和上下文空态验收项。
  - 增加“关键摘要中的影响因素”验收项。
  - 保留 `context_tags` 只读后端字段、不从标题/设备/DOM 推导的验收项。
- `docs/fatigue_review_realignment_plan_v1.md`
  - 将 P7.6/P7.16 相关描述调整为：`context_tags` 是关键摘要影响因素和 AI 输入，不再是独立 UI 卡片。
- `docs/js_api_contract.json`
  - 保持 `context_tags` 在 API 响应与 AI compact snapshot 白名单中。
  - 如描述中提到 UI 展示位置，应更新为关键摘要影响因素。

任务完成后必须新增完成报告：

- `docs/p8_1_fatigue_review_context_tag_noise_reduction_ai_input_retention_completion_report.md`

完成报告必须包含：

1. 修改文件清单。
2. UI 降噪结果。
3. `context_tags` 后端契约保留说明。
4. AI compact snapshot 白名单保留说明。
5. 禁止前端推导说明。
6. 测试命令与结果。
7. 未覆盖风险。

---

## 七、验收标准

本任务通过必须同时满足：

- 右侧不再出现独立“上下文标签”用户可见卡片。
- 无 `context_tags` 时不出现“本次活动未携带上下文标签”“暂无上下文”或任何上下文空态占位。
- 有 `context_tags` 时，右侧“关键摘要”出现“影响因素”。
- “影响因素”只消费 `data.context_tags`，不从前端其他字段推导。
- `get_fatigue_review(activity_id)` 继续返回 `context_tags`。
- `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 继续包含 `context_tags`。
- AI 输入仍不包含 DOM、ECharts、截图、活动标题、设备、路线、points、records、raw_records、track_points、fit_records、gpx_points、shadow_diff 或 diff。
- 不写 DB，不写 localStorage/sessionStorage，不改变 AI 输出边界。
- 相关测试通过，且文档验收清单已同步更新。

---

## 八、与原 P8.1 打开按钮任务的关系

历史 P8.0 报告建议下一步为“P8.1 复盘 AI 洞察最小闭环打开按钮”。本任务来自后续对话补充，优先处理上下文标签展示噪音与 AI 输入保留边界。

执行顺序建议：

1. 先完成本任务：`P8.1 复盘上下文标签降噪与 AI 输入保留`。
2. 再另行评估是否进入 AI 洞察按钮开放任务。

本任务完成并不等价于 AI 按钮已开放。
