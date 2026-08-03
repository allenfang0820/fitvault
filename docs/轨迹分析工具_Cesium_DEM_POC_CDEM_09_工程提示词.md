# CDEM-09 工程级提示词

> 任务：CDEM-09 POC 总验收与交付报告
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
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_07_回归报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_资源验收报告.md`
- `track.html` 的 Cesium 初始化、terrain provider、CP、里程、最高点 / 坡顶、进度、底部剖面、相机、缩略图跳转锚点
- `main.py` 的 DEM session cache 生命周期
- CDEM 聚焦测试与详情页回归测试

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源；DEM 只做地图环境显示。
- DEM 不进入安装包，不默认下载，不写活动数据库，不长期累积本地存储。
- 2D / 3D slider 只控制相机；真实地形独立图层开关。
- 海拔墙已彻底退役，不得恢复。
- CP、里程、最高点 / 坡顶、进度、剖面、相机、详情页缩略图跳转必须保留。
- 未实际执行的真实轨迹手测不得写成通过。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

完成 Cesium DEM POC 的总体验收文档，汇总 CDEM-00 到 CDEM-08 的执行结论、最终自动化验证、真实 UI 手测状态、剩余风险和后续建议。

## 2. Scope

允许修改：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_09_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证后更新状态
- 必要的测试期望更新，仅限总验收发现 CDEM 合同遗漏

禁止修改：

- 生产代码，除非最终自动化明确定位到 CDEM 范围内回归。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、底部剖面图、复盘和 AI 事实。
- ACS、生涯、多运动详情、力量训练、同步导入等并行 dirty worktree 文件。
- MapLibre / deck.gl、长期 DEM 缓存、自托管 DEM、离线 DEM 包管理。

## 3. Expected Work

- 汇总 CDEM-00 到 CDEM-08 的完成记录。
- 汇总最终自动化验证结果。
- 汇总 CP、里程、最高点 / 坡顶、进度、底部剖面、2D / 3D、归北、自动旋转、缩略图跳转的覆盖结论。
- 汇总海拔墙退役、Cesium 体积、ArcGIS provider、DEM 触发边界、session cache 生命周期、失败回退结论。
- 明确城市跑、山地 / 越野跑、骑行爬坡真实 UI 点检尚未自动执行，列为发布前手测。
- 给出是否进入后续正式开发的条件化建议。

## 4. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
git diff --check
```

## 5. Completion Definition

- 开发完成报告落盘。
- 最终自动化回归组和 `git diff --check` 通过。
- 所有 P0 回归项均有“自动化通过 / 手测待执行 / 风险”明确结论。
- 未执行的真实轨迹手测不被写成通过。
- 任务清单状态只在自动化全绿且报告完成后更新。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 最终自动化失败。
- 需要修改生产代码、测试合同或 CDEM 任务范围。
- 发现 CP、里程、最高点、剖面、进度、相机、缩略图跳转、DEM cache、海拔墙退役存在冲突。
- 需要把真实 UI 手测缺口改写为通过。
