# ACS-Next-02R 赛事活动详情页照片入口重构完成报告

## 交付范围

- Memory Gallery 移除照片添加入口，仅保留集中只读展示。
- Activity Detail 概览页「圈速统计」下方新增赛事照片管理器。
- 当前活动详情上下文自动绑定 `activity_id`，用户不再手动填写活动 ID。
- 仅赛事活动显示照片管理器；显示依据来自后端活动字段 `is_race`。
- 新增赛事照片 API：
  - `get_activity_race_photos`
  - `pick_and_add_activity_race_photos`
  - `reorder_activity_race_photos`
- 单个赛事活动最多 5 张照片。
- 支持一次多选添加，超出剩余额度时在复制前拒绝。
- 支持拖拽排序，排序第一张写入 `overview_banner` 角色并作为 Banner 来源。

## 契约边界

- Activity 仍是唯一事实源；照片绑定当前 Activity Detail 的 `activity_id`。
- 前端不从标题、距离、配速或 DOM 推断赛事事实。
- 前端不提交本地路径，不调用 `save_career_memory_media` 作为任意媒体入口。
- 后端内部可使用 `storage_ref`，但 API 返回值不暴露 `storage_ref`、`file_path`、本地绝对路径、raw FIT、points、track_json 或 SQLite schema。
- 文件复制到应用受控目录 `career_media/activity_race_photo/`。
- 不调用 LLM，不生成 AI Snapshot。
- 不做复杂相册、媒体物理删除、真实缩略图生成、云同步或打包真机验收。

## 主要改动

- `career_backend.py`
  - 新增活动赛事照片读取、添加、排序语义函数。
  - 使用 `career_memory_items.metadata_json.role/order_index` 保存排序与 Banner 角色。
- `main.py`
  - 新增 Activity Detail 上下文照片 API wrapper。
  - 多选前先校验剩余额度，避免超额复制文件。
- `track.html`
  - 移除 Memory Gallery 照片表单。
  - 在 Activity Detail 圈速统计下方新增 5 格赛事照片管理器。
  - 支持添加照片与拖拽排序。
- `docs/js_api_contract.json`
  - 登记新增 API 契约。
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
  - 标记 `ACS-Next-02R` 入口重构完成，并保留后续未完成项。
- `tests/test_activity_race_photo_manager_api.py`
  - 覆盖添加、读取、排序、超额、取消、非赛事拒绝和路径不泄露。

## 下一步建议

`ACS-Next-03`：Race Map / 赛事足迹完整能力。
