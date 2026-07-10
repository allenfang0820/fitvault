# ACS-Phase0-05 Readonly API Skeleton Completion Report

## Scope

This task adds the first ACS readonly pywebview API skeletons:

- `get_career_overview`
- `get_career_timeline`

Before implementation, the following references were reviewed:

1. `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
2. `docs/脉图运动生涯系统（ACS）开发任务清单.md`
3. `docs/acs_phase0_01_architecture_baseline_completion_report.md`
4. `docs/acs_phase0_03_schema_migration_completion_report.md`
5. `docs/acs_phase0_04_career_nav_shell_completion_report.md`
6. `docs/js_api_contract.json`
7. `.trae/rules/fit-arch-contrac.md`

## Implemented

- Added `career_backend.get_career_overview(conn=None)`.
- Added `career_backend.get_career_timeline(filters=None, conn=None)`.
- Added `main.Api.get_career_overview()`.
- Added `main.Api.get_career_timeline(filters=None)`.
- Registered both APIs in `docs/js_api_contract.json` under category `career`.
- Added `tests/test_career_api_skeleton.py`.

## Response Shapes

`get_career_overview` returns:

```json
{
  "summary": {
    "career_start_year": null,
    "activity_count": 0,
    "race_count": 0,
    "pb_count": 0,
    "achievement_count": 0,
    "memory_count": 0,
    "covered_city_count": 0,
    "total_distance_km": null
  },
  "latest_race": null,
  "representative_achievements": [],
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "运动生涯数据将在赛事、PB 与成就解析后生成"
  }
}
```

`get_career_timeline` returns:

```json
{
  "filters": {
    "sport": "all",
    "year": null,
    "type": "all"
  },
  "years": [],
  "candidates_count": 0,
  "status": {
    "schema_ready": true,
    "data_ready": false,
    "message": "时间轴将在 ACS 派生事件生成后展示"
  }
}
```

The pywebview methods wrap these structures with the existing unified envelope:

```json
{
  "ok": true,
  "code": 0,
  "msg": "ok",
  "data": {},
  "traceId": "<hex12>"
}
```

## Architecture Boundary

This task intentionally does not implement:

- Race Resolver
- PB Resolver
- Achievement Resolver
- FIT `sport_event` parsing
- AI Career Insight
- Career Snapshot generation
- Frontend live rendering
- User editing of races or PB records
- Any write to ACS business tables

The backend reads only ACS derived-table counts and safe Activity aggregate fields such as activity count, earliest activity year, distinct city count, and total distance. It does not expose `points`, `track_json`, raw FIT records, SQLite schema content, or local file paths.

## Compatibility Notes

- Default DB access still goes through `profile_backend.DB_PATH` and `Path`.
- The backend functions accept injected SQLite connections for tests and future migrations.
- API parameters are JSON-serializable dictionaries.
- Chinese status messages are returned through the normal pywebview envelope.
- No filesystem path, local resource, or network dependency was added.

## Verification

Passed:

```bash
python3 -m pytest tests/test_career_backend_schema.py
python3 -m pytest tests/test_career_api_skeleton.py
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m py_compile career_backend.py main.py
```

Additional check:

```bash
python3 -m json.tool docs/js_api_contract.json
```
