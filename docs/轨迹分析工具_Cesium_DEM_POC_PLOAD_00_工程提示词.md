# PLOAD-00 工程级提示词

> 任务：轨迹加载链路分段基线
> 生成时间：2026-08-03
> 父任务：CDEM-14
> 执行模式：task-loop-runner 门禁循环

## Goal

在不改变生产行为的前提下，量化高密度轨迹从 SQLite / Python 到前端统计与 Cesium 首屏的关键阶段，确认四姑娘山活动超过 5 秒等待的主要来源，并冻结 PLOAD-01、PLOAD-02、PLOAD-03 的输入指标。

## Contract Gate

已完整阅读并以以下文件为权威来源：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_轨迹加载性能优化任务清单.md` v0.2.0

必须保留 FIT / 手表和后端 canonical facts；不得改变 CP、里程、最高点 / 坡顶、进度、剖面、相机、DEM provider、session cache 或海拔墙退役合同。

## Scope

允许：

- 新增只读诊断脚本和对应测试。
- 新增 PLOAD-00 基线报告。
- 更新契约摘要、任务状态和完成记录。
- 读取本机 `~/.fitvault/user_profile.db` 中指定活动进行只读探针。

禁止：

- 修改 `track.html`、`main.py` 或其他生产代码行为。
- 写活动数据库、修改 points 或 canonical metrics。
- 以合成数据替代真实 activity `127` / `907` 的主要证据。
- 把未执行的 pywebview / DMG / DEM 网络阶段写成通过。

## Expected Areas

- `scripts/profile_track_load.py`
- `tests/test_track_load_profile_probe.py`
- `docs/轨迹分析工具_轨迹加载性能_PLOAD_00_基线报告.md`
- CDEM-14 契约摘要和任务清单

## Required Measurements

- `Api.load_activity_track()` 本地调用耗时。
- Python response JSON 编码耗时和 payload 字节数。
- points 数量与数据库 track JSON 字节数。
- 使用 `track.html` 当前 `haversine()`、`_detectPeakMarkers()`、`_buildStatsFromCanonical()` 源码的 Node 探针耗时。
- `haversine()` 路径内 `console.warn()` 调用次数。
- canonical points 的重复 `JSON.stringify()` 耗时。
- 静态确认 `updateScene()` 全量 Cartesian3、固定 `2.5s` `flyTo` 和 canonical `sync_track_context` 全量 points 路径。
- 明确无法由本地探针覆盖的 pywebview bridge、WebKit/Cesium GPU、DEM provider / tile / hillshade 阶段。

## Validation

```bash
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
.venv312/bin/python -m pytest -q tests/test_track_load_profile_probe.py tests/test_track_cesium_dem_contract.py
git diff --check
```

## Completion Definition

- 探针使用真实数据库和当前生产函数源码，输出可重复的结构化结果。
- 至少确认两个主要性能热点，并区分已测事实与待测 DMG 阶段。
- 测试与 diff review 全绿。
- PLOAD-00 标记 `Completed` 后，刷新契约摘要并进入 PLOAD-01；测试不绿时不得继续。
