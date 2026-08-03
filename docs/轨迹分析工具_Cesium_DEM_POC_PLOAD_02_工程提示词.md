# PLOAD-02 工程级提示词

> 任务：canonical 轨迹 bridge 与重复序列化优化
> 生成时间：2026-08-03
> 父任务：CDEM-14
> 前置：PLOAD-01 `Completed`

## Goal

让 canonical activity 在首次 Python → WebView 完整轨迹加载后，不再通过 `sync_track_context()` 将同一完整 points JSON 重复传回 Python，同时保留临时轨迹和 activity advice 事实合同。

## Scope

允许：

- `track.html` 的 `syncCurrentTrackContextForActivityAdvice()` payload 构造。
- `tests/test_activity_advice_frontend.py`、`tests/test_activity_advice_integration.py`、性能探针测试。
- `docs/js_api_contract.json` 的 `sync_track_context` 描述。
- PLOAD-02 报告、契约摘要和任务状态。

禁止：

- 修改 DB、FIT / GPX、canonical metrics、活动详情 / 复盘、DEM、相机、marker 或海拔墙合同。
- 由前端重新计算 canonical activity advice facts。
- 删除临时 GPX / KML / FIT points 回传。

## Contract

- `appState.persistenceMode === 'canonical_activity'` 且存在 `currentActivityId` 时，payload 不包含 `points` 键。
- 临时 session payload 继续包含 `points: appState.points`，后端可构建 `temporary_track_context`。
- 两种 payload 都继续包含 placemarks、filename、weather、activityId 和 `activityAdviceRouteFacts`。
- backend `sync_track_context()` 保持 points 可选：canonical activity 从 `activityId` 构建 DB AI snapshot，activity advice 优先消费 overview route facts；temporary activity 使用 points 聚合路线事实。
- 不同时发送轻量和全量两条正常路径；异常失败只沿用现有 `.catch()`，不自动重发完整 canonical points。

## Validation

```bash
.venv312/bin/python -m pytest -q tests/test_activity_advice_frontend.py tests/test_activity_advice_integration.py tests/test_track_load_profile_probe.py tests/test_track_cesium_dem_contract.py
jq empty docs/js_api_contract.json
node --check /tmp/fitvault_track_inline.js
git diff --check
```

## Completion Definition

- activity `127` / `907` canonical context payload 不再包含约 `9.2MB` / `7.8MB` points。
- 临时轨迹 activity advice snapshot 仍来自 points，canonical snapshot 仍来自 DB / overview facts。
- 测试、JSON、JS 语法和 adaptive review 全绿后标记 PLOAD-02 `Completed`，再进入 PLOAD-03。
