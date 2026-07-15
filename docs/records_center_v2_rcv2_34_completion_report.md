# RCV2-34 完成报告：纪录详情、候选处理与 Activity 回跳

## 完成内容

- `track.html` 新增 Records Center V2 详情卡：
  - 接入 `get_career_record_detail({ record_id })`。
  - 展示后端 ViewModel 中的 `metric`、`improvement`、`scope`、`source_mode`、`quality`、`range` 和 `activity_summary`。
  - range 只通过白名单字段展示安全摘要，不解析或展示 raw 数据。
- 当前纪录卡新增：
  - “查看详情”操作，复用当前选中纪录的分析加载链路。
  - “来源 Activity”操作，使用后端 `detail_link`，并继续走 `source="career"` 回跳。
- 候选卡新增：
  - 展示候选值、Scope、置信度、reason codes 和来源 Activity。
  - 确认/拒绝只调用 `decide_career_record_candidate({ candidate_id, decision })`。
  - 提交期间禁用同卡按钮，成功后刷新 Records Center，失败时局部反馈并恢复按钮。
- 保持旧 V1 PB detail/candidate 面板兼容；本任务只增强 V2 records shell。

## 契约复核

- 前端不提交候选值、距离、时间、功率、海拔、Activity、record key、scope、range、reason 或 evidence。
- 前端不计算纪录事实、前一纪录、累计提升、Scope、质量、置信度或 axis direction。
- `analysis_only` / `model_only` / curve cache / route comparison 没有进入候选操作。
- Activity 回跳继续使用 `detail_link.source="career"`；非 career source 会被既有回跳函数拒绝。
- 未写真实库，未触发 rebuild/apply，未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
# 15 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
# 16 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 自审结论

- diff 触达范围符合 RCV2-34：`track.html`、新增前端契约测试和任务文档。
- 候选处理路径未调用旧 `decide_career_pb_candidate`。
- range 摘要函数未包含 raw/track/GPS/polyline/path/schema 类字段。
- 无阻塞项。
