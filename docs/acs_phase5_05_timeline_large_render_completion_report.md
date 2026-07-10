# ACS-Phase5-05 Timeline 大数据量渲染与分段策略完成报告

## 任务范围

本任务完成 ACS Timeline 在大数据量场景下的前端降载策略。

已完成：

- 新增月份级分段 / 渐进渲染
- 新增每月“展开更多”入口
- 新增展开状态管理
- 筛选重新加载时重置展开状态
- 补充大数据量渲染静态契约测试
- 回归 Phase5 Timeline、Phase4 Overview 与同步逻辑测试

未实现：

- 后端分页 API
- 虚拟滚动库
- Resolver 规则调整
- Race / PB / Achievement 真值判断调整
- Memory Gallery
- AI Snapshot / AI 洞察

## 修改文件

- `track.html`
- `tests/test_career_timeline_frontend_large_render.py`
- `docs/acs_phase5_05_timeline_large_render_completion_report.md`

## 采用策略

本任务采用“按月份分段渲染 + 渐进展开”，暂不引入虚拟列表。

选择原因：

- 当前 `get_career_timeline` 已天然返回 `years[].months[].nodes[]`
- 月份是用户理解运动生涯时间轴的天然分段
- 不需要修改 API 契约
- 不引入新前端依赖
- pywebview 下原生 DOM 与按钮交互更稳定
- 能直接覆盖 500+ Timeline 节点初始渲染压力

后续如果真实用户数据达到更高节点规模，再考虑后端分页或真正虚拟列表。

## 初始展示阈值

新增常量：

```js
const CAREER_TIMELINE_MONTH_INITIAL_LIMIT = 8;
```

每个月初始最多渲染 8 个节点。

超过 8 个节点时，剩余节点不会一次性进入 DOM，而是显示：

```text
展开更多 N 个节点
```

这可以避免某个赛事密集月份一次性撑开过长 DOM。

## 展开更多行为

新增月份 key：

```js
careerTimelineMonthKey(yearValue, monthValue)
```

展开状态保存到：

```js
appState.career.timelineExpandedMonths
```

用户点击某个月份的“展开更多”后：

- 只标记该月份 key
- 只重新渲染当前 Timeline view model
- 不重新请求后端
- 不影响其他年份 / 月份
- 不破坏节点的 Activity Detail 回跳结构

展开按钮使用原生 `button`，并补充稳定尺寸、focus 态与 `overflow-wrap`，避免窄窗口文案撑开布局。

## 筛选切换后的状态处理

每次 `loadCareerTimeline(filters)` 成功拿到新的 Timeline view model 后调用：

```js
resetCareerTimelineExpansion()
```

因此：

- 切换类型筛选会重置展开状态
- 切换年份筛选会重置展开状态
- 切换运动类型筛选会重置展开状态
- 旧月份的展开状态不会污染新筛选结果

年份筛选、运动类型筛选和类型筛选仍沿用 Phase5-04 的参数传递方式。

## Activity Detail 影响

本任务未修改 Timeline 节点详情回跳结构。

节点仍由 `careerTimelineNodeHtml(node)` 统一生成，并保留：

- `role="button"`
- `tabindex="0"`
- `data-activity-id`
- `data-career-source`
- `onclick="openCareerActivityDetailFromElement(this)"`
- `onkeydown="onCareerActivityDetailKeydown(event, this)"`

“展开更多”按钮不调用 Activity Detail，也不触发后端 API。

## 数据边界确认

新增大数据量渲染相关函数不读取、不暴露：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`
- `sqlite_schema`
- `schema`

新增逻辑不计算或推断：

- `sport_event`
- `race_confidence`
- 赛事真值
- PB 真值
- 成就真值
- 距离、时长、配速等原始判定指标
- Resolver 结果晋级逻辑

前端仍只消费 Timeline view model。

## macOS / Windows 兼容性

- 未新增硬编码路径
- 未读取本地绝对路径
- 未依赖路径分隔符
- 未依赖大小写敏感文件系统
- 未引入新构建链路或浏览器库
- 中文按钮文案保持 UTF-8
- 使用原生 `button` 与既有 pywebview DOM 交互
- 展开按钮宽度固定为容器宽度，长文案可换行
- 窄窗口仍沿用 Phase5-03 的月份单列布局

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_frontend_large_render.py
# 7 passed

python3 -m pytest tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py
# 24 passed

python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py
# 20 passed

python3 -m pytest tests/test_track_html_sync_logic.py
# 24 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：本任务未启动 pywebview 真实窗口做 500+ 节点截图压测；本轮以静态契约测试和回归测试验证渲染策略不破坏既有功能。

## 下一任务建议

Phase 5 Timeline Engine 的前端与性能收口已完成，建议进入：

`ACS-Phase6-01：Memory Gallery 轻量版数据契约与空状态策略`

建议边界：

- 先设计 Memory Gallery 轻量版结构
- 每个 MemoryItem 必须绑定 `activity_id` 或 `race_id`
- 图片缺失时允许展示故事文本 / 轨迹截图占位策略，但不能空成一堆无意义占位图
- macOS / Windows 路径必须走应用受控目录
- 不暴露本地绝对路径给前端、AI 或 Snapshot
- 不生成 AI Snapshot
