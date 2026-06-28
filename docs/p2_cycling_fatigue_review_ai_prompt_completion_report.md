# P2 骑行复盘 AI 提示词专项化完成报告

## 1. 本次目标

- 按 `docs/p2_cycling_fatigue_review_ai_prompt.md` 执行 P2 骑行复盘 AI 提示词专项化。
- 让骑行复盘在 AI 层优先解释功率、踏频、心率与地形关系。
- 在无功率、功率样本不足、踏频缺失时明确降级，不再沿用跑步式主解释框架。
- 保持 AI 输出 schema、normalizer、sentinel 调用链不变。

## 2. 修改文件

- `llm_backend.py`
- `tests/test_fatigue_review_prompts.py`
- `docs/p2_cycling_fatigue_review_ai_prompt_completion_report.md`

## 3. Prompt 规则变更

- 有功率：
  - 优先解释 `summary.power_data_quality`、`summary.normalized_power(NP)`、`summary.avg_power`、`summary.power_points_count`。
  - 可以结合心率、坡度、爬升、速度解释功率输出与身体反应是否一致。
  - 明确禁止自行计算 VI、FTP、IF、TSS、W/kg。
- 无功率：
  - `missing / insufficient_points / invalid_values / length_mismatch / unavailable` 都必须触发降级。
  - 必须说明功率相关判断置信度受限，不能输出完整功率复盘。
  - 速度只能作为辅助观察，不能替代功率结论。
- 踏频可用：
  - `avg_cadence` 只作为踩踏组织辅助证据。
  - 不得推断左右平衡、扭矩、齿比、低踏高扭矩、踏频衰减。
- 踏频缺失：
  - 必须说明踩踏组织无法评估，禁止编造踏频稳定性/效率判断。
- 禁止跑步化表达：
  - 明确禁止把配速、步频、跑姿、触地、步幅、跑步节奏、恢复跑、跑步赛道作为骑行核心解释框架。
- `overall_stability`：
  - 改为按运动类型解释；骑行时侧重功率输出、心率反应、踏频组织和爬升背景。

## 4. 契约保持不变

- AI 输出 schema 不变。
- `key_dimensions` 仍是 `overall_stability / fatigue_progression / risk_triggers / context_impact` 四维。
- AI compact snapshot 白名单不变。
- 前端边界不变，未改 `track.html`。

## 5. 明确不做

- 未实现骑行评分算法。
- 未改前端 ECharts。
- 未改 DB schema。
- 未做真实 LLM 联调。

## 6. 验证

- 运行命令：`python3 -m pytest tests/test_fatigue_review_prompts.py`
- 结果：`41 passed, 1 warning`
- warning 为本机 urllib3 / LibreSSL 环境提示，与本次修改无关。

## 7. 剩余风险

- 当前仍是 prompt 级约束，真实 LLM 输出质量还需要后续联调确认。
- 跑步与骑行共享同一套输出 schema，后续若要进一步提高骑行可读性，可能还需要 P3 指标层再补“功率波动/踩踏稳定性”事实。

## 8. 下一步

- P3：骑行专项指标实现。
- P4：前端主图骑行模式。
