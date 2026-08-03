# 轨迹加载性能 PLOAD-01 完成报告

> 日期：2026-08-03
> 任务：热循环、逐次日志与峰顶检测优化
> 状态：Completed

## 1. 实现

- 删除 `haversine()` 每次调用的 `console.warn()`。
- canonical points 有有效 `dist_km` / `dist` 时直接消费；只有距离缺失或非法时才计算 fallback segment。
- 峰顶检测为每个点预计算球面单位向量，以球面弦长平方比较 250m / 300m 阈值，保留原有连续扫描、12m prominence、250m 去重和最高点 300m 升级控制流。
- 原始 points、活动事实、CP、里程、最高点 / 坡顶、DEM、相机和剖面合同未改变。

## 2. 性能对比

| activity | 场景 | 修复前 stats / peak | 修复后 | 下降 | warning calls |
| ---: | --- | ---: | ---: | ---: | ---: |
| `127` | 四姑娘山二峰登顶 | `536.802ms` | `170.412ms` | `68.3%` | `21,140,328 → 0` |
| `907` | 长坪沟到二峰大本营 | `220.093ms` | `84.722ms` | `61.5%` | `8,764,412 → 0` |
| `1117` | 西城区城市跑 | `21.511ms` | `7.259ms` | `66.3%` | `119,097 → 0` |
| `1094` | 雅安骑行 | `9.497ms` | `5.825ms` | `38.7%` | `91,646 → 0` |

以上为同一只读探针、真实数据库活动和生产函数源码结果；耗时会受机器负载影响，marker 与 warning 合同是确定性证据。

## 3. Marker 回归

- activity `127`：`1` 个 peak，最高点坐标 / 海拔保持 `102.90826616808772, 31.068927738815546, 5336.6m`。
- activity `907`：`4` 个 peak，全部经纬度、海拔和 `isHighest` 与修复前一致。
- activity `1117`：`1` 个 peak，坐标、海拔和最高点标志一致。
- activity `1094`：`2` 个 peak，坐标、海拔和最高点标志一致。
- km marker 数量分别保持 `10 / 18 / 7 / 23`。

## 4. 验证

```text
22 passed
node --check /tmp/fitvault_track_inline.js: passed
git diff --check: passed
```

adaptive review：改动局限于显示层距离 / peak 辅助函数、探针、测试和文档；未发现阻塞问题。

## 5. 下一项

进入 PLOAD-02，取消 canonical activity 在 `sync_track_context()` 中重复回传完整 points，同时保留临时 GPX / FIT 预览和 activity advice 白名单事实合同。
