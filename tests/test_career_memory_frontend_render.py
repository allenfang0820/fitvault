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

    def test_memory_gallery_dom_targets_exist_without_image_wall(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        self.assertIn('id="career-memory-status-text"', section)
        self.assertIn('id="career-memory-summary"', section)
        self.assertIn('id="career-memory-list"', section)
        self.assertIn('id="career-memory-empty"', section)
        self.assertIn("暂无生涯记忆", section)
        self.assertNotIn("<img", section)
        self.assertNotIn("photo-grid", section)

    def test_load_career_memory_calls_api_and_handles_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerMemory(filters)")
        self.assertIn("window.pywebview.api.get_career_memory", body)
        self.assertIn("memoryLoading = true", body)
        self.assertIn("memoryLoading = false", body)
        self.assertIn("memoryError", body)
        self.assertIn("requireCareerApiData(res, '生涯记忆加载失败')", body)
        self.assertIn("normalizeCareerMemory(requireCareerApiData", body)
        self.assertIn("renderCareerMemoryLoading()", body)
        self.assertIn("renderCareerMemoryError(message)", body)

    def test_memory_normalizer_uses_whitelisted_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerMemoryItem(item)",
            )
        )
        for token in (
            "items",
            "summary",
            "activity_id",
            "race_id",
            "type",
            "title",
            "story",
            "date",
            "thumbnail_url",
            "has_media",
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
        self.assertIn("暂无生涯记忆", render_body)
        self.assertIn("正在加载记忆", loading_body)
        self.assertIn("记忆暂不可用", error_body)
        self.assertNotIn("<img", render_body)
        self.assertNotIn("thumbnailUrl", render_body)

    def test_activity_bound_memory_items_reuse_activity_detail_handler(self):
        body = extract_function_body(self.source, "function careerMemoryItemHtml(item)")
        self.assertIn("item.detailLink.activityId", body)
        self.assertIn('role="button"', body)
        self.assertIn('tabindex="0"', body)
        self.assertIn('data-activity-id="', body)
        self.assertIn('data-career-source="', body)
        self.assertIn('onclick="openCareerActivityDetailFromElement(this)"', body)
        self.assertIn('onkeydown="onCareerActivityDetailKeydown(event, this)"', body)
        self.assertIn("if (activityId)", body)
        self.assertIn('return \'<div class="career-memory-item">', body)

    def test_memory_user_text_is_escaped_before_inner_html_render(self):
        body = extract_function_body(self.source, "function careerMemoryItemHtml(item)")
        edit_body = extract_function_body(self.source, "function renderCareerMemoryEditForm(item)")

        self.assertIn("safeHtml(item.story)", body)
        self.assertIn("safeHtml((item && item.title) || '未命名记忆')", body)
        self.assertIn("safeHtml(meta)", body)
        self.assertIn("safeHtml((item && item.title) || '')", edit_body)
        self.assertIn("safeHtml((item && item.story) || '')", edit_body)

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
                "function normalizeCareerMemoryItem(item)",
                "function careerMemoryItemHtml(item)",
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
