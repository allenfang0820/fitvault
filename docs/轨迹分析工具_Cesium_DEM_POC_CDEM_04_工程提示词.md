# CDEM-04 工程级提示词

> 任务：CDEM-04 DEM 会话临时缓存
> 生成时间：2026-07-30
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `README.md`
- `docs/archive/ARCHITECTURE.md`
- `docs/DIR_SPEC.md`
- `docs/field_contract_matrix.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_03_工程提示词.md`
- `main.py` 的 `Api`、应用启动 / 退出生命周期和统一 API 响应封装
- `track.html` 的 `appState`、地形图层状态机、轨迹加载和 2D / 3D 滑块绑定
- `tests/test_track_cesium_dem_contract.py` 与新增 DEM session cache 测试

刷新摘要后确认：

- 脉图保持本地优先；DEM 不进入安装包、不默认下载，且与活动 DB、工作区轨迹文件隔离。
- FIT / 手表海拔仍是活动事实源；DEM 缓存和 bbox 只服务地图环境，不得回写活动数据、统计、剖面图、复盘或 AI。
- CDEM-04 只建立会话临时缓存、启动清扫、退出清理和用户操作触发的 bbox 预备桥接；不接入实际 DEM provider、网络下载或贴地轨迹。
- 仅用户点击 `真实地形` 可创建当前 DEM session 目录；轨迹加载、启动和 2D / 3D 滑块不得创建 DEM 缓存或下载任务。
- `Api._session_id` 会被 AI 会话流程刷新；DEM 必须使用独立应用会话 ID，退出时删除当前目录，不能误删或遗留。
- CP、里程、坡顶 / 最高点、进度切片、底部剖面、2D / 3D 相机语义和海拔墙删除计划都不得受影响。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖、格式化或提交无关文件。

## 1. Goal

在不下载 DEM、也不改变地图 provider 的前提下，建立受控的 DEM 会话临时缓存边界：启动清理旧会话残留，用户选择真实地形时仅为当前路线创建带小缓冲区 bbox 的临时预备目录，应用退出时删除当前会话目录。

## 2. Scope

允许修改：

- `main.py` 中 DEM session cache manager、`Api` 桥接和 `main()` 清理生命周期
- `track.html` 中真实地形点击后的缓存预备调用，仍使用标准地形回退
- `docs/js_api_contract.json`
- `tests/test_track_dem_session_cache.py`
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_04_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证和 review 通过后更新状态
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`，仅记录 CDEM-04 结果

禁止修改：

- 实际 DEM 下载、长期缓存、LRU、容量设置、离线地形包、网络服务或 Cesium terrain provider。
- FIT / GPX 解析、活动数据库、累计爬升、最高海拔、距离、配速、剖面图、复盘和 AI 事实。
- 轨迹贴地策略、completed / remaining 分段、CP、里程、坡顶 / 最高点、相机控制和海拔墙删除逻辑。
- MapLibre / deck.gl、活动详情概览 / 复盘合同，以及并行 dirty worktree 文件。

## 3. Expected Work

- 在 `~/.fitvault/cache/dem-session/{application_session_id}/` 建立独立的 DEM 会话目录管理器。
- 启动时仅删除旧 `session_*` 残留，不创建当前目录。
- 提供只接收当前轨迹点的受控 API：验证有效 GPS 点，计算包含固定小缓冲区的 bbox，在用户动作后创建当前 session 的预备元数据，并返回统一 API 信封。
- 退出时删除当前会话目录；清理失败只记录日志，不阻断应用关闭。
- 真实地形按钮调用该 API 后，仍显式失败并回退标准地形，等待 CDEM-05 的 provider 接入。
- 更新静态 / 单元测试，锁定“无用户动作不创建目录、异常残留启动清理、退出清理、bbox 缓冲、无 DB 写入、2D / 3D 解耦”。

## 4. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py
jq empty docs/js_api_contract.json
git diff --check
```

## 5. Completion Definition

- DEM 数据不会随应用使用累积：旧会话启动清扫、当前会话退出删除。
- 应用启动和轨迹加载不会创建 DEM cache；只在用户点真实地形后预备当前路线 bbox。
- 缓存位置不在活动数据库或 `workspace/tracks`。
- 不存在实际 DEM 下载、长期缓存、provider 切换或活动事实改写。
- 聚焦测试、JSON 合法性检查和 `git diff --check` 全部通过。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- 需要接入 `CesiumTerrainProvider`、真实 DEM 下载、tile 服务、代理、长期缓存或离线包。
- 需要修改路线高度、轨迹贴地、CP / 里程 / 坡顶高度策略或海拔墙。
- 需要改变 FIT / 手表海拔、活动数据库、统计、剖面图、复盘或 AI 输入。
- 需要让 2D / 3D 滑块触发缓存、下载或地形 provider 切换。
- 测试失败指向 API 契约、启动 / 退出生命周期、活动事实或既有轨迹交互。
