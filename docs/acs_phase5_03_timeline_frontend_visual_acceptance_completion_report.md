# ACS-Phase5-03 Timeline 前端数据联调与视觉细节验收完成报告

## 任务范围

本任务对 ACS Timeline 前端接入做工程级静态联调与视觉契约验收。

已完成：

- 审计 `track.html` 中 Career Timeline 加载、筛选、归一、渲染链路
- 验证 Timeline 节点复用 Activity Detail 回跳 handler
- 补充 Timeline 视觉契约测试
- 小修 Timeline 节点正文列 `min-width: 0`
- 回归 Phase5-02 与 Phase4 前端测试

未实现：

- 后端 Resolver 规则调整
- Timeline 后端排序调整
- Memory Gallery
- AI Snapshot / AI 洞察
- pywebview 真实窗口注入联调

## 修改文件

- `track.html`
- `tests/test_career_timeline_frontend_visual_contract.py`
- `docs/acs_phase5_03_timeline_frontend_visual_acceptance_completion_report.md`

## 联调检查结果

已确认：

- 切换到「运动生涯」时调用：
  - `loadCareerOverview()`
  - `loadCareerTimeline()`
- Timeline 筛选按钮调用：
  - `setCareerTimelineTypeFilter(type)`
- API 调用只走：
  - `window.pywebview.api.get_career_timeline(filters)`
- 响应只通过：
  - `normalizeCareerTimeline`
  - `renderCareerTimeline`

Career 面板 HTML 中不直接写 API 调用，API 逻辑保留在脚本函数层。

## 视觉细节验收

新增 `tests/test_career_timeline_frontend_visual_contract.py` 覆盖：

- 年份、月份、节点容器 class 稳定存在
- 节点使用文本标签「赛事 / PB / 里程碑」，不只依赖颜色
- 长标题、长 meta、长成就描述使用 `overflow-wrap: anywhere`
- Timeline 节点正文列设置 `min-width: 0`
- 桌面端月份列为 `52px + 内容列`
- 窄窗口下月份结构单列显示
- 筛选按钮有 active 态与 `aria-pressed`
- loading / empty / error / candidate 文案存在
- candidate 提示不会调用节点渲染函数

本轮唯一小修：

```css
.career-timeline-node-body {
    min-width: 0;
}
```

用于避免长文本在 grid 内容列中撑开节点。

## Activity Detail 回跳验收

Timeline 节点继续复用：

```js
openCareerActivityDetailFromElement(this)
onCareerActivityDetailKeydown(event, this)
```

测试确认节点包含：

- `role="button"`
- `tabindex="0"`
- `data-activity-id`
- `data-career-source="career"`
- click handler
- Enter / Space 键盘 handler

本任务未新增独立详情弹窗，未新增 Activity Detail API。

## 数据边界确认

Timeline 前端函数不引用或暴露：

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

前端不计算或推断：

- 是否赛事
- 是否 PB
- 是否成就
- PB 成绩
- 成就分数
- 赛事置信度
- 候选事件晋级逻辑

## macOS / Windows 兼容性

- 未新增硬编码路径
- 未读取本地绝对路径
- 未依赖大小写敏感文件系统
- 未引入新构建链路
- 窄窗口 CSS 已覆盖 Timeline 月份单列布局
- 长中文、长英文、长数字串通过 `overflow-wrap` 与 `min-width: 0` 约束
- 中文标签与提示保持 UTF-8

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_frontend_render.py
# 8 passed

python3 -m pytest tests/test_career_timeline_frontend_visual_contract.py
# 8 passed

python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py
# 20 passed

python3 -m pytest tests/test_track_html_sync_logic.py
# 24 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：本任务未启动 pywebview 真实窗口或注入 mock 数据做浏览器截图验收；本轮以代码审计与静态测试完成联调验收。

## 下一任务建议

建议进入：

`ACS-Phase5-04：Timeline 年份筛选与运动类型筛选入口`

建议边界：

- 继续只消费 `get_career_timeline`
- 增加年份筛选入口
- 增加运动类型筛选入口
- 保持 achievement 不按 sport 过滤的后端契约提示
- 不新增后端 Resolver 规则
- 不实现 Memory Gallery
- 不生成 AI Snapshot
