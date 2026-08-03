# PLOAD-06 工程级提示词

> 任务：自动化性能合同与真实 UI 验收
> 生成时间：2026-08-03
> 执行模式：task-loop-runner 最终门禁

## 0. Contract Refresh

执行前刷新契约摘要，复读交付手册、主 CDEM 清单、性能任务清单、PLOAD-00 至 PLOAD-05 报告、CDEM-12 / CDEM-13 契约，以及当前 canonical 加载入口、`applyDataAndRender()`、marker / progress / profile / terrain 源码和测试。保留 dirty worktree。

## 1. Goal

固化整个性能改造的自动化合同，提供可从真实桌面 WebView 读取的最近一次轨迹 / terrain 分段快照，并完成最大范围自动化、网络和可行的真实打包 UI 验收。

## 2. Scope

- 为 canonical `load_activity_track()` 建立统一前端计时包装，记录 bridge + decode，不重复序列化 response。
- 在 `applyDataAndRender()` 记录 stats / marker、bounds、Cesium scene、Canvas profile、CP list、首屏同步 ready、首帧后 background settle。
- 快照只保留最近一次，并受 render revision 保护；temporary 路径明确无 bridge。
- 新增统一性能合同测试，覆盖 PLOAD-01 至 PLOAD-05 和必须保留的交互。
- 运行大轨迹、城市跑、骑行探针和完整 CDEM / 详情回归。
- 启动打包 `脉图.app`，尝试真实活动切换、标准 / 真实地形和 marker / profile smoke；精确读不到的字段明确列待手测。
- 更新任务清单、契约摘要和最终完成报告。

## 3. Constraints

- 不为计时再次 stringify 大 response，不逐点 / 逐帧 console，不写 DB。
- 不改变 FIT / GPX、canonical metrics、AI、报告、CP / 里程 / 最高点、进度或剖面语义。
- 不实施 PLOAD-04 显示抽稀，不改变 provider、cache、hillshade、marker 或相机产品参数。
- 计时异常不能阻断活动加载；旧 revision 不能覆盖新路线快照。
- 真实 UI 只能陈述实际观察结果；自动化、curl、Python 探针和 DMG smoke 证据分栏记录。
- 如最终 review 发现跨任务语义偏离，重新全文阅读所有权威文档并按 review 修复门禁处理。

## 4. Expected Files

- `track.html`
- `tests/test_track_load_performance_contract.py`
- 直接相关既有测试
- `scripts/profile_track_load.py`（仅在需要补只读字段时）
- 契约摘要、性能任务清单、PLOAD-06 / CDEM-14 完成报告

禁止修改 DB、FIT / GPX parser、provider 选型、DEM cache 实现和无关功能。

## 5. Validation

```bash
.venv312/bin/python -m pytest -q tests/test_track_load_performance_contract.py tests/test_track_load_profile_probe.py tests/test_activity_advice_frontend.py tests/test_activity_advice_integration.py tests/test_track_cesium_dem_contract.py tests/test_track_dem_session_cache.py tests/test_track_html_sync_logic.py tests/test_track_thumbnail_canvas_v4.py tests/test_v9_0_detail_tab_review.py
.venv312/bin/python scripts/profile_track_load.py --activity-id 127 --activity-id 907 --activity-id 1117 --activity-id 1094
node --check /tmp/fitvault_track_inline.js
jq empty docs/js_api_contract.json
git diff --check
```

随后运行项目中与轨迹详情直接相关的最广泛可行回归，并启动打包 app 做真实 UI smoke。

## 6. Completion Definition

- PLOAD-01 至 PLOAD-05 合同由统一测试覆盖，必须保留交互回归全绿。
- 最近一次 track / terrain 性能快照可读取且不会重复传输大 payload。
- activity `127` / `907` 与普通城市跑 / 骑行探针通过，marker 语义不变。
- JS、API JSON、完整回归、diff check 和累计 review 全绿。
- 真实 app 已启动并记录实际可验证项；无法自动读取的真实 UI 分段明确列为发布前手测，不冒充通过。
- PLOAD-00 至 PLOAD-06 状态与报告一致后，CDEM-14 才可标记完成。
