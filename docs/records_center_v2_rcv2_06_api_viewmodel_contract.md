# RCV2-06 通用 Records API、Catalog 与 ViewModel 契约

完成时间：2026-07-14

本文冻结 Records Center V2 的通用 API、Catalog、Records、Detail、History、Curve、Candidate ViewModel、错误状态和 V1 PB API 兼容关系。后续 `RCV2-14` 必须按本文实现 API 与包装器；`RCV2-07` 前端设计必须只依赖本文字段。

## 1. 统一 Envelope

所有 JS Bridge API 继续使用现有 envelope：

```json
{
  "ok": true,
  "code": "OK",
  "msg": "",
  "data": {},
  "traceId": "trace-id"
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
  "traceId": "trace-id"
}
```

## 2. 通用 Status

所有 V2 Records API 的 `data.status` 至少包含：

```json
{
  "schema_ready": true,
  "data_ready": true,
  "state": "ready",
  "message": "记录已生成",
  "records_version": "records-v2",
  "resolver_version": "records-v2",
  "catalog_version": "records-center-v2-catalog",
  "rebuilding": false,
  "partial": false,
  "validation_required": false,
  "candidate_count": 0,
  "last_rebuild_run_id": null,
  "last_rebuild_at": null,
  "warnings": []
}
```

`state` 枚举：

- `loading`
- `ready`
- `empty`
- `partial`
- `validation_required`
- `candidate_only`
- `rebuilding`
- `error`

前端行为：

| state | UI 行为 |
| --- | --- |
| `loading` | 固定尺寸骨架，不跳版。 |
| `ready` | 正常展示。 |
| `empty` | 稳定空态，不伪造纪录。 |
| `partial` | 展示可用数据和缺失说明。 |
| `validation_required` | 灰态展示规则和缺失事实，不展示正式纪录。 |
| `candidate_only` | 展示候选/待验收状态，不庆祝，不触发成就。 |
| `rebuilding` | 保留上次结果，显示重建中。 |
| `error` | 保留上次可用数据，局部错误与重试。 |

## 3. 安全白名单

所有 V2 Records API 禁止递归返回：

```text
points
points_json
track_json
raw_records
fit_records
power_points
power_stream
cadence_points
elevation_points
gps_points
file_path
storage_ref
path
thumbnail_url
file://
/Users/
\\Users\\
sqlite_master
CREATE TABLE
device_serial
serial_number
email
token
api_key
password
weight_history
```

允许返回：

- 安全展示值。
- 聚合摘要。
- reason codes 和文案 key。
- 裁剪后的活动内范围偏移。
- `scope_hash`、`scope_key` 和后端生成的 `scope_label`。
- 曲线降采样后的展示点，但不得返回原始采样。

## 4. API 总表

| API | readonly | high_risk | 说明 |
| --- | --- | --- | --- |
| `get_career_record_catalog(filters)` | true | false | V2 Catalog、运动页签、分组、可用性。 |
| `get_career_records(filters)` | true | false | V2 当前纪录列表。 |
| `get_career_record_detail(payload)` | true | false | V2 单条纪录详情。 |
| `get_career_record_history(filters)` | true | false | V2 单项历史演进与 summary。 |
| `get_career_record_curve(payload)` | true | false | V2 安全曲线 ViewModel。 |
| `get_career_record_candidates(filters)` | true | false | V2 候选列表。 |
| `decide_career_record_candidate(payload)` | false | true | V2 候选确认/拒绝。 |
| `rebuild_career_records(payload)` | false | true | V2 dry-run/rebuild。 |
| `get_career_record_rebuild_status(payload)` | true | false | V2 重建状态查询。 |
| `get_career_pb*` | true/部分 high-risk | 兼容 | V1 PB API 包装到 V2。 |

## 5. Catalog API

### 5.1 `get_career_record_catalog(filters)`

请求：

```json
{
  "sport": "all",
  "include_unavailable": true,
  "include_analysis": true
}
```

返回：

```json
{
  "sports": [
    {
      "sport": "cycling",
      "sport_label": "骑行",
      "icon": "bike",
      "availability_state": "available",
      "state_label": "可用",
      "record_count": 10,
      "active_count": 3,
      "candidate_count": 1,
      "groups": [
        {
          "group_key": "cycling_power",
          "group_label": "功率纪录",
          "family": "power_duration_pb",
          "records": [
            {
              "record_key": "cycling_power_20m",
              "display_name": "20 分钟最大功率",
              "family": "power_duration_pb",
              "metric": "power_w",
              "canonical_unit": "watts",
              "comparison": "higher_is_better",
              "axis_direction": "higher",
              "source_mode": "best_effort_duration",
              "scope_dimensions": ["sport_scope", "indoor_scope", "power_metric_scope"],
              "availability_state": "available",
              "availability_reason": null,
              "availability_message_key": "record_available",
              "priority": 120,
              "supports_curve": true,
              "supports_history": true,
              "supports_candidates": true
            }
          ]
        }
      ]
    }
  ],
  "filters": {
    "sport": "all",
    "include_unavailable": true,
    "include_analysis": true
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": ""
  }
}
```

Catalog 行为：

- 前端运动页签、左侧分组、灰态说明全部由 Catalog 驱动。
- `availability_state=available`：可展示正式纪录。
- `candidate_only`：可展示候选/待验收，但不庆祝。
- `validation_required`：展示规则、缺失事实和“待验证”空态，不展示正式纪录。
- `unavailable`：默认隐藏；`include_unavailable=true` 可用于设计/调试灰态。
- `analysis_only/model_only`：只进入分析区，不出现在当前纪录主列表。

## 6. Records API

### 6.1 `get_career_records(filters)`

请求：

```json
{
  "sport": "cycling",
  "record_key": "all",
  "family": "all",
  "scope_hash": "all",
  "status": "active",
  "year": "all"
}
```

返回：

```json
{
  "records": [
    {
      "id": "record:cycling_power_20m:scope:v2:sha256:abc",
      "activity_id": "123",
      "record_key": "cycling_power_20m",
      "pb_type": "cycling_power_20m",
      "display_name": "20 分钟最大功率",
      "sport": "cycling",
      "sport_label": "骑行",
      "family": "power_duration_pb",
      "metric": {
        "name": "power_w",
        "value": 248,
        "unit": "watts",
        "display": "248 W"
      },
      "comparison": "higher_is_better",
      "axis_direction": "higher",
      "improvement": {
        "value": 12,
        "unit": "watts",
        "display": "+12 W",
        "direction": "improved"
      },
      "event_date": "2026-07-01",
      "display_date": "2026-07-01",
      "source_mode": "best_effort_duration",
      "source_mode_label": "最佳努力 20 分钟",
      "scope": {
        "scope_hash": "scope:v2:sha256:abc",
        "scope_key": "default",
        "labels": ["户外", "原始功率"],
        "dimensions": {
          "sport_scope": "cycling_regular",
          "indoor_scope": "outdoor",
          "power_metric_scope": "raw_power_w"
        }
      },
      "range": {
        "type": "time_window",
        "start_offset_sec": 1220,
        "end_offset_sec": 2420,
        "display": "第 20:20 - 40:20"
      },
      "quality": {
        "confidence": 0.94,
        "confidence_band": "high",
        "reason_codes": ["power_stream_present", "range_attached"],
        "message_key": "record_quality_high"
      },
      "status": "active",
      "catalog_state": "available",
      "resolver_version": "records-v2",
      "rule_version": "records-v2",
      "detail_link": {
        "activity_id": "123",
        "source": "career",
        "record_id": "record:cycling_power_20m:scope:v2:sha256:abc"
      }
    }
  ],
  "summary": {
    "total": 1,
    "active_count": 1,
    "candidate_count": 0,
    "validation_required_count": 0,
    "by_sport": {"cycling": 1},
    "by_family": {"power_duration_pb": 1},
    "by_record_key": {"cycling_power_20m": 1}
  },
  "filters": {
    "sport": "cycling",
    "record_key": "all",
    "family": "all",
    "scope_hash": "all",
    "status": "active",
    "year": null
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": ""
  }
}
```

前端禁止：

- 从 `metric.value` 和前一条记录自行计算 improvement。
- 从 `comparison` 之外推断轴方向；必须使用 `axis_direction`。
- 自行拼 scope label。
- 把 `candidate` 渲染成 current record。

## 7. Detail API

### 7.1 `get_career_record_detail(payload)`

请求：

```json
{
  "record_id": "record:cycling_power_20m:scope:v2:sha256:abc",
  "record_key": "cycling_power_20m",
  "scope_hash": "scope:v2:sha256:abc"
}
```

返回：

```json
{
  "record": {
    "id": "record:cycling_power_20m:scope:v2:sha256:abc",
    "activity_id": "123",
    "record_key": "cycling_power_20m",
    "display_name": "20 分钟最大功率",
    "sport": "cycling",
    "sport_label": "骑行",
    "family": "power_duration_pb",
    "metric": {"name": "power_w", "value": 248, "unit": "watts", "display": "248 W"},
    "comparison": "higher_is_better",
    "axis_direction": "higher",
    "source_mode": "best_effort_duration",
    "scope": {"scope_hash": "scope:v2:sha256:abc", "labels": ["户外", "原始功率"], "dimensions": {}},
    "range": {"type": "time_window", "start_offset_sec": 1220, "end_offset_sec": 2420, "display": "第 20:20 - 40:20"},
    "quality": {"confidence": 0.94, "confidence_band": "high", "reason_codes": [], "message_key": "record_quality_high"},
    "detail_link": {"activity_id": "123", "source": "career", "record_id": "record:cycling_power_20m:scope:v2:sha256:abc"}
  },
  "activity_summary": {
    "activity_id": "123",
    "title": "午后骑行",
    "sport": "cycling",
    "event_date": "2026-07-01",
    "distance_display": "58.2 km",
    "duration_display": "2:14:20"
  },
  "related": {
    "history_api": "get_career_record_history",
    "curve_api": "get_career_record_curve",
    "activity_link": {"activity_id": "123", "source": "career"}
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": ""
  }
}
```

`activity_summary` 只能使用 Activity 安全摘要，不包含路线、设备、raw FIT 或轨迹。

## 8. History API

### 8.1 `get_career_record_history(filters)`

请求：

```json
{
  "record_key": "cycling_power_20m",
  "scope_hash": "scope:v2:sha256:abc",
  "include_invalidated": true
}
```

返回：

```json
{
  "records": [
    {
      "id": "record-history-1",
      "activity_id": "101",
      "event_date": "2025-05-10",
      "status": "superseded",
      "metric": {"name": "power_w", "value": 236, "unit": "watts", "display": "236 W"},
      "improvement": {"value": null, "unit": "watts", "display": "首次记录", "direction": "initial"},
      "detail_link": {"activity_id": "101", "source": "career", "record_id": "record-history-1"}
    },
    {
      "id": "record-history-2",
      "activity_id": "123",
      "event_date": "2026-07-01",
      "status": "active",
      "metric": {"name": "power_w", "value": 248, "unit": "watts", "display": "248 W"},
      "improvement": {"value": 12, "unit": "watts", "display": "+12 W", "direction": "improved"},
      "detail_link": {"activity_id": "123", "source": "career", "record_id": "record-history-2"}
    }
  ],
  "history_summary": {
    "record_key": "cycling_power_20m",
    "scope_hash": "scope:v2:sha256:abc",
    "axis_direction": "higher",
    "comparison": "higher_is_better",
    "first_value": {"value": 236, "unit": "watts", "display": "236 W"},
    "current_value": {"value": 248, "unit": "watts", "display": "248 W"},
    "total_improvement": {"value": 12, "unit": "watts", "display": "+12 W", "direction": "improved"},
    "record_count": 2,
    "invalidated_count": 0,
    "last_record_at": "2026-07-01"
  },
  "chart": {
    "x_axis": {"type": "time", "label": "日期"},
    "y_axis": {"unit": "watts", "direction": "higher"},
    "points": [
      {"x": "2025-05-10", "y": 236, "record_id": "record-history-1", "status": "superseded"},
      {"x": "2026-07-01", "y": 248, "record_id": "record-history-2", "status": "active"}
    ]
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": ""
  }
}
```

History 契约：

- `history_summary.total_improvement` 由后端计算。
- `chart.points` 是安全绘图点，不是原始运动点。
- 前端不得从 records 重新累计提升，不得自行决定 y 轴上下方向。
- `invalidated` 可以弱展示，但不得作为 current。

## 9. Curve API

### 9.1 `get_career_record_curve(payload)`

请求：

```json
{
  "curve_type": "cycling_power_duration_curve",
  "record_key": "cycling_power_20m",
  "activity_id": "123",
  "scope_hash": "scope:v2:sha256:abc"
}
```

返回：

```json
{
  "curve": {
    "curve_type": "cycling_power_duration_curve",
    "scope_hash": "scope:v2:sha256:abc",
    "algorithm_version": "records-v2-curve-1",
    "input_fingerprint": "curve-input:v2:sha256:abc",
    "x_axis": {"type": "duration_sec", "unit": "seconds", "scale": "log"},
    "y_axis": {"type": "power_w", "unit": "watts", "direction": "higher"},
    "points": [
      {"x": 5, "y": 612, "label": "5s"},
      {"x": 60, "y": 365, "label": "1m"},
      {"x": 1200, "y": 248, "label": "20m"}
    ],
    "anchors": [
      {"record_key": "cycling_power_20m", "x": 1200, "y": 248, "record_id": "record:cycling_power_20m:scope:v2:sha256:abc"}
    ],
    "quality": {
      "state": "ready",
      "reason_codes": []
    }
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": ""
  }
}
```

Curve 契约：

- `points` 是后端降采样/锚点化后的绘图点，不是 raw stream。
- 前端不得从 curve 反算纪录事实。
- `input_fingerprint` 可用于调试和缓存状态，但不包含原始采样。
- `analysis_only` 曲线只进入分析区，不写 active record。

## 10. Candidate APIs

### 10.1 `get_career_record_candidates(filters)`

请求：

```json
{
  "sport": "all",
  "record_key": "all",
  "status": "candidate"
}
```

返回：

```json
{
  "candidates": [
    {
      "id": "candidate:cycling_power_20m:123",
      "activity_id": "123",
      "record_key": "cycling_power_20m",
      "display_name": "20 分钟最大功率",
      "sport": "cycling",
      "sport_label": "骑行",
      "metric": {"name": "power_w", "value": 248, "unit": "watts", "display": "248 W"},
      "scope": {"scope_hash": "scope:v2:sha256:abc", "labels": ["户外", "原始功率"]},
      "quality": {
        "confidence": 0.84,
        "confidence_band": "candidate",
        "reason_codes": ["power_stream_gap"],
        "message_key": "record_reason_power_gap",
        "can_user_confirm": true
      },
      "candidate_state": "candidate",
      "created_at": "2026-07-14T10:00:00Z",
      "detail_link": {"activity_id": "123", "source": "career"}
    }
  ],
  "summary": {"total": 1, "by_sport": {"cycling": 1}, "by_reason_code": {"power_stream_gap": 1}},
  "status": {"schema_ready": true, "data_ready": true, "state": "ready", "message": ""}
}
```

### 10.2 `decide_career_record_candidate(payload)`

请求：

```json
{
  "candidate_id": "candidate:cycling_power_20m:123",
  "action": "confirm"
}
```

允许 action：

- `confirm`
- `reject`

返回：

```json
{
  "action": "confirm",
  "candidate_id": "candidate:cycling_power_20m:123",
  "record_id": "record:cycling_power_20m:scope:v2:sha256:abc",
  "result": "confirmed_not_activated",
  "comparison": {
    "current_record_id": "record:cycling_power_20m:scope:v2:sha256:old",
    "candidate_better": false,
    "message_key": "record_candidate_confirmed_not_better"
  },
  "metrics": {"elapsed_ms": 12}
}
```

决策契约：

- 前端不得传入修改后的成绩、距离、时间、scope、range 或 reason。
- 确认候选后由后端重新比较；不一定激活。
- hard-block、validation_required 和 candidate-only 未解除时不得写 active。
- 重复 confirm/reject 必须幂等。

## 11. Rebuild APIs

### 11.1 `rebuild_career_records(payload)`

请求：

```json
{
  "dry_run": true,
  "sport": "all",
  "record_key": "all",
  "apply_to_real_db": false
}
```

返回：

```json
{
  "run_id": "records-rebuild-20260714-001",
  "dry_run": true,
  "applied": false,
  "summary": {
    "activities_scanned": 120,
    "records_detected": 8,
    "candidates_detected": 3,
    "ignored_count": 14,
    "conflict_count": 0
  },
  "reason_counts": {
    "power_stream_gap": 1,
    "pool_length_missing": 2
  },
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "state": "ready",
    "message": "dry-run 完成"
  }
}
```

安全契约：

- `dry_run=true` 不写库。
- 没有用户明确批准，真实库不得 `applied=true`。
- 返回只包含计数和安全摘要，不返回 raw evidence。

### 11.2 `get_career_record_rebuild_status(payload)`

请求：

```json
{
  "run_id": "records-rebuild-20260714-001"
}
```

返回：

```json
{
  "run_id": "records-rebuild-20260714-001",
  "state": "completed",
  "dry_run": true,
  "started_at": "2026-07-14T10:00:00Z",
  "finished_at": "2026-07-14T10:00:08Z",
  "progress": {"scanned": 120, "total": 120},
  "summary": {"records_detected": 8, "candidates_detected": 3},
  "status": {"schema_ready": true, "data_ready": true, "state": "ready", "message": ""}
}
```

## 12. V1 PB API 兼容包装

现有 API 保留：

- `get_career_pb(filters)`
- `get_career_pb_detail(payload)`
- `get_career_pb_history(filters)`
- `decide_career_pb_candidate(payload)`
- `rebuild_career_pb_records(payload)`
- `get_career_record_events(filters)`
- `get_career_event_candidates(filters)`

包装关系：

| V1 API | V2 来源 | 兼容要求 |
| --- | --- | --- |
| `get_career_pb` | `get_career_records(status=active)` | 返回字段保持 `pb_type/pb_title/value_display/improvement_sec/detail_link`。 |
| `get_career_pb_detail` | `get_career_record_detail` | `record_id` 继续可查；返回旧 `record` shape。 |
| `get_career_pb_history` | `get_career_record_history` | `pb_type/source_mode/sport_scope` 继续可筛选。 |
| `decide_career_pb_candidate` | `decide_career_record_candidate` | 只处理 PB 候选兼容输入。 |
| `rebuild_career_pb_records` | `rebuild_career_records` | `dry_run=true` 默认安全；旧返回 summary 字段保留。 |

兼容硬约束：

- `detail_link.source` 继续为 `"career"`。
- V1 跑步四项 key 不变。
- 旧调用方不需要理解 `scope_hash`。
- `pb_type` 继续等于 V2 `record_key`。
- 旧 API 不返回 V2 curve/raw/internal schema。

## 13. Error Codes

| code | 场景 |
| --- | --- |
| `OK` | 成功。 |
| `RECORD_NOT_FOUND` | record_id 不存在或不可见。 |
| `RECORD_CATALOG_UNAVAILABLE` | Catalog 未初始化或 schema 不可用。 |
| `RECORD_VALIDATION_REQUIRED` | 该纪录族需要数据验收。 |
| `RECORD_CANDIDATE_ONLY` | 该纪录只允许候选。 |
| `RECORD_SCOPE_REQUIRED` | 动态纪录缺 scope。 |
| `RECORD_CURVE_UNAVAILABLE` | 曲线不存在或 cache 未生成。 |
| `RECORD_CANDIDATE_NOT_FOUND` | 候选不存在。 |
| `RECORD_CANDIDATE_ALREADY_DECIDED` | 候选已处理，幂等返回。 |
| `RECORD_CANDIDATE_HARD_BLOCKED` | 候选不允许用户确认。 |
| `RECORD_REBUILD_RUNNING` | 重建正在执行。 |
| `RECORD_REBUILD_DRY_RUN_ONLY` | 当前只允许 dry-run。 |
| `RECORD_SCHEMA_NOT_READY` | schema 未准备好。 |
| `RECORD_UNSAFE_PAYLOAD` | 请求或响应命中安全禁止字段。 |

## 14. `docs/js_api_contract.json` 计划变更

后续 `RCV2-14` 或契约实现任务再修改 `docs/js_api_contract.json`，计划新增：

- `get_career_record_catalog`
- `get_career_records`
- `get_career_record_detail`
- `get_career_record_history`
- `get_career_record_curve`
- `get_career_record_candidates`
- `decide_career_record_candidate`
- `rebuild_career_records`
- `get_career_record_rebuild_status`

计划更新：

- `get_career_pb` 描述中标注 V1 wrapper。
- `get_career_pb_detail` 描述中标注由 V2 detail 包装。
- `get_career_pb_history` 描述中标注由 V2 history 包装。
- `decide_career_pb_candidate` 描述中标注代理到 V2 candidate decision。
- `rebuild_career_pb_records` 描述中强调真实库默认 dry-run 和用户授权。
- `get_career_record_events` 扩展 filters：`record_key/scope_hash/run_id/decision`。
- `get_career_event_candidates` 扩展 V2 record candidate summary，但不透传 raw evidence JSON。

## 15. Mock fixtures 与测试计划

`RCV2-14` 至少新增：

- Catalog mock：跑步 available、骑行 available、泳池 validation_required、公开水域 candidate_only、越野 candidate_only、analysis/model 不进入 active。
- Records mock：running V1 兼容、cycling power scope、多维 scope label、candidate-only 灰态。
- Detail mock：activity_summary 安全字段。
- History mock：higher/lower 两种 axis_direction，total_improvement 后端给出。
- Curve mock：cycling power duration points 为安全绘图点，禁止 raw stream。
- Candidate mock：可确认/不可确认两类。
- Rebuild mock：dry-run 不写库、真实库未授权不 apply。
- V1 response snapshot：旧字段仍存在，`detail_link.source="career"`。
- 禁止字段扫描：所有 API 响应递归扫描安全黑名单。
