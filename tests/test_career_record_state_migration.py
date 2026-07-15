import sqlite3
import unittest

import career_backend


def _decision(activity_id: str, elapsed_time_sec: int, *, time_quality: str = "reliable_elapsed") -> dict:
    summary = {
        "activity_id": activity_id,
        "sport": "running",
        "source_mode": "activity_total",
        "event_date": f"2026-07-{int(activity_id):02d}",
        "distance_m": 5000,
        "elapsed_time_sec": elapsed_time_sec,
        "distance_quality": "reliable_distance",
        "time_quality": time_quality,
        "reason_codes": (),
    }
    match = career_backend.match_record_definition(summary)
    return career_backend.build_record_candidate_decision(summary, match)


def _pb_rows(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT id, activity_id, pb_type, value, status, previous_record_id,
               improvement, evidence_key, resolver_version, decision_source
        FROM career_pb_records
        ORDER BY status, CAST(value AS INTEGER), id
        """
    ).fetchall()


def _event_types(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT event_type FROM career_record_events ORDER BY created_at, id"
        ).fetchall()
    ]


class CareerRecordStateMigrationTest(unittest.TestCase):
    def test_first_auto_confirm_activates_record_and_events(self):
        conn = sqlite3.connect(":memory:")
        try:
            decision = _decision("1", 1500)

            result = career_backend.apply_record_candidate_decision(conn, decision)

            self.assertEqual(result["action"], "activated")
            rows = _pb_rows(conn)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][1], "1")
            self.assertEqual(rows[0][3], "1500")
            self.assertEqual(rows[0][4], "active")
            self.assertIsNone(rows[0][5])
            self.assertEqual(rows[0][8], "records-v1")
            self.assertIn("detected", _event_types(conn))
            self.assertIn("activated", _event_types(conn))
        finally:
            conn.close()

    def test_faster_record_supersedes_previous_and_keeps_single_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            first = _decision("1", 1500)
            faster = _decision("2", 1450)

            career_backend.apply_record_candidate_decision(conn, first)
            result = career_backend.apply_record_candidate_decision(conn, faster)

            self.assertEqual(result["action"], "activated")
            rows = _pb_rows(conn)
            active = [row for row in rows if row[4] == "active"]
            superseded = [row for row in rows if row[4] == "superseded"]
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][1], "2")
            self.assertEqual(active[0][3], "1450")
            self.assertEqual(active[0][6], "50")
            self.assertEqual(len(superseded), 1)
            self.assertEqual(active[0][5], superseded[0][0])
            self.assertIn("superseded", _event_types(conn))
        finally:
            conn.close()

    def test_tie_or_slower_record_does_not_change_active(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.apply_record_candidate_decision(conn, _decision("1", 1500))

            tie = career_backend.apply_record_candidate_decision(conn, _decision("2", 1500))
            slower = career_backend.apply_record_candidate_decision(conn, _decision("3", 1600))

            self.assertEqual(tie["action"], "unchanged")
            self.assertEqual(slower["action"], "unchanged")
            active = [row for row in _pb_rows(conn) if row[4] == "active"]
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0][1], "1")
            self.assertEqual(active[0][3], "1500")
            self.assertGreaterEqual(_event_types(conn).count("recalculated"), 2)
        finally:
            conn.close()

    def test_medium_confidence_creates_idempotent_candidate_without_current_record(self):
        conn = sqlite3.connect(":memory:")
        try:
            decision = _decision("1", 1500, time_quality="semantics_unknown")

            first = career_backend.apply_record_candidate_decision(conn, decision)
            second = career_backend.apply_record_candidate_decision(conn, decision)

            self.assertEqual(first["action"], "candidate_created")
            self.assertEqual(first["candidate_id"], second["candidate_id"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_event_candidates").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
        finally:
            conn.close()

    def test_confirmed_candidate_rejoins_comparison_and_activates(self):
        conn = sqlite3.connect(":memory:")
        try:
            decision = _decision("1", 1500, time_quality="semantics_unknown")
            candidate = career_backend.apply_record_candidate_decision(conn, decision)

            result = career_backend.decide_career_pb_candidate(candidate["candidate_id"], "confirm", conn=conn)

            self.assertTrue(result["ok"])
            self.assertEqual(result["data"]["action"], "activated")
            row = _pb_rows(conn)[0]
            self.assertEqual(row[1], "1")
            self.assertEqual(row[4], "active")
            self.assertEqual(row[9], "user")
            status = conn.execute(
                "SELECT status FROM career_event_candidates WHERE id = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
            self.assertEqual(status, "confirmed")
            self.assertIn("user_confirmed", _event_types(conn))
        finally:
            conn.close()

    def test_rejected_candidate_does_not_enter_history_chain(self):
        conn = sqlite3.connect(":memory:")
        try:
            decision = _decision("1", 1500, time_quality="semantics_unknown")
            candidate = career_backend.apply_record_candidate_decision(conn, decision)

            result = career_backend.decide_career_pb_candidate(candidate["candidate_id"], "reject", conn=conn)

            self.assertTrue(result["ok"])
            self.assertEqual(result["data"]["action"], "rejected")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM career_pb_records").fetchone()[0], 0)
            status = conn.execute(
                "SELECT status FROM career_event_candidates WHERE id = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
            self.assertEqual(status, "rejected")
            self.assertIn("user_rejected", _event_types(conn))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

