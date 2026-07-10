# ACS-Phase7-04 Career Insight 前端只读占位渲染完成报告

## 任务范围

本任务在「运动生涯」页面新增 Career Insight 的前端只读占位渲染区，展示 Phase7-03 后端返回的 fallback insight。

已完成：

- 新增 Career Insight 前端状态
- 新增「生涯洞察」section
- 新增 fallback insight 渲染
- 新增刷新本地洞察按钮
- Career tab 进入时自动加载本地洞察
- 新增前端静态契约测试

未实现：

- 不接真实 LLM
- 不拼 AI prompt
- 不展示 Snapshot 原文
- 不展示调试 JSON
- 不新增正式 AI 洞察承诺文案

## 修改文件

- `track.html`
  - 新增 Career Insight DOM 区块
  - 新增 Career Insight CSS
  - 新增 `appState.career.insight*` 状态
  - 新增 `normalizeCareerInsight`
  - 新增 `renderCareerInsight`
  - 新增 `renderCareerInsightLoading`
  - 新增 `renderCareerInsightError`
  - 新增 `loadCareerInsight`
  - Career tab 进入时调用 `loadCareerInsight({ refresh_snapshot: false })`
- `tests/test_career_insight_frontend_render.py`
  - 新增 Career Insight 前端边界测试
- `docs/acs_phase7_04_career_insight_frontend_placeholder_completion_report.md`

## 前端展示结构

新增 section：

```html
<section class="career-section" data-career-section="insight">
```

展示内容：

- 标题：`生涯洞察`
- 状态：`等待本地洞察` / `本地洞察可用`
- 来源轻量文本：`source · snapshot_version`
- fallback insight title
- fallback insight summary
- highlights 列表
- next_steps 列表
- disclaimer

按钮：

- `刷新本地洞察`
- 点击后调用 `loadCareerInsight({ refresh_snapshot: true })`

## API 调用方式

页面进入 Career tab 时自动调用：

```js
loadCareerInsight({ refresh_snapshot: false })
```

按钮刷新时调用：

```js
loadCareerInsight({ refresh_snapshot: true })
```

`loadCareerInsight` 只调用：

```js
window.pywebview.api.generate_career_insight(payload)
```

payload 只包含：

```json
{
  "refresh_snapshot": true
}
```

## 为什么不展示 Snapshot 原文

Career Snapshot 是给后端 AI 生成链路使用的压缩上下文，不是用户界面文档。

前端只展示 `generate_career_insight` 返回的 fallback insight，是为了：

- 避免用户误以为 Snapshot 是正式洞察文案。
- 避免调试 JSON 成为产品界面负担。
- 避免未来 Snapshot 字段变化直接影响 UI。
- 保持 AI 输入边界集中在后端。

## 按钮文案策略

按钮使用“刷新本地洞察”，没有使用“AI 深度总结”“生成 AI 洞察”等文案。

原因：

- 当前阶段不调用 LLM。
- 当前结果是本地 fallback，占位语义应当诚实。
- 后续真实 LLM 接入前，不提前承诺 AI 总结能力。

## forbidden 字段确认

前端 Career Insight 相关函数不读取、不展示、不透传：

- points / points_json
- track_json
- raw_records / fit_records
- file_path
- advanced_metrics
- shadow_diff_json
- sqlite_schema / schema
- storage_ref
- path
- thumbnail_url
- detail_link

不展示 Snapshot JSON，不使用 `JSON.stringify` 渲染调试数据。

## 不调用 LLM 确认

- 前端不调用 `call_llm`。
- 前端不调用 `get_latest_career_snapshot`。
- 前端不拼 prompt。
- 前端只调用 `generate_career_insight`。
- 后端当前 `generate_career_insight` 仍为 fallback 骨架。

## macOS / Windows 兼容性

- 使用普通 DOM / button / div / list 渲染。
- 未新增浏览器高级 API。
- 未新增路径处理逻辑。
- 未新增本地文件选择器。
- 移动端下 toolbar 单列排列，避免按钮与状态文本重叠。
- 中文文案保持 UTF-8。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_insight_frontend_render.py
python3 -m pytest tests/test_career_insight_frontend_render.py tests/test_career_insight_api_skeleton.py tests/test_career_snapshot_persistence.py tests/test_career_snapshot_builder.py tests/test_career_overview_frontend_render.py tests/test_career_timeline_frontend_render.py tests/test_career_memory_frontend_render.py tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- 新增前端测试：8 passed。
- 相关 ACS 前后端回归：79 passed。
- JS API 契约 JSON：合法。

说明：当前 macOS Python 环境仍有 urllib3 / LibreSSL warning，不影响测试结果。

## 下一个任务建议

建议进入 `ACS-Phase7-05：Career Insight 前端视觉验收与空状态细化`。

建议边界：

- 只做 UI 文案、状态、移动端可读性和手动验收补强。
- 不接 LLM。
- 不展示 Snapshot 原文。
- 不新增 prompt 或 AI 调用。
