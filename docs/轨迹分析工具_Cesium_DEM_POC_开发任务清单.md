---
title: 轨迹分析工具 Cesium 升级与 DEM 地形 POC 开发任务清单
version: v0.1.0
status: Planning
type: Ordered Engineering Task List
updated: 2026-07-30
source:
  - docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md
---

# 轨迹分析工具 Cesium 升级与 DEM 地形 POC 开发任务清单

本文档把 `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md` 拆为可独立执行、验证、提交和回归的工程任务。

本轮目标是在保留现有轨迹分析能力的前提下，完成 Cesium 升级、真实 DEM 地形图层 POC、DEM 会话临时缓存和海拔墙彻底退役。

## 0. 执行规则

- 唯一产品和工程基线是 `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`。
- 每个任务开始前执行 `git status --short`，阅读将要修改文件的既有 diff。
- 当前工作区可能包含运动详情、多运动、力量训练、ACS 或其他并行任务改动；不得 stash、reset、覆盖、格式化或提交无关改动。
- 每个任务只修改“允许改动文件”列出的范围。发现必须扩大范围时，先更新本清单和交付手册。
- 任何业务代码改动前，必须先完成本任务清单落盘并由当前任务引用。
- DEM 不进入安装包，不默认下载，不写入活动记录数据库。
- 海拔墙直接退役，不保留用户入口、内部调试开关或隐藏兼容能力。
- 2D / 3D 滑块只控制视角，不负责地形 provider 或 DEM 下载。
- FIT / 手表海拔仍是活动记录事实，不允许用 DEM 改写累计爬升、最高海拔、剖面图或复盘事实。
- CP 点、里程点、最高点 / 坡顶、进度滑块、底部剖面图联动、活动详情跳转轨迹分析工具等既有能力必须保留。
- 每个任务结束后运行聚焦测试、`git diff --check`，并记录未能自动验证的手测项。
- 除最终验收任务外，各任务应能单独提交；不要把资源升级、图层 UI、DEM 缓存、海拔墙删除和回归修复压成一个不可回滚的大提交。

## 1. 总体状态

| 顺序 | 任务 | 状态 | 前置 | 主要交付物 |
| --- | --- | --- | --- | --- |
| 1 | CDEM-00 基线审计与合同冻结 | `Completed` | 无 | 当前 Cesium/交互/海拔墙/测试基线报告 |
| 2 | CDEM-01 Cesium 1.143 本地资源升级 | `Completed` | CDEM-00 | `lib/Cesium` 升级与资源路径验证 |
| 3 | CDEM-02 Viewer 初始化兼容 | `Completed` | CDEM-01 | Cesium viewer 在新版本下可启动 |
| 4 | CDEM-03 地形图层开关 | `Completed` | CDEM-02 | 标准地形 / 真实地形 UI 与状态机 |
| 5 | CDEM-04 DEM 会话临时缓存 | `Completed` | CDEM-03 | session cache 创建、清理、异常残留清扫 |
| 6 | CDEM-05 真实地形轨迹贴合与语义轨迹保留 | `Completed` | CDEM-03, CDEM-04 | 轨迹近地/贴地渲染与分段语义兼容 |
| 7 | CDEM-06 海拔墙彻底退役 | `Completed` | CDEM-05 | wall entity、状态、样式、测试断言删除 |
| 8 | CDEM-07 既有分析交互回归 | `Completed` | CDEM-06 | CP、里程、最高点、剖面、进度、相机回归；完整回归组通过 |
| 9 | CDEM-08 安装包、网络和存储验收 | `Completed` | CDEM-07 | 体积、DEM 下载、临时缓存清理测量 |
| 10 | CDEM-09 POC 总验收与交付报告 | `Completed` | CDEM-08 | 自动化总验收完成；真实 UI smoke 待发布前补齐 |
| 11 | CDEM-10 顶部工具栏响应式可达性修复 | `Completed` | CDEM-09 | 顶栏语义分组与窄屏更多菜单 |
| 12 | CDEM-11 顶栏统计与视角组防重叠修复 | `Completed` | CDEM-10 | 长统计值防溢出与临界宽度验收 |
| 13 | CDEM-12 地形切换相机一致性修复 | `Planned` | CDEM-09 | 独立修复任务清单与后续实施入口 |
| 14 | CDEM-13 真实地形标记清晰度修复 | `Planned` | CDEM-05 | CP / 里程 / 最高点像素与真实 UI 门禁 |

## 2. 任务依赖

```text
CDEM-00
  |
CDEM-01 ---> CDEM-02 ---> CDEM-03 ---> CDEM-04
                                      \       |
                                       \      v
                                        ---> CDEM-05 ---> CDEM-06 ---> CDEM-07 ---> CDEM-08 ---> CDEM-09
```

`CDEM-03` 完成后可先做 UI 静态测试，但真实 DEM 行为必须等 `CDEM-04` 的会话缓存边界明确后再接入。

---

## 3. CDEM-00：基线审计与合同冻结

优先级：P0
状态：`Completed`
性质：审计 / 合同 / 不改生产行为
前置：无

### 目标

冻结当前轨迹分析工具的 Cesium 版本、资源体积、viewer 初始化、海拔墙实现、CP 点、里程点、最高点、剖面图、进度滑块和相机控制基线，避免升级时误删现有能力。

### 允许改动文件

- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- 可新增 `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- 可新增聚焦静态测试，例如 `tests/test_track_cesium_dem_contract.py`

### 必做

- 记录当前 `lib/Cesium` 体积和文件数量。
- 记录 `track.html` 中 Cesium 初始化入口、`window.CESIUM_BASE_URL`、Workers、Widgets、Assets 加载方式。
- 盘点海拔墙相关 entity、状态、样式、开关和测试断言。
- 盘点 CP 点展示 / 新增 / 编辑入口。
- 盘点里程点、最高点 / 坡顶、进度滑块、底部剖面图、2D / 3D 滑块、指南针、归北、自动旋转入口。
- 明确本轮不做 MapLibre + deck.gl 2D 路线诊断页。

### 验收

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

### 完成标准

- 基线审计报告能指导后续任务定位所有必须保留的交互入口。
- 测试或报告明确列出海拔墙待删除范围。
- 本任务不修改 `track.html` 生产行为。

### 非目标

- 不升级 Cesium。
- 不新增 DEM。
- 不删除海拔墙。

---

## 4. CDEM-01：Cesium 1.143 本地资源升级

优先级：P0
状态：`Completed`
性质：前端本地依赖 / 资源替换
前置：CDEM-00

### 目标

将轨迹分析工具本地 Cesium 资源升级到 `1.143` 方向，并保持本地自托管资源结构可被 pywebview 页面加载。

### 允许改动文件

- `lib/Cesium/**`
- `.gitattributes`，仅限为 `lib/Cesium/**` 配置第三方构建产物 whitespace 检查边界
- `track.html` 中 Cesium 版本引用、fallback 文案和资源路径相关代码
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`
- `tests/test_track_cesium_dem_contract.py`

### 必做

- 使用官方 `cesium@1.143` 构建产物替换或更新本地 `lib/Cesium`。
- 保持 `window.CESIUM_BASE_URL` 指向本地资源。
- 确认 `Cesium.js`、Workers、Assets、Widgets CSS 都能从本地加载。
- 移除或收敛与旧版本不一致的 CDN fallback，避免本地 `1.143` 与 CDN `1.105.1` 混用。
- 记录升级前后 `lib/Cesium` 体积差异。

### 验收

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

### 完成标准

- 本地 Cesium 资源可被页面引用。
- 版本引用不再混杂旧版。
- 安装包潜在增量有记录。

### 非目标

- 不接入 DEM provider。
- 不改轨迹渲染。
- 不删除海拔墙。

---

## 5. CDEM-02：Viewer 初始化兼容

优先级：P0
状态：`Completed`
性质：前端 Cesium runtime 兼容
前置：CDEM-01

### 目标

确认 Cesium `1.143` 下现有 viewer 初始化、相机、底图、事件绑定和渲染循环正常运行。

### 允许改动文件

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- 可新增浏览器 / pywebview 手测记录文档

### 必做

- 适配 `new Cesium.Viewer(...)` 初始化参数。
- 确认现有 CARTO 或标准底图仍能显示。
- 确认 `EllipsoidTerrainProvider` 或标准地形 fallback 可用。
- 确认 `setupViewerInteractions()` 在新版本下不报错。
- 保护 2D / 3D 滑块的 `lookAt` 与 `lookAtTransform(Cesium.Matrix4.IDENTITY)` 释放链路。
- 确认 `requestSceneRender()`、相机 changed 监听、指南针同步正常。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

### 手测

- 打开轨迹分析工具，Cesium canvas 非空。
- 导入或加载一条真实户外轨迹。
- 拖动 2D / 3D 滑块后地图仍可平移、缩放、旋转。
- 点击归北后相机正常。

### 完成标准

- 无 DEM 情况下，现有轨迹分析页可正常运行。
- Cesium 升级未破坏基本相机控制。

### 非目标

- 不新增真实地形图层 UI。
- 不修改活动数据。

### CDEM-02 完成记录

- Cesium 1.143 `Viewer` 源码核对确认：旧 `options.imageryProvider` 只会阻止默认底图，不会把自定义 provider 加入 `scene.imageryLayers`。
- `track.html::initCesiumViewer()` 已改为 `baseLayer: standardBaseLayer`，其中 `standardBaseLayer = new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider(...))`。
- 标准地形仍为 `new Cesium.EllipsoidTerrainProvider()`，未接入 DEM provider。
- `setupViewerInteractions()`、`requestSceneRender()`、camera `changed` 监听、指南针同步和 2D / 3D 滑块 `lookAtTransform(Cesium.Matrix4.IDENTITY)` 释放链路保持不变。
- 已更新 `tests/test_track_cesium_dem_contract.py`，防止 Viewer options 回退到旧 `imageryProvider:`。
- 验证通过：Cesium API module probe、`tests/test_track_cesium_dem_contract.py`、`git diff --check`。

---

## 6. CDEM-03：地形图层开关

优先级：P0
状态：`Completed`
性质：前端 UI / 状态机
前置：CDEM-02

### 目标

新增独立地形图层控制，让用户主动在标准地形与真实地形之间切换。该开关不得与 2D / 3D 视角滑块耦合。

### 允许改动文件

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- 可新增前端静态语义测试

### 必做

- 新增图层入口，建议文案为 `图层`、`标准地形`、`真实地形`。
- 默认选择标准地形。
- 点击真实地形后进入 loading 状态，例如 `真实地形 · 加载中`。
- 加载失败时回退标准地形。
- 2D / 3D 滑块不触发 DEM 下载、不切换 terrain provider。
- 2D 状态下真实地形开关可以保留或弱化，但不能改变滑块语义。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py
git diff --check
```

### 完成标准

- 图层控制与视角控制在代码和交互上分离。
- 没有弹窗确认。
- 没有默认下载 DEM 的路径。

### 非目标

- 不实现长期缓存。
- 不实现离线地形包。

### CDEM-03 完成记录

- 轨迹顶栏新增独立 `图层` 控件，提供 `标准地形` 和 `真实地形` 两个选项。
- 默认状态为 `standard / idle`，且 Cesium 初始化完成后同步控件状态。
- 真实地形点击路径进入 `loading`；CDEM-04 尚未提供 session cache / provider 时，显式回退到椭球标准地形，并通过轻量 toast 提示。
- 2D / 3D 滑块监听只调用相机 `lookAt`，静态测试确认其不调用任何地形图层函数。
- 未引入 DEM provider、下载、缓存、后端 API、数据库写入或活动事实改写。
- 聚焦验证通过：`12 passed`，`git diff --check` 通过。

---

## 7. CDEM-04：DEM 会话临时缓存

优先级：P0
状态：`Completed`
性质：缓存生命周期 / 本地存储边界
前置：CDEM-03

### 目标

实现 DEM 会话临时缓存。用户主动选择真实地形后，脉图只下载当前路线附近 DEM，退出程序后删除，启动时清理上次异常退出残留。

### 允许改动文件

- `main.py` 或当前 pywebview API 所在文件
- `track_backend.py`，仅当 DEM 范围计算需复用轨迹工具函数
- `track.html`
- 可新增 `tests/test_track_dem_session_cache.py`
- `docs/js_api_contract.json`，仅当新增前后端 API 合同

### 必做

- 定义 DEM session 目录，例如 `~/Library/Application Support/FitVault/cache/dem-session/{session_id}/`。
- 启动时清理非当前 session 的旧 DEM 目录。
- 退出时清理当前 session DEM 目录。
- 根据当前轨迹 bbox 外扩少量缓冲区估算 DEM 下载范围。
- DEM 临时文件不得写入活动数据库。
- DEM 下载失败必须可回退标准地形。
- 不做长期缓存、不做 LRU、不做缓存上限 UI。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py
jq empty docs/js_api_contract.json
git diff --check
```

### 手测

- 选择真实地形后生成 session DEM 目录。
- 退出程序后 session DEM 目录被删除。
- 模拟异常残留后，下次启动清理旧目录。

### 完成标准

- DEM 存储不会随使用累积。
- 首次启动不下载 DEM。
- 用户未选择真实地形时不创建 DEM 下载任务。

### 非目标

- 不做永久离线 DEM。
- 不做缓存管理设置页。

### CDEM-04 完成记录

- 新增 `DemSessionCache`，缓存根目录为 `~/.fitvault/cache/dem-session/`，与活动数据库和 `~/.fitvault/workspace/tracks/` 隔离。
- `Api` 构造时只清理旧 `session_*` 残留，不创建当前目录；当前目录只在用户点击 `真实地形` 后由 `prepare_dem_session_cache(points_json)` 创建。
- route bbox 使用有效 GPS 经纬度和固定 `1500m` 缓冲区生成，仅写入当前 session 的 `route-bbox.json`；不下载 DEM、不切换 provider、不返回本地路径，也不写活动数据库。
- `main()` 的退出 `finally` 调用 `api.cleanup_dem_session_cache()`，删除当前 session 目录；AI 使用的 `_session_id` 与 DEM 应用会话 ID 保持分离，避免轨迹 / AI 会话刷新造成清理遗漏。
- `track.html` 的真实地形点击会先预备 DEM session cache，随后仍受控回退标准地形，正式 provider 接入留给 CDEM-05。
- 聚焦验证通过：`18 passed`、`jq empty docs/js_api_contract.json`、`git diff --check`。

---

## 8. CDEM-05：真实地形轨迹贴合与语义轨迹保留

优先级：P0
状态：`Completed`
性质：轨迹渲染 / terrain provider 集成
前置：CDEM-03, CDEM-04

### 目标

在真实地形图层下显示轨迹与地形关系，同时保留当前进度切片、完成 / 未完成轨迹分段和语义轨迹样式。

### 允许改动文件

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- 可新增轨迹渲染聚焦测试

### 必做

- 在标准地形下保持当前轨迹渲染行为。
- 在真实地形下使用贴地或近地显示策略。
- 保留 completed / remaining track entity 和进度切片。
- 保留 CP 点、里程点、最高点 / 坡顶标记的显示高度策略。
- 不用 DEM 改写 FIT 海拔或统计口径。
- 保护底部海拔剖面图的数据来源和联动。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_thumbnail_canvas_v4.py
git diff --check
```

### 手测

- 标准地形下拖动进度滑块，完成 / 未完成轨迹分段正常。
- 真实地形下拖动进度滑块，完成 / 未完成轨迹分段正常。
- CP、里程、最高点 / 坡顶标记不被地形遮挡到不可用。

### 完成标准

- 真实地形只是显示层，不改变活动事实。
- 语义轨迹能力不因 terrain provider 切换丢失。

### 非目标

- 不做高程差异诊断。
- 不做 MapLibre 2D 诊断。

### CDEM-05 完成记录

- 默认在线 DEM provider 采用 ArcGIS World Elevation：`Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(ARCGIS_WORLD_ELEVATION_TERRAIN_URL)`。
- `loadRealTerrainLayerForCurrentTrack()` 保留 CDEM-04 的 `prepare_dem_session_cache(JSON.stringify(appState.points))` 作为用户动作前置边界；只有用户点击 `真实地形` 才创建 provider。
- 标准地形仍使用 `new Cesium.EllipsoidTerrainProvider()`，并通过 `refreshTerrainSensitiveScene()` 在图层切换后重建 scene entity。
- 真实地形 ready 时，completed / remaining 轨迹保留 `CallbackProperty` 和 `appState.progress` 切片，并设置 `clampToGround: useRealTerrain`。
- CP、里程点、最高点 / 坡顶在真实地形下使用 `Cesium.HeightReference.RELATIVE_TO_GROUND` 与小高度偏移；标准地形下保持既有 FIT 海拔夸张高度策略。
- 海拔墙未在本任务删除，但真实地形 ready 时不显示，避免与 DEM 地形混淆；彻底删除留给 CDEM-06。
- 未使用 DEM 改写 FIT 海拔、累计爬升、最高海拔、底部剖面图、复盘或 AI 输入。
- 聚焦验证通过：`19 passed`、缩略图相关测试 `32 passed`、`git diff --check`。

---

## 9. CDEM-06：海拔墙彻底退役

优先级：P0
状态：`Completed`
性质：删除冗余功能 / 防混淆
前置：CDEM-05

### 目标

彻底删除海拔墙作为产品和内部能力的所有活跃实现，确保底部半透明海拔剖面图成为唯一海拔剖面表达。

### 允许改动文件

- `track.html`
- 与海拔墙断言直接相关的测试
- `docs/轨迹分析工具_Cesium_DEM_POC_基线审计报告.md`

### 必做

- 删除 wall entity 创建、更新和销毁逻辑。
- 删除海拔墙相关状态变量。
- 删除海拔墙相关 CSS。
- 删除海拔墙相关 UI、开关、说明和注释。
- 删除或更新测试中的海拔墙断言。
- 确认删除没有误伤 full positions、altitude arrays、progress slicing、profile chart。

### 验收

```bash
rg -n "wallEntity|elevation wall|海拔墙|wall\\.wall|Cesium\\.Wall" track.html tests
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_thumbnail_canvas_v4.py
git diff --check
```

### 完成标准

- 用户界面无海拔墙入口。
- 代码中无活跃 wall entity。
- 无内部调试开关或隐藏兼容路径。
- 底部剖面图仍正常显示和联动。

### 非目标

- 不删除底部海拔剖面图。
- 不删除轨迹海拔事实。

### CDEM-06 完成记录

- `track.html` 已删除 `wallEntity`、`海拔剖面堆积墙` 点击命中、wall entity 创建 / 删除、`wallColor`、`fullMaxHeights` 和 `fullMinHeights`。
- `appState.fullPositions` 保留，completed / remaining 轨迹继续使用 `CallbackProperty` 和 `appState.progress` 维护分段。
- 底部半透明剖面图、`drawProfileChart()`、`profile-canvas` 点击新增 CP 联动均保留。
- CP、里程点、最高点 / 坡顶、2D / 3D 滑块、ArcGIS 真实地形 provider 和 DEM session cache 均未删除。
- grep 验收无 `wallEntity`、`elevation wall`、`海拔墙`、`海拔剖面堆积墙`、`wall.wall`、`Cesium.Wall` 残留。
- 聚焦验证通过：`51 passed`、`git diff --check`。

---

## 10. CDEM-07：既有分析交互回归

优先级：P0
状态：`Completed`
性质：功能回归 / 不新增产品能力
前置：CDEM-06

### 目标

系统性验证并修复 Cesium 升级、DEM 图层和海拔墙删除后所有既有轨迹分析交互。

### 允许改动文件

- `track.html`
- 与轨迹分析交互直接相关的测试
- 可新增手测清单或回归报告

### 必做

- 验证 CP 点展示。
- 验证 CP 点新增。
- 验证 CP 点编辑。
- 验证里程点展示和开关。
- 验证最高点 / 坡顶标记展示和开关。
- 验证进度滑块和轨迹进度切片。
- 验证底部剖面图点击 / 定位联动。
- 验证 2D / 3D 滑块。
- 验证指南针 / 归北。
- 验证自动旋转，若该入口仍保留。
- 验证活动详情页轨迹缩略图跳转轨迹分析工具。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
git diff --check
```

### 手测

- 使用城市跑、山地 / 越野跑、骑行爬坡各一条真实轨迹。
- 每条轨迹在标准地形和真实地形下均执行完整点检。

### 完成标准

- 既有轨迹分析交互无丢失。
- 如存在因 Cesium 升级导致的交互差异，必须记录并给出处理结论。

### 非目标

- 不新增路线诊断 Tab。
- 不扩展 CP 数据模型。

---

## 11. CDEM-08：安装包、网络和存储验收

优先级：P1
状态：`Planned`
性质：发布门禁 / 性能与资源
前置：CDEM-07

### 目标

确认 Cesium 升级和 DEM POC 不显著增加安装包压力，不造成长期本地存储累积，不因网络失败阻断轨迹分析工具。

### 允许改动文件

- 可新增 `docs/轨迹分析工具_Cesium_DEM_POC_资源验收报告.md`
- 与缓存清理或降级提示直接相关的代码
- 相关聚焦测试

### 必做

- 记录升级后 `lib/Cesium` 体积。
- 记录安装包潜在增量。
- 确认 DEM 不进入安装包。
- 确认首次启动不下载 DEM。
- 确认用户选择真实地形才下载 DEM。
- 确认 DEM session cache 不写数据库。
- 模拟 DEM 服务不可用，确认可回退标准地形。
- 验证退出清理和启动清理。

### 验收

```bash
du -sh lib/Cesium
find lib/Cesium -type f | wc -l
.venv312/bin/python -m pytest -q tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py
git diff --check
```

### 完成标准

- 存储策略符合交付手册：会话临时缓存，退出删除，启动清理残留。
- 网络失败不会阻断标准轨迹分析工具。
- 资源增量有明确记录。

### 非目标

- 不实现国内 DEM 服务选型终局方案。
- 不做长期离线包。

### CDEM-08 完成记录

- `lib/Cesium` 当前体积和文件数为 `22M / 392 files`，相对 CDEM-00 基线 `18M / 375 files` 潜在增量约 `+4M / +17 files`。
- ArcGIS World Elevation endpoint 当前探测通过：HTTP `200`，耗时约 `0.896565s`，下载 `8074` bytes。
- DEM 不进入安装包，不默认下载；真实地形只在用户点击 `真实地形` 后进入 `prepare_dem_session_cache(...)` 与 ArcGIS provider 创建路径。
- DEM session cache 仍为会话临时缓存：启动清理旧 session，用户动作后创建当前 session，退出清理当前 session。
- 网络失败回退标准地形：`applyStandardTerrainLayer('真实地形暂不可用')` 恢复 `EllipsoidTerrainProvider`。
- 验证通过：`tests/test_track_dem_session_cache.py tests/test_track_cesium_dem_contract.py`、`git diff --check`。

---

## 12. CDEM-09：POC 总验收与交付报告

优先级：P0
状态：`Planned`
性质：全链路验收 / 发布结论
前置：CDEM-08

### 目标

完成本次 POC 的全链路验收，输出可交付结论，明确是否进入后续正式开发或继续修正。

### 允许改动文件

- 可新增 `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- 必要的测试期望更新

### 必做

- 汇总 CDEM-00 到 CDEM-08 的执行结果。
- 汇总城市跑、山地 / 越野跑、骑行爬坡三类真实轨迹验收。
- 汇总 CP、里程、最高点 / 坡顶、进度、剖面、相机、跳转的回归结果。
- 汇总海拔墙退役确认。
- 汇总安装包、DEM 下载和临时缓存清理结果。
- 明确未完成项、风险和后续建议。

### 验收

```bash
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
git diff --check
```

### 完成标准

- POC 结果有完整交付报告。
- 所有 P0 回归项有明确通过、失败或延期结论。
- 失败项不得被包装成已完成。

### 非目标

- 不创建中期 MapLibre + deck.gl 开发任务。
- 不发布正式长期 DEM 缓存能力。

### CDEM-09 完成记录

- 开发完成报告已落盘：`docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`。
- 最终自动化回归通过：`tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py` 共 `161 passed`。
- `git diff --check` 通过。
- 海拔墙残留 grep 无命中。
- 城市跑、山地 / 越野跑、骑行爬坡真实桌面 UI 点检尚未执行，已明确列为发布前手测，不包装为通过。
- 交付结论：自动化总验收通过，可进入真实 UI smoke；正式发布前必须补齐真实轨迹和网络失败回退点检。

## 13. 后续交接提示

后续开发 Agent 启动时必须先读：

1. `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
2. `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
3. CDEM-00 产出的基线审计报告
4. `track.html` 中 Cesium 初始化、相机控制、轨迹 entity、CP 点、里程点、最高点 / 坡顶、进度滑块和底部剖面图相关代码

启动提示：

```text
请严格按 docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md 执行。
本轮目标是 Cesium 升级、真实 DEM 地形 POC、DEM 会话临时缓存、海拔墙彻底退役。
不得改写 FIT/手表海拔事实，不得引入 MapLibre + deck.gl，不得丢失 CP 点、里程点、最高点/坡顶、进度滑块、底部剖面图、2D/3D 滑块等既有能力。
每项任务开始前检查 dirty worktree，每项任务结束后运行聚焦测试和 git diff --check。
```

---

## 14. CDEM-10：顶部工具栏响应式可达性修复

优先级：P1
状态：`Completed`
性质：前端布局 / 既有入口可达性
前置：CDEM-09 自动化验收

### 目标

修复轨迹分析工具顶栏在中小桌面窗口下被裁切的问题，保证所有已存在的地图工具均可发现、聚焦和操作。

### 允许改动文件

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_10_工程提示词.md`
- 本任务清单的状态与完成记录

### 必做

- 按统计、视角、地形、主动作、次级动作、标记显隐、进度重组顶栏语义组。
- 宽屏完整显示；中等宽度压缩统计与次级动作并以逻辑行换行；窄屏将次级动作放入可键盘访问的真实“更多”菜单。
- 不得依赖隐藏横向滚动条承载功能；不得用 `display:none` 丢失任一既有工具入口。
- 保护既有控件 ID、inline handler 和绑定：归北、2D / 3D、标准 / 真实地形、导入、剖面、漫游、导出、CP / 里程 / 坡顶和进度。
- 不修改 Cesium、DEM、海拔墙退役、FIT / 手表海拔事实或后端接口。

### 验收

```bash
node --check /tmp/fitvault_track_inline.js
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py
git diff --check
```

### 手测

- 约 1440px、1180px、960px 宽的桌面窗口下，顶栏没有被裁切。
- 次级动作菜单可用鼠标和键盘打开，剖面、漫游、导出仍可触发。
- 归北、2D / 3D、地形切换、标记开关、进度滑块和导入入口仍可操作。

### 完成标准

- 不再存在仅能靠不可见横向滚动访问的顶栏控件。
- 自动化合同、JavaScript 语法和 diff 检查全绿。
- 手测未执行时明确保留为待点检，不包装为通过。

### 完成记录

- 顶栏已按统计、视角、地形、主动作、次级动作、标记显隐和进度分组；删除依赖不可见横向滚动的单行布局。
- 宽屏完整单行；1180px / 960px 自动逻辑换行且无横向溢出；900px 以下提供真实“更多轨迹工具”菜单，次级动作可点击、Esc 关闭且操作后自动收起。
- 原有归北、2D / 3D、标准 / 真实地形、导入、剖面、漫游、导出、CP / 里程 / 坡顶和进度入口保留，未改动相机、terrain provider、DEM cache 或活动事实逻辑。
- 验证通过：CDEM 完整聚焦回归组 `166 passed`、`node --check /tmp/fitvault_track_inline.js`、`git diff --check`。浏览器实测覆盖 1440px、1180px、960px 和 880px；真实活动数据下的发布前 UI smoke 仍待 CDEM-09 门禁补齐。

---

## 15. CDEM-11：顶栏统计与视角组防重叠修复

优先级：P1
状态：`Completed`
性质：前端布局回归修复
前置：CDEM-10

### 目标

修复真实统计值变长时，路线统计胶囊溢出统计组并覆盖归北按钮、2D / 3D 滑块的问题。

### 允许改动文件

- `track.html`
- `tests/test_track_cesium_dem_contract.py`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_CDEM_11_工程提示词.md`
- 本任务清单状态与完成记录

### 必做

- 统计组不得收缩到其不可收缩子项的内容宽度以下。
- 空间不足时按语义组换行，不能让统计子项越界覆盖视角组。
- 长统计值场景下，统计组与视角组矩形不得相交。
- 保留归北、2D / 3D、地形、导入、次级动作、标记开关和进度入口及其原有行为。
- 不修改数据、地图、DEM、相机或后端逻辑。

### 验收

```bash
node --check /tmp/fitvault_track_inline.js
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py
git diff --check
```

### 完成标准

- 静态合同锁定统计组不可缩水边界。
- 浏览器长统计值 / 临界宽度扫描无矩形相交、无横向裁切。
- CDEM 完整回归、JS 语法和 diff 检查全绿。

### 完成记录

- 统计组改为 `flex: 1 0 auto; min-width: max-content`，禁止父组缩水后让长统计内容越界。
- 长值夹具在 1440、1180、1040、960px 实测均无统计 / 视角矩形相交，统计组与顶栏均无横向溢出。
- 归北、2D / 3D、地形、导入、剖面、漫游、导出、标记开关和进度入口保持原行为；未修改相机、terrain provider、DEM cache、FIT / GPX 或 DB。
- 验证通过：完整 CDEM 回归 `166 passed`、JS 语法检查、`git diff --check`。临时夹具已清理。

---

## 16. CDEM-12：地形切换相机一致性修复

优先级：P0
状态：`Planned`
性质：相机状态 / terrain provider 异步切换 / 既有交互回归
前置：CDEM-09
详细任务源：`docs/轨迹分析工具_地形切换相机一致性修复任务清单.md`

### 目标

保留现有 2D / 3D slider 与标准 / 真实地形图层的职责分工，在 terrain provider、高度基准和贴地渲染切换后，保持同一屏幕中心地理焦点、相机姿态、slider 值和近似相同屏幕尺度，消除视觉跳跃。

### 边界

- 不合并 slider 与 terrain provider 语义。
- 不重新 framing 路线，不调用 `flyToBoundingSphere` 适配轨迹。
- 不改变 DEM provider、缓存、垂直夸张、hillshade、贴地轨迹和 marker 高度产品参数。
- 不修改 FIT / GPX、DB、剖面、统计、复盘或 AI 事实。

### 完成标准

- 详细清单 CTCAM-00 至 CTCAM-07 依序完成且门禁全绿。
- 标准→真实、真实→标准、失败回退和快速反向切换均满足相机量化合同。
- 2D、中间角度、3D 三种 slider 状态均完成自动化与真实桌面 UI 验收。

### 真实打包环境补充证据

- 2026-08-03：用户在打包后的 DMG 中实测，反馈切换标准 / 真实地形时相机视角变化不大，当前结果可接受。
- 该证据仅覆盖用户实际测试到的打包环境和场景，不能替代 CTCAM-00 至 CTCAM-07 要求的完整真实 UI 验收矩阵，因此 CDEM-12 状态暂不改为 `Completed`。

---

## 17. CDEM-13：真实地形标记清晰度修复

优先级：P0
状态：`Planned`
性质：Cesium billboard / label / HiDPI / WebView 视觉回归
前置：CDEM-05
详细任务源：`docs/轨迹分析工具_真实地形标记清晰度修复任务清单.md`

### 目标

分别修复真实地形下 CP canvas billboard、最高点 / 坡顶 billboard 和里程 point + label 的模糊问题，在不同 DPR、相机距离和 2D / 3D 视角下保持清晰、稳定且不过度遮挡。

### 边界

- 不恢复 SVG text / filter / emoji billboard。
- 不以统一放大 marker 代替清晰度修复。
- 不在未完成兼容与性能 POC 前恢复 FXAA、提高 MSAA 或全局 resolution scale。
- 不修改 marker 业务语义、CP 编辑、里程层级、最高点优先级、DEM、相机、FIT / GPX 或 DB。

### 完成标准

- 详细清单 MCLR-00 至 MCLR-07 依序完成且门禁全绿。
- Retina / 非 Retina、近中远距离、2D / 中间 / 3D 均有像素和真实 UI 证据。
- CP、里程、最高点功能和 declutter 合同保持通过。

---

## 18. CDEM-14：高密度轨迹加载性能优化

优先级：P0
状态：`Implementation Complete / User Manual Acceptance Pending`
性质：轨迹加载链路 / WebView bridge / Cesium 首屏性能
前置：CDEM-13 规划完成；生产实现前必须先完成 PLOAD-00 基线测量
详细任务源：`docs/轨迹分析工具_轨迹加载性能优化任务清单.md`
工程提示词：`docs/轨迹分析工具_Cesium_DEM_POC_CDEM_14_工程提示词.md`

### 当前问题证据

- “四姑娘山二峰登顶”活动（activity `127`）包含 `26,052` 个轨迹点，track JSON 约 `9.3 MB`。
- “长坪沟到四姑娘山二峰大本营徒步”活动（activity `907`）包含 `21,690` 个轨迹点，track JSON 约 `7.9 MB`。
- 本地后端 `load_activity_track` 读取约 `0.05–0.07s`，主要瓶颈待在真实 DMG 中通过分段计时确认。
- 当前 `haversine()` 在每次调用时执行 `console.warn()`；高密度 canonical 距离循环和峰顶邻域扫描可能产生大量重复日志，列为首要低风险修复项。

### 目标

降低高密度轨迹从活动选择到地图、指标和剖面可操作的首屏等待，且不丢失 CP、里程、最高点 / 坡顶、进度、剖面和相机能力。

### 边界

- 不改 FIT / GPX、DB、统计、复盘、AI 或活动事实。
- 不用显示抽稀结果改写原始 points 或事实指标。
- 不改变 2D / 3D slider 与标准 / 真实地形图层的职责分工。
- 不改变 DEM provider、session cache 生命周期和 CDEM-12 相机合同。

### 完成标准

- 详细清单 PLOAD-00 至 PLOAD-06 依序完成且测试与 diff review 全绿。
- PLOAD-00 已完成：真实 activity `127` / `907` 的前端热循环、逐次日志、payload 和固定相机路径已形成基线；下一项为 PLOAD-01 热循环与峰顶检测优化。
- PLOAD-01 已完成：高密度轨迹 stats / peak 探针下降约 `61–68%`，warning count 降为 `0`，四条真实轨迹的 km / peak marker 语义与位置保持一致；下一项为 PLOAD-02 canonical 重复传输优化。
- PLOAD-02 已完成：canonical context payload 对 activity `127` / `907` 分别减少 `99.992%` / `99.996%`，temporary points 和 activity advice 事实合同保持；下一项为 PLOAD-03 相机与非关键工作调度。
- PLOAD-03 已完成：首屏 / 后台分层、render revision 和可中断 `0.8s` 初始相机定位落地。
- PLOAD-04 已完成：基于中期数据决定不采用显示几何抽稀，不引入双轨迹结构。
- PLOAD-05 已完成：标准 / 真实地形成本隔离，真实地形阶段快照和有界 tile listener 落地。
- PLOAD-06 实现与自动化完成：轨迹专项 `212 passed`，全仓 `3505 passed, 5 skipped, 262 subtests passed`，当前源码打包 app 启动成功；用户手动验收待回填。
- PLOAD-01 至 PLOAD-03 后必须复测；达到目标时 PLOAD-04 以“不采用显示抽稀”的证据结论完成，不强行引入双轨迹结构。
- 高密度轨迹首屏交互等待相对 PLOAD-00 基线下降至少 `30%`。
- 真实 DMG 覆盖四姑娘山高密度轨迹、城市跑、山地 / 越野跑和骑行轨迹；未执行场景不得写成通过。
- CP 编辑、里程 1/5/10km、最高点优先级、进度切片、底部剖面联动和 CDEM-12 相机体验保持通过。
- CDEM-14 在用户完成真实 UI 手测并确认首屏体验前，不标记最终产品验收完成。
