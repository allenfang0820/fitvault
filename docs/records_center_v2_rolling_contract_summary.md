# 记录中心 V2 滚动契约摘要

更新时间：2026-07-15

用途：从 `RCV2-01` 开始，每个任务默认先读本摘要、当前任务条目、上一任务完成报告和直接涉及的代码/契约/测试。只有出现产品语义、API/schema、真实数据结果或摘要内容的严重冲突时，才全文重读 V2 交付手册和契约文档。

## 当前任务进度

- V2 任务总数：`RCV2-00` 至 `RCV2-44`，共 45 项。
- 已完成：`RCV2-00` 至 `RCV2-42`。
- 当前下一任务：`RCV2-43 Windows 真机、pywebview 与视觉验收`，当前阻塞于缺少 Windows 真机环境。
- V1 继承基线：`RC-00` 至 `RC-27` 已完成；旧 `RC-28` 至 `RC-30` 不再代表最终发布完成，V2 完成后按新清单重新验收平台和发布门禁。
- 最新基线验证：RCV2-42 macOS/pywebview/envelope `32 passed`；Records V2 前端 `21 passed`；视觉/数据边界 `20 passed`；`career_backend.py` / `main.py` py_compile 通过；未打包。

## 全局硬约束

- Activity 是唯一事实源。
- 打包/发布/生成 DMG 或 MSI 前必须先阅读 `docs/打包前必读.md`，并通过 `.venv312` Python 3.12 runtime gate：`PYTHON=.venv312/bin/python scripts/install_packaging_deps.sh`、`.venv312/bin/python scripts/check_python312_runtime.py`、`.venv312/bin/python -m packaging_diagnostics`。Codex 代打包不得跳过。
- Resolver/状态迁移服务是正式纪录唯一写入口。
- 前端只渲染 ViewModel，不计算纪录、Scope、累计提升、轴方向或置信度。
- AI 只消费安全 Records Snapshot，不读取 raw FIT、功率流、轨迹、路径、SQLite schema 或体重历史。
- 每条纪录必须绑定 `activity_id`；分段、功率、路线和泳段纪录还必须绑定 Activity 内范围。
- 继续使用并兼容 `career_pb_records`、`career_record_events` 和 `career_event_candidates`，不新建同义事实表。
- `get_career_pb*` 与 `detail_link.source = "career"` 保持兼容。
- 置信度阈值：`>0.90` 自动确认，`0.70-0.90` 候选，`<0.70` 忽略；边界 `0.70/0.90` 均为候选。
- 跑步 V1 四项结果不得因 V2 改变。
- 模型估计和分析曲线不得污染正式纪录。
- 未通过数据验收的运动必须在 Catalog 中 `available=false` 或 validation required。
- 第一次 V2 真实数据评估只允许备份、staging 和 dry-run；没有用户批准不得 apply 真实库。
- 用户仍未授权重新打包；`RCV2-44` 前不得生成、签名、公证或替换发布包。
- 工作区已有改动属于用户；不得覆盖、回退或整理无关修改。

## V2 产品与运动规则摘要

- 产品名继续是“记录中心”，位于“运动生涯”内部；“PB”只作为个人最佳成绩标签。
- 跑步继承 V1：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`，整次 Activity，包含边界的 `±3%`，整数秒 elapsed time，越低越好。
- 骑行新增标准距离最快成绩入口：10K、20K、40K、50K、100K、180K，越低越好；V2 先注册为 `validation_required`，需距离-时间流契约冻结后才能生成 active，不得用整次活动均速替代。
- 骑行核心是 Power Duration Curve 和固定功率锚点：5s、30s、1m、5m、10m、20m、30m、60m、2h，越高越好；0W 是有效滑行，缺失不是 0W，不跨长暂停/断点；eFTP、CP、W′、MAP、PMax 是模型估计，不是正式纪录。
- 骑行整次活动纪录包括最长距离、最大爬升、最长历时、最大机械功；最快均速暂不作为 V2 核心正式纪录。
- 徒步只接收 `hiking`，不混排 walking/mountaineering/trail_running；正式纪录为最长距离、最大累计爬升、最长 elapsed time、最高海拔、最大连续爬升；不设置通用最快 5K/10K。
- 游泳分 `pool_swimming` 与 `open_water_swimming`。泳池需明确 pool length、连续 Length/Lap、泳姿 Scope；缺少 pool length 不得默认 25m。公开水域 V2.0 用整次活动标准距离 `±5%` 和强 GPS/计时质量。
- 越野跑分离 road running、trail running、hiking、mountaineering；正式整次纪录为距离、爬升、历时、海拔、连续爬升；路线/赛段 PR 使用同路线/同方向 elapsed time，在真实样本验收前 candidate-only；Pace/GAP Curve 只做分析。

## 当前代码基线

- `career_backend.py` 目前的 `RecordDefinition` 仍是 V1 形态：`key/sport/category/display_name/metric/canonical_unit/comparison/source_mode/standard_distance_m/tolerance_ratio/minimum_data_requirements/enabled_release/rule_version/priority`。
- `RECORD_DEFINITIONS` 当前只包含四项 running V1；允许单位仅 `seconds`，source mode 仅 `activity_total`。
- `career_pb_records` 已具备 V1 扩展字段：`evidence_key/source_mode/sport_scope/previous_record_id/resolver_version/confirmed_at/rejected_at/invalidated_at/decision_source/decided_at`。
- `career_record_events` 已存在 append-only 事件表；`career_event_candidates` 已用于 PB 候选。
- `get_career_pb()` 只返回 active 纪录；`get_career_pb_detail()`、`get_career_pb_history()`、`get_career_record_events()` 已存在只读 API；`decide_career_pb_candidate()` 和 `rebuild_career_pb_records()` 是高风险写接口。
- `docs/js_api_contract.json` 目前仍以 PB API 为主，还没有 V2 通用 `get_career_record_catalog/get_career_records/get_career_record_curve` 等契约。
- `track.html` 记录中心仍是 V1 `career-pb-*` 结构，并仍存在 `cycling_distance` 等未交付骑行 PB 筛选项；这些是 V2 前端重构和冗余清理对象，不能解释为骑行纪录算法已完成。
- Career Overview 已统计 running/cycling/walking/hiking/swimming 距离，但这不是 Records V2 正式纪录。

## 真实数据与用户决策

- V1 staged 结果中不确定 PB 继续全部保持候选；真实库不做强制重建。
- V2 新运动第一次全量评估必须先在副本 dry-run，不得对真实库 apply。
- 手册中的只读审计摘要：骑行 94 条，其中 67 条有汇总功率和逐点功率流；徒步 7 条、登山 5 条、步行 38 条；游泳 2 条且均为公开水域；越野跑真实样本为 0。
- `RCV2-01` 已用当前真实库只读复核这些数字和字段覆盖；真实库审计前后修改时间均为 `1784001529`，未写库。
- RCV2-01 真实库复核：普通骑行 94 条，电助力 2 条；普通骑行中 67 条有正的汇总功率/NP 和逐点功率流，27 条无可用功率流；徒步 7 条、登山 5 条、步行 38 条；游泳 2 条且均为公开水域；越野跑 0 条。
- 当前 `duration_sec/duration` 主要来自 FIT session `total_timer_time`，仅在缺失时 fallback `total_elapsed_time`；多运动正式 elapsed 语义必须继续带质量标记，不能由前端选择。
- `user_profile_snapshots` 有同步日期级体重快照，但没有活动日期级、来源质量明确的历史体重表；W/kg 不能用当前体重回填历史。
- 当前没有独立 canonical `pool_length` Activity 字段，且 `MetricsResolver` 对 `lap_swimming` 有 25m fallback；V2 正式泳池纪录必须新增/冻结 pool length 事实，不能使用 fallback 生成 active。

## 工作区边界

- 当前工作区已有大量未提交改动，涉及 `career_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json`、多份 ACS/疲劳复盘/年度 AI 文档和测试。
- 后续每个任务必须先查看 `git status --short` 与相关 diff，只处理本任务范围。
- 用户要求因 V2 改版造成的 V1 冗余垃圾代码一并清理；清理必须随具体任务执行，不能在审计任务中泛化删除。
- 已识别的 V1 冗余清理候选：`track.html` 中未交付骑行 PB 筛选项、V1 `career-pb-*` 视觉结构中与 V2 Catalog/Records Shell 冲突的硬编码、旧 PB 文案残留。实际删除时必须由对应前端/API 任务验证替代路径已经存在。

## RCV2-02 Golden fixture 结论

- 新增 `tests/fixtures/records_center_v2/golden_manifest.json`，版本为 `records-center-v2-golden-fixtures-v1`。
- 新增 `tests/test_records_center_v2_golden_fixtures.py`，验证 schema、覆盖项、candidate-only 限制和敏感字段扫描；结果 `4 passed`。
- Fixture 均为合成数据，坐标使用 `synthetic_xy_meters`，不含真实路径、真实 GPS、设备序列号、账号、token 或体重历史。
- 覆盖 case：骑行非 1Hz/0W、骑行缺失/断点/尖峰、电助力排除、徒步海拔尖峰/连续爬升、泳池休息/泳姿/pool length 缺失、公开水域 `±5%` 边界/GPS 跳点、越野同向/反向/低重合路线。
- Fixture 全绿只能证明算法开发输入可用，不能把泳池或越野标记为真实数据 Verified。

## RCV2-03 Registry 与 Scope 冻结结论

- 新增契约：`docs/records_center_v2_rcv2_03_registry_scope_contract.md`。
- V2 `RecordDefinition` 字段已冻结：`key/sport/family/display_name/metric/canonical_unit/comparison/source_mode/scope_dimensions/minimum_data_requirements/quality_policy/enabled_release/rule_version/priority/availability_state/availability_reason/standard_distance_m/standard_duration_sec/tolerance_ratio/dynamic_scope/legacy_category`。
- family 白名单：`distance_time_pb`、`power_duration_pb`、`activity_total_record`、`route_pr`、`segment_pr`、`analysis_curve`、`model_estimate`；其中 `analysis_curve` 和 `model_estimate` 不写正式纪录。
- source_mode 白名单：`activity_total`、`best_effort_duration`、`best_effort_distance`、`route_total`、`segment`。
- scope_dimensions 白名单：`sport_scope`、`indoor_scope`、`power_metric_scope`、`pool_length_scope`、`stroke_scope`、`water_scope`、`route_key`、`segment_key`；全部由后端生成。
- availability 白名单：`available`、`candidate_only`、`validation_required`、`unavailable`、`analysis_only`、`model_only`。
- 跑步 V1 四项完全继承：`running_5k`、`running_10k`、`running_half_marathon`、`running_marathon`，`±3%`、`activity_total`、`seconds`、`lower_is_better` 均不变。
- 骑行功率锚点冻结为 `cycling_power_5s/30s/1m/5m/20m/60m`，`best_effort_duration`、`watts`、`higher_is_better`，Scope 为 `sport_scope/indoor_scope/power_metric_scope`；0W 有效，缺失不是 0W，e-bike 排除。
- 骑行整次活动纪录冻结为 `cycling_longest_distance`、`cycling_max_ascent`、`cycling_longest_elapsed_time`、`cycling_max_work`；其中机械功 `validation_required`，最快均速不作为 V2 正式纪录。
- 徒步纪录冻结为 `hiking_longest_distance`、`hiking_max_ascent`、`hiking_longest_elapsed_time`、`hiking_max_altitude`、`hiking_max_single_climb`；只接收 `hiking`，最大连续爬升 `candidate_only` 且必须带范围。
- 泳池标准距离冻结为 50m、100m、200m、400m、800m、1500m，`best_effort_distance`、`seconds`、`lower_is_better`，Scope 为 `water_scope/pool_length_scope/stroke_scope`；因无真实泳池样本和 pool length schema 缺失，默认 `validation_required`。
- 公开水域标准距离冻结为 750m、1500m、1900m、3800m、5K、10K，整次活动 `±5%`，默认 `candidate_only`；另有最长距离和最长历时 `candidate_only`。
- 越野整次纪录冻结为距离、爬升、历时、最高海拔、最大连续爬升，默认 `candidate_only`。
- 动态越野路线/赛段 key 只注册 `trail_route_best_time`、`trail_segment_best_time`、`trail_climb_segment_best_time`；实例身份为 `record_key + "::" + scope_key`。
- 明确不注册为正式 active record：W/kg、eFTP、CP、W′、MAP、PMax、GAP/NGP、SWOLF 趋势、Pace/GAP 曲线。
- RCV2-03 验证：契约白名单/唯一性脚本输出 `contract_check_ok record_keys=45`；golden fixture 测试 `4 passed`。

## RCV2-04 质量、置信度与原因码冻结结论

- 新增契约：`docs/records_center_v2_rcv2_04_quality_confidence_contract.md`。
- 继续继承阈值：`>0.90` 自动确认，`0.70-0.90` 候选，`<0.70` 忽略；`0.70/0.90` 均为候选。
- 决策优先级冻结：`analysis_only/model_only` 短路；hard-block 短路；Registry `validation_required` 不得 active；Registry `candidate_only` 最高只能 candidate；最后才按 confidence 进入 auto/candidate/ignored。
- `QualityDecision` 输出冻结：`decision/confidence/confidence_band/reason_codes/user_message_key/log_safety/can_user_confirm/blocks_active/evidence_fingerprint`。
- reason code 必须是稳定英文枚举；前端只翻译后端给出的 `user_message_key`，不得解析技术 evidence。
- 用户确认只能确认候选证据，不得修改成绩、距离、时间、功率、海拔、Activity、record key、scope 或范围。
- 用户不可确认 hard-block：Activity 删除/解析失败/mock、record definition 冲突、缺 Activity ID、缺 metric、缺必需 scope/range、标准距离超容差、e-bike 混入普通骑行、功率锚点缺功率流、缺 pool length/fallback、路线反向/低重合/缺 route signature、W/kg 缺历史体重。
- 用户可确认降级候选：时间语义不明、合理性离群、功率缺失点/断点/尖峰、海拔尖峰/累计爬升质量、连续爬升复核、未知泳姿但 pool length 已确认、公开水域 GPS 不可靠、真实样本缺失导致的 candidate-only。
- 样本不足冻结：泳池 `validation_required`；公开水域 `candidate_only`；越野 `candidate_only`；徒步最大连续爬升 `candidate_only`；W/kg 不进入正式纪录。
- 日志/API 禁止返回 raw FIT、完整轨迹、真实 GPS 点、路径、设备序列号、账号、token、SQLite schema 或体重历史。
- RCV2-04 验证：reason code 白名单检查输出 `quality_contract_check_ok reason_codes=78 fixture_codes=11`；golden fixture 测试 `4 passed`。

## RCV2-05 Schema、Cache、Route 与回滚冻结结论

- 新增契约：`docs/records_center_v2_rcv2_05_schema_cache_route_contract.md`。
- 继续复用 `career_pb_records` 作为唯一正式纪录事实表，不新建 `records`、`records_history`、`personal_records`、`career_records` 等同义事实表。
- 继续复用 `career_record_events` append-only 事件表和 `career_event_candidates` 候选容器。
- 当前代码已具备 V1 扩展列：`evidence_key/source_mode/sport_scope/previous_record_id/resolver_version/confirmed_at/rejected_at/invalidated_at/decision_source/decided_at/display_metadata_json`。
- V2 计划新增 `career_pb_records` 字段：`record_key/record_family/scope_json/scope_key/scope_hash/range_json/quality_json/metric_value_num/metric_name/catalog_state/rule_version`。
- `pb_type` 保持旧 API 兼容，V2 写入时同步为 `record_key`；`sport_scope` 保留 legacy 简化 scope，但唯一性转向 `scope_hash`。
- Scope canonicalization：只允许 `sport_scope/indoor_scope/power_metric_scope/pool_length_scope/stroke_scope/water_scope/route_key/segment_key`；排序 JSON 后生成 `scope:v2:sha256:*`。
- V2 active 唯一键冻结为 `record_key + source_mode + scope_hash WHERE status='active'`；迁移期保留 V1 `pb_type/source_mode/sport_scope` active 索引。
- V2 evidence key 冻结为 `evidence:v2:{record_key}:{activity_id}:{source_mode}:{scope_hash}:{range_hash}:{metric_hash}:{rule_version}`。
- Curve Cache 表计划：`career_record_curve_cache`；只保存安全 `curve_json/quality_json/input_fingerprint`，是派生缓存，不是 canonical record。
- Route 派生表计划：`career_route_signatures` 和 `career_route_matches`；只保存路线签名摘要、shape hash、覆盖率、重合度等，不保存完整轨迹、真实 GPS 点或可还原路线的高精度 polyline。
- Migration 必须支持 `dry_run=True`，不写库，输出新增表/列/索引、回填计数、冲突计数、阻塞项。
- `RCV2-40` 前不得对真实库 apply V2 migration；真实数据只允许备份和 staging dry-run，除非用户明确批准。
- RCV2-05 验证：schema 契约检查输出 `schema_contract_check_ok`；golden fixture 测试 `4 passed`。

## RCV2-06 API、Catalog 与 ViewModel 冻结结论

- 新增契约：`docs/records_center_v2_rcv2_06_api_viewmodel_contract.md`。
- 通用 API 计划：`get_career_record_catalog`、`get_career_records`、`get_career_record_detail`、`get_career_record_history`、`get_career_record_curve`、`get_career_record_candidates`、`decide_career_record_candidate`、`rebuild_career_records`、`get_career_record_rebuild_status`。
- Catalog 是运动页签、左侧分组、灰态可用性和状态说明的唯一来源；状态包括 `available/candidate_only/validation_required/unavailable/analysis_only/model_only`。
- Records ViewModel 冻结：`metric/improvement/scope/range/quality/status/catalog_state/detail_link`；前端不得计算 improvement、scope label、confidence 或轴方向。
- History ViewModel 冻结：后端提供 `history_summary.total_improvement`、`axis_direction` 和安全 `chart.points`；前端不得自行累计提升或判断 y 轴方向。
- Curve ViewModel 只返回安全降采样/锚点绘图点和 anchors，不返回 raw stream；curve 不反向作为纪录事实。
- Candidate APIs 冻结：用户只能 confirm/reject，不能提交修改后的成绩、距离、时间、scope、range 或 reason。
- Rebuild API 冻结：`dry_run=true` 不写库；没有用户明确批准，真实库不得 `applied=true`。
- V1 `get_career_pb*` 保持为 V2 包装器；`pb_type == record_key`，旧调用方无需理解 `scope_hash`，`detail_link.source="career"` 不变。
- `docs/js_api_contract.json` 后续计划新增/更新项已列出，但 RCV2-06 未修改 JSON。
- API 安全黑名单包括 raw points、轨迹、功率流、路径、SQLite schema、设备序列号、账号 token、体重历史等。
- RCV2-06 验证：API 契约检查输出 `api_contract_check_ok`；golden fixture 测试 `4 passed`。

## RCV2-07 视觉、交互与响应式冻结结论

- 新增契约：`docs/records_center_v2_rcv2_07_visual_interaction_contract.md`。
- 视觉参考取舍：保留深色沉浸、蓝色高亮、左侧纪录卡、右侧大图、底部摘要卡、大圆角和柔和边框；舍弃外部 CDN、表现指数、伪年度数据、头像/通知独立外壳和硬编码 PB 列表。
- 页面定位为 `运动生涯 > 记录中心`，嵌入现有脉图外壳。
- Sport tabs、左侧分组、灰态状态、候选数量全部由 Catalog/ViewModel 驱动。
- 信息架构：顶部运动页签；二级状态页签 `当前纪录/演进/候选`；左侧分组和 record cards；右侧主图、详情和底部摘要。
- 五运动展示规则冻结：跑步 History；骑行 Power Duration Curve/整次活动；徒步海拔和连续爬升候选；游泳泳池 validation-required 与公开水域 candidate-only；越野整次/路线/赛段 candidate-only 与 Pace/GAP analysis-only。
- 状态冻结：Loading、Empty、Partial、Candidate、Validation Required、Rebuilding、Error。
- 响应式断点冻结：桌面、1100px、980px、720px、<520px。
- 禁止前端显示“表现指数”、伪年度 mock、外部 CDN；禁止前端计算纪录事实、Scope、置信度、improvement、history summary 或 axis direction。
- 后续前端实现阶段需清理 V1 冗余：`track.html` 旧 `career-pb-*` 硬编码、未交付骑行 PB 筛选项和 PB-only 文案。
- RCV2-07 验证：视觉契约检查输出 `visual_contract_check_ok`；golden fixture 测试 `4 passed`。

## RCV2-08 测试矩阵、真实数据与发布门禁冻结结论

- 新增契约：`docs/records_center_v2_rcv2_08_test_release_gate_contract.md`。
- 阶段测试矩阵覆盖 `RCV2-09` 至 `RCV2-44`，后续任务应优先从矩阵选择定向测试。
- Golden fixture 策略冻结：fixture 可用于算法边界和回归，但通过不等于真实数据 Verified。
- 真实数据验收计划冻结：`RCV2-40` 前只允许备份、staging 和 dry-run；没有用户批准不得 apply 真实库。
- 用户当前仍要求暂时不要打包；`RCV2-44` 前不得生成、签名、公证或替换发布包。
- Candidate-only 验收规则冻结：candidate-only 不触发 Achievement/Timeline/Overview current，不庆祝。
- 安全扫描黑名单、性能目标、日志观测证据、前端截图验收、macOS/Windows 独立门禁和发布前置条件已冻结。
- Milestone A（`RCV2-00` 至 `RCV2-08`）已完成，可以进入代码化阶段。
- RCV2-08 验证：门禁契约检查输出 `test_release_gate_contract_check_ok`；golden fixture 测试 `4 passed`。

## RCV2-09 Registry 与动态 Catalog 代码化结论

- `RecordDefinition` 已扩展 V2 字段：`family/scope_dimensions/quality_policy/availability_state/availability_reason/standard_duration_sec/dynamic_scope/legacy_category`。
- Registry 白名单已扩展：sport、family、unit、comparison、source_mode、scope_dimensions、availability。
- `RECORD_DEFINITIONS` 已包含多运动 V2 definitions：跑步、骑行功率、骑行整次活动、徒步、泳池、公开水域、越野整次、越野 route/segment。
- 新增 `get_career_record_catalog()` 纯函数，从 Registry 派生 sport tabs、groups、records、axis_direction、availability、scope_dimensions 和 curve/history/candidate 能力。
- V1 `match_record_definition()` 默认仍只匹配 `RUNNING_RECORD_DEFINITIONS`，新运动 definitions 只进入 Catalog，不触发旧 Resolver 写入。
- analysis/model 项未进入 active record definitions；W/kg、eFTP、CP、W′、GAP/NGP 等仍不注册为正式纪录。
- V1 `get_career_pb*` 兼容字段未修改；`detail_link.source="career"` 保持由旧路径维护。
- RCV2-09 验证：Registry/fixture `23 passed, 13 subtests passed`；PB Resolver/API `20 passed`；加宽基线 `49 passed, 13 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-10 Scope schema migration 与 Curve Cache 基础设施结论

- `CAREER_SCHEMA_VERSION` 已提升到 `2026-07-14.records-v2.10`。
- `career_pb_records` 已补齐 V2 字段：`record_key/record_family/scope_json/scope_key/scope_hash/range_json/quality_json/metric_value_num/metric_name/catalog_state/rule_version`。
- `career_record_events` 已补齐 V2 字段：`record_key/scope_hash/scope_key/run_id/decision/reason_codes_json`。
- 已新增派生表：`career_record_curve_cache`、`career_route_signatures`、`career_route_matches`。
- Scope canonicalization/helper 已实现：只接受冻结 scope dimensions，生成 `scope:v2:sha256:*`；legacy rows 会从 `sport_scope` 回填 `scope_json/scope_key/scope_hash`。
- 已新增 V2 active/evidence、事件、候选、curve cache、route signature、route match 索引；V1 索引保留。
- `plan_career_records_v2_schema_migration(conn)` 是只读 dry-run，报告缺失表/列/索引、legacy rows 回填计数和 active scope 冲突。
- Curve Cache 基础设施已实现：`compute_career_record_curve_input_fingerprint()`、`save_career_record_curve_cache()`、`get_career_record_curve_cache()`、`invalidate_career_record_curve_cache()`、`cleanup_career_record_curve_cache_versions()`。
- Curve Cache 只允许 `cycling_power_duration_curve/trail_pace_curve/trail_gap_curve/pool_swim_pace_curve`，写入前拒绝 raw FIT、完整轨迹、原始功率流、本地路径、真实 GPS 点、体重历史等敏感字段。
- Curve Cache、Route Signature、Route Match 仍是派生数据，不是正式纪录事实源，不参与 active 状态迁移。
- RCV2-10 验证：schema/registry `31 passed, 16 subtests passed`；PB API/fixtures `14 passed`；宽回归 `61 passed, 16 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-11 通用 Record Evidence 与 source_mode 扩展结论

- 新增 `RecordEvidence` 模型和 `build_record_evidence()` 纯 helper；Evidence 构建不写库、不切换 active、不创建候选。
- 新增 `canonicalize_record_range()`、`canonicalize_record_quality()`、通用 source_mode 校验和 scope key 派生。
- Evidence key 已按冻结格式生成：`evidence:v2:{record_key}:{activity_id}:{source_mode}:{scope_hash}:{range_hash}:{metric_hash}:{rule_version}`。
- Evidence fingerprint 使用 canonical JSON；同一事实输入顺序变化不改变 key，metric/range/scope 改变会改变 key。
- Evidence 严格绑定 Registry：未知 `record_key` 被拒绝；`source_mode/sport/metric_name/metric_unit` 必须与 `RecordDefinition` 一致。
- 五类 source_mode 已覆盖：`activity_total`、`best_effort_duration`、`best_effort_distance`、`route_total`、`segment`。
- `best_effort_duration/best_effort_distance/segment` 必须携带 Activity 内 range；`route_total` 必须有 `scope.route_key`；`segment` 必须有 `segment_key`。
- Evidence 安全校验拒绝 raw FIT、完整轨迹、原始功率流、本地路径、真实 GPS 点、未脱敏设备标识、账号/token 和体重历史。
- V1 `record_evidence_key()` 与 `build_record_candidate_decision()` 行为未迁移，旧 running PB resolver 兼容测试通过。
- RCV2-11 验证：Evidence/Registry `25 passed, 18 subtests passed`；PB Resolver/API/状态机 `26 passed`；宽回归 `67 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-12 读取与验证提示

## RCV2-12 Scope 感知的状态迁移、事件与候选闭环结论

- 新增 `compare_record_metric()`，按 Registry 支持 `lower_is_better` 与 `higher_is_better`。
- 新增 V2 scoped active 查询，状态迁移以 `record_key + source_mode + scope_hash` 为比较边界。
- 新增 V2 event helper，写入 `record_key/scope_hash/scope_key/run_id/decision/reason_codes_json`，payload 经过 Evidence 安全校验。
- 新增 V2 candidate helper，候选 JSON 只保存安全裁剪后的 Record Evidence，不允许用户改值、range、scope 或 reason。
- 新增 `apply_record_evidence_state()`：支持 `auto_confirm/candidate/ignored`，同 Scope 替代，不同 Scope 共存，tie/未提升只记录 recalculated。
- 新增 `decide_career_record_v2_candidate()`：confirm 使用原始 Evidence 重新比较；reject 后同 evidence 不重复提示。
- V2 写入 `career_pb_records` 时同步 legacy 兼容列和 V2 列；`sport_scope=scope_key` 用于保留旧 V1 active index 兼容。
- `validation_required` 与 `candidate_only` Registry 状态会把高置信 Evidence 降为候选；`analysis_only/model_only/unavailable` 不进入状态机。
- V1 `apply_record_candidate_decision()` 和 `decide_career_pb_candidate()` 未迁移，旧 running PB 状态迁移测试通过。
- RCV2-12 验证：V2/V1 状态机 `13 passed`；Evidence/schema/PB `38 passed, 8 subtests passed`；宽回归 `80 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-13 读取与验证提示

## RCV2-13 增量分发、删除回退、重建与回滚闭环结论

- 新增 `plan_activity_record_v2_dispatch()`、`plan_career_records_v2_rebuild()`、`rebuild_career_records_v2()`。
- Dispatch 默认只分发 `available` definitions；`candidate_only/validation_required` 不自动 apply。
- 修复 sport 归一顺序：`trail_running` 优先归为越野，不被 `RUNNING_SPORT_TYPES` 误归为跑步。
- 新增 `invalidate_career_record_state_for_activity()`：支持 dry-run/apply、record/cache/route 失效、同 Scope fallback 和 savepoint 回滚。
- Activity 失效会处理：active V2 record、`career_record_curve_cache`、`career_route_signatures`、`career_route_matches`。
- fallback 只在同 `record_key/source_mode/scope_hash` 中选择，按 Registry 比较方向排序，并要求 fallback Activity 仍存在且未删除。
- V2 rebuild plan 输出 `run_id/by_sport/by_family/by_reason/summary/items/cancelled`。
- V2 rebuild apply 当前只提供事务壳，不生成多运动 evidence；具体 sport resolver 从 RCV2-15 开始接入。
- RCV2-13 验证：V2 rebuild/state `12 passed`；V1 rebuild/lifecycle/incremental `14 passed`；宽回归 `99 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-14 读取与验证提示

- 默认读取本摘要、`RCV2-14` 任务条目、`RCV2-06` API/ViewModel 契约、`RCV2-12/13` 完成报告和现有 `get_career_pb*` API 实现。
- 目标是实现通用 Records 只读 API 与 V1 兼容包装器，并更新 `docs/js_api_contract.json`。
- 通用 API 必须只返回 ViewModel 和安全 envelope，不暴露 raw evidence payload、schema、路径、轨迹、功率流或设备标识。
- V1 `get_career_pb*` 返回兼容；旧前端继续可用。

## RCV2-14 通用 Records API 与 V1 兼容包装器结论

- 通用 Records API 已具备：`get_career_records`、`get_career_record_detail`、`get_career_record_history`、`get_career_record_curve`、`get_career_record_candidates`、`decide_career_record_candidate`、`rebuild_career_records`、`get_career_record_rebuild_status`。
- `get_career_record_catalog` 继续由 V2 Registry/Catalog 派生，作为前端运动页签、分组、灰态和能力展示唯一来源。
- Records ViewModel 由后端生成 `metric/improvement/scope/range/quality/status/catalog_state/detail_link`，前端不得补算或推断。
- History ViewModel 由后端生成 `history_summary`、`axis_direction`、`chart.points`；前端不得自行累计提升或决定 y 轴方向。
- Curve API 只返回派生缓存安全 `points/anchors` 与哈希 `input_fingerprint`；不返回 raw FIT、完整轨迹、原始功率流或可还原路线的路径数据。
- Candidate API 只允许 confirm/reject，用户不得提交修改后的成绩、距离、时间、scope、range 或 reason。
- `rebuild_career_records()` 默认 `dry_run=True`；没有用户明确批准不得对真实库 apply。
- V1 `get_career_pb*` 兼容路径保持可用，`career_pb_records/career_record_events/career_event_candidates` 继续作为事实/事件/候选容器。
- `docs/js_api_contract.json` 中 9 个 RCV2-14 API 标记已复核：只读接口 `readonly=true`；`decide_career_record_candidate` 和 `rebuild_career_records` 为 `high_risk=true`。
- RCV2-14 验证：API/PB 定向测试 `16 passed`；Records V2 contract 校验 `contract_ok True missing [] wrong_flags []`。

## RCV2-15 读取与验证提示

- 默认读取本摘要、`RCV2-15` 任务条目、`RCV2-03/04/06/11/14` 结论、`tests/fixtures/records_center_v2/golden_manifest.json` 中骑行功率相关 cases，以及现有 FIT/activity power 字段读取路径。
- 目标是实现骑行功率流规范化与质量检测，不生成正式骑行功率纪录，不写真实库。
- 必须区分 `0W` 有效滑行与功率缺失；缺失/断点/尖峰/采样异常/e-bike 混入必须产生稳定 reason code。
- 输出必须是安全摘要和质量结果；不得向 API、日志或 completion report 写入 raw FIT、完整 points、原始 power stream、本地路径、设备序列号或体重历史。
- 验证优先选择骑行 golden fixtures、功率质量单测、Registry/Evidence 兼容测试和 V1 PB 兼容测试。

## RCV2-15 骑行功率流规范化与质量检测结论

- 新增 `normalize_cycling_power_stream_for_records()` 纯函数，输出内部 `clean_points` 与安全 `quality_summary`，不写库、不创建候选、不切换 active。
- 支持时间字段 `t/time_sec/elapsed_sec/elapsed_time_sec/timestamp/time`，支持功率字段 `power_w/power/watts/enhanced_power/Power`。
- 时间归一为 Activity-relative `t_sec`；相同输入重复运行输出稳定。
- `0W` 保留为有效滑行值；缺失功率、负值、非数值和无效时间戳不会被当作 0W。
- 非 1Hz 使用相邻采样 interval 做 time-weighted average；gap 阈值由配置 `max_gap_sec` 与采样中位间隔倍数共同决定，避免干净低频采样误降级。
- 断点、缺失样本、尖峰、无效时间和低覆盖率输出稳定 reason codes：`missing_power_stream_sample`、`power_stream_gap`、`power_spike_detected`、`duration_semantics_unknown`、`plausibility_outlier`、`power_stream_missing`。
- e-bike 输出 `ebike_scope_excluded`，`sport_scope=ebike_excluded`，不会进入普通骑行功率纪录。
- 安全质量摘要不包含 raw point list、raw FIT、路径、设备序列号、storage ref 或体重历史；`power_source` 标签会清洗敏感内容。
- RCV2-15 验证：定向/fixture `8 passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `61 passed, 18 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-16 读取与验证提示

- 默认读取本摘要、`RCV2-16` 任务条目、`RCV2-10` Curve Cache helper、`RCV2-15` 完成报告与 `tests/test_career_record_cycling_power_stream.py`。
- 目标是实现单活动 Power Duration Curve resolver 和 cache integration，不写 active record。
- 必须复用 `normalize_cycling_power_stream_for_records()` 的 `clean_points/quality_summary`，不得绕过 0W/缺失/gap/尖峰质量门禁。
- 固定窗口至少覆盖 5s、30s、1m、5m、20m、60m；活动短于窗口必须返回 `activity_shorter_than_window`，不得造点。
- 每个曲线锚点必须包含 value、duration、activity-relative range、quality state/reason codes；窗口不得跨 gap。
- 使用 `compute_career_record_curve_input_fingerprint()`、`save_career_record_curve_cache()` 与 `get_career_record_curve_cache()`；缓存是派生数据，不能反向成为正式纪录事实。
- 验证优先选择 RCV2-15 功率单测、新增 curve/cache 测试、V2 rebuild/API/Evidence 兼容测试。

## RCV2-16 单活动功率持续时间曲线与缓存结论

- 新增 `resolve_cycling_power_duration_curve()`，默认计算 5s、30s、60s、300s、1200s、3600s 固定窗口。
- Resolver 复用 RCV2-15 `clean_points/quality_summary`，基于 step intervals 做精确 time-weighted integration。
- 窗口不得跨 gap；活动短于窗口返回 unavailable anchor 和 `activity_shorter_than_window`。
- tie 选择更早 activity-relative range。
- 每个 anchor 输出 `duration_sec/value/unit/range/quality`；曲线输出 `anchors/points/axis/scope`，其中 points 可由 anchors 派生。
- Cache fingerprint 使用安全 stream hash、scope、algorithm version 和 rule version；stream hash 只保存哈希，不保存原始功率点。
- `career_record_curve_cache` 中只保存安全 anchors/quality；由于 cache 安全规则禁止 `points` 键，落库时移除 points，命中后由 resolver 从 anchors 派生展示 points。
- RCV2-16 不写 active record、不创建候选、不调用状态机。
- RCV2-16 验证：power curve/stream `8 passed`；schema/cache/API/rebuild `23 passed, 3 subtests passed`；加宽回归 `65 passed, 18 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-17 读取与验证提示

- 默认读取本摘要、`RCV2-17` 任务条目、`RCV2-12` 状态迁移结论、`RCV2-15/16` 完成报告与 `tests/test_career_record_cycling_power_curve.py`。
- 目标是把 Power Duration Curve anchors 转换为 `RecordEvidence` 并接入 `apply_record_evidence_state()`，开始产生正式 V2 纪录/候选。
- 必须只处理 Registry 中六个固定锚点：`cycling_power_5s/30s/1m/5m/20m/60m`；不得实现 1s，不得写 eFTP/CP/W′。
- Evidence 必须带 `range_data`、`scope`、`quality`、`source_mode=best_effort_duration`、`metric_name=power_w`、`metric_unit=watts`。
- 质量不足、candidate-only 或 Registry 限制必须进入候选或 ignored；不得绕过 RCV2-04 阈值。
- 增量/重建/重复导入必须幂等；不同 scope 不互相替代。
- 验证优先选择新增 cycling power resolver 测试、V2 state/rebuild、Evidence、Registry 和 V1 PB 兼容测试。

## RCV2-17 骑行固定功率锚点正式纪录 Resolver 结论

- 新增 duration 到 record key 映射：5s、30s、60s、300s、1200s、3600s 分别对应 `cycling_power_5s/30s/1m/5m/20m/60m`。
- 新增 `build_cycling_power_record_evidences()`，从 RCV2-16 curve anchors 生成安全 `RecordEvidence`。
- 新增 `apply_cycling_power_duration_records()`，默认 `dry_run=True`；显式 `dry_run=False` 时通过 `apply_record_evidence_state()` 写入 V2 状态机。
- Evidence 固定 `source_mode=best_effort_duration`、`metric_name=power_w`、`metric_unit=watts`，并携带 activity-relative `range_json`。
- 高质量 anchor 进入 `auto_confirm`；带缺失、gap、尖峰等 reason code 的 anchor 进入 candidate；e-bike/不可用 anchor 不生成正式 evidence。
- higher-is-better 替代、tie unchanged、重复导入幂等、候选创建和同 scope fallback promotion 已由内存库测试覆盖。
- 修正 Records API 安全扫描：禁止敏感字段键和路径/schema 值，但允许冻结 reason code（如 `power_stream_gap`）作为普通字符串值出现。
- RCV2-17 验证：定向 `13 passed`；状态机/API/PB `34 passed, 5 subtests passed`；加宽回归 `82 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-18 读取与验证提示

- 默认读取本摘要、`RCV2-18` 任务条目、`RCV2-01` 真实数据审计中关于体重字段的结论、`RCV2-03/04/17` 结论和现有 Activity 安全字段读取路径。
- 目标是实现骑行整次活动纪录：最长距离、最大爬升、最长 elapsed time、最大机械功；同时冻结 W/kg 门禁。
- W/kg 不在当前 Registry 中注册为 active record；无活动日期附近可靠历史体重时不得创建 W/kg fact、candidate 或 active。
- 不得使用当前体重回填历史活动。
- 机械功优先从功率流积分或可信汇总计算；质量不明时只能 candidate/validation_required。
- 室内骑行无距离/爬升时应 not applicable，不填 0 纪录。
- 不实现最快均速核心纪录。
- 验证优先选择新增 cycling total resolver 测试、RCV2-17 功率测试、V2 state/API/Evidence 和 V1 PB 兼容测试。

## RCV2-18 骑行 W/kg 门禁与整次活动纪录结论

- 新增 `resolve_cycling_wkg_gate()`；无活动日期附近可靠历史体重时返回 unavailable 和 `historical_weight_missing`，不创建 W/kg fact/candidate/active。
- 即使存在可靠历史体重，当前也只返回 gate available；因 Registry 未开放 W/kg active record，`evidence_created=false`。
- 新增 `build_cycling_activity_total_record_evidences()` 和 `apply_cycling_activity_total_records()`，默认 dry-run。
- 已支持 `cycling_longest_distance`、`cycling_max_ascent`、`cycling_longest_elapsed_time`、`cycling_max_work`。
- 室内无距离/爬升时返回 `not_applicable_indoor_metric_missing`，不填 0 纪录。
- 机械功优先从 RCV2-15 功率流 time-weighted 积分得到；无功率流时可使用可信汇总并降级为 `work_integration_quality_unknown`。
- `cycling_max_work` 因 Registry `validation_required` 会被 V2 状态机降为 candidate，不进入 active。
- e-bike 整次活动纪录全部排除。
- RCV2-18 验证：定向 `10 passed`；状态机/API/PB `23 passed`；加宽回归 `87 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-19 读取与验证提示

- 默认读取本摘要、`RCV2-19` 任务条目、`RCV2-06/14` API 契约、`RCV2-17/18` 完成报告、`docs/js_api_contract.json` Records V2 API 条目和骑行相关测试。
- 目标是补齐骑行只读表面和测试闭环，不新增写接口。
- Catalog 必须区分 `cycling_power` 与 `cycling_activity_total` 分组，并表达 `cycling_max_work` validation required 与 W/kg unavailable。
- API/ViewModel 必须能展示当前纪录、历史、详情、PDC curve、室内外 scope、W/Wkg 状态和无功率/部分功率状态。
- 无逐点功率活动不得进入 PDC；model estimates 必须带模型标签且不得成为 active record。
- 验证优先选择 RCV2-17/18 tests、Records API contract、安全扫描和 V1 PB 兼容测试。

## RCV2-19 骑行 Catalog、API、Curve ViewModel 与测试闭环结论

- Catalog sport-level 新增 `capabilities`，骑行可表达 PDC、整次活动纪录、W/kg gate、model-only 估计和 scope dimensions。
- `power_duration_curve` capability 使用 `requires_point_power` 表达逐点功率需求，避免把 `power_stream` 作为 payload key。
- `wkg` capability 当前为 `unavailable`，`creates_record=false`，reason codes 包含 `historical_weight_missing` 和 `wkg_registry_not_enabled`。
- `model_estimates` capability 为 `model_only`，包含 eFTP、CP、W′、MAP、PMax，且 `creates_record=false`。
- `docs/js_api_contract.json` 已更新 `get_career_record_catalog` returns/description，明确 capabilities 是 Catalog 的一部分。
- 新增骑行 API surface 测试覆盖 Catalog、Records、Detail、History、Curve、Candidate 和安全字段扫描。
- RCV2-19 验证：定向 `12 passed`；contract/API/PB/Evidence `22 passed, 5 subtests passed`；加宽回归 `89 passed, 21 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-20 读取与验证提示

- 默认读取本摘要、`RCV2-20` 任务条目、`RCV2-03/04/11` 结论、hiking/walking/mountaineering/trail_running 相关 Registry definitions 和 Activity sport normalization 代码。
- 目标是实现 Hiking Fact Adapter 与 activity-total evidence，不处理连续爬升。
- 必须严格分离 `hiking`、`walking`、`mountaineering`、`trail_running`；标题只能作为辅助证据，不能单独改变类型。
- 生成 evidence：`hiking_longest_distance`、`hiking_max_ascent`、`hiking_longest_elapsed_time`、`hiking_max_altitude`。
- 时间/单位/来源不明时降级为 candidate；错误类型不得自动成为正式纪录。
- 验证优先选择新增 hiking fact tests、Evidence/State/API/PB 兼容测试。

## RCV2-20 徒步运动边界与 Activity-total Evidence 结论

- `_activity_sport_for_record_dispatch()` 已收紧：`hiking/hike/trekking` 才归为 hiking；walking、mountaineering、trail_running 不再混入 hiking。
- 新增 `build_hiking_activity_total_record_evidences()` 和 `apply_hiking_activity_total_records()`，默认 dry-run。
- 已生成四个 activity-total evidence：`hiking_longest_distance`、`hiking_max_ascent`、`hiking_longest_elapsed_time`、`hiking_max_altitude`。
- 标题不参与类型提升；title 包含 hiking 也不能把 walking/mountaineering/trail_running 变成 hiking。
- `duration` fallback 会降级为 candidate，reason code 为 `duration_semantics_unknown`。
- RCV2-20 验证：定向 `9 passed, 3 subtests passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `93 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-21 读取与验证提示

- 默认读取本摘要、`RCV2-21` 任务条目、`RCV2-04` 海拔 reason codes、`RCV2-20` 完成报告和 golden fixture 中 `hiking_elevation_spike_single_climb`。
- 目标是实现海拔质量与最大连续爬升 resolver；最高海拔/累计爬升质量也需带 reason codes。
- 必须实现平滑、尖峰、断点、轨迹覆盖检测和连续爬升起止 range。
- 无轨迹时不得生成 `hiking_max_single_climb`。
- 不能用整次累计爬升冒充最大连续爬升。
- 异常高度只能 candidate/ignored。
- 验证优先选择新增 elevation/climb tests、hiking activity-total tests、Evidence/State/API/PB 兼容测试。

## RCV2-21 海拔质量与最大连续爬升 Resolver 结论

- 新增 `resolve_hiking_elevation_climb()`，支持海拔点、时间、距离字段解析。
- 采用孤立尖峰/谷值检测：前后方向相反且两侧跳变超过阈值；已避免把正常陡升误判为尖峰。
- 剔除尖峰后计算最大连续爬升，并输出 `gain_m/start/end`。
- 新增 `build_hiking_single_climb_record_evidence()`，生成 `hiking_max_single_climb` evidence，range 包含时间和距离起止。
- 新增 `apply_hiking_single_climb_record()`，默认 dry-run；因 Registry `candidate_only`，apply 后创建候选，不进入 active。
- 无轨迹时返回 `single_climb_range_missing`，不会用整次累计爬升冒充最大连续爬升。
- RCV2-21 验证：定向 `7 passed, 3 subtests passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `96 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-22 读取与验证提示

- 默认读取本摘要、`RCV2-22` 任务条目、`RCV2-12/14/20/21` 结论、徒步相关 tests 和 Catalog/API helper。
- 目标是完成徒步五项纪录的只读表面和状态闭环：距离、累计爬升、历时、最高海拔、最大连续爬升。
- `hiking_max_single_climb` 仍为 candidate-only；不得显示为 current active。
- Catalog 只展示 hiking，不展示 walking/mountaineering 占位。
- 必须验证当前/历史/详情 ViewModel、候选、事件和删除回退。
- 不实现通用最快 5K/10K 或 VAM 正式纪录。

## RCV2-22 徒步正式纪录、Catalog、API 与测试闭环结论

- 新增徒步 API surface 测试，覆盖 Catalog、Records、Detail、History、Candidates 和 fallback。
- Catalog 只展示 `hiking`，不展示 walking/mountaineering 占位。
- 四项 activity-total 徒步纪录进入 current active：距离、累计爬升、历时、最高海拔。
- `hiking_max_single_climb` 保持 candidate-only，不进入 current active。
- 删除 active activity 后，同 scope superseded fallback 可恢复。
- RCV2-22 验证：定向 `9 passed, 3 subtests passed`；状态机/API/PB `23 passed`；加宽回归 `98 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-23 读取与验证提示

- 默认读取本摘要、`RCV2-23` 任务条目、`RCV2-03/10` schema/scope 结论、swimming Registry definitions 和 golden fixtures 中 pool/open-water cases。
- 目标是补齐游泳 canonical facts、Pool Scope 与 schema/migration dry-run。
- 必须持久化/表达 canonical pool length，不得在正式纪录路径默认 25m。
- 必须规范化 `water_scope/pool_length_scope/stroke_scope`，并区分 pool/open_water。
- 必须规范化 Length/Lap active time、rest、distance 和 stroke。
- SWOLF 不成为正式纪录；码制泳池不在首发。
- 无 pool length 不自动确认。

## RCV2-23 游泳 canonical facts、Pool Scope 与 schema 补齐结论

- 新增游泳 canonical activity columns plan：water scope、pool length、pool length scope、stroke scope、facts quality JSON。
- 新增 schema dry-run/apply helper；默认 dry-run，不写真实库。
- 新增 `normalize_swim_canonical_facts()`，规范化 pool/open-water、pool length、stroke、Length/Lap elapsed/rest/distance/stroke。
- 缺 pool length 不默认 25m；码制泳池返回 unsupported；SWOLF 不进入正式纪录事实。
- RCV2-23 验证：定向 `8 passed`；Schema/Registry/API/PB `47 passed, 16 subtests passed`；加宽回归 `102 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-24 读取与验证提示

- 默认读取本摘要、`RCV2-24` 任务条目、`RCV2-04/11/23` 结论、pool swimming Registry definitions 和 golden fixture 中 pool swim cases。
- 目标是从 canonical lengths 生成 50m、100m、200m、400m、800m、1500m best-effort evidence。
- 必须按 pool length 精确组合距离，不使用 `±3%`。
- 休息中断窗口；转身计入游程。
- V2 首发只自动确认显式 freestyle；mixed/unknown stroke 只能 candidate。
- 每条 evidence 必须保存 Activity 和 Length/Lap 范围。

## RCV2-24 泳池 Length/Lap 最佳努力 Resolver 结论

- 新增 pool swim best-effort evidence builder 和默认 dry-run apply wrapper。
- 目标距离按 pool length 精确组合，不使用容差。
- 休息会中断窗口；活动汇总时间不能替代泳段。
- Evidence 携带 `length_start/length_end/lap_count/distance_m` 和 `water_scope/pool_length_scope/stroke_scope`。
- 缺 pool length 不生成 evidence，不默认 25m。
- 因 Registry `validation_required`，泳池 evidence apply 后进入候选，不进入 active。
- RCV2-24 验证：定向 `7 passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `105 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-25 读取与验证提示

- 默认读取本摘要、`RCV2-25` 任务条目、`RCV2-04/11/23` 结论、open-water Registry definitions 和 golden fixture `open_water_750m_boundary_and_gps_jump`。
- 目标是实现公开水域整次活动标准距离和 longest distance/elapsed evidence。
- 标准距离匹配使用包含边界的 `±5%`，比较主值为 elapsed time。
- 公开水域 V2.0 不做活动内 best-effort 分段。
- GPS 缺口、跳点、手动距离和来源不明最多 candidate。
- 不与泳池混排。

## RCV2-25 公开水域标准距离与整次活动纪录 Resolver 结论

- 新增公开水域标准距离 evidence builder 和默认 dry-run apply wrapper。
- 标准距离包括 750m、1500m、1900m、3800m、5K、10K，整次活动距离 `±5%` 匹配，边界包含。
- 比较主值为 elapsed time；另生成 longest distance 和 longest elapsed evidence。
- GPS 跳点/手动来源会降级为 `open_water_gps_unreliable`。
- 公开水域与泳池严格分离；不做活动内 best-effort 分段。
- 因 Registry candidate-only，apply 后进入候选，不进入 active。
- RCV2-25 验证：定向 `7 passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `108 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-26 读取与验证提示

- 默认读取本摘要、`RCV2-26` 任务条目、`RCV2-12/14/24/25` 结论、swim tests 和 Catalog/API helper。
- 目标是完成泳池/公开水域只读表面和状态闭环。
- Pool 仍应 validation-required；无真实泳池样本时不能 active。
- Open-water 仍 candidate-only；真实样本不强写库。
- ViewModel 必须输出 water scope、pool length scope、stroke scope、距离和质量标签。
- SWOLF 不成为正式纪录；未知泳姿不自动进入 freestyle PB。

## RCV2-26 游泳正式纪录、Catalog、API 与测试闭环结论

- 新增游泳 API surface 测试，覆盖 pool/open-water Catalog 和 candidates。
- pool records 保持 `validation_required`，open-water records 保持 `candidate_only`。
- pool/open-water 均不产生 active current records。
- 候选 ViewModel 包含 water/pool length/stroke scope。
- SWOLF 不成为正式纪录，未知泳姿不自动进入 freestyle PB。
- RCV2-26 验证：定向 `8 passed`；Contract/API/PB/Evidence `22 passed, 5 subtests passed`；加宽回归 `110 passed, 24 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-27 读取与验证提示

- 默认读取本摘要、`RCV2-27` 任务条目、`RCV2-03/11/20/21` 结论、trail_running Registry definitions 和 Activity sport dispatch。
- 目标是严格识别 trail_running，并生成距离、爬升、历时、海拔、连续爬升 evidence。
- 必须分离 road_running、trail_running、hiking、mountaineering；标题只作弱证据。
- 复用 RCV2-21 海拔/连续爬升质量服务。
- 无真实 trail 样本时使用 fixture 并保持 candidate-only/validation 状态。

## RCV2-27 越野跑分类与整次活动纪录 Evidence 结论

- 新增 trail activity-total evidence builder 和默认 dry-run apply wrapper。
- 支持五项整次 evidence：距离、爬升、历时、最高海拔、最大连续爬升。
- trail 分类只接收 `trail_running/trail_run`，road running、hiking、mountaineering 均排除；标题不提升类型。
- 连续爬升复用 RCV2-21 海拔质量服务并携带 range。
- 因 Registry candidate-only，apply 后进入候选，不进入 active。
- RCV2-27 验证：定向 `12 passed, 6 subtests passed`；Evidence/API/PB `22 passed, 5 subtests passed`；加宽回归 `113 passed, 27 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-28 读取与验证提示

- 默认读取本摘要、`RCV2-28` 任务条目、`RCV2-04/10/27` 结论、route signature schema/helper 和 golden fixture trail route cases。
- 目标是实现隐私安全 route signature 与同路线/方向匹配。
- 必须配置化 100m、5%、95%、85% 等阈值。
- 不能保存完整轨迹、真实 GPS 点或可还原路线 polyline。
- 所有 route PR 相关结果 candidate-only，不自动确认。

## RCV2-28 Route Signature 与同路线匹配结论

- 新增 `build_trail_route_signature()`：从 Activity track facts 派生 hashed route signature，只保留 route/direction key、起终点 anchor hash、shape hash、sample/corridor hash、距离和质量摘要。
- 新增 `match_trail_route_signatures()`：支持同向、反向、loop/out-and-back、端点未知、长度误差、覆盖率和 corridor overlap 判定。
- 阈值已配置化：起终点 `100m`、长度误差 `5%`、轨迹覆盖率 `95%`、corridor overlap `85%`。
- 新增 `build_trail_route_candidate_plan()`：只输出 candidate-only 匹配计划，不接入 active record。
- 新增 `save_career_route_signature()`、`get_career_route_signature()`、`save_career_route_match()`：写入既有派生表，保存前校验禁止 raw points、GPS 点、真实经纬度、polyline、路径和设备/账号类敏感字段。
- 同向同路线返回 `decision=candidate` 且带 `real_data_sample_missing`；反向返回 `route_direction_mismatch`；低重合返回 `route_match_low_overlap`；部分覆盖/短路线返回端点、长度或重合 hard-block。
- RCV2-28 验证：定向 `13 passed, 3 subtests passed`；schema/rebuild/API/PB 兼容 `33 passed, 3 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-29 读取与验证提示

- 默认读取本摘要、`RCV2-29` 任务条目、`RCV2-12/28` 结论、`RecordEvidence`/状态机和 route signature/match helper。
- 目标是把 route total、segment、climb segment 转成越野 PR evidence，并接入 Scope 状态闭环。
- 必须保持 route/segment PR candidate-only；无真实样本时不得开放正式路线 PR。
- segment evidence 必须携带 Activity 内 range；route total 必须携带 `scope.route_key`。

## RCV2-29 越野赛段 PR 与 Scope 状态闭环结论

- 新增 `build_trail_route_record_evidences()`：只接受 `decision=candidate` 且方向为 `same/loop` 的 route match，生成 `trail_route_best_time` route_total evidence。
- 新增 `build_trail_segment_record_evidences()`：普通 segment 生成 `trail_segment_best_time`，climb/uphill segment 生成 `trail_climb_segment_best_time`。
- route total 使用 whole-activity elapsed time；segment 使用 `elapsed_time_sec/duration_sec` 或 `end_sec-start_sec`；不使用 moving time。
- route total scope 必须含 `route_key`；segment/climb segment scope 必须含 `segment_key`，range 必须含 Activity 内 `start_sec/end_sec/duration_sec/segment_key`。
- 同一批 resolver 输出按 `record_key + source_mode + scope_hash` 只保留 elapsed time 最小的 evidence，保证同 Scope 批内最快唯一。
- 新增 `apply_trail_route_segment_records()`：默认 dry-run；apply 时仍走既有状态机，因 registry 为 `candidate_only` 只进候选，不自动写 active。
- RCV2-29 验证：定向 `23 passed`；兼容 `27 passed, 5 subtests passed`；`career_backend.py` py_compile 通过。

## RCV2-30 读取与验证提示

- 默认读取本摘要、`RCV2-30` 任务条目、`RCV2-10/27/29` 结论和 curve cache helper。
- 目标是冻结越野 Pace/GAP Curve 的 analysis-only 边界。
- Pace/GAP Curve 可用于前端分析和对比，但不得写正式纪录、候选纪录或 route/segment PR。
- Curve cache 不得保存 raw track、GPS 点、完整路径或可还原 polyline。

## RCV2-30 越野 Pace/GAP Curve 分析边界结论

- 新增 `resolve_trail_pace_gap_activity_curve()`：单 Activity 计算 1K、3K、5K、10K、20K、30K、50K pace/GAP anchors，不足距离输出 `activity_shorter_than_window`。
- 新增 `build_trail_pace_gap_curve_viewmodel()`：支持 `all`、`season`、`last_42_days` 时间范围，跨 Activity 按 anchor 选择 pace 最优分析结果。
- 新增 `save_trail_pace_gap_curve_cache()`：写入 `trail_pace_curve` 与 `trail_gap_curve` 派生缓存，payload 只含 anchors/summary/gap_algorithm/quality。
- GAP ViewModel 固定暴露算法版本、海拔输入状态和 limitations：analysis-only、不建模技术路况、坡度修正为近似分析。
- 未新增 `RecordDefinition`；`trail_pace_curve` / `trail_gap_curve` 不能构造 record evidence，不能进入 active record。
- RCV2-30 验证：定向 `36 passed, 16 subtests passed`；兼容 `21 passed`；`career_backend.py` py_compile 通过。

## RCV2-31 读取与验证提示

- 默认读取本摘要、`RCV2-31` 任务条目、`RCV2-14/29/30` 结论、Records API/Catalog helper 和 golden fixtures。
- 目标是整合越野整次、route/segment 和 Pace/GAP analysis 到 Catalog/API/fixture 闭环。
- Catalog 必须区分：整次纪录 candidate-only、route/segment candidate-only、Pace/GAP analysis-only。
- 没有真实越野样本时 route/segment 不开放正式可用态。

## RCV2-31 越野 Catalog/API/fixture 闭环结论

- Trail Catalog capabilities 已区分：`activity_total_records=candidate_only`、`route_segment_pr=candidate_only`、`pace_gap_curve=analysis_only`。
- `route_segment_pr` 明确 uses elapsed time、不使用 moving time；要求 route signature、same direction。
- 新增 `get_trail_route_comparison_viewmodel()` 和 pywebview wrapper `get_trail_route_comparison()`：只返回 `career_route_matches` 安全摘要，不返回 route signature 原文或路线数据。
- route comparison summary 固定 `verified_real_data=false`，避免 fixture 通过被前端误展示为真实验收。
- `docs/js_api_contract.json` 已新增 `get_trail_route_comparison`，Catalog 描述已补充越野 capabilities 约束。
- RCV2-31 验证：定向 `14 passed`；兼容 `39 passed, 13 subtests passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-32 读取与验证提示

- 默认读取本摘要、`RCV2-32` 任务条目、`RCV2-07/14/19/22/26/31` 结论、`track.html` 中 Records Center 前端入口和现有前端测试。
- 目标是多运动页面外壳、Catalog 页签与当前纪录视图。
- 前端必须消费后端 Catalog/API，不得硬编码运动纪录列表、availability、candidate-only 或 analysis-only 状态。
- 前端不得计算纪录事实、scope、confidence、improvement、axis direction 或曲线事实。

## RCV2-32 多运动页面外壳与当前纪录视图结论

- `track.html` 已新增 Records Center V2 shell：`career-records-v2-shell`、sport tabs、view tabs、group list、current list。
- 新增前端 normalize/render/load：`normalizeCareerRecordCatalog()`、`normalizeCareerRecordV2()`、`normalizeCareerRecordCandidateV2()`、`renderCareerRecordsCenter()`、`loadCareerRecordsCenter()`。
- V2 shell 消费 `get_career_record_catalog`、`get_career_records`、`get_career_record_candidates`；候选不会被渲染为当前纪录。
- 前端只展示后端 `metric.display`、`scope.labels`、`improvement.display`、`catalog_state`，不计算事实、提升、可用性、置信度或轴方向。
- 已移除旧记录筛选中的未实现 `cycling_avg_speed / 最快均速` 占位。
- RCV2-32 验证：前端定向 `26 passed`；API surface 兼容 `15 passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-33 读取与验证提示

- 默认读取本摘要、`RCV2-33` 任务条目、`RCV2-07/19/22/26/31/32` 结论、Records V2 shell 和 curve/history/route comparison API。
- 目标是多运动演进图、功率/Pace Curve 与路线对比前端。
- 前端只消费 `get_career_record_history`、`get_career_record_curve`、`get_trail_route_comparison` ViewModel；不得从曲线/DOM/ECharts 推导正式纪录。

## RCV2-33 多运动演进图、功率/Pace Curve 与路线对比结论

- `track.html` 已新增 Records Center V2 analysis panel，支持历史演进、curve anchors 和越野路线对比摘要。
- 当前纪录卡可被选择进入分析面板；支持键盘触发和空状态提示。
- 新增图表生命周期管理：按 container 复用/销毁 ECharts 实例，窗口 resize 时安全重绘。
- 前端仅调用 `get_career_record_history`、`get_career_record_curve`、`get_trail_route_comparison`；曲线/路线对比只作为分析视图，不反向生成纪录事实。
- 历史图使用后端 `axis_direction` 控制方向；前端不自行判断 higher/lower。
- Pace/GAP 和 route comparison 明确显示分析/候选语义，不展示为正式 PB。
- 所有图表均提供可访问的列表替代视图，覆盖单节点、空曲线和加载失败状态。
- RCV2-33 验证：前端图表定向 `10 passed`；API 兼容 `9 passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-34 读取与验证提示

- 默认读取本摘要、`RCV2-34` 任务条目、`RCV2-14/32/33` 结论、Records V2 detail/candidate API、Activity detail 跳转函数和 `track.html` 当前 Records V2 shell。
- 目标是统一多运动详情、候选确认/拒绝和来源 Activity 回跳体验。
- 详情必须消费 `get_career_record_detail` ViewModel；前端不得计算前一纪录、提升、Scope、质量、range 或 Activity 来源。
- 候选必须消费 `get_career_record_candidates`，确认/拒绝只调用 `decide_career_record_candidate` 并传递候选 ID/decision，不允许提交修改后的值、距离、时间、scope、range、reason 或 evidence。
- Activity Detail 跳转继续使用 `detail_link.source="career"`，不得从 DOM 或候选内容拼接真实来源。
- 模型、analysis curve、cache 和 route comparison 不进入候选确认/拒绝操作。
- 验证优先选择新增详情/候选前端测试、现有 Records V2 shell/chart 测试、Records V2 API 和 PB 兼容测试。

## RCV2-34 纪录详情、候选处理与 Activity 回跳结论

- `track.html` 已新增 V2 detail card，并在当前纪录选中时调用 `get_career_record_detail({ record_id })`。
- detail card 展示后端 ViewModel 中的 `metric/improvement/scope/source_mode/quality/range/activity_summary`；前端不计算事实、提升、质量或 Scope。
- Range 只按白名单字段展示安全摘要：时间范围、距离范围、泳段/Lap、segment/route key 等；不展示 raw stream、track、GPS、路径或 schema。
- 当前纪录卡新增“查看详情”和“来源 Activity”；Activity 回跳继续使用后端 `detail_link.source="career"`。
- 候选卡展示候选值、Scope、置信度、reason codes 和来源 Activity；候选不会进入 current record。
- 候选确认/拒绝只调用 `decide_career_record_candidate({ candidate_id, decision })`，提交期间禁用按钮，成功刷新 Records Center，失败局部反馈。
- 旧 V1 PB detail/candidate 面板保持兼容；V2 新路径未调用旧 `decide_career_pb_candidate`。
- RCV2-34 验证：前端详情/候选定向 `15 passed`；API/PB 兼容 `16 passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-35 读取与验证提示

- 默认读取本摘要、`RCV2-35` 任务条目、`RCV2-07/32/33/34` 结论、Records Center V2 shell/detail/candidate CSS/JS 和现有前端静态测试。
- 目标是补齐页面状态、响应式、无障碍和视觉验收证据。
- 必须覆盖 Loading、Empty、Partial、Candidate、Rebuilding、Error、Validation Required 等状态的可验证渲染入口。
- 响应式重点：1440、1100、980、720、窄窗口；不得用隐藏溢出来掩盖布局问题。
- 无障碍重点：键盘、焦点、aria-live、aria-label、图标名称、reduced motion 和可访问列表 fallback。
- 若无法实际生成截图，应记录环境限制并提供代码级/静态可复验替代证据。
- 验证优先选择新增响应式/a11y 前端测试、RCV2-32/33/34 前端测试，以及必要的 API 兼容测试。

## RCV2-35 页面状态、响应式、无障碍与视觉截图结论

- `track.html` 已新增 Records V2 状态条 `career-record-status-strip`。
- 状态覆盖：Loading、Empty、Partial、Candidate、Rebuilding、Error、Validation Required。
- 响应式新增 1100、980、720、520 断点；窄屏下 layout 单列、group selector 横向选择、analysis/detail 降列、超窄屏按钮满宽。
- 无障碍新增：状态条 `aria-live`、group cards 键盘选择、操作按钮 `aria-label`、候选提交 `aria-busy`、reduced motion。
- 视觉验收记录写入 `docs/records_center_v2_rcv2_35_visual_acceptance.md`；本轮 in-app browser 因安全策略阻止访问本地 `file://` 页面，未生成截图，已记录限制与替代证据。
- 新增 `tests/test_career_records_v2_responsive_a11y_frontend.py`。
- RCV2-35 验证：前端状态/响应式/a11y 定向 `21 passed`；API 兼容 `6 passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-36 读取与验证提示

- 默认读取本摘要、`RCV2-36` 任务条目、`RCV2-12/14/35` 结论、Overview/Timeline/Race/Achievement 现有 builder/API/tests，以及 record events/active records ViewModel。
- 目标是让多运动正式纪录安全进入现有 ACS 消费者，同时避免候选、曲线、cache、model 和 no-change rebuild 泄漏。
- Overview 只能统计正式 active/superseded，显示 sport/family，不统计 candidate-only 或 analysis/model。
- Timeline 只消费正式 record event，并保持幂等；候选不进入正式 timeline node。
- Race Archive 与赛事事实保持边界，不从纪录反推赛事。
- Achievement 只由正式 record event 触发；candidate、rebuild no-change、cache、curve 和 model 不触发。
- 验证优先选择跨模块集成测试、timeline/overview/achievement 既有测试和 Records V2 API 测试。

## RCV2-36 Overview、Timeline、Race 与 Achievement 联动结论

- `career_backend.py` 新增 `get_career_records_downstream_integration()` 作为 Records V2 下游集成守卫。
- Overview 摘要只接收 `active/superseded` 正式纪录，并输出 `by_sport/by_family`。
- Timeline 摘要只接收正式 record events：`activated`、`activated_from_rebuild`、`user_confirmed`，幂等键为 `career_record_events.id`。
- Race Archive 明确 `consumes_records=false`、`record_derived_race_count=0`，不从纪录反推赛事。
- Achievement 只允许正式 record event 触发；candidate、curve/cache、model 和 recalculated/no-change 不触发。
- 排除项显式输出：候选数、curve cache 数、排除 event types、排除 catalog states 和 model/analysis family。
- 新增 `tests/test_career_records_v2_downstream_integration.py`。
- RCV2-36 验证：跨模块集成定向 `27 passed`；Records API 兼容 `6 passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-37 读取与验证提示

- 默认读取本摘要、`RCV2-37` 任务条目、`RCV2-14/33/36` 结论、现有 `build_career_snapshot()`、AI insight/trends 相关 builder/tests，以及 Records V2 API/curve/downstream helper。
- 目标是安全压缩 V2 当前正式纪录、最近刷新、候选数量、演进摘要和 curve availability，供 AI 和 Trends 消费。
- Snapshot 必须区分 facts、analysis 和 model；不得把 GAP/NGP/eFTP/curve/model 改写为“刷新正式纪录”。
- AI 只能解释来源和变化，不能重算、确认候选或写 canonical 纪录表。
- Trends 可消费 PDC/Pace/GAP 摘要，但必须标注 algorithm/model/source，并在样本不足或 unavailable 时降级。
- 禁止 raw streams、track、route signature、path、schema、体重详情和候选 evidence 泄露。
- 验证优先选择 snapshot builder、AI/Trends contract、Records V2 API 和安全扫描测试。

## RCV2-37 Records Snapshot、AI 与 Trends 联动结论

- `build_career_snapshot()` 的 `records_summary` 已扩展为：`current_records/formal_records/recent_refreshes/candidate_count/evolution_summary/curve_availability/trend_inputs`。
- `formal_records` 只包含 `active/superseded` 正式纪录，排除 `analysis_only/model_only/unavailable` catalog state 与 `analysis_curve/model_estimate` family。
- Legacy `current_records` 增加 model/analysis 过滤，避免 eFTP/GAP/NGP 等模型估计混入旧 PB 摘要。
- `recent_refreshes` 限定为正式刷新事件：`activated`、`activated_from_rebuild`、`user_confirmed`；`recalculated` 只进入演进统计，不作为正式刷新。
- `curve_availability` 只暴露 curve 元数据：`curve_type/sport/source_mode/state/sample_count/algorithm_versions/latest_generated_at/source/kind/creates_formal_record`；不读取或返回 curve payload、points、anchors、input fingerprint。
- `trend_inputs.curve_inputs` 为 PDC/Pace/GAP 提供 Trends 安全输入，并统一标记 `kind=analysis`、`source=career_record_curve_cache`、`creates_formal_record=false`。
- `trend_inputs.model_boundary` 明确 eFTP、CP、W′、MAP、PMax、GAP、NGP 不生成正式纪录，不暴露 candidate evidence。
- AI fallback 只消费安全 Snapshot；新增分析曲线可用性文案时明确“仅作趋势参考”，不重算、不确认、不写 canonical 表。
- `docs/js_api_contract.json` 已更新 `get_latest_career_snapshot` 返回契约与安全描述。
- 新增 `tests/test_career_records_v2_snapshot_ai_trends.py`。
- RCV2-37 验证：Snapshot/AI/Trends 定向与兼容合并 `41 passed`；`career_backend.py` / `main.py` py_compile 通过；`docs/js_api_contract.json` JSON 解析通过。

## RCV2-38 读取与验证提示

- 默认读取本摘要、`RCV2-38` 任务条目、`RCV2-13/14/37` 结论、Records V2 rebuild/curve/route/API/UI 相关代码，以及安全扫描、性能、日志和 observability 测试。
- 目标是验证 V2 重计算、Curve、Route、API 和 UI 在本地应用中的安全、性能、日志和可观测性闭环。
- 必须继续遵守：不写真实库、不打包；真实数据只允许备份/staging/dry-run，除非用户明确批准。
- 安全重点：API/log/docs/UI 不得泄露 raw FIT、raw streams、points、track、route signature、path、schema、设备标识、体重详情、candidate evidence。
- 性能重点：rebuild、curve cache、route comparison 和 Records Center 页面加载需有本地可复验指标或守卫。
- 日志重点：高风险写接口、dry-run/apply 状态、candidate 决策、rebuild/run_id 需要可观测但不泄露证据 payload。
- 验证优先选择新增安全/性能/日志测试、Records V2 API/downstream/snapshot 测试和必要前端静态测试。

## RCV2-38 安全、性能、日志与可观测性闭环结论

- 新增 `records_v2_observability_contract()`，冻结 Records V2 性能目标、高风险操作门禁、日志白名单与敏感字段黑名单。
- 新增 `records_v2_safe_observation()`，观测输出只允许 run_id、dry_run、action/decision、counts、by_sport/by_family/by_reason、elapsed_ms 等白名单字段。
- 列表、history、candidate、curve、route comparison 均返回诊断 metrics；curve/route 增加 cache hit/miss；route comparison 输出 `route_candidates`。
- Rebuild plan 返回 `metrics`、`observability` 和 `failure_recovery`，包含 by_sport/by_family/by_reason、cache/route 计数、savepoint、batch、cancel 能力。
- Route 观测使用抽象 `route_cache_count`，不输出 route signature 本体或可还原路线内容。
- Candidate confirm/reject 返回安全 `metrics/observability`，仍只接受 candidate_id + decision，不接受候选值修改。
- `main.py` 高风险入口新增安全日志；`rebuild_career_records(dry_run=false)` 未带 `apply_to_real_db=true` 时仍在进入后端写路径前拒绝。
- `docs/js_api_contract.json` 已更新 rebuild contract。
- 新增 `tests/test_career_records_v2_security_perf_observability.py`。
- RCV2-38 验证：安全/性能/日志/可观测性与兼容合并 `25 passed`；`career_backend.py` / `main.py` py_compile 通过；`docs/js_api_contract.json` JSON 解析通过。

## RCV2-39 读取与验证提示

- 默认读取本摘要、`RCV2-39` 任务条目、`RCV2-15` 至 `RCV2-38` 结论、现有测试目录与本地验证命令。
- 目标是运行并修复 V2 自动化测试矩阵，证明多运动扩展未破坏 V1 和相邻功能。
- 必须运行 Registry/schema/state/rebuild/API 各运动定向测试、前端/响应式/a11y、安全/性能/pywebview 契约测试、`tests/test_career_*.py`、Activity import/sync/delete/detail/refresh 相关回归、Python compile、API JSON 和敏感字段/静态视觉检查。
- 不得为通过测试降低产品规则、删除断言或跳过失败用例；环境性未执行项必须记录替代证据。
- 仍然不打包；真实数据 apply 仍需用户明确授权。

## RCV2-39 V2 自动化测试矩阵与全量回归结论

- Records V2 定向矩阵通过：`185 passed, 27 subtests passed`。
- 全部 `tests/test_career_*.py` 通过：`729 passed, 52 subtests passed`。
- Activity import/sync/delete/detail/refresh 相邻回归通过：`521 passed, 1 skipped, 27 subtests passed`。
- Python compile 通过：`career_backend.py`、`main.py`、`metrics_registry.py`、`metrics_resolver.py`、`utils/metrics_calc.py`。
- `docs/js_api_contract.json` JSON 解析通过。
- 静态检查通过：`track.html` 不再出现 viewport 字号或负 letter-spacing；高风险日志未记录 clean payload / payload_json / evidence_json。
- 修复兼容问题：`get_trace_activity_history()` 保留统一 envelope，同时镜像旧顶层分页/筛选字段；常规活动列表去重优先按 Activity id，避免不同活动被语义折叠。
- 修复契约边界：`get_career_record_curve.returns` 不再出现 `points` 字面量；Activity invalidation 外部字段使用 `route_cache` 而不是 route signature 字样。
- 未执行真实库 apply；未打包。

## RCV2-40 读取与验证提示

- 默认读取本摘要、`RCV2-40` 任务条目、`RCV2-08/39` 结论、真实库路径/当前 DB 状态、V2 schema migration dry-run、records rebuild dry-run 和 Catalog 可用性相关代码。
- 目标是在真实数据副本上完成备份、staging dry-run 和人工复核报告；不得写真实库。
- 必须验证源 DB 和备份/副本哈希，记录真实库 dry-run 前后关键计数/mtime 不变。
- 在 staging 副本上确保 schema 并执行 V2 plan/dry-run，按运动、纪录族、Scope、active/candidate/ignored/reason 汇总。
- 抽查骑行功率、徒步海拔、公开水域；泳池/越野必须明确样本限制。
- 输出用户可决策报告：哪些 Catalog 可保持 available，哪些必须保持 candidate-only/validation-required。

## RCV2-40 真实数据备份、staging dry-run 与人工复核结论

- 已生成脱敏 dry-run 摘要：`docs/records_center_v2_real_data/rcv2_40/rcv2_40_staging_dry_run_summary.json`。
- 已生成 backup 与 staging 副本，初始 hash 均匹配源库。
- 源库前后 hash、mtime_ns、关键表计数均一致，证明未写真实库。
- 源库关键计数：`activities=981`、`career_pb_records=3`、`career_event_candidates=129`、`career_ai_insights=14`。
- 源库候选类型：`race/candidate=125`、`race/resolved=4`；V2 `pb_record` candidate 为 0。
- 真实样本：骑行 368 条（66 条有功率摘要）、徒步 33 条（33 条有海拔/爬升摘要）、公开水域 7 条、泳池 0 条、越野跑 0 条。
- staging schema ensure 成功，schema version 为 `2026-07-14.records-v2.10`。
- staging rebuild dry-run：processed 981，dispatch planned 854，ignored 127；by_family 为 `distance_time_pb=1812`、`power_duration_pb=2208`、`activity_total_record=1236`。
- staging cache/route 当前为空：curve cache 0，route cache 0，route match 0，route candidates 0。
- 真实 staging rebuild plan 耗时约 1897 ms，高于小样本诊断目标 1000 ms；不阻塞 RCV2-40，但真实 apply 前应继续观察。
- Catalog 决策建议：跑步保持 V1 兼容；骑行/徒步可展示但真实写入仍需授权；公开水域 candidate-only；泳池 validation-required；越野 candidate-only / analysis-only。
- 用户既有决策“全部保持候选，不写入真实库”继续有效；未执行真实库 apply，未打包。

## RCV2-41 读取与验证提示

- 默认读取本摘要、`RCV2-41` 任务条目、`RCV2-40` 完成报告与 dry-run 摘要、Catalog/Registry 当前 availability 定义。
- 目标是记录用户 no-apply / keep-candidate 决策，并冻结 Catalog 与真实验收状态一致。
- 没有新的明确授权不得执行真实 apply；用户已给出的原则是“先全部保持候选，不写入真实库”。
- 泳池/越野无真实样本不能标 Verified；公开水域保持 candidate-only；骑行/徒步虽有样本，正式写入仍需候选/质量门禁与后续授权。
- 交付物应包含用户决策记录、Catalog 最终状态、真实库不变证据和完成报告。

## RCV2-41 用户数据决策与 Catalog 可用性最终冻结结论

- 用户 no-apply / keep-candidate 决策已记录：`docs/records_center_v2_rcv2_41_user_decision_catalog_freeze.md`。
- 当前 Catalog 与真实验收状态一致，无需代码修改：
  - running：available 4
  - cycling：available 9，validation_required 1
  - hiking：available 4，candidate_only 1
  - pool_swimming：validation_required 6
  - open_water_swimming：candidate_only 8
  - trail_running：candidate_only 8
- 未执行真实库 apply，未确认/拒绝真实候选，未打包。
- RCV2-41 验证：Catalog/Registry/API/golden fixture 定向 `29 passed, 13 subtests passed`；`career_backend.py` / `main.py` py_compile 通过。

## RCV2-42 读取与验证提示

- 默认读取本摘要、`RCV2-42` 任务条目、`RCV2-39/41` 结论、macOS/pywebview API bridge、Records Center V2 前端 shell、视觉验收文档和现有 macOS closure 测试。
- 目标是在当前 macOS 环境验证 V2 运行时、pywebview、视觉和数据边界，不擅自重新打包。
- 必须验证 pywebview bridge 暴露 Records V2 API，统一 envelope 正常，前端不计算事实，不泄露敏感字段。
- 视觉验收可使用静态/代码级证据；如本地 Browser 仍阻止 file://，记录限制与替代证据。
- 不生成、签名、公证或替换发布包。

## RCV2-42 macOS 当前环境、pywebview 与视觉验收结论

- `pywebview` import 可用。
- `main.Api` Records V2 只读 smoke 通过：Catalog、records、candidates、rebuild status、latest snapshot 均返回统一 envelope。
- main.Api smoke 前后源库内容 hash 和关键计数不变；mtime 曾变化，后续纯 read-only SQLite 复核 hash/mtime/counts 稳定。若发布前要求 mtime 严格不变，需要另行收紧只读连接策略。
- macOS/pywebview/envelope 测试 `32 passed`。
- Records V2 前端测试 `21 passed`。
- 视觉/数据边界测试 `20 passed`。
- `career_backend.py` / `main.py` py_compile 通过。
- 只读检查发现历史 build/dist/DMG/app/spec 产物存在；本轮未运行 PyInstaller、DMG、签名、公证或发布包替换。
- GUI 截图未生成，沿用当前环境 file:// 限制，使用静态/测试证据替代。

## RCV2-43 阻塞说明

- `RCV2-43 Windows 真机、pywebview 与视觉验收` 必须在 Windows 真机环境验证启动、pywebview bridge、ECharts、字体、滚动、多尺寸布局、路径/数据库/cache 和五运动 Records Center。
- 当前执行环境是 macOS，无法完成 Windows 真机门禁。
- 在获得 Windows 环境前，不应把 RCV2-43 标记为 Done，也不能进入最终发布门禁。
