# 环境挑战卡片 手工测试清单 (V_ENV.1.14)

> **版本**:v1.0(V_ENV.1.x Phase 1 MVP)
> **适用版本**:环境挑战 P0(1.1~1.7)+ P1 测试(1.8~1.11)全部通过
> **对齐契约**:fit-arch-contrac §2.1 全链路 / §五 AI 边界 / §六 审计字段隔离
> **关联文档**:`docs/environment_challenge_v1_contract.md`
> **核心目的**:在自动化测试覆盖之外,补充真实 pywebview + 真实 LLM + 真实 DB 下的端到端验收

---

## 0. 前置条件

### 0.1 环境
- [ ] App 正在运行(`python main.py` 已启动 pywebview)
- [ ] 数据库 `~/.fitvault/user_profile.db` 存在且有数据
- [ ] LLM 网关**无需连通**(本卡片不消费 AI Snapshot)

### 0.2 数据准备(至少 5 个 sport 各 1 条)
- [ ] **running** 至少 1 条 FIT 文件
- [ ] **trail_running** 至少 1 条 FIT 文件
- [ ] **hiking** 至少 1 条 FIT 文件
- [ ] **cycling** 至少 1 条 FIT 文件
- [ ] **mountain_biking** 至少 1 条 FIT 文件
- [ ] **skiing** 至少 1 条 FIT 文件(用于低温替换测试)
- [ ] **mountaineering** 至少 1 条 FIT 文件(用于低温替换测试)

### 0.3 准备工具
- [ ] 打开 pywebview DevTools(`F12` 或右键 → Inspect)
- [ ] Console 标签页保留,准备看 `renderActivityDetailSidebar` 调用日志
- [ ] 准备截图工具,记录每个测试的最终卡片效果

---

## 1. 侧栏顺序验证(任务 1.7 验收)

### 1.1 测试目标
验证「环境挑战」卡片插入到「训练收益」下方、5 张卡完整按序排列。

### 1.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 启动 app,打开任意活动详情 | 弹出 Modal,定位到「概览」Tab |  |
| 2 | 视觉确认右侧栏卡片顺序 | 顺序为:**🌦 历史天气 → 🔥 训练收益 → ⛰️ 环境挑战 → ❤️ 身体状态(占位)→ ✨ 活动摘要(占位)** |  |
| 3 | 检查「环境挑战」卡片标题 | 标题为 "⛰️ 环境挑战",副标题显示运动类型中文(SPORT_TYPE_CN 映射) |  |
| 4 | 检查「环境挑战」卡片 4 行 | 4 行:爬升挑战 / 海拔环境 / 温度环境 / 技术路线 |  |
| 5 | 检查「技术路线」行 | 右侧显示 "—"(Phase 1 占位,Phase 2 上线后会显示数值) |  |
| 6 | DevTools Console 检查 | 无 `shadow_diff` 警告 / 无 `environment_challenge` 错误 |  |

### 1.3 验收准则
- [ ] **AC-1**:5 张卡完整显示,无丢失
- [ ] **AC-2**:`⛰️ 环境挑战` 在 `🔥 训练收益` 之后、`❤️ 身体状态` 之前
- [ ] **AC-3**:卡片样式与 `🌦 历史天气` / `🔥 训练收益` 视觉一致(玻璃态 + 行式布局)
- [ ] **AC-4**:`技术路线` 行显示 `—`(Phase 1 占位)

---

## 2. 5 种运动类型切换(任务 1.2 / 1.3 验收)

### 2.1 测试目标
验证 **5 种核心运动(running / trail_running / hiking / cycling / mountain_biking)** 都返回各自的 4 子块语义,**同等级不同运动不同语义**。

### 2.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开 running 活动详情 | 4 行 label 走 `RUNNING_SEMANTICS` |  |
| 2 | 打开 trail_running 活动详情 | 4 行 label 走 `TRAIL_RUNNING_SEMANTICS`(与 running 不完全相同) |  |
| 3 | 打开 hiking 活动详情 | 4 行 label 走 `HIKING_SEMANTICS` |  |
| 4 | 打开 cycling 活动详情 | 4 行 label 走 `CYCLING_SEMANTICS` |  |
| 5 | 打开 mountain_biking 活动详情 | 4 行 label 走 `MOUNTAIN_BIKING_SEMANTICS` |  |
| 6 | 对比 running vs trail_running 同一海拔/爬升/温度数据 | 至少 1 个 label 文本不同(语义不同) |  |

### 2.3 验收准则
- [ ] **AC-5**:5 个运动类型都返回 `phase: 1`、`data_source: "fit_sdk"`
- [ ] **AC-6**:每个运动的 4 子块 label 互不相同(同等级不同运动不同语义)
- [ ] **AC-7**:`sport_type` 在 `environment_challenge` 内透传原值(不被翻译)
- [ ] **AC-8**:副标题正确显示运动类型中文标签(从 `SPORT_TYPE_CN` 查表)

---

## 3. 滑雪/登山低温替换(任务 1.3 `_classify_cold_level` 验收)

### 3.1 测试目标
验证 `skiing` 和 `mountaineering` 的 `heat` 子块**自动走低温 5 档**(与普通运动的高温 4 档解耦)。

### 3.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开 skiing 活动详情,温度 -15°C | `heat.label` = 「低温环境」 / level=2 / 标题显示「🌡️ 低温环境」(非「温度环境」) |  |
| 2 | 打开 skiing 活动详情,温度 0°C | `heat.label` = 「温度舒适」 / level=0(0°C 归低温第 0 档) |  |
| 3 | 打开 skiing 活动详情,温度 -30°C | `heat.label` = 「严寒环境」 / level=3 |  |
| 4 | 打开 skiing 活动详情,温度 -35°C | `heat.label` = 「极寒挑战」 / level=4 |  |
| 5 | 打开 mountaineering 活动详情,温度 -10°C | `heat.label` = 「略低温」 / level=1 |  |
| 6 | 对比 skiing 与 trail_running 同一温度 -15°C | skiing 显示低温;trail_running 显示「山地气候舒适」 |  |

### 3.3 验收准则
- [ ] **AC-9**:skiing/mountaineering 的 `heat` 标题为「🌡️ 低温环境」(普通运动为「🌡️ 温度环境」)
- [ ] **AC-10**:skiing/mountaineering 的 `heat.label` 取自 `COLD_SEMANTICS`(5 档:温度舒适/略低温/低温环境/严寒环境/极寒挑战)
- [ ] **AC-11**:skiing/mountaineering 的 `heat.metric_value` 是**温度值**(非 product)—— 控制台打印应见 `-15` 而非 `null`
- [ ] **AC-12**:skiing/mountaineering 的非 heat 子块走兜底表(skiing → trail_running, mountaineering → hiking)

---

## 4. 海拔 5 档分级(任务 1.1 `classify_altitude_stress` 验收)

### 4.1 测试目标
验证 `altitude` 子块按 `max_altitude_m` 严格映射到 0~4 档。

### 4.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开海平面附近(running 100m)活动 | `altitude.level=0` / label = 「低海拔环境」 |  |
| 2 | 打开 1499m 山顶活动 | `altitude.level=0`(临界,严格小于 1500 归 0) |  |
| 3 | 打开 1500m 山顶活动 | `altitude.level=1` / label = 「轻度压力」 或对应运动语义 |  |
| 4 | 打开 3499m 活动 | `altitude.level=2` |  |
| 5 | 打开 3500m 活动 | `altitude.level=3` / label = 「高海拔…环境」 |  |
| 6 | 打开 4500m 活动 | `altitude.level=4` / label = 「极限高海拔…」 |  |
| 7 | 打开 8848m(珠峰)活动 | `altitude.level=4` |  |

### 4.3 验收准则
- [ ] **AC-13**:5 档临界值 1500/2500/3500/4500 严格按调研报告 §3.2 表映射
- [ ] **AC-14**:每档的 label 文案根据 `sport_type` 不同(如 hiking「极限高海拔环境」/ running「极限高海拔挑战」)

---

## 5. 爬升挑战 5 档分级(任务 1.3 `_classify_climb_density_level` 验收)

### 5.1 测试目标
验证 `climb_density = total_ascent / distance` 派生 + 5 档映射。

### 5.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开平路跑步(0 爬升/10km)活动 | `climb.metric_value=0.0` / level=0 / label = 「平路路线」 |  |
| 2 | 打开稍有起伏(150m/10km=15)活动 | `climb.metric_value=15.0` / level=1 / label = 「略有起伏」 |  |
| 3 | 打开持续爬升(450m/10km=45)活动 | `climb.metric_value=45.0` / level=2 / label = 「持续爬升路线」 |  |
| 4 | 打开高强度爬升(800m/10km=80)活动 | `climb.metric_value=80.0` / level=3 / label = 「高强度爬升跑」 |  |
| 5 | 打开极限爬升(1500m/10km=150)活动 | `climb.metric_value=150.0` / level=4 / label = 「极限爬升挑战」 |  |

### 5.3 验收准则
- [ ] **AC-15**:`climb.metric_value` 保留 2 位小数(round(2))
- [ ] **AC-16**:5 档临界值 10/30/60/100 严格按调研报告 §3.1 表映射
- [ ] **AC-17**:`distance_km <= 0` 不会触发异常(降级 0.0)

---

## 6. 温度 4 档分级(普通运动,任务 1.1 `classify_heat_stress` 验收)

### 6.1 测试目标
验证普通运动(running / cycling 等) `heat` 子块按 product = temp × humidity 映射 0~3 档。

### 6.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 跑步 20°C × 0.5 湿度 = 10 | `heat.level=0` / label = 「环境舒适」 |  |
| 2 | 跑步 28°C × 0.6 湿度 = 16.8(湿度低) | `heat.level=0` / 数学上 product<500(注:调研报告 §3.3 文档示例是 Level 1,但数学判 Level 0) |  |
| 3 | 跑步 30°C × 0.7 湿度 = 21 | `heat.level=0`(同上,数学判定) |  |
| 4 | 跑步 50°C × 1.0 湿度 = 50 | `heat.level=0` |  |
| 5 | 跑步 600°C × 1.0 = 600(极端合成) | `heat.level=1` |  |
| 6 | 跑步 2000°C × 1.0 = 2000 | `heat.level=2` |  |
| 7 | 跑步 3000°C × 1.0 = 3000 | `heat.level=3` / label = 「高温耐力挑战」 |  |
| 8 | 跑步 35°C + 无 humidity(单维度降级) | `heat.level=2`(30≤t<35 档) |  |
| 9 | 跑步 无温度 + 无 humidity | `heat.level=0` / `metric_value=None` |  |

### 6.3 验收准则
- [ ] **AC-18**:`heat.metric_value` 是 round(1) 的 product(非温度,非 humidity)
- [ ] **AC-19**:4 档临界值 500/1200/2100 严格按数学判定
- [ ] **AC-20**:`temp_c is None` → level=0,`metric_value=None`
- [ ] **AC-21**:`humidity is None` 走单维度温度粗分(4 档按 25/30/35 临界)

---

## 7. humidity 三入口防御性归一化(任务 1.3 `_resolve_humidity_0to1` 验收)

### 7.1 测试目标
验证 `humidity` 来自 `raw["weather"]` / `meta["weather"]` / `meta["humidity"]` 三个入口,均经防御性归一化(0~1 vs 0~100)。

### 7.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | raw.weather.humidity=85(0~100) | 归一 0.85,30°C × 0.85 = 25.5,`metric_value=25.5` |  |
| 2 | raw.weather.humidity=0.85(0~1) | 直接传,30°C × 0.85 = 25.5,`metric_value=25.5` |  |
| 3 | meta.weather.humidity=70(0~100,raw 无 weather) | 归一 0.7,30°C × 0.7 = 21.0 |  |
| 4 | meta.humidity=0.5(裸字段) | 直接传,30°C × 0.5 = 15.0 |  |
| 5 | raw.weather.humidity=150(异常 > 100) | 视为 None,`metric_value=None`,降级 |  |
| 6 | raw.weather.humidity=-10(异常 < 0) | 视为 None |  |
| 7 | raw.weather.humidity=100(边界) | 归一 1.0,`metric_value=30.0`(30°C × 1.0) |  |

### 7.3 验收准则
- [ ] **AC-22**:三入口均能消费,优先级 `raw["weather"]` > `meta["weather"]` > `meta["humidity"]`
- [ ] **AC-23**:`h > 1.0` 自动除 100(Open-Meteo / Garmin 百分数归一)
- [ ] **AC-24**:`h <= 1.0` 直接传(用户传入 0~1)
- [ ] **AC-25**:`h > 100` 视为 None(异常值降级)

---

## 8. 降级路径(任务 1.1 / 1.2 / 1.3 综合验收)

### 8.1 测试目标
验证所有可能的降级路径不抛异常、显示合理占位。

### 8.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开老 FIT 文件(无 total_ascent) | `climb.metric_value=0.0` / level=0 |  |
| 2 | 打开老 FIT 文件(无 max_altitude) | `altitude.metric_value=0.0` / level=0 |  |
| 3 | 打开老 FIT 文件(无 avg_temperature) | `heat.metric_value=None` / level=0 |  |
| 4 | 打开老 FIT 文件(无 weather) | `heat` 走单维度降级 |  |
| 5 | 打开 treadmill_running(未在表中) | 4 子块 label 走 running 兜底 |  |
| 6 | 打开 swimming(未在表中) | 4 子块 label 走 running 兜底 |  |
| 7 | 打开 < 10m 距离的迷你活动 | `climb.metric_value=0.0`(防除零) |  |

### 8.3 验收准则
- [ ] **AC-26**:所有降级路径不抛异常
- [ ] **AC-27**:未匹配运动(非 8 键)走 running 兜底,fallback 文案合理
- [ ] **AC-28**:`climb_density` 在 `distance=0` 时返回 0.0,level=0

---

## 9. §六 审计字段隔离(任务 1.4 / 1.10 验收)

### 9.1 测试目标
验证 `environment_challenge` 绝不携带 `shadow_diff` / `shadow_diff_json` 字段;前端的 `shadow_diff` 隔离逻辑生效。

### 9.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | DevTools Console 执行:`copy(record.detail.environment_challenge)` | 4 子块不含 `shadow_diff` 任何变体 |  |
| 2 | 手动注入 `environment_challenge.shadow_diff = {x: 1}`(测试桩) | 卡片消失(前端 `if (ec.shadow_diff ...) return ''`) |  |
| 3 | 手动注入 `environment_challenge.climb.shadow_diff = {x: 1}`(测试桩) | 卡片消失(同源) |  |
| 4 | DevTools Network 检查 AI 洞察调用 | 任何 LLM 请求都不含 `environment_challenge` payload |  |
| 5 | DB 查询 `ai_snapshots` 表 | 不含 `environment_challenge` JSON |  |

### 9.3 验收准则
- [ ] **AC-29**:`environment_challenge` 4 子块均无 `shadow_diff` / `shadow_diff_json` / `diff`
- [ ] **AC-30**:前端 `if (ec.shadow_diff || ec.shadow_diff_json || ec.diff)` 校验生效,命中即返空
- [ ] **AC-31**:AI 洞察 / AI snapshot / `ai_snapshots` 表均不含 `environment_challenge`

---

## 10. 切 Tab / 切 sport 状态保留(任务 1.7 验收)

### 10.1 测试目标
验证切换不同 Tab / sport state 时,「环境挑战」卡片正确重新渲染,不出现陈旧数据。

### 10.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 打开活动 A(running 1000m/10km),看卡片 | 4 子块数据 |  |
| 2 | 切到「复盘」Tab,再切回「概览」Tab | 卡片数据**重新拉取**或保持缓存均可,但不能错位(跑 A 渲染 B 数据) |  |
| 3 | 关闭活动 A,打开活动 B(trail_running 500m/5km) | 卡片切到 B 的数据 |  |
| 4 | 在 A 详情页切 sport filter(若支持) | 卡片重渲染 |  |
| 5 | DevTools Console 检查 | 无 `record.detail.environment_challenge is undefined` 错误 |  |

### 10.3 验收准则
- [ ] **AC-32**:切 Tab 不出现陈旧数据(数据归属当前 activity_id)
- [ ] **AC-33**:切 sport 不出现 null pointer
- [ ] **AC-34**:Console 无与 `environment_challenge` 相关的 error/warn

---

## 11. §五 AI 边界(任务 1.10 验收)

### 11.1 测试目标
验证前端**不消费** `points[]` / `records[]`,**不计算**任何指标。

### 11.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | DevTools Console:`copy(record.detail.environment_challenge)` | 所有 `metric_value` 是数字(无 NaN / 无 undefined) |  |
| 2 | DevTools Console:`Object.keys(record.detail.environment_challenge)` | 含 `sport_type / climb / altitude / heat / technical_terrain / phase / data_source` |  |
| 3 | 修改 `record.detail.environment_challenge.climb.metric_value = 9999` | UI 立即刷新显示 9999(证明前端无缓存) |  |
| 4 | 反向断言:DevTools 触发 `get_environment_challenge_semantic` | 报 ReferenceError(前端无此函数,纯消费) |  |

### 11.3 验收准则
- [ ] **AC-35**:`metric_value` 全部为 `number` 或 `null`(无 `undefined` / 无 `NaN`)
- [ ] **AC-36**:`_buildEnvironmentChallengeCard` 函数体内不含 `points[]` 引用(静态 grep 验证)
- [ ] **AC-37**:前端**不调用** `get_environment_challenge_semantic` / `classify_*` / `calculate_climb_density`

---

## 16. v1.1 释义字段验收(任务 2.1~2.8 验收)

### 16.1 测试目标
验证 v1.1 升级:`label` 字段从 `str` 升级为 `dict{label, explanation}`,前端展示**等级文案 + 释义短语双层信息**,**不展示原始 `metric_value` 数字**。

### 16.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | DevTools `Object.keys(record.detail.environment_challenge.climb)` | 包含 `metric_name` / `metric_value` / `level` / `label` |  |
| 2 | `record.detail.environment_challenge.climb.label` | 是**对象**(非字符串) |  |
| 3 | `climb.label.label` | 是字符串,如「极限爬升挑战」 |  |
| 4 | `climb.label.explanation` | 是字符串,如「极端爬升密度,纯靠爬升能力,建议分段休息」 |  |
| 5 | 视觉确认 UI | 4 行(climb/altitude/heat/terrain)中 climb/altitude/heat 3 行**显示释义**,terrain 行**不显示释义** |  |
| 6 | 视觉确认「爬升挑战」行的右侧 | **不显示** `100.01` 这样的密度数字(§五 5.1 边界) |  |
| 7 | 视觉确认「温度环境」行的右侧 | 同上,只显示等级 + label + 释义,无 product 数字 |  |
| 8 | 视觉确认「技术路线」行 | 显示「—」+ 不显示 explanation(Phase 1 占位) |  |
| 9 | DevTools 测 `esc(block.label.explanation)` 字符串含 `<script>` | 渲染后**不执行脚本** |  |
| 10 | 切换 running → trail_running 活动 | 释义文案**随之变化**(同等级不同运动不同语义) |  |
| 11 | 切换 skiing 活动 | 温度环境的 label + explanation 都来自 `COLD_SEMANTICS`(低温 5 档) |  |
| 12 | 浏览器 DevTools Console | 无 `TypeError: Cannot read property 'label' of undefined` 错误 |  |

### 16.3 验收准则
- [ ] **AC-40**:`climb.label` / `altitude.label` / `heat.label` 是 `object` 类型,含 `label` + `explanation` 两键
- [ ] **AC-41**:`technical_terrain.label` 仍是 `string "--"`,不渲染 explanation
- [ ] **AC-42**:`metric_value` 数字**不在 UI 任何位置显示**(静态 grep track.html 无 `metric_value` 引用在前端)
- [ ] **AC-43**:`explanation` 字符串经 `esc()` 防护,XSS 不生效
- [ ] **AC-44**:6 运动 × 4 模块 × 5/4 档 = 120 条 explanation 全部有内容(单元测试覆盖)

### 16.4 关键文案抽检(每运动 × 每档 1 条)

| 运动 | level | label 期望 | explanation 关键字(应包含) |
|---|---|---|---|
| running | 0 | 平路路线 | "几乎无爬升" |
| running | 4 | 极限爬升挑战 | "分段休息" |
| trail_running | 3 | 高强度山地爬升 | "爬升能力" |
| hiking | 4 | 极限长爬升路线 | "充分准备" |
| cycling | 2 | 长爬坡路线 | "档位" |
| mountain_biking | 4 | 极限山地骑行挑战 | "爬坡能力" |
| skiing(heat) | 0 | 温度舒适 | "0°C" |
| skiing(heat) | 4 | 极寒挑战 | "专业防寒" |
| mountaineering(heat) | 2 | 低温环境 | "全套防寒" |

---

## 12. 数据契约版本(任务 1.13 §10 验收)

### 12.1 测试目标
验证 `phase` 字段存在,便于未来 Phase 2 切换。

### 12.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 任意活动详情 DevTools:`record.detail.environment_challenge.phase` | 等于 `1` |  |
| 2 | `record.detail.environment_challenge.data_source` | 等于 `"fit_sdk"` |  |
| 3 | 未来 Phase 2 上线后 | 验证 `phase=2` 时 `technical_terrain.available=true` |  |

### 12.3 验收准则
- [ ] **AC-38**:`phase=1` 在所有活动详情中一致
- [ ] **AC-39**:`data_source="fit_sdk"` 标识稳定(§2.2 可信分层)

---

## 13. 综合验收清单

### 13.1 数据流闭环

- [ ] 导入 FIT → `MetricsResolver.resolve()` 注入 `final_data["environment_challenge"]` → `get_activity_detail` API 透传 → 前端 `_buildEnvironmentChallengeCard` 消费 → 5 张卡第 3 张位置渲染

### 13.2 性能基线(粗略)

- [ ] 单条活动详情 Modal 打开 ≤ 200ms(环境挑战派生可忽略不计)
- [ ] 切 Tab 重新渲染 ≤ 50ms

### 13.3 跨浏览器 / 跨平台

- [ ] macOS 12+ (Safari / Chrome / Edge)
- [ ] Windows 10+ (Chrome / Edge)
- [ ] pywebview 5.0+(项目固定版本)

---

## 14. 已知问题 / 预存在失败(任务 1.13 §10.2 登记)

| # | 问题 | 责任 |
|---|---|---|
| 1 | `test_v9_2_overview_m0.py` 7 个失败 | V9.2.3 grid 重构者(track.html 现状与旧测试规约错位) |
| 2 | `test_laps_real_data.py` 2 个失败 | schema 迁移维护者(`_ensure_schema_initialized` 签名) |

**修复责任与本任务无关**。

---

## 15. 签字

| 角色 | 姓名 | 日期 | 备注 |
|---|---|---|---|
| 实施者 |  |  |  |
| 验收者 |  |  |  |
| 复核者 |  |  |  |

---

> **本清单 44 个 AC 验证项(AC-1~AC-44)+ 5 个综合验收项 = 49 个验收点**。Phase 1 MVP 全部覆盖(含 v1.1 释义字段增强 AC-40~AC-44),Phase 2 上线后需追加 GPS curvature 验收(待 §4.4 子任务启动)。
