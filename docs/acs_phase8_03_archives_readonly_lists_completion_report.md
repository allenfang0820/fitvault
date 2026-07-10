# ACS-Phase8-03：PB / 赛事 / 里程碑分区只读列表完成报告

## 任务范围

本任务将「运动生涯」页面中的 `archives` 生涯分区从静态结构预留升级为三组只读列表：

- 赛事档案
- PB 记录
- 荣誉里程碑

本任务只改前端页面、前端契约测试、任务清单和完成报告。

未做：

- 不改后端事实逻辑。
- 不改 Career API 返回结构。
- 不新增 pywebview API。
- 不调用 Resolver。
- 不接真实 AI。
- 不调用 `call_llm` 或 `llm_backend`。
- 不展示 Career Snapshot JSON / debug JSON。
- 不把 Windows 真机未验收事项标记为完成。

## 修改文件

- `track.html`
- `tests/test_career_archives_frontend_render.py`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/acs_phase8_03_archives_readonly_lists_completion_report.md`

## 实现方式

`track.html` 的 `data-career-section="archives"` 现在包含三个渲染目标：

- `data-career-archive-list="races"`
- `data-career-archive-list="pbs"`
- `data-career-archive-list="achievements"`

新增前端状态：

- `appState.career.archives`
- `appState.career.archivesLoading`
- `appState.career.archivesError`

新增加载函数：

- `loadCareerArchives()`

切换到「运动生涯」一级页面时，会与 Overview、Timeline、Memory、Insight 一起触发：

- `loadCareerArchives().catch(...)`

## API 调用边界

Archives 只调用既有白名单只读 API：

- `window.pywebview.api.get_career_races({})`
- `window.pywebview.api.get_career_pb({})`
- `window.pywebview.api.get_career_achievements({})`

没有新增 API，没有调用 Resolver，没有读取 SQLite 或原始 FIT。

## 白名单字段

新增白名单 normalizer：

- `normalizeCareerArchives(payload)`
- `normalizeCareerArchiveRace(item)`
- `normalizeCareerArchivePb(item)`
- `normalizeCareerArchiveAchievement(item)`

Race 只使用：

- `id`
- `activity_id`
- `name`
- `event_type`
- `sport`
- `event_date`
- `city`
- `confidence_level`
- `detail_link`

PB 只使用：

- `id`
- `activity_id`
- `sport`
- `pb_type`
- `value`
- `value_unit`
- `improvement_sec`
- `event_date`
- `detail_link`

Achievement 只使用：

- `id`
- `activity_id`
- `achievement_type`
- `title`
- `event_date`
- `score`
- `icon`
- `description`
- `detail_link`

Archives 前端列表不透传 `display_metadata`，不使用 `Object.assign` 或 `...item`。

## 加载态 / 空态 / 错误态

新增渲染函数：

- `renderCareerArchives(viewModel)`
- `renderCareerArchivesLoading()`
- `renderCareerArchivesError(message)`
- `renderCareerArchiveGroup(name, items, emptyText, renderer)`

行为：

- 加载时显示“正在加载分区”。
- 单组无数据时显示对应组空态。
- 全部无数据时显示总空态。
- 失败时显示“生涯分区暂不可用”或具体错误消息。
- 每组最多展示前 5 条，避免右栏膨胀。

## 活动详情跳转

新增列表项渲染函数：

- `careerArchiveRaceHtml(item)`
- `careerArchivePbHtml(item)`
- `careerArchiveAchievementHtml(item)`
- `careerArchiveItemShell(item, title, meta)`

有 `activity_id` 的条目复用既有活动详情跳转：

- `openCareerActivityDetailFromElement(this)`
- `onCareerActivityDetailKeydown(event, this)`
- `data-activity-id`
- `data-career-source="career"`

无 `activity_id` 的条目只渲染为普通只读项。

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
- 未将 `display_metadata` 透传到 archive list。
- 未恢复旧荣誉墙照片卡片墙。

## macOS / Windows 兼容性说明

- 本次只新增前端 HTML/CSS/JS 和文本测试，不新增平台相关文件 IO。
- 所有数据仍通过 pywebview 统一 API envelope 获取。
- 列表文本使用 `overflow-wrap: anywhere`，降低中文、英文长词、Windows 字体差异导致的溢出风险。
- 移动端继续沿用 Phase8 单列布局。
- Windows 真机字体、滚动条和 pywebview 初始化差异仍留给 `ACS-Phase8-04` 验收。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_archives_frontend_render.py
python3 -m pytest tests/test_career_phase8_frontend_readiness.py tests/test_career_phase8_visual_density.py
python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

## 下一个建议任务

建议进入：

`ACS-Phase8-04：运动生涯页面跨平台视觉回归`
