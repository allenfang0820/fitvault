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


class TestCareerMemoryMediaFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_media_state_uses_safe_thumbnail_view_field_only(self):
        body = extract_function_body(self.source, "function careerMemoryAlbumCardHtml(album)")
        self.assertIn("cover.imageRef", body)
        self.assertIn("career-memory-album-art", body)
        self.assertIn("safeHtml(artTitle)", body)
        self.assertNotIn("暂无封面", body)
        self.assertIn("<img", body)
        self.assertIn("imageRef", body)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, body)

    def test_normalizer_accepts_only_safe_media_view_fields(self):
        body = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryPhoto(photo)",
            )
        )
        self.assertIn("thumbnail_url", body)
        self.assertIn("preview_url", body)
        self.assertIn("image_ref", body)
        self.assertIn("cover", body)
        self.assertNotIn("Object.assign", body)
        self.assertNotIn("...album", body)
        self.assertNotIn("...photo", body)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, body)

    def test_memory_section_has_no_photo_picker_entry(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        lowered = section.lower()
        self.assertNotIn('type="file"', lowered)
        self.assertNotIn("upload", lowered)
        self.assertNotIn("select_directory", lowered)
        self.assertNotIn("career-memory-photo-toggle", section)
        self.assertNotIn("career-memory-photo-form", section)
        self.assertNotIn("saveCareerMemoryPhoto()", section)
        self.assertNotIn("save_career_memory_media", section)

    def test_memory_frontend_keeps_media_boundary(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryPhoto(photo)",
                "function careerMemoryAlbumCardHtml(album)",
                "function renderCareerMemory(viewModel)",
            )
        )
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        self.assertNotIn("window.pywebview.api.save_career_memory_media", relevant)
        self.assertNotIn("window.pywebview.api.pick_and_save_career_memory_photo", relevant)

    def test_activity_detail_has_race_photo_manager_without_manual_activity_input(self):
        detail_section = extract_between(
            self.source,
            '<div class="detail-tab-panel active" id="detail-tab-overview">',
            '<!-- Row 1+2 Col 3: 3 张卡垂直堆叠',
        )
        self.assertIn("activity-race-photo-panel", detail_section)
        self.assertIn("activity-race-photo-grid", detail_section)
        self.assertNotIn("career-memory-photo-activity-id", detail_section)
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function activityRacePhotoCellHtml(photo, index)",
                "function renderActivityRacePhotoManager(record, viewModel)",
                "async function loadActivityRacePhotos(record)",
                "async function addActivityRacePhotos()",
                "async function reorderActivityRacePhotos(orderedIds)",
                "async function deleteActivityRacePhoto(event, photoId)",
            )
        )
        self.assertIn("record && record.is_race", relevant)
        self.assertIn("window.pywebview.api.get_activity_race_photos", relevant)
        self.assertIn("window.pywebview.api.pick_and_add_activity_race_photos", relevant)
        self.assertIn("window.pywebview.api.reorder_activity_race_photos", relevant)
        self.assertIn("window.pywebview.api.deactivate_activity_race_photo", relevant)
        self.assertIn(">+</button>", relevant)
        self.assertIn("draggable", relevant)
        self.assertNotIn("window.pywebview.api.save_career_memory_media", relevant)
        for token in FORBIDDEN_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)

    def test_activity_detail_open_path_resets_photo_gallery_without_blocking_detail_load(self):
        body = extract_function_body(self.source, "async function openActivityDetailModal(activityId)")
        self.assertIn("appState.activityRacePhotos = null", body)
        self.assertIn("renderActivityRacePhotoManager(null)", body)
        self.assertNotIn("renderActivityRacePhotoManager(null, appState.activityRacePhotos)", body)


if __name__ == "__main__":
    unittest.main()
