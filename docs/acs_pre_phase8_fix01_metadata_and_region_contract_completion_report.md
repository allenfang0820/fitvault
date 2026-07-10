# ACS-PrePhase8-Fix01：metadata 脱敏与地区刷新契约登记完成报告

## 背景

Phase8 前 review 发现两个需要优先修复的问题：

1. ACS Race/PB/Achievement/Overview 公开 API 的 `display_metadata_json` 清洗未覆盖 `storage_ref`、`path`、`thumbnail_url`、`detail_link`，存在把本地路径、存储引用或内部跳转结构透出到 public metadata 的风险。
2. `main.Api.refresh_activity_region` 已由前端调用，但未登记到 `docs/js_api_contract.json`。

## 修改文件

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_races_api.py`
- `tests/test_career_pb_api.py`
- `tests/test_career_achievements_api.py`
- `tests/test_career_timeline_engine_closure.py`
- `tests/test_career_overview_api_closure.py`
- `tests/test_fit_sync.py`

## 修复内容

- 新增 `ACS_PUBLIC_METADATA_FORBIDDEN_KEYS`，在原公开响应禁止字段基础上补充：
  - `storage_ref`
  - `path`
  - `thumbnail_url`
  - `detail_link`
- `_sanitize_public_metadata()` 改为使用 `ACS_PUBLIC_METADATA_FORBIDDEN_KEYS` 递归清洗 metadata。
- 保留 Race/PB/Achievement/Timeline/Overview view-model 顶层 `detail_link`，因为它是前端活动详情跳转契约的一部分；本次只禁止 `display_metadata` 内部泄露 `detail_link`。
- `CAREER_SNAPSHOT_FORBIDDEN_KEYS` 继续覆盖同一组扩展禁止字段。

## API 契约登记

`docs/js_api_contract.json` 新增：

- `refresh_activity_region`
- 分类：`activity`
- 参数：`activity_id:int`
- 返回：统一 envelope，`data` 内仅包含地区刷新结果字段
- 契约边界：不读取或返回 `raw FIT`、`points`、`track_json`、`file_path` 或 `SQLite schema`

未改动 `refresh_activity_region` 运行逻辑。

## 测试覆盖

- Race/PB/Achievement API 增加或扩展 metadata 污染样本，覆盖扩展禁止字段的递归清洗。
- Overview 聚合层验证 latest race、latest PB、代表 PB、代表成就中的 `display_metadata` 不泄露扩展禁止字段。
- Timeline 验证节点不返回 `display_metadata`，同时继续保留顶层 `detail_link`。
- `test_fit_sync.py` 增加 `refresh_activity_region` 契约登记断言。

## macOS / Windows 兼容性

- 脱敏测试同时覆盖 Unix 风格路径 `/Users/`、`/tmp/` 与 Windows 风格 `\\Users\\`。
- 本次不新增平台相关路径拼接、文件 IO、系统命令或 UI 行为。
- JSON 契约保持 UTF-8 文本与标准 JSON 格式。

## 验证结果

已通过：

```bash
python3 -m json.tool docs/js_api_contract.json >/dev/null
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m pytest tests/test_career_races_api.py tests/test_career_pb_api.py tests/test_career_achievements_api.py
python3 -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_overview_api_closure.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m pytest tests/test_fit_sync.py -k "refresh_activity_region or update_activity_title"
```

说明：macOS Python 环境仍出现既有 `urllib3/LibreSSL` warning，不影响本次测试通过。

## 边界确认

- 未新增 Phase8 功能。
- 未修改 UI。
- 未修改 `refresh_activity_region` 运行逻辑。
- 未修改 `update_activity_title` / `set_activity_race_flag` 行为。
- 未引入 LLM、`call_llm` 或新 prompt 逻辑。

## 下一个任务

建议回到原计划进入：

`ACS-Phase8-01：运动生涯前端页面阶段验收与 Phase8 任务清单重排`
