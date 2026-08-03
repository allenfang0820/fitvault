# PLOAD-04 工程级提示词

> 任务：Cesium 显示几何可选 POC 决策
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 复杂度门禁

## 0. Contract Refresh

执行前刷新 `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`，复读性能任务清单 PLOAD-04、PLOAD-00 基线和 PLOAD-01 至 PLOAD-03 完成报告。保留 dirty worktree，不修改无关文件。

## 1. Goal

依据前三项低风险优化的实测数据，决定是否需要为 Cesium polyline 引入单独显示几何。若已无证据支持几何是首屏主瓶颈，则以“不采用”结论完成，避免为清单形式强行增加双轨迹结构。

## 2. Scope

- 汇总 activity `127` / `907` 的点数、算法降幅、context payload 缩减和 PLOAD-03 首屏调度结果。
- 核对全量 Cartesian3 仍存在，但没有独立分段数据证明它是剩余主瓶颈。
- 记录不采用显示抽稀的理由、回滚 / 重开条件和 PLOAD-06 后续证据要求。
- 更新任务状态、契约摘要和决策报告。

## 3. Constraints

- 不修改 `track.html`、`main.py`、Cesium entity、points 或生产行为。
- 不新增显示点数组、抽稀算法、点数阈值、Worker 或渐进渲染占位实现。
- 不改变 CP、1/5/10km、最高点 / 坡顶、进度、剖面、相机或 terrain 合同。
- 不把未执行的真实 DMG / WebView GPU 分段写成已通过。
- 若证据与任务清单冲突，重新全文阅读交付手册、任务清单和契约摘要后停止扩展范围。

## 4. Expected Files

- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_轨迹加载性能优化任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_轨迹加载性能_PLOAD_04_决策报告.md`
- 本工程提示词

## 5. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_load_profile_probe.py tests/test_track_cesium_dem_contract.py
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
git diff --check
```

额外审查本任务没有新增 `track.html` 生产 diff。

## 6. Completion Definition

- 采用 / 不采用结论有 PLOAD-01 至 PLOAD-03 数据支持。
- 不采用时，生产代码保持不变，重开条件明确指向 PLOAD-06 真实 DMG 分段证据。
- 聚焦测试、探针和 diff check 全绿，自适应审查无阻断项。
