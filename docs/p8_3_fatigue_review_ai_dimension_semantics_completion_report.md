# P8.3 复盘 AI 洞察四维语义回正完成报告

## 1. 本阶段目标

P8.3 将复盘 AI 洞察的 `key_dimensions` 从通用运动表现维度回正为更贴合复盘 UI 的四维语义。

本阶段只修改 AI schema、prompt、normalizer、前端 label 兜底和测试；不改复盘主图，不改右侧栏，不改「本次复盘概览」布局，不把 AI 四维嵌入概览卡。

## 2. 旧四维与新四维对照

| 旧 key | 旧语义 | 新 key | 新语义 |
|---|---|---|---|
| `stability` | 心肺稳定 | `overall_stability` | 全程稳定性 |
| `endurance` | 耐力 | `fatigue_progression` | 疲劳阶段 |
| `bonk_risk` | 撞墙风险 | `risk_triggers` | 风险触发 |
| `environment` | 环境压力 | `context_impact` | 外部影响 |

## 3. 新四维定义

- `overall_stability` / 全程稳定性：解释整场心率、配速、效率、步频和节奏是否稳定，可指出波动发生在前段、中段或后段。
- `fatigue_progression` / 疲劳阶段：解释疲劳是否出现、从哪里出现、是否持续或加重。
- `risk_triggers` / 风险触发：解释 Bonk 风险、collapse events、训练负荷或后端已识别事件中真正值得注意的风险线索。
- `context_impact` / 外部影响：解释天气、温度、湿度、地形、路线、设备或数据质量对本次表现的影响。

## 4. 修改文件

- `llm_backend.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_prompts.py`
- `tests/test_fatigue_review_e2e_contract.py`
- `tests/test_e2e_fatigue_review.py`
- `tests/test_v9_0_detail_tab_review.py`
- `docs/p8_3_fatigue_review_ai_dimension_semantics_completion_report.md`

## 5. Normalizer 容错策略

`normalize_fatigue_review_json()` 已改为固定输出四维顺序：

```text
overall_stability
fatigue_progression
risk_triggers
context_impact
```

容错策略：

- 支持新 key 原样进入固定顺序。
- 兼容旧 key，并映射到新 key。
- 统一使用新中文 label，避免旧 label 继续显示。
- 缺失维度补 `level: unknown` 和 `comment: 暂无足够数据`。
- 重复维度只保留第一条。
- 非法 `level` 降级为 `unknown`。
- comment 截断，避免撑破 Modal。
- 解析失败仍返回 `empty_fatigue_review_insight(error)`。

## 6. 前端显示策略

前端仍只渲染 normalizer 输出的 `key_dimensions`，不计算 level，不从前端 metrics 推导维度。

新增 `_fatigueReviewAiDimensionLabel(key, fallback)` 作为中文兜底：

- `overall_stability` -> `全程稳定性`
- `fatigue_progression` -> `疲劳阶段`
- `risk_triggers` -> `风险触发`
- `context_impact` -> `外部影响`

## 7. 契约保持项

通过。

- 前端调用仍为 `call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)`。
- 前端不传 `activityId / metrics / curves / fatigue_zones / collapse_events / points / DOM / chartPayload`。
- compact snapshot 白名单不变。
- 不写 DB。
- 不写 `ai_snapshots`。
- 不写 `localStorage`。
- 不写 `sessionStorage`。
- 不修改 `metrics / curves / fatigue_zones / collapse_events`。
- 不改 P7 已冻结 UI 布局。

## 8. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_prompts.py
# 33 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_e2e_contract.py tests/test_e2e_fatigue_review.py
# 74 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_ai_insight_p6.py
# 15 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 121 passed, 1 warning

python3 -m json.tool docs/js_api_contract.json
# passed
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P8.3 回归失败。

## 9. 剩余风险

- 本阶段未做真实 LLM 长文本视觉验收。
- 如果外部模型无视 prompt 返回旧 key，normalizer 会映射，但解释文案本身仍可能保留旧思路，需要真实联调观察。
- 当前四维仍在 AI Modal 内展示，尚未嵌入「本次复盘概览」。

## 10. 下一步建议

进入 P8.4「本次复盘概览四维总览卡」。

P8.4 建议将「本次复盘概览」升级为四维总览卡：

- 未生成 AI 时展示后端规则版四维概览。
- 生成 AI 后用 AI 四维解释增强同一位置。
- 保持 AI 输出只做解释层，不参与指标计算，不写 DB。
