# 脉图 AI 个性化交付手册 v1

## 1. 背景与目标

脉图当前已经支持通过 CLI 或 HTTP 网关接入大模型。现有 AI 功能主要基于后端生成的数据快照进行解读，例如单次活动复盘、雷达图洞察、活动建议和全局 AI 助手。这种方式符合当前架构契约：FIT 与 DB 是事实源，后端 Resolver 负责语义翻译，AI 负责解释和建议。

长期目标不是让 AI 直接访问本地数据库，而是建立一个受控的「用户运动记忆系统」。AI 看到的不是原始表、token、完整轨迹或内部字段，而是后端生成、可追溯、可删除、可更新的长期画像与记忆摘要。

目标形态：

- AI 能理解用户长期运动习惯、能力边界、恢复趋势和风险模式。
- AI 的个性化建议有明确事实依据，且可追溯到系统摘要。
- AI 不直接连接数据库，不写入事实字段，不篡改 FIT/DB。
- 用户可以查看、修正、删除 AI 记忆，形成反馈闭环。
- 个性化能力本地优先，可在 CLI 或 HTTP 网关两种大模型通道下工作。

## 2. 行业方向参考

当前主流运动 AI 产品大体正在从「单次活动解读」走向「长期画像 + 趋势记忆 + 目标管理 + 反馈闭环」。

### 2.1 Strava Athlete Intelligence

Strava 的 Athlete Intelligence 侧重把单次活动与近期趋势翻译为用户可理解的摘要。它强调用 AI 解释配速、心率、爬升、功率、Relative Effort 等活动指标，适合轻量复盘和社交表达。

对脉图的启发：

- 单次活动快照仍然是高频 AI 入口。
- AI 输出要避免堆指标，应把复杂数据翻译成用户听得懂的运动反馈。
- 近期趋势可以作为单次活动解读的上下文，但不应让 AI 直接读取全量历史。

参考：

- Strava Athlete Intelligence: https://support.strava.com/en-us/articles/15401629-athlete-intelligence-on-strava
- Strava Press: https://press.strava.com/articles/stravas-athlete-intelligence-translates-workout-data-into-simple-and

### 2.2 WHOOP Coach

WHOOP Coach 更接近长期个性化教练。它围绕恢复、HRV、睡眠、压力、行为和目标提供对话式解释，并强调用户持续佩戴数据带来的个性化理解。

对脉图的启发：

- 长期生理画像比单次活动更能支撑「懂我」。
- AI 需要知道用户的恢复基线、疲劳模式和生活行为上下文。
- 反馈闭环很重要，用户行为与主观反馈能改进后续建议。

参考：

- WHOOP Coach: https://www.whoop.com/us/en/thelocker/whoop-unveils-the-new-whoop-coach-powered-by-openai/
- OpenAI WHOOP case: https://openai.com/index/whoop/

### 2.3 Garmin Connect+ Active Intelligence

Garmin Connect+ 的 Active Intelligence 强调基于健康与活动数据提供个性化洞察，并随用户数据积累而更个性化。Garmin 的优势在于设备生态和长期生理/训练数据。

对脉图的启发：

- 个性化不是把原始数据交给 AI，而是平台先把健康和活动数据组织为可信洞察。
- 「随着系统更了解你」应落到长期画像、趋势摘要和目标状态上。
- 授权、隐私和数据边界应成为产品能力的一部分。

参考：

- Garmin Connect+ press release: https://www.garmin.com/en-US/newsroom/press-release/wearables-health/elevate-your-health-and-fitness-goals-with-garmin-connect/
- Garmin Active Intelligence support: https://support.garmin.com/en-US/?faq=kWi5DoaMPZ4VCJBA0lFWP7

### 2.4 Runna / AI 训练计划产品

Runna 这类产品重点在目标、计划、执行与调整。它们不是只解释单次运动，而是根据用户目标与执行反馈持续调整训练安排。

对脉图的启发：

- 目标管理是个性化 AI 的核心输入。
- AI 建议应与用户下一步行动连接，例如训练、恢复、补给、装备和周期安排。
- 计划执行结果和用户反馈应回写到「个性化记忆」，但不能直接改写事实数据。

参考：

- Runna: https://www.runna.com/
- Runna App Store: https://apps.apple.com/us/app/runna-running-plans-coach/id1594204443

## 3. 产品原则

### 3.1 AI 不直连数据库

AI 不允许直接访问 SQLite、FIT 文件目录、tokenstore、账号授权文件或任意本地文件。所有 AI 输入必须由后端白名单函数生成。

原因：

- 防止隐私泄露。
- 防止 AI 误读内部字段。
- 防止绕过 Resolver 语义层。
- 保持 FIT/DB/Resolver/UI 的架构边界。

### 3.2 后端生成长期画像

个性化上下文由后端周期性生成，存储为结构化 JSON，而不是让 AI 临时查询数据库。长期画像可以由活动、恢复、趋势、目标和用户反馈组成。

### 3.3 AI 只解释、建议和提出记忆候选

AI 不直接写事实字段。AI 可以输出：

- 解读文本。
- 建议。
- 待确认的记忆候选。
- 待确认的目标调整建议。

最终是否写入长期记忆，由后端规则和用户确认决定。

### 3.4 所有记忆必须可追溯

每条长期记忆必须包含来源、更新时间、置信度和证据摘要。禁止生成无来源的「AI 印象」。

### 3.5 用户拥有记忆控制权

用户必须可以查看、删除、禁用或修正 AI 记忆。错误记忆不应长期污染后续建议。

## 4. 总体架构

建议新增五层：

1. 长期画像层：由后端从 DB 和 Resolver 输出生成结构化画像。
2. 记忆卡片层：存放稳定、可追溯、可编辑的个性化模式。
3. 目标与计划层：存放用户当前目标、备赛、训练周期和约束。
4. 反馈闭环层：记录用户对 AI 建议的反馈，不写入事实字段。
5. AI 上下文装配层：按场景选择最小必要画像与记忆，生成 compact snapshot。

推荐数据流：

```text
FIT / GPX / Provider Sync
  -> Resolver
  -> DB canonical fields
  -> Long-term profile builder
  -> Memory cards / Goal state / Feedback summary
  -> AI context assembler
  -> CLI or HTTP LLM
  -> AI response / memory candidates
  -> user confirmation / backend validation
```

禁止数据流：

```text
AI -> SQLite
AI -> FIT raw files
AI -> tokenstore
AI -> arbitrary local path
AI -> direct DB mutation
```

## 5. 数据模型建议

### 5.1 长期运动画像 user_athlete_profile

用途：描述用户整体运动状态，主要供 AI 上下文使用。

建议字段：

```json
{
  "profile_version": 1,
  "updated_at": "2026-07-07T12:00:00+08:00",
  "windows": {
    "last_30d": {},
    "last_90d": {},
    "last_180d": {},
    "last_365d": {}
  },
  "sports": {
    "running": {
      "frequency_per_week": 4.2,
      "typical_distance_km": [6, 14],
      "typical_duration_min": [35, 90],
      "typical_pace_sec_per_km": [300, 390],
      "long_run_km_p80": 18.5,
      "hr_drift_pattern": "moderate_after_60min",
      "confidence": "medium"
    },
    "cycling": {
      "frequency_per_week": 1.1,
      "typical_distance_km": [30, 85],
      "power_available": true,
      "fatigue_pattern": "late_power_drop"
    }
  },
  "recovery": {
    "hrv_baseline": 58,
    "resting_hr_baseline": 52,
    "sleep_pattern": "late_bedtime_weekdays",
    "confidence": "low"
  },
  "risk_patterns": [
    "long_run_late_hr_drift",
    "hot_weather_performance_drop"
  ]
}
```

生成原则：

- 只使用 DB/API 契约字段，不从 UI、DOM、图表数据推导。
- 指标必须标注窗口期。
- 不足样本必须降级 confidence。
- 不把 AI 判断写入该画像，除非由后端规则确认。

### 5.2 AI 记忆卡片 ai_memory_cards

用途：存放稳定的个性化模式。

建议结构：

```json
{
  "id": "mem_20260707_hr_drift_long_run",
  "type": "user_pattern",
  "title": "长距离后程心率漂移倾向",
  "summary": "近 90 天多次 60 分钟以上跑步中，后半程心率漂移更明显。",
  "evidence": {
    "window": "last_90d",
    "sample_count": 12,
    "positive_count": 8,
    "metrics": ["hr_drift", "duration_sec", "avg_pace"]
  },
  "confidence": "medium",
  "status": "active",
  "source": "system_summary",
  "created_at": "2026-07-07T12:00:00+08:00",
  "updated_at": "2026-07-07T12:00:00+08:00"
}
```

记忆类型：

- `user_pattern`：长期行为或表现模式。
- `risk_pattern`：反复出现的风险。
- `preference`：表达风格、训练偏好、提醒偏好。
- `goal`：用户目标或备赛状态。
- `correction`：用户纠正过的 AI 误判。

状态：

- `candidate`：AI 或系统提出，等待确认。
- `active`：生效。
- `dismissed`：用户拒绝。
- `archived`：过期或被新证据替代。

### 5.3 用户目标 user_goals

用途：让 AI 建议有方向，而不是泛泛分析。

建议结构：

```json
{
  "id": "goal_2026_autumn_half_marathon",
  "type": "race",
  "sport_type": "running",
  "title": "秋季半马",
  "target_date": "2026-10-18",
  "target_outcome": "finish_strong",
  "constraints": {
    "max_training_days_per_week": 5,
    "avoid_days": ["Monday"],
    "injury_notes": []
  },
  "status": "active",
  "updated_at": "2026-07-07T12:00:00+08:00"
}
```

### 5.4 AI 反馈 ai_feedback_events

用途：建立反馈闭环。

建议事件：

- `helpful`：建议有帮助。
- `not_helpful`：建议无帮助。
- `wrong_reasoning`：原因判断错。
- `user_correction`：用户给出纠正。
- `adopted`：建议被采纳。
- `ignored`：建议未采纳。

建议结构：

```json
{
  "id": "fb_20260707_001",
  "target_type": "activity_insight",
  "target_id": "activity_343",
  "feedback_type": "user_correction",
  "text": "这次不是疲劳，是天气太热导致心率高。",
  "created_at": "2026-07-07T12:00:00+08:00"
}
```

## 6. AI 上下文装配

不同 AI 场景只装配最小必要上下文。

### 6.1 单次活动复盘

输入：

- 当前活动复盘快照。
- 同运动类型近 30/90 天摘要。
- 与本次活动相关的 3 到 5 条记忆卡片。
- 当前目标摘要，如有。

禁止：

- 全量轨迹点。
- 全量历史活动。
- 原始 FIT 字段。
- DB 内部字段。

### 6.2 雷达图洞察

输入：

- 当前雷达快照。
- 各维度近 90 天趋势摘要。
- 与恢复、负荷、强度相关的记忆卡片。

输出：

- 近期训练状态解释。
- 风险提示。
- 下一步建议。

### 6.3 活动建议

输入：

- 当前路线事实白名单。
- 用户显式填写的计划上下文。
- 相关目标。
- 相关偏好记忆，例如补给偏好、装备提醒偏好。

禁止：

- 历史天气直接拼入 prompt。
- DOM 文本。
- 前端统计 fallback。

### 6.4 全局 AI 助手

输入：

- 用户长期画像摘要。
- 活跃目标。
- 最近 7/30/90 天摘要。
- 少量相关记忆卡片。

注意：

- 全局助手不是数据库查询器。
- 用户问具体活动时，后端必须先定位活动并生成专用快照，再交给 AI。

## 7. 产品功能设计

### 7.1 AI 记忆中心

位置建议：系统配置页或个人运动数据页新增「AI 记忆」入口。

功能：

- 查看当前有效记忆。
- 查看记忆证据。
- 删除记忆。
- 暂停某类提醒。
- 确认或拒绝 AI 记忆候选。

### 7.2 AI 反馈按钮

在 AI 输出底部增加轻量反馈：

- 有帮助
- 不准确
- 不想再看到
- 补充原因

反馈必须写入 `ai_feedback_events`，不直接改 DB 事实字段。

### 7.3 周报/月报

新增周期总结：

- 本周训练负荷。
- 本周恢复状态。
- 本周最佳活动。
- 本周风险模式。
- 下周建议。

周报/月报由后端先生成事实摘要，再由 AI 写成自然语言。

### 7.4 目标追踪

新增目标模块：

- 创建目标。
- 目标进展。
- 训练一致性。
- 风险偏离。
- AI 建议下一步。

AI 可以建议目标调整，但必须由用户确认。

## 8. 隐私与安全要求

### 8.1 最小上下文原则

每次 AI 调用只传当前任务必要字段。不得因为「可能有用」传全量历史。

### 8.2 本地优先

长期画像和记忆卡片默认存本地数据库。若用户使用 HTTP 网关，应明确提示发送给大模型的上下文范围。

### 8.3 可导出与可删除

用户应可以导出或删除 AI 记忆与反馈数据。

### 8.4 敏感字段黑名单

永不进入 AI 上下文：

- token、cookie、授权文件路径。
- 账号密码、MFA。
- 原始数据库路径。
- 完整 FIT 文件。
- 全量轨迹点。
- 未白名单的内部调试字段。
- shadow_diff/debug-only 数据。

## 9. 实施路线

### Phase 1：长期画像 MVP

目标：让 AI 拥有稳定的长期运动摘要。

任务：

- 新增长期画像 builder。
- 生成 last_30d / last_90d / last_180d 摘要。
- 支持 running / cycling / hiking 三类基础画像。
- 在全局 AI 助手和单次复盘中接入画像摘要。

验收：

- AI 上下文中出现长期画像摘要。
- 长期画像只来自后端 DB/API 契约字段。
- 无原始轨迹点、无 token、无 debug 字段。

### Phase 2：记忆卡片

目标：沉淀稳定用户模式。

任务：

- 新增 `ai_memory_cards` 表或 JSON 存储。
- 支持系统生成候选记忆。
- 支持用户确认、删除、归档。
- AI 上下文按场景选择相关记忆。

验收：

- 记忆有证据、置信度、来源和状态。
- 用户可删除。
- AI 不直接写 active 记忆。

### Phase 3：反馈闭环

目标：让 AI 输出能被用户纠正。

任务：

- AI 输出增加反馈入口。
- 新增 `ai_feedback_events`。
- 每周汇总反馈，生成 correction 记忆候选。

验收：

- 用户反馈可持久化。
- 反馈不会改写活动事实。
- AI 下次回答能避开已纠正误判。

### Phase 4：目标与周期总结

目标：从解释工具升级为训练陪伴系统。

任务：

- 新增目标管理。
- 新增周报/月报。
- 将目标状态接入复盘、活动建议和全局助手。

验收：

- AI 建议与用户目标关联。
- 周报/月报事实摘要可追溯。
- 用户可关闭周期总结。

## 10. 验收清单

架构验收：

- AI 不直接访问 DB。
- AI 输入由后端白名单函数生成。
- Resolver 是语义翻译层。
- 记忆卡片不存原始轨迹点。
- AI 输出不写事实字段。

产品验收：

- 用户能看到 AI 记忆。
- 用户能删除 AI 记忆。
- 用户能反馈 AI 输出。
- AI 回答能体现长期画像。
- AI 能区分事实、推断和建议。

安全验收：

- AI 上下文不含 token、cookie、密码、MFA。
- AI 上下文不含完整 file_path，除非是明确授权的本地工具任务。
- AI 上下文不含 shadow_diff/debug 字段。
- HTTP 网关模式下可显示本次发送摘要。

质量验收：

- 样本不足时输出低置信度。
- 记忆过期或被新证据推翻时自动归档。
- 错误反馈能生成 correction 候选。
- 周期总结可复现同一事实输入。

## 11. 推荐优先级

最高优先级：

1. 长期画像 MVP。
2. AI 上下文装配器。
3. 记忆卡片数据模型。
4. 记忆中心 UI。

第二优先级：

1. 用户反馈闭环。
2. 周报/月报。
3. 目标追踪。

暂不建议优先做：

- AI 直接 SQL 查询。
- AI 自动改训练计划并写入事实表。
- 全量历史活动直接塞进 prompt。
- 让 HTTP 网关长期保存用户完整运动数据。

## 12. 一句话结论

脉图 AI 个性化的正确方向不是让 AI 直接访问数据库，而是让后端把用户长期运动事实加工成「可控、可追溯、可删除」的长期画像和记忆卡片。AI 基于这些受控上下文提供解释、建议和反馈闭环，才能既越来越懂用户，又不破坏本地优先和数据契约。
