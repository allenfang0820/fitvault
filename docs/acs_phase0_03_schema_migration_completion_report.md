# ACS-Phase0-03 Schema Migration Completion Report

## Scope

This task establishes the ACS V1 derived-data schema skeleton in `career_backend.py`.

Before implementation, the following references were reviewed:

1. `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
2. `docs/脉图运动生涯系统（ACS）开发任务清单.md`
3. `docs/js_api_contract.json`
4. `.trae/rules/fit-arch-contrac.md`

## Implemented

- Updated `CAREER_SCHEMA_VERSION` to `2026-07-07.phase0.03`.
- Added idempotent ACS business-table migration for:
  - `career_race_events`
  - `career_pb_records`
  - `career_achievement_events`
  - `career_memory_items`
  - `career_snapshots`
  - `career_event_candidates`
- Added lookup indexes for activity traceability, timeline sorting, PB lookup, snapshot generation, and candidate review.
- Kept `ensure_career_schema(conn=None)` compatible with injected test connections and the default `profile_backend.DB_PATH`.

## Architecture Boundary

The migration creates only derived indexes, snapshot records, and display metadata. It does not implement:

- Race resolver logic
- PB resolver logic
- Achievement resolver logic
- Career APIs
- Frontend navigation or rendering
- FIT `sport_event` parsing
- AI prompt generation

Every formal ACS business table that represents a user-visible event keeps an `activity_id` reference. `career_snapshots` is the AI-facing summary store and intentionally does not copy raw Activity facts.

## Raw Fact Guardrails

The schema intentionally avoids raw Activity payload columns such as:

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `gps`
- `heart_rate`
- `file_path`

Memory records use `storage_ref` rather than a local absolute path, so later macOS and Windows packaging can map assets through an application-controlled storage layer without exposing filesystem paths to AI.

## Compatibility Notes

- SQLite migration is idempotent through `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
- The default connection still resolves `profile_backend.DB_PATH` via `Path`, preserving macOS and Windows path compatibility.
- No platform-specific path separators or absolute local paths were introduced.
- No pywebview API surface was changed in this task.

## Verification

Passed:

```bash
python3 -m pytest tests/test_career_backend_schema.py
```

Additional verification should be run with the next integration task:

```bash
python3 -m pytest tests/test_ai_snapshot_resolver.py
python3 -m py_compile career_backend.py main.py
```
