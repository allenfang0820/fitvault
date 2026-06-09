# P7.1 复盘 Tab 信息架构稿完成报告

## 1. 任务目标

在 P7.0 设计边界内，固定“复盘 Tab = 草图分析页”的信息架构，明确后续 P7.x UI 实现的页面区块顺序、区块职责、字段来源、空态策略和响应式骨架。

## 2. 修改文件

- `docs/p7_fatigue_review_analysis_cockpit_information_architecture.md`
- `docs/fatigue_review_realignment_plan_v1.md`
- `docs/detail_tab_review_manual_test_checklist.md`

## 3. 信息架构摘要

复盘 Tab 内部从上到下固定为 8 个区块：

1. Tab 内部标题与状态行
2. 分析摘要带
3. 核心状态区
4. 能力与负荷区
5. 主图分析区
6. 事件与疲劳区间解释区
7. 上下文与建议区
8. disclaimer / 数据边界说明

## 4. 字段来源矩阵摘要

- 标题与状态行读取 API envelope 状态和 P6.1 前端冻结状态。
- 分析摘要带读取 `sport_type / curves.distance / curves / fatigue_zones / collapse_events / metrics`。
- 核心状态区读取 `metrics.hr_drift / decoupling / bonk_risk / events`。
- 能力与负荷区读取 `metrics.efficiency / durability / cadence_stability / training_load`。
- 主图分析区读取 `curves / fatigue_zones / collapse_events`，其中 X 轴只允许使用 `curves.distance`。
- 事件与疲劳区间读取 `collapse_events / fatigue_zones`。
- 上下文与建议读取 `context_tags / advice / disclaimer`。

所有字段只允许前端格式化展示，禁止前端事实推导。

## 5. 空态策略摘要

已覆盖：

- `get_fatigue_review` 返回 `code != 0`
- `data` 为空
- `metrics` 部分缺失
- `curves.distance` 为空
- `fatigue_zones` 为空
- `collapse_events` 为空
- `context_tags` 为空
- `advice` 为空
- `sport_type` 暂不适用

## 6. 响应式骨架摘要

- 桌面端：摘要带横向展示，指标卡多列，主图占主列，事件/上下文/建议为右侧信息列。
- 中等宽度：指标卡换行，主图占整行，侧栏内容下移。
- 窄屏：所有区块单列堆叠，摘要状态项换行，长文本自然换行。
- 固定格式元素需要稳定尺寸约束，避免加载态和空态切换造成布局跳动。

## 7. 契约约束确认

- `get_fatigue_review(activity_id)` 仍是复盘 Tab 唯一数据源。
- 前端不得从 speed/time/total_distance_m/points/DOM 推导事实字段。
- `curves.distance` 是图表 X 轴、疲劳带和事件定位的唯一后端权威距离来源。
- `metrics / fatigue_zones / collapse_events / context_tags / advice / disclaimer` 只能从后端 snapshot 白名单读取。
- 字段缺失、数组为空或运动类型不适用时展示空态、弱化态或“待接入”，不得前端补算。
- P7 UI 改造不得写 DB，不得改 canonical 数据，不得让 AI 输出参与指标计算。
- `shadow_diff / shadow_diff_json / diff / records / points / raw_records / track_points` 禁止进入复盘主展示和 AI 输入。
- AI 洞察入口继续保持 P6.1 冻结态。

## 8. 未实现内容

本阶段只做文档规划：

- 未修改 `track.html`
- 未修改后端 API
- 未修改后端算法
- 未修改 AI prompt builder / normalizer
- 未修改 `docs/js_api_contract.json`
- 未修改 DB schema

## 9. 验证结果

已执行：

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：44 passed, 1 warning。

说明：warning 为本地 Python `urllib3` / LibreSSL 环境提示，与 P7.1 文档规划无关。

## 10. 下一步建议

进入 P7.2 顶部分析摘要带，实现复盘 Tab 内部的标题状态行、分析摘要带和 AI 冻结状态展示。
