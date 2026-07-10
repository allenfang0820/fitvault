# ACS-Next-02 Memory Gallery 媒体生命周期闭环完成报告

## 交付范围

- 新增 Memory Gallery 单张照片选择 API：`pick_and_save_career_memory_photo(payload)`。
- 本地图片仅通过系统选择器进入，复制到应用受控目录 `career_media/memory_photo/`。
- 后端仅保存 `memory/photo/...` 安全逻辑引用，API 返回白名单 MemoryItem view model。
- `get_career_memory` 在受控图片文件存在时返回 `thumbnail_url=data:image/...`，不返回 `storage_ref`、本地路径或原始活动数据。
- 前端新增“添加照片”表单，并在记忆列表渲染白名单缩略图。
- 既有 `deactivate_career_memory_item` 扩展到照片卡片入口，完成软停用闭环。

## 契约边界

- Activity 仍是单一事实源；照片记忆必须绑定 `activity_id`。
- 前端不推断赛事、PB、成就或训练事实，只渲染后端返回的 MemoryItem。
- 不暴露 raw FIT、points、track_json、file_path、storage_ref、SQLite schema 或本地绝对路径。
- 本任务不调用 LLM，不生成 AI Snapshot。
- 本任务未完成复杂相册、批量管理、真实缩略图生成、媒体文件物理删除、轨迹截图自动生成。
- macOS / Windows 打包与真机验收未执行，仍保持未完成状态。

## 主要改动

- `career_backend.py`
  - `photo` MemoryItem 在受控图片存在时返回可渲染 `thumbnail_url`。
- `main.py`
  - 抽象受控图片复制工具。
  - 新增 `CAREER_MEMORY_PHOTO_DIRNAME` 与 `pick_and_save_career_memory_photo`。
- `track.html`
  - Memory Gallery 新增添加照片入口、照片表单、缩略图渲染。
  - 照片记忆可通过既有停用 API 软停用。
- `docs/js_api_contract.json`
  - 登记 `pick_and_save_career_memory_photo` 契约。
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
  - 标记 `ACS-Next-02` 代码闭环完成，并保留后续未完成项。
- `tests/test_career_memory_photo_lifecycle_api.py`
  - 覆盖选择、复制、保存、白名单返回、渲染、停用、取消和非图片拒绝。

## 下一步建议

`ACS-Next-03`：Race Map / 赛事足迹完整能力。
