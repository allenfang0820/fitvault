# ACS-Phase8-04：运动生涯页面跨平台视觉回归完成报告

## 任务范围

本任务完成 Phase8 的代码层跨平台视觉回归验收，聚焦「运动生涯」页面在 macOS / Windows pywebview 环境下容易出现的布局、滚动、窄窗口、局部错误态和安全边界风险。

本任务只做：

- 核验 Career 页面 CSS / DOM / JS 的跨平台稳定性。
- 做少量 CSS 加固。
- 新增跨平台视觉契约测试。
- 更新任务清单，明确 Windows 真机验收仍留在 Phase9。
- 新增本完成报告。

未做：

- 不做 Windows 真机验证。
- 不做打包验证。
- 不做 Playwright 截图验收。
- 不改后端事实逻辑。
- 不改 Career API 返回结构。
- 不新增 pywebview API。
- 不调用 Resolver。
- 不接真实 AI，不调用 `call_llm` 或 `llm_backend`。

## 自动化可验证项

新增测试：

- `tests/test_career_phase8_cross_platform_visual_contract.py`

覆盖：

- 全局字体包含 macOS / Windows 常见 fallback：
  - `-apple-system`
  - `BlinkMacSystemFont`
  - `"Segoe UI"`
  - `Roboto`
  - `sans-serif`
- Career 主滚动容器：
  - `height: 100%`
  - `min-height: 0`
  - `overflow: auto`
  - `overflow-x: hidden`
- Career 主布局 / 列容器：
  - `career-layout` 有 `min-height: 0`
  - `career-column` 有 `min-width: 0` 与 `min-height: 0`
- 窄窗口 CSS 覆盖：
  - `.career-layout`
  - `.career-overview-grid`
  - `.career-bucket-list`
  - `.career-spotlight`
  - `.career-timeline-month`
  - `.career-memory-story-row`
  - `.career-insight-toolbar`
- Overview / Timeline / Archives / Memory / Insight loader 均有：
  - `try/catch`
  - pywebview API 不可用错误态
  - 局部 `render...Error(message)`
- 切换到 Career 面板时各模块用 `.catch(...)` 独立加载，互不阻塞。
- 交互项和长文本区域具备 `overflow-wrap: anywhere`。
- Career visual / render 相关切片不包含禁止字段：
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
  - `display_metadata`
- Career 主面板不回退为旧荣誉墙照片墙或 coming soon 主形态。

## CSS 调整

`track.html`：

- `.career-shell` 增加 `overflow-x: hidden`，避免 Windows 滚动条宽度或长文本导致横向溢出。
- `.career-column` 增加 `min-height: 0`，降低右栏内容在 flex/grid 组合下挤压滚动容器的风险。

未调整主结构，未新增视觉模块。

## macOS 代码层验收结论

当前 macOS 本地代码层回归通过：

- Career 页面具备稳定滚动容器。
- 窄窗口单列策略已有测试守护。
- Timeline 长列表仍使用月级 progressive rendering。
- Archives / Memory / Insight 右栏内容使用紧凑列表和局部空态 / 错误态。
- pywebview API 初始化慢或接口暂不可用时，各模块显示局部错误态，不阻塞整页。

## Windows 真机未验证说明

当前环境无法直接完成 Windows 真机验证，因此没有勾选 Phase9 Windows 验收项。

仍需后续在 Windows 打包 / 真机环境确认：

- 中文字体与 emoji/icon 混排。
- Windows 滚动条宽度下是否无横向溢出。
- pywebview 初始化慢或接口暂不可用时，各区块是否只显示局部错误态。
- Timeline 长列表滚动是否流畅。
- Overview / Timeline / Archives / Memory / Insight 在常见窗口尺寸下是否可读。

任务清单已新增 Phase9 Windows 真机运动生涯页面验证项。

## pywebview 局部错误态确认

已确认以下模块均有局部错误态：

- `loadCareerOverview()` -> `renderCareerOverviewError(message)`
- `loadCareerTimeline(filters)` -> `renderCareerTimelineError(message)`
- `loadCareerArchives()` -> `renderCareerArchivesError(message)`
- `loadCareerMemory(filters)` -> `renderCareerMemoryError(message)`
- `loadCareerInsight(options)` -> `renderCareerInsightError(message)`

切换到 Career 面板时，以上模块分别以 `.catch(...)` 触发，不会因为单一模块失败中断其他模块。

## 安全边界确认

- 未改后端事实逻辑。
- 未改 Career API 返回结构。
- 未新增 pywebview API。
- 未调用 Resolver。
- 未接真实 AI。
- 未调用 `call_llm` 或 `llm_backend`。
- 未展示 Career Snapshot JSON / debug JSON。
- 未新增 prompt。
- 未读取或暴露 raw FIT、points、track_json、file_path、storage_ref、本地路径或 SQLite schema。
- 未将 `display_metadata` 透传到前端列表。
- 未重做 ACS 页面主结构。
- 未新增营销式 hero。
- 未恢复旧荣誉墙照片卡片墙。
- 未把 Windows 真机未验收事项标记为完成。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_phase8_cross_platform_visual_contract.py
python3 -m pytest tests/test_career_phase8_frontend_readiness.py tests/test_career_phase8_visual_density.py
python3 -m pytest tests/test_career_archives_frontend_render.py
python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

## 下一个建议任务

建议进入：

`ACS-Phase9-01：ACS SQLite migration 与路径兼容性审计`

Phase8 前端代码层可以阶段收口；Windows 真机视觉验收继续保留在 Phase9。
