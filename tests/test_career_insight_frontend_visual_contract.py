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
    "thumbnail_url",
    "detail_link",
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


class TestCareerInsightFrontendVisualContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.dom = extract_between(
            cls.source,
            '<section class="career-section" data-career-section="insight">',
            "</section>",
        )
        cls.css = extract_between(
            cls.source,
            ".career-insight-shell {",
            ".career-bucket-list {",
        )
        cls.mobile_css = extract_between(
            cls.source,
            "@media (max-width: 980px)",
            "/* V1.0:三个预留 tab",
        )
        cls.relevant_js = "\n".join(
            extract_function_body(cls.source, signature)
            for signature in (
                "function normalizeCareerInsight(payload)",
                "function careerInsightListHtml(items, className, label)",
                "function renderCareerInsight(viewModel)",
                "function renderCareerInsightLoading()",
                "function renderCareerInsightError(message)",
                "async function loadCareerInsight(options)",
            )
        )

    def test_placeholder_copy_is_local_and_not_misleading_ai_copy(self):
        self.assertIn("本地洞察将基于安全摘要生成", self.dom)
        self.assertIn("不会调用 AI", self.dom)
        self.assertIn("不会展示快照原文", self.dom)
        for text in (
            "AI 深度总结已生成",
            "AI 洞察已生成",
            "生成 AI 洞察",
            "Snapshot JSON",
            "调试 JSON",
        ):
            self.assertNotIn(text, self.dom)
            self.assertNotIn(text, self.relevant_js)

    def test_loading_low_data_and_error_copy_are_scoped_to_insight_block(self):
        self.assertIn("正在生成本地洞察", self.relevant_js)
        self.assertIn("需要更多生涯数据，本地洞察将基于安全摘要生成。", self.relevant_js)
        self.assertIn("本地洞察暂不可用", self.relevant_js)
        self.assertIn("生涯本地洞察接口暂不可用", self.relevant_js)
        self.assertNotIn("alert(", self.relevant_js)

    def test_highlights_and_next_steps_have_distinct_visual_blocks(self):
        self.assertIn(".career-insight-block", self.css)
        self.assertIn(".career-insight-block.next-steps", self.css)
        self.assertIn(".career-insight-block-label", self.css)
        self.assertIn(".career-insight-list.next-steps li::before", self.css)
        self.assertIn("阶段亮点", self.relevant_js)
        self.assertIn("下一步建议", self.relevant_js)
        self.assertIn("'highlights'", self.relevant_js)
        self.assertIn("'next-steps'", self.relevant_js)

    def test_disclaimer_and_disabled_button_are_visually_deemphasized(self):
        self.assertIn(".career-insight-action:disabled", self.css)
        self.assertIn("cursor: not-allowed", self.css)
        disclaimer_css = extract_between(
            self.css,
            ".career-insight-disclaimer {",
            ".career-insight-block {",
        )
        self.assertIn("border-top", disclaimer_css)
        self.assertIn("font-size: 0.62rem", disclaimer_css)
        self.assertIn("color: #64748b", disclaimer_css)

    def test_mobile_css_keeps_compact_single_column_insight_layout(self):
        self.assertIn(".career-insight-toolbar", self.mobile_css)
        self.assertIn("flex-direction: column", self.mobile_css)
        self.assertIn("align-items: flex-start", self.mobile_css)
        self.assertIn(".career-insight-block", self.mobile_css)
        self.assertIn("width: 100%", self.mobile_css)
        self.assertIn(".career-insight-list li", self.mobile_css)

    def test_frontend_visual_slice_does_not_expose_snapshot_or_forbidden_fields(self):
        relevant = "\n".join((self.dom, self.css, self.relevant_js))
        self.assertNotIn("<pre", relevant)
        self.assertNotIn("JSON.stringify", relevant)
        self.assertNotIn("get_latest_career_snapshot", relevant)
        self.assertNotIn("call_llm", relevant)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, self.relevant_js)


if __name__ == "__main__":
    unittest.main()
