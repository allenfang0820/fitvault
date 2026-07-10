# ACS-Phase7-06 Career Insight Phase7 闭环验收与任务清单回填完成报告

## 任务范围

本任务对 Phase 7：AI Career Insight 的 01-05 已完成任务做阶段闭环验收，并回填 ACS 开发任务清单。

本任务只做：

- Phase7 完成状态核验。
- Career Insight 当前实现链路核对。
- 任务清单回填。
- 阶段闭环报告补充。
- 相关测试回归。

未做：

- 不接真实 LLM。
- 不新增 prompt 构建。
- 不改 Career Insight 后端行为。
- 不改 Career Insight 前端 UI。
- 不改 `main.py`、`career_backend.py` 或 `docs/js_api_contract.json`。

## Phase7 完成范围

Phase7 当前可判定为“本地 fallback 洞察闭环”：

- `build_career_snapshot(conn=None)`
  - 已生成白名单 Career Snapshot。
  - Snapshot 只包含 summary、primary_sport、PB 摘要、major achievements、timeline digest、representative memories。
- `save_career_snapshot(conn=None)`
  - 已支持后端受控保存 latest Snapshot。
- `get_latest_career_snapshot(conn=None)`
  - 已支持只读调试读取。
  - 不自动生成，不调用 LLM。
- `generate_career_insight(payload=None, conn=None)`
  - 已支持本地 fallback insight。
  - 支持 `refresh_snapshot` 受控刷新。
  - 不调用 `call_llm`，不调用 `llm_backend`。
- pywebview API
  - 已暴露 `get_latest_career_snapshot` 只读 API。
  - 已暴露 `generate_career_insight` fallback API。
- Career Insight 前端
  - 已接入「运动生涯」页面。
  - 已支持加载、刷新、空态、错误态、fallback 展示与移动端约束。
  - 不展示 Snapshot 原文、Snapshot JSON 或 debug JSON。

## 已完成任务列表

- `ACS-Phase7-01：Career Snapshot 生成器白名单骨架`
- `ACS-Phase7-02：Career Snapshot 持久化与只读调试 API`
- `ACS-Phase7-03：Career Insight 后端生成 API 骨架`
- `ACS-Phase7-04：Career Insight 前端只读占位渲染`
- `ACS-Phase7-05：Career Insight 前端视觉验收与空状态细化`
- `ACS-Phase7-06：Career Insight Phase7 闭环验收与任务清单回填`

## 当前明确未做事项

- 未接入真实 LLM。
- 未构造真实 AI Career Insight prompt。
- 未新增 AI 输出持久化表。
- 未新增 AI 结果缓存策略。
- 未把用户故事全文、媒体引用、轨迹点或本地路径送入 AI。
- 未把 Career Snapshot 原文展示给用户。
- 未把真实 AI 能力包装成已经可用的产品文案。

以上事项应进入后续增强任务，不能视为 Phase7 当前闭环的一部分。

## 安全边界确认

Phase7 当前闭环保持以下边界：

- 不调用 `call_llm`。
- 不调用 `llm_backend`。
- 不展示 Snapshot 原文。
- 不展示 Snapshot JSON / debug JSON。
- 不读取或展示以下禁止字段：
  - `points`
  - `points_json`
  - `track_json`
  - `raw_records`
  - `fit_records`
  - `file_path`
  - `advanced_metrics`
  - `shadow_diff_json`
  - `sqlite_schema`
  - `schema`
  - `storage_ref`
  - `path`
  - `thumbnail_url`
  - `detail_link`

说明：项目其他既有模块和 API 契约文档中仍可能出现这些字段名，用于原有运动详情、复盘、记忆相册或禁止项说明；Phase7 验收以 Career Insight / Career Snapshot 相关函数、前端渲染切片和测试断言为准。

## 任务清单回填

已更新 `docs/脉图运动生涯系统（ACS）开发任务清单.md`：

- 将 Phase7 已完成项标记为完成。
- 明确 Phase7 当前完成的是本地 fallback 闭环。
- 将真实 AI 接入、prompt 契约、AI 输出缓存与更高阶降级策略放入后续增强。

## macOS / Windows 兼容性

- Phase7 未引入平台专有 API。
- 后端 SQLite 读写使用参数化 SQL 和受控连接。
- Snapshot / Insight JSON 使用 UTF-8 文案，不依赖系统路径分隔符。
- 前端只通过 pywebview API 调用 `generate_career_insight({ refresh_snapshot })`。
- 不读取、不拼接、不展示本地绝对路径。
- Windows pywebview 接口暂不可用或初始化较慢时，前端错误态限制在 Career Insight 模块内。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_snapshot_builder.py
python3 -m pytest tests/test_career_snapshot_persistence.py
python3 -m pytest tests/test_career_insight_api_skeleton.py
python3 -m pytest tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_career_insight_frontend_visual_contract.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py
```

结果：

- Snapshot Builder：5 passed
- Snapshot Persistence：9 passed
- Career Insight API Skeleton：11 passed
- Career Insight Frontend Render：8 passed
- Career Insight Frontend Visual Contract：6 passed
- Track HTML Sync Logic：24 passed
- JS API 契约 JSON：合法
- Career Overview / Timeline / Memory Frontend 回归：22 passed

说明：当前 macOS 系统 Python 环境仍有 `urllib3` / LibreSSL warning，不影响测试结果。

## 阶段结论

Phase7 可以判定为阶段闭环，但闭环口径是：

> Career Insight 本地 fallback 洞察闭环完成，真实 LLM Career Insight 尚未开始。

这个状态满足进入后续阶段的条件，因为：

- Snapshot 白名单已建立。
- Snapshot 持久化与只读读取已建立。
- Insight API envelope 已建立。
- 前端占位区已建立。
- 安全边界已有测试守护。
- 真实 AI 能力没有被提前承诺或误展示。

## 下一个建议任务

建议进入 `ACS-Phase8-01：运动生涯前端页面阶段验收与 Phase8 任务清单重排`。

原因：

- 当前项目实际上已经在较早任务中完成了一级「运动生涯」入口、Overview、Timeline、Memory 与 Career Insight 的轻量前端接入。
- 原任务清单的 Phase8 仍显示为未完成，需要先做一次“设计清单 vs 实际实现”的重排，避免后续重复建设页面骨架。
