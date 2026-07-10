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
    "path",
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


class TestCareerMemoryStoryFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_memory_gallery_is_readonly_without_inline_upload_or_story_form(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        self.assertIn("Memory Gallery", section)
        self.assertIn("仅集中展示", section)
        self.assertNotIn("添加故事", section)
        self.assertNotIn('id="career-memory-story-toggle"', section)
        self.assertNotIn('id="career-memory-story-form"', section)
        self.assertNotIn('id="career-memory-story-activity-id"', section)
        self.assertNotIn('id="career-memory-story-race-id"', section)
        self.assertNotIn('id="career-memory-story-title"', section)
        self.assertNotIn('id="career-memory-story-text"', section)
        self.assertNotIn('id="career-memory-story-error"', section)
        self.assertNotIn("saveCareerMemoryStory()", section)
        self.assertNotIn("<dialog", section)
        self.assertNotIn("modal", section.lower())

    def test_story_form_state_is_inline_not_modal(self):
        state_body = extract_function_body(self.source, "function renderCareerMemoryStoryFormState()")
        toggle_body = extract_function_body(self.source, "function toggleCareerMemoryStoryForm(show)")
        self.assertIn("career-memory-story-form", state_body)
        self.assertIn("classList.toggle('is-visible'", state_body)
        self.assertIn("memoryStoryFormVisible", state_body + toggle_body)
        self.assertNotIn("showModal", state_body + toggle_body)
        self.assertNotIn("dialog", state_body + toggle_body)

    def test_save_story_calls_api_with_whitelisted_payload(self):
        body = extract_function_body(self.source, "async function saveCareerMemoryStory()")
        self.assertIn("window.pywebview.api.save_career_memory_story", body)
        self.assertIn("const payload = {", body)
        self.assertIn("activity_id: activityId", body)
        self.assertIn("race_id: raceId", body)
        self.assertIn("title: title", body)
        self.assertIn("story: story", body)
        self.assertIn("requireCareerApiData(res, '记忆故事保存失败')", body)
        self.assertIn("loadCareerMemory()", body)
        payload_block = extract_between(body, "const payload = {", "};")
        self.assertIn("activity_id", payload_block)
        self.assertIn("race_id", payload_block)
        self.assertIn("title", payload_block)
        self.assertIn("story", payload_block)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, payload_block)

    def test_empty_values_return_before_backend_call(self):
        body = extract_function_body(self.source, "async function saveCareerMemoryStory()")
        api_index = body.find("window.pywebview.api.save_career_memory_story")
        self.assertGreater(api_index, 0)
        validation_body = body[:api_index]
        self.assertIn("!activityId && !raceId", validation_body)
        self.assertIn("!title", validation_body)
        self.assertIn("!story", validation_body)
        self.assertIn("return;", validation_body)

    def test_story_form_state_is_in_app_state(self):
        state_slice = extract_between(
            self.source,
            "career: {",
            "}\n    };",
        )
        self.assertIn("memoryStoryFormVisible", state_slice)
        self.assertIn("memoryStorySaving", state_slice)
        self.assertIn("memoryStoryError", state_slice)

    def test_mobile_style_keeps_story_form_single_column(self):
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        self.assertIn(".career-memory-story-row", mobile_css)
        self.assertIn("grid-template-columns: 1fr", mobile_css)

    def test_story_frontend_keeps_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function clearCareerMemoryStoryFormFields()",
                "function renderCareerMemoryStoryFormState()",
                "function toggleCareerMemoryStoryForm(show)",
                "async function saveCareerMemoryStory()",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)


if __name__ == "__main__":
    unittest.main()
