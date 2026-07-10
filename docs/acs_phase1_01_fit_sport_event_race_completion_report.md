# ACS-Phase1-01 FIT Sport Event Race Completion Report

## Scope

This task connects the FIT native race marker to the canonical Activity database:

```text
FIT session.sport_event -> parsed activity payload -> activities.is_race
```

Before implementation, the following references were reviewed:

1. `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
2. `docs/脉图运动生涯系统（ACS）开发任务清单.md`
3. `docs/acs_phase0_01_architecture_baseline_completion_report.md`
4. `docs/acs_phase0_03_schema_migration_completion_report.md`
5. `docs/acs_phase0_04_career_nav_shell_completion_report.md`
6. `docs/acs_phase0_05_readonly_api_skeleton_completion_report.md`
7. `docs/js_api_contract.json`
8. `.trae/rules/fit-arch-contrac.md`

## Implemented

- `fit_engine.py`
  - Reads FIT `session.sport_event`.
  - Preserves the scalar value in `basic_info.sport_event`.
- `main.py`
  - Adds `_is_fit_sport_event_race(value)`.
  - Treats `race`, `*.race`, and numeric enum `4` as race.
  - Adds `sport_event` and `is_race` to the parsed activity payload.
  - Persists `activities.is_race` after insert.
  - Persists `activities.is_race` after update/re-import.
- `tests/test_fit_sport_event_race.py`
  - Covers string race marker.
  - Covers numeric race marker.
  - Covers missing and non-race marker.
  - Covers insert/update persistence.
  - Covers idempotent schema availability.

## Race Detection Rule

Only the FIT native `session.sport_event` marker is used in this task.

Accepted race values:

- `"race"`
- enum-like strings ending in `.race` or `:race`
- `4`
- `"4"`

All missing, empty, or other values are treated as non-race and write `is_race = 0`.

## Database Write

The existing `activities.is_race INTEGER DEFAULT 0` column is reused.

The insert and update paths set the value explicitly after the main activity row write:

```text
is_race = 1 if FIT sport_event is race/4
is_race = 0 otherwise
```

This keeps the large existing INSERT/UPDATE column lists stable and avoids changing unrelated field ordering.

## Explicit Non-Goals

This task intentionally does not implement:

- Race Resolver综合判断
- 标题关键词推断赛事
- 距离区间推断赛事
- 用户确认赛事
- `career_race_events` generation
- `get_career_races` API
- ACS timeline rendering
- AI Career Insight
- Career Snapshot generation
- Frontend race badges

## Compatibility Notes

- No platform-specific path handling was added.
- SQLite migration remains idempotent; `is_race` already exists in existing schema migration.
- Old activities and FIT files without `sport_event` remain valid and default to non-race.
- Chinese filenames and titles are not touched.
- No local paths, raw FIT records, `points`, or `track_json` are added to AI or ACS Snapshot paths.
- `fit_sdk_engine.py` was referenced in the task prompt, but this repository currently does not contain that file; the active FIT SDK path is in `fit_engine.py` and `main.py`.

## Verification

Passed:

```bash
python3 -m pytest tests/test_fit_sport_event_race.py
python3 -m pytest tests/test_fit_sync.py
python3 -m pytest tests/test_career_api_skeleton.py
python3 -m pytest tests/test_career_backend_schema.py
python3 -m py_compile fit_engine.py main.py career_backend.py
```

`fit_sdk_engine.py` was not compiled because the file is not present in the workspace.
