# P6.1 复盘 AI 洞察入口冻结完成报告

## 1. 本次目标

- 保留 P6 后端 AI 洞察能力。
- 在 UI 设计定稿前冻结复盘页 AI 洞察入口。
- 确保用户无法通过复盘 Tab 触发 LLM。
- 不回退 P6 后端代码、不修改 prompt / normalizer、不改数据契约。

## 2. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/p6_1_fatigue_review_ai_entry_freeze_completion_report.md`

## 3. 冻结策略

- `fr-ai-generate-btn` 保留但禁用。
- 按钮文案改为 `🤖 AI 洞察待开放`。
- 按钮增加 `aria-disabled="true"`。
- 按钮 title 为 `AI 洞察将在 UI 定稿后开放`。
- 移除按钮上的 `onclick="onFatigueReviewAiInsight()"`。
- 新增 `_freezeFatigueReviewAiEntry()`，统一设置冻结状态。
- `_clearFatigueAiInsight()`、`_clearFatigueReviewInsight()` 和 AI 四态渲染后都会保持按钮冻结。
- 复盘 AI 缓存 banner 暂不渲染，避免形成第二个 AI 入口。

## 4. 保留能力

- `onFatigueReviewAiInsight()` 函数保留。
- `__FATIGUE_REVIEW_INSIGHT__` 后端 sentinel 保留。
- P6 compact AI snapshot 和测试保留。
- 后续 UI 定稿后，可以通过恢复按钮 onclick / enabled 状态重新开放入口。

## 5. 测试变更

- `tests/test_v9_0_detail_tab_review.py`
  - 增加 AI 入口冻结断言。
  - 检查 `_freezeFatigueReviewAiEntry()` 存在。
  - 检查 `_clearFatigueReviewInsight()` 保持入口冻结。
- `tests/test_fatigue_review_quality_gate.py`
  - 增加“按钮冻结但能力保留”门禁。

## 6. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_envelope.py
```

```text
109 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P6.1 修改无关。
- 本机无 `python` 命令，继续使用 `python3` 完成验证。

## 7. 下一步建议

- 继续进行复盘 UI 真实页面验收和设计打磨。
- UI 定稿后再开放 AI 洞察入口，并跑真实 LLM 联调。
