# P6 运动复盘 AI 洞察接入完成报告

## 1. 本次目标

- 正式执行 P6 运动复盘 AI 洞察接入。
- 修复 `__FATIGUE_REVIEW_INSIGHT__` sentinel 主路径。
- 让 AI 只消费后端权威 compact insight snapshot。
- 保持 P0-P5 边界：不恢复前端推导、不改复盘数据契约、不写 DB、不进入 `ai_snapshots`。

## 2. 修改文件

- `main.py`
- `docs/js_api_contract.json`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `tests/test_fatigue_review_ai_insight_p6.py`
- `tests/test_fatigue_review_quality_gate.py`
- `tests/test_e2e_fatigue_review.py`
- `docs/p6_fatigue_review_ai_insight_completion_report.md`

## 3. 后端 sentinel 修复

- `Api.call_llm()` 中 `__FATIGUE_REVIEW_INSIGHT__` 分支前置到 LLM 配置校验之前。
- sentinel 入口先执行：
  - `self._chat_messages = []`
  - `self._new_session_id()`
- 无活动上下文、DB 无记录、数据不足、LLM 配置缺失、LLM 异常均返回统一 envelope + `empty_fatigue_review_insight(...)`。
- 修复旧版无参调用 `_build_fatigue_review_snapshot()` 的问题。

## 4. AI snapshot 边界

- 新增 `_extract_fatigue_review_activity_id()`，从 `_ai_snapshot` 中定位活动 ID。
- `sync_track_context()` 在后端 `_ai_snapshot` 中保留 `activity_id` 控制字段。
- 新增 `_build_fatigue_review_insight_snapshot(activity_id, sport_type)`：
  - 从 DB row 构建权威复盘 snapshot。
  - 只挑选 AI 所需白名单字段。
  - 将全量 `curves` 压缩为 `curves_summary`。
  - 递归移除 forbidden 字段。

AI snapshot 包含：

- `activity_id`
- `sport_type`
- `metrics`
- `fatigue_zones`
- `collapse_events`
- `curves_summary`
- `context_tags`
- `advice`
- `disclaimer`

AI snapshot 不包含：

- 全量 `curves`
- `records`
- `points`
- `raw_records`
- `track_points`
- `shadow_diff`
- `shadow_diff_json`
- `diff`

## 5. Prompt / Normalizer

- 继续复用 `llm_backend.build_fatigue_review_messages()`。
- 继续复用 `llm_backend.normalize_fatigue_review_json()`。
- 继续复用 `llm_backend.empty_fatigue_review_insight()`。
- Prompt 仍包含 DATA BOUNDARY、禁止重算、禁止 canonical 写回、禁止 shadow_diff 等约束。

## 6. 前端四态

- 前端 `onFatigueReviewAiInsight()` 继续只传：
  - `__FATIGUE_REVIEW_INSIGHT__`
  - `sportType`
- 前端不传 metrics / curves / points / chart payload。
- AI Modal 继续使用 P4 的 `fr-ai-*` 独立 id。
- loading / success / error / empty 四态沿用既有渲染函数。

## 7. 测试变更

- 新增 `tests/test_fatigue_review_ai_insight_p6.py`，覆盖：
  - 活动 ID 提取候选字段。
  - compact AI snapshot 白名单。
  - 无活动上下文 empty insight。
  - DB 无记录 empty insight。
  - happy path 使用 compact snapshot。
  - LLM 异常 empty insight。
  - sentinel 分支不写 DB。
- 更新 `tests/test_fatigue_review_quality_gate.py`，将 AI 边界门禁升级为 P6 后状态。
- 更新 `tests/test_e2e_fatigue_review.py`，mock 活动不存在路径，避免本机只读 DB schema 初始化影响 1004 测试。

## 8. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_prompts.py tests/test_e2e_fatigue_review.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
178 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P6 修改无关。
- 本机无 `python` 命令，继续使用 `python3` 完成验证。

## 9. 未处理事项

- 尚未做真实 LLM 网关的人工联调。
- 尚未用真实跑步 / 越野跑 / 骑行 / 徒步样本逐条人工确认 AI 文案质量。

## 10. 下一步建议

- 做一次真实应用手工联调：加载活动详情 → 切复盘 Tab → 点击生成 AI 洞察。
- 选 3-5 条不同运动类型活动，检查 AI 文案是否严格引用 snapshot、是否避免编造事件和数值。
