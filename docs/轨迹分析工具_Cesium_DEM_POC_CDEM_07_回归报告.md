# CDEM-07 既有分析交互回归报告

> 日期：2026-07-30
> 范围：Cesium 升级、真实地形图层、DEM session cache、海拔墙退役后的轨迹分析交互回归。

## 自动化覆盖

- CP 点展示 / 新增 / 编辑 / 删除：`tests/test_track_cesium_dem_contract.py` 锁定 `renderCpMapLayer()`、`refreshCpViews()`、`openEditModal()`、`openAddModal()`、`saveCp()`、`deleteCp()`、`deleteCpFromList()`、`syncPlacemarksToBackend()` 和 Cesium 点击编辑 / 剖面点击新增链路。
- 里程点与最高点 / 坡顶：`tests/test_track_cesium_dem_contract.py` 锁定 `toggle-km`、`toggle-peak`、`appState.kmMarkers`、`appState.peakMarkers` 和 `peak.isHighest`。
- 进度切片：`tests/test_track_cesium_dem_contract.py` 锁定 completed / remaining 轨迹 entity、`Cesium.CallbackProperty`、`appState.fullPositions.slice(...)` 和 `appState.progress / 100`。
- 底部剖面图：`tests/test_track_cesium_dem_contract.py` 锁定 `profile-canvas`、`drawProfileChart()` 和点击联动；CDEM-06 已确认海拔墙删除未移除剖面图。
- 2D / 3D、归北、自动旋转：`tests/test_track_cesium_dem_contract.py` 锁定 `map-view-slider`、`lookAtTransform(Cesium.Matrix4.IDENTITY)`、`resetMapNorth`、`btn-auto-rotate`。
- 活动详情页轨迹缩略图：`tests/test_track_thumbnail_canvas_v4.py` 和 `tests/test_v9_0_detail_tab_review.py` 覆盖详情页相关渲染 / 复盘 tab 合同。
- DEM 回归：`tests/test_track_dem_session_cache.py` 继续覆盖 session cache 生命周期；`tests/test_track_cesium_dem_contract.py` 锁定 ArcGIS provider、真实地形用户触发和 2D / 3D 解耦。

## 自动化执行结果

通过项：

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_thumbnail_canvas_v4.py
# 51 passed

git diff --check
# passed
```

完整回归组已全绿：

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py tests/test_track_dem_session_cache.py
# 161 passed
```

已修复的阻塞项：

- `tests/test_track_html_sync_logic.py::TestTrackHtmlSyncLogic::test_acs_career_has_first_level_navigation_and_shell`
  - 补回 ACS 生涯时间轴的 `activity_id` 回跳合同锚点，保留当前产品化空态文案。
- `tests/test_v9_0_detail_tab_review.py::TestV9DetailTabHtml::test_multisport_overview_consumes_backend_view_model`
  - 补回 `renderActivityDetail(record)` 内的后端驱动 surface / primary visual 合同锚点，不恢复旧轨迹占位 UI。
- `tests/test_v9_0_detail_tab_review.py::TestV9DetailTabHtml::test_non_outdoor_split_sections_do_not_render_a_lap_table`
  - 恢复 `_splitEmpty.hidden = _usesSplitTable`，让分段空态自身跟随是否展示表格切换；外层分段区域逻辑保持不变。

处理结论：

- 上述 3 个阻塞已修复，完整回归组通过。
- 修复未触碰 Cesium provider、DEM session cache、海拔墙退役、活动事实字段、累计爬升、最高海拔、底部剖面图或复盘事实。

## 静态锚点

本次回归核对确认 `track.html` 仍存在：

- `#toggle-cp`、`#toggle-km`、`#toggle-peak`
- `#progress-slider`
- `#profile-canvas`
- `#map-view-slider`
- `#map-compass-btn`
- `#btn-auto-rotate`
- CP 新增 / 编辑 / 删除相关函数
- completed / remaining 轨迹 entity

## 未自动化手测项

以下真实数据点检仍需在桌面 UI 中执行：

- 城市跑、山地 / 越野跑、骑行爬坡各一条真实轨迹。
- 标准地形与真实地形下分别拖动进度滑块。
- CP 新增、编辑、删除。
- 里程点和最高点 / 坡顶开关。
- 底部剖面图点击定位 / 新增 CP。
- 2D / 3D 滑块、归北、自动旋转。
- 活动详情页轨迹缩略图跳转轨迹分析工具。

## 结论

自动化和静态合同未发现 CDEM-01 至 CDEM-06 引入既有轨迹分析交互回归。海拔墙保持退役状态，底部剖面图继续作为唯一海拔剖面表达。

CDEM-07 的 CDEM 聚焦验收和任务清单完整回归组均已通过，可按任务循环进入 CDEM-08。
