# PLOAD-05 工程级提示词

> 任务：真实 DEM 加载性能隔离
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 门禁循环

## 0. Contract Refresh

执行前刷新契约摘要，复读交付手册的 DEM 用户触发 / 会话缓存 / 失败回退边界、性能任务清单 PLOAD-05、CDEM-12 相机合同以及当前 terrain / hillshade / marker 重建源码和测试。保留所有无关 dirty 修改。

## 1. Goal

把标准轨迹首屏和用户主动选择真实地形后的网络 / terrain settle 成本明确分离，并为真实 DMG 验收提供一次性可读取的阶段记录。

## 2. Scope

- 记录 DEM session bbox 准备耗时。
- 记录 `ArcGISTiledElevationTerrainProvider.fromUrl()` metadata 耗时。
- 在 provider assignment 后记录是否观察到 pending terrain tile、首批 tile 完成时间和稳定 settle 时间。
- 记录 hillshade overlay 同步建立耗时和 terrain-sensitive scene / marker 重建耗时。
- 保存最近一次标准 / 真实地形切换性能记录；失败时记录错误阶段并继续标准地形回退。
- 增加聚焦静态 / Node 测试和网络可用性报告；未执行真实 WebView tile 的部分保留为 PLOAD-06 待测。

## 3. Constraints

- 标准活动加载不得触发 DEM cache、ArcGIS metadata、tile settle 或 hillshade。
- 不修改 ArcGIS provider / hillshade URL、缓存目录 / 清理、vertical exaggeration 和视觉参数。
- 不在 postRender、tile progress 或轨迹点循环逐次写 console。
- 事件监听必须在成功、超时和异常路径清理。
- 不改变 terrain 按钮与 2D / 3D slider 分工，不新增 route fit 或相机跳变。
- 不修改 points、FIT / GPX、DB、统计、复盘或 AI 事实。
- 若计时需要改变 provider 生命周期、缓存语义或相机合同，立即停止并重新全文阅读权威文档。

## 4. Expected Files

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- 必要时新增 terrain timing 聚焦测试
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_轨迹加载性能优化任务清单.md`
- PLOAD-05 完成报告与本工程提示词

禁止修改 `main.py` DEM cache 实现、provider 选型、marker 视觉和无关测试。

## 5. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_load_profile_probe.py
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
node --check /tmp/fitvault_track_inline.js
git diff --check
```

网络探针分别请求 ArcGIS terrain metadata 和 hillshade tile；该探针只能证明当前网络可达，不得替代真实 Cesium / WebView tile settle。

## 6. Completion Definition

- 标准路径没有新增 DEM 等待。
- 真实地形记录覆盖 cache、metadata、首批 tile、settle、hillshade、marker rebuild、total 和失败状态。
- tile 监听有界且无泄漏，未观察到的阶段保持 `null` / 明确状态。
- 失败回退、缓存生命周期、相机和活动事实合同全绿。
- 聚焦测试、JS 语法、网络探针、diff check 和 adaptive review 通过。
