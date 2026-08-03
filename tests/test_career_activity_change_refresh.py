import tempfile
from pathlib import Path
from unittest import mock

import career_backend
import main
import profile_backend


def _flatten_timeline_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


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


def test_delete_activities_invalidates_pb_records_for_deleted_activity():
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

            fit_path = tracks_dir / "pb-delete-me.fit"
            fit_path.write_text("fit", encoding="utf-8")
            activity_id = profile_backend.save_activity({
                "filename": "pb-delete-me.fit",
                "sport_type": "running",
                "dist_km": 5.0,
                "duration_sec": 1500,
                "start_time": "2026-07-11T08:00:00Z",
                "file_path": str(fit_path),
                "points_json": [{"distance_m": 5000, "t_sec": 1500}],
            })

            conn = profile_backend._conn()
            try:
                career_backend.ensure_career_schema(conn)
                row = career_backend._fetch_pb_resolver_activity_row(conn, activity_id)
                summary = career_backend._record_performance_summary(row)
                summary["time_quality"] = "reliable_elapsed"
                summary["elapsed_time_sec"] = 1500
                match = career_backend.match_record_definition(summary)
                decision = career_backend.build_record_candidate_decision(summary, match)
                career_backend.apply_record_candidate_decision(conn, decision)
                conn.commit()
            finally:
                conn.close()

            refresh_result = {"ok": True, "reason": "delete_activities"}
            with mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result):
                result = main.Api.__new__(main.Api).delete_activities([activity_id], "DELETE:1")

            assert result["ok"] is True
            assert result["data"]["deleted"] == 1
            conn = profile_backend._conn()
            try:
                status = conn.execute(
                    "SELECT status FROM career_pb_records WHERE activity_id = ?",
                    (str(activity_id),),
                ).fetchone()[0]
            finally:
                conn.close()
            assert status == "invalidated"
        finally:
            profile_backend.DB_PATH = original_db_path
            main.TRACKS_DIR = original_tracks_dir
            main._ACTIVITY_SYNC_SCHEMA_READY_FOR = original_schema_ready


def test_delete_activities_updates_record_timeline_milestones_for_deleted_best_activity():
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

            first_fit = tracks_dir / "timeline-5k-first.fit"
            best_fit = tracks_dir / "timeline-5k-best.fit"
            first_fit.write_text("fit", encoding="utf-8")
            best_fit.write_text("fit", encoding="utf-8")
            first_id = profile_backend.save_activity({
                "filename": first_fit.name,
                "sport_type": "running",
                "dist_km": 5.0,
                "duration_sec": 1800,
                "start_time": "2026-07-11T08:00:00Z",
                "file_path": str(first_fit),
                "points_json": [{"distance_m": 5000, "t_sec": 1800}],
            })
            best_id = profile_backend.save_activity({
                "filename": best_fit.name,
                "sport_type": "running",
                "dist_km": 5.0,
                "duration_sec": 1700,
                "start_time": "2026-07-12T08:00:00Z",
                "file_path": str(best_fit),
                "points_json": [{"distance_m": 5000, "t_sec": 1700}],
            })

            conn = profile_backend._conn()
            try:
                career_backend.rebuild_career_record_metric_results(
                    conn,
                    sport="running",
                    record_keys=["running_5k"],
                    dry_run=False,
                )
                before_nodes = _flatten_timeline_nodes(
                    career_backend.get_career_timeline({"type": "record"}, conn)
                )
                assert any(
                    node["event_type"] == "current_best" and node["activity_id"] == str(best_id)
                    for node in before_nodes
                )
                assert not any(
                    node["event_type"] == "record_breaking" and node["activity_id"] == str(best_id)
                    for node in before_nodes
                )
                conn.commit()
            finally:
                conn.close()

            refresh_result = {"ok": True, "reason": "delete_activities"}
            with mock.patch("main._refresh_career_derived_events_safe", return_value=refresh_result):
                result = main.Api.__new__(main.Api).delete_activities([best_id], "DELETE:1")

            assert result["ok"] is True
            assert result["data"]["deleted"] == 1
            conn = profile_backend._conn()
            try:
                timeline = career_backend.get_career_timeline({"type": "record"}, conn)
                nodes = _flatten_timeline_nodes(timeline)
            finally:
                conn.close()

            assert not any(node["activity_id"] == str(best_id) for node in nodes)
            current_best_nodes = [
                node for node in nodes
                if node["event_type"] == "current_best" and node["record_key"] == "running_5k"
            ]
            assert len(current_best_nodes) == 1
            assert current_best_nodes[0]["activity_id"] == str(first_id)
            assert not any(
                node["event_type"] == "record_breaking"
                and (node["activity_id"] == str(best_id) or node["detail_link"]["activity_id"] == str(best_id))
                for node in nodes
            )
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
