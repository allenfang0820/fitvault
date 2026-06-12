# P7.20 复盘 UI 契约标注去工程化完成报告

## 1. 任务目标

P7.20 的目标是清理复盘 UI 中面向用户展示的工程化契约标注，让页面从“调试/契约验收视角”回到“运动复盘产品视角”。

本阶段只处理用户可见文案，不修改复盘数据契约、不开放 AI 洞察、不改变后端算法、不写 DB。

## 2. 清理原则

本轮采用以下边界：

- 用户可见 UI 不展示 `data.xxx`、`curves.xxx`、`fatigue_zones`、`collapse_events`、`distance_curve`、`Resolver`、`DOM 推导` 等工程词。
- 内部变量、函数名、测试契约、后端白名单和质量门禁继续允许使用契约字段名。
- 契约字段名只作为开发和测试约束存在，不作为普通用户的阅读内容存在。
- 文案改写必须保持事实来源不变，不能因为去工程化而引入前端推导。

## 3. 已完成的 UI 文案回正

顶部摘要：

- `后端权威快照` 调整为 `本次复盘概览`。
- 摘要说明调整为面向用户的复盘描述。
- 加载态从接口/后端快照说明调整为 `正在读取本次活动的复盘数据。`
- `FIT + Resolver` 调整为 `运动文件解析完成`。

主图区域：

- 主图副标题调整为 `按距离展开本次活动的关键变化`。
- 数据边界说明调整为 `心率、配速、海拔和疲劳阶段会在同一条距离轴上对照显示。`
- 图例不再展示 `curves.hr`、`curves.speed`、`curves.altitude`、`curves.efficiency`、`curves.gap`、`curves.grade`、`curves.terrain_load`。
- 距离轴空态从契约字段提示调整为 `距离轴暂不可用`。
- 距离轴状态从 `distance_curve = ...` 调整为 `距离轴已校准 · N 个采样点`。

右侧摘要与空态：

- 上下文空态调整为 `本次活动未携带上下文标签`、`暂无上下文`。
- 事件空态调整为 `暂无事件`。
- 状态区间空态调整为 `暂无阶段` / `暂无区间`。
- 建议空态调整为 `暂时没有可展示的训练建议。`、`暂无建议`。
- 风险、事件、区间等说明改为自然中文，不再暴露字段路径。

AI 入口：

- AI 按钮 tooltip 调整为 `AI 洞察功能即将开放`。
- 按钮仍保持冻结状态。

## 4. 契约保留情况

已确认以下契约仍保留：

- 复盘 Tab 事实源仍为 `get_fatigue_review(activity_id)` 后端 snapshot。
- 主图曲线仍只读取 `data.curves`。
- 距离轴仍只读取 `data.curves.distance`。
- 疲劳区间仍只读取 `data.fatigue_zones`。
- 事件图钉仍只读取 `data.collapse_events`。
- 建议仍只读取 `data.advice` 和 `data.disclaimer`。
- 前端未从 DOM、截图、ECharts 像素、活动标题、设备、路线或曲线走势推导事实。
- 契约测试仍允许在代码层检查字段路径，避免去工程化变成契约放松。

## 5. AI 冻结核对

通过。

- `fr-ai-generate-btn` 仍为 `disabled`。
- `aria-disabled="true"` 仍保留。
- 未新增 `onclick="onFatigueReviewAiInsight()"`。
- 未新增前端 `call_llm` 调用路径。
- 未改动 AI prompt、normalizer 或后端 sentinel 行为。

## 6. 修改文件

- `track.html`
- `tests/test_v9_0_detail_tab_review.py`
- `tests/test_fatigue_review_quality_gate.py`
- `docs/p7_20_fatigue_review_ui_contract_label_cleanup_completion_report.md`

## 7. 测试结果

```bash
python3 -m pytest tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
# 99 passed, 1 warning

python3 -m pytest tests/test_fatigue_review_ai_insight_p6.py tests/test_fatigue_review_ai_preflight_p8.py
# 13 passed, 1 warning
```

warning 为本地 Python `urllib3` / LibreSSL 环境提示，不是 P7.20 回归失败。

## 8. 剩余风险

- 本轮是静态文案和测试门禁收口，未重新做真实浏览器截图对照。
- 代码内部仍会出现契约字段名，这是正常现象；P7.20 禁止的是用户可见展示，不是开发契约本身。
- 后续新增复盘模块时，仍需同步检查用户文案，避免再次把字段路径直接显示到页面上。

## 9. 下一步建议

建议先做一次备份提交和 push，再进入 P8.1「复盘 AI 洞察最小闭环打开按钮」。

P8.1 仍需遵守：

- 只解除经过审查的 AI 入口冻结。
- 前端只传 sentinel 和 activity_id。
- AI snapshot 只由后端白名单构建。
- AI 输出只做解释层展示，不参与指标、曲线、疲劳区间、事件计算。
- 不写 DB。
