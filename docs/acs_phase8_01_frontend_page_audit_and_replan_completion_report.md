# ACS-Phase8-01：运动生涯前端页面阶段验收与任务清单重排完成报告

## 任务范围

本任务对 ACS Phase8「前端页面」做阶段验收与任务重排。

本任务只做：

- 核验 `track.html` 中运动生涯页面当前形态。
- 核验现有前端测试对 Phase8 基础要求的覆盖。
- 补充一个小型 readiness 测试，防止 ACS 主页面回退成旧荣誉墙 / coming soon 形态。
- 回填 `docs/脉图运动生涯系统（ACS）开发任务清单.md` 的 Phase8 状态。
- 新增本完成报告。

未做：

- 不重做 ACS 页面 UI。
- 不新增大型前端模块。
- 不修改 Career API 行为。
- 不修改 Race/PB/Achievement/Memory/Insight 后端逻辑。
- 不接真实 LLM，不调用 `call_llm`，不新增 prompt。
- 不展示 Career Snapshot JSON / debug JSON。
- 不把 Windows 真机未验证事项标记为完成。

## 已核验文件

- `track.html`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/acs_phase7_06_career_insight_phase7_closure_completion_report.md`
- `docs/acs_pre_phase8_fix01_metadata_and_region_contract_completion_report.md`
- `tests/test_track_html_sync_logic.py`
- `tests/test_career_overview_frontend_integration.py`
- `tests/test_career_overview_frontend_render.py`
- `tests/test_career_timeline_frontend_render.py`
- `tests/test_career_timeline_frontend_filters.py`
- `tests/test_career_timeline_frontend_large_render.py`
- `tests/test_career_timeline_frontend_visual_contract.py`
- `tests/test_career_memory_frontend_render.py`
- `tests/test_career_memory_media_frontend.py`
- `tests/test_career_insight_frontend_render.py`
- `tests/test_career_insight_frontend_visual_contract.py`

## Phase8 原始要求

- 新增一级导航「运动生涯」。
- 页面结构包含生涯总览、时间轴、筛选、PB / 赛事 / 里程碑分区。
- 不再使用“照片卡片墙 + coming soon 遮罩”作为主形态。
- 卡片紧凑、可扫描，不做营销式大 hero。
- 移动端单列布局。
- Windows 下注意字体、滚动条、窗口尺寸和 pywebview 渲染差异。

## 当前实现证据

`track.html` 当前已经具备：

- 一级导航：`bookmark-tab[data-panel="career"]`，文案为「运动生涯」。
- 主面板：`panel-career`。
- 总览区：`data-career-section="overview"`，包含生涯开始、活动数、累计距离、覆盖城市、赛事档案、PB、成就等指标。
- 时间轴区：`data-career-section="timeline"`，包含全部 / 赛事 / PB / 里程碑、年份、运动类型筛选。
- 分区区：`data-career-section="archives"`，包含赛事档案、PB 记录、荣誉里程碑。
- 洞察区：`data-career-section="insight"`，当前为本地 fallback 洞察。
- 记忆区：`data-career-section="memory"`，包含轻量记忆列表和故事编辑入口。
- 旧荣誉墙：已降级为 `data-legacy-honor-entry="career-link"` 的跳转入口，不再作为 ACS 主页面。
- 移动端：`@media (max-width: 980px)` 下 Career 布局、总览网格、Bucket、Timeline 月份、Memory 表单与 Insight 工具栏切到单列或紧凑布局。

## 已完成项

- 一级导航「运动生涯」已完成。
- Phase8 基础页面结构已完成。
- ACS 主形态已从旧照片卡片墙 / coming soon 遮罩迁移到 Career 页面。
- 页面卡片形态以指标、列表、节点和紧凑区块为主，不是营销式 hero。
- 移动端单列布局已有 CSS 与测试守护。

## 未完成项

- Windows 真机字体、滚动条、窗口尺寸和 pywebview 渲染差异尚未完成验收。
- PB / 赛事 / 里程碑分区目前仍是轻量结构预留，尚未升级为完整只读列表。
- 真实 AI Career Insight 尚未开始，仍保持 Phase7 本地 fallback 边界。
- 更高阶视觉验收，如长时间轴滚动、窄窗口密度、右侧列高度平衡，仍建议单独任务处理。

## 新增测试

新增：

- `tests/test_career_phase8_frontend_readiness.py`

覆盖：

- 一级导航与主面板存在。
- Overview / Timeline / Archives / Insight / Memory 核心区块存在。
- Timeline 筛选存在。
- ACS 主面板不包含 `coming-soon-overlay`、`honor-card`、`honor-photo`、`赛事照片占位` 或 `代码疯狂产生中`。
- 移动端 CSS 包含 Career 单列布局约束。

## 后续 Phase8 建议任务

- `ACS-Phase8-02：运动生涯页面视觉密度与滚动体验验收`
  - 聚焦桌面窗口高度、长时间轴滚动、右侧列高度、紧凑扫描体验。
  - 不改后端事实逻辑，不接真实 AI。

- `ACS-Phase8-03：PB / 赛事 / 里程碑分区从结构预留升级为只读列表`
  - 仅消费 `get_career_races`、`get_career_pb`、`get_career_achievements` 白名单 API。
  - 不在前端计算赛事、PB 或成就事实。

- `ACS-Phase8-04：运动生涯页面跨平台视觉回归`
  - macOS / Windows 分别核验中文字体、滚动条、窗口尺寸、pywebview 初始化慢或 API 暂不可用时的错误态。
  - Windows 真机未完成前不得勾选 Phase9 Windows 验收项。

## macOS / Windows 兼容性注意事项

- 当前改动只新增文本测试和文档，不新增平台相关运行时代码。
- 现有前端使用 pywebview 统一 API envelope，不在 Phase8 页面中读取本地路径。
- 移动端 / 窄窗口布局已由 CSS 与测试守护。
- Windows 真机的字体、滚动条、窗口尺寸、中文渲染和 pywebview 差异仍需后续任务实测。

## 安全边界确认

- 未接入真实 LLM。
- 未调用 `call_llm` 或 `llm_backend`。
- 未展示 Career Snapshot 原文、Snapshot JSON 或 debug JSON。
- 未新增后端事实写入。
- 未暴露 raw FIT、points、track_json、file_path、storage_ref、本地路径或 SQLite schema。
- Phase8 前端只通过既有白名单 API 和本地 fallback view-model 展示。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_phase8_frontend_readiness.py
python3 -m pytest tests/test_career_overview_frontend_integration.py
python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_visual_contract.py
python3 -m pytest tests/test_career_insight_frontend_visual_contract.py tests/test_track_html_sync_logic.py
python3 -m pytest tests/test_career_memory_media_frontend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

说明：macOS Python 环境如出现既有 `urllib3/LibreSSL` warning，不影响本任务判断。

## 阶段结论

Phase8 的“基础前端页面”可以判定为已完成，但完成口径是：

> 运动生涯一级入口、主页面结构、总览、时间轴、筛选、分区预留、记忆与本地洞察的轻量页面闭环已完成。

仍不能判定完成的是：

> Windows 真机视觉验收、完整 PB / 赛事 / 里程碑只读列表、真实 AI Career Insight。

## 下一个建议任务

建议进入：

`ACS-Phase8-02：运动生涯页面视觉密度与滚动体验验收`
