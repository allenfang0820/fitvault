# ACS-Phase7-05 Career Insight 前端视觉验收清单

## 验收范围

本清单只覆盖「运动生涯 / 生涯洞察」前端占位区的视觉状态、文案边界和跨平台 pywebview 表现。

不覆盖：

- 真实 LLM 调用。
- 后端 Career Snapshot 生成逻辑。
- API 契约字段新增或变更。
- 运动生涯其他模块重排。

## 桌面端检查

- 进入「运动生涯」一级标签后，生涯洞察区位于现有 Career 页面结构内，不形成新的首页、英雄区或大面积营销式布局。
- 标题为「生涯洞察」，状态文案在右侧小号展示。
- 默认空态显示「本地洞察将基于安全摘要生成」，并明确当前不会调用 AI、不会展示快照原文。
- 刷新按钮文案为「刷新本地洞察」，点击时按钮进入禁用态，不出现重复触发的视觉错觉。
- 有洞察内容时，卡片展示标题、摘要、阶段亮点、下一步建议和弱化免责声明。
- 「阶段亮点」和「下一步建议」有清晰但克制的视觉分隔，不依赖弹窗或大面积装饰。
- 免责声明比主体内容更弱，不能抢占正文层级。

## 窄屏检查

- 工具栏在窄屏下改为单列，状态与按钮不互相挤压。
- 洞察列表块保持 100% 宽度，长句可换行，不撑开页面。
- 卡片、空态、错误态都保持在 Career section 内，不覆盖其他模块。

## 状态检查

- 初始空态：展示本地洞察说明，不展示 JSON、调试数据或 Snapshot 原文。
- 加载态：状态文案为「正在生成本地洞察」，刷新按钮禁用。
- 低数据态：可展示「需要更多生涯数据，本地洞察将基于安全摘要生成」。
- 错误态：错误只展示在生涯洞察模块内，不弹窗，不影响 Overview、Timeline、Memory 模块。
- fallback 态：只能描述为本地降级洞察，不得暗示 AI 已经完成深度总结。

## 禁止项检查

前端界面不得展示或读取以下字段：

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
- `storage_ref`
- `path`
- `thumbnail_url`
- `detail_link`

不得出现：

- `Snapshot JSON`
- `调试 JSON`
- `<pre>` 快照原文渲染
- `JSON.stringify` 调试输出
- `AI 深度总结已生成`
- `生成 AI 洞察`

## macOS / Windows 兼容性

- 前端只调用 `window.pywebview.api.generate_career_insight({ refresh_snapshot })`，不依赖平台路径分隔符。
- 按钮禁用态、空态、错误态只使用标准 DOM / CSS，不依赖 macOS 专有能力。
- 错误态应兼容 Windows pywebview 初始化较慢或接口暂不可用的情况。
- 不读取本地文件路径、不展示文件路径、不拼接平台相关路径。

## 自动化验证

建议回归命令：

```bash
python3 -m pytest tests/test_career_insight_frontend_visual_contract.py
python3 -m pytest tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_career_insight_api_skeleton.py
python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```
