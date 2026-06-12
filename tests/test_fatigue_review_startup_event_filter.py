from __future__ import annotations

from main import _build_fatigue_review_collapse_events


def test_startup_fatigue_zone_does_not_create_collapse_event():
    events = _build_fatigue_review_collapse_events(
        bonk_events=[],
        fatigue_zones=[{"start_km": 0.0, "end_km": 0.08, "level": "high"}],
    )

    fatigue_event_types = {
        "FATIGUE_DRIFT_START",
        "EFFICIENCY_DROP",
        "SUSTAINED_FATIGUE",
    }
    assert not any(ev["type"] in fatigue_event_types for ev in events)


def test_mid_run_fatigue_zone_still_creates_collapse_event():
    events = _build_fatigue_review_collapse_events(
        bonk_events=[],
        fatigue_zones=[{"start_km": 3.0, "end_km": 4.0, "level": "high"}],
    )

    event_types = {ev["type"] for ev in events}
    assert "FATIGUE_DRIFT_START" in event_types
    assert events[0]["trigger_km"] == 3.0


def test_startup_bonk_event_is_not_filtered():
    events = _build_fatigue_review_collapse_events(
        bonk_events=[
            {
                "type": "BONK_WARNING",
                "trigger_km": 0.05,
                "value_y": 0.04,
                "description": "test bonk",
            }
        ],
        fatigue_zones=[],
    )

    assert len(events) == 1
    assert events[0]["type"] == "BONK_WARNING"
    assert events[0]["trigger_km"] == 0.05


def test_startup_zone_filtered_but_later_zone_remains():
    events = _build_fatigue_review_collapse_events(
        bonk_events=[],
        fatigue_zones=[
            {"start_km": 0.0, "end_km": 0.08, "level": "high"},
            {"start_km": 2.0, "end_km": 3.0, "level": "high"},
        ],
    )

    assert events
    assert all((ev.get("trigger_km") or 0.0) >= 0.1 for ev in events)
