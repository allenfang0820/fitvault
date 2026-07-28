from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import main
import profile_backend


ROOT = Path(__file__).resolve().parents[1]


def test_task01_contract_summary_refresh_rules_exist():
    text = (ROOT / "docs/personal_sport_data_performance_contract_summary.md").read_text(encoding="utf-8")
    assert "从 Task 02 开始" in text
    assert "重新全文阅读相关原始契约" in text
    assert "重要偏离触发条件" in text


def test_task01_frontend_perf_events_are_minimal_and_safe():
    html = (ROOT / "track.html").read_text(encoding="utf-8")
    required_events = [
        "activity_list_api_done",
        "activity_list_render_done",
        "activity_detail_api_done",
        "activity_detail_render_done",
        "fatigue_review_api_done",
        "fatigue_review_panels_done",
        "fatigue_review_chart_done",
    ]
    for event_name in required_events:
        assert event_name in html

    for event_name in required_events:
        marker = f"markStartupPhase('{event_name}'"
        start = html.index(marker)
        snippet = html[start : start + 900]
        assert "payload_bytes" in snippet or "_ms" in snippet or "curve_points" in snippet
        assert "track_points" not in snippet
        assert "raw_points" not in snippet
        assert "curves:" not in snippet
        assert "raw_records" not in snippet


def test_task01_api_contract_documents_elapsed_fields():
    contract = json.loads((ROOT / "docs/js_api_contract.json").read_text(encoding="utf-8"))
    by_name = {item.get("name"): item for item in contract.get("methods", [])}
    for name in ("get_activity_list", "get_sport_hub_activity_page", "get_activity_detail", "get_fatigue_review"):
        returns = by_name[name].get("returns", "")
        assert "api_elapsed_ms" in returns
    assert "cache_status" in by_name["get_fatigue_review"].get("returns", "")


def test_task09_temporary_frontend_performance_button_and_bridge_are_removed():
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    html = (ROOT / "track.html").read_text(encoding="utf-8")
    contract = json.loads((ROOT / "docs/js_api_contract.json").read_text(encoding="utf-8"))
    by_name = {item.get("name"): item for item in contract.get("methods", [])}

    assert "showFatigueReviewPerformanceDiagnostics" not in html
    assert "record_frontend_performance_events" not in html
    assert "get_frontend_performance_trace" not in html
    assert "queueFrontendPerformanceDiagnostic" not in html
    assert "FRONTEND_PERF_EVENT_MAX_STORED" not in main_text
    assert "def record_frontend_performance_events" not in main_text
    assert "def get_frontend_performance_trace" not in main_text
    assert "record_frontend_performance_events" not in by_name
    assert "get_frontend_performance_trace" not in by_name
    assert "review_backend_profile" in by_name["get_fatigue_review"].get("returns", "")


def test_task10_review_backend_profile_is_response_only_and_safe(tmp_path, monkeypatch):
    db_path = tmp_path / "profile.sqlite"
    _seed_profile_schema_sentinel(db_path)
    monkeypatch.setattr(profile_backend, "DB_PATH", db_path)
    monkeypatch.setattr(profile_backend, "_SCHEMA_READY_FOR", None)

    row = {
        "id": 1001,
        "updated_at": "2026-07-27T10:00:00",
        "processing_status": "ready",
        "sport_type": "running",
    }
    api = main.Api()
    api._fetch_activity_row = lambda activity_id: dict(row)
    api._build_fatigue_review_snapshot = lambda activity_row: {
        "sport_type": "running",
        "summary": {},
        "metrics": {},
        "curves": {"distance": [0, 1, 2], "hr": [120, 130, 140]},
        "display_curves": {},
        "ai_insight": None,
    }

    first = api.get_fatigue_review(1001)
    second = api.get_fatigue_review(1001)

    assert first["data"]["cache_status"] == "miss"
    assert second["data"]["cache_status"] == "hit"
    for response in (first, second):
        profile = response["data"].get("review_backend_profile")
        assert profile["storage"] == "response_diagnostic"
        assert profile["event_count"] >= 1
        encoded = json.dumps(profile, ensure_ascii=False)
        for forbidden in ("raw_points", "records", "track_json", "points_json", "curves", "title", "file_path"):
            assert forbidden not in encoded

    conn = sqlite3.connect(db_path)
    try:
        cached = conn.execute(
            "SELECT payload_json FROM fatigue_review_snapshot_cache WHERE activity_id = 1001"
        ).fetchone()
    finally:
        conn.close()
    assert cached is not None
    assert "review_backend_profile" not in cached[0]


def test_task10_review_history_curve_queries_are_windowed_before_large_json_fetch():
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "def _fetch_review_history_curve_candidates" in main_text
    assert "_activity_history_coarse_time_filter" in main_text
    assert "SELECT id, {time_select_sql}, {derived_select_sql}" in main_text
    assert "SELECT id, {track_select_sql}, {points_select_sql}" in main_text
    contract = json.loads((ROOT / "docs/js_api_contract.json").read_text(encoding="utf-8"))
    by_name = {item.get("name"): item for item in contract.get("methods", [])}
    assert "review_backend_profile" in by_name["get_fatigue_review"].get("returns", "")
    assert "response_diagnostic" in by_name["get_fatigue_review"].get("returns", "")


def test_task01_benchmark_script_is_readonly():
    text = (ROOT / "scripts/benchmark_personal_sport_data.py").read_text(encoding="utf-8")
    forbidden_tokens = ["INSERT ", "UPDATE ", "DELETE ", "commit("]
    for token in forbidden_tokens:
        assert token not in text
    assert "get_sport_hub_activity_page" in text
    assert "get_activity_detail" in text
    assert "get_fatigue_review" in text


def test_task02_activity_list_query_avoids_large_track_json_fields():
    text = (ROOT / "profile_backend.py").read_text(encoding="utf-8")
    start = text.index("def get_activity_list_filtered(")
    end = text.index("# 别名保持向后兼容", start)
    body = text[start:end]
    sql_start = body.index("page_cte =")
    sql_body = body[sql_start:]

    assert "track_json" not in sql_body
    assert "points_json" not in sql_body
    assert "COUNT(DISTINCT" in sql_body
    assert "GROUP BY" in sql_body
    assert "LIMIT ? OFFSET ?" in sql_body


def test_task03_profile_schema_sentinel_skips_full_init(tmp_path):
    db_path = tmp_path / "profile.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE app_migrations (key TEXT PRIMARY KEY, status TEXT, updated_at TEXT, details_json TEXT)")
    conn.execute(
        "INSERT INTO app_migrations (key, status, updated_at, details_json) VALUES (?, 'done', datetime('now'), '{}')",
        (profile_backend.PROFILE_SCHEMA_SENTINEL_KEY,),
    )
    conn.commit()
    conn.close()

    old_db_path = profile_backend.DB_PATH
    old_schema_ready = profile_backend._SCHEMA_READY_FOR
    try:
        profile_backend.DB_PATH = db_path
        profile_backend._SCHEMA_READY_FOR = None
        profile_backend._conn().close()
        check = sqlite3.connect(db_path)
        try:
            row = check.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user_profile'"
            ).fetchone()
            assert row is None
        finally:
            check.close()
    finally:
        profile_backend.DB_PATH = old_db_path
        profile_backend._SCHEMA_READY_FOR = old_schema_ready


def test_task03_activity_sync_schema_sentinel_skips_heavy_updates(tmp_path):
    db_path = tmp_path / "activity.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE app_migrations (key TEXT PRIMARY KEY, status TEXT, updated_at TEXT, details_json TEXT)")
    conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY)")
    conn.execute(
        "INSERT INTO app_migrations (key, status, updated_at, details_json) VALUES (?, 'done', datetime('now'), '{}')",
        (main.ACTIVITY_SYNC_SCHEMA_SENTINEL_KEY,),
    )
    conn.commit()
    conn.close()

    old_db_path = profile_backend.DB_PATH
    old_profile_schema = profile_backend._SCHEMA_READY_FOR
    old_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
    try:
        profile_backend.DB_PATH = db_path
        profile_backend._SCHEMA_READY_FOR = str(db_path.resolve())
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None

        main.ensure_activity_sync_schema()

        assert main._ACTIVITY_SYNC_SCHEMA_READY_FOR == str(db_path.resolve())
    finally:
        profile_backend.DB_PATH = old_db_path
        profile_backend._SCHEMA_READY_FOR = old_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = old_main_schema


def test_task04_detail_summary_contract_is_lightweight_and_progressive():
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    start = main_text.index("DETAIL_SUMMARY_API_COLUMNS")
    end = main_text.index("API_CODE_EXTERNAL_SERVICE", start)
    summary_columns = main_text[start:end]
    for forbidden in ("track_json", "points_json", "laps_json", "hr_curve", "speed_curve", "cadence_curve"):
        assert forbidden not in summary_columns
    assert "def get_activity_detail_summary" in main_text
    assert '"detail_pending": True' in main_text
    assert '"detail_pending": False' in main_text

    html = (ROOT / "track.html").read_text(encoding="utf-8")
    assert "get_activity_detail_summary" in html
    assert "activity_detail_summary_api_done" in html
    assert "activity_detail_summary_render_done" in html
    assert "!cached.detail_pending" in html
    assert "summary_first" in html

    contract = json.loads((ROOT / "docs/js_api_contract.json").read_text(encoding="utf-8"))
    by_name = {item.get("name"): item for item in contract.get("methods", [])}
    assert "get_activity_detail_summary" in by_name
    assert "detail_pending=true" in by_name["get_activity_detail_summary"].get("returns", "")


def _seed_profile_schema_sentinel(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE app_migrations (key TEXT PRIMARY KEY, status TEXT, updated_at TEXT, details_json TEXT)"
        )
        conn.execute(
            "INSERT INTO app_migrations (key, status, updated_at, details_json) VALUES (?, 'done', datetime('now'), '{}')",
            (profile_backend.PROFILE_SCHEMA_SENTINEL_KEY,),
        )
        conn.commit()
    finally:
        conn.close()


def test_task05_fatigue_review_cache_hit_skips_snapshot_build_and_ai_content(tmp_path, monkeypatch):
    db_path = tmp_path / "profile.sqlite"
    _seed_profile_schema_sentinel(db_path)
    monkeypatch.setattr(profile_backend, "DB_PATH", db_path)
    monkeypatch.setattr(profile_backend, "_SCHEMA_READY_FOR", None)

    row = {
        "id": 501,
        "updated_at": "2026-07-23T10:00:00",
        "processing_status": "ready",
        "sport_type": "running",
    }
    build_calls = []
    api = main.Api()
    api._fetch_activity_row = lambda activity_id: dict(row)

    def build_snapshot(activity_row):
        build_calls.append(activity_row["updated_at"])
        return {
            "sport_type": "running",
            "summary": {"duration_sec": 1800},
            "metrics": {"hr_drift": {"level": "flat"}},
            "curves": {"distance": [0, 1]},
            "ai_insight": {"text": "generated text must not be cached"},
        }

    api._build_fatigue_review_snapshot = build_snapshot

    first = api.get_fatigue_review(501)
    second = api.get_fatigue_review(501)

    assert first["ok"] is True
    assert first["data"]["cache_status"] == "miss"
    assert second["ok"] is True
    assert second["data"]["cache_status"] == "hit"
    assert second["data"]["summary"] == {"duration_sec": 1800}
    assert second["data"]["ai_insight"] is None
    assert build_calls == ["2026-07-23T10:00:00"]


def test_task05_fatigue_review_cache_invalidates_on_activity_or_version_change(tmp_path, monkeypatch):
    db_path = tmp_path / "profile.sqlite"
    _seed_profile_schema_sentinel(db_path)
    monkeypatch.setattr(profile_backend, "DB_PATH", db_path)
    monkeypatch.setattr(profile_backend, "_SCHEMA_READY_FOR", None)

    row = {
        "id": 502,
        "updated_at": "2026-07-23T10:00:00",
        "processing_status": "ready",
        "sport_type": "running",
    }
    build_calls = []
    api = main.Api()
    api._fetch_activity_row = lambda activity_id: dict(row)

    def build_snapshot(activity_row):
        build_calls.append(activity_row["updated_at"])
        return {
            "sport_type": "running",
            "review_profile": "endurance_outdoor",
            "not_applicable_reason": None,
            "available_review_facts": {"duration_sec": 1800},
            "summary": {"updated_at": activity_row["updated_at"]},
            "metrics": {},
            "curves": {},
            "ai_insight": None,
        }

    api._build_fatigue_review_snapshot = build_snapshot

    assert api.get_fatigue_review(502)["data"]["cache_status"] == "miss"
    assert api.get_fatigue_review(502)["data"]["cache_status"] == "hit"

    row["updated_at"] = "2026-07-23T11:00:00"
    assert api.get_fatigue_review(502)["data"]["cache_status"] == "miss"
    assert api.get_fatigue_review(502)["data"]["cache_status"] == "hit"

    monkeypatch.setattr(main, "FATIGUE_REVIEW_CACHE_VERSION", "fatigue_review_snapshot_test_next")
    refreshed = api.get_fatigue_review(502)
    assert refreshed["data"]["cache_status"] == "miss"
    assert refreshed["data"]["review_profile"] == "endurance_outdoor"
    assert refreshed["data"]["not_applicable_reason"] is None
    assert refreshed["data"]["available_review_facts"] == {"duration_sec": 1800}
    assert build_calls == [
        "2026-07-23T10:00:00",
        "2026-07-23T11:00:00",
        "2026-07-23T11:00:00",
    ]


def test_task06_fatigue_review_defaults_to_sampled_curves_and_full_on_demand(tmp_path, monkeypatch):
    db_path = tmp_path / "profile.sqlite"
    _seed_profile_schema_sentinel(db_path)
    monkeypatch.setattr(profile_backend, "DB_PATH", db_path)
    monkeypatch.setattr(profile_backend, "_SCHEMA_READY_FOR", None)

    axis_len = 3000
    event_index = 1777
    zone_start_index = 900
    zone_end_index = 2100
    distance = [round(index * 0.01, 3) for index in range(axis_len)]
    hr = [130 + (index % 30) for index in range(axis_len)]
    hr[event_index] = 222
    speed = [3.0 + ((index % 11) / 10.0) for index in range(axis_len)]
    altitude = [100 + (index % 100) for index in range(axis_len)]
    altitude[2401] = 1888
    pace = [300 + (index % 50) for index in range(axis_len)]
    row = {
        "id": 601,
        "updated_at": "2026-07-24T09:00:00",
        "processing_status": "ready",
        "sport_type": "running",
    }
    build_calls = []
    api = main.Api()
    api._fetch_activity_row = lambda activity_id: dict(row)

    def build_snapshot(activity_row):
        build_calls.append(activity_row["updated_at"])
        return {
            "sport_type": "running",
            "summary": {},
            "metrics": {},
            "collapse_events": [{"trigger_km": distance[event_index], "value_y": hr[event_index]}],
            "fatigue_zones": [
                {"start_km": distance[zone_start_index], "end_km": distance[zone_end_index], "level": "medium"}
            ],
            "curves": {
                "distance": distance,
                "time": list(range(axis_len)),
                "hr": hr,
                "speed": speed,
                "altitude": altitude,
                "grade": [0.1 for _ in range(axis_len)],
                "gap": speed,
                "efficiency": [0.8 for _ in range(axis_len)],
                "terrain_load": [0.2 for _ in range(axis_len)],
                "power": [],
                "cadence": [],
                "total_distance_m": distance[-1] * 1000,
            },
            "display_curves": {
                "pace_sec_per_km": pace,
                "pace_raw_sec_per_km": pace,
                "pace_capped": [False for _ in range(axis_len)],
                "gap_pace_sec_per_km": pace,
                "gap_pace_raw_sec_per_km": pace,
                "gap_pace_capped": [False for _ in range(axis_len)],
            },
            "ai_insight": None,
        }

    api._build_fatigue_review_snapshot = build_snapshot

    sampled = api.get_fatigue_review(601)
    sampled_data = sampled["data"]
    sampled_distance = sampled_data["curves"]["distance"]
    assert sampled["ok"] is True
    assert sampled_data["cache_status"] == "miss"
    assert sampled_data["curve_resolution"] == "sampled"
    assert sampled_data["curve_points_original"] == axis_len
    assert 0 < sampled_data["curve_points_returned"] <= main.FATIGUE_REVIEW_CURVE_SAMPLE_MAX_POINTS
    assert len(sampled_distance) == sampled_data["curve_points_returned"]
    assert len(sampled_data["display_curves"]["pace_sec_per_km"]) == len(sampled_distance)
    assert sampled_distance[0] == distance[0]
    assert sampled_distance[-1] == distance[-1]
    assert distance[event_index] in sampled_distance
    assert hr[event_index] in sampled_data["curves"]["hr"]
    assert altitude[2401] in sampled_data["curves"]["altitude"]
    assert sampled_data["full_curves_available"] is True

    full = api.get_fatigue_review(601, "full")
    full_data = full["data"]
    assert full["ok"] is True
    assert full_data["cache_status"] == "hit"
    assert full_data["curve_resolution"] == "full"
    assert full_data["curve_points_original"] == axis_len
    assert full_data["curve_points_returned"] == axis_len
    assert len(full_data["curves"]["distance"]) == axis_len
    assert build_calls == ["2026-07-24T09:00:00"]


def test_task06_curve_resolution_contract_is_documented():
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "def get_fatigue_review(self, activity_id: int, curve_resolution: Any = None)" in main_text
    assert "_prepare_fatigue_review_snapshot_for_response" in main_text
    assert "FATIGUE_REVIEW_CURVE_SAMPLE_TARGET_POINTS" in main_text

    contract = json.loads((ROOT / "docs/js_api_contract.json").read_text(encoding="utf-8"))
    by_name = {item.get("name"): item for item in contract.get("methods", [])}
    returns = by_name["get_fatigue_review"].get("returns", "")
    assert "curve_resolution" in returns
    assert "curve_points_original" in returns
    assert "full_curves_available" in returns

    html = (ROOT / "track.html").read_text(encoding="utf-8")
    assert "curve_resolution: data.curve_resolution" in html
    assert "curve_points_original" in html


def test_task07_historical_curve_cache_reuses_canonical_json_parse(monkeypatch):
    api = main.Api()
    raw_points = json.dumps(
        [
            {"speed": 3.1, "cadence": 82},
            {"speed": 3.4, "cadence": 84},
            {"speed": 3.2, "cadence": 83},
        ],
        ensure_ascii=False,
    )
    original_safe_json_list = main._safe_json_list
    parse_calls = []

    def counting_safe_json_list(value):
        if value == raw_points:
            parse_calls.append(value)
        return original_safe_json_list(value)

    monkeypatch.setattr(main, "_safe_json_list", counting_safe_json_list)
    api._fatigue_review_historical_curve_cache = {}

    speed_curve, speed_quality = api._review_historical_curve_cached(raw_points, None, "speed")
    cadence_curve, cadence_quality = api._review_historical_curve_cached(raw_points, None, "cadence")

    assert speed_curve == [3.1, 3.4, 3.2]
    assert cadence_curve == [82.0, 84.0, 83.0]
    assert speed_quality == "canonical_track_json"
    assert cadence_quality == "canonical_track_json"
    assert len(parse_calls) == 1

    api._fatigue_review_historical_curve_cache = {}
    api._review_historical_curve_cached(raw_points, None, "speed")
    assert len(parse_calls) == 2


def test_task07_historical_curve_cache_preserves_derived_fallback(monkeypatch):
    api = main.Api()
    raw_points_without_speed = json.dumps([{"cadence": 82}, {"cadence": 84}], ensure_ascii=False)
    derived_speed = json.dumps([3.1, 3.4], ensure_ascii=False)
    api._fatigue_review_historical_curve_cache = {}

    speed_curve, source_quality = api._review_historical_curve_cached(
        raw_points_without_speed,
        derived_speed,
        "speed",
    )
    assert speed_curve == [3.1, 3.4]
    assert source_quality == "legacy_derived_column"

    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "self._review_historical_curve_cached" in main_text
    assert "_fatigue_review_historical_curve_cache = {}" in main_text
