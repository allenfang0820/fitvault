# CDEM-13 工程级提示词

> 任务：真实地形 CP / 里程 / 最高点标记清晰度分析与任务规划
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 门禁循环

## 0. 契约核对

执行前必须阅读并刷新 CDEM 开发交付手册、主任务清单、契约摘要、开发完成报告、相机一致性修复任务清单，以及 `track.html` 的 pin canvas、billboard、label、viewer 分辨率和 WebView shader 兼容代码。

本轮只分析并落盘任务，不修改生产代码。dirty worktree 中无关修改必须保留。

## 1. Goal

生成独立、可量化的真实地形标记清晰度修复任务清单，覆盖 CP、里程和最高点三种不同渲染链路，并保持现有功能与 WebView 兼容边界。

## 2. Evidence To Preserve

- `buildMapPinCanvasImage()` 固定 backing scale `2`。
- CP / 最高点 / 普通坡顶 billboard 使用不同且非整比目标尺寸。
- `scaleByDistance` 对 billboard 做连续非整数缩放。
- 里程点是 point + 12px label，不是 canvas billboard。
- pin cache key 不包含 DPR / 尺寸。
- `MSAA=1`、FXAA 关闭是兼容性边界，不能未经 POC 直接恢复。

## 3. Required Task Decomposition

至少拆分：像素 / DPR 基线测量、HiDPI 图钉纹理合同、距离缩放策略、里程标记清晰度、Viewer resolution POC、地形遮挡检查、自动化和真实 UI 验收。

每项任务必须包含目标、允许文件、禁止项、测试、量化完成标准和回滚条件。

## 4. Forbidden Scope

- 不恢复 SVG filter / text 或 emoji billboard。
- 不恢复动态光照、阴影 shader、FXAA 或高 MSAA，除非独立 POC 证明 macOS WebView 兼容且性能可接受。
- 不修改 DEM provider / cache、相机一致性合同、FIT / GPX、DB、剖面、复盘或 AI。
- 不以放大所有 marker 代替清晰度修复。

## 5. Deliverables And Validation

- `docs/轨迹分析工具_真实地形标记清晰度修复任务清单.md`
- CDEM 主清单中的 CDEM-13 入口
- 相机一致性任务清单中的独立关联说明
- 刷新后的契约摘要

```bash
rg -n "DPR|scaleByDistance|billboard|里程|最高点|CP|resolutionScale|MSAA|FXAA|真实 UI" docs/轨迹分析工具_真实地形标记清晰度修复任务清单.md
git diff --check
```

## 6. Completion Definition

- 三类 marker 不被错误视为同一渲染问题。
- 清单包含像素级和真实 UI 证据门禁。
- 本轮不修改 `track.html` 或测试生产行为。
