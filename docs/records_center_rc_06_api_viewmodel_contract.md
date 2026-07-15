# RC-06 API、ViewModel 与错误状态契约冻结

日期：2026-07-13

## 执行提示词

目标：冻结当前纪录、详情、历史、候选、候选决策和重建状态的前后端数据契约，为前端设计和后端实现提供共同接口。

范围：API 名称、请求/响应 ViewModel、统一 envelope、status、错误码、readonly/high-risk、安全白名单、mock fixtures。

约束：不实现接口，不更新 `docs/js_api_contract.json`，不改前端，不写数据库。

完成定义：前端设计无需假设额外字段；后端实现无需从页面反推数据结构。

## 1. 统一 Envelope

所有 JS Bridge API 继续使用现有 envelope：

```json
{
  "ok": true,
  "code": "OK",
  "msg": "",
  "data": {},
  "traceId": "..."
}
```

错误：

```json
{
  "ok": false,
  "code": "RECORD_NOT_FOUND",
  "msg": "纪录不存在",
  "data": {
    "status": {
      "schema_ready": true,
      "data_ready": false,
      "state": "error",
      "message": "纪录不存在"
    }
  },
  "traceId": "..."
}
```

## 2. 通用 Status

所有 Records API 的 `data.status` 至少包含：

```json
{
  "schema_ready": true,
  "data_ready": true,
  "state": "ready",
  "message": "记录已生成",
  "resolver_version": "records-v1",
  "rebuilding": false,
  "partial": false,
  "candidate_count": 0,
  "last_rebuild_run_id": null,
  "last_rebuild_at": null
}
```

`state` 枚举：

- `loading`
- `ready`
- `empty`
- `partial`
- `rebuilding`
- `error`

前端状态映射：

| state | UI 行为 |
| --- | --- |
| `loading` | 固定尺寸骨架 |
| `ready` | 正常展示 |
| `empty` | 稳定空态 |
| `partial` | 展示可用数据和缺失说明 |
| `rebuilding` | 保留上次结果，显示重建中 |
| `error` | 保留上次可用数据，显示局部错误与重试 |

## 3. 安全白名单

所有 Records API 禁止递归返回：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `advanced_metrics`
- `file_path`
- `storage_ref`
- `path`
- `thumbnail_url`
- `file://`
- `/Users/`
- `\\Users\\`
- SQLite schema / `sqlite_master`

`display_metadata` 只能包含白名单解释字段：

- `source_mode`
- `standard_distance_m`
- `actual_distance_m`
- `distance_error_ratio`
- `elapsed_time_sec`
- `timer_time_sec`
- `time_quality`
- `distance_quality`
- `confidence`
- `confidence_level`
- `reason_codes`
- `previous_record_id`
- `previous_value`
- `improvement_sec`
- `resolver_version`

## 4. API 总表

| API | readonly | high_risk | 说明 |
| --- | --- | --- | --- |
| `get_career_pb(filters)` | true | false | 当前正式纪录列表，兼容现有 API |
| `get_career_pb_detail(payload)` | true | false | 单条纪录详情 |
| `get_career_pb_history(filters)` | true | false | 单项纪录演进 |
| `get_career_pb_candidates(filters)` | true | false | 待确认候选 |
| `decide_career_pb_candidate(payload)` | false | true | 确认/拒绝候选 |
| `rebuild_career_pb_records(payload)` | false | true | 启动或查询重建 |

写接口必须校验 payload、幂等、防重复提交，并写 Record Event。

## 5. `get_career_pb(filters)`

兼容保留并扩展。

请求：

```json
{
  "sport": "running",
  "year": "all",
  "pb_type": "all",
  "source": "all",
  "source_mode": "activity_total"
}
```

返回：

```json
{
  "pb_records": [
    {
      "id": "pb:running_10k:150",
      "activity_id": "150",
      "sport": "running",
      "sport_label": "跑步",
      "pb_type": "running_10k",
      "pb_type_label": "10K",
      "pb_title": "10K PB",
      "value": 3278,
      "value_unit": "seconds",
      "value_display": "54:38",
      "improvement_sec": null,
      "improvement_display": "首次记录",
      "event_date": "2024-06-29",
      "year": 2024,
      "month": 6,
      "display_date": "2024-06-29",
      "confidence": 0.96,
      "confidence_level": "high",
      "confidence_label": "高置信度",
      "source": "resolver",
      "source_label": "规则识别",
      "source_mode": "activity_total",
      "source_mode_label": "整次活动",
      "resolver_version": "records-v1",
      "display_metadata": {
        "standard_distance_m": 10000,
        "actual_distance_m": 10026,
        "distance_error_ratio": 0.0026,
        "time_quality": "reliable_elapsed",
        "reason_codes": ["distance_within_3_percent", "elapsed_time_reliable"]
      },
      "detail_link": {
        "activity_id": "150",
        "source": "career"
      }
    }
  ],
  "summary": {
    "total": 1,
    "active_count": 1,
    "candidate_count": 0,
    "new_records_last_30d": 0,
    "by_pb_type": {"running_10k": 1},
    "by_sport": {"running": 1},
    "by_year": {"2024": 1}
  },
  "filters": {
    "sport": "running",
    "year": null,
    "pb_type": "all",
    "source": "all",
    "source_mode": "activity_total"
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": "记录已生成",
    "resolver_version": "records-v1",
    "rebuilding": false,
    "partial": false,
    "candidate_count": 0
  }
}
```

排序：

```text
Registry priority ASC, event_date DESC, id DESC
```

## 6. `get_career_pb_detail(payload)`

请求：

```json
{
  "record_id": "pb:running_10k:150"
}
```

返回：

```json
{
  "record": {
    "id": "pb:running_10k:150",
    "activity_id": "150",
    "pb_type": "running_10k",
    "pb_title": "10K PB",
    "value": 3278,
    "value_display": "54:38",
    "improvement_sec": null,
    "previous_record_id": null,
    "event_date": "2024-06-29",
    "source_mode": "activity_total",
    "source_mode_label": "整次活动",
    "time_basis_label": "实际经过时间",
    "distance": {
      "actual_m": 10026,
      "standard_m": 10000,
      "error_ratio": 0.0026,
      "error_display": "0.26%"
    },
    "confidence": {
      "score": 0.96,
      "level": "high",
      "label": "高置信度",
      "reason_codes": ["distance_within_3_percent", "elapsed_time_reliable"]
    },
    "activity_summary": {
      "title": "北京市 跑步",
      "sport_label": "跑步",
      "display_date": "2024-06-29"
    },
    "detail_link": {
      "activity_id": "150",
      "source": "career"
    }
  },
  "history_preview": [],
  "status": {"schema_ready": true, "data_ready": true, "state": "ready"}
}
```

## 7. `get_career_pb_history(filters)`

请求：

```json
{
  "pb_type": "running_10k",
  "source_mode": "activity_total",
  "include_invalidated": false
}
```

返回：

```json
{
  "record_key": "running_10k",
  "record_label": "10K",
  "source_mode": "activity_total",
  "current_record_id": "pb:running_10k:150",
  "history": [
    {
      "record_id": "pb:running_10k:150",
      "activity_id": "150",
      "value": 3278,
      "value_display": "54:38",
      "improvement_sec": null,
      "improvement_display": "首次记录",
      "event_date": "2024-06-29",
      "status": "active",
      "detail_link": {"activity_id": "150", "source": "career"}
    }
  ],
  "status": {"schema_ready": true, "data_ready": true, "state": "ready"}
}
```

排序：`event_date ASC, created_at ASC, record_id ASC`。

## 8. `get_career_pb_candidates(filters)`

请求：

```json
{
  "sport": "running",
  "pb_type": "all",
  "confidence_level": "candidate"
}
```

返回：

```json
{
  "candidates": [
    {
      "id": "pb:running_5k:candidate:123",
      "activity_id": "123",
      "pb_type": "running_5k",
      "pb_type_label": "5K",
      "candidate_title": "可能的 5K 纪录",
      "value": 1500,
      "value_unit": "seconds",
      "value_display": "25:00",
      "event_date": "2026-07-01",
      "source_mode": "activity_total",
      "confidence": 0.82,
      "confidence_level": "candidate",
      "reason_codes": ["duration_semantics_unknown"],
      "reason_display": ["计时口径需要确认"],
      "distance": {
        "actual_m": 5000,
        "standard_m": 5000,
        "error_ratio": 0
      },
      "decision": {
        "allowed": true,
        "state": "pending"
      },
      "detail_link": {"activity_id": "123", "source": "career"}
    }
  ],
  "summary": {
    "total": 1,
    "by_pb_type": {"running_5k": 1}
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "candidate_count": 1
  }
}
```

候选不得出现在 `get_career_pb().pb_records` 中。

## 9. `decide_career_pb_candidate(payload)`

请求：

```json
{
  "record_id": "pb:running_5k:candidate:123",
  "decision": "confirm"
}
```

`decision` 只允许：

- `confirm`
- `reject`

返回：

```json
{
  "decision": "confirm",
  "record_id": "pb:running_5k:candidate:123",
  "status": "active",
  "activated_record_id": "pb:running_5k:123",
  "superseded_record_id": null,
  "event_ids": ["record_event:user_confirmed:..."],
  "refresh": {
    "current": true,
    "history": true,
    "candidates": true
  },
  "message": "候选纪录已确认",
  "status_view": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready"
  }
}
```

写接口规则：

- 已处理候选重复提交返回稳定结果或 `RECORD_ALREADY_DECIDED`，不得重复写语义相同事件。
- 非 candidate 状态返回 `INVALID_RECORD_STATE`。
- 非法 decision 返回 `INVALID_DECISION`。

## 10. `rebuild_career_pb_records(payload)`

请求：

```json
{
  "mode": "dry_run",
  "reason": "registry_version_changed"
}
```

`mode`：

- `status`
- `dry_run`
- `apply`

返回：

```json
{
  "run_id": "records-rebuild-20260713-001",
  "mode": "dry_run",
  "resolver_version": "records-v1",
  "state": "completed",
  "summary": {
    "processed": 95,
    "unchanged": 2,
    "added": 0,
    "replaced": 1,
    "removed": 5,
    "candidates": 0,
    "skipped": 0
  },
  "changes": [
    {
      "pb_type": "running_10k",
      "old_record_id": "pb:running_10k:108",
      "new_activity_id": "150",
      "reason_codes": ["distance_rule_changed", "old_record_outside_3_percent"]
    }
  ],
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "rebuilding": false
  }
}
```

`apply` 是高风险写操作，必须：

- 防重入。
- 有 dry-run 计划。
- 事务应用。
- 失败保留旧 active。

## 11. 错误码

| code | 含义 |
| --- | --- |
| `RECORD_NOT_FOUND` | 纪录不存在 |
| `ACTIVITY_NOT_FOUND` | 来源 Activity 不存在 |
| `INVALID_DECISION` | 候选操作非法 |
| `INVALID_RECORD_STATE` | 当前状态不允许该操作 |
| `RECORD_ALREADY_DECIDED` | 候选已处理 |
| `REBUILD_IN_PROGRESS` | 正在重建 |
| `REBUILD_PLAN_REQUIRED` | apply 前缺少 dry-run 计划 |
| `RECORDS_UNAVAILABLE` | 数据暂不可用 |
| `SCHEMA_NOT_READY` | schema 未完成 |
| `VALIDATION_ERROR` | payload 校验失败 |

## 12. Mock Fixtures

RC-07 前端设计使用以下 fixture 集合：

- `records_empty`: 无 Activity 或无匹配纪录。
- `records_current`: 5K、10K、半马 active。
- `records_candidate`: 存在待确认候选。
- `records_rebuilding`: `state=rebuilding` 且有旧 current。
- `records_error`: 局部 API 失败但保留旧数据。
- `records_history_10k_changed`: 10K 因 `±3%` 从活动 `108` 替换为 `150`。

Mock 数据必须只使用本契约字段，不得包含未冻结字段。

## 13. `docs/js_api_contract.json` 计划变更

RC-17/RC-18 实现时同步：

- 更新现有 `get_career_pb` returns/status/source_mode。
- 新增 `get_career_pb_detail`。
- 新增 `get_career_pb_history`。
- 新增 `get_career_pb_candidates`。
- 新增 `decide_career_pb_candidate`，`readonly=false`，`high_risk=true`。
- 新增 `rebuild_career_pb_records`，`readonly=false`，`high_risk=true`。
- 所有描述加入禁止字段边界。
