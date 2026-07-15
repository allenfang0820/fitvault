# 记录中心滚动契约摘要

更新时间：2026-07-14

用途：后续 `RC-01` 至 `RC-30` 每个任务开始前先刷新本摘要，再决定是否需要全文重读交付手册、任务清单或契约文档。若发生产品语义、公开 API、数据模型、迁移策略或任务依赖冲突，必须回到源文档全文复核。

## 当前任务进度

- 已完成：`RC-00` 至 `RC-27`。
- 当前下一任务：`RC-28 macOS 当前环境与打包产物验收`。
- 最近验证：全部 Career 测试 `468 passed, 24 subtests passed`；活动导入/刷新相关回归 `168 passed`；`career_backend.py`、`main.py` py_compile 通过；`docs/js_api_contract.json` JSON 校验通过。

## 冻结产品与工程边界

- 用户可见模块名为“记录中心”，单项成绩称“纪录”；V1 仍在 ACS/运动生涯内部作为二级页面。
- V1 范围只包含跑步 5K、10K、半程马拉松、马拉松的整次 Activity PB。
- Activity 是唯一事实源；PB Resolver 是正式纪录唯一写入口；前端、AI、Timeline、Overview 只消费后端 ViewModel 或 Snapshot。
- 保留 `career_pb_records`、`get_career_pb()`、`detail_link.source = "career"`。
- 不做最佳分段、骑行功率曲线、路线纪录、环境纪录、公开排行榜，也不新建与 `career_pb_records` 重叠的平行事实表。

## RC-00 代码基线结论

- 当前 PB Resolver 读取 Activity 安全摘要列：`id/sport_type/sub_sport_type/start_time/start_time_utc/dist_km/distance/duration/duration_sec/deleted_at`。
- 当前距离事实源优先 `dist_km`，否则使用 `distance`；当 `distance > 1000` 时按米转公里，否则直接视为公里。
- 当前计时事实源优先 `duration`，否则 `duration_sec`；二者真实 elapsed/moving 语义尚未审计，必须由 `RC-01` 回答。
- 当前跑步 PB 类型和距离区间为硬编码：`running_5k 4.8-5.3km`、`running_10k 9.5-10.8km`、`running_half_marathon 20.5-21.7km`、`running_marathon 41.0-43.0km`。
- 当前比较值为 `duration_sec` 整数秒，`career_pb_records.value` 以 TEXT 保存，读取 active 时通过 `CAST(value AS INTEGER)` 排序。
- 当前状态实际写入 `active` 和 `superseded`；schema 允许任意 status 字符串，但还没有 candidate/rejected/invalidated 的 PB 流程与事件表。
- 当前 ID 规则为 `pb:{pb_type}:{activity_id}`；同一 Activity 同一 PB 类型幂等，当前每个 `pb_type` 通过事务更新避免多个 active。
- 当前 `get_career_pb()` 只返回 active 记录，支持 `sport/year/pb_type/source` 筛选，返回 `pb_records/summary/filters/status`，每条记录含 `detail_link: {activity_id, source: "career"}`。
- 当前前端仍显示“PB 记录/PB 档案”，并在筛选中包含骑行 PB 类型；这是后续记录中心 UI 迁移项，不属于 RC-00 修改范围。
- 当前 Timeline 明确排除 PB 节点：`type=pb` 稳定返回空结果；`type=all/race` 只在赛事节点上聚合 `pb_badge_scope` 皇冠信息。

## RC-01 字段事实源结论

- 当前 FIT 解析的 `duration_sec` 来源主要是 FIT session `total_timer_time`；`fit_engine` 仅在 `total_timer_time` 缺失时 fallback 到 `total_elapsed_time`，导入后 `duration` 与 `duration_sec` 同源。
- 当前真实库 active running Activity 共 95 条，`duration == duration_sec` 为 95 条，因此两个字段不能互相证明 elapsed 语义。
- 使用轨迹点首尾时间只读交叉校验：84 条 running 的 points elapsed 与 `duration_sec` 相差不超过 5 秒，8 条 points elapsed 明显大于 `duration_sec`，3 条 `duration_sec` 略大于 points elapsed。
- 标准距离样本中：5K bucket 6 条、10K bucket 5 条、半马 bucket 2 条均未发现 points elapsed 明显大于 `duration_sec`；但字段语义仍不能直接冻结为 elapsed。
- 距离 canonical 建议使用 `dist_km * 1000`。真实 running 中 95 条都有 `dist_km`，其中 6 条存在 `distance == dist_km` 的历史单位歧义，说明 `distance` 不能单独作为米字段信任。
- RC-03/RC-09 应冻结并实现 `elapsed_time_sec` Performance Summary；当前 `duration_sec` 只能作为 `timer_time_sec` 或经过交叉校验后的候选输入。

## RC-02 真实库 ±3% 影响结论

- 当前真实库 active running Activity 为 95 条。
- 迁移到统一 `±3%` 后不会新增候选；会移除 `running_5k` 2 条、`running_10k` 3 条。
- `running_5k` active 不变，仍为活动 `167`，5.11123km，1628s。
- `running_10k` active 会变化：当前硬编码范围 best 是活动 `108`，9.53095km，2406s；新 `±3%` best 是活动 `150`，10.02619km，3278s。
- 活动 `108` 同时存在计时质量风险：轨迹 elapsed 2450s，比 `duration_sec` 2406s 多 44s，属于 `timer_time_only`。
- `running_half_marathon` active 不变，仍为活动 `239`；但 dry-run 的 Activity 日期与表内 `event_date` 有一天差异，需要后续冻结本地日期口径。
- `running_marathon` 当前无候选。

## RC-03 Registry 与比较规则结论

- V1 Registry 只包含 `running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- 每项定义固定：`sport=running`、`category=distance_time`、`metric=elapsed_time_sec`、`canonical_unit=seconds`、`comparison=lower_is_better`、`source_mode=activity_total`、`tolerance_ratio=0.03`、`rule_version=records-v1`。
- 标准距离：5,000m、10,000m、21,097.5m、42,195m。
- 匹配公式固定为 `abs(actual-standard)/standard <= 0.03`，边界包含。
- V1 不做活动内最佳分段；不能从 10K/半马/全马截取 5K 或 10K。
- 比较规则：更小整数秒 `elapsed_time_sec` 才刷新；相同秒数不刷新；首条纪录 `improvement=null`；平均配速只展示不比较。
- Registry 初始化必须检测同一 `sport + source_mode + category` 下的区间重叠；冲突配置失败，不运行时静默选择。
- `duration_sec` 只能作为旧字段输入，不能作为 Registry metric；RC-09 必须输出 Performance Summary 的 `elapsed_time_sec`、`time_quality` 和 reason codes。

## RC-04 置信度与状态机结论

- 状态冻结为 `candidate`、`active`、`superseded`、`rejected`、`invalidated`。
- 阈值冻结：`confidence > 0.90` 自动进入正式比较；`0.70 <= confidence <= 0.90` 生成 candidate；`confidence < 0.70` 忽略正式 PB，仅记录跳过原因。
- `0.90` 和 `0.70` 都属于 candidate。
- 评分维度至少包含 sport、distance、time、activity_integrity、device_gps_quality、plausibility。
- 每个降级必须有稳定英文 `reason_codes`，前端只翻译，不推导业务语义。
- 用户操作仅 `confirm` / `reject`；确认不允许改成绩值、距离、时间、Activity 或 record key。
- 同一 evidence 幂等键建议：`record_key + activity_id + evidence_key + resolver_version`；V1 evidence key 为 `activity_total:{activity_id}:{record_key}:{distance_m}:{elapsed_time_sec}`。
- rejected 同版本同 evidence 不再提示；仅 resolver version 改变且成绩证据实质变化时可重新 candidate。
- active 来源删除/损坏/关键字段变化时标记 `invalidated`，从剩余有效历史回退下一 active；回退不触发新纪录通知或 Achievement。

## RC-05 数据模型结论

- 继续使用 `career_pb_records`，禁止新建同义 `records/personal_records/records_history` 事实表。
- `career_pb_records` 新增字段冻结：`evidence_key`、`source_mode`、`sport_scope`、`previous_record_id`、`resolver_version`、`confirmed_at`、`rejected_at`、`invalidated_at`、`decision_source`、`decided_at`。
- 旧行默认：`source_mode='activity_total'`、`sport_scope='default'`、`resolver_version='legacy'`、`evidence_key='activity_total:' || activity_id || ':' || pb_type || ':' || value`。
- 新增 append-only `career_record_events`，事件类型包含 `detected/candidate_created/user_confirmed/user_rejected/activated/superseded/invalidated/recalculated/migration_backfilled/activated_from_rebuild`。
- active 唯一性优先使用 partial unique index：`pb_type, source_mode, sport_scope WHERE status='active'`；不支持时必须事务检查 fallback。
- evidence 幂等唯一：`pb_type, activity_id, evidence_key, resolver_version`。
- `value` 暂保留 TEXT；所有比较必须按 `value_unit` 转数值，跑步 V1 为整数秒。
- migration 顺序必须事务化、幂等；失败 rollback 后旧 `get_career_pb()` 仍可读取 active。
- 来源 Activity 软删除或关键字段变化时不物理删除 PB，标记 `invalidated` 并写事件。

## RC-06 API/ViewModel 结论

- 保留并扩展 `get_career_pb(filters)`；新增 `get_career_pb_detail`、`get_career_pb_history`、`get_career_pb_candidates`、`decide_career_pb_candidate`、`rebuild_career_pb_records`。
- 统一 envelope 仍为 `{ok, code, msg, data, traceId}`。
- 所有 Records API status 至少包含 `schema_ready/data_ready/state/message/resolver_version/rebuilding/partial/candidate_count/last_rebuild_run_id/last_rebuild_at`。
- `status.state` 枚举：`loading/ready/empty/partial/rebuilding/error`。
- `decide_career_pb_candidate` 与 `rebuild_career_pb_records` 是写接口，`readonly=false`、`high_risk=true`。
- 所有响应递归禁止 raw FIT、points、track_json、file_path、storage_ref、本地路径和 SQLite schema。
- `get_career_pb()` 的 current record ViewModel 必须包含 `source_mode/source_mode_label/resolver_version/display_metadata/detail_link`，候选不得出现在 current 列表中。
- 前端 mock fixtures 冻结为 `records_empty/records_current/records_candidate/records_rebuilding/records_error/records_history_10k_changed`。

## RC-07 前端设计结论

- 二级导航 `PB -> 记录`，页面标题 `记录中心`。
- 页面三视图冻结为 `当前纪录 / 演进 / 候选`。
- 原型路径：`/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe.html`。
- 桌面截图：`/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe-desktop.png`。
- 移动截图：`/Users/fanglei/.codex/visualizations/2026/07/13/019f5a4a-9a5f-7790-aedd-a157955fe040/records-center-wireframe-mobile.png`。
- 当前纪录视图：状态带、筛选、摘要、跑步四项纪录列表、详情区域。
- 演进视图：单一 record key，lower-is-better 图表语义，历史节点。
- 候选视图：reason、置信度、Activity 入口、确认/拒绝，确认前不替换 current。
- 前端仍不得计算 PB、improvement、confidence 或 record type。
- Milestone A 完成；后续进入 RC-08 至 RC-16 Resolver 与数据闭环。

## RC-08 代码实现结论

- `career_backend.py` 已新增不可变 `RecordDefinition` 和 `RUNNING_RECORD_DEFINITIONS`。
- Registry 覆盖四项 V1 running record：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`。
- Registry 字段遵循 RC-03：`metric=elapsed_time_sec`、`canonical_unit=seconds`、`comparison=lower_is_better`、`source_mode=activity_total`、`tolerance_ratio=0.03`、`rule_version=records-v1`。
- 新增 `validate_record_registry()`，覆盖 key 唯一、单位合法、比较方向合法、source mode 合法和同 scope 区间冲突。
- `PB_TYPE_LABELS`、`PB_TIMELINE_TITLES`、`PB_OVERVIEW_TYPE_PRIORITY` 已从 Registry 派生。
- `RUNNING_PB_DISTANCE_RANGES` 仍作为 legacy Resolver 范围保留至 RC-10，确保 RC-08 不改变现有 active PB。
- 新增测试 `tests/test_career_record_registry.py`，结果 `5 passed`；既有 PB 定向回归 `22 passed`。

## RC-09 代码实现结论

- `career_backend.py` 新增 `_record_performance_summary(row)`，输出 `activity_id/sport/event_date/distance_m/distance_km/elapsed_time_sec/timer_time_sec/distance_quality/time_quality/reason_codes`。
- PB candidate 构建已改为从 Performance Summary 读取距离和时间，不再直接在候选层挑 `duration/duration_sec` 或 `dist_km/distance`。
- 当前兼容策略：legacy `duration/duration_sec` 仍填充 `elapsed_time_sec`，但 `time_quality='semantics_unknown'`，reason codes 包含 `duration_from_total_timer_time` 和 `duration_semantics_unknown`。
- PB `display_metadata_json` 增加白名单 `performance_summary`，不包含 raw points、track_json、file_path。
- RC-09 不改变 active PB 结果，不引入 candidate 状态；RC-11 需要基于 `time_quality` 降级候选。
- 测试：`tests/test_career_pb_resolver.py` 扩展至 10 个用例；Registry+PB+API+Timeline 组合回归 `29 passed`。

## RC-10 代码实现结论

- `career_backend.py` 新增 `match_record_definition(summary, definitions=...)`，按 Registry 执行 `±3%` 包含边界匹配。
- `match_record_definition` 输出 `record_key/source_mode/standard_distance_m/actual_distance_m/distance_error_ratio/definition`。
- 若一个 summary 命中多个 definition，抛出 `ValueError`，不静默选择。
- `career_backend.py` 新增 `compare_record_performance(candidate_value, current_value)`。
- 比较规则：非正候选 invalid；无 current 为首条纪录；更快刷新并给 `improvement_sec`；相同秒数不刷新；更慢不刷新。
- 当前正式写表 Resolver 仍使用 legacy 范围，避免 RC-10 提前改写真实 active；后续由状态迁移/重建任务接入。
- 测试：Registry 匹配/比较扩展后组合回归 `34 passed, 11 subtests passed`。

## RC-11 代码实现结论

- `career_backend.py` 新增记录候选纯决策函数：`score_record_confidence(summary, match)`、`record_evidence_key(summary, match)`、`build_record_candidate_decision(summary, match=None)`。
- 置信度阈值按 RC-04 冻结执行：`>0.90 => auto_confirm/high`，`0.70 <= confidence <= 0.90 => candidate/medium`，`<0.70 => ignored/low`。
- 旧 `duration/duration_sec` 形成的 `time_quality='semantics_unknown'` 会降级为 candidate，不自动写入正式 current。
- 缺距离、缺 elapsed time 或未命中标准距离的 Activity 会输出 `ignored` 与稳定英文 `reason_codes`。
- V1 evidence key 已稳定为 `activity_total:{activity_id}:{record_key}:{distance_m}:{elapsed_time_sec}`，为 RC-12/RC-13 的幂等 candidate/event 写入做准备。
- RC-11 未接入当前 `resolve_pb_records()` 写入链路，未改变 active PB 结果。
- 测试：Registry+PB+API+Timeline 组合回归 `39 passed, 13 subtests passed`，`career_backend.py` py_compile 通过。

## RC-12 代码实现结论

- `career_pb_records` schema 已加入 RC-05 冻结字段：`evidence_key/source_mode/sport_scope/previous_record_id/resolver_version/confirmed_at/rejected_at/invalidated_at/decision_source/decided_at`。
- 旧行 migration 默认：`source_mode='activity_total'`、`sport_scope='default'`、`resolver_version='legacy'`、`decision_source='resolver'`。
- 旧行 `evidence_key` 回填为 `activity_total:{activity_id}:{pb_type}:{value}`，保证旧 `get_career_pb()` 可继续读取 active。
- 新增 append-only `career_record_events` 表，包含 `record_id/activity_id/pb_type/event_type/event_at/evidence_key/resolver_version/source/payload_json/created_at`。
- 新增索引：active scope 唯一、evidence version 唯一、record events record/activity/evidence 查询索引。
- `ensure_career_schema()` 使用 savepoint 包裹迁移；失败时回滚本次 schema 变更，legacy PB 行保持可读。
- legacy `_upsert_active_pb_record()` 调整为先 supersede 旧 active 再插入新 active，以兼容 active scope 唯一索引。
- 测试：Records schema migration + Registry + PB + API + Timeline 组合回归 `44 passed, 13 subtests passed`，`career_backend.py` py_compile 通过。

## 工作区风险

- 工作区在 RC-00 开始前已有大量未提交改动，涉及 `career_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json` 以及多个非 PB 文件和未跟踪文档/测试。
- 本轮 RC-00 只新增/修改记录中心文档与任务清单状态，不改业务代码。
- 后续每个任务必须先用 `git diff --name-status` 和定向 diff 确认自己的文件边界，不得回退或覆盖既有无关改动。

## RC-13 代码实现结论

- `career_backend.py` 新增 Records 状态迁移服务：`apply_record_candidate_decision(conn, decision)`。
- 新增 PB candidate 用户决策函数：`decide_career_pb_candidate(candidate_id, decision, conn=None)`，支持 `confirm/reject`。
- `auto_confirm` 会写 active；若已有更慢 active，则旧纪录 `superseded`，新纪录写入 `previous_record_id` 与 `improvement`。
- 相同或更慢成绩不改变 active，只写 `recalculated` event。
- 中置信 `candidate` 写入 `career_event_candidates(candidate_type='pb_record')`，不污染 `career_pb_records` current/history，并以 evidence key 幂等。
- `reject` 后 candidate 不进入历史链；`confirm` 后重新参与比较并按结果激活或保持 unchanged。
- 所有路径写入 append-only `career_record_events`：`detected/candidate_created/activated/superseded/recalculated/ignored/user_confirmed/user_rejected`。
- 公开 `get_career_pb()` 和 legacy `resolve_pb_records()` 的返回 shape 保持兼容。
- 测试：Records state migration + schema + registry + PB + API + Timeline 组合回归 `50 passed, 13 subtests passed`，`career_backend.py` py_compile 通过。

## RC-14 代码实现结论

- `career_backend.py` 新增 `evaluate_activity_record_increment(conn, activity_id)` 和 `evaluate_activity_record_increments(conn, activity_ids)`。
- 增量入口只读取单个 Activity 的 PB 白名单字段，复用 Performance Summary、Registry、confidence decision 和 RC-13 状态迁移服务。
- `refresh_career_derived_events(conn=None, include_pb=True)` 新增兼容参数；默认仍执行旧全量 PB。
- `main.py` 的单 FIT 同步成功后会把 `activity_id` 传入 `_refresh_career_derived_events_safe()`，先执行 PB 增量，再跳过 legacy PB 全量刷新，避免中置信 candidate 被旧 Resolver 写成 active。
- 增量失败仍由 safe wrapper 捕获，不阻塞 Activity 基础事实保存。
- 测试：Records incremental + state migration + schema + registry + PB + API + Timeline 组合回归 `53 passed, 13 subtests passed`，`career_backend.py/main.py` py_compile 通过。

## RC-15 代码实现结论

- `career_backend.py` 新增 `plan_records_rebuild(conn, resolver_version=...)`，dry-run 不写 PB/candidate。
- 新增 `rebuild_records(conn, dry_run=True, resolver_version=...)`，正式 apply 使用 savepoint，失败回滚本次应用。
- dry-run 输出 `run_id/resolver_version/processed/progress/summary/items`。
- action 分类为 `new/replace/candidate/unchanged/ignored`。
- rebuild 不先清空旧纪录；正式 apply 逐项复用 RC-13 状态迁移服务。
- `_RECORDS_REBUILD_IN_PROGRESS` 提供本地进程内防重入。
- 同一 evidence 重复 rebuild 不重复 candidate 或 `candidate_created` event。
- 测试：Records rebuild + incremental + state migration + schema + registry + PB + API + Timeline 组合回归 `57 passed, 13 subtests passed`，`career_backend.py/main.py` py_compile 通过。

## RC-16 代码实现结论

- `career_backend.py` 新增 `repair_record_lifecycle(conn, record_key=None)`。
- records-v1 active 行在 Activity 缺失/软删除、不再命中 record、record key 改变或 evidence key 改变时标记 `invalidated`。
- legacy 行只按 Activity 缺失/删除判断失效，避免误伤旧数据。
- 同 `pb_type/source_mode/sport_scope` 中最快有效 superseded 会被提升为 active，并写 `activated_from_rebuild` event。
- fallback 不作为新纪录事件，不触发庆祝语义。
- repair 使用 savepoint；失败回滚本次状态变化。
- 重复 repair 不重复 `invalidated` event。
- 测试：Records lifecycle + rebuild + incremental + state migration + schema + registry + PB + API + Timeline 组合回归 `61 passed, 13 subtests passed`，`career_backend.py/main.py` py_compile 通过。

## RC-17 代码实现结论

- `get_career_pb()` 保持旧字段兼容，并新增 `source_mode/source_mode_label/sport_scope/resolver_version/status/evidence_key/previous_record_id/detail_link.record_id`。
- `get_career_pb()` status 新增 `resolver_version/candidate_count`。
- 新增后端只读函数：`get_career_pb_detail(record_id, conn=None)` 与 `get_career_pb_history(pb_type, filters=None, conn=None)`。
- 新增 pywebview wrapper：`Api.get_career_pb_detail()` 与 `Api.get_career_pb_history()`。
- `docs/js_api_contract.json` 已注册两个新 readonly API，并更新 `get_career_pb` returns。
- 测试：PB API + lifecycle + rebuild + incremental + state migration + schema + registry + PB resolver + Timeline 组合回归 `63 passed, 13 subtests passed`，py_compile 与 contract JSON 校验通过。

## RC-18 代码实现结论

- `career_backend.py` 新增 `get_career_record_events(filters=None, conn=None)`，支持 `record_id/pb_type/record_key/event_type` 筛选。
- `main.py` 新增 `Api.decide_career_pb_candidate(payload)`，只接受 `confirm/reject`。
- `main.py` 新增 `Api.rebuild_career_pb_records(payload=None)`，默认 dry-run；apply 失败 rollback。
- `main.py` 新增 `Api.get_career_record_events(filters=None)`。
- `docs/js_api_contract.json` 已将 candidate decision 与 rebuild 标记为 `readonly=false/high_risk=true`，events 查询为 `readonly=true/high_risk=false`。
- 测试：Record maintenance API + PB API + lifecycle + rebuild + incremental + state migration + schema + registry + PB resolver + Timeline 组合回归 `66 passed, 13 subtests passed`，py_compile 与 contract JSON 校验通过。

## RC-19 代码实现结论

- `track.html` 运动生涯二级导航用户可见 `PB` 已改为 `记录`，页面标题映射为 `记录中心`。
- 当前 PB 区块用户可见标题改为 `记录中心`，筛选/空态文案改为记录语义。
- 当前纪录摘要消费后端 `status.candidate_count`，显示 `待确认 N 项`。
- 当前纪录卡继续只展示后端 ViewModel 字段，新增展示 `source_mode_label`，前端仍不计算 PB/improvement/confidence/record type。
- 内部 page key 暂保留 `pb`，避免扩大路由改动。
- 测试：Career archives frontend + phase8 readiness + Records/PB/API 组合回归 `84 passed, 13 subtests passed`，后端 py_compile 通过。

## RC-20 代码实现结论

- `track.html` 当前纪录区新增 `career-pb-detail-panel`。
- 当前纪录卡新增 `查看演进` 按钮，携带 `data-record-id` 与 `data-pb-type`。
- 新增 `renderCareerPbDetailPanel(detail, history)`、`loadCareerPbDetail(recordId, pbType)`、`openCareerRecordDetailFromElement(event, el)`。
- `normalizeCareerDetailLink()` 支持 `record_id/recordId`。
- 详情面板调用 `api.get_career_pb_detail(recordId)` 与 `api.get_career_pb_history(pbType || 'all', {})`。
- 当前纪录卡 Activity 回跳能力保留；“查看演进”按钮使用 `stopPropagation()` 避免误触发。
- 测试：Career archives frontend + phase8 readiness + Records/PB/API 组合回归 `85 passed, 13 subtests passed`，后端 py_compile 通过。

## RC-21 代码实现结论

- `track.html` 当前纪录区新增 `career-pb-candidate-panel`。
- 新增 `normalizeCareerRecordCandidate(item)`、`renderCareerPbCandidates(candidates)`、`decideCareerPbCandidateFromElement(event, el)`。
- `loadCareerArchives()` 现在加载 `api.get_career_event_candidates({ candidate_type: 'pb_record', status: 'candidate' })`。
- confirm/reject 只提交 `candidate_id` 与 `decision`，成功后刷新 `loadCareerArchives()`。
- 前端不修改成绩、距离、时间、Activity 或 record key。
- 测试：Career archives frontend + phase8 readiness + Records/PB/API 组合回归 `86 passed, 13 subtests passed`，后端 py_compile 通过。

## RC-22 代码实现结论

- 记录中心状态/摘要/详情/候选面板增加 `aria-live="polite"`。
- “查看演进”“确认”“拒绝”按钮增加 `aria-label` 与 `title`。
- 候选 confirm/reject 提交期间禁用当前按钮，并显示 `确认中...` / `处理中...`；失败时恢复。
- 新增 `.career-pb-detail-action:disabled` 样式；移动端详情面板间距补强。
- 测试：Career archives frontend + phase8 readiness + Records/PB/API 组合回归 `87 passed, 13 subtests passed`，后端 py_compile 通过。

## RC-23 入口提示

`RC-23` 需要联动 Overview、Timeline、Race、Achievement：记录中心更新后 overview/latest_pb/timeline PB crown/achievement 不应重复或冲突；新纪录事件消费需幂等，不让 candidate 出现在正式 timeline。

## RC-23 代码实现结论

- Overview PB 摘要只消费正式 active/superseded 纪录事实；`pb_record` candidate 不进入 `pb_count`、`latest_pb` 或 `representative_pb_records`。
- PB 的 `detail_link` 在 Overview 中保留 `{activity_id, source: "career", record_id}`，用于记录详情/演进；Race/Achievement 仍保持 Activity 回跳契约。
- Timeline 候选禁入测试限定在 Timeline 面板/流程；记录中心页面自身仍可调用候选 API。
- 同一 `pb_type/source_mode/sport_scope` 只允许一个 active；历史测试数据需将旧纪录置为 `superseded`。
- 测试：Overview + Timeline + Records/PB/API 组合回归 `125 passed, 13 subtests passed`，后端 py_compile 通过。

## RC-24 入口提示

`RC-24` 需要把 Records facts 安全压缩进 `career_snapshots`：只输出当前纪录、最近刷新、候选数量和演进摘要白名单；AI/Trends 只能解释，不得重算 PB，不得读取候选强结论，不得暴露 raw FIT、轨迹、路径、schema 或 detail link。

## RC-24 代码实现结论

- Career Snapshot 复用 `career_snapshots`，新增 `records_summary` 分区，不新增平行事实表。
- `records_summary` 白名单字段为 `current_records`、`recent_refreshes`、`candidate_count`、`evolution_summary`、`trend_inputs`。
- `recent_refreshes` 只包含正式刷新事件：`activated`、`activated_from_rebuild`、`user_confirmed`、`recalculated`；候选只保留数量。
- `trend_inputs.interpretation` 固定为 `frequency_only`，只表达刷新频率和演进事件数量，不表达能力提升。
- AI fallback 只消费白名单 Snapshot，不调用 LLM、不读取候选证据、不重算 PB、不写 canonical 事实表。
- Snapshot 清洗继续禁止 `detail_link`、raw FIT、points、track_json、file_path、storage_ref、schema、thumbnail_url、payload 等敏感/越权字段。
- 测试：Snapshot + Insight + Records/PB + Overview/Timeline 组合回归 `126 passed, 13 subtests passed`，后端 py_compile 和 JS API JSON 校验通过。

## RC-25 入口提示

`RC-25` 需要收敛记录中心安全、性能、日志与可观测性：高风险写接口要有确认/输入边界，批量重建要有范围和结果摘要，日志不得泄露 raw FIT/本地路径/证据 payload，关键路径应有可测试的性能或查询数量保护，错误状态要可诊断但不暴露敏感数据。

## RC-25 代码实现结论

- `_sanitize_public_metadata()` 递归移除禁止 key，并清空疑似本地路径字符串值；事件 payload 嵌套清洗有测试覆盖。
- 增量评估、批量增量、重建计划/应用、候选决策、PB 查询/详情/历史/事件查询均返回耗时指标。
- 重建 metrics 包含 `processed`、`reason_counts`、`applied_summary`；事件查询 metrics 包含 `returned_count`。
- 安全日志只记录 run_id、resolver_version、处理/应用摘要、原因计数和耗时，不记录 payload、证据原文、raw FIT、轨迹、路径或 schema。
- 10,000 条合成 Activity 的 rebuild dry-run 性能门已纳入自动化测试，门限为 `metrics.elapsed_ms < 8000ms` 且 wall time `< 10000ms`。
- 测试：RC-25 定向 `63 passed, 13 subtests passed`；组合回归 `150 passed, 13 subtests passed`；后端 py_compile 和 JS API JSON 校验通过。

## RC-26 入口提示

`RC-26` 需要把已完成的 Records Center 能力整理成自动化测试矩阵与宽回归门：覆盖 Registry、Performance Summary、Resolver、Schema、状态迁移、增量、重建、API、前端三视图、跨模块、Snapshot/AI、性能安全；补齐缺口后运行最宽可行回归，并记录最终测试矩阵。

## RC-26 代码实现结论

- `ensure_career_schema()` 默认连接缓存增加 DB path 维度，切换 `profile_backend.DB_PATH` 时不会跳过新库初始化。
- Timeline 旧测试数据更新为符合 active PB scope 唯一约束。
- FIT sync 旧断言更新为导入后 `refresh_career_derived_events(include_pb=False)`，匹配 Records 增量评估契约。
- 测试矩阵文档已覆盖 Registry、Performance Summary、Resolver、Schema、状态机、增量、重建、API、前端、跨模块、Snapshot/AI、性能安全、JSON contract 与编译。
- 验证：全部 Career 测试 `468 passed, 24 subtests passed`；活动导入/刷新相关回归 `168 passed`；py_compile 和 JSON contract 校验通过。

## RC-27 入口提示

`RC-27` 需要在当前真实库上执行 Records Center dry-run、迁移影响与人工复核材料：不得直接破坏真实 active 结果；先备份或只读审计，再输出新增/替换/候选/回退差异、性能耗时、风险清单和可人工确认的样本。

## RC-27 代码实现结论

- 已备份真实库 `/Users/fanglei/.fitvault/user_profile.db`，备份 sha256 与源库一致：`c76b6ce5d7bb736e8510e5b750b1fcf8f93285a122f582e050d57bbd2470108f`。
- 已在 staging 副本执行 dry-run：processed `253`，summary 为 `candidate=13`、`ignored=240`、`new=0`、`replace=0`、`unchanged=0`，耗时约 `37ms`。
- 已在 staging 副本执行 apply 验证：active PB 仍为 `3`，候选从 `32` 增至 `45`，新增 `13` 条候选。
- 当前 active PB 为 running_10k activity `108`、running_half_marathon activity `239`、running_5k activity `167`。
- 13 条候选共同原因包含 `duration_semantics_unknown`，按冻结规则需要人工确认，不能自动发布。
- 用户人工复核结论：先全部保持候选，不写入真实库；本轮不对真实库执行 rebuild/apply。

## RC-28 入口提示

`RC-28` 需要在当前 macOS 环境验收记录中心功能与打包产物：确认本地应用可启动、记录中心前端可用、只读/写接口 envelope 正常、真实库保持 RC-27 决策不被污染，并检查现有 macOS 打包脚本或产物状态；若需要新打包但缺少签名/环境，应记录为待发布风险而非擅自扩展。
