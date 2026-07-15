import sqlite3
import unittest

import career_backend


def constant_power_activity(activity_id: str, watts: int, duration_sec: int = 7200):
    return {
        "activity": {
            "activity_id": activity_id,
            "sport_type": "cycling",
            "indoor_scope": "outdoor",
            "duration_sec": duration_sec,
            "event_date": f"2026-07-{int(activity_id):02d}",
            "power_source": "synthetic_power_meter",
        },
        "points": [
            {"t": 0, "power_w": watts},
            {"t": duration_sec, "power_w": watts},
        ],
    }


class CareerRecordCyclingPowerResolverTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY,
                sport_type TEXT,
                start_time TEXT,
                duration_sec INTEGER,
                deleted_at TEXT
            )
            """
        )
        self.conn.executemany(
            """
            INSERT INTO activities (id, sport_type, start_time, duration_sec, deleted_at)
            VALUES (?, 'cycling', ?, 3600, NULL)
            """,
            [
                (1, "2026-07-01T00:00:00Z"),
                (2, "2026-07-02T00:00:00Z"),
                (3, "2026-07-03T00:00:00Z"),
            ],
        )

    def tearDown(self):
        self.conn.close()

    def test_builds_nine_power_evidences_in_dry_run(self):
        data = constant_power_activity("1", 200)

        plan = career_backend.apply_cycling_power_duration_records(
            self.conn,
            data["points"],
            activity=data["activity"],
            dry_run=True,
        )

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["planned_count"], 9)
        self.assertEqual(plan["skipped"], [])
        keys = {evidence["record_key"] for evidence in plan["evidences"]}
        self.assertEqual(
            keys,
            {
                "cycling_power_5s",
                "cycling_power_30s",
                "cycling_power_1m",
                "cycling_power_5m",
                "cycling_power_10m",
                "cycling_power_20m",
                "cycling_power_30m",
                "cycling_power_60m",
                "cycling_power_2h",
            },
        )
        for evidence in plan["evidences"]:
            self.assertEqual(evidence["source_mode"], "best_effort_duration")
            self.assertEqual(evidence["metric"]["name"], "power_w")
            self.assertEqual(evidence["metric"]["unit"], "watts")
            self.assertEqual(evidence["quality"]["decision"], "auto_confirm")
            self.assertIn("start_sec", evidence["range_json"])

    def test_apply_replaces_lower_power_and_tie_is_unchanged(self):
        first = constant_power_activity("1", 200)
        second = constant_power_activity("2", 250)
        tie = constant_power_activity("3", 250)

        first_result = career_backend.apply_cycling_power_duration_records(
            self.conn,
            first["points"],
            activity=first["activity"],
            dry_run=False,
            run_id="test:first",
        )
        second_result = career_backend.apply_cycling_power_duration_records(
            self.conn,
            second["points"],
            activity=second["activity"],
            dry_run=False,
            run_id="test:second",
        )
        tie_result = career_backend.apply_cycling_power_duration_records(
            self.conn,
            tie["points"],
            activity=tie["activity"],
            dry_run=False,
            run_id="test:tie",
        )

        self.assertEqual(first_result["summary"], {"activated": 9})
        self.assertEqual(second_result["summary"], {"activated": 9})
        self.assertEqual(tie_result["summary"], {"unchanged": 9})
        records = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"]
        self.assertEqual(len(records), 9)
        self.assertTrue(all(record["metric"]["value"] == 250 for record in records))
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'superseded'").fetchone()[0],
            9,
        )

    def test_quality_degraded_power_anchor_becomes_candidate(self):
        activity = {
            "activity_id": "1",
            "sport_type": "cycling",
            "indoor_scope": "outdoor",
            "duration_sec": 26,
            "event_date": "2026-07-01",
        }
        points = [
            {"t": 0, "power_w": 180},
            {"t": 1, "power_w": 0},
            {"t": 2, "power_w": None},
            {"t": 4, "power_w": 250},
            {"t": 5, "power_w": 260},
            {"t": 6, "power_w": 900},
            {"t": 7, "power_w": 255},
            {"t": 20, "power_w": 240},
            {"t": 21, "power_w": 245},
            {"t": 23, "power_w": 250},
            {"t": 26, "power_w": 260},
        ]

        result = career_backend.apply_cycling_power_duration_records(
            self.conn,
            points,
            activity=activity,
            windows_sec=(5,),
            dry_run=False,
            run_id="test:candidate",
        )

        self.assertEqual(result["summary"], {"candidate_created": 1})
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM career_pb_records WHERE status = 'active'").fetchone()[0],
            0,
        )
        candidate = career_backend.get_career_record_candidates({"status": "candidate"}, conn=self.conn)["candidates"][0]
        self.assertEqual(candidate["record_key"], "cycling_power_5s")
        self.assertIn("power_stream_gap", candidate["quality"]["reason_codes"])

    def test_ebike_scope_is_ignored_without_evidence(self):
        result = career_backend.apply_cycling_power_duration_records(
            self.conn,
            [{"t": 0, "power_w": 200}, {"t": 3600, "power_w": 200}],
            activity={"activity_id": "1", "sport_type": "e_biking", "duration_sec": 3600},
            dry_run=True,
        )

        self.assertEqual(result["planned_count"], 0)
        self.assertTrue(result["skipped"])

    def test_activity_invalidation_promotes_same_scope_fallback(self):
        first = constant_power_activity("1", 200)
        second = constant_power_activity("2", 250)
        career_backend.apply_cycling_power_duration_records(
            self.conn,
            first["points"],
            activity=first["activity"],
            windows_sec=(5,),
            dry_run=False,
        )
        career_backend.apply_cycling_power_duration_records(
            self.conn,
            second["points"],
            activity=second["activity"],
            windows_sec=(5,),
            dry_run=False,
        )

        invalidated = career_backend.invalidate_career_record_state_for_activity(
            self.conn,
            "2",
            dry_run=False,
            reason="test_activity_deleted",
        )

        self.assertEqual(len(invalidated["invalidated"]), 1)
        self.assertEqual(len(invalidated["promoted"]), 1)
        active = career_backend.get_career_records({"sport": "cycling"}, conn=self.conn)["records"][0]
        self.assertEqual(active["activity_id"], "1")
        self.assertEqual(active["metric"]["value"], 200)


if __name__ == "__main__":
    unittest.main()
