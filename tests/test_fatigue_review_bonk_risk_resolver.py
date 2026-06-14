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


def test_build_bonk_risk_preserves_high_confidence_event_window():
    risk = MetricsResolver._build_bonk_risk(
        total_calories=2100.0,
        sport_type="running",
        bonk_events=[{
            "type": "BONK_WARNING",
            "confidence": "high",
            "risk_start_km": 28.4,
            "risk_end_km": 31.2,
            "evidence": ["EI持续下降约18%", "速度/配速同步变差"],
        }],
    )

    assert risk["is_at_risk"] is True
    assert risk["confidence"] == "high"
    assert risk["risk_start_km"] == 28.4
    assert risk["risk_end_km"] == 31.2
    assert "evidence" in risk


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


def _distance_curve(total_km: float, n: int = 120) -> list[float]:
    step_m = total_km * 1000.0 / (n - 1)
    return [i * step_m for i in range(n)]


def test_detect_bonk_event_uses_sustained_window_not_half_anchor():
    n = 120
    distance = _distance_curve(42.2, n)
    # Stable through 30 km, then sustained efficiency and speed decline.
    ei = [1.0] * 86 + [0.82 - min(i, 20) * 0.004 for i in range(34)]
    speed = [3.2] * 86 + [2.85 - min(i, 20) * 0.01 for i in range(34)]
    hr = [152] * 86 + [158] * 34
    cadence = [176] * 86 + [168] * 34

    events = MetricsResolver._detect_bonk_event(
        distance_curve=distance,
        ei_curve=ei,
        total_calories=2600.0,
        sport_type="running",
        time_curve=[i * 180 for i in range(n)],
        speed_curve=speed,
        hr_curve=hr,
        cadence_curve=cadence,
        weight_kg=68,
        avg_hr=158,
        profile_max_hr=190,
        profile_resting_hr=48,
        lactate_threshold_hr=172,
    )

    assert len(events) == 1
    event = events[0]
    assert event["type"] == "BONK_WARNING"
    assert event["title"] == "能量断档风险线索"
    assert event["risk_start_km"] > 28.0
    assert abs(event["risk_start_km"] - 21.1) > 3.0
    assert event["trigger_km"] == event["risk_start_km"]
    assert event["risk_end_km"] > event["risk_start_km"]
    assert event["confidence"] in {"medium", "high"}
    assert "不代表精确撞墙坐标" in event["description"]


def test_detect_bonk_event_low_energy_short_easy_run_has_no_pin():
    n = 80
    distance = _distance_curve(8.0, n)
    ei = [1.0 - i * 0.0005 for i in range(n)]
    events = MetricsResolver._detect_bonk_event(
        distance_curve=distance,
        ei_curve=ei,
        total_calories=520.0,
        sport_type="running",
        time_curve=[i * 45 for i in range(n)],
        speed_curve=[2.6] * n,
        hr_curve=[128] * n,
        weight_kg=70,
        avg_hr=128,
        profile_max_hr=190,
        profile_resting_hr=50,
    )

    assert events == []


def test_detect_bonk_event_energy_without_performance_evidence_has_no_pin():
    n = 120
    distance = _distance_curve(42.2, n)
    events = MetricsResolver._detect_bonk_event(
        distance_curve=distance,
        ei_curve=[1.0] * n,
        total_calories=2600.0,
        sport_type="running",
        time_curve=[i * 180 for i in range(n)],
        speed_curve=[3.1] * n,
        hr_curve=[156] * n,
        weight_kg=68,
        avg_hr=156,
        profile_max_hr=190,
        profile_resting_hr=48,
        lactate_threshold_hr=172,
    )

    assert events == []


def test_resolved_payload_uses_resolver_sampled_axis_for_energy_event(monkeypatch):
    import main

    n_raw = 300
    n_sampled = 200
    sampled_distance = _distance_curve(42.2, n_sampled)
    sampled_ei = [1.0] * 142 + [0.82 - min(i, 20) * 0.004 for i in range(58)]
    sampled_speed = [3.2] * 142 + [2.85 - min(i, 20) * 0.01 for i in range(58)]
    sampled_hr = [152] * 142 + [158] * 58

    class FakeResolver(MetricsResolver):
        def resolve(self, raw, meta):
            return {
                "distance_curve": sampled_distance,
                "time_curve": [i * 120 for i in range(n_sampled)],
                "altitude_curve": [100.0] * n_sampled,
                "gap_curve": [3.0] * n_sampled,
                "grade_curve": [0.0] * n_sampled,
                "efficiency_curve": sampled_ei,
                "hr_curve": sampled_hr,
                "speed_curve": sampled_speed,
                "cadence_curve": [176] * n_sampled,
                "context_tags": {},
            }

    monkeypatch.setattr(main, "MetricsResolver", FakeResolver)
    bundle = {
        "records": [{"timestamp": object(), "distance": i * 100.0} for i in range(n_raw)],
        "distance_curve_m": _distance_curve(42.2, n_raw),
        "time_curve_sec": [i * 80 for i in range(n_raw)],
        "altitude_curve_m": [100.0] * n_raw,
        "hr_curve": [152] * n_raw,
        "speed_curve_mps": [3.2] * n_raw,
        "cadence_curve": [176] * n_raw,
        "power_curve": [],
        "total_distance_m": 42200.0,
        "duration_sec": 24000,
        "calories": 2600.0,
        "avg_heart_rate": 158,
        "profile_max_hr": 190,
        "profile_resting_hr": 48,
        "profile_weight_kg": 68,
        "lactate_threshold_hr": 172,
    }

    payload = main._build_resolved_payload_v81(bundle, "running")

    assert len(payload["distance_curve"]) == n_sampled
    assert len(payload["efficiency_curve"]) == n_sampled
    assert len(payload["speed_curve"]) == n_sampled
    assert len(payload["altitude_curve"]) == n_sampled
    assert payload["insight_events"]
    assert payload["insight_events"][0]["risk_start_km"] > 27.0
    assert abs(payload["insight_events"][0]["risk_start_km"] - 21.1) > 3.0


def test_resolved_payload_resamples_altitude_when_resolver_axis_is_sampled(monkeypatch):
    import main

    n_raw = 300
    n_sampled = 120
    sampled_distance = _distance_curve(8.3, n_sampled)

    class FakeResolver(MetricsResolver):
        def resolve(self, raw, meta):
            return {
                "distance_curve": sampled_distance,
                "time_curve": [i * 180 for i in range(n_sampled)],
                "gap_curve": [1.2] * n_sampled,
                "grade_curve": [4.0] * n_sampled,
                "efficiency_curve": [0.02] * n_sampled,
                "hr_curve": [132] * n_sampled,
                "speed_curve": [0.32] * n_sampled,
                "cadence_curve": [80] * n_sampled,
                "context_tags": {},
            }

    monkeypatch.setattr(main, "MetricsResolver", FakeResolver)
    bundle = {
        "records": [{"timestamp": object(), "distance": i * 28.0} for i in range(n_raw)],
        "distance_curve_m": _distance_curve(8.3, n_raw),
        "time_curve_sec": [i * 90 for i in range(n_raw)],
        "altitude_curve_m": [700.0 + i * 3.0 for i in range(n_raw)],
        "hr_curve": [132] * n_raw,
        "speed_curve_mps": [0.32] * n_raw,
        "cadence_curve": [80] * n_raw,
        "power_curve": [],
        "total_distance_m": 8300.0,
        "duration_sec": 26000,
        "calories": 2600.0,
        "avg_heart_rate": 132,
        "profile_max_hr": 186,
        "profile_resting_hr": 52,
        "profile_weight_kg": 72.9,
        "lactate_threshold_hr": 166,
    }

    payload = main._build_resolved_payload_v81(bundle, "mountaineering")

    assert len(payload["distance_curve"]) == n_sampled
    assert len(payload["altitude_curve"]) == n_sampled
    assert payload["altitude_curve"][0] == 700.0
    assert payload["altitude_curve"][-1] > payload["altitude_curve"][0]


def test_main_no_longer_hardcodes_bonk_1600_threshold():
    main_src = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "total_calories >= 1600.0" not in main_src
    assert "MetricsResolver._build_bonk_risk" in main_src
