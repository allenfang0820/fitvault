from __future__ import annotations

from pathlib import Path

from metrics_resolver import MetricsResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_bonk_risk_running_low_without_event():
    risk = MetricsResolver._build_bonk_risk(
        total_calories=1200.0,
        sport_type="running",
        bonk_events=[],
    )

    assert risk["is_at_risk"] is False
    assert risk["risk_level"] == "low"
    assert risk["confidence"] == "low"
    assert risk["zone"] == [1400.0, 1800.0]


def test_build_bonk_risk_running_event_in_moderate_zone():
    risk = MetricsResolver._build_bonk_risk(
        total_calories=1500.0,
        sport_type="running",
        bonk_events=[{"type": "BONK_WARNING"}],
    )

    assert risk["is_at_risk"] is True
    assert risk["risk_level"] == "moderate"
    assert risk["confidence"] == "medium"


def test_build_bonk_risk_cycling_uses_cycling_threshold():
    risk = MetricsResolver._build_bonk_risk(
        total_calories=1700.0,
        sport_type="cycling",
        bonk_events=[{"type": "BONK_WARNING"}],
    )

    assert risk["is_at_risk"] is False
    assert risk["risk_level"] == "low"
    assert risk["zone"] == [1800.0, 2400.0]


def test_build_bonk_risk_zero_calories_unavailable():
    risk = MetricsResolver._build_bonk_risk(
        total_calories=0.0,
        sport_type="running",
        bonk_events=[{"type": "BONK_WARNING"}],
    )

    assert risk["is_at_risk"] is False
    assert risk["risk_level"] == "unknown"
    assert risk["confidence"] == "unavailable"


def test_main_no_longer_hardcodes_bonk_1600_threshold():
    main_src = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "total_calories >= 1600.0" not in main_src
    assert "MetricsResolver._build_bonk_risk" in main_src
