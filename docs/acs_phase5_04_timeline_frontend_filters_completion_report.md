# ACS-Phase5-04 Timeline 年份筛选与运动类型筛选入口完成报告

## 任务范围

本任务为 ACS Timeline 前端补充筛选入口：

- 年份筛选
- 运动类型筛选
- 当前筛选状态文案
- 里程碑节点不按运动类型过滤的提示

本任务只调整前端视图与筛选参数传递，不改后端 API、Resolver、数据库结构或语义识别规则。

未实现：

- 后端 Resolver 规则调整
- Timeline 后端分页或虚拟列表
- Memory Gallery
- AI Snapshot / AI 洞察
- Activity Detail 新接口
- 前端本地计算赛事、PB、成就或记忆节点

## 修改文件

- `track.html`
- `tests/test_career_timeline_frontend_filters.py`
- `docs/acs_phase5_04_timeline_frontend_filters_completion_report.md`

## 筛选入口

Timeline 筛选区新增两个原生 `select` 控件：

- `career-timeline-year-filter`
  - 默认项：`全部年份`
  - 变更后调用 `onCareerTimelineYearFilterChange(this)`
  - 保留当前 `type` 与 `sport`
  - 将年份参数写入 `appState.career.timelineFilters.year`

- `career-timeline-sport-filter`
  - 默认项：`全部运动`
  - 当前支持：`running`、`cycling`
  - 变更后调用 `onCareerTimelineSportFilterChange(this)`
  - 保留当前 `type` 与 `year`
  - 将运动类型参数写入 `appState.career.timelineFilters.sport`

筛选后统一调用：

```js
loadCareerTimeline(appState.career.timelineFilters)
```

前端不在 HTML 面板内直接调用 `window.pywebview.api`，API 入口仍集中在脚本函数层。

## 年份来源

年份选项来自 `get_career_timeline` 返回 view model 中的：

```js
timeline.years[].year
```

前端通过 `careerTimelineYearsFromTimeline(timeline)` 提取并倒序排序，写入：

```js
appState.career.timelineAvailableYears
```

若某次筛选返回空年份，但此前已有可用年份列表，则保留旧年份列表，避免用户筛选到空结果后无法切回其他年份。

## 运动类型行为

运动类型筛选只负责把 `sport` 参数传给 `get_career_timeline`，不在前端本地过滤 Timeline 节点。

运动类型显示文案：

- `all`：全部运动
- `running`：跑步
- `cycling`：骑行

本任务未扩展后端支持的运动类型枚举；后续如需增加游泳、徒步等类型，应先确认后端 canonical sport 字段和 Timeline API 契约。

## 里程碑提示行为

当筛选类型为 `achievement` 且运动类型不是 `all` 时，前端显示提示：

```text
里程碑节点不按运动类型过滤
```

原因：

- 里程碑属于 ACS 派生语义节点
- 其归属和展示应由后端 Resolver / Timeline view model 决定
- 前端不能根据 `node.sport` 或任何原始字段自行过滤成就节点

测试已覆盖 `renderCareerTimeline(viewModel)` 不执行本地 `.filter()`，也不读取 `node.sport`。

## Activity Detail 影响

本任务未修改 Activity Detail 回跳链路。

Timeline 节点仍沿用已有：

- `detail_link.activity_id`
- `detail_link.source = "career"`
- `openCareerActivityDetailFromElement`
- `onCareerActivityDetailKeydown`

年份与运动类型筛选只影响 Timeline 列表加载参数，不影响详情页 API、详情弹窗、轨迹渲染或活动列表编辑入口。

## 数据边界确认

新增筛选相关函数不读取、不暴露以下数据：

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

新增筛选相关函数不计算或推断：

- `sport_event`
- `race_confidence`
- 赛事真值
- PB 真值
- 成就真值
- 距离、时长、配速等原始判定指标
- Resolver 结果晋级逻辑

前端只消费 Timeline view model，不绕过后端 Resolver。

## macOS / Windows 兼容性

- 未新增硬编码路径
- 未读取本地绝对路径
- 未依赖系统分隔符
- 未依赖大小写敏感文件系统
- 未引入新构建工具或平台特定依赖
- 中文文案保持 UTF-8
- 使用原生 `select` 控件，兼容 pywebview 桌面壳
- 窄窗口下筛选控件可换行展示，避免按钮和文案挤压溢出

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_frontend_filters.py
# passed

python3 -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py
# passed

python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py
# passed

python3 -m pytest tests/test_track_html_sync_logic.py
# passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：本任务未启动 pywebview 真实桌面窗口做人工截图验收；本轮以静态契约测试和前端结构测试完成验证。

## 下一任务建议

建议进入：

`ACS-Phase5-05：Timeline 大数据量渲染与分段/分页策略`

建议边界：

- 只处理 Timeline 前端在 500+ 节点下的渲染可用性
- 优先采用按年份 / 月份分段渲染或渐进展开
- 不改 Resolver 语义规则
- 不改 Race / PB / Achievement 真值判断
- 不实现 Memory Gallery
- 不生成 AI Snapshot
- 如确需后端分页，应先单独确认 API 契约变更
