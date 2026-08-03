# CDEM-00 工程级提示词

> 任务：CDEM-00 基线审计与合同冻结
> 生成时间：2026-07-30
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `README.md`
- `docs/archive/ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/field_contract_matrix.md`
- `docs/js_api_contract.json`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`

刷新摘要后确认：

- FIT / 手表海拔是活动事实源，DEM 只是地图显示层。
- 前端不得从 DEM、DOM、Cesium entity、剖面图或轨迹点改写复盘 / AI / DB 事实。
- 2D / 3D 滑块只管相机视角。
- 真实地形必须是独立图层开关。
- DEM 不进安装包，不默认下载，不做长期缓存。
- 海拔墙后续必须彻底退役。
- CP 点、里程点、最高点 / 坡顶、进度、底部剖面图、相机、自动旋转和详情跳转必须保留。

## 1. Goal

冻结当前轨迹分析工具的 Cesium / 交互 / 海拔墙 / 测试基线，生成后续任务可引用的事实锚点，避免升级或删除时误伤既有功能。

## 2. Scope

只做审计、文档和静态契约测试，不修改生产行为。

允许修改：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_00_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `tests/test_track_cesium_dem_contract.py`

禁止修改：

- `track.html` 生产行为。
- `lib/Cesium/**`。
- `main.py`、`track_backend.py`、`fit_engine.py`、`metrics_resolver.py`、`metrics_registry.py`。
- 活动数据库、FIT / GPX 解析链路、复盘算法、AI prompt、MapLibre / deck.gl 相关实现。
- 与本任务无关的并行 dirty worktree 文件。

## 3. Expected Work

- 记录当前 `lib/Cesium` 体积和文件数量。
- 记录 Cesium 初始化、资源路径、Workers / Widgets / Assets 结构。
- 盘点海拔墙相关状态、点击识别、entity 创建范围和后续删除目标。
- 盘点 CP、里程、坡顶、进度、底部剖面图、2D / 3D、指南针 / 归北、自动旋转等保留入口。
- 新增聚焦静态测试，锁住 CDEM-00 基线。
- 将任务清单中 CDEM-00 状态更新为已完成仅在测试通过之后执行。

## 4. Validation

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

## 5. Completion Definition

- 基线审计报告能指导后续任务定位所有必须保留或删除的轨迹分析入口。
- 静态测试通过并覆盖当前 Cesium 资源、viewer 初始化、海拔墙基线和既有交互锚点。
- 未修改 `track.html` 生产行为。
- `git diff --check` 通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档：

- 需要修改本任务允许文件以外的文件。
- 测试发现与交付手册或任务清单不一致。
- 准备提前升级 Cesium、接入 DEM 或删除海拔墙。
- 发现 CP / 里程 / 坡顶 / 进度 / 剖面 / 相机入口与报告描述冲突。

