import sqlite3
import unittest

import career_backend


class CareerRecordSwimCanonicalFactsTest(unittest.TestCase):
    def test_pool_swim_25m_lengths_are_normalized_without_defaulting(self):
        facts = career_backend.normalize_swim_canonical_facts(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "lap_swimming",
                "pool_length_m": 25,
                "stroke_scope": "freestyle",
            },
            lengths=[
                {"index": 0, "elapsed_sec": 31, "stroke": "freestyle", "rest_after_sec": 0},
                {"index": 1, "elapsed_sec": 32, "stroke": "freestyle", "rest_after_sec": 45},
            ],
        )

        self.assertEqual(facts["water_scope"], "pool_swimming")
        self.assertEqual(facts["pool_length_scope"], "scm_25m")
        self.assertEqual(facts["stroke_scope"], "freestyle")
        self.assertEqual(len(facts["lengths"]), 2)
        self.assertEqual(facts["lengths"][0]["distance_m"], 25.0)
        self.assertEqual(facts["quality"]["state"], "high")

    def test_missing_pool_length_does_not_default_to_25m(self):
        facts = career_backend.normalize_swim_canonical_facts(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "lap_swimming",
                "stroke_scope": "unknown",
            },
            lengths=[{"index": 0, "elapsed_sec": 30}],
        )

        self.assertEqual(facts["water_scope"], "pool_swimming")
        self.assertIsNone(facts["pool_length_m"])
        self.assertEqual(facts["pool_length_scope"], "")
        self.assertEqual(facts["lengths"], [])
        self.assertEqual(facts["quality"]["state"], "ignored")
        self.assertIn("pool_length_missing", facts["quality"]["reason_codes"])

    def test_open_water_scope_does_not_require_pool_length(self):
        facts = career_backend.normalize_swim_canonical_facts(
            activity={
                "sport_type": "swimming",
                "sub_sport_type": "open_water",
                "distance_m": 1500,
            },
            lengths=None,
        )

        self.assertEqual(facts["water_scope"], "open_water_swimming")
        self.assertIsNone(facts["pool_length_m"])
        self.assertEqual(facts["pool_length_scope"], "")

    def test_schema_migration_plan_and_apply_are_explicit(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE activities (id INTEGER PRIMARY KEY)")
            plan = career_backend.plan_swim_canonical_facts_schema_migration(conn)
            self.assertTrue(plan["dry_run"])
            self.assertIn("swim_pool_length_m", plan["missing_columns"])

            applied = career_backend.apply_swim_canonical_facts_schema_migration(conn, dry_run=False)
            self.assertFalse(applied["dry_run"])
            followup = career_backend.plan_swim_canonical_facts_schema_migration(conn)
            self.assertEqual(followup["missing_columns"], [])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
