# ACS-Phase6-04 Memory 媒体引用轻量接入完成报告

## 任务范围

本任务在 Phase6 Memory Gallery 轻量版基础上，补齐 `photo` / `track` 型 MemoryItem 的安全媒体引用写入能力。

已完成：

- 新增后端 `save_career_memory_media`
- 新增 pywebview API 包装
- 新增 JS API 契约
- 新增媒体引用安全校验
- 新增 photo / track 后端契约测试
- 新增 Memory 媒体前端边界测试

未实现：

- 真实上传器
- 文件选择器
- 文件复制 / 删除
- 复杂相册布局
- 真实缩略图渲染
- AI Snapshot 或 LLM 调用

## 修改文件

- `career_backend.py`
  - 新增 `_normalize_memory_media_ref`
  - 新增 `save_career_memory_media(payload, conn=None)`
- `main.py`
  - 新增 `save_career_memory_media(self, payload=None)`
- `docs/js_api_contract.json`
  - 新增 `save_career_memory_media` 契约
- `tests/test_career_memory_media_api.py`
  - 新增后端媒体引用 API 测试
- `tests/test_career_memory_media_frontend.py`
  - 新增前端媒体展示边界测试

## 新 API

pywebview API：

```python
save_career_memory_media(payload)
```

后端函数：

```python
career_backend.save_career_memory_media(payload, conn=None)
```

输入白名单：

```json
{
  "activity_id": "1",
  "race_id": "",
  "memory_type": "photo",
  "title": "冲线照片",
  "media_ref": "memory/photo/finish.jpg"
}
```

`memory_type` 仅支持：

- `photo`
- `track`

返回结构仍使用安全 MemoryItem view model：

```json
{
  "item": {
    "id": "memory:photo:activity:1:...",
    "activity_id": "1",
    "race_id": "",
    "type": "photo",
    "title": "冲线照片",
    "story": "",
    "date": "2026-05-19",
    "thumbnail_url": "",
    "has_media": true,
    "detail_link": {
      "activity_id": "1",
      "source": "career"
    }
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "记忆媒体已保存"
  }
}
```

## 校验规则

- `activity_id` 和 `race_id` 至少填写一个。
- 若绑定 `activity_id`，沿用活动存在性与 deleted 校验。
- `memory_type` 必须为 `photo` 或 `track`。
- `title` trim 后不能为空。
- `title` 最长 80 字符。
- `media_ref` trim 后不能为空。
- 同一绑定目标、同一类型、同一 `media_ref` 重复保存会 upsert 同一条记录。

## media_ref 安全策略

允许：

- `memory/photo/example.jpg`
- `memory/track/example.png`
- `asset:memory:photo:xxx`
- `asset:memory:track:xxx`

拒绝：

- 绝对路径
- 用户目录路径
- 临时目录路径
- Windows 盘符路径
- UNC 网络路径
- 反斜杠路径
- 上级目录片段
- `file:` URL
- 非 `memory/` 或 `asset:memory:` 开头的引用

`media_ref` 仅写入后端 `storage_ref`。公开 API 不返回 `storage_ref`。

## 前端展示边界

本任务未新增真实上传 UI。

现有 Memory Gallery 展示策略保持：

- `photo` 类型显示“照片”标签。
- `track` 类型显示“轨迹”标签。
- `has_media=true` 时只显示“已绑定媒体”。
- 不渲染 `<img>`。
- 不读取或展示真实媒体引用。
- 不提交媒体引用到 AI。

## 数据边界确认

本任务不读取、不返回、不提交：

- raw FIT
- points / points_json
- track_json
- file_path
- SQLite schema
- 本地绝对路径

本任务不调用 LLM，不生成 AI Snapshot，不写入 AI 上下文。

## macOS / Windows 兼容性

- 不硬编码 `/Users/...` 或 Windows 盘符路径。
- 后端拒绝平台绝对路径和反斜杠路径。
- SQLite 写入使用参数化 SQL。
- 中文标题与中文错误信息保持 UTF-8。
- pywebview API envelope 保持 `{ok, code, msg, data, traceId}`。
- 前端未新增 OS 相关文件选择或路径处理逻辑。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_media_api.py tests/test_career_memory_media_frontend.py
python3 -m pytest tests/test_career_memory_media_api.py tests/test_career_memory_media_frontend.py tests/test_career_memory_story_edit_api.py tests/test_career_memory_story_edit_frontend.py tests/test_career_memory_story_api.py tests/test_career_memory_story_frontend.py tests/test_career_memory_api.py tests/test_career_memory_frontend_render.py tests/test_career_timeline_frontend_large_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_overview_frontend_render.py tests/test_career_overview_activity_detail_link.py tests/test_career_overview_frontend_integration.py tests/test_track_html_sync_logic.py tests/test_career_backend_schema.py tests/test_career_overview_api_closure.py
python3 -m py_compile career_backend.py main.py profile_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
```

结果：

- 新增测试：14 passed。
- ACS 相邻回归：142 passed。
- Python 编译：通过。
- JS API 契约 JSON：合法。

说明：当前 macOS Python 环境仍有 urllib3 / LibreSSL warning，不影响测试结果。

## 下一任务建议

建议进入 `ACS-Phase6-05：Memory Gallery Phase6 闭环验收与任务清单回填`。

目标：

- 对 Phase6-01 到 Phase6-04 的 Memory Gallery 能力做一次闭环审计。
- 在 `docs/脉图运动生涯系统（ACS）开发任务清单.md` 中回填已完成项。
- 明确 Phase6 尚未做的真实上传器/复杂相册属于后续增强，不阻塞进入 Phase7。
- 为 `ACS-Phase7-01：Career Snapshot 生成器白名单骨架` 做入口准备。
