---
title: ACS 年度 AI 总结执行日志
version: v0.1.0
updated: 2026-07-14
source:
  - docs/acs_next_annual_ai_summary_task_list.md
  - docs/acs_next_annual_ai_summary_delivery_manual.md
---

# ACS 年度 AI 总结执行日志

本文记录年度 AI 总结任务循环的工程级提示词、滚动契约摘要、基线证据、验证结果和 review 结论。每个后续任务完成后必须追加或更新本日志，作为继续执行时的默认项目契约摘要。

## 滚动项目契约摘要

- `Activity` 是唯一事实源；Race、PB、Achievement、Milestone 等语义只由对应 Resolver 产生。
- Year Snapshot 是年度 AI 唯一允许消费的上下文；前端不得扫描 Activity、DOM 或本地缓存拼装年度事实。
- AI 只写结构化叙事，不写 canonical 事实；年度统计、日期、成绩、事件身份和 `detail_link` 必须由后端 Resolver-backed evidence 回填。
- v3 报告必须先建立年度主线，再分层揭示事实；不得在第一句话一次性公布所有年度统计。
- v3 高光时刻来自后端可信候选池，覆盖赛事、PB、成就、最长距离、最长时长、最高海拔、累计爬升阈值和代表城市。
- 城市足迹必须来自活动定位事实；城市文化提示只能来自受控词典，AI 不得自由常识扩写或暗示用户实际吃喝旅行。
- 全生涯 Career Snapshot 与年度 Year Snapshot 必须按 scope、年份、版本、ID、fingerprint、缓存键和 API 分离。
- 旧通用记忆、赛事照片内部存储、媒体引用、本地路径、raw FIT、points、track_json、SQLite schema、token 和 Provider 授权信息不得进入 Year Snapshot 或 Career Snapshot。
- 年度卡片始终可点击，但只导航到 AI 总结页的对应年度模式；点击年度卡片不得调用 LLM。
- 年度报告按年份沉淀；相同 `year + source_fingerprint` 不得重复调用 LLM。
- 报告是否可更新只由年度事实指纹变化决定；系统日期、`generated_at`、`as_of_date`、traceId、Prompt 版本、模型版本、照片或 UI 设置不得单独改变事实指纹。
- 更新失败、超时、非 JSON 或 evidence 校验失败不得覆盖旧报告。
- 现有全生涯 `generate_career_insight` fallback 必须保留，直到另有全生涯真实 AI 迁移任务。

## ACS-Year-AI-10A 工程级提示词

目标：冻结 v3 分层叙事、高光候选池与城市足迹契约，让年度报告从统计摘要升级为更有阅读节奏和分享欲的完整年度故事。

范围：只修改年度 AI 总结交付手册、任务清单和执行日志；不改运行时代码。

约束：不得放开 AI 自由使用常识；不得让 AI 自行判定 PB、赛事、城市或里程碑；不得改变模型配置边界；不打包 DMG。

预期文件：

- `docs/acs_next_annual_ai_summary_delivery_manual.md`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`

验证命令：

```bash
rg -n "v3|分层事实|高光|城市足迹|受控文化词典" docs/acs_next_annual_ai_summary_delivery_manual.md docs/acs_next_annual_ai_summary_task_list.md docs/acs_next_annual_ai_summary_execution_log.md
```

完成定义：文档明确 v3 报告不得首句一次性报完全部数据；冻结后端高光候选类型、城市文化词典边界、动态省略规则和 AI 禁止推断规则；清单新增 10A-10C 后续任务。

## ACS-Year-AI-10A 结果

状态：Done。

实现摘要：

- 交付手册新增 v3 叙事节奏升级，冻结“先主线、再逐层揭示数据”的报告节奏。
- 交付手册新增高光候选池和排序原则，覆盖赛事、PB、成就、最长距离、最高海拔、累计爬升和城市足迹。
- 交付手册新增受控城市文化词典，明确成都/火锅、神户/和牛等只能作为城市文化提示，不得暗示用户实际消费或旅行经历。
- 任务清单新增 `ACS-Year-AI-10A`、`10B`、`10C` 和 Milestone F。

Review 结论：通过。本任务只改文档和任务状态，未修改运行时代码。

下一任务：`ACS-Year-AI-10B`。

## ACS-Year-AI-10B 工程级提示词

目标：实现 v3 Year Snapshot 线索、Prompt 和报告校验，让年度报告能按分层事实、高光时刻和城市足迹组织内容。

范围：允许修改 `career_backend.py`、`llm_backend.py`、`track.html`、年度 AI 相关测试、`docs/js_api_contract.json`、年度任务文档和执行日志。

约束：不改变前端生成 API payload，仍只允许 `{ year }`；不写死模型，继续使用脉图运行时 LLM 配置；AI 不得自行生成事实；城市文化提示只能来自后端受控词典；旧 v1/v2 缓存继续可读，不因 prompt/schema 升级暴露“无事实变化重新生成”。

预期文件：

- `career_backend.py`
- `llm_backend.py`
- `track.html`
- `tests/test_career_year_snapshot_contract.py`
- `tests/test_career_year_snapshot_activity_aggregation.py`
- `tests/test_career_year_ai_report_validation.py`
- `tests/test_career_year_llm_prompt.py`
- `tests/test_career_year_insight_render_frontend.py`
- `docs/js_api_contract.json`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py tests/test_career_year_generate_api.py tests/test_career_year_insight_render_frontend.py -q
.venv312/bin/python -m py_compile career_backend.py llm_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

完成定义：Snapshot 包含稳定、安全的 `highlight_moments` 与 `city_moments`；Prompt/schema 升级为 v3 并要求分层节奏；校验器输出分层事实引导且不首句报完全部数字；前端能渲染 v3 文章；定向测试和 diff review 通过。

## ACS-Year-AI-10B 结果

状态：Done。

实现摘要：

- Year Snapshot 升级为 `acs.year.v2`，新增 `highlight_moments` 与 `city_moments`。
- 后端高光候选池按 Resolver evidence 优先，补充最长距离、最长时长、最高海拔、年度累计爬升阈值和代表城市，最多 5 条。
- 城市文化提示来自受控词典，例如成都/火锅、神户/和牛；仅作为城市文化提示进入 Snapshot，不表示用户实际消费或旅行经历。
- Prompt 升级为 `acs.year.summary.zh-CN.v3`，要求先建立年度主线，再逐层揭示事实，并禁止 opening 或第一段一次性公布全部年度数据。
- 报告校验器支持 `footprints` 章节、后端高光引用和 `fact_leads` 分层事实引导；保留 `fact_lead` 兼容旧前端和旧报告结构。
- 前端文章渲染优先展示 `fact_leads`，无该字段时回退 `fact_lead`。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py tests/test_career_year_generate_api.py tests/test_career_year_insight_render_frontend.py -q
50 passed, 6 subtests passed in 0.57s

.venv312/bin/python -m pytest tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_insight_read_api.py tests/test_career_year_insight_service.py tests/test_career_year_report_state.py tests/test_career_year_request_isolation_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py -q
48 passed, 4 subtests passed in 0.40s

.venv312/bin/python -m pytest $(rg --files tests | rg 'career_year') -q
109 passed, 10 subtests passed in 0.90s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

Review 结论：通过。新增字段只来自 Activity 安全字段和 Resolver-backed evidence，不读取 raw FIT、points、track_json、本地路径、照片或 token；前端生成 payload 仍只有 `{ year }`；模型仍来自运行时配置，不写死在功能内。真实 OpenClaw 首轮暴露 `footprints` 章节引用 `achievement:first_city:*` 被校验器拒绝的问题；已修复为允许后端 first_city achievement 作为城市足迹证据。

下一任务：`ACS-Year-AI-10C`。

## ACS-Year-AI-10C 结果

状态：Done。

验证结果：

```text
.venv312/bin/python -m pytest $(rg --files tests | rg '^tests/test_.*(career_|records_center).*\.py$') -q
594 passed, 38 subtests passed in 3.12s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

真实链路验收：

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

Review 结论：通过。年度相关测试、ACS 宽回归与真实 OpenClaw 生成均通过；未执行 DMG 打包。

下一任务：`ACS-Year-AI-11A`。

## ACS-Year-AI-11A 工程级提示词

目标：在 v3 事实边界和高光足迹能力不变的前提下，把年度报告语气升级为更有分享欲和成就感的年度运动故事。

范围：允许修改 `llm_backend.py`、`career_backend.py`、`track.html`、年度 Prompt / 校验 / 服务 / 前端测试、交付手册、任务清单、执行日志和完成报告；不得修改模型配置来源、生成 API payload、Year Snapshot 事实语义或打包 DMG。

约束：Prompt 只消费 Year Snapshot；前端生成仍只传 `{ year }`；模型仍来自脉图运行时 LLM 配置；v2 旧报告继续可读；v3 schema 只作为格式升级门禁，不改变 `source_fingerprint`；AI 不得编造城市经历、饮食消费、旅行、身体感受、心理动机或“最强/失败”等等级评价；禁止营销鸡血。

验证命令：

```bash
.venv312/bin/python -m pytest $(rg --files tests | rg 'career_year') -q
.venv312/bin/python -m py_compile career_backend.py llm_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
git diff --check -- llm_backend.py career_backend.py track.html tests/test_career_year_llm_prompt.py tests/test_career_year_ai_report_validation.py tests/test_career_year_generate_api.py tests/test_career_year_insight_service.py tests/test_career_year_insight_render_frontend.py docs/acs_next_annual_ai_summary_delivery_manual.md docs/acs_next_annual_ai_summary_task_list.md docs/acs_next_annual_ai_summary_execution_log.md docs/js_api_contract.json
```

完成定义：Prompt 版本为 `acs.year.summary.zh-CN.v4`；当前内容 schema 为 `acs.year.report.v3`；标题、副标题、opening、closing、letter 和 share_caption 更有截图分享欲与成就感；v2/v3 前端兼容；旧 v2 可触发受控升级；年度定向测试、静态校验和 adaptive diff review 通过。

## ACS-Year-AI-11A 结果

状态：Done。

实现摘要：

- Prompt 升级为 `acs.year.summary.zh-CN.v4`，明确目标读感是“用户读完会有成就感，也愿意截图分享”。
- 当前报告 schema 升级为 `acs.year.report.v3`，用于触发同事实指纹旧 v2 报告的受控格式升级。
- 前端文章渲染同时接受 `acs.year.report.v2` 和 `acs.year.report.v3`，旧报告继续可读。
- 后端补充 closing、letter_to_next_year 与 share_caption 的不完整句尾清理，避免分享文案或收束语停在冒号、顿号、分号等不完整结尾。
- 真实 2026、2025、2024 年度报告已重新生成到 v4/v3 schema；2025 因模型未选择有效城市证据而自然省略 footprints 章节，符合“无有效证据自然省略”规则。

验证结果：

```text
.venv312/bin/python -m pytest $(rg --files tests | rg 'career_year') -q
110 passed, 10 subtests passed

.venv312/bin/python -m pytest $(rg --files tests | rg '^tests/test_.*(career_|records_center).*\.py$') -q
618 passed, 46 subtests passed

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

Review 结论：通过。v4 仅升级语气和当前结构 schema，不改变 Snapshot、fingerprint、模型配置来源、前端 payload 或 canonical 事实边界；所有 AI 文本仍经 schema、章节、evidence、长度和安全清洗后展示。宽回归中发现的历史前端 CSS 锚点缺失已用零行为注释恢复。未执行 DMG 打包。

下一任务：无。除最终 DMG 打包外，年度 AI 总结当前任务清单已完成。

## ACS-Year-AI-00 工程级提示词

目标：建立年度 AI 总结开发可信起点，冻结后续任务使用的项目契约摘要，并同步旧 Phase7 文档中与通用记忆退役冲突的描述。

范围：只允许修改现行文档、API 契约、年度 AI 执行日志和 00 完成报告；允许只读审计 `career_backend.py`、`main.py`、`track.html` 和相关测试。

约束：不得实现 Year Snapshot；不得新增年度 API；不得改变运行时代码行为；不得删除历史完成报告；不得恢复 `representative_memories`、`memory_count` 或旧通用 MemoryItem 作为 AI 输入。

预期文件：

- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_00_contract_freeze_completion_report.md`
- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/js_api_contract.json`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py tests/test_career_memory_retirement.py -q
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
! rg -n "representative_memories|memory_count" docs/脉图运动生涯系统（ACS）开发团队交付手册.md docs/脉图运动生涯系统（ACS）开发任务清单.md docs/js_api_contract.json
```

完成定义：现行文档不再把旧通用记忆作为 AI Snapshot 白名单；交付手册、主任务清单和 API 契约明确全生涯与年度链路分离；完成报告列出当前代码基线和缺口；定向测试与静态契约检查通过；diff review 确认没有运行时代码行为变化。

## ACS-Year-AI-00 基线证据

- `career_backend.py` 现有 `career_snapshots` 表只包含 `id`、`snapshot_type`、`generated_at`、`content_json`、`source_version`、`created_at`，尚无年度 fingerprint 或年度 AI 输出缓存。
- `career_backend.py` 现有 `build_career_snapshot` 产出全生涯 `snapshot_version='acs.v1'`，包含 summary、primary_sport、PB、records、achievement、timeline 和 status。
- `career_backend.py` 现有 `generate_career_insight` 只支持 `refresh_snapshot`，返回本地 fallback，不调用 `llm_backend`。
- `main.py` 暴露 `get_latest_career_snapshot` 和 `generate_career_insight`，尚无 `get_career_year_insight` 或 `generate_career_year_insight`。
- `track.html` AI 总结页当前只有“AI 生涯总结 · 生涯洞察”和“刷新本地洞察”，页面文案明确当前不会调用 AI。
- `track.html` 年度卡片由 `careerSeasonCardHtml` 渲染为非交互 `div`，`data-career-season-hint` 仍为 `点击我试试`。
- 当前仓库未发现 `career_ai_insights`、`source_fingerprint`、`year_snapshot`、年度报告状态解析器或真实年度 LLM 入口。

## ACS-Year-AI-00 结果

状态：Done。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py tests/test_career_memory_retirement.py -q
30 passed in 0.41s

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed

rg -n "representative_memories|memory_count" docs/脉图运动生涯系统（ACS）开发团队交付手册.md docs/脉图运动生涯系统（ACS）开发任务清单.md docs/js_api_contract.json
no matches
```

Review 结论：本任务只改动文档、API 契约和年度 AI 执行记录；未修改运行时代码，未新增 API，未改变现有全生涯 fallback 行为。发现并修正了文档 JSON 示例中的重复 `metadata` 字段。

下一任务：`ACS-Year-AI-01A`。

## ACS-Year-AI-01A 工程级提示词

目标：冻结 `acs.year.v1` Year Snapshot schema、年度安全白名单、递归禁止字段集合、合法年份范围和无数据年份行为，为后续聚合、指纹、状态机、缓存和 LLM 提供同一个年度数据契约。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_contract.py`、更新任务状态和执行日志。仅在需要登记公开 API 时修改 `docs/js_api_contract.json`，本任务未新增 API，因此不修改 API 契约。

约束：不实现真实 LLM；不持久化 Snapshot；不让前端接触 Snapshot 原文；不实现年度 Activity 聚合、Resolver evidence 聚合、同期比较或 fingerprint 计算；不得改变现有全生涯 `build_career_snapshot` / `generate_career_insight` fallback 行为。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_contract.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_01a_snapshot_contract_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：Year Snapshot 顶层字段、字段类型、空值语义、排序规则、数值精度描述、安全 Activity / Resolver 字段、递归禁止字段、合法年份和 no-data shape 均由代码和测试冻结；手册 7.2 样例可由测试 fixture 表达；定向测试和 diff review 通过。

## ACS-Year-AI-01A 结果

状态：Done。

实现摘要：

- 新增 `CAREER_YEAR_SNAPSHOT_VERSION='acs.year.v1'`、`CAREER_YEAR_SNAPSHOT_SCOPE='year'`、顶层字段顺序、字段 schema 描述、Activity 安全字段白名单和 Resolver evidence 字段白名单。
- 新增年度递归禁止字段集合，覆盖 raw FIT、points、track、路径、媒体、SQL、token、Provider 配置和已退役记忆字段。
- 新增 `build_career_year_snapshot` no-data shell，固定 12 个月 `month_digest`、零值 `summary`、空 evidence、不可用 comparison 和空 `source_fingerprint`。
- 新增 `validate_career_year_snapshot_contract`，校验顶层字段顺序、版本、scope、合法年份、period、summary、列表排序、comparison、data_quality、fingerprint 类型和递归禁止字段。
- 新增 rich / light / no-data / current partial year 测试 fixture。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
13 passed in 0.13s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。本任务未新增持久化、未调用 LLM、未改前端、未改全生涯 fallback；`conn` 参数保留为后续聚合任务扩展点，当前显式丢弃以避免 01A 越界读取数据库。

下一任务：`ACS-Year-AI-01B`。

## ACS-Year-AI-01B 工程级提示词

目标：实现 Year Snapshot 的 Activity 事实层，只读取目标年份未删除有效 Activity，产出稳定年度 summary、sport_breakdown、12 个月 month_digest 和 available_years。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_activity_aggregation.py`、更新任务状态、执行日志和完成报告。

约束：不把普通 Activity 全量列表放入 Snapshot；不从标题推断运动类型、城市、赛事或里程碑；不读取轨迹点补算年度距离；不实现 Resolver evidence、同期比较、fingerprint、持久化、API 或前端。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_activity_aggregation.py`
- `tests/test_career_year_snapshot_contract.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_01b_activity_aggregation_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：Snapshot 只包含目标年份有效 Activity 聚合事实；单运动、多运动、空月份、删除 Activity、跨年边界、距离/时长 canonical 字段和 available_years 均有测试；旧 Career Snapshot 测试保持通过；diff review 确认没有普通 Activity 明细、标题、points、路径或媒体进入 Snapshot。

## ACS-Year-AI-01B 结果

状态：Done。

实现摘要：

- `build_career_year_snapshot` 现在读取目标年份有效 Activity，填充年度 summary、sport_breakdown、month_digest、data_through 和 data_quality。
- 新增 `get_career_year_snapshot_available_years`，只基于有效 Activity 日期返回倒序年份。
- 月度摘要固定 12 项，无活动月份使用明确零值。
- 每月 `primary_sport` 使用活动数、距离和 sport 名称作为稳定排序规则。
- 距离统一保留 1 位小数，时长使用整数秒。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py -q
18 passed in 0.11s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。输出仍保持 01A 顶层 schema，不包含普通 Activity 明细、活动标题、points、track、本地路径、照片或媒体引用；未改全生涯 Career Snapshot fallback，未新增持久化和 LLM 调用。

下一任务：`ACS-Year-AI-01C`。

## ACS-Year-AI-01C 工程级提示词

目标：建立年度 Resolver evidence catalog，为 AI 的关键时刻提供唯一可引用、可校验、可回跳 Activity Detail 的后端证据集合。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_evidence.py`、更新任务状态、执行日志和完成报告；可运行 Race / PB / Achievement 现有 resolver/API 回归。

约束：只读取目标年份 active Race、PB、Achievement / Milestone 结果；每条 evidence 必须绑定目标年份有效 Activity；不读取候选、inactive、rejected、superseded 结果；不把照片、缩略图、媒体引用、故事或 display metadata 原始证据放入 evidence；不让 AI 生成 evidence ID；不实现同期比较、fingerprint、持久化、API 或前端。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_evidence.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_01c_evidence_catalog_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py -q
.venv312/bin/python -m pytest tests/test_career_achievement_resolver.py tests/test_career_seasons_api.py -q
.venv312/bin/python -m pytest tests/test_career_race_resolver.py tests/test_career_pb_resolver.py tests/test_career_races_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：年度 evidence catalog 包含稳定 `evidence_id`、`activity_id`、`type`、`title`、`date`、`value`；排序按 `date + type + evidence_id`；跨年、inactive、candidate、未绑定有效 Activity 的事实均不进入；summary 中 race/PB/achievement 数量与 evidence 一致；定向测试与 diff review 通过。

## ACS-Year-AI-01C 结果

状态：Done。

实现摘要：

- 新增 `_career_year_resolver_evidence`，只读取 active Race / PB / Achievement 表的安全展示列。
- evidence_id 统一命名空间为 `race:*`、`pb:*`、`achievement:*`，已带前缀的 ID 不重复加前缀。
- evidence 必须同时满足事件日期属于目标年份、activity_id 绑定目标年份有效 Activity。
- evidence 稳定去重并按 `date + type + evidence_id` 排序。
- Snapshot summary 的 `race_count`、`pb_count`、`achievement_count` 由 evidence catalog 回填。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py -q
16 passed in 0.11s

.venv312/bin/python -m pytest tests/test_career_achievement_resolver.py tests/test_career_seasons_api.py -q
18 passed in 0.10s

.venv312/bin/python -m pytest tests/test_career_race_resolver.py tests/test_career_pb_resolver.py tests/test_career_races_api.py tests/test_career_pb_api.py -q
45 passed in 0.23s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。evidence 输出只包含 `evidence_id`、`activity_id`、`type`、`title`、`date`、`value`，未带候选、display metadata、照片、缩略图、媒体引用、本地路径或 raw 轨迹字段；未新增持久化、API、前端或 LLM 调用。

下一任务：`ACS-Year-AI-01D`。

## ACS-Year-AI-01D 工程级提示词

目标：完成 Year Snapshot 的 period、data_quality 和上一年同期 / 完整自然年 comparison，使 AI 不需要计算差值或猜测数据完整性。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_period_comparison.py`、更新既有年度 Snapshot 契约测试、任务状态、执行日志和完成报告。

约束：AI 不计算百分比或差值；不因查看日期推进改变比较截止范围；不实现 fingerprint、持久化、API、前端或 LLM；缺失比较数据时 delta 必须为 null，并返回稳定 reason。

契约刷新：`comparison` 增加 `reason` 字段，用于表达 `no_current_year_data`、`previous_year_no_data` 等稳定不可用原因码。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_period_comparison.py`
- `tests/test_career_year_snapshot_contract.py`
- `tests/test_career_year_snapshot_activity_aggregation.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_01d_period_comparison_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：当前年使用 `data_through` 比较上一年同日期范围；历史年比较完整自然年；上一年无数据返回 unavailable reason 和 null deltas；data_quality 区分 no_data、limited、ready；闰年、1 月初、上一年无数据和跨年边界有测试；diff review 通过。

## ACS-Year-AI-01D 结果

状态：Done。

实现摘要：

- `period.data_through` / `latest_activity_date` 使用进入 Snapshot 的最新 Activity 或 Resolver evidence 日期。
- 当前部分年度使用上一年同月同日范围，比较截止点来自 `data_through`，不来自查看日期推进。
- 历史年度使用完整自然年对比完整自然年。
- comparison 输出后端计算的活动、距离、时长、赛事和 PB 差值。
- 无当前数据或上一年无可比数据时，comparison 返回 unavailable、稳定 reason 和 null deltas。
- data_quality 输出 `no_data`、`limited`、`ready` 和稳定 warnings。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
48 passed in 0.36s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。`as_of_date` 只影响 period 展示，不作为比较截止；不可用比较保持 null delta；未新增持久化、API、前端或 LLM 调用。review 中清理了 01B 遗留的无用变量。

下一任务：`ACS-Year-AI-02A`。

## ACS-Year-AI-02A 工程级提示词

目标：实现 Year Snapshot 的 canonical JSON 与稳定 `source_fingerprint`，准确表达进入年度报告的事实是否变化。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_fingerprint.py`、更新年度 Snapshot 契约测试、任务状态、执行日志和完成报告。

约束：不得直接 hash 整个运行时 Snapshot；必须通过独立 `report_source_fields`；排除 `source_fingerprint` 自身、`generated_at`、`as_of_date`、traceId、状态文案、日志字段、UI 状态、Prompt / model 版本；不实现状态机、持久化、API、前端或 LLM。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_fingerprint.py`
- `tests/test_career_year_snapshot_contract.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_02a_fingerprint_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_contract.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：fingerprint 格式固定为 `sha256:{hex}`；相同事实跨多次构建稳定；允许字段变化导致 fingerprint 变化；Resolver evidence 变化导致 fingerprint 变化；日期推进、运行时字段、Prompt/model/UI 字段、排序差异和等价浮点表达不改变 fingerprint；diff review 通过。

## ACS-Year-AI-02A 结果

状态：Done。

实现摘要：

- 新增 `career_year_snapshot_report_source_fields`，只选择年度报告事实字段作为 hash 输入。
- 新增 `career_year_snapshot_canonical_json` 和 `_canonicalize_career_year_value`，统一字典排序、列表排序和浮点表达。
- 新增 `compute_career_year_source_fingerprint`，输出 `sha256:{hex}`。
- `build_career_year_snapshot` 现在生成稳定 `source_fingerprint`。
- 旧 no-data 空 fingerprint 契约已刷新为稳定 sha256 fingerprint。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_contract.py -q
18 passed in 0.12s

.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
27 passed in 0.30s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。fingerprint 不直接 hash 整个 Snapshot，运行时字段和 `as_of_date` 被排除；未新增状态机、持久化、API、前端或 LLM 调用。review 中同步修正了 `source_fingerprint` schema 描述。

下一任务：`ACS-Year-AI-02B`。

## ACS-Year-AI-02B 工程级提示词

目标：建立纯后端年度报告状态解析器，根据当前 Snapshot、最新成功报告、AI 可用性和运行中任务返回唯一状态与允许操作。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_report_state.py`、更新任务状态、执行日志和完成报告。

约束：不调用 LLM；不读 DOM、当前页面或前端缓存；不让前端用当前年份推断刷新能力；不建表、不持久化、不新增 API；状态文案与状态码分离，前端后续只消费状态码决定操作。

预期文件：

- `career_backend.py`
- `tests/test_career_year_report_state.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_02b_state_resolver_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py -q
.venv312/bin/python -m pytest tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：核心状态 `no_data`、`not_generated`、`ready`、`stale` 和运行态 `generating`、`failed`、`ai_unavailable` 全部有表驱动测试；返回 `can_generate`、`can_refresh`、`has_source_changes`；没有数据优先；旧报告在生成中、失败和 AI 不可用时保留可展示；`ready` 不可通过额外 runtime flag 变成可生成；diff review 通过。

## ACS-Year-AI-02B 结果

状态：Done。

实现摘要：

- 新增 `CAREER_YEAR_REPORT_STATES`。
- 新增 `resolve_career_year_report_state` 纯函数。
- 输出 `status`、`base_status`、`can_generate`、`can_refresh`、`has_source_changes`、`report_available`、`display_report`、`preserve_report`、当前 fingerprint 和报告 fingerprint。
- `generating`、`failed`、`ai_unavailable` 会覆盖展示状态，但保留 `base_status` 表达事实与缓存关系。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py -q
19 passed, 4 subtests passed in 0.12s

.venv312/bin/python -m pytest tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py tests/test_career_year_snapshot_period_comparison.py tests/test_career_year_snapshot_evidence.py tests/test_career_year_snapshot_activity_aggregation.py tests/test_career_year_snapshot_contract.py -q
35 passed, 4 subtests passed in 0.17s

.venv312/bin/python -m pytest tests/test_career_snapshot_builder.py tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py -q
27 passed in 0.34s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。状态解析器不依赖前端、DOM、页面缓存或 LLM；未新增持久化、API 或前端行为。Milestone A 的 Snapshot、fingerprint 和状态机代码门禁已完成。

下一任务：`ACS-Year-AI-03A`。

## ACS-Year-AI-03A 工程级提示词

目标：复用 `career_snapshots` 保存每年可重建的白名单 Year Snapshot，并提供后端内部构建、保存和读取能力。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_snapshot_persistence.py`、更新任务状态、执行日志和完成报告。

约束：年度 Snapshot 使用稳定 ID `career_snapshot:year:{year}`、`snapshot_type=career_year`、`source_version=acs.year.v1`；每年独立 upsert，不覆盖全生涯 `career_snapshot:latest`；保存前执行禁止字段递归检查；读取历史脏数据时再次裁剪、重算 fingerprint 并校验；明确连接所有权下的 commit / rollback / close；不暴露前端任意写 Snapshot 的 pywebview API；不调用 LLM、不改前端展示、不写 Activity / Race / PB / Achievement / 照片 canonical 表。

预期文件：

- `career_backend.py`
- `tests/test_career_year_snapshot_persistence.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_03a_snapshot_persistence_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：多年份保存和读取互不覆盖；年度与全生涯 Snapshot 共表但按 ID/type 隔离；历史脏内容不会把禁止字段返回给调用方；保存结果返回 fingerprint、版本和保存时间但不向普通前端展示完整 Snapshot；旧全生涯 Snapshot 测试不回归；diff review 通过。

## ACS-Year-AI-03A 结果

状态：Done。

实现摘要：

- 新增 `CAREER_YEAR_SNAPSHOT_TYPE = "career_year"`。
- 新增 `_career_year_snapshot_id`、`_strip_career_year_forbidden`、`_sanitize_saved_career_year_snapshot`。
- 新增 `save_career_year_snapshot`，复用 `career_snapshots` 以 `career_snapshot:year:{year}` upsert 年度派生 Snapshot。
- 新增 `get_career_year_snapshot`，读取时按年度白名单字段裁剪、重新计算 `source_fingerprint` 并执行契约校验。
- 新增年度 Snapshot 持久化测试，覆盖稳定 ID/type/version、多年份隔离、全生涯隔离、空读取不生成、历史脏内容裁剪、保存前禁止字段拒绝和 pywebview 写 API 未暴露。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py tests/test_career_year_snapshot_fingerprint.py -q
20 passed, 4 subtests passed in 0.20s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.22s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。03A diff 只触达年度 Snapshot 内部持久化、测试和文档；未覆盖 `career_snapshot:latest`，未暴露 `save_career_year_snapshot` pywebview API，未向普通前端返回完整 Snapshot，未写 canonical 事实表。

下一任务：`ACS-Year-AI-03B`。

## ACS-Year-AI-03B 工程级提示词

目标：新增独立 AI 输出缓存表 `career_ai_insights` 和仓储函数，使年度报告按年份、事实指纹、Prompt 和模型可审计地保存，并能原子切换当前展示版本。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_ai_insights_repository.py`、更新任务状态、执行日志和完成报告。

约束：不调用 LLM；不新增 pywebview API；不改前端；不把 AI 输出写入 Activity、Race、PB、Achievement、照片或全生涯 Snapshot 表；只允许校验成功的输出进入 `ready`；新报告成功后同一事务内把同一 `scope/scope_key` 旧 ready 标为 `superseded`；第一版保留历史审计记录但不提供用户可见版本管理；migration 可重复执行，失败必须 rollback 或明确抛错，不留下半建表状态。

预期文件：

- `career_backend.py`
- `tests/test_career_ai_insights_repository.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_03b_ai_insights_cache_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：`career_ai_insights` 表、唯一约束和查询索引创建可重复；多年份、多 fingerprint、多 prompt/model 缓存互不覆盖；按完整缓存键可查；当前成功报告读取只返回 `ready`；未校验输出不能进入 `ready`；新 ready 报告与旧 ready->superseded 原子切换；migration 失败回滚且不破坏旧 `career_snapshots` 数据；diff review 通过。

## ACS-Year-AI-03B 结果

状态：Done。

实现摘要：

- 新增 `CAREER_AI_INSIGHT_SCOPE_YEAR` 和 `CAREER_AI_INSIGHT_STATUSES`。
- `ensure_career_schema` 新增 `career_ai_insights` 表、唯一约束和按 scope / scope_key / status / generated_at 查询索引。
- 新增 `insert_career_ai_insight`，用于插入或更新非当前候选/失败/审计缓存记录。
- 新增 `activate_career_ai_insight`，要求 `content_validated=True`，并在事务内把同一 `scope/scope_key` 下旧 `ready` 标为 `superseded`。
- 新增 `save_ready_career_ai_insight`，封装“插入新报告 -> 原子切换当前 ready”的成功路径。
- 新增 `get_current_career_ai_insight`、`get_career_ai_insight_by_cache_key` 和 `get_career_ai_insight_by_id`。
- 新增仓储测试，覆盖 schema 幂等、唯一约束、ready 校验、多年份/多 fingerprint/多 prompt/model 审计隔离、候选与激活分离、事实表不写入和 migration 失败回滚。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
20 passed, 4 subtests passed in 0.24s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.23s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。迁移在 schema savepoint 内，失败回滚且不破坏旧 `career_snapshots`；`ready` 写入必须经过显式校验参数；当前版本按 `scope/scope_key` 单一 ready 表达；缓存写入未触达 Activity、Race、PB、Achievement、照片或全生涯 Snapshot 表；未新增 LLM、前端或 pywebview API。

下一任务：`ACS-Year-AI-04A`。

## ACS-Year-AI-04A 工程级提示词

目标：实现不调用 LLM 的年度报告页后端只读服务，统一返回年份列表、当前年度事实、安全 fallback、缓存报告和报告状态。

范围：允许修改 `career_backend.py`、新增 `tests/test_career_year_insight_service.py`、更新任务状态、执行日志和完成报告。

约束：只构建或读取 Year Snapshot 与年度 AI 缓存；不调用 LLM；不写 AI 成功缓存；不新增 pywebview API；不改前端；不把 Snapshot 原文、debug JSON、SQLite schema、本地路径或禁止字段返回前端；`facts` 只能来自后端年度安全聚合；本地 fallback 必须明确 `mode=local_fallback` 且不得伪装为 AI 报告；无成功报告时 `report` 为空；AI 不可用但有历史成功报告时继续返回该报告；默认年份为最近一个有有效 Activity 的年份。

预期文件：

- `career_backend.py`
- `tests/test_career_year_insight_service.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_04a_read_service_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：`no_data`、`not_generated`、`ready`、`stale`、AI 不可用且有旧报告均有稳定返回；返回字段包含 `available_years`、`year`、`report_state`、`can_generate`、`can_refresh`、`has_source_changes`、`facts`、`report`、`generated_at`、`data_through`、`status`；服务不调用 LLM、不写 AI 缓存、不返回完整 Snapshot；diff review 通过。

## ACS-Year-AI-04A 结果

状态：Done。

实现摘要：

- 新增 `get_career_year_insight` 后端只读服务。
- 新增 `_career_year_facts_view`，从 Year Snapshot 生成安全 facts 投影。
- 新增 `_career_year_local_fallback`，返回明确非 AI 的本地事实摘要、关键事件、月度节奏和比较结果。
- 新增 `_career_year_report_view`，把缓存 `ready` 报告转换为年度页面可消费的 AI report。
- 默认年份来自 `get_career_year_snapshot_available_years` 的最新有效 Activity 年份；无数据时 `year=None`。
- 服务组合当前 Snapshot、`career_ai_insights` 当前 ready 报告和 `resolve_career_year_report_state`，不调用 LLM、不写 AI 缓存。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
25 passed, 4 subtests passed in 0.30s

.venv312/bin/python -m pytest tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py -q
16 passed in 0.23s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。服务路径未引用 `llm_backend`，未调用 ready 缓存保存函数，未新增 API 或前端行为；`report=None` 与 `local_fallback.mode=local_fallback` 明确区分无 AI 报告状态；facts 不返回完整 Snapshot、debug JSON 或 `source_fingerprint`。

下一任务：`ACS-Year-AI-04B`。

## ACS-Year-AI-04B 工程级提示词

目标：通过 `main.Api.get_career_year_insight({ year })` 暴露年度报告只读能力，并同步 pywebview envelope 与 JS API 契约。

范围：允许修改 `main.py`、`docs/js_api_contract.json`、新增 `tests/test_career_year_insight_read_api.py`，并更新任务状态、执行日志和完成报告。

约束：只读 API；只接受冻结字段 `year`；未知字段拒绝；year 执行类型和范围校验；使用统一 `{ok, code, msg, data, traceId}` envelope；无数据年份返回稳定业务状态，不泄露 SQL 或栈；日志不得记录 Snapshot 原文；不改变 `generate_career_insight` payload 和返回结构；不把年度字段塞进全生涯 API；不新增生成 API、不调用 LLM。

预期文件：

- `main.py`
- `docs/js_api_contract.json`
- `tests/test_career_year_insight_read_api.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_04b_read_api_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
.venv312/bin/python -m py_compile main.py career_backend.py
```

完成定义：API envelope、参数校验、错误 envelope、无数据年份稳定业务状态和 JS API 契约测试通过；全生涯 `generate_career_insight` 不回归；diff review 通过。

## ACS-Year-AI-04B 结果

状态：Done。

实现摘要：

- 新增 `main.Api.get_career_year_insight(payload)`。
- 参数仅允许 `year`；未知字段、布尔、非整数和超范围年份返回 validation envelope。
- 成功响应使用统一 `{ok, code, msg, data, traceId}`，data 来自后端年度只读服务。
- 成功日志只记录 year、traceId、report_state 和耗时。
- `docs/js_api_contract.json` 新增 `get_career_year_insight` 契约，明确只读、无 LLM、无写缓存、无 Snapshot 原文。
- 新增 `tests/test_career_year_insight_read_api.py`，覆盖 envelope、默认年份、无数据年份业务状态、参数校验、JS API 契约和全生涯 `generate_career_insight` 不被替换。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.19s

.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py tests/test_career_year_snapshot_persistence.py tests/test_career_year_report_state.py -q
25 passed, 4 subtests passed in 0.23s

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed

.venv312/bin/python -m py_compile main.py career_backend.py
passed
```

Review 结论：通过。API 是年度只读外壳，未调用 LLM，未写 AI 缓存或事实表；未知字段和非法 year 不泄露内部信息；全生涯 `generate_career_insight` 保持原契约。

下一任务：`ACS-Year-AI-05A`。

## ACS-Year-AI-05A 工程级提示词

目标：把 Overview 年度卡片改造成稳定的年度总结入口，点击或键盘触发只导航到 AI 总结页年度模式并发起只读年度加载。

范围：允许修改 `track.html`、前端静态测试、任务状态、执行日志和完成报告。

约束：年度卡片使用原生 `button` 或等价键盘语义；`aria-label="查看 {year} 年度总结"`；Enter / Space 可触发；悬停提示改为“查看年度总结”；保留 DIN 年份、统计胶囊、轻微上浮和克制布局；点击不得调用 `generate_career_year_insight`、`generate_career_insight` 或 `call_llm`；年度卡片不得增加 `not_generated / stale / ready` 状态胶囊；本任务只做入口与只读加载钩子，年度页完整模式与渲染留给 05B/05C。

预期文件：

- `track.html`
- `tests/test_career_overview_frontend_render.py`
- `tests/test_career_year_card_navigation_frontend.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_05a_year_card_navigation_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_card_navigation_frontend.py tests/test_career_overview_frontend_render.py tests/test_career_insight_frontend_render.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
```

完成定义：静态测试证明年度卡片是可访问 button，鼠标和键盘均可触发；点击只切到 insight 页并调用 `get_career_year_insight` 只读 API；不调用年度生成、全生涯生成或 LLM；Overview 年度统计胶囊无回归；diff review 通过。

## ACS-Year-AI-05A 结果

状态：Done。

实现摘要：

- `.career-season-card` 改为原生 `button`，保留原有视觉密度与上浮效果。
- 增加 `aria-label="查看 {year} 年度总结"`、`focus-visible` 样式和“查看年度总结”悬停提示。
- `careerSeasonCardHtml` 点击调用 `openCareerYearInsight(year)`。
- 新增 `openCareerYearInsight`：设置 `appState.career.insightMode='year'`、记录选中年份、切换到 `insight` 页并调用年度只读加载。
- 新增 `loadCareerYearInsight`：只调用 `window.pywebview.api.get_career_year_insight`，存储年度 ViewModel。
- `loadCareerInsight` 设置 `insightMode='career'`，为后续年度 / 生涯分段切换做状态隔离准备。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_card_navigation_frontend.py tests/test_career_overview_frontend_render.py tests/test_career_insight_frontend_render.py -q
23 passed in 0.06s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.12s
```

Review 结论：通过。年度卡片点击路径只调用 `get_career_year_insight` 只读 API；未调用 `generate_career_year_insight`、`generate_career_insight` 或 `call_llm`；未新增年度状态胶囊；原 Overview 年度统计胶囊测试无回归。

下一任务：`ACS-Year-AI-05B`。

## ACS-Year-AI-05B 工程级提示词

目标：在现有 AI 总结页框架中增加 `年度总结 / 生涯总结` 分段模式和后端驱动年份选择，同时保留全生涯 fallback。

范围：允许修改 `track.html`、前端静态测试、任务状态、执行日志和完成报告。

约束：年份胶囊来源只能是后端 `available_years`；顶部导航进入 AI 总结页默认加载最近有数据年份；年度卡片进入时选中卡片年份；无年度数据时不伪造当前年份；年度与生涯分别维护 ViewModel、loading、error 和 request state；切换模式不覆盖另一模式已加载内容；生涯模式继续使用现有 `generate_career_insight` fallback；不调用年度生成 API 或 LLM；不从 Overview 卡片或 Activity 列表推断年份。

预期文件：

- `track.html`
- `tests/test_career_year_insight_mode_frontend.py`
- `tests/test_career_insight_frontend_render.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_05b_insight_mode_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_insight_frontend_render.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
```

完成定义：年度 / 生涯模式可稳定切换；年份选择只消费后端 `available_years`；顶部导航默认读取最近后端年份；年度卡片选中目标年份；前端不存在年份推断或错误缓存键复用；diff review 通过。

## ACS-Year-AI-05B 结果

状态：Done。

实现摘要：

- AI 总结页 toolbar 增加 `年度总结 / 生涯总结` 分段控制。
- 新增年份胶囊容器 `career-year-selector`，只渲染后端 ViewModel 的 `available_years`。
- `appState.career` 增加年度与生涯分离的 ViewModel、loading、error 和 selected year 状态。
- 新增 `renderCareerYearSelector`、`renderCareerInsightModeShell`、`renderCareerYearInsight`、`setCareerInsightMode`、`enterCareerInsightFromTopNav`。
- `switchCareerPage('insight')` 时默认进入年度模式，并调用 `loadCareerYearInsight({})` 让后端决定最近有效年份。
- 年度卡片进入时设置 `suppressInsightAutoLoad`，避免顶部默认加载覆盖卡片年份。
- 生涯模式保留原 `generate_career_insight` fallback。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_insight_frontend_render.py -q
17 passed in 0.05s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.12s
```

Review 结论：通过。年份选择仅消费 `available_years`，未从 Overview 卡片、Activity 列表或当前日期推断年份；年度与生涯状态分离；年度模式只调用 `get_career_year_insight`，生涯模式保留 `generate_career_insight`，未调用 LLM。

下一任务：`ACS-Year-AI-05C`。

## ACS-Year-AI-05C 工程级提示词

目标：完成年度页面的事实概览、报告章节和全状态渲染，不依赖真实 LLM 即可形成可用页面闭环。

范围：允许修改 `track.html`、新增/更新年度前端静态测试、任务状态、执行日志和完成报告。

约束：事实概览直接渲染后端 `facts`；报告章节顺序固定为主线、关键时刻、运动节奏、上一年比较、下一年方向、免责声明；本地 fallback 必须明确非 AI；`ready/stale/ai_unavailable` 可展示历史 report；`not_generated/failed/generating/no_data` 有独立文案；本阶段不得调用生成 API 或 LLM；按钮可作为后续生成入口占位，但不得绑定不存在的生成调用。

预期文件：

- `track.html`
- `tests/test_career_year_insight_render_frontend.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_05c_year_render_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
```

完成定义：年度标题、生成时间、data_through、部分年度说明、事实概览、报告章节和 no_data/not_generated/ready/stale/generating/failed/ai_unavailable 状态均被静态测试锁定；loading、旧报告和错误提示不会互相覆盖；diff review 通过。

## ACS-Year-AI-05C 结果

状态：Done。

实现摘要：

- 新增 `careerYearFactsHtml` / `careerYearFactHtml`，渲染后端 `facts.summary` 的年度事实概览。
- 新增 `careerYearStateMessage`，覆盖七种年度报告状态。
- 新增 `careerYearActionHtml`，为后续生成任务保留无绑定动作占位。
- 新增 `careerYearReportSectionsHtml`，固定主线、关键时刻、运动节奏、上一年比较、下一年方向、免责声明顺序。
- `renderCareerYearInsight` 现在展示年度标题、生成时间、`data_through`、部分年度说明、状态文案、事实概览、章节和免责声明。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py -q
13 passed in 0.04s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_phase9_pywebview_envelope.py -q
9 passed in 0.09s
```

Review 结论：通过。年度渲染只消费后端 facts/report/local_fallback；状态覆盖完整；生成按钮未绑定 `generate_career_year_insight`、`generate_career_insight` 或 `call_llm`；本地 fallback 文案明确非 AI。

下一任务：`ACS-Year-AI-05D`。

## ACS-Year-AI-05D 工程级提示词

目标：为年度总结读取增加请求 token 与模式/年份校验，防止快速切换年份、切换模式或晚到响应覆盖当前页面。

范围：允许修改 `track.html`、新增前端静态测试、任务状态、执行日志和完成报告。

约束：每次年度读取生成递增 request id；响应写入前校验 request id、当前模式和选中年份；切到生涯模式后年度响应不得覆盖生涯页面；A 年响应不得覆盖 B 年；不得调用生成 API 或 LLM。

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_request_isolation_frontend.py tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py -q
```

## ACS-Year-AI-05D 结果

状态：Done。

实现摘要：

- `loadCareerYearInsight` 每次请求生成递增 `requestId` 并写入 `appState.career.yearInsightRequestId`。
- 发起请求时冻结 `requestedYear`。
- 响应写入前校验 request id、当前模式和响应年份。
- 过期响应返回 `ignored=true/reason=stale_year_insight_response`，不写入 ViewModel。
- 过期错误返回 `ignored=true/reason=stale_year_insight_error`，不覆盖当前页面错误。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_request_isolation_frontend.py tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py -q
14 passed in 0.05s
```

Review 结论：通过。guard 位于年度 ViewModel 写入之前；切换生涯模式或快速切换年份后，晚到响应不会覆盖当前页面；未新增生成 API 或 LLM 调用。

下一任务：`ACS-Year-AI-06A`。

## ACS-Year-AI-06A 工程级提示词

目标：建立年度报告专用 Prompt assembler 和受控 LLM 调用，只把白名单 Year Snapshot 交给现有 LLM 配置链路，并严格要求 JSON 输出。

范围：允许修改 `llm_backend.py`、新增 `tests/test_career_year_llm_prompt.py`、更新任务状态、执行日志和完成报告。

约束：Prompt version 固定为 `acs.year.summary.zh-CN.v1`；system/developer prompt 明确 AI 只能使用给定 Snapshot；当前部分年度必须使用“截至当前数据周期”语气；禁止伤病、心理、生活事件、训练动机、年度等级、详细训练计划和医疗建议；数据不足时降级表达，不补全故事；输出严格 JSON，禁止 Markdown code fence 或附加解释；模型、URL、token、provider 只能从现有 LLM 配置读取，前端不得提交；调用层使用受控超时与最多一次格式修复机会；测试使用 fake client，不依赖真实网络；日志不得输出完整 Prompt、Snapshot 或原始 AI 响应。

预期文件：

- `llm_backend.py`
- `tests/test_career_year_llm_prompt.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_06a_prompt_llm_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_insight_service.py -q
.venv312/bin/python -m py_compile llm_backend.py
```

完成定义：测试证明禁止字段和前端 payload 不进入 Prompt；fake LLM 可返回符合基础 schema 的示例结果；Markdown code fence 或非 JSON 响应会触发一次修复；配置来自 `load_llm_config` 与 `generate_text` 链路；diff review 通过。

## ACS-Year-AI-06A 结果

状态：Done。

实现摘要：

- 新增 `CAREER_YEAR_SUMMARY_PROMPT_VERSION = "acs.year.summary.zh-CN.v1"`。
- 新增 `career_year_summary_prompt_payload`，只取 Year Snapshot 白名单字段并递归剔除禁止字段。
- 新增 `build_career_year_summary_messages`，明确事实边界、部分年度语气、禁止主题和严格 JSON schema。
- 新增 `_strict_json_object_from_text`，拒绝 Markdown code fence、附加解释和非对象 JSON。
- 新增 `_career_year_summary_repair_messages`，最多一次要求模型重输严格 JSON。
- 新增 `generate_career_year_summary`，读取现有 LLM config，支持 fake client，日志只记录安全摘要。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py -q
5 passed in 0.10s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_insight_service.py -q
11 passed in 0.11s

.venv312/bin/python -m py_compile llm_backend.py
passed
```

Review 结论：通过。Prompt 不包含前端 payload、token、本地路径、points 或 track_json；fake client 证明配置由后端传入；格式修复最多一次；未新增前端生成 API。

下一任务：`ACS-Year-AI-06B`。

## ACS-Year-AI-06B 工程级提示词

目标：把 LLM 输出视为不可信叙事草稿，经过严格校验后转换成可缓存、可展示的年度报告。

范围：允许修改 `career_backend.py`、必要时同步 `llm_backend.py` 的年度报告 JSON schema、添加或更新年度 AI 报告校验测试、更新任务状态、执行日志和完成报告。

约束：校验 `schema_version` 和 year；限制 headline、annual_thread、rhythm_summary、comparison_summary、directions、commentary、caveats 的数量与长度；所有 `key_moments[].evidence_id` 必须来自当前 Year Snapshot；去重重复 evidence，未知 evidence 低于阈值时丢弃，达到阈值时整份失败；关键时刻目标为 3 至 5 个，证据不足时允许少于 3 个但不得编造；关键时刻标题、日期、成绩、activity_id、detail link 必须由后端 evidence 回填；清洗 HTML、script、Markdown code fence 和异常控制字符；comparison 不可用时不得保留确定性同比结论；输出 year、事实摘要和关键事件事实不得采用 AI 自己提供的值；不得新增真实 LLM 网络依赖或日志输出 Prompt/Snapshot/raw response。

预期文件：

- `career_backend.py`
- `llm_backend.py`
- `tests/test_career_year_ai_report_validation.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_06b_report_validation_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py -q
.venv312/bin/python -m py_compile career_backend.py llm_backend.py
```

完成定义：非对象/错 schema/错 year、未知 evidence、重复 evidence、超长输出和脚本内容均有测试；通过校验的报告中所有事实可追溯到当前 Snapshot；diff review 确认没有 LLM 调用、没有信任 AI 事实、没有泄露日志。

## ACS-Year-AI-06B 结果

状态：Done。

实现摘要：

- 新增年度 AI 报告校验器 `validate_career_year_ai_report`。
- 校验 `schema_version` 与 year，并复用 Year Snapshot contract 校验。
- 对 `key_moments[].evidence_id` 做存在性验证、重复去重和未知 evidence 阈值失败。
- 使用后端 evidence 回填关键时刻标题、日期、成绩、`activity_id` 和 `detail_link`。
- 清洗 HTML、script、Markdown code fence、异常控制字符，并限制文本长度与列表数量。
- comparison 不可用时强制降级比较摘要，避免确定性同比结论。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py -q
12 passed in 0.13s

.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_ai_insights_repository.py -q
11 passed in 0.12s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py
passed
```

Review 结论：通过。校验器不调用 LLM，不信任 AI 提供的事实字段；关键事件事实从当前 Snapshot evidence 回填；无 Prompt、Snapshot 或 raw response 日志泄露。

下一任务：`ACS-Year-AI-06C`。

## ACS-Year-AI-06C 工程级提示词

目标：新增年度生成 / 更新 API `generate_career_year_insight({ year })`，严格按照后端状态决定是否允许调用 LLM，并在成功后写入年度 AI 缓存。

范围：允许修改 `career_backend.py`、`main.py`、`docs/js_api_contract.json`、新增/更新年度生成 API 测试、更新任务状态、执行日志和完成报告。前端按钮绑定和并发单飞留给后续任务，不在本任务扩展。

约束：前端/API payload 只能提交 `year`；拒绝 prompt、Snapshot、model、force 和任意事实字段；`not_generated` 允许首次生成；`stale` 允许更新；`ready` 返回缓存或“已是最新”，不得调用 LLM；`no_data` 返回不可生成业务状态；AI 配置缺失或 LLM 调用不可用返回 `ai_unavailable`，保留 facts 和旧报告；成功流程必须是构建当前 Snapshot -> 再查缓存 -> 调用年度 LLM -> 校验 AI 输出 -> 后端事实回填 -> 原子写入 ready 缓存 -> 返回新报告；使用统一 pywebview envelope；不得影响既有 full-career `generate_career_insight`。

预期文件：

- `career_backend.py`
- `main.py`
- `docs/js_api_contract.json`
- `tests/test_career_year_generate_api.py`
- `tests/test_career_year_insight_service.py`
- `tests/test_career_year_insight_read_api.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_06c_generate_api_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_insight_service.py tests/test_career_year_insight_read_api.py -q
.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py tests/test_career_ai_insights_repository.py -q
.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py
```

完成定义：fake LLM 验证 `not_generated`/`stale` 生成调用，`ready`/`no_data`/非法 payload 零调用；成功生成后只读 API 可立即读到新报告；API envelope 与 JS contract 注册完成；diff review 确认年度链路独立于 `generate_career_insight`。

## ACS-Year-AI-06C 结果

状态：Done。

实现摘要：

- 新增后端 `generate_career_year_insight(year)`，按年度状态机限制 LLM 调用。
- `no_data` 返回不可生成业务状态；`ready` 返回已是最新且不调用 LLM；`not_generated` 与 `stale` 允许调用年度 LLM。
- 成功流程为当前 Year Snapshot -> 完整缓存键再查 -> LLM -> `validate_career_year_ai_report` -> `save_ready_career_ai_insight` -> 返回只读 view。
- AI 配置缺失或调用/校验失败时返回 `ai_unavailable` 业务状态，并通过只读 view 保留 facts 与历史报告。
- 新增 pywebview `Api.generate_career_year_insight(payload)`，payload 仅支持 `year`，未知字段、bool、非法年份均返回 validation envelope。
- 更新 `docs/js_api_contract.json` 注册年度生成 API，并明确不复用全生涯 `generate_career_insight`。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_insight_service.py tests/test_career_year_insight_read_api.py -q
17 passed in 0.19s

.venv312/bin/python -m pytest tests/test_career_year_ai_report_validation.py tests/test_career_year_llm_prompt.py tests/test_career_ai_insights_repository.py -q
18 passed in 0.10s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py
passed
```

Review 结论：通过。状态门位于 LLM 调用前；API 不接受 prompt/Snapshot/model/force/事实字段；年度生成链路独立于 full-career `generate_career_insight`；日志只记录 year、状态和耗时，不输出 Prompt、Snapshot 或 raw AI response。

下一任务：`ACS-Year-AI-07A`。

## ACS-Year-AI-07A 工程级提示词

目标：确保相同年度事实只产生一次有效 AI 调用和一个可复用缓存结果，冻结 ready 状态禁止重复生成的幂等契约。

范围：允许修改 `career_backend.py`、`main.py`、年度生成测试、任务状态、执行日志和完成报告。不得引入并发单飞锁；并发竞争留给 07B。

约束：生成前按完整缓存键 `scope + scope_key + source_fingerprint + prompt_version + model_id` 再查；命中缓存直接返回，不调用 LLM；相同请求重复提交返回一致报告和 ready 状态；`ready` 状态即使前端构造 prompt/model/force/Snapshot/事实字段也不能绕过，因为 pywebview API 必须先拒绝未知字段；Prompt/model 版本变化不自动把用户可见状态改为 stale；若内部明确使用新 Prompt/model，也不得向用户暴露无事实变化的重新生成入口；缓存读取和状态解析使用同一当前 ready 选择规则。

预期文件：

- `career_backend.py`
- `main.py`
- `tests/test_career_year_generate_api.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_07a_cache_idempotency_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_ai_report_validation.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

完成定义：fake LLM 调用计数证明重复生成与缓存命中不二次调用；DB 唯一约束与服务层状态门同时被测试覆盖；ready 状态无法被前端额外字段绕过；diff review 确认没有扩大到并发单飞或 UI 绑定。

## ACS-Year-AI-07A 结果

状态：Done。

实现摘要：

- 服务层生成前按完整缓存键再次查询，并只复用已验证过的 `ready/superseded` 缓存。
- 相同年度事实重复提交时，第二次在 `ready` 状态门前返回，不再调用 LLM。
- 无事实变化时，即使内部 prompt/model 参数变化，用户可见状态仍为 `ready`，不暴露刷新入口。
- 已验证的精确 `superseded` 缓存可重新激活并返回 `cache_hit`；未验证 `candidate` 缓存不被信任，仍需重新走 LLM + 校验。
- pywebview 继续拒绝额外 payload 字段，前端无法通过 prompt/model/force/Snapshot 绕过 ready 状态门。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
20 passed in 0.30s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_ai_report_validation.py -q
13 passed in 0.10s

.venv312/bin/python -m py_compile career_backend.py main.py
passed
```

Review 结论：通过。07A 未引入并发单飞或 UI 绑定；只收口服务层缓存幂等。candidate 不再被缓存命中路径误激活。

下一任务：`ACS-Year-AI-07B`。

## ACS-Year-AI-07B 工程级提示词

目标：实现同一 `year + fingerprint` 的进程内单飞控制，避免重复点击、多窗口或并发请求产生重复 LLM 调用和版本竞争。

范围：允许修改 `career_backend.py`、年度生成并发测试、任务状态、执行日志和完成报告。不得实现 07C 的失败矩阵和用户重试 UI。

约束：同一进程内按 `year + source_fingerprint + prompt_version + model_id` 建立单飞注册表；第二个相同请求等待同一结果或复用进行中结果，不发第二次 LLM；不同年份允许并行；锁定后再次检查完整缓存键，覆盖两个窗口同时到达；新报告写入与旧报告 supersede 继续通过 `save_ready_career_ai_insight` 的事务完成；LLM 生成期间若年度事实再次变化，旧 fingerprint 结果不得标记为当前 ready，应丢弃为非当前结果并返回重新解析后的状态；异常、取消和超时必须释放单飞状态。

预期文件：

- `career_backend.py`
- `tests/test_career_year_generate_api.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_07b_singleflight_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py -q
.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
.venv312/bin/python -m py_compile career_backend.py
```

完成定义：并发测试证明同一键只调用一次 LLM；不同年份不会共用锁或串写报告；生成期间事实变化不会把旧 fingerprint 结果写成当前 ready；事务失败后旧报告仍为当前版本；diff review 确认单飞状态总能释放。

## ACS-Year-AI-07B 结果

状态：Done。

实现摘要：

- 新增年度生成 single-flight 注册表，key 为 `year + source_fingerprint + prompt_version + model_id`。
- 同 key 并发请求中，leader 执行 LLM，follower 等待并复用同一结果，不发第二次 LLM。
- leader 获得飞行权后再次查询完整缓存键，覆盖两个窗口同时到达时的缓存竞争。
- 不同年份使用不同 key，可并行进入 LLM；缓存写入遇到 SQLite locked 时做窄重试。
- LLM 返回后重新构建当前 Year Snapshot；若 fingerprint 变化，则丢弃旧结果，不写入 ready。
- 写入失败时回滚本次生成，旧 ready 报告仍保持当前版本。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py -q
13 passed in 0.46s

.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
11 passed in 0.12s

.venv312/bin/python -m py_compile career_backend.py
passed
```

Review 结论：通过。单飞状态在 `finally` 发布并移除；等待者返回 leader 的深拷贝结果；不同年份不共用锁；source fingerprint 变化不会污染 ready 缓存。

下一任务：`ACS-Year-AI-07C`。

## ACS-Year-AI-07C 工程级提示词

目标：完成年度生成链路的失败策略、安全日志和用户可恢复行为。

范围：允许修改 `career_backend.py`、年度生成失败测试、任务状态、执行日志和完成报告。前端 retry UI 只做后端契约支撑，不在本任务绑定按钮。

约束：覆盖网络失败、超时、非 JSON、schema 失败、错 year、未知 evidence、空输出和超长输出；纯格式错误的受控修复由 06A LLM 调用层保持最多一次，不新增无限重试；首次生成失败保留 facts 并返回 failed 状态；更新失败保留旧报告、原 generated_at 和旧 fingerprint；错误 envelope / generation view 不回显 token、URL 密钥、Prompt、Snapshot、底层请求体或原始 AI 响应；日志只保留 year、fingerprint 前缀、prompt version、model id、耗时、结果状态等安全摘要；明确区分参数错误、无数据、AI 未配置、超时、格式失败、证据失败和持久化失败。

预期文件：

- `career_backend.py`
- `tests/test_career_year_generate_api.py`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`
- `docs/acs_year_ai_07c_failure_privacy_completion_report.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_ai_report_validation.py -q
.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py tests/test_career_year_insight_read_api.py -q
.venv312/bin/python -m py_compile career_backend.py llm_backend.py main.py
```

完成定义：失败矩阵测试全部通过；日志捕获测试确认没有敏感内容；任意失败均不污染 canonical 表，且不新增或篡改 Activity/Race/PB/Achievement 事实。

## ACS-Year-AI-07C 结果

状态：Done。

实现摘要：

- 生成失败按 phase 分类为 `network_failed`、`timeout`、`format_failed`、`schema_failed`、`evidence_failed`、`persistence_failed`。
- 首次生成失败返回 `failed` 页面状态并保留 facts，不写 AI 缓存。
- 更新失败通过 `failed` runtime 状态保留旧报告、旧 generated_at 和旧 fingerprint。
- AI 配置缺失仍返回 `ai_unavailable`，与调用失败区分。
- 后端失败日志改为安全摘要，不输出异常正文、Prompt、Snapshot、raw response、URL 或 token。
- 超长/脚本输出继续通过 06B 清洗和长度限制，不泄露原始文本。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_ai_report_validation.py -q
23 passed, 6 subtests passed in 0.53s

.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py tests/test_career_year_insight_read_api.py -q
11 passed in 0.11s

.venv312/bin/python -m py_compile career_backend.py llm_backend.py main.py
passed
```

Review 结论：通过。失败返回和日志均使用固定安全文案；日志只记录 year、fingerprint 前缀、prompt/model、phase、status、elapsed；失败不污染 Activity/Race/PB/Achievement canonical 表。

下一任务：`ACS-Year-AI-08A`。

## ACS-Year-AI-08A 工程级提示词

目标：汇总并补齐年度 AI 测试矩阵，执行最宽实际可行的 ACS 回归，并对累计 diff 做质量 review。

范围：允许新增测试矩阵/回归报告文档，必要时补极小测试缺口；不得借 08A 改产品语义、改 UI 绑定或打包 DMG。

约束：映射交付手册第 19、20 节验收标准；运行所有新增 `test_career_year_*` 测试；联跑现有 `test_career*.py` 宽回归；运行 Python 编译和 `docs/js_api_contract.json` 解析；静态检查禁止字段、前端零推断、年度 / 生涯 API 分离；失败测试不得通过删除断言、降低语义或恢复旧记忆能力规避。

预期文件：

- `docs/acs_year_ai_08a_test_matrix_and_regression_report.md`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_*.py -q
.venv312/bin/python -m pytest tests/test_career*.py -q
.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

完成定义：定向测试全绿；ACS 宽回归全绿，或仅剩有证据且与本功能无关的既有失败并在报告中记录；review 无阻塞问题。

## ACS-Year-AI-08A 结果

状态：Done。

实现摘要：

- 新增年度 AI 测试矩阵与 ACS 宽回归报告。
- 执行所有 `test_career_year_*.py` 年度测试。
- 执行所有 `test_career*.py` ACS 宽回归。
- 执行 Python 编译与 `docs/js_api_contract.json` JSON 解析。
- 执行静态检查：旧记忆退役字段、前端生成绑定、年度 / 生涯 API 分离。
- 修复首轮宽回归发现的 `"memory_count"` 静态退役契约问题；运行时仍通过 forbidden set 禁止该字段。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_memory_retirement.py -q
3 passed in 0.13s

.venv312/bin/python -m pytest tests/test_career_year_*.py -q
97 passed, 10 subtests passed in 0.74s

.venv312/bin/python -m pytest tests/test_career*.py -q
576 passed, 38 subtests passed in 2.59s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

Review 结论：通过。年度测试矩阵覆盖 Snapshot、fingerprint、状态机、缓存、API、前端、并发、安全和兼容；ACS 宽回归全绿；未执行 DMG 打包。

下一任务：`ACS-Year-AI-08B`。

## ACS-Year-AI-08B 工程级提示词

目标：使用当前真实数据库和受控样例验证年度事实、状态变化、报告沉淀及页面视觉，覆盖桌面/移动视口与真实 AI 首次生成/更新。

范围：允许读取真实 DB 状态、调用年度只读/生成 API、记录验收结果和截图/人工验收记录；不得打包 DMG；不得记录完整 Prompt、Snapshot、token 或 raw AI response。

约束：必须覆盖当前年份持续新增活动、历史年份补导入活动由 ready 进入 stale、历史年份无事实变化保持 ready、丰富年度、轻量年度、单/多运动类型、上一年无可靠比较、AI 配置缺失/超时/格式错误、更新失败旧报告仍可读。真实 AI 至少完成一次首次生成和一次事实变化后的更新验证，才能标记真实 AI 完成。

中途阻塞与解除：

- 真实 DB 存在：`/Users/fanglei/.fitvault/user_profile.db`。
- 活动年份可用：2026=135、2025=51、2024=25、2023=4、2022=7、2020=4、2019=10、2018=17。
- 初始判断将 OpenClaw 空 model 误判为不可用；用户确认“只要脉图的大模型配置成功，任何可用模型都可以生产报告，参考 AI 洞察功能方案”。
- 已修正年度链路：CLI 模式按全局 AI 配置判断可用性，OpenClaw 空 model 允许使用默认模型；缓存 / 日志使用 `openclaw-default` 运行时标识。

## ACS-Year-AI-08B 结果

状态：Done。

实现摘要：

- 修正年度生成对 OpenClaw 默认模型的可用性判断，避免把年度功能绑定到具体模型配置。
- 修复 AI 报告缓存安全检查：允许后端回填的 `detail_link`，仍禁止本地路径、raw FIT、points、track_json、token 和旧 memory 字段。
- 在真实 DB 上完成 2024 年度首次 AI 生成。
- 在真实 DB 临时拷贝上完成 2023 年度事实变化后的 stale -> ready 更新验证。
- 完成真实数据状态抽样和视觉逐项验收记录。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_year_llm_prompt.py tests/test_career_year_insight_read_api.py -q
28 passed, 6 subtests passed in 0.58s

.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_generate_api.py tests/test_career_year_ai_report_validation.py tests/test_career_memory_retirement.py -q
34 passed, 6 subtests passed in 0.57s

.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_year_request_isolation_frontend.py -q
17 passed in 0.08s
```

真实 AI 结果：

```text
真实 DB 2024 首次生成：ready / generated / openclaw-default / headline=夏日集中发力，首个10公里完赛
临时拷贝 2023 更新验证：ready -> stale -> ready，activity_count 4 -> 5
```

Review 结论：通过。真实 AI 链路不记录 Prompt、Snapshot、token 或 raw response；真实活动表未被受控样例污染；未打包 DMG。

下一任务：`ACS-Year-AI-08C`。

## ACS-Year-AI-08C 工程级提示词

目标：完成跨平台代码检查、发布门禁与最终文档收口，准确标记代码级、真实 AI、产品验收、macOS 打包、Windows 真机等完成等级。

范围：允许修改最终完成报告、任务状态、执行日志和必要的契约文档；允许执行代码级测试、静态检查、JSON 解析、Python 编译和可行的 macOS `.app` 构建验证；不得执行最终 DMG 打包。

约束：检查 SQLite migration、线程/锁、时间与时区、JSON、日志、pywebview、LLM 调用证书/超时/编码/打包依赖；Windows 只能做代码级检查，不伪装真机验收；macOS 若执行打包，只能到 `.app` 或构建日志验证，不运行 DMG 创建；同步交付手册、任务清单、API 契约、执行日志和最终完成报告；记录未完成边界、已知风险、回滚方式和下一步建议。

预期文件：

- `docs/acs_year_ai_summary_completion_report.md`
- `docs/acs_next_annual_ai_summary_task_list.md`
- `docs/acs_next_annual_ai_summary_execution_log.md`

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_*.py -q
.venv312/bin/python -m pytest tests/test_career*.py -q
.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

完成定义：文档、代码、API 和测试契约一致；完成等级准确；没有未说明的阻塞项或数据风险；明确未执行 DMG 打包。

## ACS-Year-AI-08C 结果

状态：Done。

实现摘要：

- 完成最终完成报告 `docs/acs_year_ai_summary_completion_report.md`。
- 执行年度测试全集、ACS 宽回归、Python 编译、API JSON 解析。
- 执行 macOS `.app` 构建验证，输出到 `dist/acs_year_ai_08c/脉图.app`。
- 执行 `.app` 产物存在性、关键资源和 codesign 验证。
- 明确未执行 DMG 打包、notarization、Windows 真机和 Windows 打包。
- 记录真实 AI 写入边界、回滚方式和下一步建议。

验证结果：

```text
.venv312/bin/python -m pytest tests/test_career_year_*.py -q
98 passed, 10 subtests passed in 0.91s

.venv312/bin/python -m pytest tests/test_career*.py -q
578 passed, 38 subtests passed in 3.14s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed

PYTHONPATH=. .venv312/bin/pyinstaller HikingTrackAnalyzer.spec --noconfirm --distpath dist/acs_year_ai_08c --workpath build/acs_year_ai_08c
Build complete

codesign --verify --deep --strict --verbose=2 dist/acs_year_ai_08c/脉图.app
valid on disk; satisfies its Designated Requirement
```

Review 结论：通过。文档、代码、API 和测试契约一致；完成等级已区分代码级、真实 AI、产品验收、macOS `.app`、DMG、Windows 真机；未执行 DMG 打包。

下一任务：无。除最终 DMG 打包外，年度 AI 总结任务清单已完成。

## 2026-07-14 叙事 v2 增量启动摘要

首次完整阅读形成的项目摘要继续有效：Year Snapshot 是 AI 唯一上下文；Activity/Resolver 拥有事实语义；年度更新由 `source_fingerprint` 驱动；年卡片只导航；前端生成请求只传 `year`；模型来自脉图现有运行时配置，功能不写死模型；旧报告和生成失败保护规则不变。

本次需求变化：用户可见结果从工程字段卡片升级为一篇连续年度故事，重点回答年度努力、成绩、比赛、进步、节奏和写给下一年的话；AI 负责温暖克制的叙事，后端继续负责数字、日期、成绩、证据和链接；生成过程必须有明确过渡反馈；未来分享图片只预留母稿字段，本期不实现。

## ACS-Year-AI-09A 工程级提示词

目标：冻结完整长文、AI 语气、事实/叙事边界、v1 兼容升级和生成中反馈契约。

范围：仅修改年度 AI 交付手册、任务清单和执行日志，不修改运行时代码。

约束：保持 Snapshot、fingerprint、缓存安全、年卡片导航、任意运行时模型配置和只传 `year` 的 API 边界；v1 报告不得丢失；分享图片不在本期实现；不得打包 DMG。

验证命令：

```bash
rg -n "acs.year.report.v2|温暖、克制、真诚|format_upgrade_available|正在整理你的|ACS-Year-AI-09[ABCDE]" docs/acs_next_annual_ai_summary_delivery_manual.md docs/acs_next_annual_ai_summary_task_list.md
git diff --check -- docs/acs_next_annual_ai_summary_delivery_manual.md docs/acs_next_annual_ai_summary_task_list.md docs/acs_next_annual_ai_summary_execution_log.md
```

完成定义：v2 结构、章节省略、语气、证据回填、事实导语、v1 迁移、生成过渡和五项实施顺序均有唯一清晰契约；静态检查和 diff review 通过。

## ACS-Year-AI-09A 结果

状态：Done。

实现摘要：交付手册已冻结完整文章式报告、v2 schema、动态章节、温暖克制语气、后端事实导语、v1 一次性格式升级和生成过渡；任务清单新增 `09A` 至 `09E` 有序增量。

验证结果：契约关键词检查和 `git diff --check` 通过。

Review 结论：通过。改动仅涉及约定文档；未改变 Snapshot、fingerprint、运行时模型配置、年卡片/API 边界或 DMG 状态。

下一任务：`ACS-Year-AI-09B`。

## ACS-Year-AI-09B 工程级提示词

目标：实现 v2 Prompt、严格 schema 校验、证据回填和后端文章 ViewModel，使任何脉图已配置可用模型都能生成统一形态的完整年度故事。

范围：允许修改 `llm_backend.py`、`career_backend.py` 和年度 Prompt/报告校验/服务测试；不得改前端、Snapshot、fingerprint、模型配置来源或生成 API payload。

约束：Prompt 只接收 Year Snapshot；AI 不输出精确事实或 HTML；章节仅允许固定 type 并按顺序；缺少赛事/进步/同比事实时删除对应章节；后端生成事实导语并回填 evidence；所有文本清洗限长；不得打包 DMG。

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_llm_prompt.py tests/test_career_year_ai_report_validation.py tests/test_career_year_insight_service.py -q
.venv312/bin/python -m py_compile llm_backend.py career_backend.py
```

完成定义：Prompt 和 schema 为 v2；模型选择继续来自统一配置；合法报告得到完整 article ViewModel，非法章节/证据/文本安全降级；定向测试和 adaptive diff review 通过。

## ACS-Year-AI-09B 结果

状态：Done。

实现摘要：Prompt/schema 升级为 v2；新增固定章节顺序、基础章节门禁、可选章节事实门禁、evidence 类型回填、后端事实导语、长文文本清洗和精确数字句过滤；保留 legacy 字段别名供前端迁移期读取；模型仍从统一运行时配置取得。

验证结果：19 个 Prompt、报告校验和只读服务定向测试通过；Python 编译与 diff check 通过。

Review 结论：通过。高风险点为 AI 不可信结构与事实复述，现由 schema、章节白名单、证据类型、基础章节、数字拒绝和后端事实导语共同收口；未改 Snapshot/fingerprint/API payload。

下一任务：`ACS-Year-AI-09C`。

## ACS-Year-AI-09C 工程级提示词

目标：保持 v1 报告可见，并允许同一事实指纹受控生成一次 v2 报告。

范围：允许修改 `career_backend.py`、年度 read/generate/cache 测试和必要 API 契约；不得删除历史缓存、改变事实指纹、开放 force/model/prompt 前端参数或改前端渲染。

约束：read API 零 LLM；只有当前同指纹报告不是 v2 时返回 `format_upgrade_available=true`；生成 API 将格式升级视为受控允许动作；v2 成功原子切换、失败保留 v1；v2 已存在时禁止重复；测试 generator 默认使用 v2 prompt。

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_service.py tests/test_career_year_generate_api.py tests/test_career_ai_insights_repository.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

完成定义：v1 可读、升级标识正确、一次性升级成功/失败/缓存/并发受控，所有定向测试与 adaptive diff review 通过。

## ACS-Year-AI-09C 结果

状态：Done。

实现摘要：只读 ViewModel 新增格式升级标识；生成门禁允许同指纹 v1 一次升级 v2；失败保留 v1、成功原子切换且 v2 禁止重复；修复缓存 ID 误用 Snapshot 排除字段导致同指纹不同 Prompt/模型 ID 冲突的问题。

验证结果：32 个只读服务、生成 API 和缓存仓储测试及 6 个子测试通过；Python 编译与 diff check 通过。

Review 结论：通过。缓存 ID 仍由完整唯一键稳定生成，旧行无需迁移；已有同键行继续由数据库复合唯一约束更新，格式升级不会改变事实指纹或开放前端模型参数。

下一任务：`ACS-Year-AI-09D`。

## ACS-Year-AI-09D 工程级提示词

目标：把 v2 报告渲染为一篇连续可读的年度故事，并让生成过程有清晰、即时且可访问的反馈。

范围：允许修改 `track.html` 和年度前端契约测试；不得改 Overview 年卡片只导航边界、后端 Snapshot、模型配置或生成 API payload。

约束：v2 顺序为标题/副标题/事实导语/开篇/正文章节与证据/收束/写给下一年；v1 使用兼容视图；格式升级按钮只由后端标识驱动；生成中保留事实/旧报告，显示“正在整理你的 {year} 年运动故事”、轮换步骤和 skeleton；禁用重复点击；尊重 reduced motion；年份 request token 隔离不变。

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_request_isolation_frontend.py tests/test_career_year_card_navigation_frontend.py -q
```

完成定义：v2 文章与 v1 兼容均可渲染；生成/更新/格式升级操作正确；生成反馈明确且无伪造百分比；前端安全、键盘、切年隔离测试与 adaptive diff review 通过。

## ACS-Year-AI-09D 结果

状态：Done。

实现摘要：新增 v2 单列文章渲染、事实导语、正文段落、证据回跳、收束和写给下一年；v1 继续走兼容视图；ready 旧格式显示升级动作；生成中展示年度故事提示、五步轮换与 skeleton，并在成功、失败、切年和切换模式时释放计时器。

验证结果：21 个年度前端渲染、模式、请求隔离和年卡导航测试通过；diff check 通过。

Review 结论：通过。所有 AI 文本均经 `safeHtml`；证据回跳只使用后端 activity id；前端请求仍只传 `year`；reduced motion、键盘和晚到响应边界保留。

下一任务：`ACS-Year-AI-09E`。

## ACS-Year-AI-09E 工程级提示词

目标：完成叙事 v2 的自动化宽回归、真实 OpenClaw 链路验收、累计 review 和文档状态收口。

范围：允许运行年度/ACS 相关测试、读取真实 DB、使用脉图现有模型配置生成一份受控年度 v2 报告、更新执行日志/任务清单/完成报告和必要契约；不得打包 DMG。

约束：真实调用不记录完整 Prompt、Snapshot、token 或 raw response；不写 canonical 活动/赛事/PB/成就表；若无可升级/生成年份只做只读检查；测试失败最多定向修复三轮；最终 review 检查跨任务 schema、缓存、API、前端和旧报告兼容。

验证命令：

```bash
.venv312/bin/python -m pytest tests/test_career_year_*.py tests/test_career_ai_insights_repository.py -q
.venv312/bin/python -m pytest tests/test_career*.py -q
.venv312/bin/python -m py_compile career_backend.py llm_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
```

完成定义：全部自动化门禁全绿；真实链路能生成或升级 v2 且使用运行时模型配置；无 canonical 污染；累计 review 无阻塞项；文档准确标记完成及 DMG 未执行。

## ACS-Year-AI-09E 结果

状态：Done。

实现摘要：完成年度与 ACS 生涯宽回归；真实运行时配置确认为 OpenClaw CLI，未指定功能内模型；2025 v1 报告成功升级为 v2。真实首轮暴露 OpenClaw 会在叙事中复述数字，随后将安全策略调整为删除含精确数字的 AI 句子并由本地安全句补位，后端事实导语/evidence 继续承担数字展示。

验证结果：

```text
年度测试：114 passed, 10 subtests passed
ACS 生涯宽回归：587 passed, 38 subtests passed
Python py_compile：passed
docs/js_api_contract.json：valid JSON
真实 2025：ready / generated / acs.year.report.v2 / acs.year.summary.zh-CN.v2 / openclaw-default
章节：annual_story / progress / rhythm / comparison
fact_lead / closing / letter_to_next_year：present
canonical Activity/Race/PB/Achievement 表计数：unchanged
```

Review 结论：通过。累计高风险点包括 schema 大版本、同指纹跨 Prompt 缓存、旧报告切换、AI 数字复述、DOM 文本安全、计时器与晚到响应；均有实现门禁和测试覆盖。API 仍只接受 `year`，模型仍来自脉图运行时配置，未执行 DMG 打包。

下一任务：无。`ACS-Year-AI-09A` 至 `09E` 全部完成。

## ACS-Year-AI-FIX-01：生成时间当地时区展示

问题：`career_ai_insights.generated_at` 以 UTC 正确持久化，但年度报告只读 API 原样返回 `+00:00`，前端又直接显示 ISO 字符串，导致中国本地用户看到 UTC 时间。

修复：保持数据库 UTC、缓存排序和审计语义不变；新增年度报告显示时间转换，将 API 顶层、report 和 generation 中的 `generated_at` 转为运行设备当地时区；前端使用 `toLocaleString` 输出本地可读时间；同步交付手册和 API 契约。

验证：

```text
真实 2025 缓存 stored_offset = +00:00
年度 API generated_at offset = +08:00
report.generated_at offset = +08:00
年度测试 = 115 passed, 10 subtests passed
ACS 生涯宽回归 = 588 passed, 38 subtests passed
```

Review：通过。时间转换只发生在展示边界，不修改数据库值、不改变缓存键、fingerprint、排序或生成状态。
