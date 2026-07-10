# ACS-Phase4-04 Career Overview Activity Detail 回跳完成报告

## 任务范围

本任务为 Career Overview 的最近赛事、最新 PB、代表成就 spotlight 条目接入 Activity Detail 回跳能力。

已完成：

- 为 spotlight 条目绑定点击回跳
- 新增键盘回车 / 空格触发
- 新增 `openCareerActivityDetailFromElement`
- 新增 `onCareerActivityDetailKeydown`
- 复用现有 Activity Detail 打开路径
- 新增 `tests/test_career_overview_activity_detail_link.py`

未实现：

- 完整 Timeline UI
- Memory Gallery
- AI Career Insight
- 新后端 API
- Activity Detail 数据契约调整
- Resolver / API 语义调整

## 复用的 Activity Detail 路径

复用现有：

```js
openActivityDetailModal(activityId)
```

该路径内部继续使用现有 Activity Detail 加载与渲染流程。本任务不新增后端 API，不自行构造 Activity Detail payload。

## 回跳 Handler 行为

新增：

```js
function openCareerActivityDetailFromElement(el)
```

行为：

- 读取 `data-activity-id`
- 读取 `data-career-source`
- 仅当 `data-career-source === "career"` 时继续
- 非法或缺失 activity id 时安全返回
- 设置 `appState.activityDetailSource = "career"`
- 调用 `openActivityDetailModal(activityId)`

## 键盘可访问性

spotlight 条目新增：

```html
role="button"
tabindex="0"
onclick="openCareerActivityDetailFromElement(this)"
onkeydown="onCareerActivityDetailKeydown(event, this)"
```

`onCareerActivityDetailKeydown` 支持：

- `Enter`
- 空格
- `Spacebar`

## 安全边界

回跳 handler 不引用或读取：

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

回跳 handler 不计算 Race / PB / Achievement 事实，只读取 DOM 上的 `activity_id` 与 `source=career`。

## 已运行测试

已通过：

```bash
python3 -m pytest tests/test_career_overview_activity_detail_link.py
# 6 passed

python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_overview_frontend_integration.py tests/test_track_html_sync_logic.py
# 38 passed

python3 -m pytest tests/test_career_overview_api_closure.py tests/test_career_api_skeleton.py
# 9 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：后端 pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase5-01：Timeline Engine 年月结构与筛选收口`

如继续前端打磨，也可进入：

`ACS-Phase4-05：Career Overview 首屏视觉细节与移动端检查`
