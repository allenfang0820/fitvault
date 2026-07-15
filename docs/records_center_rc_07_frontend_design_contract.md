# RC-07 记录中心前端设计与交互冻结

日期：2026-07-13

## 执行提示词

目标：基于 RC-06 ViewModel 完成可交付的记录中心前端设计，明确“当前纪录 / 演进 / 候选”三条路径和所有响应式、状态与交互细节。

范围：运动生涯二级导航、页面结构、桌面/移动布局、三视图、状态、候选交互、新纪录反馈、无障碍与前端验收。

约束：不在设计中加入未交付的骑行、路线、功率曲线占位卡；不让前端 mock 产生新业务规则；不修改 `track.html`。

完成定义：产品、设计、前端和后端可对同一交互逐项确认；Milestone A 完成。

## 1. 原型与截图

可交互线框：

```text
/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe.html
```

桌面验收截图：

```text
/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe-desktop.png
```

移动验收截图：

```text
/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe-mobile.png
```

截图验证：使用本机 Google Chrome + Playwright 渲染，桌面宽度 1280px，移动宽度 390px；未发现明显空白、重叠或横向溢出。

## 2. 信息架构

运动生涯二级导航：

```text
总览 / 时间轴 / 赛事 / 记录 / 荣誉 / 记忆
```

变更冻结：

- 旧导航 `PB` 改为 `记录`。
- 页面标题为 `记录中心`。
- 页面副标题为 `跑步个人纪录` 或等价短文案。
- 卡片内部仍可显示 `5K PB`、`10K PB` 等用户熟悉标签。

页面三视图：

```text
当前纪录 | 演进 | 候选
```

三视图使用 tabs/segmented control，不使用三个大卡片作为导航。

## 3. 当前纪录视图

页面顺序：

1. 页面标题与口径标签。
2. 视图 tabs。
3. 状态带：Ready / Rebuilding / Partial / Error / Candidate。
4. 筛选：运动类型、年份；V1 运动类型仅跑步。
5. 摘要：当前纪录数、近 30 天刷新数、待确认数。
6. 跑步纪录列表。
7. 右侧详情区域；移动端下移为列表后详情。

纪录卡字段：

- 纪录名：`5K PB`、`10K PB`、`半程马拉松`、`马拉松`。
- 当前值：后端 `value_display`。
- 日期：后端 `display_date`。
- 提升：后端 `improvement_display`，首条显示“首次记录”。
- 来源模式：`source_mode_label = 整次活动`。
- 状态徽标：仅后端给出的正式状态，如新纪录。

前端禁止：

- 不计算 PB。
- 不计算 improvement。
- 不判断 confidence。
- 不从距离/标题推导纪录类型。

## 4. 详情区域

点击当前纪录卡后展示详情：

- 纪录标题。
- 成绩。
- 提升量。
- 实际距离。
- 标准距离与误差。
- 计时口径。
- 来源活动标题。
- 判定置信度。
- 打开 Activity Detail 主按钮。

Activity Detail 跳转：

```json
{
  "detail_link": {
    "activity_id": "150",
    "source": "career"
  }
}
```

前端只使用 `detail_link`，不得拼接本地路径或读取 raw media。

## 5. 演进视图

结构：

- 纪录类型选择器。
- 当前纪录摘要。
- 单一纪录类型的演进图。
- 历史节点列表。

图表规则：

- 一次只展示一种 record key。
- 跑步用时越低越好，图表必须明确“用时越低，成绩越好”。
- 可使用反向 Y 轴或提升标记，避免让更快成绩看起来像退步。
- 历史按时间顺序展示，节点使用后端 `history`。
- 只有首条历史时显示稳定空演进，不渲染破碎图表。

## 6. 候选视图

候选卡字段：

- 可能匹配的纪录类型。
- 成绩。
- 实际距离。
- 日期。
- 置信度等级。
- reason display。
- 来源 Activity 入口。
- `确认纪录`。
- `不是有效纪录`。

交互：

- 提交期间禁用两个按钮。
- confirm 成功后刷新 current/history/candidates。
- reject 成功后从候选列表移除。
- API 失败时保留候选，并显示局部错误。
- 候选确认前不得显示为正式纪录。
- 候选不得触发新纪录通知。

## 7. 页面状态

状态来自 RC-06 `status.state`。

| state | 视觉策略 |
| --- | --- |
| `loading` | 固定尺寸骨架，保留布局 |
| `ready` | 正常展示 |
| `empty` | 说明尚无符合规则的记录，提供返回活动入口 |
| `partial` | 展示可用数据，说明缺失或待确认原因 |
| `rebuilding` | 保留旧结果，显示正在重新计算 |
| `error` | 保留上次可用数据，局部错误和重试 |

禁止：

- `undefined`
- `NaN`
- 空 JSON
- 本地路径
- `file://`

## 8. 新纪录反馈

正式激活新纪录时显示轻量通知：

```text
刷新 10K 纪录
47:50，比上次快 35 秒
```

首条纪录：

```text
建立首条 10K 记录
```

不触发通知：

- candidate。
- rejected。
- rebuild 后无变化。
- invalidated 后回退。
- migration/recalculated 替换。

点击通知进入纪录详情。

## 9. 响应式

桌面：

- 左侧运动生涯二级导航。
- 主区域 current 列表 + 右侧详情。
- 摘要三列。
- 演进视图左图右历史。

移动：

- 顶部横向二级导航。
- 单列布局。
- tabs 可换行。
- 摘要、列表、详情纵向排列。
- 候选操作按钮可换行。
- 长中文标题换行或截断，不遮挡成绩。

验收宽度：

- 桌面 1280px。
- 移动 390px。
- 最小支持 320px，后续实现需补前端测试。

## 10. 无障碍

要求：

- tabs 使用 `role="tablist"` / `role="tab"` / `aria-selected`。
- 纪录卡使用原生 button。
- 详情区域使用 `aria-live="polite"`。
- 图表包含 title/desc。
- 图标按钮必须有可访问名称；纯装饰图标 `aria-hidden="true"`。
- 状态不能只靠颜色区分，必须有文字。
- 键盘可切换 tabs、选择纪录、打开 Activity、确认/拒绝候选。

## 11. 组件清单

| 组件 | 数据来源 | 说明 |
| --- | --- | --- |
| RecordsNavItem | static + route | `记录` active 状态 |
| RecordsTabs | local state | 当前纪录/演进/候选 |
| RecordsStatusStrip | API status | 页面状态 |
| RecordsSummary | `get_career_pb.summary` | 当前、近 30 天、候选 |
| RecordCard | `get_career_pb.pb_records[]` | 当前纪录卡 |
| RecordDetail | `get_career_pb_detail.record` | 详情 |
| RecordEvolutionChart | `get_career_pb_history.history` | 演进 |
| CandidateCard | `get_career_pb_candidates.candidates[]` | 候选处理 |
| NewRecordToast | new record event | 轻量通知 |

## 12. RC-19/RC-22 实现输入

RC-19：

- 导航 `PB -> 记录`。
- 页面标题 `记录中心`。
- 当前纪录视图。
- 仅渲染 V1 跑步四项，不展示未交付骑行占位。

RC-20：

- 详情与演进。
- 图表处理 lower-is-better。

RC-21：

- 候选确认/拒绝。
- 提交中禁用和错误恢复。

RC-22：

- 状态族、响应式、无障碍、新纪录反馈。

## 13. Milestone A 结论

RC-00 至 RC-07 已形成：

- 当前实现基线。
- 距离/计时事实源审计。
- 真实库 `±3%` 影响审计。
- Registry 与比较规则。
- 置信度与状态机。
- 数据模型与事件表。
- API/ViewModel。
- 前端设计与线框。

Milestone A 可进入 Resolver 与数据闭环阶段，但不得跳过 RC-08 至 RC-16 的后端实现顺序。
