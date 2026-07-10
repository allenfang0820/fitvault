# ACS-Phase1-02 用户手动赛事标记完成报告

## 任务边界

- 本任务只补齐用户手动标记 / 取消赛事的后端能力。
- 不实现 Race Resolver、标题关键词推断、距离区间推断、`career_race_events` 生成、`get_career_races` API、前端 UI 或 AI/Snapshot 接入。
- Activity 仍是赛事事实的唯一回跳源，所有写入都落在 `activities` 的赛事元数据字段。

## 完成内容

1. 新增赛事来源元数据列
   - `race_source TEXT`
   - `race_confirmed_at TEXT`
   - `race_confidence TEXT`
   - `race_override INTEGER DEFAULT 0`

2. 补齐 schema 兼容路径
   - `main.ensure_activity_sync_schema()` 增加幂等补列。
   - `profile_backend` 初始化 / 迁移补列清单同步增加同名字段。
   - 兼容 macOS / Windows 的本地 SQLite 旧库启动迁移，不依赖平台特定路径或文件锁行为。

3. FIT race 写入来源化
   - FIT `session.sport_event == race` 写入：
     - `is_race = 1`
     - `race_source = 'fit_sport_event'`
     - `race_confidence = 'high'`
     - `race_override = 0`
   - FIT 非 race 同步会清空 FIT 来源赛事状态。
   - 若已有 `race_source = 'user'` 或 `race_override = 1`，后续 FIT 同步不覆盖用户确认或取消。

4. 新增用户手动赛事标记 API
   - 方法：`Api.set_activity_race_flag(activity_id, is_race, source='user')`
   - 仅允许 `source='user'`。
   - 成功返回统一 envelope：

```json
{
  "ok": true,
  "code": 0,
  "msg": "赛事标记已更新",
  "data": {
    "activity_id": 123,
    "is_race": true,
    "race_source": "user",
    "race_confidence": "high",
    "race_override": 1,
    "race_confirmed_at": "2026-07-07 22:00:00"
  },
  "traceId": "..."
}
```

5. 更新 JS API 契约
   - `docs/js_api_contract.json` 新增 `set_activity_race_flag`。
   - 明确该 API 不修改 FIT 原始文件、轨迹、运动事实或 AI/Snapshot 数据。

## 修改文件

- `main.py`
- `profile_backend.py`
- `docs/js_api_contract.json`
- `tests/test_fit_sport_event_race.py`
- `tests/test_activity_race_flag_api.py`

## 验证结果

- `python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py`
  - 14 passed
- `python3 -m pytest tests/test_fit_sync.py tests/test_career_api_skeleton.py`
  - 116 passed
- `python3 -m pytest tests/test_career_backend_schema.py`
  - 7 passed
- `python3 -m py_compile fit_engine.py main.py career_backend.py`
  - passed
- `python3 -m json.tool docs/js_api_contract.json`
  - passed

## 后续任务

原计划下一个任务是 `ACS-Phase1-03：建立 Race Resolver 与赛事候选置信度模型`。

该任务应读取：

- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `.trae/rules/fit-arch-contrac.md`
- 本报告

建议边界：

- 聚合赛事证据：FIT `sport_event`、用户确认状态、用户编辑标题、活动距离区间、城市 / 时间。
- 输出 `high / medium / low` 置信度。
- 低置信度只进入候选，不进入正式主时间轴。
- 仍不生成 PB、成就、记忆，也不接前端 UI。
