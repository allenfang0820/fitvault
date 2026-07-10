# ACS-Phase8-02：运动生涯页面视觉密度与滚动体验验收完成报告

## 任务范围

本任务对「运动生涯」页面做视觉密度与滚动体验的工程验收，并补充测试护栏。

本任务只做：

- 核验 `track.html` 中 Career 页面 CSS、DOM 与 Timeline 渲染策略。
- 做少量 Header 文案与 CSS 密度微调。
- 新增 focused 视觉密度测试。
- 记录验收结论与后续任务。

未做：

- 不重做 ACS 页面主结构。
- 不新增后端能力。
- 不修改 Career API 返回结构。
- 不新增 pywebview API。
- 不接真实 AI，不调用 `call_llm` 或 `llm_backend`。
- 不展示 Career Snapshot JSON / debug JSON。
- 不恢复旧荣誉墙照片卡片墙。
- 不把 Windows 真机未验收事项标记为完成。

## 已核验布局点

- `career-header`
- `career-title-block`
- `career-subtitle`
- `career-layout`
- `career-column`
- `career-section`
- `career-overview-grid`
- `career-spotlight`
- `career-timeline-shell`
- `career-timeline-years`
- `career-timeline-month`
- `career-timeline-node`
- `career-timeline-expand-btn`
- `career-memory-*`
- `career-insight-*`
- `@media (max-width: 980px)` 下的移动端 / 窄窗口布局

## 做出的调整

`track.html`：

- 压缩 Career Header 高度：
  - `.career-header` padding 从 `14px 16px` 调整为 `12px 14px`。
  - `.career-subtitle` margin、字号、行高和最大宽度收紧。
- 更新过期副标题：
  - 从“当前仅建立页面入口和结构壳”改为当前阶段真实口径：
  - “总览、时间轴、赛事、PB、里程碑与记忆统一沉淀，所有事实均可回跳到原始活动。”

新增测试：

- `tests/test_career_phase8_visual_density.py`

测试覆盖：

- Header 文案足够短，不再使用“结构壳”或 coming soon 口径。
- Header / Subtitle CSS 保持紧凑。
- Section、Overview 指标、Timeline 节点、Memory item、Insight card 使用紧凑尺寸。
- Timeline 每月初始最多展示 8 个节点，并通过“展开更多”按月扩展。
- Career 主面板不包含旧荣誉墙照片墙、coming soon、hero 主形态。
- 移动端 CSS 保持单列、换行和长文本防溢出约束。

## 视觉密度与滚动体验结论

当前 Career 页面满足 Phase8-02 的基础验收：

- 主页面是工具型信息界面，不是营销式 hero。
- Header 不再占用过多首屏高度。
- Overview、Timeline、Memory、Insight 均为紧凑卡片 / 列表 / 节点表达。
- Timeline 长列表使用月级 progressive rendering：
  - `CAREER_TIMELINE_MONTH_INITIAL_LIMIT = 8`
  - 初始渲染 `nodes.slice(0, CAREER_TIMELINE_MONTH_INITIAL_LIMIT)`
  - 超出部分通过 `career-timeline-expand-btn` 展开
  - 展开状态按 `year-month` key 记录，不重新请求后端
- Timeline 节点、Memory 标题、Insight 状态等长文本使用 `overflow-wrap: anywhere`。
- 窄窗口下 Career 两列、总览网格、分区列表、Spotlight、Timeline 月份布局切换为单列。

## 仍未完成

- 未做 Windows 真机 pywebview 视觉验收。
- 未做 Playwright 截图级像素验收。
- 未把 PB / 赛事 / 里程碑分区升级为完整只读列表。
- 未接真实 AI Career Insight。

## macOS / Windows 兼容性说明

- 本次只调整 HTML/CSS 静态页面与测试，不新增平台相关文件 IO、路径拼接或系统 API。
- 页面继续通过 pywebview 白名单 API 拉取数据，不读取本地路径。
- 文案与 CSS 均为 UTF-8，中文在 macOS 本地测试环境可解析。
- Windows 字体、滚动条宽度、窗口尺寸和 pywebview 初始化差异仍需 Phase8-04 真机验收。

## 安全边界确认

- 未改后端事实逻辑。
- 未改 Career API 返回结构。
- 未新增 pywebview API。
- 未接真实 AI。
- 未调用 `call_llm` 或 `llm_backend`。
- 未展示 Career Snapshot JSON / debug JSON。
- 未新增 prompt。
- 未读取或暴露 raw FIT、points、track_json、file_path、storage_ref、本地路径或 SQLite schema。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_phase8_visual_density.py
python3 -m pytest tests/test_career_phase8_frontend_readiness.py
python3 -m pytest tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py
python3 -m pytest tests/test_career_insight_frontend_visual_contract.py tests/test_career_memory_frontend_render.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

## 下一个建议任务

建议进入：

`ACS-Phase8-03：PB / 赛事 / 里程碑分区从结构预留升级为只读列表`
