# PLOAD-03 相机定位与非关键工作调度完成报告

> 日期：2026-08-03
> 状态：Completed
> 任务来源：`docs/轨迹分析工具_轨迹加载性能优化任务清单.md`

## 1. 交付结果

- 首屏同步保留 `updateScene()`、顶部权威统计、Canvas 海拔剖面和 `renderCpList()`。
- ECharts、canonical / temporary context sync、轨迹报告、临时路线地区解析和性能雷达进入首帧后的逐项 idle 队列。
- 每次有效 `applyDataAndRender()` 递增 render revision；旧路线的待执行任务在首帧前或任务之间被取消。
- 初始路线 `flyTo` 从固定 `2.5s` 调整为 `0.8s`，destination、heading、pitch、roll 和 range 计算保持不变。
- 初始定位可抢占上一轮尚未结束的相机控制；slider、归北、缩放、平移、旋转等新的用户控制可取消初始飞行并接管相机。

本任务未修改 terrain provider、CDEM-12 地形切换恢复、marker 视觉 / 高度、轨迹 points、FIT / GPX、数据库或活动事实。

## 2. 中期复测

| Activity | 点数 | stats / peak | warning | km / peak | canonical context |
| --- | ---: | ---: | ---: | --- | ---: |
| `127` 四姑娘山二峰登顶 | 26,052 | `178.074ms` | 0 | 10 / 1 | `99.992%` 缩减 |
| `907` 长坪沟至二峰大本营 | 21,690 | `87.305ms` | 0 | 18 / 4 | `99.996%` 缩减 |

本轮探针确认 marker 数量、经纬度、海拔和最高点标志保持 PLOAD-01 基线；运行时自然波动不改变 PLOAD-01 已确认的 `68.3%` / `61.5%` 热点降幅。

静态首屏合同：

- `has_fixed_2_5s_fly_to = false`
- `has_short_interruptible_initial_flight = true`
- `has_revision_guarded_post_paint_work = true`
- canonical 不携带 points，temporary session 仍携带 points

## 3. 验证

```text
41 passed
node --check: passed
git diff --check: passed
```

Node 调度测试覆盖旧 revision 丢弃和当前 revision 顺序执行。adaptive diff review 发现并修复了“上一轮 orbit 未结束时新路线 framing 可能被跳过”的 ownership 边缘问题；复审无阻断项。

## 4. PLOAD-04 决策

本轮建议 **不采用 Cesium 显示几何抽稀**：

- 已识别的确定性热点已经分别获得 `61.5%–68.3%` 算法降幅和 `99.992%–99.996%` 重复 context payload 缩减。
- 首屏已不再同步等待 ECharts / 报告 / 雷达 / context sync，也不再被固定 `2.5s` 动画定义完成。
- 当前没有分段证据证明全量 Cartesian3 / polyline 是剩余主瓶颈；此时引入原始轨迹与显示轨迹双结构会扩大进度、CP、里程、最高点和剖面联动风险。

因此 PLOAD-04 应以“不采用显示抽稀”的证据结论完成。真实 DMG 的首屏可交互时间、完整 settle 时间和用户感知降幅仍需在 PLOAD-06 实测，本文不将本地探针写成真实 UI 通过。
