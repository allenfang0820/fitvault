# P8.4 本次复盘概览四维总览卡完成报告

## 1. 本阶段目标

P8.4 将复盘 Tab 顶部「本次复盘概览」升级为四维总览卡，让首屏直接承载：

- 全程稳定性
- 疲劳阶段
- 风险触发
- 外部影响

本阶段只改概览区域，不改分层主图、左侧泳道、右侧摘要栏、状态阶段概览、图层控制、活动详情顶部信息或 Tab 体系。

## 2. UI 结构说明

在 `fr-status-strip` 内新增：

```html
<div class="fr-overview-dimensions" id="fr-overview-dimensions">
```

四个卡片固定使用：

- `data-fr-ai-dim="overall_stability"`
- `data-fr-ai-dim="fatigue_progression"`
- `data-fr-ai-dim="risk_triggers"`
- `data-fr-ai-dim="context_impact"`

桌面端四列展示，720px 以下两列，480px 以下单列，避免挤压主图和摘要文本。

## 3. 规则版四维数据来源

新增 `_buildFatigueReviewOverviewDimensions(data)`。

规则版只读取 `get_fatigue_review(activity_id)` 返回的后端 snapshot：

- `data.metrics`
- `data.fatigue_zones`
- `data.collapse_events`
- `data.context_tags`
- `data.advice`
- `data.disclaimer`
- `data.sport_type`

不读取 DOM，不读取 ECharts，不读取 chart payload，不读取 points，不调用 LLM，不在前端重新计算心率漂移、解耦、Bonk 或疲劳区间。

## 4. AI 增强方式

AI 成功后，`_renderFatigueReviewAiSuccess(insight)` 调用：

```js
_buildFatigueReviewOverviewDimensionsFromAi(insight.key_dimensions)
```

AI 增强只读取 `insight.key_dimensions`，并通过 `_renderFatigueReviewOverviewDimensions(..., 'ai')` 更新同一组四维卡片。

AI Modal 仍保留，用于展示详细总评、维度评分、事件解读和建议。

## 5. 清空态 / 阅后即焚

新增 `_lastFatigueReviewData` 作为当前页面内存态。

- 复盘加载成功后，保存当前后端 snapshot 并渲染规则版四维。
- AI 成功后，四维卡显示 AI 增强态。
- `_clearFatigueReviewInsight()` 清空 AI 结果后，如果仍有 `_lastFatigueReviewData`，恢复规则版四维。
- loading / error / 关闭复盘面板时清理或回到占位态。

不写 DB，不写 `localStorage`，不写 `sessionStorage`。

## 6. 契约保持项

通过。

- 前端 AI 调用仍为 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。
- 前端不传 `activityId / metrics / curves / fatigue_zones / collapse_events / points / DOM / chartPayload`。
- AI 增强不覆盖 `metrics / curves / fatigue_zones / collapse_events`。
- AI 不参与主图渲染。
- 不写 DB。
- 不写 `ai_snapshots`。
- 不写 `localStorage`。
- 不写 `sessionStorage`。
- 不改 P7 主图结构和右侧栏结构。

## 7. 测试结果

```bash
python3 -m pytest tests/test_v9_0_detail_tab_review.py tests/test_fatigue_review_quality_gate.py
# 125 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py
# 15 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_prompts.py tests/test_fatigue_review_e2e_contract.py tests/test_e2e_fatigue_review.py
# 107 passed, 1 warning
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.4 回归失败。

## 8. 剩余风险

- 本轮未做真实浏览器截图验收，需在实际窗口中观察四维卡在长中文、窄屏和 AI 长解释下的视觉表现。
- AI 成功态的文案质量仍取决于真实 LLM 输出，P8.4 只保证承载结构和契约边界。
- 当前规则版文案是轻量归纳，后续可根据真实用户反馈继续润色。

## 9. 下一步建议

进入 P8.5「真实 AI 文案与 Modal 可读性验收」。

重点检查：

- 点击 `生成 AI 洞察` 后四维卡是否从规则版切到 AI 增强态。
- AI Modal 长文本是否可读。
- 切 Tab、切活动、重新点击、关闭详情后 AI 增强态是否清空并恢复规则版。
- 窄屏和常用窗口尺寸下四维卡是否不溢出、不遮挡主图。
