# CDEM-07 工程级提示词

> 任务：CDEM-07 既有分析交互回归
> 生成时间：2026-07-30
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `README.md`
- `docs/archive/ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/field_contract_matrix.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_06_工程提示词.md`
- `track.html` 的 CP、里程、最高点 / 坡顶、进度滑块、底部剖面图、2D / 3D 滑块、归北、自动旋转和活动详情跳转锚点
- `tests/test_track_cesium_dem_contract.py`
- `tests/test_track_html_sync_logic.py`
- `tests/test_track_thumbnail_canvas_v4.py`
- `tests/test_v9_0_detail_tab_review.py`

刷新摘要后确认：

- CDEM-07 不新增产品能力，除非发现前序任务引入回归才修复。
- FIT / 手表海拔仍是活动事实源，底部剖面图继续消费该数据。
- 海拔墙已经退役，不能为了回归测试恢复。
- ArcGIS 真实地形 provider、DEM session cache、标准地形回退和 2D / 3D 解耦需要保持。
- CP、里程、最高点 / 坡顶、进度切片、底部剖面、相机、归北、自动旋转和详情页缩略图跳转不得丢失。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

系统性验证 Cesium 升级、真实地形图层、DEM session cache 和海拔墙退役后，既有轨迹分析交互仍具备完整锚点和自动化合同覆盖。

## 2. Scope

允许修改：

- 与轨迹分析交互回归直接相关的测试或极小修复
- 可新增 `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_07_回归报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_07_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证和 review 通过后更新状态
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`，仅记录 CDEM-07 结果

禁止修改：

- `main.py`、`docs/js_api_contract.json`、DEM cache 生命周期和 pywebview API，除非测试定位到 CDEM 回归。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、剖面图、复盘和 AI 事实。
- 恢复海拔墙、引入 MapLibre / deck.gl、重做活动详情概览 / 复盘合同，以及并行 dirty worktree 文件。

## 3. Expected Work

- 运行任务清单指定测试组。
- 静态核对 `track.html` 中 CP、里程、最高点 / 坡顶、进度滑块、底部剖面图、2D / 3D、归北、自动旋转和详情页跳转锚点。
- 若测试失败，先判断是否 CDEM 范围内回归；只修复本轮引入的回归。
- 生成回归报告，记录自动化覆盖、未能自动验证的真实轨迹手测项和结论。

## 4. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py tests/test_track_dem_session_cache.py
git diff --check
```

## 5. Completion Definition

- 任务清单指定自动化回归测试通过。
- 回归报告明确 CP、里程、最高点 / 坡顶、进度、剖面、相机、归北、自动旋转、缩略图跳转的自动化 / 静态覆盖情况。
- 未恢复海拔墙，未改写任何活动事实、统计、复盘或 AI 输入。
- 聚焦测试和 `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 测试失败指向 CP、进度切片、底部剖面、相机释放链路或详情页跳转。
- 需要修改 FIT / 手表海拔、活动数据库、统计、复盘或 AI 输入。
- 需要修改 ArcGIS provider、DEM session cache 或恢复海拔墙。
