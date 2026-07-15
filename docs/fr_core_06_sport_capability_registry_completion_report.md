# FR-Core-06 运动类型能力注册表单一真理源完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 复盘运动类型路由由 `metrics_registry.py` 的 review capability registry 作为单一真理源。
- `get_fatigue_review` 快照顶层必须返回后端规范化后的 `review_mode` 与 `capabilities`。
- 前端和 AI 只消费后端 `review_mode/capabilities` 做分流；本地 sport 字符串判断只能作为兼容降级 fallback。

## 2. FR-Core-06 任务契约摘要

- `indoor_cycling / e_biking` 必须进入 cycling 复盘模式。
- `treadmill_running` 必须进入 running 复盘模式。
- `training / cardio / strength_training / breathing / stair_climbing` 等不适合单次耐力复盘的运动必须进入 `not_applicable` 或受限 general 模式，不能默认当 running。
- 同一 sport 在后端 snapshot、前端渲染和 AI prompt 中的 mode 必须一致。

## 3. 工程级提示词

目标：把复盘运动类型能力矩阵收敛为后端单一真理源，消除后端、前端和 AI 各自复制 sport 集合导致的专项错路由。

范围：
- 允许修改 `metrics_registry.py`、`metrics_resolver.py`、`utils/metrics_calc.py`、`main.py`、`track.html`、`llm_backend.py`。
- 允许新增专项矩阵测试，并同步 `docs/js_api_contract.json` 与交付手册。

边界：
- 不修改 HR 传感器来源。
- 不修改步频低置信度算法。
- 不修改历史 baseline 迁移策略。
- 不修改打包或发布流程。
- 不把 unknown 默认当 running。

验收：
- indoor cycling 在后端指标、解释信号、卡片和图表中全部进入 cycling 模式。
- 后端、前端、AI 三处读取同一 `review_mode`。
- 特殊运动样本不再复用错误跑步语义。
- API contract 和快照白名单包含新增顶层字段。

## 4. 实现摘要

- 新增 `normalize_review_sport_type()`、`get_review_mode()`、`get_review_capabilities()`、`REVIEW_MODE_SPORTS` 与 `REVIEW_SPORT_CAPABILITY_REGISTRY`。
- Resolver、主复盘快照和曲线专项判断改为从 registry 获取 mode/capability。
- 空态和正常复盘快照都导出 `review_mode/capabilities`。
- AI prompt builder 改为读取 snapshot 的 `review_mode`，不再维护独立 sport mode map。
- 前端指标卡和 copy group 优先读取后端 `review_mode`，保留兼容 fallback。
- 文档契约同步声明 `review_mode/capabilities` 是后端 registry 导出的 API 字段。

## 5. 验证结果

通过：

```bash
jq empty docs/js_api_contract.json
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_sport_capability_registry.py'
.venv312/bin/python -m pytest -q tests/test_resolver_sport_isolation.py tests/test_fatigue_review_prompts.py
.venv312/bin/python -m pytest -q tests/test_fatigue_review_quality_gate.py::TestP5SnapshotWhitelistGate::test_snapshot_top_level_and_curves_whitelist tests/test_fatigue_review_quality_gate.py::TestP5P4UiStructureGate::test_metric_card_user_facing_copy_and_tooltips tests/test_fatigue_review_quality_gate.py::TestP5P4UiStructureGate::test_p5_cycling_ui_reads_backend_explanation_signals_only tests/test_v9_0_detail_tab_review.py::TestV9AiInsightModalHtml::test_p7_3_metric_render_uses_metrics_only tests/test_v9_0_detail_tab_review.py::TestV9AiInsightModalHtml::test_p5_cycling_metric_cards_use_power_and_pedaling_profile
```

结果：

- `test_fatigue_review_sport_capability_registry.py`：4/4 通过。
- `test_resolver_sport_isolation.py + test_fatigue_review_prompts.py`：129/129 通过。
- 前端白名单与专项 UI 窄测：5/5 通过。
- `docs/js_api_contract.json`：JSON 校验通过。

红线回归：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
```

结果：FR-Core-01 至 FR-Core-06 相关红线保持通过；剩余 1 个失败继续锚定 FR-Core-07：running durability 缺失文案仍出现“功率曲线样本不足”。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-07：指标卡、缺失原因与运动专项文案分流`。
