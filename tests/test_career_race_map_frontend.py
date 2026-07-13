import unittest
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

    def test_footprint_page_no_longer_uses_legacy_race_map_targets(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="footprint">',
            '</section>',
        )
        self.assertIn('id="career-footprint-map"', section)
        self.assertIn("生涯足迹", section)
        self.assertNotIn("career-race-map-locations", section)
        self.assertNotIn("career-race-map-status-text", section)
        self.assertNotIn("赛事起点", section)

    def test_load_career_data_uses_footprint_loader(self):
        body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerFootprint().catch", body)
        self.assertNotIn("loadCareerRaceMap().catch", body)


if __name__ == "__main__":
    unittest.main()
