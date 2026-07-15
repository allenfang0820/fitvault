# RCV2-37 完成报告：Records Snapshot、AI 与 Trends 联动

## 结论

RCV2-37 已完成。Career Snapshot 现在可安全压缩 Records Center V2 的正式纪录、候选数量、正式刷新事件、演进摘要和 curve availability，并为 AI fallback 与 Trends 提供明确的 facts / analysis / model 边界。

## 主要变更

- `career_backend.py`
  - 新增 Records Snapshot V2 安全摘要：
    - `formal_records`：只包含 `active/superseded` 正式纪录，排除 `analysis_only/model_only/unavailable` 和 analysis/model family。
    - `curve_availability`：只统计 `curve_type/sport/source_mode/algorithm_version/sample_count/latest_generated_at/state` 等安全元数据。
    - `trend_inputs.curve_inputs`：为 PDC/Pace/GAP 提供 Trends 可消费输入，统一标记 `kind=analysis`、`source=career_record_curve_cache`、`creates_formal_record=false`。
    - `trend_inputs.model_boundary`：明确 eFTP、CP、W′、MAP、PMax、GAP、NGP 等模型/分析输出不生成正式纪录、不暴露 candidate evidence。
  - 将 `recent_refreshes` 限定为正式刷新事件：`activated`、`activated_from_rebuild`、`user_confirmed`；`recalculated` 只保留在演进统计中，不再被误读为正式刷新。
  - 扩展 saved Career Snapshot sanitizer，历史脏内容会被裁剪成当前安全 schema。
  - AI fallback highlights 保持旧“当前纪录 N 项”兼容文案，同时新增“分析曲线可用 N 类，仅作趋势参考”边界文案。
  - 过滤 legacy `current_records` 中的 model/analysis active 行，避免模型估计混入旧 PB 摘要。
- `docs/js_api_contract.json`
  - 更新 `get_latest_career_snapshot` 返回契约，加入 `formal_records`、`curve_availability` 和扩展后的 `trend_inputs`。
  - 明确 curve/PDC/Pace/GAP 只作为 analysis 来源，模型估计不得表述为正式纪录刷新。
- `tests/test_career_records_v2_snapshot_ai_trends.py`
  - 新增 Snapshot / AI / Trends 定向测试。
- `tests/test_career_snapshot_builder.py`
  - 更新 Records Summary 白名单与 trend input 断言。
- `tests/test_career_snapshot_persistence.py`
  - 更新历史脏 Snapshot sanitizer 的 interpretation 断言。

## 安全边界

- Snapshot 不返回 raw FIT、raw streams、points、track、route signature、path、SQLite schema、体重详情、candidate evidence 或 curve payload。
- Curve cache 只进入 availability/analysis 摘要，不反向生成或刷新正式纪录。
- 模型估计与分析输出只出现在 `model_boundary.excluded_estimates`，不进入 `formal_records`。
- AI fallback 只消费安全 Snapshot，不重算纪录、不确认候选、不写 canonical 表。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_snapshot_builder.py -q
# 10 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_records_v2_downstream_integration.py tests/test_career_insight_api_skeleton.py -q
# 21 passed

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_snapshot_builder.py -q
# 20 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_snapshot_ai_trends.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_records_v2_api.py tests/test_career_records_v2_downstream_integration.py tests/test_career_insight_api_skeleton.py -q
# 41 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed

.venv312/bin/python - <<'PY'
import json
from pathlib import Path
json.loads(Path('docs/js_api_contract.json').read_text(encoding='utf-8'))
print('js_api_contract_json_ok')
PY
# js_api_contract_json_ok
```

## 自适应复核

- 本任务实际触碰范围符合预期：Snapshot builder、AI fallback highlights、JS API contract、snapshot/AI/trends 测试和任务文档。
- 工作区存在大量前序任务未提交 diff；本轮复核按 RCV2-37 新增符号与测试覆盖进行 scoped review，未清理、回退或覆盖无关改动。
- 未执行打包、签名、公证或发布包替换。
- 未对真实库执行 apply/rebuild；所有测试均为内存库或静态契约检查。

## 后续任务入口

进入 `RCV2-38 安全、性能、日志与可观测性闭环`。重点验证 V2 rebuild、Curve、Route、API 和 UI 的安全扫描、性能目标、日志观测与不可泄露字段。
