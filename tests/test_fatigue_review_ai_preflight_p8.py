from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TRACK_HTML = os.path.join(PROJECT_ROOT, "track.html")
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
LLM_BACKEND_PY = os.path.join(PROJECT_ROOT, "llm_backend.py")
P80_PROMPT = os.path.join(PROJECT_ROOT, "docs", "p8_0_fatigue_review_ai_preflight_contract_review_prompt.md")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_function(source: str, signature: str) -> str:
    idx = source.find(signature)
    if idx < 0:
        return ""
    end = source.find("\n    function ", idx + len(signature))
    if end < 0:
        end = source.find("\n    async function ", idx + len(signature))
    if end < 0:
        end = idx + 4000
    return source[idx:end]


class TestP81FrontendOpenGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_p81_opens_ai_button_with_minimal_click_handler(self):
        idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(idx, 0)
        start = self.html.rfind("<button", 0, idx)
        end = self.html.find("</button>", idx)
        button = self.html[start:end]
        self.assertNotIn("disabled", button)
        self.assertNotIn('aria-disabled="true"', button)
        self.assertIn("生成 AI 洞察", button)
        self.assertIn('onclick="onFatigueReviewAiInsight()"', button)
        self.assertNotIn("call_llm", button)

    def test_p81_frontend_call_only_passes_sentinel_and_sport_type(self):
        body = _extract_function(self.html, "async function onFatigueReviewAiInsight()")
        self.assertIn("_lastFatigueReviewData && _lastFatigueReviewData.sport_type", body)
        self.assertIn("call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)", body)
        self.assertNotIn("JSON.stringify", body)
        self.assertNotIn("prompt", body.lower())
        for forbidden in (
            "activityData",
            "curves",
            "metrics",
            "fatigue_zones",
            "collapse_events",
            "points",
            "chartPayload",
            "querySelector",
            "getOption",
        ):
            self.assertNotIn(forbidden, body)

    def test_p80_ai_cache_compat_layer_does_not_persist_insight(self):
        start = self.html.find("function _saveFatigueReviewCache(")
        self.assertGreater(start, 0)
        end = self.html.find("\n    // === V6.3 双向联动", start)
        cache_block = self.html[start:end]
        for forbidden in (
            "sessionStorage.setItem",
            "sessionStorage.getItem",
            "sessionStorage.removeItem",
            "localStorage",
            "fatigue_review_ai:",
            "source: 'session_cache'",
        ):
            self.assertNotIn(forbidden, cache_block)
        self.assertIn("function _saveFatigueReviewCache", cache_block)
        self.assertIn("return null;", cache_block)
        self.assertIn("return false;", cache_block)


class TestP80BackendPreflight(unittest.TestCase):
    def test_p80_compact_snapshot_strips_forbidden_fields_recursively(self):
        from main import Api

        api = Api()
        api._fetch_activity_row = MagicMock(return_value={
            "id": 42,
            "sport_type": "running",
        })
        api._build_fatigue_review_snapshot = MagicMock(return_value={
            "sport_type": "running",
            "metrics": {
                "hr_drift": {"value": 1.2},
                "points": [{"hr": 150}],
                "nested": {"fit_records": [{"bad": True}]},
            },
            "fatigue_zones": [
                {"start_km": 0, "end_km": 1, "level": "medium", "gpx_points": [1, 2]},
            ],
            "collapse_events": [
                {"event_id": "e1", "trigger_km": 1.0, "raw_records": [{"bad": True}]},
            ],
            "curves": {
                "distance": [0, 1],
                "hr": [120, 130],
                "points": [{"bad": True}],
            },
            "context_tags": {"weather": "晴", "track_points": [{"bad": True}]},
            "environment_context": {"has_weather": True, "temperature_c": 18.0, "points": [{"bad": True}]},
            "advice": "保持节奏",
            "disclaimer": "AI 生成仅供参考",
            "shadow_diff": {"bad": True},
        })

        snapshot = api._build_fatigue_review_insight_snapshot(42, "running")
        encoded = json.dumps(snapshot, ensure_ascii=False)

        self.assertEqual(
            set(snapshot.keys()),
            {
                "activity_id",
                "sport_type",
                "metrics",
                "fatigue_zones",
                "collapse_events",
                "curves_summary",
                "context_tags",
                "environment_context",
                "advice",
                "disclaimer",
            },
        )
        for forbidden in (
            "records",
            "points",
            "raw_records",
            "track_points",
            "fit_records",
            "gpx_points",
            "shadow_diff",
            "shadow_diff_json",
            "diff",
        ):
            self.assertNotIn('"' + forbidden + '"', encoded)

    def test_p80_sentinel_branch_does_not_write_db_or_canonical_fields(self):
        main = _read(MAIN_PY)
        branch_start = main.index("if prompt == self.FATIGUE_REVIEW_INSIGHT")
        branch_end = main.index("if prompt == self.REPORT_ACTIVITY_ADVICE", branch_start)
        branch = main[branch_start:branch_end]
        for forbidden in ("INSERT", "UPDATE", "DELETE", "ai_snapshots"):
            self.assertNotIn(forbidden, branch)
        self.assertIn("_build_fatigue_review_insight_snapshot(activity_id, sport_type)", branch)
        self.assertIn("llm_backend.normalize_fatigue_review_json(text)", branch)


class TestP80DocsPreflight(unittest.TestCase):
    def test_p80_prompt_records_open_handoff_boundary(self):
        prompt = _read(P80_PROMPT)
        for required in (
            "P8.0 只做开放前审查，不打开 AI 按钮",
            "不写 `localStorage` / `sessionStorage` 持久化 AI 事实",
            "P8.0 复盘 AI 洞察开放前契约复核通过，允许进入 P8.1 最小闭环打开按钮。",
        ):
            self.assertIn(required, prompt)


if __name__ == "__main__":
    unittest.main()
