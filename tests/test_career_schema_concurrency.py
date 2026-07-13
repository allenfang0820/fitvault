import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import career_backend
import main
import profile_backend


class TestCareerSchemaConcurrency(unittest.TestCase):
    def test_parallel_career_read_apis_do_not_race_schema_ensure(self):
        original_db_path = profile_backend.DB_PATH
        original_ready = career_backend.CAREER_DEFAULT_SCHEMA_READY
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                profile_backend.DB_PATH = str(Path(tmpdir) / "career.sqlite")
                career_backend.CAREER_DEFAULT_SCHEMA_READY = False

                def call(name: str):
                    api = main.Api()
                    if name == "overview":
                        return name, api.get_career_overview()
                    if name == "seasons":
                        return name, api.get_career_seasons({})
                    if name == "timeline":
                        return name, api.get_career_timeline({})
                    if name == "races":
                        return name, api.get_career_races({})
                    if name == "pb":
                        return name, api.get_career_pb({})
                    if name == "achievements":
                        return name, api.get_career_achievements({})
                    if name == "candidates":
                        return name, api.get_career_event_candidates({"candidate_type": "pb_record", "status": "candidate"})
                    if name == "footprint":
                        return name, api.get_career_footprint({"year": "all", "sport": "all"})
                    if name == "memory":
                        return name, api.get_career_memory_gallery()
                    raise AssertionError(name)

                names = ["overview", "seasons", "timeline", "races", "pb", "achievements", "candidates", "footprint", "memory"]
                with ThreadPoolExecutor(max_workers=len(names)) as executor:
                    results = [future.result() for future in as_completed([executor.submit(call, name) for name in names])]

                failures = [(name, result) for name, result in results if not result.get("ok") or result.get("code") != 0]
                self.assertEqual(failures, [])
        finally:
            profile_backend.DB_PATH = original_db_path
            career_backend.CAREER_DEFAULT_SCHEMA_READY = original_ready


if __name__ == "__main__":
    unittest.main()
