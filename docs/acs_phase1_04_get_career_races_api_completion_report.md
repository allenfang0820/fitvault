# ACS-Phase1-04 get_career_races API 完成报告

## 任务范围

本任务实现 ACS 赛事档案只读 API，用于读取 Race Resolver 已生成的正式赛事记录。

已完成：

- `career_backend.get_career_races(filters=None, conn=None)`
- `Api.get_career_races(filters=None)`
- `docs/js_api_contract.json` 方法登记
- `tests/test_career_races_api.py`

未实现：

- 前端 UI
- 重新运行或修改 Race Resolver
- PB / Achievement / Memory
- AI Snapshot / AI 洞察
- Timeline 节点渲染

## API 返回结构

`Api.get_career_races(filters)` 返回统一 envelope：

```json
{
  "ok": true,
  "code": 0,
  "msg": "ok",
  "data": {
    "races": [
      {
        "id": "race:123",
        "activity_id": "123",
        "name": "2026 成都半程马拉松",
        "event_type": "half_marathon",
        "sport": "running",
        "event_date": "2026-05-19",
        "city": "成都",
        "confidence": 1.0,
        "source": "user",
        "confidence_level": "high",
        "display_metadata": {},
        "detail_link": {
          "activity_id": "123",
          "source": "career"
        }
      }
    ],
    "summary": {
      "total": 1,
      "by_event_type": {"half_marathon": 1},
      "by_sport": {"running": 1},
      "by_year": {"2026": 1}
    },
    "filters": {
      "sport": "all",
      "year": null,
      "event_type": "all",
      "source": "all"
    },
    "status": {
      "schema_ready": true,
      "data_ready": true,
      "message": "赛事档案已生成"
    }
  },
  "traceId": "..."
}
```

## filters 规则

支持：

- `sport`
- `year`
- `event_type`
- `source`

默认：

```json
{
  "sport": "all",
  "year": null,
  "event_type": "all",
  "source": "all"
}
```

排序：

```sql
ORDER BY event_date DESC, id DESC
```

仅返回：

```sql
status = 'active'
```

## forbidden fields 验证

API 不读取或返回以下字段：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`
- `sqlite_schema`
- `schema`

测试 `test_main_api_get_career_races_returns_unified_envelope` 与响应递归 forbidden key 检查已覆盖。

## macOS / Windows 兼容性

- 默认连接仍使用 `profile_backend.DB_PATH`。
- 测试通过 `tempfile.TemporaryDirectory()` 和 `Path` 创建临时 SQLite 文件。
- 不硬编码系统路径。
- 中文城市与赛事名通过 JSON `ensure_ascii=False` 保留。
- 不向前端或 AI 暴露本地绝对路径。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_races_api.py
# 6 passed

python3 -m pytest tests/test_career_race_resolver.py
# 9 passed

python3 -m pytest tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
# 12 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed

python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
# 14 passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

原计划下一个任务建议：

`ACS-Phase1-05：赛事档案与 Career Overview / Timeline 的轻量联动`

建议边界：

- `get_career_overview()` 返回 `latest_race`。
- `get_career_timeline()` 开始读取正式赛事并生成基础 years/months 节点。
- 仍不接前端 UI。
- 不做 PB / 成就 / 记忆。
