# ACS-Phase6-02 MemoryItem 手动故事绑定完成报告

## 任务范围

本任务在 Phase6-01 Memory Gallery 轻量只读能力基础上，新增 story 型 MemoryItem 的最小手动写入能力。

已完成：

- 新增 `save_career_memory_story` 后端保存函数
- 新增 pywebview API 暴露
- 更新 `docs/js_api_contract.json`
- 在 Memory Gallery 区域新增 inline “添加故事”表单
- 保存成功后刷新 `get_career_memory`
- 新增后端与前端契约测试

未实现：

- 图片上传 / 文件选择 / 文件复制 / 文件删除
- 轨迹截图生成
- AI 生成故事
- AI Snapshot
- Memory Timeline 节点
- 复杂相册管理器

## 修改文件

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_memory_story_api.py`
- `tests/test_career_memory_story_frontend.py`
- `docs/acs_phase6_02_memory_story_binding_completion_report.md`

## 新增 API

pywebview API：

```python
save_career_memory_story(payload)
```

后端函数：

```python
career_backend.save_career_memory_story(payload, conn=None)
```

输入白名单：

```json
{
  "activity_id": "1",
  "race_id": "",
  "title": "第一次半马",
  "story": "那天最后 3 公里很难，但我撑住了。"
}
```

返回结构：

```json
{
  "item": {
    "id": "memory:story:activity:1:...",
    "activity_id": "1",
    "race_id": "",
    "type": "story",
    "title": "第一次半马",
    "story": "那天最后 3 公里很难，但我撑住了。",
    "date": "2026-05-19",
    "thumbnail_url": "",
    "has_media": false,
    "detail_link": {
      "activity_id": "1",
      "source": "career"
    }
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "记忆故事已保存"
  }
}
```

`main.py` 包装为统一 envelope：

```json
{ "ok": true, "code": 0, "msg": "ok", "data": {}, "traceId": "..." }
```

参数错误返回 `1001`。

## 参数校验规则

后端校验：

- `activity_id` 和 `race_id` 至少填写一个
- `title` trim 后不能为空
- `story` trim 后不能为空
- `title` 最长 80 字符
- `story` 最长 500 字符
- 若 `activities` 表存在，`activity_id` 必须存在
- 若 `activities.deleted_at` 存在且非空，拒绝绑定已删除活动

前端也做轻量校验：

- 空绑定目标不调用后端
- 空标题不调用后端
- 空故事不调用后端
- payload 只包含 `activity_id`、`race_id`、`title`、`story`

## 绑定规则

优先绑定 Activity：

- 有 `activity_id` 时，后端校验 Activity 存在且未删除
- `event_date` 优先取 Activity 的 `start_time` / `start_time_utc`
- 成功后 `detail_link = {activity_id, source: "career"}`

Race-only 绑定：

- 允许只有 `race_id`
- 不伪造 `activity_id`
- 返回 `detail_link.activity_id = ""`
- 前端展示为普通不可点击 MemoryItem

## 写入规则

只写入 story 型 MemoryItem：

- `memory_type = "story"`
- `storage_ref = ""`
- `story_text = story`
- `title = title`
- `event_date`
- `status = "active"`
- `metadata_json.source = "user"`

id 采用稳定策略：

```text
memory:story:{activity|race}:{target}:{sha1(target|title|story)[0:12]}
```

同一个绑定目标、同标题、同故事重复保存会 upsert 同一条记录，不会无限重复创建。

## 前端入口

Memory Gallery 区域新增：

- `添加故事` 按钮
- inline 表单 `career-memory-story-form`
- 活动 ID 输入框
- 赛事 ID 输入框
- 记忆标题输入框
- 故事 textarea
- 保存 / 取消按钮
- 错误文案区域

交互：

- 点击“添加故事”原位展开表单
- 不使用 modal / dialog
- 保存成功后清空并收起表单
- 调用 `loadCareerMemory()` 刷新列表
- 保存失败时在表单内显示简洁错误

## 路径安全策略

本任务不接收、不写入、不返回：

- `path`
- `file_path`
- `storage_ref` 本地路径
- 本地绝对路径
- raw FIT
- `points`
- `points_json`
- `track_json`
- SQLite schema

保存 story 时强制：

```python
storage_ref = ""
```

前端没有路径输入框，也不提交路径字段。

## 数据边界确认

本任务不计算或推断：

- 是否赛事
- 是否 PB
- 是否成就
- 是否应该自动生成记忆
- 赛事置信度
- PB / Achievement 真值
- AI 叙事事实

用户输入的 story 只是绑定到 Activity / Race 的记忆文本，不进入 AI Snapshot，不调用 LLM。

## macOS / Windows 兼容性

- 未新增硬编码平台路径
- 未依赖路径分隔符
- SQLite 写入使用参数化 SQL
- 中文标题 / 故事保持 UTF-8
- 表单为普通 DOM input / textarea / button
- 窄窗口下 story 表单单列展示，避免输入框重叠
- pywebview API envelope 契约保持不变

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_story_api.py
# 7 passed

python3 -m pytest tests/test_career_memory_story_frontend.py
# 7 passed

python3 -m pytest tests/test_career_memory_api.py tests/test_career_memory_frontend_render.py
# 12 passed

python3 -m pytest tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py
# 31 passed

python3 -m pytest tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py
# 20 passed

python3 -m pytest tests/test_track_html_sync_logic.py
# 24 passed

python3 -m pytest tests/test_career_backend_schema.py tests/test_career_overview_api_closure.py
# 11 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：`pytest` 期间存在当前 macOS Python 环境的 urllib3 / LibreSSL warning，不影响测试结果。

## 下一任务建议

建议进入：

`ACS-Phase6-03：Memory Story 编辑与停用能力`

建议边界：

- 支持编辑已有 story MemoryItem 的标题 / 故事
- 支持停用 MemoryItem，使用 `status != active`，不物理删除
- 不做图片上传
- 不做文件删除
- 不调用 LLM
- 不生成 AI Snapshot
- 继续保持路径不外露
