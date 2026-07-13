import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"

FORBIDDEN_SECURITY_TOKENS = (
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "storage_ref",
    "sqlite_schema",
    "file://",
    "/Users/",
    "\\Users\\",
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


def _assert_no_forbidden(testcase: unittest.TestCase, value) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    for token in FORBIDDEN_SECURITY_TOKENS:
        testcase.assertNotIn(token, serialized)


class TestCareerFootprintMemoryGallerySecurity(unittest.TestCase):
    def test_frontend_new_normalizers_do_not_passthrough_raw_objects_or_forbidden_fields(self):
        source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        relevant = "\n".join(
            extract_function_body(source, signature)
            for signature in (
                "function normalizeCareerFootprintRegion(item)",
                "function normalizeCareerFootprintMissing(item)",
                "function normalizeCareerFootprint(payload)",
                "function normalizeCareerMemory(payload)",
                "function normalizeCareerMemoryAlbum(album)",
                "function normalizeCareerMemoryPhoto(photo)",
                "function careerMemoryAlbumCardHtml(album)",
                "function renderCareerMemoryPhotoModal()",
            )
        )

        self.assertNotIn("Object.assign", relevant)
        self.assertNotIn("...item", relevant)
        self.assertNotIn("...album", relevant)
        self.assertNotIn("...photo", relevant)
        for token in FORBIDDEN_SECURITY_TOKENS:
            self.assertNotIn(token, relevant)
        self.assertNotIn("get_career_memory(", extract_function_body(source, "async function loadCareerMemory(filters)"))

    def test_backend_footprint_and_gallery_do_not_return_forbidden_fields(self):
        original_tracks_dir = profile_backend.TRACKS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_backend.TRACKS_DIR = Path(tmpdir) / "workspace" / "tracks"
            profile_backend.TRACKS_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(":memory:")
            try:
                conn.execute(
                    """
                    CREATE TABLE activities (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        start_time TEXT,
                        sport_type TEXT,
                        region_city TEXT,
                        region_country TEXT,
                        deleted_at TEXT,
                        is_race INTEGER DEFAULT 1,
                        points_json TEXT,
                        track_json TEXT,
                        file_path TEXT
                    )
                    """
                )
                career_backend.ensure_career_schema(conn)
                conn.execute(
                    """
                    INSERT INTO activities
                        (id, title, start_time, sport_type, region_city, region_country,
                         deleted_at, is_race, points_json, track_json, file_path)
                    VALUES
                        (1, 'Forbidden Title /tmp/private.fit', '2026-05-19T08:00:00+08:00',
                         'running', '成都市', '中国', NULL, 1, '[forbidden]', '[forbidden]', '/Users/private.fit')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO career_race_events
                        (id, activity_id, name, event_type, sport, event_date,
                         location_json, performance_summary_json, confidence, source, status, display_metadata_json)
                    VALUES
                        ('race:1', '1', '苏州 10K', '10k', 'running', '2026-05-19',
                         '{"city":"苏州"}', '{}', 1.0, 'user', 'active', '{}')
                    """
                )

                footprint = career_backend.get_career_footprint(conn=conn)
                gallery = career_backend.get_career_memory_gallery(conn=conn)

                _assert_no_forbidden(self, footprint)
                _assert_no_forbidden(self, gallery)
                self.assertEqual(footprint["map_mode"], "china")
                self.assertEqual(gallery["summary"]["album_count"], 1)
            finally:
                conn.close()
                profile_backend.TRACKS_DIR = original_tracks_dir


if __name__ == "__main__":
    unittest.main()
