import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import career_backend
from fit_engine import FITCoreEngine
import main


class SwimSourceFactPersistenceTest(unittest.TestCase):
    def test_fit_session_reader_exposes_pool_source_fields(self):
        class FakeSessionMessage:
            fields = []

            def get_value(self, key):
                return {
                    "pool_length": 25,
                    "pool_length_unit": "m",
                    "swim_stroke": "freestyle",
                }.get(key)

        class FakeFit:
            def get_messages(self, name):
                return [FakeSessionMessage()] if name == "session" else []

        session = FITCoreEngine._read_session_info(FakeFit())

        self.assertEqual(session["pool_length"], 25)
        self.assertEqual(session["pool_length_unit"], "m")
        self.assertEqual(session["swim_stroke"], "freestyle")

    def test_fit_sync_parse_builds_pool_canonical_facts_from_session_fields(self):
        fake_core = {
            "basic_info": {
                "title": "Pool session",
                "title_source": "fit",
                "sport": "swimming",
                "sub_sport": "lap_swimming",
                "total_distance_km": 0.05,
                "total_timer_time": 62,
                "pool_length_m": 25,
                "pool_length_unit": "m",
                "swim_stroke": "freestyle",
            },
            "track_data": [],
            "lap_data": [
                {
                    "total_distance": 25,
                    "total_timer_time": 31,
                    "swim_stroke": "freestyle",
                    "lengths": 1,
                },
                {
                    "total_distance": 25,
                    "total_timer_time": 31,
                    "swim_stroke": "freestyle",
                    "lengths": 1,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            fit_path = Path(temp_dir) / "pool.fit"
            fit_path.write_bytes(b"fit")
            with mock.patch.object(main.FITCoreEngine, "parse_fit_file", return_value=fake_core):
                activity = main._parse_fit_activity_for_sync(fit_path)

        self.assertEqual(activity["swim_water_scope"], "pool_swimming")
        self.assertEqual(activity["swim_pool_length_m"], 25.0)
        self.assertEqual(activity["swim_pool_length_unit"], "m")
        self.assertEqual(activity["swim_pool_length_scope"], "scm_25m")
        self.assertEqual(activity["swim_stroke_scope"], "freestyle")
        self.assertEqual(
            json.loads(activity["swim_facts_quality_json"])["reason_codes"],
            [],
        )

    def test_schema_migration_and_canonical_activity_write_are_idempotent(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO activities DEFAULT VALUES")

            first = career_backend.apply_swim_canonical_facts_schema_migration(
                conn, dry_run=False
            )
            second = career_backend.apply_swim_canonical_facts_schema_migration(
                conn, dry_run=False
            )
            self.assertIn("activities.swim_pool_length_unit", first["added_columns"])
            self.assertEqual(second["added_columns"], [])

            fields = career_backend.build_swim_canonical_activity_fields(
                activity={
                    "sport_type": "swimming",
                    "sub_sport_type": "lap_swimming",
                    "pool_length_m": 50,
                    "pool_length_unit": "m",
                    "swim_stroke": "backstroke",
                },
                lengths=[{"elapsed_sec": 42, "swim_stroke": "backstroke"}],
            )
            main._update_activity_swim_canonical_facts(conn, 1, fields)
            row = conn.execute(
                """
                SELECT swim_water_scope, swim_pool_length_m,
                       swim_pool_length_unit, swim_pool_length_scope,
                       swim_stroke_scope, swim_facts_quality_json
                FROM activities WHERE id = 1
                """
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(dict(row)["swim_water_scope"], "pool_swimming")
        self.assertEqual(dict(row)["swim_pool_length_m"], 50.0)
        self.assertEqual(dict(row)["swim_pool_length_unit"], "m")
        self.assertEqual(dict(row)["swim_pool_length_scope"], "scm_50m")
        self.assertEqual(dict(row)["swim_stroke_scope"], "backstroke")
        self.assertEqual(json.loads(dict(row)["swim_facts_quality_json"])["state"], "high")

    def test_pool_resolver_uses_canonical_pool_fields_without_legacy_aliases(self):
        plan = career_backend.build_pool_swim_best_effort_evidences(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "lap_swimming",
                "swim_pool_length_m": 25,
                "swim_pool_length_unit": "m",
                "swim_stroke_scope": "freestyle",
                "id": 17,
                "start_time": "2026-07-01T08:00:00+08:00",
            },
            lengths=[
                {"elapsed_sec": 30, "swim_stroke": "freestyle"},
                {"elapsed_sec": 31, "swim_stroke": "freestyle"},
            ],
            target_distances_m=(50,),
        )

        self.assertEqual(len(plan["evidences"]), 1)
        evidence = plan["evidences"][0].to_dict()
        self.assertEqual(evidence["record_key"], "pool_swim_50m")
        self.assertEqual(
            evidence["scope_json"]["pool_length_scope"], "scm_25m"
        )

    def test_missing_canonical_pool_length_remains_controlled_empty_state(self):
        facts = career_backend.normalize_swim_canonical_facts(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "lap_swimming",
                "swim_pool_length_unit": "m",
            },
            lengths=[{"elapsed_sec": 30}],
        )

        self.assertIsNone(facts["pool_length_m"])
        self.assertIn("pool_length_missing", facts["quality"]["reason_codes"])

    def test_yard_pool_unit_is_never_treated_as_metric_pool_length(self):
        facts = career_backend.normalize_swim_canonical_facts(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "lap_swimming",
                "swim_pool_length_m": 25,
                "swim_pool_length_unit": "pool_length_unit_yard",
            },
            lengths=[{"elapsed_sec": 30}],
        )

        self.assertEqual(facts["pool_length_scope"], "")
        self.assertIn(
            "pool_length_yards_unsupported",
            facts["quality"]["reason_codes"],
        )


if __name__ == "__main__":
    unittest.main()
