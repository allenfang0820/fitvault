# ACS-Phase6-03 Memory Story 编辑与停用能力完成报告

## 任务范围

- 为 `memory_type="story"` 的 MemoryItem 增加编辑能力。
- 为 MemoryItem 增加停用能力，采用 `status='inactive'`，不物理删除。
- 前端采用卡片原位编辑，不使用弹窗。
- 不涉及图片上传、媒体复制、AI Snapshot、Timeline 语义变更。

## 修改文件

- `career_backend.py`
  - 新增 `_fetch_memory_row`
  - 新增 `update_career_memory_story(payload, conn=None)`
  - 新增 `deactivate_career_memory_item(payload, conn=None)`
- `main.py`
  - 新增 pywebview API 包装：
    - `update_career_memory_story`
    - `deactivate_career_memory_item`
- `track.html`
  - Memory story 卡片新增“编辑 / 停用”操作。
  - 编辑态在卡片内部展示标题输入框与故事文本框。
  - 保存与停用成功后刷新 `loadCareerMemory()`。
- `docs/js_api_contract.json`
  - 新增两个写接口契约。
- `tests/test_career_memory_story_edit_api.py`
  - 覆盖编辑与停用后端契约。
- `tests/test_career_memory_story_edit_frontend.py`
  - 覆盖前端原位编辑、白名单 payload 和移动端布局契约。

## API 契约

### update_career_memory_story

输入白名单：

```json
{
  "id": "memory id",
  "title": "记忆标题",
  "story": "故事文本"
}
```

规则：

- `id` 必填。
- `title` 非空，最多 80 字符。
- `story` 非空，最多 500 字符。
- 只允许编辑 `status='active'` 且 `memory_type='story'` 的记录。
- 只更新 `title`、`story_text`、`metadata_json`、`updated_at`。
- 保持 `activity_id`、`race_id`、`memory_type`、`storage_ref`、`event_date`、`created_at` 不变。

### deactivate_career_memory_item

输入白名单：

```json
{
  "id": "memory id"
}
```

规则：

- `id` 必填。
- 记录不存在时报校验错误。
- 只更新 `status='inactive'` 与 `updated_at`。
- 不删除数据库记录，不删除或改写媒体引用。
- `get_career_memory` 仍只返回 active 记录，因此停用后列表不再显示该 MemoryItem。

## 前端行为

- Story 记忆卡片右侧显示“编辑 / 停用”操作。
- 非 story 类型不显示编辑/停用入口。
- 点击“编辑”后在当前卡片内进入编辑态。
- 保存 payload 只包含 `id/title/story`。
- 停用 payload 只包含 `id`。
- 编辑态禁用活动详情跳转，避免输入时误触。
- 操作按钮使用 `event.stopPropagation()`，不会触发卡片详情跳转。
- 移动端 Memory 操作区允许换行，避免挤压标题。

## 数据边界与兼容性

- 返回值仍使用白名单 view model，不返回 `storage_ref`、本地绝对路径、FIT 原始记录、points、track_json 或 SQLite schema。
- 前端不读取、不提交本地路径、原始轨迹点、SQLite schema。
- 未引入 OS 专属路径逻辑；macOS / Windows 路径兼容原则保持在后端受控目录边界内。
- 本任务不调用 LLM，不生成 AI Snapshot。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_story_edit_api.py tests/test_career_memory_story_edit_frontend.py
python3 -m pytest tests/test_career_memory_story_edit_api.py tests/test_career_memory_story_edit_frontend.py tests/test_career_memory_story_api.py tests/test_career_memory_story_frontend.py tests/test_career_memory_api.py tests/test_career_memory_frontend_render.py tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py tests/test_track_html_sync_logic.py tests/test_career_backend_schema.py tests/test_career_overview_api_closure.py
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- 新增测试：16 passed。
- ACS 相邻回归：128 passed。
- Python 编译：通过。
- API 契约 JSON：合法。

## 下一任务建议

建议进入 `ACS-Phase6-04：Memory 媒体引用轻量接入`。

目标是继续在 Phase 6 范围内补齐 Memory Gallery 的图片/轨迹截图型 MemoryItem，但仍坚持轻量策略：只接入应用受控目录内的媒体引用与安全 view model，不做复杂相册、不暴露本地路径、不把媒体路径或原始活动数据交给 AI。
