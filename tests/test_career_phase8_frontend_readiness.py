import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestCareerPhase8FrontendReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.career_panel = extract_between(
            cls.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        cls.mobile_css = extract_between(
            cls.source,
            "@media (max-width: 980px) {",
            "@media (max-width: 768px) {",
        )

    def test_career_is_first_level_navigation_with_primary_panel(self):
        self.assertIn('class="bookmark-tab" data-panel="career"', self.source)
        self.assertIn('<span class="tab-label">运动生涯</span>', self.source)
        self.assertIn('id="panel-career" class="tab-panel"', self.source)
        self.assertIn('data-legacy-honor-entry="career-link"', self.source)
        self.assertIn("switchToCareerFromHonorWall", self.source)

    def test_phase8_primary_sections_and_filters_are_present(self):
        for section in ("overview", "timeline", "archives", "pb", "achievements", "insight", "memory"):
            self.assertIn(f'data-career-section="{section}"', self.career_panel)

        for label in ("生涯总览", "生涯时间轴", "赛事档案", "记录中心", "荣誉里程碑", "AI 生涯总结", "生涯足迹"):
            self.assertIn(label, self.career_panel)

        for filter_value in ("all", "race", "milestone"):
            self.assertIn(f'data-career-timeline-filter="{filter_value}"', self.career_panel)
        self.assertNotIn('data-career-timeline-filter="pb"', self.career_panel)
        self.assertIn('id="career-timeline-year-capsules"', self.career_panel)
        self.assertNotIn('id="career-timeline-year-filter"', self.career_panel)
        self.assertNotIn('id="career-timeline-sport-filter"', self.career_panel)

    def test_acs_product_shell_has_top_level_secondary_navigation(self):
        self.assertIn('data-acs-product-shell="v1"', self.career_panel)
        self.assertIn('class="career-product-nav"', self.career_panel)
        for page in ("overview", "timeline", "races", "pb", "achievements", "insight", "footprint"):
            self.assertIn(f'data-career-page-target="{page}"', self.career_panel)
            self.assertIn(f'data-career-page="{page}"', self.career_panel)
        for label in ("总览", "时间轴", "赛事档案", "PB", "荣誉", "AI 总结", "足迹"):
            self.assertIn(label, self.career_panel)

    def test_career_primary_surface_is_not_legacy_photo_wall_or_coming_soon(self):
        self.assertNotIn("coming-soon-overlay", self.career_panel)
        self.assertNotIn("honor-card", self.career_panel)
        self.assertNotIn("honor-photo", self.career_panel)
        self.assertNotIn("赛事照片占位", self.career_panel)
        self.assertNotIn("代码疯狂产生中", self.career_panel)

    def test_mobile_css_keeps_phase8_layout_single_column(self):
        self.assertIn(".career-layout", self.mobile_css)
        self.assertIn(".career-overview-grid", self.mobile_css)
        self.assertIn(".career-bucket-list", self.mobile_css)
        self.assertIn("grid-template-columns: 1fr", self.mobile_css)
        self.assertIn(".career-timeline-month", self.mobile_css)
        self.assertIn(".career-memory-list", self.mobile_css)
        self.assertIn(".career-insight-toolbar", self.mobile_css)


if __name__ == "__main__":
    unittest.main()
