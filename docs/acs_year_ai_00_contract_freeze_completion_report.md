---
title: ACS-Year-AI-00 契约与基线冻结完成报告
task: ACS-Year-AI-00
status: Done
updated: 2026-07-14
---

# ACS-Year-AI-00 契约与基线冻结完成报告

## 工程级提示词摘要

目标：建立年度 AI 总结开发可信起点，冻结后续任务使用的项目契约摘要，并同步旧 Phase7 文档中与通用记忆退役冲突的描述。

范围：只改文档、API 契约、执行日志和完成报告；只读审计 `career_backend.py`、`main.py`、`track.html` 与相关测试。

约束：不实现 Year Snapshot，不新增年度 API，不改变运行时代码行为，不恢复旧通用记忆语义。

完成定义：现行文档不再把旧通用记忆作为 AI Snapshot 白名单；全生涯 Snapshot 与年度 Snapshot 分离规则已冻结；完成报告列出真实代码基线；验证与 review 通过。

## 当前基线

- Career Snapshot：`career_backend.py` 中 `build_career_snapshot` 只构建全生涯 `acs.v1` 白名单 Snapshot。
- 持久化：`career_snapshots` 表当前只服务全生涯 Snapshot，未包含年度 source fingerprint 或年度报告缓存。
- 全生涯 fallback：`generate_career_insight` 只返回本地 fallback 洞察，不调用 `llm_backend`。
- pywebview API：`main.py` 当前只有 `get_latest_career_snapshot` 与 `generate_career_insight`，尚无年度只读或年度生成 API。
- 前端 AI 页：`track.html` 当前只有全生涯本地洞察页面，无年度模式、年份选择和年度状态渲染。
- 年度卡片：当前渲染为非交互 `div`，hover 文案仍为 `点击我试试`，尚未导航到年度 AI 总结页。

## 缺口确认

- 尚无 Year Snapshot。
- 尚无稳定 `source_fingerprint`。
- 尚无年度报告状态解析器。
- 尚无 `career_ai_insights`。
- 尚无年度 AI 输出缓存。
- 尚无真实年度 LLM pipeline。
- 尚无年度卡片导航和年度 AI 总结页 ViewModel。

## 契约同步

- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md` 已移除 `representative_memories` / `memory_count` 作为 AI 输入或 Overview 示例字段的描述。
- `docs/脉图运动生涯系统（ACS）开发任务清单.md` 已把旧 MemoryItem 能力改写为历史退役说明，并明确赛事照片内部存储不得进入 Snapshot。
- `docs/js_api_contract.json` 已明确 `get_latest_career_snapshot` / `generate_career_insight` 只服务全生涯 fallback，年度 AI 总结必须走独立 Year Snapshot、状态机、缓存和 API。
- `docs/acs_next_annual_ai_summary_execution_log.md` 已建立滚动项目契约摘要，供后续任务复用和刷新。

## 验证

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py tests/test_career_memory_retirement.py -q
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
! rg -n "representative_memories|memory_count" docs/脉图运动生涯系统（ACS）开发团队交付手册.md docs/脉图运动生涯系统（ACS）开发任务清单.md docs/js_api_contract.json
```

结果：

- `30 passed in 0.41s`
- `docs/js_api_contract.json` JSON 校验通过。
- 旧字段静态扫描无命中。

## Review 结论

通过。本任务只改动文档、API 契约和年度 AI 执行记录；未修改运行时代码，未新增 API，未改变现有全生涯 fallback 行为。review 中发现并修正了文档 JSON 示例中的重复 `metadata` 字段。
