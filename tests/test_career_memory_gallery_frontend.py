import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_GALLERY_FRONTEND_TOKENS = (
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "advanced_metrics",
    "shadow_diff_json",
    "sqlite_schema",
    "storage_ref",
    "file://",
    "/Users/",
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


class TestCareerMemoryGalleryFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_memory_section_contains_album_wall_targets(self):
        section = extract_between(
            self.source,
            '<section class="career-section" data-career-section="memory">',
            '</section>',
        )
        self.assertIn("赛事相册", section)
        self.assertIn('id="career-memory-list"', section)
        self.assertIn('id="career-memory-album-detail"', section)
        self.assertIn('id="career-memory-photo-modal"', section)
        self.assertIn('id="career-memory-empty"', section)
        self.assertIn("按赛事组织相册", section)
        self.assertNotIn('type="file"', section.lower())
        self.assertNotIn("save_career_memory_media", section)

    def test_load_career_memory_uses_gallery_api_and_envelope(self):
        body = extract_function_body(self.source, "async function loadCareerMemory(filters)")
        self.assertIn("api.get_career_memory_gallery", body)
        self.assertIn("requireCareerApiData(res, '赛事相册加载失败')", body)
        self.assertIn("normalizeCareerMemory(requireCareerApiData", body)
        self.assertIn("renderCareerMemoryLoading()", body)
        self.assertIn("renderCareerMemoryError(message)", body)
        self.assertIn("for (let attempt = 0; attempt < 2; attempt += 1)", body)
        self.assertIn("await waitCareerApiRetry(360)", body)
        self.assertNotIn("window.pywebview.api.get_career_memory(", body)

    def test_gallery_normalizers_use_album_whitelist_fields(self):
        relevant = "\n".join(
            extract_function_body(self.source, signature)
            for signature in (
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryAlbumFootprint(footprint)",
                "function normalizeCareerMemoryPhoto(photo)",
            )
        )
        for token in (
            "albums",
            "cover",
            "photos",
            "race_id",
            "activity_id",
            "title",
            "event_date",
            "display_date",
            "location",
            "image_ref",
            "thumbnail_url",
            "preview_url",
            "photo_count",
            "is_empty",
            "footprint",
            "region_key",
            "country_code",
            "map_mode",
            "detail_link",
        ):
            self.assertIn(token, relevant)
        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...album", relevant)
        self.assertNotIn("...photo", relevant)
        for token in FORBIDDEN_GALLERY_FRONTEND_TOKENS:
            self.assertNotIn(token, relevant)

    def test_album_card_is_four_three_clickable_and_uses_safe_cover(self):
        css = extract_between(
            self.source,
            ".career-memory-album-card {",
            ".career-memory-empty {",
        )
        body = extract_function_body(self.source, "function careerMemoryAlbumCardHtml(album)")
        self.assertIn("aspect-ratio: 4 / 3", css)
        self.assertIn("career-memory-album-cover", body)
        self.assertIn("career-memory-album-placeholder", body)
        self.assertIn("career-memory-album-art", body)
        self.assertIn("career-memory-album-art-word", body)
        self.assertIn("data-career-album-art-text", body)
        self.assertIn("cover.imageRef", body)
        self.assertIn('data-career-memory-album-id="', body)
        self.assertIn('onclick="openCareerMemoryAlbum(this)"', body)
        self.assertIn("safeHtml(title)", body)
        self.assertIn("safeHtml(artTitle)", body)
        self.assertIn("safeHtml(meta", body)
        self.assertNotIn("暂无封面", body)
        for token in FORBIDDEN_GALLERY_FRONTEND_TOKENS:
            self.assertNotIn(token, body)

    def test_album_empty_cover_fallback_matches_overview_banner_title_art_style(self):
        css = extract_between(
            self.source,
            ".career-memory-album-art {",
            ".career-memory-album-overlay {",
        )
        self.assertIn('"PingFang SC"', css)
        self.assertIn('"Microsoft YaHei UI"', css)
        self.assertIn("background-clip: text", css)
        self.assertIn("text-shadow", css)
        self.assertIn("opacity: 0.78", css)
        self.assertIn("skewX(-7deg)", css)
        self.assertIn("career-memory-album-art-word::after", css)
        self.assertIn("content: attr(data-career-album-art-text)", css)
        self.assertIn("scaleY(-0.52)", css)

    def test_render_memory_renders_albums_and_album_summary(self):
        body = extract_function_body(self.source, "function renderCareerMemory(viewModel)")
        self.assertIn("vm.albums", body)
        self.assertIn("careerMemoryAlbumCardHtml", body)
        self.assertIn("renderCareerMemoryAlbumDetail(selectedAlbum)", body)
        self.assertIn("albumCount", body)
        self.assertIn("emptyAlbumCount", body)
        self.assertIn("暂无赛事相册", body)
        self.assertNotIn("careerMemoryItemHtml", body)

    def test_album_click_expands_photo_grid_and_back_to_wall(self):
        open_body = extract_function_body(self.source, "function openCareerMemoryAlbum(el)")
        close_body = extract_function_body(self.source, "function closeCareerMemoryAlbum()")
        detail_body = extract_function_body(self.source, "function renderCareerMemoryAlbumDetail(album)")
        photo_body = extract_function_body(self.source, "function careerMemoryPhotoCellHtml(photo, index)")
        render_body = extract_function_body(self.source, "function renderCareerMemory(viewModel)")

        self.assertIn("selectedMemoryAlbumId", open_body)
        self.assertIn("focusCareerFootprintForAlbum(album)", open_body)
        self.assertIn("renderCareerMemory(appState.career.memory", open_body)
        self.assertIn("selectedMemoryAlbumId = ''", close_body)
        self.assertIn("clearCareerFootprintAlbumFocus()", close_body)
        self.assertIn("career-memory-album-detail", detail_body)
        self.assertIn("career-memory-photo-grid", detail_body)
        self.assertIn("careerMemoryPhotoCellHtml(photo, index)", detail_body)
        self.assertIn("返回相册墙", detail_body)
        self.assertIn("这个赛事还没有上传照片", detail_body)
        self.assertIn("career-memory-photo-cell", photo_body)
        self.assertIn("onerror=", photo_body)
        self.assertIn('onclick="openCareerMemoryPhoto(this)"', photo_body)
        self.assertIn("listEl.style.display = selectedAlbum ? 'none' : ''", render_body)
        for token in FORBIDDEN_GALLERY_FRONTEND_TOKENS:
            self.assertNotIn(token, detail_body + "\n" + photo_body)

    def test_album_click_focuses_footprint_map_from_structured_album_footprint(self):
        normalize_body = extract_function_body(self.source, "function normalizeCareerMemoryAlbumFootprint(footprint)")
        focus_body = extract_function_body(self.source, "function focusCareerFootprintForAlbum(album)")
        source_body = extract_function_body(self.source, "function findCareerFootprintRegionForAlbumFocus(regionKey, countryCode, mapMode)")
        mode_body = extract_function_body(self.source, "function careerAlbumFootprintMapMode(footprint)")
        clear_body = extract_function_body(self.source, "function clearCareerFootprintAlbumFocus()")

        self.assertIn("regionKey: String(raw.region_key || '')", normalize_body)
        self.assertIn("countryCode: String(raw.country_code || '')", normalize_body)
        self.assertIn("mapMode: ['world', 'china', 'japan', 'us'].indexOf(mapMode)", normalize_body)
        self.assertIn("footprint.countryCode === 'CN'", mode_body)
        self.assertIn("footprint.countryCode === 'JP'", mode_body)
        self.assertIn("footprint.mapMode === 'us'", mode_body)
        self.assertIn("/^US-[A-Z]{2}$/.test", mode_body)
        self.assertNotIn("footprint.countryCode === 'US' || footprint.mapMode === 'us'", mode_body)
        self.assertIn("careerAlbumFootprintMapRegionKey(footprint, mapMode)", focus_body)
        self.assertIn("findCareerFootprintRegionForAlbumFocus(regionKey, footprint.countryCode, mapMode)", focus_body)
        self.assertIn("sourceRegion && sourceRegion.activityCount", focus_body)
        self.assertIn("sourceRegion && sourceRegion.raceCount", focus_body)
        self.assertIn("appState.career.footprint.regions", source_body)
        self.assertIn("regions: [focusedRegion]", focus_body)
        self.assertIn("renderCareerFootprint({", focus_body)
        self.assertIn("当前相册足迹", focus_body)
        self.assertIn("renderCareerFootprint(appState.career.footprint", clear_body)
        self.assertNotIn("album.title", focus_body)
        self.assertNotIn("locationDisplay", focus_body)

    def test_photo_modal_supports_close_step_and_keyboard(self):
        open_body = extract_function_body(self.source, "function openCareerMemoryPhoto(el)")
        close_body = extract_function_body(self.source, "function closeCareerMemoryPhoto()")
        step_body = extract_function_body(self.source, "function stepCareerMemoryPhoto(delta)")
        modal_body = extract_function_body(self.source, "function renderCareerMemoryPhotoModal()")
        key_body = extract_function_body(self.source, "function onCareerMemoryPhotoModalKeydown(event)")

        self.assertIn("selectedMemoryPhotoIndex", open_body)
        self.assertIn("renderCareerMemoryPhotoModal()", open_body)
        self.assertIn("selectedMemoryPhotoIndex = -1", close_body)
        self.assertIn("Math.max(0, Math.min(photos.length - 1", step_body)
        self.assertIn("career-memory-photo-modal", modal_body)
        self.assertIn("photo.previewUrl || photo.thumbnailUrl", modal_body)
        self.assertIn("上一张", modal_body)
        self.assertIn("下一张", modal_body)
        self.assertIn("关闭", modal_body)
        self.assertIn("event.key === 'Escape'", key_body)
        self.assertIn("event.key === 'ArrowLeft'", key_body)
        self.assertIn("event.key === 'ArrowRight'", key_body)
        self.assertIn("document.addEventListener('keydown', onCareerMemoryPhotoModalKeydown)", self.source)
        for token in FORBIDDEN_GALLERY_FRONTEND_TOKENS:
            self.assertNotIn(token, open_body + close_body + step_body + modal_body + key_body)


if __name__ == "__main__":
    unittest.main()
