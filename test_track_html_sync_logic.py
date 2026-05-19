import unittest
from pathlib import Path


TRACK_HTML_PATH = Path("/Users/fanglei/应用开发/AI track/track.html")


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


class TestTrackHtmlSyncLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_page_size_change_does_not_trigger_sync(self):
        body = extract_function_body(self.source, "async function onSportHubPageSizeChange()")
        self.assertNotIn("syncAndLoadSportHubRecords", body)
        self.assertNotIn("sync_local_fit_files", body)
        self.assertIn("refreshSnapshot: false", body)
        self.assertIn("loadSportHubActivityList", body)

    def test_local_pagination_short_circuits_without_refreshing_snapshot(self):
        body = extract_function_body(self.source, "async function loadSportHubActivityList(options = {})")
        self.assertIn("const refreshSnapshot = !!options.refreshSnapshot || !sportHubState.recordsReady;", body)
        self.assertIn("if (!refreshSnapshot)", body)
        self.assertIn("applySportHubRecordFilters(resetPage);", body)
        self.assertIn("get_activity_list_snapshot", body)

    def test_report_panel_renders_weather_card_and_syncs_weather_context(self):
        self.assertIn("历史天气环境感知", self.source)
        self.assertIn("setCurrentWeather(data.weather || null);", self.source)
        self.assertIn("weather: appState.currentWeather", self.source)

    def test_ai_report_uses_dynamic_sport_labels_instead_of_fixed_hiking(self):
        self.assertIn("function getDynamicSportMeta(typeStr)", self.source)
        self.assertIn("getDynamicSportMeta(appState.sportType)", self.source)


if __name__ == "__main__":
    unittest.main()
