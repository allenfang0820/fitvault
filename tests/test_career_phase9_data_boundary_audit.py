import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

DANGEROUS_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "storage_ref",
    "path",
}

DANGEROUS_TEXT = (
    "/Users/",
    "\\Users\\",
    "C:/Users/",
    "C:\\Users\\",
    "/tmp/",
    "sqlite_schema",
    "[forbidden]",
)

ACS_FRONTEND_SIGNATURES = (
    "function normalizeCareerRace(item)",
    "function normalizeCareerPbRecord(item)",
    "function normalizeCareerAchievement(item)",
    "function normalizeCareerOverview(payload)",
    "async function loadCareerOverview()",
    "function normalizeCareerArchives(payload)",
    "async function loadCareerArchives()",
    "function normalizeCareerTimeline(payload)",
    "function normalizeCareerTimelineNode(item)",
    "function careerTimelineNodePositionStyle(node, month)",
    "function careerTimelineTrackHtml(month, track)",
    "function careerTimelineMonthHtml(month)",
    "async function loadCareerTimeline(filters)",
    "function normalizeCareerMemory(payload)",
    "function normalizeCareerMemoryAlbum(album)",
    "function normalizeCareerMemoryPhoto(photo)",
    "async function loadCareerMemory(filters)",
    "function renderCareerYearInsight(viewModel)",
    "async function loadCareerYearInsight(options)",
)


def _create_activities_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            title TEXT,
            sport_type TEXT,
            start_time TEXT,
            start_time_utc TEXT,
            dist_km REAL,
            distance REAL,
            duration_sec REAL,
            avg_pace REAL,
            region_city TEXT,
            deleted_at TEXT,
            points_json TEXT,
            track_json TEXT,
            file_path TEXT,
            raw_records TEXT
        )
        """
    )


def _seed_acs_boundary_fixture(conn: sqlite3.Connection) -> None:
    _create_activities_table(conn)
    career_backend.ensure_career_schema(conn)
    conn.execute(
        """
        INSERT INTO activities
            (id, title, sport_type, start_time, start_time_utc, dist_km, distance,
             duration_sec, avg_pace, region_city, deleted_at, points_json, track_json,
             file_path, raw_records)
        VALUES
            (1, '苏州 10K', 'running', '2026-05-19T07:00:00+08:00', '',
             10.0, NULL, 3600, 360, '苏州', NULL, '[forbidden]',
             '[forbidden]', '/tmp/forbidden.fit', '[forbidden]')
        """
    )
    conn.execute(
        """
        INSERT INTO career_race_events
            (id, activity_id, name, event_type, sport, event_date, location_json,
             confidence, source, status, display_metadata_json)
        VALUES
            ('race:1', '1', '苏州 10K 精英赛', '10k', 'running', '2026-05-19',
             '{"city":"苏州"}', 0.96, 'resolver', 'active',
             '{"path":"/Users/example/private.fit","evidence":{"file_path":"C:/Users/example/private.fit","confidence_level":"high"},"safe_label":"保留"}')
        """
    )
    conn.execute(
        """
        INSERT INTO career_pb_records
            (id, activity_id, sport, pb_type, value, value_unit, improvement,
             event_date, confidence, source, status, display_metadata_json)
        VALUES
            ('pb:1', '1', 'running', 'running_10k', '3600', 'sec', NULL,
             '2026-05-19', 1.0, 'resolver', 'active',
             '{"storage_ref":"memory/private.jpg","path":"/tmp/private.jpg","safe_label":"PB"}')
        """
    )
    conn.execute(
        """
        INSERT INTO career_achievement_events
            (id, activity_id, achievement_type, title, event_date, score, icon,
             description, confidence, source, status, display_metadata_json)
        VALUES
            ('achievement:1', '1', 'first_running_10k', '首次跑完 10K',
             '2026-05-19', 80, 'flag', '完成第一个 10K', 1.0, 'resolver',
             'active', '{"advanced_metrics":{"secret":true},"sqlite_schema":"bad","safe_label":"成就"}')
        """
    )
    conn.execute(
        """
        INSERT INTO career_memory_items
            (id, race_id, activity_id, memory_type, storage_ref, story_text,
             metadata_json, title, event_date, status)
        VALUES
            ('memory:1', 'race:1', '1', 'photo', 'memory/photo/苏州 10K 终点.jpg',
             '终点冲线记忆', '{"thumbnail_url":"/Users/example/thumb.jpg","path":"/tmp/private.jpg"}',
             '苏州 10K 终点', '2026-05-19', 'active')
        """
    )
    conn.commit()


def _assert_no_dangerous_boundary_leak(testcase, value, *, forbid_thumbnail=False, forbid_detail_link=False):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).strip().lower()
            testcase.assertNotIn(normalized_key, DANGEROUS_KEYS)
            if forbid_thumbnail:
                testcase.assertNotEqual(normalized_key, "thumbnail_url")
            if forbid_detail_link:
                testcase.assertNotEqual(normalized_key, "detail_link")
            _assert_no_dangerous_boundary_leak(
                testcase,
                child,
                forbid_thumbnail=forbid_thumbnail,
                forbid_detail_link=forbid_detail_link,
            )
    elif isinstance(value, list):
        for child in value:
            _assert_no_dangerous_boundary_leak(
                testcase,
                child,
                forbid_thumbnail=forbid_thumbnail,
                forbid_detail_link=forbid_detail_link,
            )
    elif isinstance(value, str):
        for token in DANGEROUS_TEXT:
            testcase.assertNotIn(token, value)


def _extract_function_body(source: str, signature: str) -> str:
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


class TestCareerPhase9DataBoundaryAudit(unittest.TestCase):
    def test_career_api_snapshot_and_insight_do_not_leak_raw_or_local_storage_fields(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory(prefix="脉图 ACS boundary ") as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "含 空格" / "career.sqlite"
                profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    _seed_acs_boundary_fixture(conn)
                finally:
                    conn.close()

                api = main.Api()
                public_responses = (
                    api.get_career_overview(),
                    api.get_career_timeline({"type": "all"}),
                    api.get_career_races({}),
                    api.get_career_pb({}),
                    api.get_career_achievements({}),
                    api.get_career_memory_gallery({}),
                )
                for response in public_responses:
                    self.assertTrue(response.get("ok"), response)
                    self.assertEqual(response.get("code"), main.API_CODE_OK)
                    _assert_no_dangerous_boundary_leak(self, response)

                insight = api.generate_career_insight({"refresh_snapshot": True})
                snapshot = api.get_latest_career_snapshot()
                for response in (insight, snapshot):
                    self.assertTrue(response.get("ok"), response)
                    self.assertEqual(response.get("code"), main.API_CODE_OK)
                    _assert_no_dangerous_boundary_leak(
                        self,
                        response,
                        forbid_thumbnail=True,
                        forbid_detail_link=True,
                    )
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_career_frontend_uses_envelope_helper_and_does_not_infer_from_raw_activity_facts(self):
        source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        relevant = "\n".join(_extract_function_body(source, signature) for signature in ACS_FRONTEND_SIGNATURES)
        for token in (
            "call_llm",
            "points_json",
            "track_json",
            "file_path",
            "storage_ref",
            "sqlite_schema",
            "sport_event",
            "race_confidence",
            "dist_km",
            "duration_sec",
            "avg_pace",
        ):
            self.assertNotIn(token, relevant)

        for signature in (
            "async function loadCareerOverview()",
            "async function loadCareerArchives()",
            "async function loadCareerTimeline(filters)",
            "async function loadCareerMemory(filters)",
            "async function loadCareerYearInsight(options)",
        ):
            body = _extract_function_body(source, signature)
            self.assertIn("requireCareerApiData", body, signature)

    def test_career_js_contract_keeps_raw_storage_and_ai_boundaries_explicit(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        career_entries = [
            entry for entry in contract.get("methods", [])
            if entry.get("category") == "career"
        ]
        self.assertGreaterEqual(len(career_entries), 8)
        for entry in career_entries:
            returns = str(entry.get("returns") or "")
            description = str(entry.get("description") or "")
            for token in ("storage_ref", "file_path", "track_json", "points", "SQLite schema"):
                self.assertNotIn(token, returns, entry.get("name"))
            self.assertIn("不", description, entry.get("name"))
            if entry.get("name") == "generate_career_insight":
                self.assertIn("不调用 LLM", description)


if __name__ == "__main__":
    unittest.main()
