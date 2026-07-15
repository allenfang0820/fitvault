# ACS-Year-AI-06A 年度 Prompt、模型调用与严格 JSON 输出完成报告

## 状态

Done。

## 交付内容

- 新增年度 Prompt version：`acs.year.summary.zh-CN.v1`。
- 新增年度 Prompt 白名单 payload：`career_year_summary_prompt_payload()`。
- 新增年度 Prompt assembler：`build_career_year_summary_messages()`。
- 新增严格 JSON 解析：`_strict_json_object_from_text()`。
- 新增一次格式修复消息：`_career_year_summary_repair_messages()`。
- 新增受控调用入口：`generate_career_year_summary()`。

## 契约边界

- Prompt 只接收 Year Snapshot 白名单字段。
- 禁止字段、前端 payload、token、路径、points、track_json 不进入 Prompt。
- 当前部分年度要求使用“截至当前数据周期”语气。
- Prompt 明确禁止伤病、心理、生活事件、训练动机、年度等级、详细训练计划和医疗建议。
- 输出必须是严格 JSON；Markdown code fence 或附加解释会触发一次修复。
- LLM 配置来自 `load_llm_config()` / `generate_text()` 链路；测试可注入 fake client。
- 日志不输出完整 Prompt、Snapshot 或原始 AI 响应。

## 验证

```text
.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py -q
5 passed in 0.10s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_insight_service.py -q
11 passed in 0.11s

.venv312/bin/python -m py_compile llm_backend.py
passed
```

## Review 结论

通过。06A 新增路径未接前端生成 API，未真实调用网络测试，fake client 覆盖配置传递、严格 JSON 和一次修复；日志只记录 year、fingerprint 前缀、prompt version、model、耗时和状态。
