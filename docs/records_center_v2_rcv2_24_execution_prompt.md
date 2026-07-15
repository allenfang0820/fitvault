# RCV2-24 工程级执行提示词：泳池 Length/Lap 最佳努力 Resolver

## 目标

从连续有效 Length/Lap 中生成 50m、100m、200m、400m、800m、1500m 最佳用时 evidence。

## 契约边界

- 按 pool length 精确组合距离，不使用容差。
- 休息中断 best-effort 窗口。
- 无 pool length 不生成 evidence。
- validation_required 不进入 active。
