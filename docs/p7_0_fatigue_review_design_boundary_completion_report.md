# P7.0 复盘分析驾驶舱设计边界确认完成报告

## 1. 任务目标

确认 P7 复盘分析驾驶舱的设计边界，确保后续 UI 实现只吸收草图中“分析”页对应的复盘内容结构，不误改现有活动详情顶部、Tab 系统或提前开放 AI 洞察。

## 2. 本次改动

- 更新 `docs/fatigue_review_realignment_plan_v1.md`
  - 新增 P7 状态总览。
  - 新增 `P7 复盘分析驾驶舱` 章节。
  - 明确 P7.0 当前状态、设计边界、数据与架构契约、P7.x 任务拆分和验收标准。
  - 将推荐执行顺序延伸到 P7。
- 更新 `docs/detail_tab_review_manual_test_checklist.md`
  - 新增 `1.1.2 P7.0 复盘分析驾驶舱设计边界` 手工用例。
  - 新增 `6.2 P7 设计边界门禁`。

## 3. 已冻结边界

- 保持现有活动详情顶部信息：活动标题、时间、设备、路线等继续使用既有设计。
- 保持现有详情 Tab 系统：项目“复盘”Tab 等价于草图“分析”页。
- 不实现草图最右侧首页、活动、日历等全局导航按钮。
- 不实现草图顶部分享、导出等全局动作区。
- AI 洞察入口继续保持 P6.1 冻结态：按钮置灰、无 onclick、不触发 `call_llm`。

## 4. 契约约束

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 前端不得从 speed/time/total_distance_m/points/DOM 推导事实字段。
- `curves.distance` 仍是图表 X 轴、疲劳带和事件定位的唯一后端权威距离来源。
- `metrics / fatigue_zones / collapse_events / context_tags / advice / disclaimer` 只能从后端 snapshot 白名单读取。
- 字段缺失、数组为空或运动类型不适用时展示空态、弱化态或“待接入”，不得前端补算。
- P7 UI 改造不得写 DB，不得改 canonical 数据，不得让 AI 输出参与指标计算。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 禁止进入复盘主展示和 AI 输入。

## 5. 后续任务建议

- P7.1：复盘 Tab 信息架构稿。
- P7.2：顶部分析摘要带。
- P7.3：核心指标驾驶舱。
- P7.4：主图容器与图例。
- P7.5：事件与疲劳区间说明。
- P7.6：建议与上下文侧栏。
- P7.7：响应式与可读性检查。
- P7.8：视觉回归测试与手工清单。
- P7.9：UI 定稿后 AI 入口复核。

## 6. 验证

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：44 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与本次 P7.0 文档边界确认无关。
