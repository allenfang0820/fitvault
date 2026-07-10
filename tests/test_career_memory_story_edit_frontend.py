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


class TestCareerMemoryStoryEditFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_story_item_html_has_edit_and_deactivate_controls(self):
        body = extract_function_body(self.source, "function careerMemoryItemHtml(item)")
        self.assertIn("isStory && memoryId && !isEditing", body)
        self.assertIn("beginCareerMemoryEdit", body)
        self.assertIn("deactivateCareerMemoryItem", body)
        self.assertIn("data-career-memory-id", body)
        self.assertIn("event.stopPropagation()", body)
        self.assertIn("编辑故事", body)
        self.assertIn("停用记忆", body)

    def test_non_story_items_do_not_get_edit_controls(self):
        body = extract_function_body(self.source, "function careerMemoryItemHtml(item)")
        edit_start = body.find("const editAction =")
        self.assertGreater(edit_start, -1)
        edit_block = body[edit_start:body.find("const deactivateAction =", edit_start)]
        self.assertIn("isStory && memoryId && !isEditing", edit_block)
        self.assertNotIn("photo", edit_block)
        self.assertNotIn("track", edit_block)
        deactivate_block = body[body.find("const deactivateAction ="):body.find("const actions =", edit_start)]
        self.assertIn("memoryId && !isEditing", deactivate_block)

    def test_inline_edit_form_is_not_modal(self):
        form_body = extract_function_body(self.source, "function renderCareerMemoryEditForm(item)")
        self.assertIn("career-memory-edit-form", form_body)
        self.assertIn('id="career-memory-edit-title"', form_body)
        self.assertIn('id="career-memory-edit-story"', form_body)
        self.assertIn("saveCareerMemoryEdit", form_body)
        self.assertIn("cancelCareerMemoryEdit", form_body)
        self.assertNotIn("showModal", form_body)
        self.assertNotIn("dialog", form_body)
        self.assertNotIn("modal", form_body.lower())

    def test_edit_state_is_in_app_state(self):
        state_slice = extract_between(
            self.source,
            "career: {",
            "}\n    };",
        )
        self.assertIn("memoryEditingId", state_slice)
        self.assertIn("memoryEditSaving", state_slice)
        self.assertIn("memoryEditError", state_slice)

    def test_save_edit_calls_api_with_whitelisted_payload(self):
        body = extract_function_body(self.source, "async function saveCareerMemoryEdit(id)")
        self.assertIn("window.pywebview.api.update_career_memory_story", body)
        self.assertIn("const payload = {", body)
        self.assertIn("id: memoryId", body)
        self.assertIn("title: title", body)
        self.assertIn("story: story", body)
        self.assertIn("loadCareerMemory()", body)
        payload_block = extract_between(body, "const payload = {", "};")
        self.assertIn("id", payload_block)
        self.assertIn("title", payload_block)
        self.assertIn("story", payload_block)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, payload_block)
        self.assertNotIn("activity_id", payload_block)
        self.assertNotIn("race_id", payload_block)

    def test_save_edit_validates_before_backend_call(self):
        body = extract_function_body(self.source, "async function saveCareerMemoryEdit(id)")
        api_index = body.find("window.pywebview.api.update_career_memory_story")
        self.assertGreater(api_index, 0)
        validation_body = body[:api_index]
        self.assertIn("!memoryId", validation_body)
        self.assertIn("!title", validation_body)
        self.assertIn("!story", validation_body)
        self.assertIn("return;", validation_body)

    def test_deactivate_calls_api_with_id_only_and_refreshes(self):
        body = extract_function_body(self.source, "async function deactivateCareerMemoryItem(id)")
        self.assertIn("window.pywebview.api.deactivate_career_memory_item", body)
        self.assertIn("deactivate_career_memory_item({ id: memoryId })", body)
        self.assertIn("loadCareerMemory()", body)
        self.assertNotIn("delete ", body)
        self.assertNotIn("removeChild", body)

    def test_edit_frontend_keeps_data_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function renderCareerMemoryEditForm(item)",
                "function careerMemoryItemHtml(item)",
                "function beginCareerMemoryEdit(id)",
                "function cancelCareerMemoryEdit()",
                "async function saveCareerMemoryEdit(id)",
                "async function deactivateCareerMemoryItem(id)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)

    def test_mobile_style_keeps_memory_actions_wrapping(self):
        mobile_css = extract_between(
            self.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        self.assertIn(".career-memory-item-head", mobile_css)
        self.assertIn("flex-wrap: wrap", mobile_css)
        self.assertIn(".career-memory-item-actions", mobile_css)
        self.assertIn("justify-content: flex-start", mobile_css)


if __name__ == "__main__":
    unittest.main()
