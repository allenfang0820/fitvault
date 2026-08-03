# CDEM-01 工程级提示词

> 任务：CDEM-01 Cesium 1.143 本地资源升级
> 生成时间：2026-07-30
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `tests/test_track_cesium_dem_contract.py`
- `track.html` 的 Cesium 资源加载与初始化区域

刷新摘要后确认：

- FIT / 手表海拔仍是活动事实源，Cesium 资源升级不得改变活动事实。
- 本任务只替换本地 Cesium 资源和版本 fallback，不接入 DEM provider。
- `window.CESIUM_BASE_URL` 必须继续指向 `lib/Cesium/`。
- CDN fallback 不得继续混用 `1.105.1`。
- CP、里程、坡顶、进度、底部剖面图、相机和海拔墙基线都不在本任务改动范围内。
- dirty worktree 中存在大量无关改动，不得 stash、reset、覆盖或格式化。

## 1. Goal

将轨迹分析工具本地 Cesium 构建资源升级到官方 `cesium@1.143`，并保持 pywebview 页面可继续从本地 `lib/Cesium` 访问 Cesium 主文件、Workers、Assets 和 Widgets CSS。

## 2. Scope

允许修改：

- `lib/Cesium/**`
- `.gitattributes`，仅限为 `lib/Cesium/**` 配置第三方构建产物 whitespace 检查边界
- `track.html` 中 Cesium CSS / script fallback 版本和资源路径相关代码
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_01_工程提示词.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`，仅在验证通过后更新状态

禁止修改：

- viewer 初始化功能语义、轨迹渲染、海拔墙、CP、里程、坡顶、进度、剖面图和相机控制逻辑。
- `main.py`、`track_backend.py`、`fit_engine.py`、`metrics_resolver.py`、`metrics_registry.py`。
- `docs/js_api_contract.json`。
- FIT / GPX 解析、活动数据库、复盘算法、AI prompt、MapLibre / deck.gl 实现。
- 与本任务无关的并行 dirty worktree 文件。

## 3. Expected Work

- 获取官方 `cesium@1.143` 包。
- 使用官方 `Build/Cesium` 产物更新 `lib/Cesium`。
- 保持 `window.CESIUM_BASE_URL = 'lib/Cesium/'`。
- 将 `track.html` 中 Cesium CDN fallback 从 `1.105.1` 更新为 `1.143`，或收敛为与本地版本一致。
- 更新静态契约测试中的版本断言。
- 记录升级前后体积和文件数量。
- 如官方构建产物触发 `git diff --check` 的 whitespace 噪声，仅允许通过 `.gitattributes` 对 `lib/Cesium/**` 设置第三方资源边界，不扩大到业务源码。

## 4. Validation

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

## 5. Completion Definition

- `lib/Cesium` 来自官方 `cesium@1.143` 的 `Build/Cesium` 产物。
- 页面本地资源路径仍完整。
- `track.html` 不再混杂旧版 Cesium fallback。
- 聚焦契约测试和 `git diff --check` 通过。
- 基线审计报告记录升级后的资源体积和潜在安装包增量。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读相关文档或源码：

- Cesium 包结构与 CDEM-00 基线结构不一致。
- 需要修改 viewer 初始化、轨迹 entity、海拔墙或相机控制逻辑。
- 测试要求接入 DEM provider、删除海拔墙或修改活动事实。
- 发现 `track.html` 中旧版 Cesium fallback 无法只通过版本更新解决。
