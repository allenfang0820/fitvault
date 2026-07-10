# ACS-Phase7-05 Career Insight 前端视觉验收与空状态细化完成报告

## 任务边界

本任务只细化 Phase7-04 已接入的 Career Insight 前端占位区，聚焦视觉层级、状态文案、前端契约测试和验收文档。

未改动：

- `career_backend.py`
- `main.py`
- `docs/js_api_contract.json`
- 真实 LLM 调用链路
- Career Snapshot 后端生成与持久化逻辑

## 改动文件

- `track.html`
  - 补充刷新按钮禁用态。
  - 将 highlights 与 next_steps 拆成「阶段亮点」「下一步建议」两个视觉块。
  - 弱化 disclaimer 视觉层级。
  - 细化空态、加载态、低数据态、错误态文案。
  - 补充窄屏下洞察块的宽度与字号约束。
- `tests/test_career_insight_frontend_render.py`
  - 同步 Phase7-05 新列表渲染结构的断言。
- `tests/test_career_insight_frontend_visual_contract.py`
  - 新增 Career Insight 前端视觉契约测试。
- `docs/acs_phase7_05_career_insight_frontend_visual_acceptance.md`
  - 新增手动/视觉验收清单。
- `docs/acs_phase7_05_career_insight_frontend_visual_completion_report.md`
  - 新增本完成报告。

## UI 状态细化

- 初始空态：强调「本地洞察将基于安全摘要生成」。
- 加载态：状态栏展示「正在生成本地洞察」，刷新按钮禁用。
- 低数据态：默认提示「需要更多生涯数据，本地洞察将基于安全摘要生成」。
- 错误态：错误文案限制在生涯洞察模块内，不使用弹窗。
- fallback 态：继续标记为本地降级洞察，不误导为 AI 已生成。

## 视觉调整

- 「阶段亮点」采用低对比边框块，保持与 Career 页面整体密度一致。
- 「下一步建议」使用轻微区分的边框和列表符号，便于扫读。
- disclaimer 增加顶部分隔线，字体和颜色降权。
- 窄屏下工具栏纵向排列，列表块 100% 宽度，避免内容挤压。

## 安全与契约确认

- 未调用 `call_llm`。
- 未新增 Prompt 构建。
- 未展示 Snapshot 原文。
- 未展示 Snapshot JSON 或调试 JSON。
- 前端只调用 `generate_career_insight({ refresh_snapshot })`。
- Career Insight 前端相关函数不读取、不展示、不透传手册禁止字段。

## macOS / Windows 兼容性

- 本任务为 HTML / CSS / JS 前端状态细化，不引入平台专有 API。
- pywebview 仍只依赖既有 `window.pywebview.api.generate_career_insight`。
- 不读取、不拼接、不展示本地路径。
- Windows 下接口初始化较慢时，错误态仍在模块内降级展示。

## 验证结果

- `python3 -m pytest tests/test_career_insight_frontend_visual_contract.py`
  - 6 passed
- `python3 -m pytest tests/test_career_insight_frontend_render.py`
  - 8 passed
- `python3 -m pytest tests/test_career_insight_api_skeleton.py`
  - 11 passed
  - 仅出现 macOS 系统 Python / LibreSSL 的 `urllib3` 环境提醒，不影响测试结果。
- `python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py`
  - 22 passed
- `python3 -m pytest tests/test_track_html_sync_logic.py`
  - 24 passed
- `python3 -m json.tool docs/js_api_contract.json >/dev/null`
  - passed

## 下一个建议任务

建议进入 `ACS-Phase7-06：Career Insight Phase7 闭环验收与任务清单回填`。
