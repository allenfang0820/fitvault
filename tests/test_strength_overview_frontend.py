from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "track.html").read_text(encoding="utf-8")
VENDORED_UMD = ROOT / "lib" / "body-muscles" / "body-muscles.umd.min.js"


def test_body_muscles_is_local_pinned_and_licensed() -> None:
    assert '<script src="lib/body-muscles/body-muscles.umd.min.js"></script>' in HTML
    assert "unpkg.com/body-muscles" not in HTML
    assert "cdn.jsdelivr.net/npm/body-muscles" not in HTML
    assert VENDORED_UMD.stat().st_size == 29293
    assert hashlib.sha256(VENDORED_UMD.read_bytes()).hexdigest() == (
        "fe4cd10dd3e982803621d0737d8610ad5b408055f6cb916aebb3a72a8a547aa8"
    )
    assert (ROOT / "lib" / "body-muscles" / "LICENSE").exists()
    assert (ROOT / "lib" / "body-muscles" / "NOTICE").exists()


def test_structured_strength_has_dedicated_layout_not_track_thumbnail_layout() -> None:
    assert 'id="activity-detail-strength-root"' in HTML
    assert 'id="activity-detail-standard-overview"' in HTML
    assert "primaryVisual === 'strength_muscle_map'" in HTML
    assert "standardOverview.hidden = true" in HTML
    assert "grid-template-columns: minmax(520px, 1.25fr) minmax(360px, 0.9fr)" in HTML
    assert ".strength-body-views" in HTML
    assert "min-height: 420px" in HTML
    assert ".overview-2x2[hidden]" in HTML
    assert "display: none !important" in HTML


def test_non_outdoor_standard_overview_removes_track_and_lap_modules() -> None:
    assert 'id="activity-detail-overview-main"' in HTML
    assert "var showTrackModule = primaryVisual === 'track_map' && hasTrackVisual" in HTML
    assert "trackSection.hidden = !showTrackModule" in HTML
    assert "splitArea.hidden = !_usesSplitTable" in HTML
    assert "splitSection !== 'laps' || isEnduranceOutdoor" in HTML
    assert "is-facts-only" in HTML
    assert "本次不需要轨迹地图" not in HTML
    assert "训练记录摘要<br>" not in HTML


def test_strength_layout_has_front_back_desktop_and_mobile_modes() -> None:
    assert "data-strength-chart=\"front\"" in HTML
    assert "data-strength-chart=\"back\"" in HTML
    assert "new library.BodyChart(frontHost" in HTML
    assert "new library.BodyChart(backHost" in HTML
    assert "@media (max-width: 759px)" in HTML
    assert 'data-mobile-view="front"' in HTML
    assert 'data-mobile-view="back"' in HTML
    assert "_setStrengthMobileView" in HTML


def test_strength_metrics_only_read_backend_strength_summary() -> None:
    for field in (
        "strength_exercise_count",
        "strength_working_set_count",
        "strength_total_reps",
        "strength_total_volume_kg",
    ):
        assert field in HTML
    assert "strengthSummary.distinct_exercise_count" in HTML
    assert "strengthSummary.working_set_count" in HTML
    assert "strengthSummary.total_reps" in HTML
    assert "strengthSummary.total_volume_kg" in HTML
    assert "reps * weight" not in HTML


def test_strength_interactions_are_mouse_keyboard_touch_and_state_safe() -> None:
    assert "onMuscleClick: onClick" in HTML
    assert "onMuscleHover: onHover" in HTML
    assert "event.key === 'Enter' || event.key === ' '" in HTML
    assert "row.addEventListener('click', selectRow)" in HTML
    assert "_destroyStrengthOverviewCharts" in HTML
    assert "_resetStrengthOverview" in HTML
    assert "chart.destroy()" in HTML
    assert "_strengthEscape(exercise.exercise_name" in HTML
    assert "_strengthLevelLabel" in HTML
    assert "path.setAttribute('aria-hidden', 'true')" in HTML
    assert "path.style.pointerEvents = 'none'" in HTML


def test_strength_partial_and_unmapped_states_remain_visible() -> None:
    assert "组未映射" in HTML
    assert "已记录动作暂未建立肌群映射" in HTML
    assert "if (viewToggle) viewToggle.hidden = true" in HTML
    assert "自重/未记录" in HTML
    assert "未识别动作不会进入肌肉图" in HTML
    assert "相对分布，不代表疲劳" in HTML


def test_strength_materialization_states_use_distinct_fact_copy() -> None:
    for text in (
        "正在补全训练数据",
        "本次活动未记录可用的动作组",
        "原始训练文件当前不可用",
        "训练数据补全未完成",
        "可以稍后重试",
    ):
        assert text in HTML
    for message_code in (
        "strength_materialization_pending",
        "strength_sets_not_recorded",
        "strength_source_unavailable",
        "strength_materialization_failed",
        "strength_materialization_ready",
    ):
        assert message_code in HTML
    assert "strength_materialization_error" not in HTML


def test_pending_strength_refresh_is_single_start_bounded_and_state_safe() -> None:
    assert "STRENGTH_MATERIALIZATION_POLL_MAX_ATTEMPTS = 6" in HTML
    assert "STRENGTH_MATERIALIZATION_POLL_INTERVAL_MS = 1500" in HTML
    assert "if (!_strengthMaterializationRefreshState.started)" in HTML
    assert "start_strength_materialization_backfill({ limit: 25 })" in HTML
    assert "get_strength_materialization_backfill_status()" in HTML
    assert "fetchSportHubActivityDetail(activityId)" in HTML
    assert "status !== 'pending'" in HTML
    assert "_strengthMaterializationRefreshState.attempts >= STRENGTH_MATERIALIZATION_POLL_MAX_ATTEMPTS" in HTML
    assert HTML.count("_stopStrengthMaterializationRefresh();") >= 5
    assert "sportHubState.activeDetailId !== activityId" in HTML


def test_strength_poc_supports_unmapped_and_library_fallback_modes() -> None:
    poc = (ROOT / "tests" / "fixtures" / "strength_overview_poc.html").read_text(encoding="utf-8")
    assert "pocParams.get('mode') === 'unmapped'" in poc
    assert "pocParams.get('library') === 'missing'" in poc
