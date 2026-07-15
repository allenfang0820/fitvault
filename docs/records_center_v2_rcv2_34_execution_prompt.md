# RCV2-34 工程级提示词：纪录详情、候选处理与 Activity 回跳

## 目标

在 Records Center V2 shell 中统一多运动纪录详情、候选确认/拒绝和来源 Activity 回跳体验。前端只消费后端 ViewModel，不修改候选事实，不把候选、analysis curve 或 model estimate 提前显示为正式纪录。

## 范围

- 在 `track.html` 新增 V2 record detail panel，并接入 `get_career_record_detail`。
- 当前纪录卡提供“详情/来源 Activity”主操作；详情展示值、前一纪录/提升、Scope、来源模式、质量、range 摘要、Activity 安全摘要与历史提示。
- 分段/路线/泳段等 range 只展示后端安全摘要，不暴露 raw stream、track、GPS、路径或可还原路线。
- 候选卡展示后端候选 ViewModel 的值、Scope、原因、置信度和来源 Activity。
- 候选确认/拒绝只调用 `decide_career_record_candidate({ candidate_id, decision })`；提交期间禁用按钮，成功后局部刷新 Records/Candidates/Analysis，失败时局部提示并恢复按钮。
- Activity Detail 跳转统一使用后端 `detail_link`，且 `source` 保持 `career`。
- 新增 RCV2-34 前端契约测试。

## 约束

- 前端不得修改或提交候选值、距离、时间、功率、海拔、Activity、record key、scope、range、reason 或 evidence。
- 前端不得计算 PB/纪录事实、前一纪录、提升、Scope、质量、置信度、axis direction 或 range 语义。
- `analysis_only`、`model_only`、curve cache 和 route comparison 不进入候选操作。
- 保持 V1 `get_career_pb*` 和旧 PB 面板兼容；本任务只增强 V2 records shell。
- 不写真实库；确认/拒绝代码只接通既有 API，不执行真实数据批处理。
- 不打包。

## 预期文件

- `track.html`
- `tests/test_career_records_v2_detail_candidate_frontend.py`
- `docs/records_center_v2_rcv2_34_completion_report.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- `docs/records_center_v2_rolling_contract_summary.md`

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- 五运动 current record 均可打开 V2 detail，并可从后端 `detail_link` 回跳 Activity。
- 候选只显示为候选，不进入 current record；确认/拒绝只传 candidate id 与 decision。
- 提交防重复、成功刷新、失败局部反馈可静态验证。
- Detail、Candidate、Activity 跳转路径均不暴露 raw FIT、track、power stream、GPS、路径、schema、设备或体重历史。
