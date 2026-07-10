# ACS-Phase4-03 Career Overview 前端首屏轻量渲染完成报告

## 任务范围

本任务在已有 `get_career_overview` 前端安全调用与 view model 归一基础上，为「运动生涯」一级页增加轻量 Overview 首屏渲染。

已完成：

- 扩展 Career Overview summary 指标位
- 新增最近赛事、最新 PB、代表成就 spotlight 展示位
- 扩展 `renderCareerOverview`
- 新增 spotlight 渲染 helper
- 新增 Activity Detail 回跳 data hooks
- 新增 `tests/test_career_overview_frontend_render.py`

未实现：

- 完整 ACS 前端视觉设计
- Timeline UI
- Memory Gallery
- AI Career Insight
- Activity Detail 实际跳转动作
- 新后端 API
- Resolver 规则调整

## 渲染内容

Summary metrics：

- 生涯开始
- 活动数
- 累计距离
- 覆盖城市
- 赛事
- PB
- 成就

Spotlight：

- 最近赛事
- 最新 PB
- 代表成就

渲染数据全部来自 `normalizeCareerOverview` 后的 view model。

## 状态处理

继续保留并扩展：

- loading：显示“正在加载生涯总览”
- error：显示错误状态并保留稳定空 view model
- empty：显示空状态占位
- ready：渲染 summary 与 spotlight

只有普通 Activity、没有 Race / PB / Achievement 时，summary 可正常展示，spotlight 保持空状态。

## 安全边界

前端渲染层不引用或保留：

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

渲染层不进行以下事实推导：

- 根据距离判断 PB
- 根据标题判断赛事
- 根据分数重新排序成就
- 根据 Activity 原始字段推导城市、距离、赛事类型

动态 HTML 使用 `safeHtml`。

## 点击回跳准备

Spotlight 条目已添加：

```html
data-activity-id="..."
data-career-source="career"
```

本任务未绑定实际打开 Activity Detail 的点击行为，留给下一任务实现。

## 已运行测试

已通过：

```bash
python3 -m pytest tests/test_career_overview_frontend_render.py
# 7 passed

python3 -m pytest tests/test_career_overview_frontend_integration.py tests/test_track_html_sync_logic.py
# 31 passed

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

`ACS-Phase4-04：Career Overview Activity Detail 回跳`

建议边界：

- 使用本任务已添加的 data hooks
- 点击最近赛事、最新 PB、代表成就时打开 Activity Detail
- 不新增后端 API
- 不做完整 Timeline UI
