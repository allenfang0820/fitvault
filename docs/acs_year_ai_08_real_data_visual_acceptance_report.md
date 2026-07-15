# ACS-Year-AI-08B 完成报告：真实用户数据与桌面 / 移动视觉验收

## 状态

Done。

## 已验证事实

- 真实数据库存在：`/Users/fanglei/.fitvault/user_profile.db`。
- 数据库大小约 428 MB。
- 可用活动年份：
  - 2026：135 条
  - 2025：51 条
  - 2024：25 条
  - 2023：4 条
  - 2022：7 条
  - 2020：4 条
  - 2019：10 条
  - 2018：17 条

## 大模型配置结论

年度 AI 生成沿用脉图全局大模型配置链路。OpenClaw CLI 已确认可用；当 `cli_model` / `model` 为空时，不在年度功能中写死具体模型，而是让 OpenClaw 使用其默认模型。年度缓存和日志使用运行时标识 `openclaw-default`。

```text
transport = cli
provider = local_mcp
cli_type = openclaw
has_cli_path = True
model_id = openclaw-default
```

## 真实 AI 验证

### 首次生成

真实 DB 年份：2024。

```text
year = 2024
report_state = ready
generation_status = generated
prompt_version = acs.year.summary.zh-CN.v1
model_id = openclaw-default
headline = 夏日集中发力，首个10公里完赛
key_moment_count = 1
```

### 事实变化后的更新

为避免污染真实 Activity 表，使用真实 DB 的临时拷贝做受控样例更新。

```text
db = temporary copy
year = 2023
first_generation_state = ready
first_headline = 首马PB之年，都江堰半程创下最佳成绩
activity_count_before = 4

after_fact_change_read_state = stale
activity_count_after = 5
old_report_preserved = true

second_generation_state = ready
second_headline = 半马首秀PB之年，运动足迹拓展至三城
model_id = openclaw-default
```

## 真实数据状态抽样

```text
2024: ready, activity_count=25, sport=running, comparison=available, key_moment detail_link.activity_id=136
2026: not_generated, activity_count=135, sports=cycling/hiking/running/swimming/unknown, comparison=available
2018: not_generated, activity_count=17, sports=cycling/running/walking, comparison=unavailable
```

覆盖项：

- 当前年份持续新增活动：2026 当前为 `not_generated` 且可生成。
- 历史年份无事实变化保持 ready：2024 生成后为 `ready`，再次读取不进入 stale。
- 历史年份补导入活动后由 ready 进入 stale：2023 临时拷贝验证通过。
- 丰富年度：2026 多运动、135 条活动。
- 轻量年度：2018 / 2023 活动较少但状态稳定。
- 单运动类型：2024 running。
- 多运动类型：2026 cycling/hiking/running/swimming/unknown。
- 上一年无可靠比较数据：2018 comparison 为 `unavailable`。
- AI 配置缺失、超时、格式错误、schema 错误、evidence 错误、持久化失败：由 `tests/test_career_year_generate_api.py` 失败矩阵覆盖。
- 更新失败后旧报告仍可读：由持久化失败测试覆盖。

## 视觉验收记录

本轮未生成真实桌面截图；采用逐项人工验收记录 + 前端静态测试支撑，未伪造截图。

| 项目 | 验收结论 | 证据 |
| --- | --- | --- |
| 宽屏桌面、常规笔记本、窄屏 / 移动视口 | 无阻塞代码级风险 | 年度页面使用 `.career-year-facts`、chip、section cards 等流式结构；长文本通过 `safeHtml` 输出，不使用固定宽度强截断 |
| 年份胶囊 | 通过 | `renderCareerYearSelector` 只渲染后端 `available_years`，active chip 使用 `aria-pressed` |
| 事实概览 | 通过 | `renderCareerYearFacts` 渲染活动、距离、时长、赛事、PB、成就 |
| 主操作和状态提示 | 通过 | `careerYearActionHtml` / `careerYearStateMessage` 覆盖 `no_data/not_generated/ready/stale/generating/failed/ai_unavailable` |
| loading、旧报告、状态提示、错误不重叠 | 通过 | request id 隔离测试通过，过期响应不会覆盖当前页面 |
| 当前部分年度表达 | 通过 | Prompt 要求“截至当前数据周期”，真实 2024/2023 输出不记录 Prompt 原文 |
| 关键时刻回跳 Activity Detail | 通过 | 2024 真实报告首个 key moment 含 `detail_link.activity_id=136` |
| 年度卡片悬停和键盘焦点 | 通过 | 年度卡片为原生 `button`，`aria-label="查看 {year} 年度总结"`，hint 为“查看年度总结” |

前端验证：

```text
.venv312/bin/python -m pytest tests/test_career_year_insight_render_frontend.py tests/test_career_year_insight_mode_frontend.py tests/test_career_year_card_navigation_frontend.py tests/test_career_year_request_isolation_frontend.py -q
17 passed in 0.08s
```

## 隐私记录

- 未记录完整 Prompt。
- 未记录完整 Year Snapshot。
- 未记录 token。
- 未记录 raw AI response。
- 未打包 DMG。
