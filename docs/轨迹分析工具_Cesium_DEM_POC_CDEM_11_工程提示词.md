# CDEM-11 工程级提示词

> 任务：顶栏统计与归北 / 2D / 3D 视角组防重叠修复
> 生成时间：2026-07-31
> 执行模式：task-loop-runner 门禁循环

## 0. 契约核对

执行前读取并刷新：`.trae/rules/fit-arch-contrac.md`、CDEM 开发交付手册、任务清单、契约摘要、开发完成报告、CDEM-10 工程提示词、`track.html` 顶栏 CSS / HTML 和 CDEM 静态合同测试。

本轮确认：只允许修复顶栏布局；不得改活动事实、统计值、FIT / GPX、数据库、DEM provider / cache、Cesium entity、相机逻辑、地形切换或海拔墙退役状态。dirty worktree 中无关修改必须保留。

## 1. Goal

确保真实统计值变长时，统计组始终拥有完整内容宽度；窗口空间不足时让后续视角组整体换行，杜绝统计胶囊覆盖归北按钮或 2D / 3D slider。

## 2. Root Cause

`.topbar-stats { flex: 1 1 280px; }` 允许收缩，且共享分组规则设置 `min-width: 0`；其内部 `.mini-stat` 为 `flex: 0 0 auto`、`white-space: nowrap`。真实值增长后，统计子项总宽度可大于父组缩水宽度，并因顶栏 `overflow: visible` 绘制到相邻视角组上。

## 3. Scope And Constraints

- 统计组使用内容安全的 flex / min-width 约束，禁止缩到子项总宽度以下。
- 保持 `.panel-inner` 分组换行，不引入绝对定位或负 margin。
- 视角组、归北和 slider 不隐藏、不缩放、不改事件。
- 保留 CDEM-10 更多菜单及全部工具 ID / handler。
- 测试必须锁定统计组防收缩规则，并验证所有入口仍存在。

## 4. Validation

```bash
node --check /tmp/fitvault_track_inline.js
.venv312/bin/python -m pytest -q tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
git diff --check
```

浏览器验收：使用代表性长值（如 `123.45 km`、`12:34:56`、`12345 m`、`8848 m`）扫描临界窗口宽度，确认 `.topbar-stats` 的 `scrollWidth <= clientWidth`，并且统计组与 `.topbar-view-controls` 的可见矩形不相交。

## 5. Completion Definition

- 长值不会越出统计组并覆盖视角控件。
- 空间不足时按完整语义组换行。
- 自动化与浏览器布局验收全绿。
- 任务清单和契约摘要回填实际证据。

## 6. Reread Triggers

如需隐藏或重写视角控件、改变统计展示值、修改 terrain provider / 相机 / 后端，或测试暴露跨 CDEM 合同冲突，必须暂停并重新全文阅读相关原始合同。
