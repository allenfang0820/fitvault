# CDEM-10 工程级提示词

> 任务：轨迹分析工具顶部工具栏响应式可达性修复
> 生成时间：2026-07-31
> 执行模式：task-loop-runner 门禁循环

## 0. 架构契约核对

执行前必须阅读并刷新：

- `.trae/rules/fit-arch-contrac.md`
- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发交付手册.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发任务清单.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_契约摘要.md`
- `docs/轨迹分析工具_Cesium_DEM_POC_开发完成报告.md`
- `track.html` 中顶栏 CSS / HTML、terrain provider、相机控制、顶栏绑定
- `tests/test_track_cesium_dem_contract.py`

刷新后确认：FIT / 手表海拔和活动统计仍是后端事实；DEM 仅是显示层；2D / 3D 只控制相机；海拔墙已退役；DEM session cache 与 provider 不在本任务范围；dirty worktree 必须保留。

## 1. Goal

修复顶部工具栏在不同窗口宽度下的裁切，使现有工具入口始终可访问，而不改变地图行为。

## 2. Scope

允许修改：`track.html` 的顶栏结构和 CSS、对应静态合同测试、本轮契约摘要、任务清单与本提示词。

禁止修改：FIT / GPX 解析、数据库、API、活动事实、DEM provider / 缓存、Cesium 相机或 entity 逻辑、海拔墙、MapLibre / deck.gl，以及所有无关 dirty 文件。

## 3. Implementation Requirements

- 将顶栏分为统计、视角、地形、主动作、次级动作、标记显隐和进度等语义组。
- 宽屏完整单行；中等宽度压缩统计、使用图标化次级动作并允许逻辑换行；窄屏将次级动作置入原生、可键盘操作的“更多”菜单。
- 禁止以隐藏滚动条、无提示溢出或 `display:none` 遗失功能来解决宽度问题。
- 保留以下 ID 与行为：`map-compass-btn`、`map-view-slider`、`terrain-layer-standard`、`terrain-layer-real`、`btn-auto-rotate`、`toggle-cp`、`toggle-km`、`toggle-peak`、`progress-slider`，以及导入、剖面、导出动作。
- 界面适配只影响显示和可达性；地形切换不得改相机、2D / 3D slider 或轨迹状态。

## 4. Validation

```bash
node --check /tmp/fitvault_track_inline.js
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py
git diff --check
```

手测：约 1440px、1180px、960px 宽桌面窗口，确认无裁切；在窄屏打开“更多”菜单，确认剖面、漫游、导出均能点击；确认地图视角、地形、标记和进度控制不变。

## 5. Completion Definition

- 顶栏不再依赖不可见横向滚动。
- 每个既有工具入口在对应宽度均可发现并操作。
- 聚焦测试、JS 语法检查和 `git diff --check` 通过。
- 未执行的桌面 UI 手测列为待点检。

## 6. Reread Triggers

出现以下任一情况，必须重新全文阅读上述交付手册、任务清单和契约摘要后再继续：需要修改控件行为或事件绑定；需要改变相机、terrain provider、DEM cache 或活动事实；测试合同与现有功能冲突；需要扩大到活动详情、复盘、导入或后端代码。
