# ACS-Phase9-04 完成报告：数据边界与前端零推断总审计

## 任务范围

- 审计 `career_backend.py` 的 Career public API、Snapshot 与 Insight 出口。
- 审计 `track.html` 中 Career/ACS 相关加载、渲染、编辑与停用函数。
- 审计 `docs/js_api_contract.json` 中 Career API 契约描述。
- 补充代码层回归测试，固化 ACS 数据边界与前端零推断约束。

## 发现与修复

- 未发现 ACS public API 向前端返回 raw FIT、points、track_json、file_path、storage_ref、SQLite schema 或本地绝对路径。
- 未发现 Career Snapshot / Career Insight 暴露 `thumbnail_url`、`detail_link`、本地路径或底层存储字段。
- 发现前端部分 Career API 调用仍使用手写 envelope 判断，已统一收敛为 `requireCareerApiData()`：
  - `loadCareerArchives()`
  - `loadCareerTimeline()`
  - `loadCareerInsight()`
  - `saveCareerMemoryEdit()`
  - `deactivateCareerMemoryItem()`
- 保持前端只消费后端 view model；赛事、PB、成就与时间轴事实仍由后端 resolver/API 负责，前端不从原始轨迹、距离、配速或 `sport_event` 推断事实。

## 新增/更新测试

- 新增 `tests/test_career_phase9_data_boundary_audit.py`
  - 验证 Career public API、Snapshot 与 Insight 不泄露危险 key、危险文本、本地绝对路径或底层存储字段。
  - 验证 Career 前端函数不调用 `call_llm`，不读取 `points_json`、`track_json`、`file_path`、`storage_ref`、`sqlite_schema` 等字段。
  - 验证 Career 前端主要 API 入口统一使用 `requireCareerApiData()`。
  - 验证 `docs/js_api_contract.json` 的 Career 契约不把危险字段写入返回结构。
- 更新 `tests/test_career_timeline_frontend_render.py`
  - 将时间轴加载测试从手写 envelope 判断迁移为 `requireCareerApiData()` 断言。
- 更新 `tests/test_career_insight_frontend_render.py`
  - 将 Insight 加载测试从 `res.data || {}` 迁移为 `requireCareerApiData()` 断言。

## 验证结果

```bash
python3 -m pytest tests/test_career_phase9_data_boundary_audit.py tests/test_career_timeline_frontend_render.py tests/test_career_insight_frontend_render.py tests/test_career_phase9_pywebview_envelope.py
```

结果：`22 passed`。

## 未执行项

- 未执行 Windows 真机验证。
- 未执行 Windows 打包验证。
- 未执行 macOS 打包产物验证。

上述验证按当前计划后置到开发完成后的打包验证阶段。

## 下一个建议任务

`ACS-Phase9-05`：macOS 代码层轻量验收与开发收口检查。

