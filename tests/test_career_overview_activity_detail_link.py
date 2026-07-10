import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_HANDLER_TOKENS = (
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "schema",
)

FORBIDDEN_FACT_TOKENS = (
    "sport_event",
    "race_confidence",
    "dist_km",
    "duration_sec",
    "avg_pace",
    "career_race_events",
    "career_pb_records",
    "career_achievement_events",
)


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


class TestCareerOverviewActivityDetailLink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_spotlight_item_has_click_and_keyboard_hooks(self):
        body = extract_function_body(self.source, "function careerSpotlightItemHtml(item, title, meta)")
        self.assertIn("data-activity-id", body)
        self.assertIn("data-career-source", body)
        self.assertIn('role="button"', body)
        self.assertIn('tabindex="0"', body)
        self.assertIn('onclick="openCareerActivityDetailFromElement(this)"', body)
        self.assertIn('onkeydown="onCareerActivityDetailKeydown(event, this)"', body)

    def test_handler_reads_activity_id_and_requires_career_source(self):
        body = extract_function_body(self.source, "function openCareerActivityDetailFromElement(el)")
        self.assertIn("getAttribute('data-activity-id')", body)
        self.assertIn("getAttribute('data-career-source')", body)
        self.assertIn("source !== 'career'", body)
        self.assertIn("if (!activityId) return;", body)
        self.assertIn("parseInt", body)

    def test_handler_reuses_existing_activity_detail_path_without_new_api(self):
        body = extract_function_body(self.source, "function openCareerActivityDetailFromElement(el)")
        self.assertIn("appState.activityDetailSource = 'career';", body)
        self.assertIn("openActivityDetailModal(activityId)", body)
        self.assertNotIn("window.pywebview.api", body)
        self.assertNotIn("get_activity_detail", body)
        self.assertNotIn("load_activity_track", body)

    def test_keyboard_handler_triggers_only_enter_or_space(self):
        body = extract_function_body(self.source, "function onCareerActivityDetailKeydown(event, el)")
        self.assertIn("key !== 'Enter'", body)
        self.assertIn("key !== ' '", body)
        self.assertIn("key !== 'Spacebar'", body)
        self.assertIn("preventDefault", body)
        self.assertIn("openCareerActivityDetailFromElement(el)", body)

    def test_handler_does_not_reference_forbidden_raw_fields_or_compute_facts(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function openCareerActivityDetailFromElement(el)",
                "function onCareerActivityDetailKeydown(event, el)",
            )
        )
        for token in FORBIDDEN_HANDLER_TOKENS:
            self.assertNotIn(token, relevant)
        for token in FORBIDDEN_FACT_TOKENS:
            self.assertNotIn(token, relevant)

    def test_activity_detail_source_state_exists(self):
        self.assertIn("activityDetailSource: ''", self.source)


if __name__ == "__main__":
    unittest.main()
