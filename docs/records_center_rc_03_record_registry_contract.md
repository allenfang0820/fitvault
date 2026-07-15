# RC-03 Record Registry 与比较规则冻结

日期：2026-07-13

## 执行提示词

目标：冻结 V1 四项跑步纪录的唯一规则来源，消除代码、SQL、API 和前端各自硬编码口径的风险。

范围：Record Registry 契约、比较规则、冲突检测策略、测试用例表和后续代码化输入。

约束：不加入骑行、越野、游泳或故事纪录；不实现 UI；不迁移真实数据；不改变当前业务代码。

完成定义：后续任何模块只引用 Registry key，不重复定义距离范围和比较方向。

## 1. Registry 单一来源原则

Records Center V1 的纪录定义必须由后端 Registry 提供，其他层不得重复维护标准距离、容差、比较方向或单位。

允许引用 Registry 的模块：

- PB Resolver
- Records API ViewModel
- Overview/Timeline/Achievement 联动
- Frontend 展示层
- Records Snapshot
- 测试夹具与 mock

禁止：

- 前端根据距离或标题判断 PB 类型。
- SQL 里直接散落标准距离区间。
- Timeline、Overview、Achievement 复制 PB 类型规则。
- AI 或 Snapshot 重新计算成绩事实。

## 2. V1 RecordDefinition 结构

代码化时建议使用不可变结构，字段如下：

```python
RecordDefinition(
    key: str,
    sport: str,
    category: str,
    display_name: str,
    metric: str,
    canonical_unit: str,
    comparison: str,
    source_mode: str,
    standard_distance_m: float,
    tolerance_ratio: float,
    minimum_data_requirements: tuple[str, ...],
    enabled_release: str,
    rule_version: str,
)
```

字段冻结：

| 字段 | V1 规则 |
| --- | --- |
| `key` | 发布后不可改变语义 |
| `sport` | V1 固定为 `running` |
| `category` | 固定为 `distance_time` |
| `metric` | 固定为 `elapsed_time_sec` |
| `canonical_unit` | 固定为 `seconds` |
| `comparison` | 固定为 `lower_is_better` |
| `source_mode` | V1 固定为 `activity_total` |
| `tolerance_ratio` | 固定为 `0.03`，包含边界 |
| `rule_version` | V1 固定为 `records-v1` |

## 3. V1 注册定义

```json
[
  {
    "key": "running_5k",
    "sport": "running",
    "category": "distance_time",
    "display_name": "5K",
    "metric": "elapsed_time_sec",
    "canonical_unit": "seconds",
    "comparison": "lower_is_better",
    "source_mode": "activity_total",
    "standard_distance_m": 5000,
    "tolerance_ratio": 0.03,
    "minimum_data_requirements": [
      "activity_id",
      "sport",
      "distance_m",
      "elapsed_time_sec",
      "event_date"
    ],
    "enabled_release": "records-v1",
    "rule_version": "records-v1"
  },
  {
    "key": "running_10k",
    "sport": "running",
    "category": "distance_time",
    "display_name": "10K",
    "metric": "elapsed_time_sec",
    "canonical_unit": "seconds",
    "comparison": "lower_is_better",
    "source_mode": "activity_total",
    "standard_distance_m": 10000,
    "tolerance_ratio": 0.03,
    "minimum_data_requirements": [
      "activity_id",
      "sport",
      "distance_m",
      "elapsed_time_sec",
      "event_date"
    ],
    "enabled_release": "records-v1",
    "rule_version": "records-v1"
  },
  {
    "key": "running_half_marathon",
    "sport": "running",
    "category": "distance_time",
    "display_name": "半程马拉松",
    "metric": "elapsed_time_sec",
    "canonical_unit": "seconds",
    "comparison": "lower_is_better",
    "source_mode": "activity_total",
    "standard_distance_m": 21097.5,
    "tolerance_ratio": 0.03,
    "minimum_data_requirements": [
      "activity_id",
      "sport",
      "distance_m",
      "elapsed_time_sec",
      "event_date"
    ],
    "enabled_release": "records-v1",
    "rule_version": "records-v1"
  },
  {
    "key": "running_marathon",
    "sport": "running",
    "category": "distance_time",
    "display_name": "马拉松",
    "metric": "elapsed_time_sec",
    "canonical_unit": "seconds",
    "comparison": "lower_is_better",
    "source_mode": "activity_total",
    "standard_distance_m": 42195,
    "tolerance_ratio": 0.03,
    "minimum_data_requirements": [
      "activity_id",
      "sport",
      "distance_m",
      "elapsed_time_sec",
      "event_date"
    ],
    "enabled_release": "records-v1",
    "rule_version": "records-v1"
  }
]
```

## 4. 标准距离匹配

统一公式：

```text
distance_error_ratio = abs(actual_distance_m - standard_distance_m) / standard_distance_m
matched = distance_error_ratio <= tolerance_ratio
```

边界冻结：

- `0.03` 恰好命中，必须匹配。
- `0.0300001` 不匹配。
- 不能再使用 4.8-5.3km、9.5-10.8km 这类手写范围。
- V1 只使用 `activity_total`，不能从 10K 活动截取最快 5K，也不能从马拉松截取半马。

匹配输出至少包含：

```json
{
  "record_key": "running_10k",
  "source_mode": "activity_total",
  "standard_distance_m": 10000,
  "actual_distance_m": 10026,
  "distance_error_ratio": 0.0026
}
```

## 5. 多定义冲突策略

正常 V1 四项定义在 `±3%` 下不会重叠。Registry 初始化必须检测区间冲突：

```text
range_low = standard_distance_m * (1 - tolerance_ratio)
range_high = standard_distance_m * (1 + tolerance_ratio)
```

若同一 `sport + source_mode + category` 下任意两个定义的区间重叠：

1. Registry validation 失败。
2. Resolver 启动或测试失败。
3. 不允许运行时静默选择一个定义。

若未来新增定义导致单个 Activity 同时匹配多个定义，且 Registry validation 未捕获：

1. Resolver 必须返回明确错误或跳过该 evidence。
2. 写审计原因 `record_definition_conflict`。
3. 不写 active，也不生成候选。

本策略优先于手册附录中的“相对误差最小”兜底；V1 代码化阶段以“不允许重叠配置”为硬约束，减少静默误判。

## 6. 成绩比较规则

比较主值：

```text
elapsed_time_sec: int
```

规则：

- `new_record = candidate.elapsed_time_sec < current.elapsed_time_sec`
- 相同秒数不刷新，不替换当前纪录。
- 更慢成绩不刷新，不写新的正式纪录。
- 当前纪录不存在时，第一条有效成绩成为首条纪录。
- 首条纪录 `improvement = null`。
- 刷新纪录时 `improvement = previous.elapsed_time_sec - current.elapsed_time_sec`。
- 日期不参与成绩优劣，只用于稳定排序和展示。
- 平均配速只用于展示，不能作为比较主值。

稳定排序建议：

```text
(elapsed_time_sec ASC, event_date ASC, activity_id ASC)
```

用途：当全量重建遇到相同成绩时保持 deterministic，但相同秒数仍不刷新当前纪录。

## 7. 字段质量前置条件

RC-01 已确认当前 `duration/duration_sec` 来自 `total_timer_time`，不能直接冻结为 elapsed。Registry 只定义 metric，不负责字段来源选择。

Performance Summary 必须先提供：

```json
{
  "distance_m": 10026,
  "elapsed_time_sec": 3278,
  "time_quality": "reliable_elapsed",
  "distance_quality": "reliable_distance",
  "reason_codes": []
}
```

Resolver 使用要求：

- `distance_m > 0`
- `elapsed_time_sec > 0`
- `time_quality == "reliable_elapsed"` 才能自动确认。
- `time_quality in {"timer_time_only", "semantics_unknown"}` 最高进入候选。
- 缺失或非正数时间/距离直接忽略。

## 8. 真实库迁移注意事项

RC-02 只读 dry-run 结论：

- `running_5k` active 不变。
- `running_10k` active 会从活动 `108` 变为活动 `150`。
- 活动 `108` 是 9.53095km，超出新 `±3%`，且 `duration_sec` 比轨迹 elapsed 短 44 秒。
- `running_half_marathon` active 不变，但当前表内 `event_date` 与 Activity 本地日期存在一天差异，后续 API/数据任务必须冻结日期来源。
- `running_marathon` 当前无候选。

迁移要求：

- 任何正式应用前必须经过 dry-run 和人工复核。
- 不得把规则迁移伪装成当天刷新纪录。
- 若 active 替换来自规则变化，应写 `recalculated`/migration 事件，而不是新纪录庆祝事件。

## 9. 测试用例表

| 编号 | 场景 | 输入 | 预期 |
| --- | --- | --- | --- |
| REG-001 | key 唯一 | 重复 `running_5k` | Registry validation 失败 |
| REG-002 | 单位合法 | `canonical_unit = "seconds"` | 通过 |
| REG-003 | 非法单位 | `canonical_unit = "sec"` | 失败 |
| REG-004 | 比较方向合法 | `lower_is_better` | 通过 |
| REG-005 | 非法比较方向 | `faster_is_better` | 失败 |
| REG-006 | source mode 合法 | `activity_total` | 通过 |
| REG-007 | 区间不重叠 | V1 四项定义 | 通过 |
| REG-008 | 区间冲突 | 新增与 5K 重叠定义 | 失败 |
| MATCH-001 | 5K 下边界 | 4850m | 匹配 `running_5k` |
| MATCH-002 | 5K 标准 | 5000m | 匹配 `running_5k` |
| MATCH-003 | 5K 上边界 | 5150m | 匹配 `running_5k` |
| MATCH-004 | 5K 下边界外 | 4849.99m | 不匹配 |
| MATCH-005 | 5K 上边界外 | 5150.01m | 不匹配 |
| MATCH-006 | 10K 下边界 | 9700m | 匹配 `running_10k` |
| MATCH-007 | 10K 上边界 | 10300m | 匹配 `running_10k` |
| MATCH-008 | 半马标准 | 21097.5m | 匹配 `running_half_marathon` |
| MATCH-009 | 全马标准 | 42195m | 匹配 `running_marathon` |
| CMP-001 | 首条纪录 | 无 current，候选 3278s | active，improvement null |
| CMP-002 | 更快刷新 | current 3300s，候选 3278s | 刷新，improvement 22 |
| CMP-003 | 相同秒数 | current 3278s，候选 3278s | 不刷新 |
| CMP-004 | 更慢 | current 3278s，候选 3300s | 不刷新 |
| CMP-005 | 非正时间 | 0s 或 -1s | 忽略 |
| CMP-006 | 非正距离 | 0m 或 -1m | 忽略 |
| CMP-007 | 旧 timer time | `time_quality = timer_time_only` | 最高候选，不自动 active |
| CMP-008 | 旧语义未知 | `time_quality = semantics_unknown` | 最高候选，不自动 active |

## 10. RC-08 代码化输入

后续代码化最小交付：

- `RecordDefinition` 不可变数据结构。
- `RUNNING_RECORD_DEFINITIONS` 或等价 Registry。
- `get_record_definition(key)`。
- `iter_enabled_record_definitions(sport=None, source_mode=None)`。
- `match_record_definitions(summary)`。
- `validate_record_registry()`。
- Registry 单元测试覆盖第 9 节。
