# RCV2-35 视觉验收证据：页面状态、响应式与无障碍

更新时间：2026-07-15

## 截图结果

本轮尝试使用 Codex in-app browser 打开本地页面：

```text
file:///Users/fanglei/应用开发/AI track/track.html
```

浏览器安全策略阻止访问本地 `file://` 页面，提示该 URL 被 Browser use URL policy 拦截。按照工具安全规则，本轮未通过本地 HTTP 服务、CDP 或其他绕过方式继续访问同一页面。

因此 RCV2-35 的截图验收记录为：截图工具受限，未生成桌面/窄屏截图；采用代码级静态验收和自动化测试作为可复验替代证据。

## 替代验收证据

### 状态覆盖

`track.html` 已新增 `career-record-status-strip`，并通过 `renderCareerRecordStatusStrip()` 覆盖：

- Loading
- Empty
- Partial
- Candidate
- Rebuilding
- Error
- Validation Required

### 响应式覆盖

Records Center V2 已新增断点：

- `@media (max-width: 1100px)`
- `@media (max-width: 980px)`
- `@media (max-width: 720px)`
- `@media (max-width: 520px)`

窄屏下：

- records layout 转单列；
- group selector 转横向选择器；
- analysis grid 转单列；
- detail facts 从 4 列降为 2 列/1 列；
- action buttons 在超窄屏转满宽；
- 使用 `overflow-wrap:anywhere` 处理长中文、长成绩和多 Scope。

### 无障碍覆盖

- `career-record-status-strip` 使用 `aria-live="polite"`。
- sport/view tabs 使用 `aria-pressed`。
- group cards 使用 `role="button"`、`tabindex="0"`、`aria-pressed`，支持 Enter/Space。
- current/candidate/detail Activity 操作按钮带 `aria-label`。
- 候选提交期间按钮 `disabled` 且带 `aria-busy="true"`。
- 图表已有可访问列表替代视图：历史节点、曲线锚点、路线对比。
- `prefers-reduced-motion: reduce` 下关闭 Records V2 交互过渡。

## 自动化验收命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_responsive_a11y_frontend.py tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
# 21 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py -q
# 6 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 待后续人工/真机复验

打包前或 pywebview 真机验收阶段，应在真实桌面应用中补充：

- 1440 桌面截图；
- 720 或 520 窄屏截图；
- 候选列表大量数据截图；
- validation-required / error / rebuilding 状态截图。

本项不阻塞 RCV2-35 代码级完成，但应作为 RCV2-42 / RCV2-43 平台验收输入。
