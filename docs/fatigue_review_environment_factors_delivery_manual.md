# 疲劳复盘外部影响语义优化交付手册

## 1. 背景

本次优化针对疲劳复盘中“外部影响”文案误判问题：某骑行活动天气为 `21.7°C / 湿度 89%`，界面却评价为“温度偏高，心率更容易上浮”。这不是单纯的大模型幻觉，而是后端压力标签、环境事实、前端展示文案三层职责混用导致的系统性问题。

已确认的当前代码现状：

- `metrics_resolver.py` 在 `context_tags` 中按单一温度阈值注入热应激，`>=20°C` 即标记为 `Moderate 热应激`。
- `main.py` 已有 `environment_context`，但该字段只表达中性天气事实，不表达用户可见的“外部影响结论”。
- `track.html` 将 `热应激 / Heat Stress / temperature / 温度 / 散热` 等关键词统一映射为“温度偏高，心率更容易上浮”，导致高湿低中温场景被误写成高温。
- `llm_backend.py` prompt 已要求区分 `environment_context` 与 `context_tags`，但还缺少一个可被 UI 与 AI 共同消费的结构化解释层。

## 2. 本次目标

一次性修复外部影响语义的一类问题，而不是每发现一个错误文案就打一个补丁。

目标包括：

- 21°C 左右高湿不再被描述为“温度偏高”。
- 跑步、骑行、徒步、登山、户外游泳按运动类型生成不同外部影响解释。
- 前端不再通过关键词猜测环境文案。
- AI 不再把中性天气事实误读为压力标签。
- 保留未来接入 AI 知识库或更复杂环境模型的扩展空间。

## 3. 非目标

本次不做以下事项：

- 不重构完整天气服务。
- 不新增数据库字段或表。
- 不把 `environment_challenge` 整套旧模块重做。
- 不计算 WBGT、Heat Index 或伪精确热风险指数。
- 不从前端 DOM、ECharts、截图、标题、设备、轨迹点重新推导环境事实。
- 不处理泳池游泳；游泳只考虑户外游泳。
- 不引入 AI 知识库能力，只保留字段扩展弹性。

## 4. 字段职责合同

### 4.1 `environment_context`

用途：表达天气和环境事实。

性质：中性事实层，不直接代表压力或影响。

示例：

```json
{
  "has_weather": true,
  "weather_label": "晴",
  "temperature_c": 21.7,
  "humidity": 89.0,
  "wind_speed_kmh": 7.6,
  "observed_date": "2026-07-22",
  "observed_hour": 5,
  "pressure_level": "none",
  "summary": "天气晴，21.7°C，湿度89%，风速7.6km/h；未识别到明显外部环境压力。"
}
```

### 4.2 `environment_factors`

用途：表达后端已经识别、可直接展示给用户的外部影响解释。

性质：解释层，是本次新增字段；UI 和 AI 均应优先消费它。

推荐结构：

```json
[
  {
    "key": "humidity",
    "category": "weather",
    "severity": "mild",
    "label": "湿度偏高",
    "comment": "温度本身不高，但湿度 89%，体感可能偏闷，散热效率可能下降。",
    "basis": {
      "temperature_c": 21.7,
      "humidity": 89.0,
      "wind_speed_kmh": 7.6
    },
    "confidence": "medium"
  }
]
```

字段约束：

- `key`：稳定机器键，如 `humidity`、`heat`、`wind`、`cold`、`altitude`、`water_temperature_missing`。
- `category`：建议使用 `weather`、`terrain`、`altitude`、`water`、`data_quality`。
- `severity`：建议使用 `info`、`mild`、`moderate`、`high`。
- `label`：短标签，用于卡片标题或列表项。
- `comment`：完整用户可见解释。
- `basis`：只放标量事实，不放 points、records、curves、DOM 文本。
- `confidence`：建议使用 `low`、`medium`、`high`。

### 4.3 `context_tags`

用途：表达压力/影响标签，主要用于 AI 解释时提高宽容度，避免把环境导致的自然生理代偿误判为用户能力不足。

性质：压力标签层，不应承载中性天气事实，也不应作为前端首选文案来源。

约束：

- 不再把 `20°C` 级别的普通温度注入为热应激。
- 只在确有压力时注入，例如明显高温、高海拔、糖原耗竭风险、极高心肺负荷。
- 旧数据兼容时，前端可以 fallback 到 `context_tags`，但不能继续使用粗暴关键词映射。

## 5. 运动类型语义规则

### 5.1 跑步 / 越野跑

主要关注：

- 温度
- 湿度
- 风
- 爬升
- 海拔

温湿度规则：

- `<25°C`：不得说“温度偏高”。
- `20–25°C + 湿度 >= 80%`：输出“湿度偏高 / 体感偏闷”。
- `25–28°C + 湿度 >= 70%`：输出“温湿度偏高”。
- `28–30°C`：输出“热环境压力”。
- `>=30°C`：输出“高温 / 热应激”。

### 5.2 骑行 / 公路骑行 / 山地车

主要关注：

- 温湿度
- 风
- 爬升
- 海拔

特殊规则：

- 骑行存在风冷效应，同温度下热压力判断应比跑步更保守。
- `21–24°C + 高湿` 只输出“湿度偏高 / 体感偏闷”，不得输出“温度偏高”。
- 不做顺逆风判断，除非后端未来提供路线方向、风向和分段事实。

### 5.3 徒步

主要关注：

- 温湿度
- 爬升
- 海拔
- 暴露时长

特殊规则：

- 徒步不是“跑得慢的跑步”，文案要弱化配速/心率漂移口径。
- 高湿可以解释为体感闷、补水需求上升、长时间暴露更吃状态。
- 爬升和海拔优先级高于跑步式热应激。

### 5.4 登山

主要关注：

- 海拔
- 爬升
- 低温
- 风寒
- 天气变化

特殊规则：

- 不套用跑步热应激语义。
- 低温/大风时走“低温 / 风寒”语义。
- 高海拔应优先解释为缺氧压力，不应轻易归因于耐力不足。

### 5.5 户外游泳

本次只考虑户外游泳，不处理泳池游泳。

主要关注：

- 水温
- 风速
- 开放水域天气
- 心率数据可信度

特殊规则：

- 水温优先于气温。
- 无 `water_temperature_c` 时，不得推断水温压力。
- 气温 `21°C + 高湿` 不应生成“温度偏高”。
- 可以生成低置信度因素：`缺少水温数据，户外游泳环境判断有限`。
- 风速较高时，可提示开放水域体感和安全影响。
- 游泳心率解释要更保守，避免直接写“心率更容易上浮”。

## 6. 推荐实现位置

### 6.1 `main.py`

新增：

- `_build_fatigue_review_environment_factors(...)`

调用位置：

- `_empty_fatigue_review_snapshot(...)` 中补空数组。
- `_build_fatigue_review_snapshot(...)` 构建 `environment_context` 后构建 `environment_factors`。
- `_build_fatigue_review_insight_snapshot(...)` compact snapshot 中加入 `environment_factors`。

### 6.2 `metrics_resolver.py`

调整：

- 收紧 `context_tags["热应激 (Heat Stress)"]` 注入阈值。
- 删除 `>=20°C` 的 `Moderate 热应激` 注入。
- 保留明显高温时对 AI 的宽容提示。

建议第一版先不要修改 `classify_heat_stress()` 和 `environment_challenge`，因为它们已有独立测试和 UI-only 合同；先把疲劳复盘用户可见路径修准。

### 6.3 `track.html`

调整：

- `_buildFatigueReviewOverviewDimensions(data)` 优先读取 `data.environment_factors`。
- `_renderFatigueReviewContextFactors(...)` 支持 `environment_factors`。
- `_fatigueReviewContextFactorCopy(...)` 只作为旧 `context_tags` fallback，且删除“温度关键词必定温度偏高”的硬编码。

### 6.4 `llm_backend.py`

调整：

- prompt 中说明 `environment_factors` 是后端已识别的外部影响解释。
- 明确 `<25°C` 不得称为“温度偏高”。
- 高湿应写“湿度偏高 / 体感偏闷”。
- 户外游泳无水温时不得推断水温压力。

### 6.5 `docs/js_api_contract.json`

同步补充：

- `get_fatigue_review(activity_id)` 返回 `environment_factors`。
- `__FATIGUE_REVIEW_INSIGHT__` compact snapshot 包含 `environment_factors`。
- 前端不得从 DOM/ECharts/截图/标题/天气卡补算该字段。

## 7. 验收矩阵

| 场景 | 期望 |
| --- | --- |
| 跑步，17°C / 77% | 有天气事实，无明显外部压力，不生成热应激 |
| 跑步，21.7°C / 89% | 生成“湿度偏高 / 体感偏闷”，不说“温度偏高” |
| 骑行，21.7°C / 89% | 生成“湿度偏高”，不说“温度偏高”，不注入热应激 |
| 徒步，24°C / 90% | 生成温和的“体感偏闷 / 长时间暴露”解释 |
| 登山，5°C / 大风 | 生成“低温 / 风寒”语义，不走热应激 |
| 登山，高海拔 | 生成海拔压力解释 |
| 户外游泳，21°C / 高湿 / 无水温 | 不生成温度压力；提示缺少水温，环境判断有限 |
| 户外游泳，有低水温 | 生成水温偏低 / 冷刺激解释 |
| 跑步，28°C / 75% | 生成热环境压力 |
| 跑步，32°C / 60% | 生成高温 / 热应激 |

## 8. 推荐验证命令

优先运行聚焦测试：

```bash
PYTHONPATH=. .venv312/bin/python -m pytest \
  tests/test_fatigue_review_snapshot_realignment.py \
  tests/test_fatigue_review_prompts.py \
  tests/test_fatigue_review_ai_preflight_p8.py \
  tests/test_fatigue_review_quality_gate.py \
  tests/test_v9_0_detail_tab_review.py \
  tests/test_response_envelope_contract.py \
  tests/test_fatigue_review_e2e_contract.py \
  tests/test_resolver_sport_isolation.py \
  -q
```

如仅验证本次新增矩阵，优先跑新增测试文件或新增测试类，再扩大到上述集合。

## 9. 交付完成标准

- `environment_factors` 出现在普通复盘 snapshot 和 AI compact snapshot 中。
- 21.7°C / 89% 骑行不再显示“温度偏高”。
- `<25°C` 场景不会通过 AI prompt 或前端 fallback 写成高温。
- 跑步、骑行、徒步、登山、户外游泳均有回归测试。
- `docs/js_api_contract.json` 与测试白名单同步更新。
- 不引入 DB schema 改动。
- 不触碰活动同步、导入去重、生涯记录等无关链路。
