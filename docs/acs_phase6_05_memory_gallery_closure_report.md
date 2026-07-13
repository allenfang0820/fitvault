# ACS-Phase6-05 Memory Gallery 闭环验收报告

> 历史状态说明（2026-07-13）：本文记录 Phase 6 当时的交付结果，不再代表当前公开接口契约。后续产品决策已退役 `get_career_memory`、故事新增/编辑/停用、通用 photo/track 写入及旧照片选择器；当前仅保留赛事 Activity Detail 照片管理、赛事相册只读浏览与 Overview Banner 首图复用。现行接口以 `docs/js_api_contract.json` 为准。

## 结论

Phase 6 Memory Gallery 的轻量闭环已完成，可以进入 Phase 7 AI Career Insight。

当前闭环是“安全 MemoryItem 索引 + 轻量展示 + story 写入编辑 + photo/track 安全媒体引用”，不是复杂相册系统。ACS-Next-02 已补齐单张照片选择器与受控复制；复杂相册、批量管理、媒体物理删除、真实缩略图渲染和轨迹截图自动生成仍保留为后续增强。

## 能力矩阵

| 阶段 | 能力 | 状态 |
| --- | --- | --- |
| Phase6-01 | Memory Gallery 轻量只读、空状态、`has_media` 状态、Activity Detail 回跳 | 已完成 |
| Phase6-02 | story 型 MemoryItem 手动新增、inline 添加故事表单、payload 白名单 | 已完成 |
| Phase6-03 | story 原位编辑、MemoryItem 软停用、不物理删除 | 已完成 |
| Phase6-04 | photo / track 型 MemoryItem 安全媒体引用写入、`media_ref` 校验 | 已完成 |
| Phase6-05 | 任务清单回填、闭环审计、文档契约测试 | 已完成 |

## API 清单

### get_career_memory

- 只读 API。
- 返回 active MemoryItem 的安全 view model。
- 支持 `all/photo/story/track` 轻量筛选。
- 不返回 `storage_ref`、本地路径、raw FIT、points、track_json 或 SQLite schema。

### save_career_memory_story

- 写入 story 型 MemoryItem。
- 输入白名单：`activity_id/race_id/title/story`。
- 至少绑定 `activity_id` 或 `race_id`。
- 有 `activity_id` 时校验活动存在且未删除。
- `storage_ref` 固定为空。

### update_career_memory_story

- 仅允许编辑 active 且 `memory_type="story"` 的 MemoryItem。
- 输入白名单：`id/title/story`。
- 只更新 `title`、`story_text`、`metadata_json`、`updated_at`。
- 不改 `activity_id`、`race_id`、`memory_type`、`event_date`、`storage_ref`、`created_at`。

### deactivate_career_memory_item

- 软停用 MemoryItem。
- 输入白名单：`id`。
- 只将 `status` 更新为 `inactive`。
- 不物理删除数据库记录。
- 不删除或改写媒体文件。

### save_career_memory_media

- 写入 photo / track 型 MemoryItem。
- 输入白名单：`activity_id/race_id/memory_type/title/media_ref`。
- `memory_type` 仅支持 `photo` 或 `track`。
- `media_ref` 只允许应用受控目录内的相对引用或逻辑引用。
- `media_ref` 写入后端 `storage_ref`，公开 API 不返回 `storage_ref`。

## MemoryItem 类型支持

| 类型 | 当前支持 | 说明 |
| --- | --- | --- |
| story | 新增、展示、原位编辑、软停用 | 完成轻量闭环 |
| photo | 安全媒体引用写入、单张照片选择与受控复制、白名单图片展示、软停用 | 不做复杂相册、批量管理、媒体物理删除和真实缩略图 |
| track | 安全媒体引用写入、展示媒体状态、软停用 | 不做自动轨迹截图生成 |

## 已完成边界

- MemoryItem 必须绑定 `activity_id` 或 `race_id`。
- 有 `activity_id` 的 MemoryItem 可回跳 Activity Detail。
- Race-only MemoryItem 不伪造 Activity Detail 跳转。
- 前端只展示轻量文本卡片与 `has_media` 状态。
- `storage_ref` 只在后端用于判断 `has_media`，不进入公开 view model。
- story 编辑采用卡片原位编辑，不使用弹窗。
- 停用采用 `status='inactive'`，不物理删除。

## 明确不做项

- 不做复杂相册上传器。
- 不做批量文件选择器。
- 不删除媒体文件。
- 不做真实缩略图渲染。
- 不做轨迹截图自动生成。
- 不做复杂相册布局或批量管理。
- 不调用 LLM。
- 不生成 AI Snapshot。

## 数据安全确认

Memory Gallery 公开 API 与前端不读取、不返回、不提交：

- `storage_ref`
- 本地绝对路径
- `file_path`
- raw FIT
- points / points_json
- track_json
- SQLite schema

`save_career_memory_media` 会把安全 `media_ref` 写入后端 `storage_ref`，但公开返回值仍只包含 `id/activity_id/race_id/type/title/story/date/thumbnail_url/has_media/detail_link`。

## macOS / Windows 兼容确认

- 未引入平台专属路径拼接。
- 后端拒绝绝对路径、Windows 盘符路径、UNC 路径、反斜杠路径和上级目录片段。
- SQLite migration 与写入保持幂等和参数化。
- 中文标题、故事、错误信息和文档保持 UTF-8。
- pywebview API envelope 保持 `{ok, code, msg, data, traceId}`。
- 前端新增单张照片选择入口，但不读取、不提交、不展示 OS 文件路径；文件选择与复制由 pywebview 后端受控 API 完成。

## Phase 7 进入判断

可以进入 Phase 7。

理由：

- Phase 6 已经提供可被 Career Snapshot 选择性摘要的 MemoryItem 轻量结构。
- Memory Gallery 已明确不向公开 API 或前端暴露本地路径。
- 真实媒体上传与复杂相册不属于 Phase 7 的 AI Snapshot 前置条件。
- Phase 7 必须继续坚持 Snapshot 白名单：只能使用 summary、PB 摘要、major achievements、timeline digest、representative memories，不得读取 `storage_ref` 或本地路径。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_phase6_closure_docs.py
python3 -m pytest tests/test_career_memory_media_api.py tests/test_career_memory_media_frontend.py
python3 -m pytest tests/test_career_memory_story_edit_api.py tests/test_career_memory_story_edit_frontend.py
python3 -m pytest tests/test_career_memory_story_api.py tests/test_career_memory_story_frontend.py
python3 -m pytest tests/test_career_memory_api.py tests/test_career_memory_frontend_render.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- Phase6 文档闭环测试：通过。
- Memory Gallery 相关回归：通过。
- `track.html` 同步逻辑回归：通过。
- JS API 契约 JSON：合法。

## 下一个任务建议

建议进入 `ACS-Phase7-01：Career Snapshot 生成器白名单骨架`。

任务边界建议：

- 只建立 Career Snapshot 的后端白名单结构。
- 只消费 ACS 安全 view model 和聚合摘要。
- 不调用 LLM。
- 不读取 raw FIT、points、track_json、file_path、SQLite schema、本地路径或 `storage_ref`。
- representative memories 只允许使用 `get_career_memory` 等价安全字段。
