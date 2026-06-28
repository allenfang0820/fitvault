# P3b 骑行复盘功率效率与耐力专项化完成报告

## 1. 本次目标

- 按 `docs/p3b_cycling_power_efficiency_durability_prompt.md` 执行 P3b-cycling。
- 将骑行活动的 `metrics.efficiency` 从跑步/速度口径升级为 `power_hr` 功率心率口径。
- 将骑行活动的 `metrics.durability` 从速度后程保持口径升级为 `power_retention` 功率后程保持口径。
- 保持跑步/general 既有 `efficiency / durability` 行为不变。
- 不改前端、不改 AI prompt/schema、不改 DB、不实现 FTP / IF / TSS / W/kg。

## 2. 执行前重新思考

- P3 已完成 `power_variability / pedaling_stability` 后端事实指标。
- P4 已完成骑行主图专项化。
- P5 已完成骑行指标卡专项化，但 `后程效率变化 / 后程保持参考` 仍只能保守展示。
- 因此 P3b 先补后端事实口径是合理顺序，避免前端继续展示跑步语义的效率/耐力。
- 本任务继续沿用 P3b 编号，避免与已完成的 P6 AI 洞察任务冲突。

## 3. 现状调查

- `main.py` 中通用 `metrics.efficiency` 由 `evaluate_efficiency(avg_hr, avg_pace...)` 生成，偏跑步/速度效率语义。
- `metrics.durability` 由 `MetricsResolver._compute_durability_index(speed_stream...)` 生成，偏速度后程保持语义。
- `_build_fatigue_review_summary()` 已提供 `avg_power / power_points_count / power_data_quality`。
- `_build_fatigue_review_curves_snapshot()` 已提供同轴 `curves.power`。
- `_build_cycling_review_metrics()` 已是 P3 骑行专项指标的集中覆盖点，适合继续承载 P3b 覆盖。

## 4. 实现内容

- 新增 `_build_cycling_power_efficiency_metric(summary, avg_hr)`。
  - 仅在 `power_data_quality == "available"` 且 `avg_power > 0` 且 `avg_hr > 0` 时计算。
  - 输出 `basis="power_hr"` 与 `power_per_hr = avg_power / avg_hr`。
  - 保留 `score / level / confidence / delta_pct / sample_size / reasons` 通用字段。
- 新增 `_build_cycling_power_durability_metric(summary, power_curve)`。
  - 仅在 `power_data_quality == "available"` 且同轴 power 曲线有效样本足够时计算。
  - 输出 `basis="power_retention"`、`head_power / tail_power / power_retention_pct`。
  - `head_speed / tail_speed` 在骑行功率口径下保留为 `null`，避免继续伪装成核心事实。
- 扩展 `_build_cycling_review_metrics(...)`。
  - 骑行 sport 覆盖 `efficiency / durability / power_variability / pedaling_stability`。
  - 非骑行 sport 仍只返回 P3 unavailable 占位，不覆盖跑步 `efficiency / durability`。
- 扩展骑行 empty snapshot。
  - `sport_type` 为骑行时，空态 `efficiency / durability` 也带 P3b 字段形态。
  - 跑步空态不新增 `basis / power_*` 字段。

## 5. 降级策略

- 无功率或功率质量非 `available`：`confidence="unavailable"`，`reasons` 标明 `power data unavailable: <quality>`。
- 缺少 `avg_power`：`efficiency` 降级为 `confidence="low"`，不计算 `power_per_hr`。
- 缺少 `avg_hr`：`efficiency` 降级为 `confidence="low"`，不计算 `power_per_hr`。
- 功率曲线样本不足：`durability` 不计算 `power_retention_pct`，并返回 `power data unavailable: insufficient_points`。
- 非骑行：不输出 P3b 覆盖，继续沿用原跑步/general 指标。

## 6. 契约保持与边界

- `get_fatigue_review(activity_id)` 仍是复盘页面唯一权威数据源。
- 前端和 AI 均不得计算或补齐 `efficiency / durability`。
- 未改 `llm_backend.py`。
- 未改 AI prompt/schema。
- 未改 DB schema/migration。
- 未改前端 ECharts 或指标卡布局。
- 未计算 FTP / IF / TSS / W/kg / 功率区间。
- 未从 power curve 重算 NP。
- 未把速度后程保持包装成功率耐力。

## 7. 验证

运行命令：

```bash
python3 -m pytest tests/test_cycling_fatigue_review_metrics.py
python3 -m pytest tests/test_cycling_fatigue_review_snapshot.py tests/test_fatigue_review_contract_realignment.py
python3 -m json.tool docs/js_api_contract.json
PYTHONPYCACHEPREFIX=/private/tmp/python_pycache_p3b python3 -m py_compile main.py
```

当前结果：

- `tests/test_cycling_fatigue_review_metrics.py`：15 passed。
- `tests/test_cycling_fatigue_review_snapshot.py tests/test_fatigue_review_contract_realignment.py`：18 passed。
- `docs/js_api_contract.json`：JSON 格式校验通过。
- `main.py` 语法编译通过。
- 普通 `python3 -m py_compile main.py` 因沙箱无法写入 macOS 用户 pycache 目录失败；改用 `PYTHONPYCACHEPREFIX=/private/tmp/python_pycache_p3b` 后通过。

## 8. 剩余风险

- 本次未接入个人历史 baseline，因此 `efficiency.delta_pct=null / sample_size=0`；原因是既有 baseline 是速度/配速语义，直接复用会混淆功率口径。
- `power_per_hr` 是单次活动内的保守启发式，不是跨人群能力评价。
- 功率后程保持可能受下坡、滑行、路口停顿、路况和跟骑影响，当前不做复杂场景识别。
- P5 指标卡文案当前仍可继续使用“后程效率变化 / 后程保持参考”的保守口吻；如要强化 P3b 用户可见语义，可另做前端文案任务。

## 9. 下一步

- 运行 P3b 全量目标回归：`tests/test_cycling_fatigue_review_snapshot.py`、`tests/test_fatigue_review_contract_realignment.py`、`docs/js_api_contract.json` JSON 校验。
- 可选后续：前端文案把骑行 `efficiency / durability` 从辅助参考进一步改为功率效率/功率保持，但仍只读后端 metrics。
