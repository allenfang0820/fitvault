# CDEM-12 工程级提示词

> 任务：地形切换相机一致性修复任务规划
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 门禁循环

## 0. 契约核对

执行前必须阅读并刷新：

- `.trae/rules/fit-arch-contrac.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`
- `track.html` 中 terrain provider、视觉模式、tile settle、scene refresh、相机 ownership、2D / 3D slider 和归北相关代码
- `tests/test_track_cesium_dem_contract.py`

本轮只规划任务，不修改生产代码。dirty worktree 中既有 Cesium、力量训练、ACS 和其他并行修改不得 stash、reset、覆盖、格式化或提交。

## 1. Goal

生成可独立执行、逐项验证的修复任务清单，使标准地形与真实地形切换后保持同一用户视图，并保留当前控件分工和全部轨迹分析功能。

## 2. Frozen Product Decisions

- 2D / 3D slider 继续只控制视角。
- 图层按钮继续只控制标准 / 真实 terrain provider。
- 标准地形允许在 3D slider 状态下显示三维透视。
- 地形切换不改 slider 值，不重新 fit 路线，不自动归北。
- 相机一致性按同一屏幕中心地理锚点、heading / pitch / roll、焦点距离和屏幕尺度定义，而不是按相机 ECEF 坐标不变定义。
- 真实地形现有 `verticalExaggeration`、hillshade、贴地轨迹和 marker 高度策略保持不变。

## 3. Required Task Decomposition

任务清单至少拆分：基线与量化验收、相机快照合同、异步切换事务、目标地表锚点解析、平滑相机恢复、轨迹 / marker 时序集成、失败与竞态回退、自动化和真实 UI 验收。

每项任务必须写明：目标、前置、允许文件、必做、禁止项、验收命令、量化完成标准和未自动化手测项。

## 4. Forbidden Scope

- 不合并 slider 与 terrain provider 语义。
- 不修改 DEM provider、缓存生命周期或安装包策略。
- 不恢复海拔墙。
- 不修改 FIT / GPX、DB、累计爬升、最高海拔、剖面、复盘或 AI 事实。
- 不用 `flyToBoundingSphere` 或路线重新 framing 掩盖视角跳变。

## 5. Deliverables And Validation

交付物：

- `docs/轨迹分析工具_地形切换相机一致性修复任务清单.md`
- 刷新后的 CDEM 契约摘要
- CDEM 主任务清单中的 CDEM-12 总任务入口

文档验证：

```bash
rg -n "2D / 3D|terrain provider|相机快照|地理锚点|竞态|失败回退|flyToBoundingSphere|真实 UI" docs/轨迹分析工具_地形切换相机一致性修复任务清单.md
git diff --check
```

## 6. Completion Definition

- 清单覆盖完整依赖链和量化验收，不把未验证场景写成通过。
- 产品控件分工、数据事实边界和既有功能保护均明确。
- 本轮只落文档，不修改 `track.html` 或测试生产行为。
