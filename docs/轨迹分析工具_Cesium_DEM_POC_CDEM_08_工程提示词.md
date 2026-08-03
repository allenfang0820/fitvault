# CDEM-08 工程级提示词

> 任务：CDEM-08 安装包、网络和存储验收
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
- `main.py` 中 `DemSessionCache`、`Api.prepare_dem_session_cache()`、`Api.cleanup_dem_session_cache()`、`main()` 退出清理
- `track.html` 中 `selectTerrainLayer()`、`loadRealTerrainLayerForCurrentTrack()`、`applyStandardTerrainLayer()`、2D / 3D slider block
- `tests/test_track_dem_session_cache.py`
- `tests/test_track_cesium_dem_contract.py`

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源；DEM 只做地图环境显示。
- DEM 不进入安装包，不默认下载，不写数据库，不生成长期缓存。
- 真实地形只由用户点击 `真实地形` 触发；2D / 3D slider 只控制相机。
- ArcGIS World Elevation 是本轮在线 DEM POC provider；本轮不做自托管、长期离线包或国内服务终局选型。
- 网络失败必须回退标准地形，不阻断轨迹分析工具。
- 海拔墙已经退役，不得恢复。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

确认 Cesium 1.143 升级与 DEM POC 在资源体积、网络依赖和本地存储方面满足短期交付手册要求，并输出可复核的资源验收报告。

## 2. Scope

允许修改：

- `docs/轨迹分析工具_Cesium_DEM_POC_资源验收报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_08_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证通过后更新状态
- 与 DEM 缓存清理或失败回退直接相关的测试 / 极小修复

禁止修改：

- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、底部剖面图、复盘和 AI 事实。
- Cesium 之外的第三方资源替换。
- ACS、生涯、多运动详情、力量训练、同步导入等并行 dirty worktree 文件。
- MapLibre / deck.gl、长期 DEM 缓存、自托管 DEM、离线 DEM 包管理。

## 3. Expected Work

- 记录 `du -sh lib/Cesium` 与 `find lib/Cesium -type f | wc -l`。
- 对比 CDEM-00 基线 `18M / 375 files`，记录潜在安装包增量。
- 静态确认 DEM 不在 `lib/Cesium` 或安装资源内，当前只通过在线 ArcGIS provider 请求。
- 静态确认首次启动不下载 DEM：`DemSessionCache.__init__()` 不创建当前 session，`initCesiumViewer()` 只用 `EllipsoidTerrainProvider`。
- 静态确认用户点击 `真实地形` 才调用 `prepare_dem_session_cache()` 和 `ArcGISTiledElevationTerrainProvider.fromUrl(...)`。
- 静态 / 测试确认 DEM session cache 不写活动数据库，启动清理旧 session，退出清理当前 session。
- 使用 `curl` 探测 ArcGIS World Elevation endpoint 当前可访问性，并记录 HTTP 状态、耗时、下载大小。
- 生成资源验收报告，明确自动化覆盖、未自动化手测项和风险。

## 4. Validation

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
curl -L -sS --connect-timeout 5 --max-time 15 -o /tmp/arcgis_terrain_pjson.txt -w 'http_code=%{http_code}\ntime_total=%{time_total}\nremote_ip=%{remote_ip}\nsize=%{size_download}\n' 'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer?f=pjson'
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py
git diff --check
```

## 5. Completion Definition

- 资源验收报告落盘并包含体积、文件数、网络探测、存储生命周期和失败回退结论。
- DEM 仍不进入安装包，不默认下载，不长期累积本地存储。
- 聚焦测试和 `git diff --check` 通过。
- 若网络探测失败，报告需明确失败不阻断标准地形，并由自动化合同覆盖回退路径。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 需要修改 DEM provider、缓存目录、缓存生命周期或 pywebview API。
- 需要将 DEM 写入长期缓存、安装包、活动数据库或轨迹事实字段。
- 需要修改 FIT / 手表海拔、累计爬升、最高海拔、底部剖面图、复盘或 AI 输入。
- 网络失败处理需要改变用户交互或跨出 `track.html` / `main.py` CDEM 范围。
