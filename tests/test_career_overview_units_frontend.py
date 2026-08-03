from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


def extract_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"未找到函数签名: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise AssertionError(f"未找到函数体起始: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"函数体括号不闭合: {signature}")
    return source[brace_start + 1:index - 1]


def test_career_overview_stat_formatters_use_chinese_units() -> None:
    source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    distance_body = extract_function_body(source, "function formatCareerDistanceKm(value)")
    elevation_body = extract_function_body(source, "function formatCareerElevationM(value)")
    weight_body = extract_function_body(source, "function formatCareerWeightKg(value, status)")
    duration_body = extract_function_body(source, "function formatCareerDurationSeconds(value)")

    assert "' km'" not in distance_body
    assert "' m'" not in elevation_body
    assert "' kg'" not in weight_body
    assert "' t'" not in weight_body
    assert "'分'" not in duration_body

    assert "' 公里'" in distance_body
    assert "' 米'" in elevation_body
    assert "' 公斤'" in weight_body
    assert "' 吨'" in weight_body
    assert "'小时'" in duration_body
    assert "'分钟'" in duration_body
    assert "'待生成'" not in weight_body


def test_career_overview_render_binds_unit_formatters_to_metric_cards() -> None:
    source = TRACK_HTML_PATH.read_text(encoding="utf-8")
    body = extract_function_body(source, "function renderCareerOverview(viewModel)")

    for field in (
        "runningDistanceKm",
        "cyclingDistanceKm",
        "walkingHikingDistanceKm",
        "swimmingDistanceKm",
        "strengthTotalWeightKg",
        "maxAltitudeM",
        "totalDuration",
        "longestActivityDistanceKm",
        "maxElevationGainM",
        "totalDistanceKm",
    ):
        assert f"setCareerOverviewField('{field}'" in body

    assert "formatCareerDistanceKm(sportTotals.runningDistanceKm)" in body
    assert "formatCareerWeightKg(sportTotals.strengthTotalWeightKg, sportTotals.strengthTotalWeightStatus)" in body
    assert "formatCareerDurationSeconds(careerStats.totalDurationSeconds)" in body


def test_career_overview_strength_placeholder_uses_default_dash_like_other_cards() -> None:
    source = TRACK_HTML_PATH.read_text(encoding="utf-8")
    assert 'data-career-overview-field="strengthTotalWeightKg">--</span>' in source
    assert 'data-career-overview-field="runningDistanceKm">--</span>' in source
    assert '待生成' not in source
