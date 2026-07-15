# RC-00 当前实现与工作区基线审计

日期：2026-07-13

## 执行提示词

目标：建立记录中心开发的可信起点，确认现有 PB Resolver、schema、API、前端、Timeline、Achievement 和测试的真实状态，并划定脏工作区边界。

范围：`career_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json`、`tests/test_career_pb_resolver.py`、`tests/test_career_pb_api.py`、`tests/test_career_timeline_pb_nodes.py`。

约束：不修改 PB 判定规则，不调整 UI，不执行 schema migration，不覆盖当前工作区中已有未提交改动。

完成定义：交付可追溯代码证据的基线审计；运行 PB 定向测试；更新滚动契约摘要和任务清单状态。

## 1. 当前 PB Resolver 基线

现有 PB Resolver 位于 `career_backend.py`，入口为 `resolve_pb_records()`。

代码证据：

- `PB_RESOLVER_ACTIVITY_COLUMNS` 只读取 Activity 安全摘要列：`id`、`sport_type`、`sub_sport_type`、`start_time`、`start_time_utc`、`dist_km`、`distance`、`duration`、`duration_sec`、`deleted_at`。
- `PB_FORBIDDEN_ACTIVITY_COLUMNS` 明确禁止 PB Resolver 读取 `points`、`points_json`、`track_json`、`raw_records`、`fit_records`、`file_path` 等字段。
- `_fetch_pb_resolver_activity_rows()` 从 `activities` 按 `_deleted_filter(conn)` 读取未删除活动。
- `_is_running_activity()` 判断 `sport_type` 或 `sub_sport_type` 是否属于 running 集合。
- `_build_pb_candidates()` 只从整次活动生成 PB 候选，不扫描分段或轨迹。

当前 Resolver 不是 Record Registry 驱动，而是直接使用硬编码常量。

## 2. 当前 PB 类型、距离区间与比较规则

当前跑步 PB 类型来自 `RUNNING_PB_DISTANCE_RANGES`：

| pb_type | 当前区间 |
| --- | --- |
| `running_5k` | 4.8-5.3 km |
| `running_10k` | 9.5-10.8 km |
| `running_half_marathon` | 20.5-21.7 km |
| `running_marathon` | 41.0-43.0 km |

这与交付手册要求的统一包含边界 `±3%` 公式不一致，属于后续 `RC-02/RC-03/RC-10` 的迁移对象。

当前比较逻辑：

- `_activity_duration_sec()` 优先使用 `duration`，否则使用 `duration_sec`。
- `_best_pb_by_type()` 以 `(duration_sec, event_date, activity_id)` 升序选择每个 `pb_type` 的最佳活动。
- `_active_pb_row()` 查询 active 时以 `CAST(value AS INTEGER)` 排序。
- `_upsert_active_pb_record()` 将新 active 写入 `value`，`value_unit` 固定为 `seconds`。
- improvement 为旧 active 秒数减新成绩秒数；首条纪录为 `null`。

RC-00 无法确认 `duration` 与 `duration_sec` 是 elapsed time 还是 moving time；这必须在 `RC-01` 通过 FIT 解析链路、Activity schema 和真实库样本审计。

## 3. 当前 ID、状态与写入行为

当前 ID 规则：

```text
pb:{pb_type}:{activity_id}
```

当前实际状态：

- Resolver 写入 `active`。
- 当同一 `pb_type` 有新的 active 时，其他 active 更新为 `superseded`。
- 现有 schema 没有限制 status 枚举，也没有 PB 专用 `candidate/rejected/invalidated` 流程。

当前幂等性：

- 同一 ID 使用 `ON CONFLICT(id) DO UPDATE`。
- 现有测试覆盖重复运行不会新增重复 PB，且 active 数稳定。

当前缺口：

- 没有 `career_record_events` append-only 审计表。
- 没有 `previous_record_id`、`source_mode`、`evidence_key`、`resolver_version` 等结构化字段。
- 没有候选确认/拒绝、删除回退或全量 dry-run/rebuild。

## 4. `career_pb_records` schema 与索引

当前 `ensure_career_schema()` 创建的 `career_pb_records` 字段：

| 字段 | 当前定义 |
| --- | --- |
| `id` | `TEXT PRIMARY KEY` |
| `activity_id` | `TEXT NOT NULL` |
| `sport` | `TEXT NOT NULL` |
| `pb_type` | `TEXT NOT NULL` |
| `value` | `TEXT NOT NULL` |
| `value_unit` | `TEXT NOT NULL DEFAULT ''` |
| `improvement` | `TEXT` |
| `event_date` | `TEXT NOT NULL` |
| `confidence` | `REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0)` |
| `source` | `TEXT NOT NULL DEFAULT 'resolver'` |
| `status` | `TEXT NOT NULL DEFAULT 'active'` |
| `display_metadata_json` | `TEXT NOT NULL DEFAULT '{}'` |
| `created_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| `updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` |

当前 PB 相关索引：

- `idx_career_pb_records_activity` on `career_pb_records(activity_id)`
- `idx_career_pb_records_sport_type_date` on `career_pb_records(sport, pb_type, event_date)`

当前不存在的结构：

- `career_record_events`
- partial unique active index
- `pb_type + activity_id + evidence_key` 唯一约束

## 5. `get_career_pb()` API 基线

后端只读函数：

- `career_backend.get_career_pb(filters, conn=None)`
- `main.py` pywebview wrapper：`get_career_pb(self, filters=None)`

当前筛选：

- `sport`
- `year`
- `pb_type`
- `source`

当前返回：

```text
{
  pb_records,
  summary,
  filters,
  status: {schema_ready, data_ready, message}
}
```

当前 `pb_records[]` 字段：

- `id`
- `activity_id`
- `sport`
- `sport_label`
- `pb_type`
- `pb_type_label`
- `pb_title`
- `value`
- `value_unit`
- `value_display`
- `improvement_sec`
- `improvement_display`
- `event_date`
- `year`
- `month`
- `display_date`
- `confidence`
- `source`
- `source_label`
- `confidence_label`
- `display_metadata`
- `detail_link: {activity_id, source: "career"}`

当前 API 契约文件 `docs/js_api_contract.json` 仍描述为“ACS PB 档案只读 API”，未包含记录中心 V1 需要的 detail/history/candidates/decision/rebuild 接口。

## 6. 前端使用位置

当前前端仍是 PB 档案页：

- 页面容器：`data-career-page="pb"`
- 页面标题：`PB 记录`
- API 调用：`api.get_career_pb(pbFilters)`
- 当前渲染：`normalizeCareerArchivePb()`、`careerPbArchiveCardHtml()`、`renderCareerArchives()`

当前前端行为：

- 只消费后端 ViewModel，不自行计算 PB、improvement 或 confidence。
- 点击 PB 卡通过 `detail_link` 或 `activity_id` 打开 Activity Detail。
- 仍显示“PB 档案/PB 记录”，且筛选器包含 `cycling_distance/cycling_ascent/cycling_avg_speed`，这与记录中心 V1 范围不一致，属于 `RC-07/RC-19` 后续设计和实现任务。

## 7. Timeline 与 Achievement 基线

Timeline：

- `get_career_timeline({"type": "pb"})` 当前稳定返回空结果。
- `type=all` 和 `type=race` 不返回独立 PB 节点。
- 后端通过 `_timeline_pb_badge_scope_by_activity()` 从 PB 表聚合 `career/season` 范围，并在 race 节点上显示 PB 皇冠。
- 测试 `tests/test_career_timeline_pb_nodes.py` 明确断言 `type=pb` 空结果、`type=all` 排除 PB 节点、sport/year filter 不会重新引入 PB 节点。

Achievement：

- 当前已有 `career_achievement_events` 表和 Achievement Resolver。
- `PB` 与 Achievement 的正式幂等联动尚未按记录中心 V1 契约实现。
- 交付手册要求未来正式刷新纪录才可生成 Achievement，候选、拒绝、重算无变化不得重复生成 Achievement。

## 8. 测试基线

命令：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed in 0.16s
```

覆盖要点：

- 四项跑步标准距离可写入 active PB。
- 同类型保留最快成绩。
- 新纪录会 supersede 旧 active 并计算 improvement。
- 非跑步、距离不匹配、缺失 duration 会跳过。
- Resolver 重复运行幂等。
- `get_career_pb()` 只返回 active，格式化显示字段稳定，清除 forbidden metadata。
- Timeline 兼容期排除 PB 节点。

## 9. 工作区边界

RC-00 开始时，工作区已有未提交修改，至少包括：

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `llm_backend.py`
- `metrics_registry.py`
- `metrics_resolver.py`
- `utils/metrics_calc.py`
- 多个现有测试文件
- 多个未跟踪 ACS/footprint/fatigue-review 文档与测试
- 本记录中心交付手册与任务清单为未跟踪文件

本任务可编辑范围：

- `docs/records_center_rc_00_baseline_audit.md`
- `docs/records_center_rolling_contract_summary.md`
- `docs/records_center_rc_00_baseline_audit_completion_report.md`
- `docs/运动生涯记录中心（PB功能）开发任务清单.md` 的 RC-00 状态和下一任务指针

本任务不应编辑业务代码或回退任何既有未提交改动。

## 10. 附录 B 问题的 RC-00 回答状态

| 问题 | 当前答案 |
| --- | --- |
| `duration` / `duration_sec` 语义 | 尚未确认；当前代码优先 `duration`，否则 `duration_sec`，RC-01 必须审计 |
| 历史 Activity 是否有可靠 elapsed 字段 | 尚未确认，RC-01 必须用真实库和解析链路回答 |
| 软删除、重新导入、Activity ID 去重契约 | PB 查询使用 `_deleted_filter` 排除删除活动；导入去重契约需后续任务审计 |
| 跑步机距离来源和质量字段 | 尚未确认，RC-01 必须覆盖 |
| Timeline 为什么排除 PB 节点 | 当前代码与测试显式保持 `type=pb` 空结果，PB 只作为 race 节点皇冠聚合 |
| Achievement 在来源 PB 失效后的策略 | 当前未实现记录中心 V1 契约，需 RC-23 冻结并实现 |
| Windows 打包环境 SQLite migration/后台重建表现 | 当前无证据，RC-29 不可无真机证据标 Done |

## 11. 下一任务输入

`RC-01` 应优先审计：

- FIT 解析到 Activity 的 `duration`、`duration_sec`、elapsed/moving time 写入链路。
- `dist_km` 与 `distance` 的单位来源和转换边界。
- 真实 SQLite 库中跑步 Activity 的时长字段覆盖率与语义可靠性。
- 跑步机、自动暂停、字段缺失样本的质量分类。
