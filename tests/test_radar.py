from unittest import mock

import main


def test_get_rolling_radar_metrics_returns_current_api_envelope():
    api = main.Api.__new__(main.Api)
    metrics = {
        "ctl": 42,
        "metrics_version": main.CURRENT_METRICS_VERSION,
        "expected_metrics_version": main.CURRENT_METRICS_VERSION,
        "needs_rebuild": False,
        "radar": {
            "type": "running",
            "dimensions": [
                {"key": "endurance", "label": "耐力", "score": 75},
            ],
        },
    }

    with mock.patch("main._rolling_aggregate_radar_metrics", return_value=metrics) as aggregate:
        result = api.get_rolling_radar_metrics("running")

    assert result == {"ok": True, "metrics": metrics}
    aggregate.assert_called_once_with("running")


def test_get_rolling_radar_metrics_returns_fallback_envelope_on_error():
    api = main.Api.__new__(main.Api)

    with mock.patch("main._rolling_aggregate_radar_metrics", side_effect=RuntimeError("boom")):
        result = api.get_rolling_radar_metrics("cycling")

    assert result["ok"] is False
    assert "boom" in result["error"]
    assert result["metrics"]["radar"] == {"type": "cycling", "dimensions": []}
    assert result["metrics"]["expected_metrics_version"] == main.CURRENT_METRICS_VERSION
