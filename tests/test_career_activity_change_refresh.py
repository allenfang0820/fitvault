import tempfile
from pathlib import Path
from unittest import mock

import main
import profile_backend


def test_manual_save_activity_triggers_career_refresh():
    api = main.Api.__new__(main.Api)
    payload = {"points_json": [{"time": "2026-07-11T08:00:00Z"}]}
    refresh_result = {"ok": True, "reason": "manual_save_activity"}

    with (
        mock.patch("profile_backend._assert_gpx_not_persisted") as assert_gpx,
        mock.patch("profile_backend.save_activity", return_value=42) as save_activity,
        mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result) as refresh,
    ):
        result = api.save_activity(payload)

    assert result == {"ok": True, "activity_id": 42, "career_refresh": refresh_result}
    assert payload["start_time"] == "2026-07-11T08:00:00Z"
    assert payload["file_path"] is None
    assert_gpx.assert_called_once_with(payload)
    save_activity.assert_called_once_with(payload)
    refresh.assert_called_once_with("manual_save_activity")


def test_manual_save_activity_refresh_failure_does_not_block_save():
    api = main.Api.__new__(main.Api)
    refresh_result = {
        "ok": False,
        "reason": "manual_save_activity",
        "error_code": "career_refresh_failed",
    }

    with (
        mock.patch("profile_backend._assert_gpx_not_persisted"),
        mock.patch("profile_backend.save_activity", return_value=7),
        mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result),
    ):
        result = api.save_activity({})

    assert result["ok"] is True
    assert result["activity_id"] == 7
    assert result["career_refresh"] == refresh_result


def test_delete_activities_triggers_career_refresh_after_deleted_rows():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        original_db_path = profile_backend.DB_PATH
        original_tracks_dir = main.TRACKS_DIR
        original_schema_ready = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        try:
            profile_backend.DB_PATH = temp_path / "activities.sqlite"
            tracks_dir = temp_path / "tracks"
            tracks_dir.mkdir()
            main.TRACKS_DIR = str(tracks_dir)
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

            fit_path = tracks_dir / "delete-me.fit"
            fit_path.write_text("fit", encoding="utf-8")
            activity_id = profile_backend.save_activity({
                "filename": "delete-me.fit",
                "dist_km": 1.0,
                "duration_sec": 60,
                "start_time": "2026-07-11T08:00:00Z",
                "file_path": str(fit_path),
                "points_json": [],
            })
            refresh_result = {"ok": True, "reason": "delete_activities"}

            with mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result) as refresh:
                result = main.Api.__new__(main.Api).delete_activities([activity_id], "DELETE:1")

            assert result["ok"] is True
            assert result["data"]["deleted"] == 1
            assert result["data"]["career_refresh"] == refresh_result
            refresh.assert_called_once_with("delete_activities")
        finally:
            profile_backend.DB_PATH = original_db_path
            main.TRACKS_DIR = original_tracks_dir
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = original_schema_ready


def test_cleanup_duplicate_activities_refreshes_only_when_rows_are_deleted():
    api = main.Api.__new__(main.Api)
    cleanup_result = {"ok": True, "dry_run": False, "rows_deleted": 2}
    refresh_result = {"ok": True, "reason": "cleanup_duplicate_activities"}

    with (
        mock.patch("profile_backend.cleanup_duplicate_activities", return_value=cleanup_result) as cleanup,
        mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result) as refresh,
    ):
        result = api.cleanup_duplicate_activities(False)

    assert result["ok"] is True
    assert result["data"]["career_refresh"] == refresh_result
    cleanup.assert_called_once_with(dry_run=False)
    refresh.assert_called_once_with("cleanup_duplicate_activities")


def test_cleanup_duplicate_activities_dry_run_does_not_refresh():
    api = main.Api.__new__(main.Api)
    cleanup_result = {"ok": True, "dry_run": True, "rows_deleted": 0}

    with (
        mock.patch("profile_backend.cleanup_duplicate_activities", return_value=cleanup_result),
        mock.patch("main._refresh_career_derived_events_safe") as refresh,
    ):
        result = api.cleanup_duplicate_activities(True)

    assert result["ok"] is True
    assert "career_refresh" not in result["data"]
    refresh.assert_not_called()
