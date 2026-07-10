# ACS-Phase1-03：建立 Race Resolver 与赛事候选置信度模型

你是 Codex，请在脉图项目中执行本任务。执行前必须先阅读并理解以下文件：

1. `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
2. `docs/脉图运动生涯系统（ACS）开发任务清单.md`
3. `.trae/rules/fit-arch-contrac.md`
4. `docs/acs_phase1_01_fit_sport_event_race_completion_report.md`
5. `docs/acs_phase1_02_user_race_flag_completion_report.md`
6. 当前代码：`career_backend.py`、`main.py`、`profile_backend.py`

## 一、任务背景

前置任务已经完成：

- FIT `session.sport_event == race` 可解析并写入 `activities.is_race`。
- FIT 来源会写入 `race_source = 'fit_sport_event'`、`race_confidence = 'high'`。
- 用户可以通过 `Api.set_activity_race_flag(activity_id, is_race, source='user')` 手动标记或取消赛事。
- 用户确认或取消优先级高于后续 FIT 同步。
- ACS schema 已预留：
  - `career_race_events`
  - `career_event_candidates`

本任务进入 Phase 1 的核心：建立 Race Resolver，让系统能从 Activity 派生赛事语义事件，并区分正式赛事与候选赛事。

## 二、任务目标

实现一个后端 Race Resolver，负责从 `activities` 读取安全字段，识别赛事证据并输出：

1. 正式赛事事件：写入 `career_race_events`
2. 低置信度赛事候选：写入 `career_event_candidates`
3. 结构化证据：写入 `evidence_json` 或 `display_metadata_json`
4. 置信度等级：
   - `high`：用户确认，或 FIT 明确 `sport_event` race
   - `medium`：标题强赛事关键词 + 标准距离区间
   - `low`：只有距离区间匹配，或弱标题线索

## 三、实现边界

本任务必须做：

- 在 `career_backend.py` 中实现 Race Resolver 相关纯后端函数。
- 只读取 `activities` 的安全摘要字段，不读取 raw FIT、points、track_json、points_json、file_path。
- 将高 / 中置信度赛事写入 `career_race_events`，低置信度只写入 `career_event_candidates`。
- 确保所有 `career_race_events` 和候选都带 `activity_id`，可回跳 Activity Detail。
- 保持幂等：重复执行 resolver 不应产生重复赛事或重复候选。
- 增加针对 resolver 的单元测试。
- 写完成报告。

本任务不得做：

- 不实现 `get_career_races` API。
- 不接前端 UI。
- 不实现 PB Engine、Achievement Engine、Memory System。
- 不把低置信度候选写入正式主时间轴。
- 不从前端、AI、标题 DOM、ECharts、轨迹点或 SQLite schema 推断赛事。
- 不暴露或存储 raw FIT、points、track_json、points_json、file_path。
- 不修改 FIT 原始文件或运动事实字段。

## 四、建议实现方案

### 1. 新增 resolver 函数

建议在 `career_backend.py` 中新增：

```python
def resolve_race_events(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    ...
```

返回结构建议：

```python
{
    "ok": True,
    "processed": 12,
    "race_events_upserted": 3,
    "candidates_upserted": 2,
    "skipped": 7,
    "status": {
        "schema_ready": True,
        "resolver": "race",
        "message": "赛事解析完成"
    }
}
```

该函数可以先作为后端内部能力，不需要注册到 `main.Api` 或 `docs/js_api_contract.json`。

### 2. 安全读取 Activity 字段

建议只 SELECT 以下字段，缺列时需要兼容旧库：

- `id`
- `title`
- `title_source`
- `sport_type`
- `sub_sport_type`
- `start_time`
- `start_time_utc`
- `dist_km`
- `distance`
- `duration`
- `duration_sec`
- `avg_pace`
- `region_city`
- `region`
- `region_display`
- `is_race`
- `race_source`
- `race_confidence`
- `race_override`
- `race_confirmed_at`
- `deleted_at`

严禁 SELECT：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`

### 3. 证据模型

建议内部生成 evidence dict：

```python
{
    "signals": [
        {"type": "user_confirmation", "level": "high", "matched": True},
        {"type": "fit_sport_event", "level": "high", "matched": True},
        {"type": "title_keyword", "level": "medium", "matched": True, "keyword": "马拉松"},
        {"type": "standard_distance", "level": "low", "matched": True, "category": "half_marathon"}
    ],
    "confidence_level": "high",
    "confidence_score": 1.0,
    "decision": "race_event"
}
```

证据 JSON 可以存入：

- `career_race_events.display_metadata_json`
- `career_event_candidates.evidence_json`

不要把 raw Activity row 直接 dump 进去。

### 4. 置信度规则

建议使用简单、可测、可解释的第一版规则：

#### high

满足任一条件：

- `race_source == 'user'` 且 `is_race == 1`
- `race_override == 1` 且 `is_race == 1`
- `race_source == 'fit_sport_event'` 且 `is_race == 1`
- `is_race == 1` 且 `race_confidence == 'high'`

注意：

- `race_source == 'user'` 且 `is_race == 0` 表示用户明确取消赛事，必须跳过，不进入正式赛事，也不进入候选。

#### medium

建议同时满足：

- 标题包含强赛事关键词，例如：
  - `马拉松`
  - `半程马拉松`
  - `半马`
  - `全马`
  - `10K`
  - `5K`
  - `越野赛`
  - `铁人三项`
  - `比赛`
  - `race`
  - `marathon`
  - `trail race`
- 距离匹配常见标准赛事区间之一：
  - 5K：4.8-5.3 km
  - 10K：9.5-10.8 km
  - 半马：20.5-21.7 km
  - 全马：41.0-43.0 km

medium 可写入 `career_race_events`，但 source 应为 `resolver`，confidence score 建议 `0.75`。

#### low

满足任一条件：

- 只有距离匹配标准赛事区间
- 只有弱标题线索，例如标题里只有“活动 / event / run”等模糊词

low 只能写入 `career_event_candidates`，`candidate_type = 'race'`，`status = 'candidate'`。

### 5. event_type / name 生成

`career_race_events.event_type` 建议：

- `5k`
- `10k`
- `half_marathon`
- `marathon`
- `trail_race`
- `triathlon`
- `race`

`name` 生成优先级：

1. 用户编辑标题：`title_source == 'user'`
2. 活动标题 `title`
3. 根据距离与城市 / 日期生成兜底名，例如 `2026 上海半程马拉松`

不要把文件名作为正式赛事名，除非没有任何其他标题信息。

### 6. 幂等策略

建议使用稳定 ID：

- `career_race_events.id = f"race:{activity_id}"`
- `career_event_candidates.id = f"race_candidate:{activity_id}"`

使用 `INSERT ... ON CONFLICT(id) DO UPDATE` 或兼容 SQLite 的先查后更新方式。

重复执行 resolver 时：

- 同一个 Activity 只保留一条正式赛事或一条候选。
- 如果用户取消赛事，应删除或标记 inactive 对应正式赛事，并删除或关闭候选。
- 如果低置信度候选升级为 high/medium，应写入正式赛事，并删除或标记 resolved 对应候选。

### 7. overview / timeline 兼容

- `get_career_overview()` 已统计 `career_race_events status='active'`，resolver 写入后 overview 的 `race_count` 应自然变更。
- `get_career_timeline()` 本任务可以不生成 timeline nodes，但不能破坏现有空状态测试。
- 不要新增前端 API。

## 五、测试要求

新增测试文件建议：

- `tests/test_career_race_resolver.py`

至少覆盖：

1. 用户确认赛事 -> 写入 `career_race_events`，confidence high，activity_id 存在。
2. 用户取消赛事 -> 不写正式赛事，不写候选；若已有事件则 inactive 或删除。
3. FIT race -> 写入 `career_race_events`，source/evidence 指向 fit_sport_event。
4. 标题强关键词 + 标准距离 -> medium，写入正式赛事。
5. 只有标准距离 -> low，只写入 `career_event_candidates`，不写 `career_race_events`。
6. 重复执行 resolver -> 不产生重复记录。
7. Resolver 不读取 / 不存储 forbidden raw fields：
   - `points`
   - `points_json`
   - `track_json`
   - `raw_records`
   - `fit_records`
   - `file_path`
   - `advanced_metrics`
   - `shadow_diff_json`
8. `get_career_overview()` 在 resolver 后能反映 `race_count`。
9. macOS / Windows 兼容：测试使用 `tempfile` 与 `profile_backend.DB_PATH` 临时库，不写死系统路径。

继续保留并通过既有测试：

- `tests/test_career_backend_schema.py`
- `tests/test_career_api_skeleton.py`
- `tests/test_fit_sport_event_race.py`
- `tests/test_activity_race_flag_api.py`

## 六、验证命令

执行完成后至少运行：

```bash
python3 -m pytest tests/test_career_race_resolver.py
python3 -m pytest tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
python3 -m py_compile career_backend.py main.py profile_backend.py
```

如修改了 API 契约，再运行：

```bash
python3 -m json.tool docs/js_api_contract.json
```

## 七、完成报告

完成后新增：

`docs/acs_phase1_03_race_resolver_completion_report.md`

报告至少包含：

- 任务范围
- 修改文件
- Race Resolver 规则
- low 候选不进入正式赛事的证明
- 用户取消优先级说明
- macOS / Windows 兼容性说明
- 测试命令与结果
- 下一任务建议

## 八、验收标准

- 所有正式赛事都可以回跳 `activity_id`。
- 用户确认和 FIT race 为 high 置信度。
- 用户取消赛事具有最高优先级，不被标题或距离规则重新推入候选。
- medium 规则必须同时具备标题强赛事关键词和标准距离。
- low 候选不会污染 `career_race_events`。
- ACS 表不存 raw FIT、轨迹、文件路径或大体积字段。
- 重复执行 resolver 幂等。
