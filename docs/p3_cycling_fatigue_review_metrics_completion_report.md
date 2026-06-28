# P3 骑行复盘专项指标实现完成报告

## 1. 本次目标

- 按 `docs/p3_cycling_fatigue_review_metrics_prompt.md` 执行 P3-cycling。
- 将 `metrics.power_variability` 与 `metrics.pedaling_stability` 从 pending 占位升级为后端事实指标。
- 保持数据不足时的明确降级。
- 不改前端 ECharts、不改 AI prompt / 输出 schema、不改 DB schema。

## 2. 现状调查

- `power_variability` 当前状态：原先在正常 snapshot 与 empty snapshot 中均为 `cycling power metric pending implementation` 占位。
- `pedaling_stability` 当前状态：原先在正常 snapshot 与 empty snapshot 中均为 `cycling cadence metric pending implementation` 占位。
- `summary / curves` 输入：P1 已提供 `summary.avg_power / normalized_power / avg_cadence / power_data_quality / cadence_data_quality` 与同轴 `curves.power / curves.cadence`。
- `curves.power/cadence` 同轴保障：仍沿用 P1 的 `_build_fatigue_review_curves_snapshot()` 与 `_build_fatigue_review_summary()` 数据质量判定。

## 3. 实现内容

- `power_variability`：
  - 新增 `_build_cycling_power_variability_metric(summary)`。
  - 仅在 `power_data_quality == "available"` 且 `avg_power / normalized_power` 均有效时计算 `vi = normalized_power / avg_power`。
  - 输出 `vi / level / confidence / avg_power / normalized_power / power_points_count / power_data_quality / reasons`。
- `pedaling_stability`：
  - 新增 `_build_cycling_pedaling_stability_metric(summary, cadence_curve)`。
  - 基于同轴踏频曲线计算 `cv / decay_pct / score`。
  - 输出 `score / level / confidence / cv / decay_pct / avg_cadence / cadence_points_count / cadence_data_quality / reasons`。
- snapshot metrics 接入：
  - 在 `_build_fatigue_review_snapshot()` 生成 `summary` 后，通过 `_build_cycling_review_metrics(...)` 覆盖两项 P3 指标。
  - `cycling / road_cycling / mountain_biking` 输出真实指标或数据质量降级。
  - 非骑行活动保留结构完整的 unavailable 占位。
- empty snapshot：
  - `_empty_fatigue_review_snapshot()` 中两项指标升级为 P3 字段形态。

## 4. 降级策略

- 无功率：`power_data_quality != available` 时 `vi=null / confidence=unavailable`，`reasons` 标明具体质量枚举。
- NP/AvgPower 缺失：不计算 VI，返回 low 或 unavailable，并写入缺失原因。
- 无踏频：`cadence_data_quality != available` 时 `score/cv/decay_pct=null / confidence=unavailable`。
- 非骑行：返回 unavailable 占位，不影响跑步复盘。

## 5. 明确不做

- 未改前端 ECharts。
- 未改 AI prompt / 输出 schema。
- 未实现 FTP / IF / TSS / W/kg。
- 未重写 `efficiency / durability`。
- 未改 DB schema。

## 6. 验证

运行命令：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py tests/test_cycling_fatigue_review_snapshot.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_prompts.py
python3 -m json.tool docs/js_api_contract.json
```

结果：

- `tests/test_cycling_fatigue_review_metrics.py`：9 passed。
- P1/P2/P3 相关回归：100 passed。
- `docs/js_api_contract.json`：JSON 格式校验通过。
- 测试过程中仅出现 urllib3 / LibreSSL 环境 warning，与本次修改无关。

## 7. 剩余风险

- `pedaling_stability.score` 是保守启发式评分，后续可以结合骑行台、户外停顿、路口滑行等上下文再细化。
- `power_variability.vi` 依赖已有 NP 字段；若设备或导入链路未提供 NP，本任务不会从曲线重算。
- power-based `efficiency / durability` 尚未专项化，仍留作后续 P3b 或独立任务。

## 8. 下一步

- P4：前端主图骑行模式，默认显示 power + hr + altitude，并加入踏频图层。
- P3b 可选：power-based efficiency / durability 语义改造。
