# PLOAD-01 工程级提示词

> 任务：热循环、逐次日志与峰顶检测优化
> 生成时间：2026-08-03
> 父任务：CDEM-14
> 前置：PLOAD-00 `Completed`

## Goal

消除 canonical 高密度轨迹首屏路径中的逐次 console 日志、无条件 fallback haversine 和峰顶邻域反复三角函数计算，同时保持 CP、里程、最高点 / 坡顶和活动事实合同。

## Scope

允许：

- `track.html` 中 `haversine()`、`_buildStatsFromCanonical()`、`_detectPeakMarkers()` 及紧邻的纯显示辅助函数。
- `scripts/profile_track_load.py`、`tests/test_track_load_profile_probe.py` 和 CDEM 聚焦测试。
- PLOAD-01 对比报告、契约摘要和任务状态。

禁止：

- 修改 `main.py`、数据库、FIT / GPX 解析、canonical metrics、DEM、相机、剖面、复盘或 AI 事实。
- 用抽稀点重算任何事实。
- 删除最高点 / 坡顶或改变 250m 去重、300m 邻域、12m prominence 和最高点升级语义。

## Implementation Contract

- `haversine()` 热函数不得逐次执行 `console.warn()`。
- canonical point 有有效 `dist_km` / `dist` 时直接消费；只有缺失或非法时才计算 fallback segment。
- 峰顶检测为 points 预计算球面单位向量，以球面弦长平方和 250m / 300m 阈值比较距离；弦长比较与当前 haversine 阈值在地球球面模型上等价，避免每次 `sin/cos/atan2`。
- 保留当前按连续点向前 / 向后扫描、超过 300m 即停止、最后接受峰顶 250m 去重、最高点 300m 升级的控制流。
- 对比 activity `127`、`907` 修复前后 peak marker 数量、经纬度、海拔、最高点标志；差异必须为零或有明确阻塞说明。

## Validation

```bash
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
.venv312/bin/python -m pytest -q tests/test_track_load_profile_probe.py tests/test_track_cesium_dem_contract.py
node --check /tmp/fitvault_track_inline.js
git diff --check
```

## Completion Definition

- activity `127` / `907` warning count 为 `0`。
- canonical stats / peak 探针耗时较 PLOAD-00 基线显著下降。
- marker 数量与位置合同保持。
- 聚焦测试、JS 语法和 diff review 全绿后标记 PLOAD-01 `Completed`，再进入 PLOAD-02。
