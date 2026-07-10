import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_RACE_MAP_TOKENS = (
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "storage_ref",
    "file://",
    "/Users/",
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


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestCareerRaceMapFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_footprint_page_contains_race_map_targets_without_manual_inputs(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="footprint">',
            '</section>',
        )
        for token in (
            'id="career-race-map-status-text"',
            'id="career-race-map-year-filter"',
            'id="career-race-map-sport-filter"',
            'id="career-race-map-locations"',
            'id="career-race-map-missing-list"',
            'id="career-race-map-empty"',
            "生涯足迹",
        ):
            self.assertIn(token, section)
        self.assertNotIn("career-memory-story-activity-id", section)
        self.assertNotIn("placeholder=\"活动 ID\"", section)
        self.assertNotIn("添加故事", section)

    def test_load_career_race_map_calls_api_and_handles_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerRaceMap(filters)")
        self.assertIn("window.pywebview", body)
        self.assertIn("api.get_career_race_map(nextFilters)", body)
        self.assertIn("requireCareerApiData(res, '赛事足迹加载失败')", body)
        self.assertIn("normalizeCareerRaceMap(requireCareerApiData", body)
        self.assertIn("renderCareerRaceMapLoading()", body)
        self.assertIn("renderCareerRaceMapError(message)", body)

    def test_race_map_normalizer_uses_whitelisted_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerRaceMapPoint(item)",
                "function normalizeCareerRaceMapMissing(item)",
                "function normalizeCareerRaceMap(payload)",
            )
        )
        for token in (
            "activity_id",
            "title",
            "sport_label",
            "event_type_label",
            "event_date",
            "city",
            "region_display",
            "lat",
            "lon",
            "detail_link",
            "locations",
            "without_coordinates",
        ):
            self.assertIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        for token in FORBIDDEN_RACE_MAP_TOKENS:
            self.assertNotIn(token, relevant)

    def test_race_map_items_return_to_activity_detail(self):
        point_body = extract_function_body(self.source, "function careerRaceMapPointHtml(item, bounds)")
        missing_body = extract_function_body(self.source, "function careerRaceMapMissingHtml(item)")
        combined = point_body + "\n" + missing_body
        self.assertIn("openCareerActivityDetailFromElement(this)", combined)
        self.assertIn('data-activity-id="', combined)
        self.assertIn('data-career-source="', combined)
        self.assertIn("item.detailLink.activityId", combined)
        self.assertIn("onCareerActivityDetailKeydown(event, this)", missing_body)

    def test_load_career_data_includes_race_map(self):
        body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerRaceMap().catch", body)


if __name__ == "__main__":
    unittest.main()
