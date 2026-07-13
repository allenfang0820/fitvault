import unittest
from pathlib import Path

import career_backend
import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"
API_CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"


class TestCareerMemoryRetirement(unittest.TestCase):
    def test_legacy_memory_backend_and_pywebview_interfaces_are_removed(self):
        retired = (
            "get_career_memory",
            "save_career_memory_story",
            "save_career_memory_media",
            "update_career_memory_story",
            "deactivate_career_memory_item",
            "pick_and_save_career_memory_photo",
        )
        for name in retired:
            self.assertFalse(hasattr(career_backend, name), name)
            self.assertFalse(hasattr(main.Api, name), name)

        self.assertTrue(hasattr(career_backend, "get_career_memory_gallery"))
        self.assertTrue(hasattr(main.Api, "get_career_memory_gallery"))
        self.assertTrue(hasattr(main.Api, "get_activity_race_photos"))

    def test_frontend_and_contract_have_no_legacy_memory_surface(self):
        source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        contract = API_CONTRACT_PATH.read_text(encoding="utf-8")
        retired = (
            "saveCareerMemoryStory",
            "saveCareerMemoryEdit",
            "deactivateCareerMemoryItem",
            "careerMemoryItemHtml",
            "career-memory-story-form",
            "career-memory-edit-form",
            '"name": "get_career_memory"',
            '"name": "save_career_memory_story"',
            '"name": "save_career_memory_media"',
            '"name": "update_career_memory_story"',
            '"name": "deactivate_career_memory_item"',
            '"name": "pick_and_save_career_memory_photo"',
        )
        for token in retired:
            self.assertNotIn(token, source + contract)

        self.assertIn("get_career_memory_gallery", source + contract)
        self.assertIn("get_activity_race_photos", contract)

    def test_season_and_snapshot_contracts_do_not_expose_memory_counts(self):
        backend_source = (PROJECT_ROOT / "career_backend.py").read_text(encoding="utf-8")
        frontend_source = TRACK_HTML_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"memory_count"', backend_source)
        self.assertNotIn("memoryCount", frontend_source)
        self.assertNotIn("careerSeasonPillHtml('memories'", frontend_source)
        self.assertNotIn("representative_memories", backend_source)


if __name__ == "__main__":
    unittest.main()
