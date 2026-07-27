# 记录中心与时间轴产品文案回归验收报告

日期：2026-07-22

## 验收范围

本次验收覆盖用户提出的记录中心、时间轴、年度快照与年度 AI 总结相关诉求：

- “游泳”标签需区分为“泳池游泳”和“公开水域游泳”。
- 记录中心不展示“候选/认证”流程，只客观呈现当前最佳与历史成绩曲线。
- “演进”不再作为用户可见标签。
- 活动成绩曲线区分“当前最佳”和“刷新记录”图钉颜色。
- 当前最佳与刷新记录节点可跳转运动详情页。
- 刷新记录进入生涯时间轴里程碑轨道，并可作为年度报告素材。
- 用户可见文案不泄漏 `V2`、`已接入`、`record_breaking`、`metric_series`、`candidate`、`active` 等工程表达。

## 本轮发现与修复

验收扫描中发现 `career_backend.py::_career_insight_record_highlights()` 仍会把年度 AI 总结 fallback highlights 拼成“当前纪录”和“待确认纪录候选”。该内容会进入报告素材，属于用户可见文案漏点。

已做最小修复：

- 将 fallback highlights 的“当前纪录”改为“当前最佳”。
- 不再把候选数量写入面向用户的 fallback highlights。
- 更新 `tests/test_career_insight_api_skeleton.py`，要求 fallback highlights 包含“当前最佳”，并禁止“当前纪录/候选”进入该输出。

## 扫描结论

旧中文文案扫描后，命中分为三类：

- 正常的测试反向断言：例如禁止“记录中心 V2 已接入”“时间轴已接入”“候选事件待确认”。
- 正常的内部/历史契约：例如后端候选处理 API、数据库状态、测试 fixture 中的 `candidate`、`active`。
- 非本次范围文案：例如 Garmin 登录失败里的“认证失败”。

未发现当前记录中心、时间轴、总览、年度结构、年度 AI 总结 fallback 的用户可见路径继续输出旧工程文案。

## 验证命令

```bash
git status --short
```

确认 worktree 原本已有大量未提交改动；本轮只触碰验收相关文件。

```bash
rg -n "记录中心 V2 已接入|记录中心 V2 接口|V2 已接入|赛事档案已接入|时间轴已接入|年度结构已接入|生涯总览已接入|当前纪录|演进|候选|认证" track.html career_backend.py tests/test_career_records_v2_frontend_shell.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_responsive_a11y_frontend.py tests/test_career_archives_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_record_event_nodes.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_year_snapshot_evidence.py tests/test_career_overview_frontend_render.py tests/test_career_insight_api_skeleton.py tests/test_career_records_v2_snapshot_ai_trends.py
```

结果：旧词只剩在测试禁止断言、内部候选处理契约、测试 fixture 或非本次范围文案中。

```bash
PYTHONPATH=. .venv312/bin/python -m pytest tests/test_career_records_v2_frontend_shell.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_responsive_a11y_frontend.py tests/test_career_archives_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_record_event_nodes.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_year_snapshot_evidence.py tests/test_career_overview_frontend_render.py tests/test_career_insight_api_skeleton.py tests/test_career_records_v2_snapshot_ai_trends.py -q
```

结果：`133 passed in 0.85s`

```bash
.venv312/bin/python -m py_compile career_backend.py
git diff --check -- track.html career_backend.py tests/test_career_records_v2_frontend_shell.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_responsive_a11y_frontend.py tests/test_career_archives_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_record_event_nodes.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_year_snapshot_evidence.py tests/test_career_overview_frontend_render.py tests/test_career_insight_api_skeleton.py tests/test_career_records_v2_snapshot_ai_trends.py
```

结果：均通过，无输出。

## 建议人工 UI 验收路径

- 生涯总览：检查“年度结构已生成”“生涯总览已生成”。
- 记录中心：检查运动类型中“泳池游泳/公开水域游泳”是否区分；页面无“候选/认证/演进/V2/已接入”。
- 记录中心曲线：检查黄色“当前最佳”和红色“刷新记录”图钉区分，并可点击进入活动详情。
- 生涯时间轴：检查刷新记录以“刷新纪录”里程碑出现，并可点击进入活动详情。
- 年度 AI 总结：检查 fallback highlights 不再出现“当前纪录/候选”。

## 边界

- 后端候选处理 API、数据库状态、测试 fixture 中仍保留 `candidate`、`active`、`record_breaking`、`metric_series` 等内部契约。
- 本轮没有处理同步性能、Garmin/COROS、FIT 导入或疲劳建议文案。
- 本轮没有启动应用做真实浏览器截图验收，仅完成代码级扫描、单元/契约测试和静态检查。
