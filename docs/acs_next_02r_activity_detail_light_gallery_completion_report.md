# ACS-Next-02R 赛事活动详情页轻量相册重构完成报告

## 本任务范围

本任务完成赛事 Activity Detail 概览页轻量相册闭环：

- 照片入口位于活动详情页概览页圈速统计下方。
- 使用当前活动详情上下文自动绑定 `activity_id`。
- Memory Gallery 保持集中展示，不提供上传、排序或删除入口。
- 同一赛事活动最多保存 5 张照片。
- 支持多选添加、宫格展示、拖拽排序。
- 排序第一张作为 Overview Banner。
- 支持删除照片，删除采用软删除。

## 修改文件

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `tests/test_activity_race_photo_manager_api.py`
- `tests/test_career_memory_media_frontend.py`
- `tests/test_career_phase9_macos_closure.py`

## 删除照片策略

- 删除接口为 `deactivate_activity_race_photo`。
- 仅将对应 `career_memory_items.status` 标记为 `inactive`。
- 不物理删除媒体文件。
- 删除后后端重排剩余 active 照片：
  - 第一张写为 `overview_banner`。
  - 其余写为 `race_gallery`。
  - `order_index` 从 0 连续重排。
- 删除最后一张后，`hero_banner_media.has_photo=false`，Overview 后续回到 `title_art` fallback。

## 契约边界

- `Activity` 仍是唯一事实源。
- ACS 只保存安全媒体引用和展示组织元数据。
- 前端不手填 `activity_id`，不自行拼接本地路径，不自行修改 Banner 角色。
- API 不返回 `storage_ref`、`file_path`、本地绝对路径、`file://`、raw FIT、points、track_json 或 SQLite schema。
- 不调用 LLM，不生成 AI Snapshot。
- 不改 FIT 解析、Race Resolver、PB Resolver 或 Achievement Resolver。

## 未完成事项

- 未做媒体文件物理删除。
- 未做复杂相册详情页或全屏大图浏览。
- 未做真实缩略图生成管线。
- 未做云同步。
- 未执行 macOS 打包产物验证。
- 未执行 Windows 打包或 Windows 真机验证。

## 验证命令

```bash
python3 -m pytest tests/test_activity_race_photo_manager_api.py tests/test_career_memory_media_frontend.py tests/test_career_overview_api_closure.py tests/test_career_overview_frontend_render.py tests/test_career_phase9_macos_closure.py -q
```

```bash
python3 -m pytest tests/test_career*.py tests/test_activity_race_photo_manager_api.py tests/test_track_html_sync_logic.py -q
```

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m py_compile career_backend.py main.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

## 下一个建议任务

`ACS-Next-03：Race Map / 赛事足迹完整能力`
