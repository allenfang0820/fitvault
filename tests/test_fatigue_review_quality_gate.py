from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
MAIN_PY = os.path.join(_PROJECT_ROOT, "main.py")
LLM_BACKEND_PY = os.path.join(_PROJECT_ROOT, "llm_backend.py")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_js_function(source: str, name: str) -> str:
    marker = "function " + name + "("
    start = source.find(marker)
    if start < 0:
        return ""
    end = source.find("\n    function ", start + len(marker))
    if end < 0:
        end = source.find("\n    async function ", start + len(marker))
    if end < 0:
        end = start + 5000
    return source[start:end]


class TestP5FrontendZeroInferenceGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_no_frontend_distance_axis_rebuilder_exists(self):
        forbidden = (
            "_distanceFromSpeedTime",
            "validSpeedSum",
            "speed[m] || 0) / validSpeedSum",
            "speed[i] || 0) * 1.0",
            "p / n * totalKm",
            "appState.points",
        )
        review_slice = self.html[self.html.find("async function openFatigueReview("):]
        for token in forbidden:
            self.assertNotIn(token, review_slice, token)

    def test_open_fatigue_review_distance_axis_only_from_backend_curve(self):
        body = _extract_js_function(self.html, "openFatigueReview")
        self.assertIn(
            "distance_curve: Array.isArray(curvesObj.distance) ? curvesObj.distance : []",
            body,
        )
        self.assertNotIn("total_distance_m", body)
        self.assertNotIn("speed_curve", body.split("distance_curve:", 1)[0])

    def test_chart_empty_state_when_backend_distance_axis_missing(self):
        body = _extract_js_function(self.html, "renderProfileAnalysisChart")
        self.assertIn("distanceCurve.length < 2", body)
        self.assertIn("后端未返回权威距离轴", body)
        self.assertIn("curves.distance = []", body)


class TestP5SnapshotWhitelistGate(unittest.TestCase):
    TOP_LEVEL_KEYS = {
        "sport_type",
        "metrics",
        "collapse_events",
        "fatigue_zones",
        "curves",
        "context_tags",
        "ai_insight",
        "advice",
        "disclaimer",
    }
    CURVE_KEYS = {
        "distance",
        "time",
        "hr",
        "speed",
        "altitude",
        "grade",
        "gap",
        "efficiency",
        "total_distance_m",
    }
    FORBIDDEN_KEYS = {
        "shadow_diff",
        "shadow_diff_json",
        "diff",
        "records",
        "points",
        "raw_records",
        "track_points",
    }

    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_historical_metrics_avg = MagicMock(return_value={
            "sample_size": 0,
            "hr_drift_pct": None,
            "decoupling_pct": None,
            "bonk_count": 0,
        })
        for name, value in {
            "_fetch_efficiency_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_durability_trend": {"level": "flat", "compared_count": 0, "baseline_ratio": None},
            "_fetch_cadence_stability_trend": {"level": "flat", "compared_count": 0, "baseline_cv": None},
            "_fetch_training_load_trend": {"level": "flat", "compared_count": 0, "baseline_load": None},
            "_fetch_load_ratio_7d_42d": {
                "ratio": None, "level": "unknown", "acute_7d": None,
                "chronic_42d": None, "compared_count": 0,
            },
        }.items():
            setattr(api, name, MagicMock(return_value=value))
        return api

    def _row(self) -> dict:
        base = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        points = []
        for i in range(50):
            points.append({
                "lat": 31.0 + i * 0.0001,
                "lon": 121.0,
                "time": (base + timedelta(seconds=i * 15)).isoformat(),
                "hr": 135 + min(i, 30),
                "speed": 3.0,
                "alt": 100 + i,
                "cadence": 84,
            })
        return {
            "id": 7,
            "sport_type": "running",
            "dist_km": 5.0,
            "distance": 5000.0,
            "duration_sec": 750,
            "calories": 800,
            "track_json": json.dumps(points),
            "hr_curve": json.dumps([p["hr"] for p in points]),
            "speed_curve": json.dumps([p["speed"] for p in points]),
            "cadence_curve": json.dumps([p["cadence"] for p in points]),
        }

    def test_snapshot_top_level_and_curves_whitelist(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        self.assertEqual(set(snapshot.keys()), self.TOP_LEVEL_KEYS)
        self.assertEqual(set(snapshot["curves"].keys()), self.CURVE_KEYS)

    def test_snapshot_forbidden_keys_absent_recursively(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for key in self.FORBIDDEN_KEYS:
            self.assertNotIn('"' + key + '"', encoded)

    def test_non_empty_drawable_curves_align_to_distance_axis(self):
        curves = self._api()._build_fatigue_review_snapshot(self._row())["curves"]
        axis_len = len(curves["distance"])
        self.assertGreater(axis_len, 0)
        for key in ("time", "hr", "speed", "altitude", "grade", "gap", "efficiency"):
            if curves[key]:
                self.assertEqual(len(curves[key]), axis_len, key)

    def test_zone_and_event_coordinates_are_backend_numbers(self):
        snapshot = self._api()._build_fatigue_review_snapshot(self._row())
        for zone in snapshot["fatigue_zones"]:
            self.assertIsInstance(zone.get("start_km"), (int, float))
            self.assertIsInstance(zone.get("end_km"), (int, float))
        for event in snapshot["collapse_events"]:
            trigger_km = event.get("trigger_km")
            self.assertTrue(trigger_km is None or isinstance(trigger_km, (int, float)))


class TestP5P4UiStructureGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)

    def test_p4_review_structure_is_preserved(self):
        for element_id in (
            "fr-review-layout",
            "fr-status-strip",
            "fr-summary-desc",
            "fr-curve-status-pill",
            "fr-risk-pill",
            "fr-ai-status-pill",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-chart-section",
            "fr-chart-title",
            "fr-chart-subtitle",
            "fr-chart-boundary",
            "fr-chart-legend",
            "fr-chart-axis-note",
            "fr-context-panel",
            "fr-context-boundary",
            "fr-events-panel",
            "fr-events-boundary",
            "fr-fatigue-zones-panel",
            "fr-fatigue-zones-boundary",
            "fr-fatigue-zone-list",
            "fr-advice-panel",
            "fr-advice-boundary",
            "fr-advice-status",
            "fatigue-review-chart",
        ):
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_4_chart_boundary_copy_is_preserved(self):
        for text in (
            "X 轴来自后端 curves.distance",
            "曲线来自 data.curves",
            "疲劳带来自 data.fatigue_zones",
            "事件来自 data.collapse_events",
            "distance_curve = data.curves.distance",
        ):
            self.assertIn(text, self.html)

    def test_p7_5_event_and_zone_boundaries_are_preserved(self):
        for text in (
            "来自 data.collapse_events",
            "位置使用 trigger_km",
            "来自 data.fatigue_zones",
            "区间使用 start_km / end_km",
            "_renderFatigueReviewEvents(data.collapse_events || [])",
            "_renderFatigueReviewZones(data.fatigue_zones || [])",
        ):
            self.assertIn(text, self.html)

    def test_p7_6_context_advice_boundaries_are_preserved(self):
        for text in (
            "来自 data.context_tags",
            "来自 data.advice",
            "data.disclaimer",
            "_renderFatigueReviewContextTags(data.context_tags || {})",
            "_renderFatigueReviewAdvice(data.advice, data.disclaimer)",
            "后端 advice 为空",
        ):
            self.assertIn(text, self.html)

    def test_p7_7_responsive_readability_css_is_preserved(self):
        for text in (
            "@media (max-width: 1100px)",
            "@media (max-width: 720px)",
            "@media (max-width: 480px)",
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "min-height: 280px",
            "overflow-wrap: anywhere",
            "flex-wrap: wrap",
        ):
            self.assertIn(text, self.html)

    def test_p7_7_no_viewport_font_or_negative_letter_spacing(self):
        self.assertNotRegex(self.html, r"font-size\s*:\s*[^;]*vw")
        self.assertNotRegex(self.html, r"letter-spacing\s*:\s*-\s*")

    def test_p7_8_visual_regression_cockpit_order_is_preserved(self):
        ordered_ids = (
            "detail-tab-review",
            "fr-status-strip",
            "fr-core-metrics-section",
            "fr-capacity-metrics-section",
            "fr-chart-section",
            "fr-context-panel",
            "fr-events-panel",
            "fr-fatigue-zones-panel",
            "fr-advice-panel",
        )
        positions = []
        for element_id in ordered_ids:
            pos = self.html.find('id="' + element_id + '"')
            self.assertGreater(pos, 0, element_id)
            positions.append(pos)
        self.assertEqual(positions, sorted(positions))

    def test_p7_8_visual_regression_freezes_sketch_scope_and_ai_entry(self):
        review_idx = self.html.find('id="detail-tab-review"')
        upload_idx = self.html.find('id="file-upload"', review_idx)
        review_body = self.html[review_idx:upload_idx if upload_idx > review_idx else review_idx + 16000]
        for token in ("首页", "日历", "分享", "导出"):
            self.assertNotIn(token, review_body)
        self.assertNotIn(">活动<", review_body)
        button_idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(button_idx, 0)
        start = self.html.rfind("<button", 0, button_idx)
        end = self.html.find("</button>", button_idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertNotIn("onclick=", button)

    def test_eight_metric_card_targets_are_preserved(self):
        for element_id in (
            "fr-hr-drift",
            "fr-decoupling",
            "fr-bonk",
            "fr-events-count",
            "fr-efficiency-score",
            "fr-durability-score",
            "fr-cadence-stability-score",
            "fr-training-load-value",
        ):
            self.assertIn('id="' + element_id + '"', self.html)

    def test_p7_3_metric_cards_have_status_and_explanation(self):
        for element_id in (
            "fr-hr-drift-status",
            "fr-decoupling-status",
            "fr-bonk-status",
            "fr-events-status",
            "fr-efficiency-status",
            "fr-durability-status",
            "fr-cadence-stability-status",
            "fr-training-load-status",
            "fr-hr-drift-sub",
            "fr-decoupling-sub",
            "fr-bonk-sub",
            "fr-events-sub",
            "fr-efficiency-sub",
            "fr-durability-sub",
            "fr-cadence-stability-sub",
            "fr-training-load-sub",
        ):
            self.assertIn('id="' + element_id + '"', self.html)
        self.assertEqual(self.html.count('class="metric-card fr-metric-card"'), 8)

    def test_fatigue_review_ids_are_not_duplicated(self):
        ids = re.findall(r'id="([^"]+)"', self.html)
        counts = {item: ids.count(item) for item in ids if item.startswith("fr")}
        duplicated = {item: count for item, count in counts.items() if count > 1}
        self.assertEqual(duplicated, {})

    def test_p7_2_summary_band_is_inside_review_tab(self):
        review_idx = self.html.find('id="detail-tab-review"')
        strip_idx = self.html.find('id="fr-status-strip"')
        core_idx = self.html.find('id="fr-core-metrics-section"')
        self.assertGreater(review_idx, 0)
        self.assertGreater(strip_idx, review_idx)
        self.assertGreater(core_idx, strip_idx)
        for element_id in (
            "fr-distance-axis-pill",
            "fr-curve-status-pill",
            "fr-risk-pill",
            "fr-event-pill",
            "fr-ai-status-pill",
        ):
            self.assertIn('id="' + element_id + '"', self.html)


class TestP5AiBoundaryGate(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read(TRACK_HTML)
        self.main = _read(MAIN_PY)
        self.llm_backend = _read(LLM_BACKEND_PY)

    def test_fatigue_review_sentinel_is_preserved(self):
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__", self.html)
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__", self.main)

    def test_frontend_ai_call_only_passes_sentinel_and_sport_type(self):
        idx = self.html.find("async function onFatigueReviewAiInsight(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    // === V6.3 渲染辅助", idx)
        body = self.html[idx:end]
        self.assertIn("call_llm('__FATIGUE_REVIEW_INSIGHT__', sportType)", body)
        for forbidden in ("metrics", "curves", "points", "chartPayload", "fatigue_zones"):
            self.assertNotIn("call_llm('__FATIGUE_REVIEW_INSIGHT__', " + forbidden, body)

    def test_p6_1_ai_button_is_frozen_but_capability_remains(self):
        button_idx = self.html.find('id="fr-ai-generate-btn"')
        self.assertGreater(button_idx, 0)
        start = self.html.rfind("<button", 0, button_idx)
        end = self.html.find("</button>", button_idx)
        button = self.html[start:end]
        self.assertIn("disabled", button)
        self.assertIn('aria-disabled="true"', button)
        self.assertNotIn("onclick=", button)
        self.assertIn("function onFatigueReviewAiInsight(", self.html)
        self.assertIn("function _freezeFatigueReviewAiEntry(", self.html)

    def test_frontend_does_not_build_fatigue_review_prompt(self):
        idx = self.html.find("async function onFatigueReviewAiInsight(")
        body = self.html[idx: self.html.find("\n    // === V6.3 渲染辅助", idx)]
        self.assertNotIn("prompt", body.lower())
        self.assertNotIn("JSON.stringify", body)

    def test_ai_insight_does_not_write_db(self):
        for source in (self.main, self.llm_backend):
            self.assertNotIn("INSERT INTO ai_snapshots", source)
        start = self.main.index("if prompt == self.FATIGUE_REVIEW_INSIGHT")
        end = self.main.index("cfg = llm_backend.load_llm_config()", start + 1)
        branch = self.main[start:end]
        for token in ("INSERT", "UPDATE", "ai_snapshots"):
            self.assertNotIn(token, branch)


if __name__ == "__main__":
    unittest.main()
