# ACS-Phase4-02 Career Overview 前端首屏数据接入准备完成报告

## 任务范围

本任务为「运动生涯」前端首屏接入 `get_career_overview` 做准备，完成安全调用点、数据适配、状态处理和静态回归测试。

已完成：

- 新增 Career Overview 前端调用函数 `loadCareerOverview`
- 新增 `normalizeCareerOverview` 及相关白名单适配函数
- 新增最小 DOM 渲染目标和 loading / error / empty 状态处理
- 切换到「运动生涯」一级 tab 时触发 Overview 加载
- 新增 `tests/test_career_overview_frontend_integration.py`

未实现：

- 完整 Career Overview 视觉 UI
- 复杂 Timeline UI
- Memory Gallery
- AI Career Insight
- 新后端 API
- Race / PB / Achievement Resolver 规则调整

## 前端调用点

新增：

```js
async function loadCareerOverview()
```

调用：

```js
window.pywebview.api.get_career_overview()
```

调用逻辑：

- 兼容统一 envelope `{ok, code, msg, data, traceId}`
- API 不存在或返回失败时进入稳定 error 状态
- 不抛出未捕获异常
- 成功后写入 `appState.career.overview`

## 数据适配规则

新增：

- `normalizeCareerOverview`
- `normalizeCareerRace`
- `normalizeCareerPbRecord`
- `normalizeCareerAchievement`
- `normalizeCareerDetailLink`

适配输出：

- `summary`
- `latestRace`
- `latestPb`
- `representativePbRecords`
- `representativeAchievements`
- `status`

适配策略：

- 只复制白名单字段
- 不整包保留后端对象
- 缺失字段给稳定默认值
- 不在前端计算赛事、PB、成就事实

## 状态处理

新增 `appState.career`：

```js
{
  overview: null,
  overviewLoading: false,
  overviewError: ""
}
```

状态覆盖：

- loading：显示“正在加载生涯总览”
- error：显示错误文案并保留稳定空 view model
- empty：显示基础空状态提示
- ready：填充首屏基础 summary 数值

## 安全边界

前端 Career Overview 接入不引用或保留：

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

前端只消费后端 `get_career_overview` 返回的安全字段，不读取 Activity 原始事实，不推导 PB / Race / Achievement。

## 已运行测试

已通过：

```bash
python3 -m pytest tests/test_career_overview_frontend_integration.py
# 7 passed

python3 -m pytest tests/test_career_overview_api_closure.py tests/test_career_api_skeleton.py
# 9 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed

python3 -m pytest tests/test_track_html_sync_logic.py
# 24 passed
```

说明：后端 pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase4-03：Career Overview 前端首屏轻量渲染`

建议边界：

- 在现有调用和 view model 基础上做轻量首屏 UI
- 展示 Activity summary、最近赛事、最新 PB、代表成就
- 不做完整 Timeline
- 不接入 AI Snapshot
