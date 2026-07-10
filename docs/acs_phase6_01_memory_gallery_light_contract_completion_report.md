# ACS-Phase6-01 Memory Gallery 轻量版数据契约与空状态策略完成报告

## 任务范围

本任务进入 ACS Phase 6，建立 Memory Gallery 轻量版工程基础。

已完成：

- 新增 `get_career_memory` 后端只读 API
- 扩展 `career_memory_items` 轻量字段迁移
- 新增 pywebview API 暴露
- 更新 `docs/js_api_contract.json`
- 前端接入运动生涯右侧 Memory Gallery 轻量区
- 新增 Memory loading / empty / error / list 渲染
- 有 `activity_id` 的 MemoryItem 复用 Activity Detail 回跳
- 新增后端与前端静态契约测试

未实现：

- 图片上传 / 文件复制 / 文件删除
- 复杂相册管理器
- AI 生成故事
- AI Snapshot
- Memory Timeline 节点
- 后端 POST 新增 / 绑定记忆项

## 修改文件

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `tests/test_career_memory_api.py`
- `tests/test_career_memory_frontend_render.py`
- `docs/acs_phase6_01_memory_gallery_light_contract_completion_report.md`

## Memory API 返回结构

新增 pywebview API：

```python
get_career_memory(filters=None)
```

后端核心函数：

```python
career_backend.get_career_memory(filters=None, conn=None)
```

返回数据：

```json
{
  "items": [
    {
      "id": "memory:1",
      "activity_id": "1",
      "race_id": "",
      "type": "story",
      "title": "第一次半马记忆",
      "story": "第一次认真记录比赛",
      "date": "2026-05-19",
      "thumbnail_url": "",
      "has_media": false,
      "detail_link": {
        "activity_id": "1",
        "source": "career"
      }
    }
  ],
  "summary": {
    "total": 1,
    "photo_count": 0,
    "story_count": 1,
    "track_count": 0
  },
  "filters": {
    "type": "all"
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "生涯记忆已生成"
  }
}
```

支持轻量筛选：

- `type=all`
- `type=photo`
- `type=story`
- `type=track`

未知类型稳定回退为 `all`。

## Schema 兼容

`career_memory_items` 保留既有字段：

- `id`
- `race_id`
- `activity_id`
- `memory_type`
- `storage_ref`
- `story_text`
- `metadata_json`
- `created_at`
- `updated_at`

本任务补充轻量只读所需列：

- `title`
- `event_date`
- `status`

新增列使用幂等迁移：

```python
_ensure_career_light_memory_columns()
```

旧库升级时不会破坏已有 MemoryItem。

## 空状态策略

表不存在、空表、无 active 记忆项时均返回稳定空结构：

```json
{
  "items": [],
  "summary": {
    "total": 0,
    "photo_count": 0,
    "story_count": 0,
    "track_count": 0
  },
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "暂无生涯记忆"
  }
}
```

前端空状态只展示简洁文案，不渲染空图片框或照片占位墙。

## 图片缺失策略

本任务不返回真实媒体地址。

即使后端记录中存在 `storage_ref`：

- `thumbnail_url` 仍返回空字符串
- `has_media` 可标记是否存在应用受控媒体引用
- 前端不渲染 `<img>`
- 前端以文本卡片展示故事 / 轨迹记忆

这样可以先完成 Memory Gallery 的结构闭环，同时避免把本地文件位置暴露给前端或 AI。

## Activity Detail 回跳规则

有 `activity_id` 的 MemoryItem：

- 渲染为可点击卡片
- 写入 `data-activity-id`
- 写入 `data-career-source="career"`
- 复用 `openCareerActivityDetailFromElement`
- 支持 Enter / Space 键盘回跳

只有 `race_id`、没有 `activity_id` 的 MemoryItem：

- 可进入返回列表
- 不伪造 `activity_id`
- 前端渲染为普通不可点击卡片

## 路径安全策略

后端不返回：

- `storage_ref`
- `path`
- `file_path`
- 本地绝对路径
- raw FIT
- `points`
- `points_json`
- `track_json`
- SQLite schema

`storage_ref` 仅在后端用于计算：

```json
{"has_media": true}
```

前端不读取、不展示、不拼接任何本地媒体路径。

## 数据边界确认

本任务不计算或推断：

- 是否赛事
- 是否 PB
- 是否成就
- 是否应该生成记忆
- 赛事置信度
- PB / Achievement 真值
- AI 叙事事实

Memory Gallery 只消费 `career_memory_items` 的 active 派生记录，并组织为轻量 view model。

## macOS / Windows 兼容性

- SQLite migration 幂等
- 未新增硬编码平台路径
- 未依赖路径分隔符
- 未返回本地绝对路径
- 未引入新前端依赖或构建链路
- 中文文案保持 UTF-8
- 前端使用普通 DOM / button / div，兼容 pywebview
- 窄窗口下沿用 Career 页面单列布局

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_api.py
# 5 passed

python3 -m pytest tests/test_career_memory_frontend_render.py
# 7 passed

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

`ACS-Phase6-02：MemoryItem 手动故事绑定 API 与前端入口`

建议边界：

- 只支持文本故事型 MemoryItem
- 必须绑定 `activity_id` 或 `race_id`
- 不做图片上传
- 不做文件复制 / 删除
- 不调用 LLM
- 不生成 AI Snapshot
- 写入后仍不返回本地绝对路径
