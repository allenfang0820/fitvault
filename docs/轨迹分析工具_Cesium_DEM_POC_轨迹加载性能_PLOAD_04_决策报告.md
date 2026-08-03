# PLOAD-04 Cesium 显示几何决策报告

> 日期：2026-08-03
> 状态：Completed
> 决策：不采用显示几何抽稀

## 1. 决策

当前不为 Cesium polyline 引入独立的抽稀显示几何，继续使用单一 `appState.points` 和当前 `appState.fullPositions` 路径。

## 2. 证据

- PLOAD-01 已将 activity `127` / `907` 的 stats / peak 热点分别降低约 `68.3%` / `61.5%`，逐点 warning 降为 `0`，marker 位置和优先级不变。
- PLOAD-02 已将两条 canonical context payload 分别缩减 `99.992%` / `99.996%`，临时路线仍保留 points。
- PLOAD-03 已将 ECharts、context sync、报告、地区解析和雷达移出首屏，并把固定 `2.5s` 初始动画改为可中断的 `0.8s` 短动画。
- PLOAD-04 复测 activity `127` / `907` 时，warning、km / peak 数量、最高点和 context 合同继续保持。
- 现有探针只确认全量 Cartesian3 路径仍存在，没有证明它是低风险优化后的剩余主瓶颈。

## 3. 风险判断

现在引入双轨迹结构会增加以下风险，而收益尚无分段证据支持：

- 进度切片与原始点索引偏移。
- CP 编辑、里程点和最高点映射漂移。
- 底部剖面点击定位与显示线不一致。
- 标准 / 真实地形 entity 重建和快速切换路线竞态扩大。

因此不为完成清单预埋抽稀算法、点数阈值、Worker 或渐进 entity。

## 4. 重开条件

仅在 PLOAD-06 的真实 DMG 分段同时满足以下条件时重开：

- 首屏可交互仍未达到相对基线至少 `30%` 的改善目标。
- Cartesian3 构建或 Cesium entity / polyline 提交被独立测量为剩余主瓶颈。
- 已能定义路线视觉偏移、marker 映射和进度 / 剖面联动的自动化门禁。

## 5. 验证

```text
24 passed
activity 127 / 907 probe: passed
git diff --check: passed
```

本任务没有修改生产代码。WebView GPU 和真实 DMG 首屏耗时仍是 PLOAD-06 待验收项。
