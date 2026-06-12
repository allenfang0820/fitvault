# P7.18F 复盘泳道高度自适应与疲劳区间合并完成报告

## 任务目标

修复复盘 UI 在间歇训练等活动中的两个问题：

- 分层泳道在部分窗口尺寸或部分图层隐藏后显得过高。
- `fatigue_zones` 相邻同级别区间被拆成大量重复状态卡片。

## 设计稿对应关系

设计稿中的主图是紧凑的多泳道时间轴，泳道应保持稳定可读的高度，不应因固定大画布被过度拉伸。状态阶段和右侧状态区间应表达连续阶段，而不是把相邻同状态拆成大量重复卡片。

## 契约约束

- 不启用 AI 洞察，不新增 `call_llm`，不修改 AI prompt。
- 不写 DB，不新增持久化字段。
- `fatigue_zones` 仍来自后端 `get_fatigue_review(activity_id)` snapshot。
- 不从 DOM、截图、ECharts 像素、活动标题、设备、路线、`points` 或曲线形状推导疲劳区间。
- 合并后的 `fatigue_zones` 统一供主图疲劳背景带、状态阶段概览、右侧状态区间和事件锚点使用。

## 后端 Fatigue Zones 合并规则

新增 `_merge_fatigue_zones_for_review(zones, merge_gap_km=0.05)`：

- 过滤非法区间：
  - `start_km / end_km` 不可解析则丢弃。
  - `end_km <= start_km` 则丢弃。
- 按 `start_km / end_km / level` 排序。
- 合并相邻或间隔很小的同级别区间：
  - `same level`
  - `next.start_km <= current.end_km + 0.05`
- 不同 level 不合并。
- 合并后保留 `start_km / end_km / level`，可保留首个 `reason / description`。
- 合并只发生在内存 snapshot 构建阶段，不写 DB。

接入点：

- `_build_fatigue_review_snapshot()` 从 Resolver 取得 `fatigue_zones` 后立即合并。
- `collapse_events` 在合并后生成，因此事件锚点与主图、阶段条、右侧区间保持一致。

## 前端泳道高度策略

`_renderFatigueReviewLayeredEcharts()` 新增按可绘制泳道数量计算图表高度：

```js
var lanePx = lanes.length <= 3 ? 78 : (lanes.length <= 5 ? 72 : 64);
var computedHeight = Math.max(360, Math.min(560, lanes.length * lanePx + 84));
containerEl.style.height = computedHeight + 'px';
```

同时将 `fatigue-review-chart` 固定大 `min-height` 从 560px 降为 360px，使 JS 高度策略可以生效。

高度表现：

- 1-3 条泳道：360px。
- 4 条泳道：372px。
- 5 条泳道：444px。
- 6 条泳道：468px。
- 7 条泳道：532px。

## 验证样本

对用户截图中的 `2025-05-11 跑步` 活动做只读验证：

- 原始 Resolver 输出 `fatigue_zones`：26 段。
- 合并后 snapshot 输出：12 段。
- 相邻同级别 high/medium 已合并。
- medium/high 交替段保留，不强行合并不同状态。
- `collapse_events` 基于合并后的区间生成。

## 修改文件

- `main.py`
- `track.html`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_quality_gate.py`

## 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 97 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py
# 45 passed, 1 warning
```

## 后续建议

P7.18F 完成后进入 P7.19 复盘 UI 终轮视觉验收与冻结，重点检查普通跑、间歇跑、短距离活动三类样本。
