import json
import re
import unittest
from pathlib import Path

import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"
TASK_LIST_PATH = PROJECT_ROOT / "docs" / "脉图运动生涯系统（ACS）开发任务清单.md"

CAREER_API_METHODS = (
    "get_career_overview",
    "get_career_timeline",
    "get_career_races",
    "get_career_race_map",
    "get_career_footprint",
    "get_career_pb",
    "get_career_achievements",
    "get_career_memory_gallery",
    "get_latest_career_snapshot",
    "generate_career_insight",
    "get_activity_race_photos",
    "pick_and_add_activity_race_photos",
    "reorder_activity_race_photos",
    "deactivate_activity_race_photo",
    "save_career_race_photo",
    "pick_and_save_career_race_photo",
)

FRONTEND_CAREER_API_METHODS = (
    "get_career_overview",
    "get_career_timeline",
    "get_career_races",
    "get_career_footprint",
    "get_career_pb",
    "get_career_memory_gallery",
    "get_career_year_insight",
    "generate_career_year_insight",
    "get_activity_race_photos",
    "pick_and_add_activity_race_photos",
    "reorder_activity_race_photos",
    "deactivate_activity_race_photo",
)

INLINE_CAREER_HANDLERS = (
    "setCareerTimelineTypeFilter",
    "setCareerTimelineYearFilter",
    "loadCareerYearInsight",
    "generateCareerYearInsight",
    "onCareerFootprintFilterChange",
    "loadActivityRacePhotos",
    "addActivityRacePhotos",
    "reorderActivityRacePhotos",
    "deleteActivityRacePhoto",
    "openCareerActivityDetailFromElement",
    "onCareerActivityDetailKeydown",
    "expandCareerTimelineTrack",
)


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


class TestCareerPhase9MacosClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.track_html = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.task_list = TASK_LIST_PATH.read_text(encoding="utf-8")
        cls.contract_methods = {
            item.get("name"): item
            for item in json.loads(CONTRACT_PATH.read_text(encoding="utf-8")).get("methods", [])
        }

    def test_main_contract_and_frontend_career_api_methods_are_aligned(self):
        api = main.Api()
        for method_name in CAREER_API_METHODS:
            self.assertTrue(hasattr(api, method_name), method_name)
            self.assertIn(method_name, self.contract_methods, method_name)

        for method_name in FRONTEND_CAREER_API_METHODS:
            direct_call = f"window.pywebview.api.{method_name}"
            local_api_call = f"api.{method_name}"
            has_call = direct_call in self.track_html or local_api_call in self.track_html
            self.assertTrue(has_call, method_name)

        self.assertNotIn("window.pywebview.api.get_latest_career_snapshot", self.track_html)
        self.assertNotIn("window.pywebview.api.save_career_snapshot", self.track_html)

    def test_career_inline_handlers_are_defined(self):
        for handler_name in INLINE_CAREER_HANDLERS:
            pattern = rf"(?:async\s+)?function\s+{re.escape(handler_name)}\s*\("
            self.assertRegex(self.track_html, pattern, handler_name)

    def test_career_frontend_loaders_check_api_and_envelope(self):
        loader_signatures = (
            "async function loadCareerOverview()",
            "async function loadCareerArchives()",
            "async function loadCareerFootprint(filters)",
            "async function loadCareerTimeline(filters)",
            "async function loadCareerMemory(filters)",
            "async function loadCareerYearInsight(options)",
            "async function loadActivityRacePhotos(record)",
            "async function addActivityRacePhotos()",
            "async function reorderActivityRacePhotos(orderedIds)",
            "async function deleteActivityRacePhoto(event, photoId)",
        )
        for signature in loader_signatures:
            body = _extract_function_body(self.track_html, signature)
            self.assertIn("window.pywebview", body, signature)
            self.assertIn("requireCareerApiData", body, signature)

    def test_windows_packaging_and_true_device_items_remain_unchecked(self):
        self.assertIn("- [ ] Windows 打包后验证：", self.task_list)
        self.assertIn("- [ ] Windows 真机验证运动生涯页面：", self.task_list)
        self.assertIn("Windows 真机与打包验证已后置，仍未完成", self.task_list)


if __name__ == "__main__":
    unittest.main()
