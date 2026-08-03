# PLOAD-03 工程级提示词

> 任务：相机定位与非关键工作调度
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 门禁循环

## 0. 契约门禁

执行前刷新并阅读：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_轨迹加载性能优化任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_14_工程提示词.md`
- `track.html` 的 `applyDataAndRender()`、相机 ownership、ECharts、报告、雷达、地区解析和 context sync 路径
- `scripts/profile_track_load.py` 与直接相关测试

工作区存在大量并行 dirty 修改。不得 stash、reset、清理、格式化或覆盖无关文件；只在下列允许范围内追加本任务变更。

## 1. Goal

让高密度路线的 Cesium 地图、顶部权威指标、底部 Canvas 海拔剖面和 CP 列表先进入可操作状态，缩短固定 `2.5s` 初始相机动画和非关键同步工作造成的感知等待，同时保持路线 framing、相机接管和 CDEM-12 地形切换合同。

## 2. Scope

- 为每次有效 `applyDataAndRender()` 增加 render revision。
- 在首帧后按可取消队列执行 ECharts、轨迹上下文同步、报告、地区解析和性能雷达。
- 保留 `updateScene()`、顶部指标、Canvas 剖面、路线 framing 数据和 CP 列表在首屏路径。
- 将初始路线 `flyTo` 改为一致的短动画，保留 destination / orientation；用户发起 slider、归北、缩放、旋转等相机控制时可取消该动画。
- 复测 activity `127`、`907` 并形成是否进入 PLOAD-04 显示几何 POC 的依据。

## 3. Constraints

- FIT / 手表和后端 canonical metrics 是事实源；不得改写 points、距离、爬升、最高海拔、复盘或 AI 事实。
- 保留 CP 展示 / 新增 / 编辑 / 删除、1/5/10km、最高点优先级、进度切片、底部剖面联动。
- 不修改 standard / real terrain provider、hillshade、DEM cache、地形切换相机恢复或 2D / 3D slider 职责。
- 不修改 marker 图钉像素、地形高度策略或显示几何点数。
- 后台队列必须在快速切换路线时阻止旧 revision 执行；任务异常不得终止后续任务或首屏。
- 若实现需要改变 API、数据生命周期、provider、活动事实或相机 framing 语义，立即停止并重新全文阅读所有权威文档和直接相关源码 / 测试。

## 4. Expected Files

- `track.html`
- `tests/test_track_load_profile_probe.py`
- 必要时新增一个仅验证调度 / 相机合同的聚焦测试文件
- `scripts/profile_track_load.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_轨迹加载性能优化任务清单.md`
- PLOAD-03 完成报告

禁止修改 `main.py`、FIT / GPX 解析、数据库、Cesium provider / cache、活动详情 / 复盘和无关测试。

## 5. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_load_profile_probe.py tests/test_activity_advice_frontend.py tests/test_track_cesium_dem_contract.py
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907
sed -n '10748,25667p;25671,31107p' track.html > /tmp/fitvault_track_inline.js
node --check /tmp/fitvault_track_inline.js
git diff --check
```

编辑后必须重新读取 `<script>` 边界再执行 `node --check`，不能盲用旧行号。adaptive review 重点检查旧 revision 写回、相机 ownership 死锁、后台任务遗漏和 terrain switching 误改。

## 6. Completion Definition

- 首屏路径不再同步执行 ECharts、报告、雷达、地区解析和 context sync。
- 固定 `2.5s` 初始路线动画已移除，短动画可被用户相机控制取消；首屏完成不依赖动画结束。
- 快速切换路线时旧后台任务不执行，当前路线任务按顺序执行且单项异常被隔离。
- activity `127`、`907` 探针、聚焦回归、JS 语法和 diff check 全绿。
- 完成报告明确 PLOAD-04 采用 / 不采用的证据，不把未执行的真实 DMG 分段写成通过。
