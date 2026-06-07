# V6 端到端验收 Checklist（人工实测）

> **契约依据**:fit-arch-contrac §3 响应结构 / §5.4 + §5.6.2 AI 边界 / §6 shadow_diff 隔离 / §7.2 安全 / §8 canonical 只读
> **自动化覆盖**:见 [tests/test_e2e_fatigue_review.py](../tests/test_e2e_fatigue_review.py)（31 个测试全绿）
> **本文档范围**:自动化无法覆盖的 UI 交互 / 视觉 / 设备实测场景

---

## 0. 环境准备

- [ ] 启动主程序（开发模式: `python src/main.py` 或 WebView 启动命令）
- [ ] 准备至少 1 个真实 FIT 文件（含 `heart_rate` / `altitude` / `distance` / `timestamp`）
- [ ] 推荐准备 2 份：
  - **样本 A**: 30-60 分钟跑步，正常完成（应**不**触发 Bonk）
  - **样本 B**: 90+ 分钟跑步，模拟长距离糖原耗尽（应**触发** Bonk，需要 `total_calories >= 1600`）
- [ ] 打开 DevTools（macOS: `Cmd+Option+I`），切到 Console 标签
- [ ] 切到 Network 标签 → Filter 输入 `fatigue_review` → 准备观察 API 调用

---

## 1. 进入运动记录

- [ ] 点击顶部「**个人运动数据**」Tab
- [ ] 在「**运动记录**」列表中点开样本 A
- [ ] **预期**:详情舱全屏打开（z-index=9999, 100vw × 100vh）
- [ ] **预期**:头部看到 3 个按钮：**🔍 进入复盘**（紫色高亮） / **← 返回活动列表** / **× 关闭**
- [ ] **预期**:详情舱内**只有** `📌 活动总结`（metrics）+ `📈 圈速统计`（lap table）+ 轨迹缩略图，**无** ECharts 容器（6.1 瘦身验收）

---

## 2. 复盘覆盖层打开

- [ ] 点击「**🔍 进入复盘**」按钮
- [ ] **预期**:
  - 详情舱 overlay 关闭（`#activity-detail-overlay` 移除 `open`）
  - 复盘覆盖层全屏打开（z-index=10000, `#fatigue-review-overlay` 添加 `open`）
  - 标题为「🔍 运动复盘」
  - 副标题 `加载中...` → 数据填充后更新为「跑步 · 5.0km · 31:25」
- [ ] **DevTools Network**:观察到 1 次 `get_fatigue_review` POST/GET，response 状态 200
- [ ] **DevTools Response**:data 字段必须 7 段（`metrics` / `collapse_events` / `curves` / `context_tags` / `ai_insight` / `advice` / `disclaimer`）

---

## 3. 4 个 metric 卡验证

- [ ] **心率漂移**:显示百分比 + 等级（极佳/良好/轻度/严重/未知）
- [ ] **解耦率**:同上
- [ ] **Bonk 风险**:显示「高」/「低」 + 置信度（low/medium）
- [ ] **崩溃事件**:显示数字（如 "0" 或 "1"），下面子标签显示「含 X 起严重」
- [ ] **样本 A 验收**:Bonk 风险应该是「低」，崩溃事件应该是 0（前提：样本 A 总热量 < 1600）
- [ ] **样本 B 验收**:Bonk 风险应该是「高」，崩溃事件应该有 1 条（触发 Bonk 状态机）

---

## 4. ECharts 三层图验证（**V7.1 关键**）

- [ ] 图表正常渲染（无 100px 塌陷，没有「图表加载失败」）
- [ ] **红色实线**:心率（HR, yAxisIndex: 0, 左侧 Y 轴）
- [ ] **蓝色实线**:实际速度（Speed, yAxisIndex: 1, 右侧 Y 轴）
- [ ] **金色虚线**:GAP 等效速度（**V7.1 之前是空数组，V7.1 之后必有数据**）—— 重点观察
- [ ] 鼠标 hover 任一曲线 → tooltip 正常显示「距离 / 数值」
- [ ] **样本 B 验收**:如果 Bonk 触发，图表 GAP 曲线上应能看到一个 `⚠️` 金色图钉（markPoint）
- [ ] **DevTools 检查**:打开 `Elements` → `#fatigue-review-chart` → 找到 `canvas` 元素 → 确认宽度 ≈ 父容器宽度（不是 100px 塌陷）

---

## 5. 事件列表 + 双向联动

- [ ] 如果 Bonk 触发，事件列表显示「BONK_WARNING · 12.5 km」卡片
- [ ] 第一项有 `.active` 紫色高亮（CSS class `event-card.active`）
- [ ] 鼠标 hover 卡片 → 卡片背景变深（`#334155`）
- [ ] **点击事件卡片** → 对应 markPoint 金色图钉**闪烁 1.5 秒**（`ECharts dispatchAction({type: 'highlight'})`）
- [ ] **DevTools Console**:无循环日志（`_fatigueReviewLinkageActive` 1.5s 防循环生效）
- [ ] **没有 Bonk 触发时**:事件列表显示「本次训练未检测到关键事件」友好提示

---

## 6. AI 洞察 4 态

### 6.1 初始态
- [ ] `📋 总评` 显示「点击右上角「生成 AI 洞察」开始分析」
- [ ] 按钮显示「🤖 生成 AI 洞察」（可点击）

### 6.2 Loading 态
- [ ] 点击「🤖 生成 AI 洞察」
- [ ] **预期**:按钮立即变「⏳ 分析中...」且 **disabled**（CSS 透明度变 0.55）
- [ ] **预期**:`📋 总评` 显示「⏳ AI 正在分析...」

### 6.3 Success 态（mock LLM 正常返回）
- [ ] **预期**:
  - `summary` 字段填充 120 字以内的中文总评
  - 4 个 `key_dimensions`（耐力/心肺稳定/撞墙风险/环境压力），每个含 label/level/comment
  - `event_interpretation` 事件整体解读（如果无事件则为空）
  - `training_advice` 改进建议
  - `disclaimer` 免责声明
- [ ] 按钮恢复「🤖 重新生成 AI 洞察」

### 6.4 Error 态（mock LLM 失败）
- [ ] **预期**:
  - `summary` 显示「❌ AI 洞察暂不可用: <error msg>」（红色）
  - 按钮显示「🤖 重试 AI 洞察」
- [ ] **DevTools Network**:`call_llm` 调用 response.ok === true（**V4.0 §5.6.2 规则 7**:错误用 empty_xxx_insight，不抛 promise reject）

### 6.5 Empty 态（mock LLM 返回空 summary）
- [ ] **预期**:
  - `summary` 显示「📭 数据不足」或「📭 <training_advice>」友好提示
  - 按钮显示「🤖 重试 AI 洞察」

---

## 7. 阅后即焚 3 触发点（**V6.3 §5.6.2 规则 5**）

### 7.1 触发点 ① 关闭触发
- [ ] 已生成 AI 洞察
- [ ] 点击「**← 返回详情**」→ 复盘覆盖层关闭
- [ ] 重新点击「🔍 进入复盘」→ 同一活动
- [ ] **预期**:AI 状态清空（`📋 总评` 重新显示「点击右上角「生成 AI 洞察」开始分析」）

### 7.2 触发点 ② 切换活动触发
- [ ] 活动 A 已生成 AI 洞察
- [ ] 返回详情舱 → 打开活动 B
- [ ] 进入 B 的复盘覆盖层
- [ ] **预期**:AI 状态清空

### 7.3 触发点 ③ 重新点击触发
- [ ] 活动 A 已生成 AI 洞察
- [ ] 再次点击「🤖 重新生成 AI 洞察」
- [ ] **预期**:旧 AI 状态清空 → loading 态 → 重新生成

---

## 8. 资源回收

- [ ] 关闭复盘覆盖层（点击「← 返回详情」）
- [ ] 打开 DevTools → Memory 标签 → 拍 snapshot
- [ ] 在 Console 执行：
  ```js
  console.log(Object.keys(profileAnalysisChartInstances));
  ```
- [ ] **预期**:输出 `["profile-analysis-chart"]`（或其他非"fatigue-review-chart"键），**不包含** `fatigue-review-chart`
- [ ] 重新打开复盘覆盖层 → 实例重建（`profile-analysis-chart` 多出一个 `fatigue-review-chart` key）

---

## 9. 响应式

- [ ] 浏览器窗口缩放到 **1024px**（Desktop 边界）→ 左 320px + 右 1fr
- [ ] 缩放到 **800px**（Tablet） → 左 30% + 右 70%（垂直堆叠）
- [ ] 缩放到 **600px**（Tablet）→ 同上，head 仍水平
- [ ] 缩放到 **375px**（Mobile） → 左 40% + 右 60%，metric-bar **2 列**，head **垂直堆叠**
- [ ] 缩放到 **320px**（极小屏）→ 仍可滚动，head/AI 面板/图表不溢出

---

## 10. 契约验收（DevTools Console）

### 10.1 响应结构
- [ ] Network → 任意 `get_fatigue_review` response：
  ```json
  {
    "code": 0,
    "msg": "ok",
    "data": { ... 7 段白名单 ... },
    "traceId": "<12位hex>"
  }
  ```

### 10.2 shadow_diff 隔离
- [ ] Console 执行：
  ```js
  JSON.stringify(window.lastFatigueReviewData || {})
  ```
- [ ] 输出中**不包含** `shadow_diff` / `shadow_diff_json` / `diff` / `records` / `unknown_msgs`

### 10.3 错误码
- [ ] 故意调用不存在的活动 ID:
  ```js
  window.pywebview.api.get_fatigue_review(99999).then(console.log)
  ```
- [ ] **预期**:`{code: 1004, msg: "未找到该活动记录", ...}`

- [ ] 故意传非法参数:
  ```js
  window.pywebview.api.get_fatigue_review(-1).then(console.log)
  ```
- [ ] **预期**:`{code: 1001, msg: "activity_id 必须为正整数", ...}`

### 10.4 Sentinel 唯一性
- [ ] Console 执行：
  ```js
  const a = [window.__TEST_FATIGUE_REVIEW_SENTINEL__ || '__FATIGUE_REVIEW_INSIGHT__'];
  console.log(a);
  ```
- [ ] **预期**:`["__FATIGUE_REVIEW_INSIGHT__"]`（4 个独立 sentinel 之一）

### 10.5 traceId 12 位 hex
- [ ] 任意 response 的 `traceId` 字段 = 12 位 hex 字符串（如 `ab12cd34ef56`）

---

## 11. 异常 Case

### 11.1 删掉 FIT 文件后再进入复盘
- [ ] 在 DB 中保留记录但**删除**原 FIT 文件
- [ ] 进入复盘
- [ ] **预期**:`code: 1004` 或 `_gap_error` 字段携带降级提示，UI 显示「数据不足」

### 11.2 LLM 网关断开
- [ ] 关闭 LLM 网关（或修改配置 `llm_base_url` 指向不存在的端点）
- [ ] 点击「🤖 生成 AI 洞察」
- [ ] **预期**:不抛 promise reject（DevTools Console 无 unhandled promise rejection 红色错误）
- [ ] **预期**:UI 显示 error 态，按钮变「🤖 重试 AI 洞察」

### 11.3 hr_curve 为空
- [ ] 导入无 HR 数据的 FIT 文件
- [ ] 进入复盘
- [ ] **预期**:ECharts 不报错，图表显示速度 + GAP（无 HR 红色实线）
- [ ] **预期**:metric 卡的心率漂移 / 解耦率 / Bonk 全部显示 `--` 或 0.0

### 11.4 完全空 records
- [ ] 极端 case:records < 2 条
- [ ] **预期**:`GapCalculator` 返回 `_empty_result("insufficient_valid_records")`
- [ ] 复盘覆盖层:`gap_curve = []` `efficiency_curve = []`
- [ ] **预期**:UI 优雅降级，metric 卡显示 `--`，事件列表显示「本次训练未检测到关键事件」

---

## 12. 性能（高级）

- [ ] `get_fatigue_review` 调用耗时 < 200ms（无 GAP 引擎时）
- [ ] `get_fatigue_review` 调用耗时 < 500ms（V7.1 GAP 引擎启用后，单 FIT 1000 records）
- [ ] 复盘覆盖层打开 → 首次 ECharts 渲染 < 100ms
- [ ] AI 洞察 4 态切换期间不卡顿（UI 响应 < 50ms）
- [ ] 关闭复盘覆盖层 → GPU/CPU 占用恢复（DevTools Performance 标签）

---

## 13. V6.4-6.8 合并验收（任务 6.2 + 6.3 范围）

| 原任务 | 当前合并 | 验证点 |
|---|---|---|
| 6.4 复盘覆盖层结构 | ✅ 任务 6.2 | 步骤 2 |
| 6.5 4 个 metric 卡 | ✅ 任务 6.2/6.3 | 步骤 3 |
| 6.6 双向联动 | ✅ 任务 6.3 | 步骤 5 |
| 6.7 AI 4 态 | ✅ 任务 6.3 | 步骤 6 |
| 6.8 响应式 3 断点 | ✅ 任务 6.2 | 步骤 9 |

**注**:6.4-6.8 已被合并到 6.2+6.3 实施完成，不需单独验收。

---

## 14. V7.1 验收

- [ ] 步骤 4 中 GAP 金色虚线**必现**（不再是 6.3 之前的空数据）
- [ ] GapCalculator.calculate(records) 真正在 Resolver 流程中被调用
- [ ] Bonk 状态机真实触发：样本 B 满足 1600 kcal + 后半程断崖 15% 时，`insight_events` 含 `BONK_WARNING`
- [ ] `decoupling_rate` 仍为 0.0（V7.13 任务升级，本任务不扩展）

---

## 验收完成签字

| 验收项 | 通过 | 备注 |
|---|---|---|
| 1. 进入运动记录 | ☐ | |
| 2. 复盘覆盖层打开 | ☐ | |
| 3. 4 metric 卡 | ☐ | |
| 4. ECharts 三层图 | ☐ | |
| 5. 事件列表 + 双向联动 | ☐ | |
| 6. AI 洞察 4 态 | ☐ | |
| 7. 阅后即焚 3 触发点 | ☐ | |
| 8. 资源回收 | ☐ | |
| 9. 响应式 | ☐ | |
| 10. 契约验收 | ☐ | |
| 11. 异常 Case | ☐ | |
| 12. 性能 | ☐ | |
| 14. V7.1 | ☐ | |

测试人:_____________ 日期:_____________ 备注:______________________
