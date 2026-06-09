# P0 运动复盘数据契约回正完成报告

## 1. 本次目标

- 使用 `docs/p0_fatigue_review_contract_prompt.md` 正式执行 P0 数据契约回正。
- 固化 `get_fatigue_review(activity_id)` 的权威 API 输出契约。
- 明确 `curves.distance` / `curves.time` / `curves.altitude` 等曲线字段由后端权威输出，前端不得重建事实距离轴。
- AI 洞察、算法链路回正和草图 UI 还原不在本阶段处理。

## 2. 修改文件

- `docs/js_api_contract.json`
- `main.py`
- `tests/test_fatigue_review_contract_realignment.py`
- `tests/test_fatigue_review_e2e_contract.py`

## 3. 契约变更

- 修正 `docs/js_api_contract.json` 中 `get_fatigue_review` 的 `line` 为当前 `main.py` 实际入口行号。
- 扩展 `returns`，新增并明确：
  - `curves.distance`：后端权威距离轴，单位 km。
  - `curves.time`：后端权威时间轴，单位 sec。
  - `curves.altitude`：后端权威海拔曲线。
  - `curves.total_distance_m`：活动总距离，单位 m。
- 在契约中明确前端零推断：前端不得通过 `_distanceFromSpeedTime` 或 points 重建事实距离轴。
- 在契约中明确 `fatigue_zones.start_km/end_km`、`collapse_events.trigger_km` 必须与 `curves.distance` 同源。
- 在契约中明确 `shadow_diff`、`shadow_diff_json`、`diff`、`records`、全量 points 禁止进入复盘 API data。
- 在描述中明确 AI 洞察 `__FATIGUE_REVIEW_INSIGHT__` 留到 P6。

## 4. 后端空态变更

- `_empty_fatigue_review_snapshot()` 的 `curves` 补齐：
  - `distance: []`
  - `time: []`
  - `altitude: []`
- `_build_fatigue_review_snapshot()` 正常返回路径的 `curves` 同步补齐上述 P0 占位字段。
- 本阶段仅补齐契约字段，不实现真实距离、时间、海拔算法输出。

## 5. 测试变更

- 新增 `tests/test_fatigue_review_contract_realignment.py`，覆盖：
  - API 契约声明后端权威曲线字段。
  - API 契约声明前端零推断。
  - API 契约禁止 debug/raw 字段。
  - API 契约标记 AI 洞察留到 P6。
  - 后端空态快照包含 P0 曲线字段。
  - 后端空态快照不包含 forbidden 字段。
- 更新 `tests/test_fatigue_review_e2e_contract.py`，把 `distance`、`time`、`altitude` 纳入 curves 白名单样例。

## 6. 验证结果

验证命令：

```bash
python -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
exit_code = 0
```

诊断结果：

- `main.py`：无新增诊断。
- `tests/test_fatigue_review_contract_realignment.py`：无新增诊断。
- `tests/test_fatigue_review_e2e_contract.py`：无新增诊断。
- `docs/js_api_contract.json`：存在既有远程 schema 404 警告，与本次修改无关。

## 7. 未处理事项

- P1 算法链路回正：真实 `distance_curve / altitude_curve / time / calories / sport_type` 来源梳理与 Resolver 输出改造。
- P2 后端快照封装：将 P1 算法输出接入 `get_fatigue_review`。
- P3/P4 前端最小展示与草图还原：删除前端事实推导并消费后端权威 `curves.distance`。
- P6 AI 洞察：修复并恢复 `__FATIGUE_REVIEW_INSIGHT__`。

## 8. 下一步建议

- 进入 P1 算法链路回正。
- 优先调查 DB / track_json / Resolver 中是否已有可追溯的 `distance_curve`、`altitude_curve`、`timestamp/time`、`calories`。
- 废弃伪 records 方案前，先确定 canonical curve bundle 的最小字段集合。
