# ACS-Phase5-02 Timeline 前端轻量渲染与筛选入口完成报告

## 任务范围

本任务在现有「运动生涯」一级页面中接入 `get_career_timeline` API，完成 Timeline 前端轻量渲染与筛选入口。

已完成：

- 扩展 `appState.career.timeline*` 状态
- 新增 Timeline API 调用与响应归一
- 新增 Timeline 年 / 月 / 节点轻量渲染
- 新增全部 / 赛事 / PB / 里程碑筛选入口
- 新增 Timeline loading / error / empty 状态
- 新增候选事件计数提示
- Timeline 节点复用 Activity Detail 回跳 handler
- 新增前端静态测试 `tests/test_career_timeline_frontend_render.py`

未实现：

- Memory Gallery
- Memory Timeline 节点
- Timeline 虚拟列表
- Timeline 年份 / 运动类型筛选 UI
- AI Snapshot / AI 洞察
- 后端 Resolver 规则调整

## 修改文件

- `track.html`
- `tests/test_career_timeline_frontend_render.py`
- `docs/acs_phase5_02_timeline_frontend_light_render_completion_report.md`

## API 消费方式

前端新增：

```js
async function loadCareerTimeline(filters)
```

只调用：

```js
window.pywebview.api.get_career_timeline(appState.career.timelineFilters)
```

并遵守统一响应结构：

```js
{ ok, code, msg, data, traceId }
```

前端只消费后端返回的 `years[].months[].nodes[]`、`filters`、`candidates_count` 与 `status`。

## 筛选行为

页面内新增紧凑筛选入口：

- 全部：`type=all`
- 赛事：`type=race`
- PB：`type=pb`
- 里程碑：`type=achievement`

切换筛选时：

- 更新 `appState.career.timelineFilters.type`
- 保留当前 `sport` 与 `year`
- 重新调用 `loadCareerTimeline`
- 更新按钮 active / `aria-pressed`

## Activity Detail 回跳

Timeline 节点渲染时写入：

```html
data-activity-id="..."
data-career-source="career"
```

并复用 Phase4 已完成的：

```js
openCareerActivityDetailFromElement(this)
onCareerActivityDetailKeydown(event, this)
```

支持：

- 鼠标点击
- Enter
- Space / Spacebar

不新增独立详情弹窗，不新增后端 API。

## 空状态 / 错误状态

已支持：

- loading：显示“正在加载时间轴”
- error：显示错误信息或“时间轴暂不可用”
- empty：显示后端状态消息或“暂无时间轴节点”
- `candidates_count > 0`：显示“候选事件待确认”提示

候选事件只显示计数提示，不渲染为正式 Timeline 节点。

## 数据边界

前端不计算或推断：

- 是否赛事
- 是否 PB
- 是否成就
- PB 成绩
- 成就分数
- 赛事置信度

前端不读取或暴露：

- raw FIT
- points / points_json
- track_json
- file_path
- SQLite schema
- 本地绝对路径
- AI snapshot

Timeline normalizer 使用白名单字段，不做 `Object.assign` 或原对象透传。

## macOS / Windows 兼容性

- 未新增平台路径处理
- 未读取本地绝对路径
- 仍通过 pywebview API envelope 消费数据
- 移动端 / 窄窗口下 Timeline 月份结构改为单列
- 中文标题、标签、状态文案在 HTML / JS 中保持 UTF-8
- 不引入新框架或构建链路

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_frontend_render.py
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

## 下一任务建议

建议进入：

`ACS-Phase5-03：Timeline 前端数据联调与视觉细节验收`

建议边界：

- 用后端真实 / 测试数据检查 Timeline 在桌面端实际渲染效果
- 验证节点点击是否正确打开 Activity Detail
- 检查窄窗口布局、长标题换行、候选提示展示
- 不新增后端 Resolver 规则
- 不实现 Memory Gallery
- 不生成 AI Snapshot
