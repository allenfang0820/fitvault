# 运动详情页多运动升级完成报告

日期：2026-07-28  
分支：`codex/activity-detail-multisport-upgrade`  
任务源：`docs/运动详情页多运动升级开发任务清单.md`  
状态：代码层与自动门禁已完成

## 1. 目标结论

本轮完成活动详情页「概览」和「复盘」的多运动升级。详情页不再把非户外运动照搬跑步或骑行页面，而是由后端事实链路决定展示模式、能力、受限原因和 AI 数据边界。

已完成：

- `metrics_registry.py` 成为 `detail_surface_mode`、`review_profile`、能力和受限原因的单一真理源。
- `get_activity_detail()` 的 `record.detail` 输出多运动概览 view model。
- `get_fatigue_review()` 的普通 snapshot 和 AI compact snapshot 输出 `review_profile`、`capabilities`、`not_applicable_reason`、`available_review_facts`。
- `track.html` 的概览和复盘优先消费后端 view model，不从 DOM、曲线或 ECharts 补算事实。
- `build_fatigue_review_messages()` 按后端 profile 做 AI prompt 分流，不跨运动、不猜事实。

## 2. 支持模式

| 模式 | 当前结论 |
| --- | --- |
| `endurance_outdoor` | 跑步、越野跑、户外骑行保留既有地图、Hero、圈速、复盘图表和事件体验 |
| `endurance_indoor` | 跑步机和室内骑行不展示路线失败、天气压力、GAP 或地形空图；只展示已有心率、功率、踏频、配速等事实 |
| `swim_pool` / `swim_open_water` | 游泳使用 /100m、SWOLF、泳段、划频、心率等事实，不套跑步或骑行结论 |
| `strength` | 无结构化动作数据时进入受限概览和受限复盘，不猜动作、组数、重量、肌群或训练量 |
| `mobility_recovery` | 瑜伽、拉伸、呼吸类活动使用恢复类受限说明，不做竞速化表现评价 |
| `generic_session` | 泛训练只展示已有事实和受限说明，不生成完整耐力复盘 |
| `not_supported` | `unknown` / `driving` 不默认跑步或骑行，进入不适用状态 |

## 3. 合同字段

新增或冻结字段：

- `detail_surface_mode`
- `overview_capabilities`
- `overview_empty_states`
- `overview_metrics`
- `primary_visual`
- `split_section`
- `review_profile`
- `capabilities`
- `not_applicable_reason`
- `available_review_facts`

这些字段已同步到 `docs/js_api_contract.json` 和聚焦测试。

## 4. 验证结果

通过：

```bash
jq empty docs/js_api_contract.json
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_sport_capability_registry.py'
.venv312/bin/python -m pytest -q tests/test_activity_detail_multi_sport_capabilities.py tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_quality_gate.py tests/test_fatigue_review_prompts.py tests/test_fatigue_review_ai_preflight_p8.py tests/test_fatigue_review_e2e_contract.py tests/test_response_envelope_contract.py tests/test_v9_0_detail_tab_review.py
git diff --check
```

结果：

- Registry unittest：5 tests OK。
- 回归 pytest：316 passed，57 subtests passed。
- `docs/js_api_contract.json`：JSON 有效。
- `git diff --check`：通过。

## 5. 手测清单

新增 `docs/activity_detail_multi_sport_manual_test_checklist.md`，覆盖：

- 桌面宽屏、中宽、窄屏。
- 详情打开、概览默认态、复盘懒加载、活动切换状态清理。
- 长文案、少卡片、无卡片、无轨迹、无分段、无曲线。
- 所有 `detail_surface_mode` 和 `review_profile` 样本。

本轮未启动 pywebview 桌面应用执行真实截图或人工逐项勾选。因此本报告不声称 live UI 截图验收已完成；发布前仍需按清单使用真实活动样本做一次人工 smoke。

## 6. 非目标和剩余风险

非目标：

- 不解析结构化力量 FIT 消息。
- 不实现肌群热图、动作组、重量、训练容量或渐进负荷趋势。
- 不修改 DB schema、打包脚本、DMG/MSI 或发布流程。

剩余风险：

- 真实设备厂商对游泳、力量和泛训练字段覆盖不一致，仍需要更多真实样本回放。
- live 响应式截图未在本轮执行，长标题、长建议和极窄窗口需要发布前人工确认。
- 结构化力量解析接入前，力量训练只能保持受限复盘，不能作为力量专项完整分析。

## 7. 发布建议

代码层门禁已通过，可以进入真实样本手测和发布候选评估。建议发布前按新增手测清单至少覆盖：户外跑步、户外骑行、跑步机、室内骑行、泳池游泳、力量训练、瑜伽或呼吸、unknown。
