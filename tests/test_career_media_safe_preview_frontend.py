import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_FRONTEND_MEDIA_TOKENS = (
    "storage_ref",
    "file_path",
    "file://",
    "/Users/",
    "\\Users\\",
    "/tmp/",
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


class TestCareerMediaSafePreviewFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_safe_preview_helper_only_accepts_data_image(self):
        body = extract_function_body(self.source, "function normalizeCareerSafeImagePreview(value)")
        self.assertIn("data:image/", body)
        self.assertIn("return preview.indexOf('data:image/') === 0 ? preview : ''", body)
        for token in FORBIDDEN_FRONTEND_MEDIA_TOKENS:
            self.assertNotIn(token, body)

    def test_overview_banner_uses_sanitized_backend_image_ref(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerHeroBanner(hero)")
        render_body = extract_function_body(self.source, "function renderCareerHeroBanner(hero)")
        photo_body = extract_function_body(self.source, "function setCareerHeroPhoto(imageRef, title)")
        reset_body = extract_function_body(self.source, "function resetCareerHeroPhotoLayers()")
        self.assertIn("normalizeCareerSafeImagePreview(media.image_ref || media.imageRef || '')", normalize_body)
        self.assertIn("activeHero.media.imageRef", render_body)
        self.assertIn("setCareerHeroPhoto(activeHero.media.imageRef", render_body)
        self.assertIn("nextLayer.src = imageRef", photo_body)
        self.assertIn("resetCareerHeroPhotoLayers()", render_body)
        self.assertIn("layer.removeAttribute('src')", reset_body)
        for token in FORBIDDEN_FRONTEND_MEDIA_TOKENS:
            self.assertNotIn(token, normalize_body + render_body + photo_body + reset_body)

    def test_activity_detail_uses_thumbnail_or_preview_url_without_manual_path_building(self):
        normalize_body = extract_function_body(self.source, "function normalizeActivityRacePhoto(item)")
        render_body = extract_function_body(self.source, "function activityRacePhotoCellHtml(photo, index)")
        self.assertIn("normalizeCareerSafeImagePreview(item.preview_url || item.thumbnail_url)", normalize_body)
        self.assertIn("photo.thumbnailUrl", render_body)
        self.assertIn("<img", render_body)
        self.assertNotIn("memory/photo/", normalize_body + render_body)
        for token in FORBIDDEN_FRONTEND_MEDIA_TOKENS:
            self.assertNotIn(token, normalize_body + render_body)

    def test_race_album_is_readonly_and_uses_safe_preview_fields(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        normalize_body = extract_function_body(self.source, "function normalizeCareerMemoryPhoto(photo)")
        render_body = extract_function_body(self.source, "function careerMemoryPhotoCellHtml(photo, index)")
        self.assertIn("normalizeCareerSafeImagePreview(photo.thumbnail_url)", normalize_body)
        self.assertIn("normalizeCareerSafeImagePreview(photo.preview_url)", normalize_body)
        self.assertIn("photo.thumbnailUrl", render_body)
        self.assertIn("<img", render_body)
        self.assertNotIn("save_career_memory_media", section)
        self.assertNotIn("pick_and_save_career_memory_photo", section)
        self.assertNotIn("career-memory-story-activity-id", section)
        for token in FORBIDDEN_FRONTEND_MEDIA_TOKENS:
            self.assertNotIn(token, section + normalize_body + render_body)


if __name__ == "__main__":
    unittest.main()
