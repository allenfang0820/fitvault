import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_FRONTEND_TOKENS = (
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
    "storage_ref",
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


class TestCareerMemoryFrontendRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_memory_gallery_dom_targets_exist_as_album_wall(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        self.assertIn('id="career-memory-status-text"', section)
        self.assertIn('id="career-memory-summary"', section)
        self.assertIn('id="career-memory-list"', section)
        self.assertIn('id="career-memory-empty"', section)
        self.assertIn("暂无赛事相册", section)
        self.assertNotIn("<img", section)
        self.assertNotIn("type=\"file\"", section.lower())

    def test_load_career_memory_calls_api_and_handles_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerMemory(filters)")
        self.assertIn("api.get_career_memory_gallery", body)
        self.assertIn("memoryLoading = true", body)
        self.assertIn("memoryLoading = false", body)
        self.assertIn("memoryError", body)
        self.assertIn("requireCareerApiData(res, '赛事相册加载失败')", body)
        self.assertIn("normalizeCareerMemory(requireCareerApiData", body)
        self.assertIn("renderCareerMemoryLoading()", body)
        self.assertIn("renderCareerMemoryError(message)", body)

    def test_memory_normalizer_uses_whitelisted_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryPhoto(photo)",
            )
        )
        for token in (
            "albums",
            "summary",
            "activity_id",
            "race_id",
            "title",
            "event_date",
            "display_date",
            "cover",
            "photos",
            "thumbnail_url",
            "preview_url",
            "image_ref",
            "detail_link",
        ):
            self.assertIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)

    def test_empty_state_is_textual_and_distinct(self):
        render_body = extract_function_body(self.source, "function renderCareerMemory(viewModel)")
        loading_body = extract_function_body(self.source, "function renderCareerMemoryLoading()")
        error_body = extract_function_body(self.source, "function renderCareerMemoryError(message)")
        self.assertIn("career-memory-empty", render_body)
        self.assertIn("暂无赛事相册", render_body)
        self.assertIn("正在加载赛事相册", loading_body)
        self.assertIn("赛事相册暂不可用", error_body)
        self.assertIn("careerMemoryAlbumCardHtml", render_body)

    def test_album_cards_are_clickable_four_three_units(self):
        body = extract_function_body(self.source, "function careerMemoryAlbumCardHtml(album)")
        css = extract_between(self.source, ".career-memory-album-card {", ".career-memory-empty {")
        self.assertIn("aspect-ratio: 4 / 3", css)
        self.assertIn('data-career-memory-album-id="', body)
        self.assertIn('onclick="openCareerMemoryAlbum(this)"', body)
        self.assertIn("career-memory-album-cover", body)
        self.assertIn("career-memory-album-placeholder", body)
        self.assertIn("career-memory-album-art", body)
        self.assertIn("safeHtml(artTitle)", body)
        self.assertIn("cover.imageRef", body)

    def test_memory_user_text_is_escaped_before_inner_html_render(self):
        body = extract_function_body(self.source, "function careerMemoryAlbumCardHtml(album)")

        self.assertIn("safeHtml(title)", body)
        self.assertIn("safeHtml(meta", body)
        self.assertIn("safeHtml(imageRef)", body)

    def test_switching_to_career_loads_memory(self):
        body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")
        self.assertIn("loadCareerData().catch", body)
        self.assertIn("loadCareerOverview().catch", load_body)
        self.assertIn("loadCareerTimeline().catch", load_body)
        self.assertIn("loadCareerMemory().catch", load_body)

    def test_memory_frontend_keeps_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryPhoto(photo)",
                "function careerMemoryAlbumCardHtml(album)",
                "function renderCareerMemory(viewModel)",
                "async function loadCareerMemory(filters)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("resolve_", relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)


if __name__ == "__main__":
    unittest.main()
