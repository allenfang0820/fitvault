---
title: ACS 年度 AI 总结 v3 叙事节奏与高光足迹完成报告
version: v0.1.0
updated: 2026-07-14
source:
  - docs/acs_next_annual_ai_summary_delivery_manual.md
  - docs/acs_next_annual_ai_summary_task_list.md
  - docs/acs_next_annual_ai_summary_execution_log.md
---

# ACS 年度 AI 总结 v3 叙事节奏与高光足迹完成报告

## 1. 目标

本轮解决年度报告阅读节奏偏统计化的问题：

- 不再首句一次性公布活动、里程、时长、赛事、PB 和成就等全部年度数字。
- 数据按故事节奏逐步展开，并解释“为什么值得记住”。
- 增加可信高光时刻，包括赛事、PB、成就、最长距离、最长时长、最高海拔、累计爬升和代表城市。
- 城市足迹进入报告，但只来自活动定位事实；地域文化提示来自受控词典。

## 2. 主要变更

- `career_backend.py`
  - Year Snapshot 升级为 `acs.year.v2`。
  - 新增 `highlight_moments` 与 `city_moments`。
  - 新增受控城市文化词典：成都/火锅、神户/和牛、北京/胡同和中轴线、上海/江边和城市夜色、杭州/西湖。
  - 新增 `fact_leads` 分层事实引导，并保留 `fact_lead` 兼容字段。
  - 报告校验器支持 `footprints` 章节和后端高光引用。

- `llm_backend.py`
  - Prompt 升级为 `acs.year.summary.zh-CN.v3`。
  - 明确禁止 opening 或第一段一次性公布全部年度数据。
  - 明确 `highlight_moments` 与 `city_moments` 的使用边界。

- `track.html`
  - v2 文章渲染优先展示 `fact_leads`，旧报告回退 `fact_lead`。

- 文档与契约
  - 交付手册新增 v3 叙事节奏、高光候选池、城市足迹与受控文化词典。
  - 任务清单新增并完成 `ACS-Year-AI-10A` 至 `10C`。
  - `docs/js_api_contract.json` 同步 `highlight_moments`、`city_moments` 和 v3 边界。

## 3. 验证

```text
.venv312/bin/python -m pytest $(rg --files tests | rg 'career_year') -q
109 passed, 10 subtests passed in 0.90s

.venv312/bin/python -m pytest $(rg --files tests | rg '^tests/test_.*(career_|records_center).*\.py$') -q
594 passed, 38 subtests passed in 3.12s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

## 4. 真实链路验收

```text
generate_career_year_insight(2026)
generation.status = generated
report_state = ready
snapshot_version = acs.year.v2
prompt_version = acs.year.summary.zh-CN.v3
model_id = openclaw-default
schema_version = acs.year.report.v2
fact_leads_count = 5
sections = annual_story, races, progress, footprints, rhythm, comparison
generated_at = 2026-07-14T19:52:35+08:00
```

真实链路中发现并修复：`footprints` 章节引用 `achievement:first_city:*` 时被误判为 evidence 类型不匹配。现已允许后端 first_city achievement 作为城市足迹证据。

## 5. 未执行项

- 未执行桌面视觉人工验收。
- 未打包 DMG。
