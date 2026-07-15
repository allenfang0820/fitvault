from __future__ import annotations

from pathlib import Path

from metrics_resolver import MetricsResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_review_decoupling_stable_excellent():
    decoupling = MetricsResolver._build_review_decoupling(
        [1.0] * 10 + [0.98] * 10
    )

    assert decoupling["pct"] == 2.0
    assert decoupling["change_pct"] == -2.0
    assert decoupling["decline_pct"] == 2.0
    assert decoupling["direction"] == "stable"
    assert decoupling["level"] == "excellent"
    assert decoupling["confidence"] == "medium"


def test_build_review_decoupling_late_decline_warn():
    decoupling = MetricsResolver._build_review_decoupling(
        [1.0] * 10 + [0.88] * 10
    )

    assert decoupling["pct"] == 12.0
    assert decoupling["change_pct"] == -12.0
    assert decoupling["decline_pct"] == 12.0
    assert decoupling["direction"] == "declined"
    assert decoupling["level"] == "warn"


def test_build_review_decoupling_late_improvement_is_positive_direction():
    decoupling = MetricsResolver._build_review_decoupling(
        [1.0] * 10 + [1.2] * 10
    )

    assert decoupling["pct"] == 0.0
    assert decoupling["change_pct"] == 20.0
    assert decoupling["decline_pct"] == 0.0
    assert decoupling["direction"] == "improved"
    assert decoupling["level"] == "excellent"


def test_build_review_decoupling_insufficient_data_keeps_legacy_empty_shape():
    decoupling = MetricsResolver._build_review_decoupling([1.0])

    assert decoupling["pct"] == 0.0
    assert decoupling["direction"] == "unknown"
    assert decoupling["change_pct"] is None
    assert decoupling["decline_pct"] is None
    assert decoupling["level"] == "unknown"


def test_main_uses_resolver_for_review_decoupling():
    main_src = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    assert "MetricsResolver._build_review_decoupling" in main_src
    assert '"excellent" if decoupling_pct < 5' not in main_src
    assert '"good" if decoupling_pct < 10' not in main_src
    assert '"warn" if decoupling_pct < 15' not in main_src
