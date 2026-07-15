---
title: ACS 年度 AI 总结 v4 分享欲与成就感语气完成报告
version: v0.1.0
updated: 2026-07-14
source:
  - docs/acs_next_annual_ai_summary_delivery_manual.md
  - docs/acs_next_annual_ai_summary_task_list.md
  - docs/acs_next_annual_ai_summary_execution_log.md
---

# ACS 年度 AI 总结 v4 分享欲与成就感语气完成报告

## 1. 目标

本轮解决年度报告“过于平实”的问题：在不突破事实边界的前提下，让用户读完更有成就感，也更愿意截图分享。

目标读感：

```text
这一年我真的做成了一些事，值得发出来，也值得被自己看见。
```

## 2. 主要变更

- `llm_backend.py`
  - Prompt 升级为 `acs.year.summary.zh-CN.v4`。
  - 明确要求标题、开篇、章节和收束更有年度感、分享欲和成就感。
  - 允许“点亮城市、留下坐标、跨过新的距离、把运动带去更多地方”等表达。
  - 继续禁止营销鸡血、生活事件推断、心理动机推断和无事实城市扩写。

- `career_backend.py`
  - 当前内容 schema 升级为 `acs.year.report.v3`，让同事实指纹旧报告可以走受控格式升级。
  - 保持 `source_fingerprint` 不变，不把 Prompt 变化伪装成年度事实更新。
  - 清理 `closing`、`letter_to_next_year`、`share_caption` 的不完整句尾。

- `track.html`
  - 前端文章渲染兼容 `acs.year.report.v2` 与 `acs.year.report.v3`。
  - 旧 v2 报告继续可读，v3 报告按同一文章视图展示。

- 文档与契约
  - 交付手册冻结 v4 分享欲与成就感语气。
  - 任务清单新增并完成 Milestone G / `ACS-Year-AI-11A`。
  - API 契约说明当前年度报告母稿为 v3，旧 v1/v2 继续兼容。

## 3. 验证

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

## 4. 真实链路验收

已在真实年度缓存中生成 v4/v3-schema 报告：

```text
2026: acs.year.report.v3 / acs.year.summary.zh-CN.v4
2025: acs.year.report.v3 / acs.year.summary.zh-CN.v4
2024: acs.year.report.v3 / acs.year.summary.zh-CN.v4
```

其中 2025 未出现 `footprints` 章节，是因为模型未选择有效城市证据；校验规则按“无有效证据自然省略”处理，未强制编造城市段落。

## 5. 未执行项

- 未打包 DMG。
- 未实现社交媒体分享图片；本轮只保留文章母稿和分享文案能力。
