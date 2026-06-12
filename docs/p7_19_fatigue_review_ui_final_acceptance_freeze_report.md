# P7.19 复盘 UI 终轮视觉验收与冻结报告

## 1. 任务目标

对 P7 复盘 UI 做终轮视觉验收与冻结判断。P7.19 不新增功能，不开放 AI 洞察，只确认 P7.10-P7.18F 已完成的主图、泳道、图层控制、右侧摘要、响应式和疲劳区间合并是否足以进入 P8。

## 2. 冻结前再思考结论

P7.19 执行前重新核对了三条边界：

- 复盘 Tab 的事实数据源仍是 `get_fatigue_review(activity_id)` 后端 snapshot。
- 前端不得从 DOM、截图、ECharts 像素、活动标题、设备、路线、`points` 或曲线走势推导事实。
- AI 入口继续冻结，不新增 `call_llm`，不修改 AI prompt，不写 DB。

本轮只发现一个冻结前应回正的小视觉问题：主图顶部图例仍保留 `速度` / `Terrain Load` 文案，而泳道标题和图层控制已统一为 `配速` / `地形负荷`。已在本轮修正为：

- `配速 · curves.speed`
- `地形负荷 · curves.terrain_load`

同步更新了静态质量门禁和手工验收清单。

## 3. 视觉验收项

已验收通过：

- 主图保持分层 ECharts 多泳道结构，共用 `curves.distance`。
- 泳道顺序保持：心率、配速、GAP、效率、海拔、坡度、地形负荷。
- 左侧泳道标题无方框，居中呈现，颜色与曲线/图层控制一致。
- Tooltip 指标顺序与泳道顺序一致，数值最多保留一位小数，整数不显示小数。
- 图层控制已移出并删除“图层与摘要”卡片。
- 图层控制包含所有曲线、疲劳带和事件开关。
- 底部重复摘要卡片和事件时间线已删除。
- 图表已绑定 window resize 与 ResizeObserver。
- 泳道高度按可绘制泳道数量自适应，避免短活动或隐藏图层后画布过高。
- `fatigue_zones` 在后端 snapshot 阶段合并相邻同级别区间，右侧状态区间不再展示相邻重复卡。

## 4. 样本抽查

当前工作区 `user_profile.db` 可用样本少于用户运行中应用截图，因此本轮自动抽查采用本地可读样本，并继承 P7.18F 对用户截图中 `2025-05-11 跑步` 间歇样本的验证结论。

本轮只读抽查结果：

| 样本 | 类型 | 曲线点数 | 疲劳区间 | 事件 | 相邻同级重复 |
|---|---|---:|---:|---:|---:|
| activity 23, 2026-05-16 running 6.44km | 普通跑 | 2670 | 1 | 1 | 0 |
| activity 24, 2023-04-22 running 19.88km | 长距离/高波动样本 | 21694 | 4 | 2 | 0 |
| activity 16, 2026-05-17 running 5.65km | 低事件样本 | 2403 | 1 | 0 | 0 |
| activity 22, 2026-04-11 hiking 11.10km | 徒步样本 | 10819 | 3 | 2 | 0 |

P7.18F 已验证用户截图问题样本：

- `2025-05-11 跑步` 原始 `fatigue_zones` 26 段，合并后 12 段。
- 相邻同级别 high / medium 已合并。
- medium / high 交替段保留，不强行合并不同状态。

## 5. 环境限制

直接调用 `Api.get_fatigue_review(activity_id)` 做只读抽查时，入口会先执行 schema ensure；当前环境下该动作触发 `sqlite3.OperationalError: attempt to write a readonly database`。为避免 P7.19 写 DB，本轮改为只读 SQL 取活动 row 后调用同一后端 `_build_fatigue_review_snapshot(row)` 验证 snapshot 形态。

该限制不影响本轮冻结判断：自动测试覆盖了 API 契约、前端门禁和错误 envelope；样本抽查覆盖了 snapshot 的曲线长度、疲劳区间、事件和相邻合并结果。

## 6. 修改文件

- `track.html`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/detail_tab_review_manual_test_checklist.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/p7_19_fatigue_review_ui_final_acceptance_freeze_report.md`

## 7. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 97 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
# 45 passed, 1 warning
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P7.19 回归失败。

## 8. 冻结决定

P7 复盘 UI 可以冻结，允许进入 P8 复盘 AI 洞察接入/开放前复核。

冻结条件：

- P8 必须继续以 `get_fatigue_review(activity_id)` 后端 snapshot 为事实源。
- P8 不得让 AI 输出参与指标、事件、疲劳区间或曲线计算。
- 是否解除 `fr-ai-generate-btn` 冻结必须在 P8 单独审查后执行。
- P8 如需新增 AI 洞察展示字段，应先补充 contract / prompt / frontend 清空态门禁。

## 9. 下一步建议

进入 P8「复盘 AI 洞察接入/开放前复核」。

建议 P8 第一阶段先做开放前审查，不直接打开按钮：

- 复核 `__FATIGUE_REVIEW_INSIGHT__` 只消费 compact 后端 snapshot。
- 复核 AI 输出只做解释层，不回写 DB，不改 metrics / curves / fatigue_zones / collapse_events。
- 复核按钮打开、loading、error、empty、success 和清空态。
- 复核 P7 冻结 UI 不因 AI 结果插入而发生布局挤压。
