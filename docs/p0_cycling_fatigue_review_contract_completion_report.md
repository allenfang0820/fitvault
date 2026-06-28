# P0 骑行复盘专项化契约与边界完成报告

## 1. 本次目标

- 按 `docs/p0_cycling_fatigue_review_contract_prompt.md` 执行 P0-cycling。
- 明确 `cycling / road_cycling / mountain_biking` 的复盘专项契约边界。
- 在 `get_fatigue_review(activity_id)` 契约中预留 `power / cadence / summary / data_quality`。
- 在复盘 AI compact snapshot 契约中预留骑行功率与踏频摘要。
- 只做契约、文档、测试和必要空态占位，不实现真实骑行算法，不改前端展示，不改 LLM 输出逻辑。

## 2. 现状核对

- `get_fatigue_review` 原 `curves` 白名单包含 `distance / time / hr / speed / altitude / grade / gap / efficiency / terrain_load / total_distance_m`，缺少 `power / cadence`。
- AI compact snapshot 原 `curves_summary` 包含 `has_hr / has_speed / has_altitude / has_grade / has_gap / has_efficiency`，缺少 `has_power / has_cadence`。
- 原契约未声明 `summary.avg_power / normalized_power / avg_cadence / power_data_quality` 等骑行摘要字段。
- forbidden 字段隔离规则已存在，继续保持 `shadow_diff / shadow_diff_json / diff / records / 全量 points` 禁止进入 API data。

## 3. 契约变更

- `docs/js_api_contract.json`
  - `get_fatigue_review.returns` 新增 `summary`。
  - `get_fatigue_review.returns` 新增 `curves.power / curves.cadence`。
  - `get_fatigue_review.returns` 预留 `metrics.power_variability / metrics.pedaling_stability`。
  - `get_fatigue_review.contract` 明确 `curves.power / curves.cadence` 必须由后端权威输出，前端不得补算、推断、拉伸或从 DOM/ECharts/points 重建。
  - `fatigue_review_ai_contract` 新增 `summary` 与 `curves_summary.has_power / has_cadence / power_points_count / cadence_points_count`。

- `docs/fatigue_review_realignment_plan_v1.md`
  - 新增 `P0-cycling 骑行复盘专项化契约` 章节。
  - 明确覆盖 `cycling / road_cycling / mountain_biking`。
  - 明确无功率、功率样本不足、踏频缺失时的降级规则。

- `docs/脉图运动复盘系统_开发团队交付手册_v1.md`
  - `_build_fatigue_review_snapshot()` 示例新增 `curves.power / curves.cadence`。
  - 示例新增 `summary` 字段。

## 4. 代码占位

- `main.py`
  - `_empty_fatigue_review_snapshot()` 新增 `curves.power / curves.cadence` 空数组。
  - `_empty_fatigue_review_snapshot()` 新增保守 `summary` 空态。
  - `_build_fatigue_review_curves_snapshot()` 将已有 bundle 中的 `power_curve / cadence_curve` 纳入白名单输出。
  - `_summarize_fatigue_review_curves_for_ai()` 新增 `has_power / has_cadence / power_points_count / cadence_points_count`。
  - `_build_fatigue_review_insight_snapshot()` 新增 `summary`。
  - `metrics` 中预留 `power_variability / pedaling_stability` unavailable 占位。

## 5. 明确不做

- 未实现 `power_variability` 真实算法。
- 未实现 `pedaling_stability` 真实算法。
- 未把骑行 `efficiency` 改成 `power/hr`。
- 未把骑行 `durability` 改成功率耐久。
- 未修改 `track.html`。
- 未修改 `llm_backend.py` 的 LLM 输出逻辑。
- 未修改 DB schema。

## 6. 验证

运行命令：

```bash
python3 -m json.tool docs/js_api_contract.json
python3 -m pytest tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py
```

结果：

- JSON 契约解析通过。
- `tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py`：43 passed。
- `tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py`：47 passed。
- 测试过程中仅出现 urllib3 / LibreSSL 环境警告，与本次契约变更无关。

## 7. 剩余风险

- `power_data_quality` 目前是 P0 级别保守判定，后续仍需 P1/P2 对异常功率、滑行 0W、样本覆盖率做更精细处理。
- `power_variability / pedaling_stability` 目前只是 unavailable 占位，不能用于用户可见能力判断。
- 骑行 AI 提示词仍未专项化，本次只保证后端 compact snapshot 契约有输入位置。
- 前端仍未切换骑行主图，展示专项化留到后续阶段。

## 8. 下一步

- P1：复盘快照补齐 power/cadence 的真实同轴输出与数据质量判定。
- P2：AI compact snapshot 接入骑行摘要并强化无功率降级。
- P3：实现骑行专项指标 `power_variability / pedaling_stability / power-based efficiency / power durability`。
