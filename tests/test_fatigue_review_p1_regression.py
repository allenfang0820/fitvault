from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_project_file(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def _api_with_mocked_trends():
    from main import Api

    api = Api.__new__(Api)
    api._fetch_historical_metrics_avg = MagicMock(return_value={
        "sample_size": 0,
        "hr_drift_pct": None,
        "decoupling_pct": None,
        "bonk_count": 0,
    })
    api._fetch_efficiency_trend = MagicMock(return_value={
        "level": "flat",
        "compared_count": 0,
        "baseline_ratio": None,
    })
    api._fetch_durability_trend = MagicMock(return_value={
        "level": "flat",
        "compared_count": 0,
        "baseline_ratio": None,
    })
    api._fetch_cadence_stability_trend = MagicMock(return_value={
        "level": "flat",
        "compared_count": 0,
        "baseline_cv": None,
    })
    api._fetch_load_ratio_7d_42d = MagicMock(return_value={
        "ratio": None,
        "level": "unknown",
        "acute_7d": None,
        "chronic_42d": None,
        "compared_count": 0,
    })
    api._fetch_training_load_trend = MagicMock(return_value={
        "level": "flat",
        "compared_count": 0,
        "baseline_load": None,
    })
    return api


def _sample_row(point_count: int = 80) -> dict:
    base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    points = []
    for i in range(point_count):
        points.append({
            "lat": 31.0 + i * 0.00008,
            "lon": 121.0,
            "time": (base + timedelta(seconds=i * 20)).isoformat(),
            "hr": 135 + min(i, 35),
            "speed": 3.2,
            "cadence": 84,
            "alt": 100.0 + i * 1.4,
        })

    return {
        "id": 42,
        "sport_type": "running",
        "dist_km": 7.5,
        "distance": 7500.0,
        "duration_sec": point_count * 20,
        "calories": 1800,
        "track_json": json.dumps(points),
        "points_json": None,
        "merged_track_json": None,
        "hr_curve": json.dumps([p["hr"] for p in points]),
        "speed_curve": json.dumps([p["speed"] for p in points]),
        "cadence_curve": json.dumps([p["cadence"] for p in points]),
    }


def _assert_forbidden_keys_absent(value):
    forbidden = {
        "shadow_diff",
        "shadow_diff_json",
        "diff",
        "records",
        "points",
        "raw_records",
        "track_points",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden)
        for child in value.values():
            _assert_forbidden_keys_absent(child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(child)


def test_p1_resolver_helpers_are_the_only_review_metric_entrypoints():
    main_src = _read_project_file("main.py")
    resolver_src = _read_project_file("metrics_resolver.py")

    assert "MetricsResolver._build_review_decoupling" in main_src
    assert "MetricsResolver._build_bonk_risk" in main_src
    assert "def _build_review_decoupling" in resolver_src
    assert "def _build_bonk_risk" in resolver_src


def test_p1_main_does_not_reintroduce_metric_thresholds():
    main_src = _read_project_file("main.py")

    forbidden_snippets = [
        "total_calories >= 1600.0",
        '"excellent" if decoupling_pct < 5',
        '"good" if decoupling_pct < 10',
        '"warn" if decoupling_pct < 15',
    ]
    for snippet in forbidden_snippets:
        assert snippet not in main_src


def test_p1_fatigue_review_snapshot_keeps_frontend_shape():
    snapshot = _api_with_mocked_trends()._build_fatigue_review_snapshot(_sample_row())

    metrics = snapshot["metrics"]
    for key in ("hr_drift", "decoupling", "bonk_risk", "events"):
        assert key in metrics

    assert {"pct", "level"}.issubset(metrics["decoupling"])
    assert {"is_at_risk", "confidence"}.issubset(metrics["bonk_risk"])
    assert isinstance(snapshot["collapse_events"], list)
    assert isinstance(snapshot["fatigue_zones"], list)
    assert isinstance(snapshot["curves"], dict)


def test_p1_fatigue_review_snapshot_excludes_forbidden_keys():
    snapshot = _api_with_mocked_trends()._build_fatigue_review_snapshot(_sample_row())

    _assert_forbidden_keys_absent(snapshot)


def test_p1_snapshot_keeps_all_review_curve_lanes_populated():
    snapshot = _api_with_mocked_trends()._build_fatigue_review_snapshot(_sample_row())
    curves = snapshot["curves"]
    axis_len = len(curves["distance"])

    assert axis_len > 0
    for key in ("hr", "speed", "gap", "efficiency", "altitude", "grade", "terrain_load"):
        assert len(curves[key]) == axis_len, key
