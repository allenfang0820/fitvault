# ACS-Phase0-04 Career Navigation Shell Completion Report

## Scope

This task adds the first-level ACS navigation shell for `运动生涯` and demotes the legacy profile-level honor wall into a transition entry.

Before implementation, the following references were reviewed:

1. `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
2. `docs/脉图运动生涯系统（ACS）开发任务清单.md`
3. `docs/acs_phase0_01_architecture_baseline_completion_report.md`
4. `docs/acs_phase0_03_schema_migration_completion_report.md`
5. `docs/js_api_contract.json`
6. `.trae/rules/fit-arch-contrac.md`

## Implemented

- Added first-level sidebar navigation item `运动生涯`.
- Added `#panel-career` as the ACS Phase 0 page shell.
- Added structural placeholders for:
  - Career Overview
  - Career Timeline
  - Race archive
  - PB records
  - Achievement milestones
  - Memory and narrative area
- Updated `switchTab()` so `career` is a first-level panel.
- Demoted the profile-level `荣誉墙` tab into `运动生涯入口`.
- Added `switchToCareerFromHonorWall()` for the transition entry.
- Stopped the legacy honor entry from loading old honor-wall data.
- Removed the old honor wall DOM container from the active profile tab surface.

## Files Changed

- `track.html`
- `tests/test_track_html_sync_logic.py`
- `docs/acs_phase0_04_career_nav_shell_completion_report.md`

## Architecture Boundary

This task is frontend shell work only. It intentionally does not implement:

- Race resolver logic
- PB resolver logic
- Achievement resolver logic
- Career backend APIs
- SQLite reads
- FIT parsing
- AI Career Insight
- Career Snapshot generation

The new ACS page does not call `window.pywebview.api.*`, does not calculate PB/race/achievement facts in frontend code, and does not use `points` or `track_json`.

## Legacy Honor Wall Demotion

The old profile-level honor wall is no longer treated as the ACS primary surface. It is now a transition entry that tells the user the capability has moved to the first-level `运动生涯` module and provides an inline button to switch there.

## macOS / Windows Compatibility Notes

- No filesystem paths or platform-specific path separators were introduced.
- No external assets or network resources were introduced.
- The navigation label uses normal text flow inside the existing sidebar tab pattern.
- The ACS shell uses responsive CSS grid fallback for narrower pywebview windows.
- The page is static and does not change pywebview API behavior.

## Verification

Passed:

```bash
python3 -m pytest tests/test_track_html_sync_logic.py
python3 -m pytest tests/test_career_backend_schema.py
python3 -m py_compile career_backend.py main.py
```

Additional targeted check run during development:

```bash
python3 -m pytest tests/test_track_html_sync_logic.py -q
```
