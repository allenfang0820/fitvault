# 多运动记录中心 V2 最新契约摘要

更新时间：2026-07-17

本文是记录中心 V2 的唯一滚动契约摘要。旧的 PB 状态链、candidate/active 写入报告、RCV2 执行链和 AI summary 相关内容不再作为实现依据。

## 1. 产品定位

记录中心 V2 展示的是从历史活动中计算出的多运动指标成绩序列。

核心链路：

```text
历史活动 -> 指标计算 -> activity-level metric series -> 当前最佳 -> 纪录刷新节点
```

当前最佳和纪录刷新节点是成绩序列的派生结果，不是右侧折线图的唯一数据源。

## 2. UI 契约

主图区固定为：

```text
左侧：记录指标项
右侧：选中指标的历史活动成绩折线图 / 演进分析
```

UI 改动范围为小到中等：不重做页面结构，不恢复数据卡片，主要替换右侧折线图的数据语义和点位标记。

左侧指标项展示：

- 指标名称
- 当前最佳成绩
- 当前最佳日期
- 可用状态

右侧主图展示：

- 所有可计算历史活动在该指标下的成绩点
- 当前最佳点高亮
- 刷新历史最佳的节点标记
- 选中点的 Activity 来源、窗口范围和质量说明

右侧主图需要调整：

- 数据源从 PB history 兼容层切换为 `get_career_record_metric_series()`。
- 每个点代表一条历史活动的指标成绩。
- 当前最佳点使用高亮样式。
- PB/纪录突破点使用 marker 或标签。
- 底部列表展示活动成绩点，而不是 active/superseded 状态链。

禁止：

- 用 PB active/superseded 两点链替代历史活动成绩序列。
- 在右侧恢复当前记录数据卡片。
- 重做左侧指标项、运动 tabs 或整体布局。
- 前端计算距离窗口、功率窗口、scope、置信度或历史最佳。
- 前端调用 preview/rebuild/materializer。
- 接入 AI summary / AI insight。

## 3. 数据分层

本方案采纳“事实按活动保存，统计动态生成或缓存”的参考原则。

明确采纳：

- 不直接把周最佳、月最佳、年最佳作为主事实存储。
- 每条活动产生可计算的指标成绩点。
- 当前最佳、年度最佳、月度最佳、生涯最佳都从成绩点派生。
- PB 突破是成绩点上的派生事件或标签。
- 多级索引 / materialized view 只作为缓存，可重建。

术语修正：

- 每条活动的指标成绩称为 `Record Metric Result`，不是 PB。
- 刷新历史最佳的节点称为 `Record Event`。
- 当前最佳、月最佳、年最佳等称为 `Record Index` 或 materialized view。

### Catalog

定义运动、指标、单位、比较方向、scope、质量门禁和可用状态。

### Metric Series

每条记录表示某个 Activity 在某个 record_key 下计算出的成绩。

建议模型名：

```text
career_record_metric_results
```

核心字段：

- `activity_id`
- `record_key`
- `sport`
- `event_date`
- `metric_value`
- `metric_unit`
- `display_value`
- `range_json`
- `quality_json`
- `scope_hash`
- `resolver_version`

### Current Best

从 metric series 中按指标比较方向选出。

### Record Progression

按时间扫描 metric series，找出刷新历史最佳的节点。它用于图上标记，不是主数据源。

### Record Index

Record Index 是缓存层，不是事实层。

可缓存：

- 当前最佳
- 年度最佳
- 月度最佳
- 周最佳
- Record Timeline
- 趋势摘要

所有索引必须可以从 metric series 重建。

## 4. 计算口径

跑步标准距离：

- 5K、10K、半马、全马。
- 每条跑步活动计算活动内连续距离窗口 Best Effort Distance。
- 每条活动每个 record_key 最多生成一个最佳成绩点。

骑行标准距离：

- 10K、20K、40K、50K、100K、180K。
- 使用 Best Effort Distance。
- 需要距离流、暂停语义和 GPS 质量门禁。

骑行功率：

- 5s、30s、1m、5m、10m、20m、30m、60m、2h。
- 每条活动计算对应窗口最大平均功率。

整次活动类：

- 最长距离、最大累计爬升、最长历时、最高海拔等。
- 可从活动 summary 生成成绩点。

游泳：

- 泳池依赖 lengths/laps/pool length。
- 公开水域依赖可靠 GPS/距离流。
- 样本不足或质量不足时必须展示受控空态或待验证状态。

## 5. API 契约

新增或重构目标 API：

```text
get_career_record_metric_series(record_key, filters)
```

返回 ViewModel：

- `record_key`
- `sport`
- `points[]`
- `current_best`
- `record_progression`
- `summary`
- `filters`
- `status`
- `metrics`

`points[]` 必须包含：

- `activity_id`
- `event_date`
- `metric`
- `range`
- `quality`
- `is_current_best`
- `is_record_breaking`

已有 `get_career_records()` 可继续提供左侧当前最佳摘要，但其结果必须从 metric series 派生。

## 6. 状态契约

指标状态：

- `available`
- `partial`
- `validation_required`
- `sample_missing`
- `unsupported`

成绩点质量：

- `high_confidence`
- `estimated`
- `fallback`
- `validation_required`

## 7. 性能契约

切换运动或指标时不得全量扫描历史 FIT/track。

允许：

- 导入/刷新活动时增量计算。
- 后台 materialize/cache。
- 只读 ViewModel 聚合。

禁止：

- 前端触发 preview。
- 切换标签时临时全量 materializer。
- 用 AI 或 LLM 补齐缺失成绩。

## 8. 当前纠偏结论

此前 PB active/superseded history 只能表达“纪录刷新链”，不能表达“历史活动成绩变化”。

记录中心 V2 后续开发必须以 activity-level metric series 为主数据源。

## 9. 可扩展能力

采用 metric series + record event + record index 后，可以自然支持：

- Record Timeline：展示所有 PB 突破事件。
- 成长曲线：展示每次活动成绩变化。
- 年/月/周最佳：按时间窗口聚合。
- 季节、天气、心率、功率等条件分析。
- 荣誉墙和生涯时间轴。
- 未来 AI 洞察。

这些能力都不得要求重写主数据模型。

### 未来 AI 价值

当前阶段不接入 AI，但数据模型必须让未来 AI 从“读一次数据快照”升级为“理解用户长期运动行为”。

AI 未来可以基于以下结构理解用户：

- 每条活动的指标成绩点。
- PB 突破事件。
- 成绩停滞、恢复、波动和突破周期。
- 不同季节、天气、心率、功率、爬升条件下的表现差异。
- 某个指标在多年里的训练响应和成长轨迹。

因此记录中心底层数据必须保存可追溯、可聚合、可重建的 activity-level metric series，而不是只保存最终 PB。

边界：

- 当前阶段只建设数据基础。
- 不调用 LLM。
- 不写 `career_ai_insights`。
- 不生成 AI 文案。
