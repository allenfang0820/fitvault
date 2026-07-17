import json
import sqlite3
import unittest

import career_backend


FORBIDDEN_RESPONSE_KEYS = {
    "points",
    "points_json",
    "track_json",
    "raw_records",
    "fit_records",
    "file_path",
    "evidence_json",
    "payload_json",
    "sqlite_schema",
    "schema",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _insert_record(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "record:running_5k",
        "activity_id": "activity-running-5k",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "event_date": "2026-05-20",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
        "record_key": "running_5k",
        "record_family": "distance_time_pb",
        "source_mode": "best_effort_distance",
        "scope_hash": "scope:running",
        "scope_key": "default",
        "scope_json": json.dumps({"sport_scope": "default"}, ensure_ascii=False),
        "catalog_state": "available",
        "metric_value_num": 1500,
        "metric_name": "elapsed_time_sec",
        "rule_version": "records-v2-test",
    }
    data.update(overrides)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_pb_records)").fetchall()}
    payload = {key: value for key, value in data.items() if key in columns}
    placeholders = ", ".join("?" for _ in payload)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(payload)}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def _insert_record_event(conn: sqlite3.Connection, **overrides) -> None:
    record_id = str(overrides.get("record_id") or "record:running_5k")
    record_key = str(overrides.get("record_key") or "running_5k")
    data = {
        "id": f"record_event:activated:{record_id}",
        "record_id": record_id,
        "activity_id": str(overrides.get("activity_id") or "activity-running-5k"),
        "pb_type": record_key,
        "event_type": "activated",
        "event_at": "2026-05-21 08:30:00",
        "evidence_key": "evidence:1",
        "resolver_version": "records-v2-test",
        "source": "resolver",
        "record_key": record_key,
        "scope_hash": "scope:test",
        "scope_key": "default",
        "run_id": "run:1",
        "decision": "activate",
        "reason_codes_json": "[]",
        "payload_json": json.dumps(
            {
                "evidence_json": {"file_path": "/tmp/hidden.fit"},
                "points_json": "[forbidden]",
            },
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_record_events)").fetchall()}
    payload = {key: value for key, value in data.items() if key in columns}
    placeholders = ", ".join("?" for _ in payload)
    conn.execute(
        f"INSERT INTO career_record_events ({', '.join(payload)}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def _insert_achievement(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "achievement:record:first_formal_record",
        "activity_id": "activity-running-5k",
        "achievement_type": "record_first_formal_record",
        "title": "首次建立正式记录",
        "event_date": "2026-05-21",
        "score": 70,
        "icon": "sparkles",
        "description": "记录中心首次拥有可确认的正式个人记录",
        "confidence": 1.0,
        "source": "record_derived",
        "status": "active",
        "display_metadata_json": json.dumps(
            {"resolver": "record_derived_achievement"},
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(career_achievement_events)").fetchall()}
    payload = {key: value for key, value in data.items() if key in columns}
    placeholders = ", ".join("?" for _ in payload)
    conn.execute(
        f"INSERT INTO career_achievement_events ({', '.join(payload)}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def _insert_candidate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO career_event_candidates
            (id, activity_id, candidate_type, title, evidence_json, confidence, status)
        VALUES
            ('candidate:record:1', 'activity-candidate', 'pb_record', '候选纪录',
             '{"file_path": "/tmp/hidden.fit"}', 0.9, 'candidate')
        """
    )


class RecordDerivedAchievementPlannerTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        career_backend.ensure_career_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _achievement_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM career_achievement_events").fetchone()[0])

    def test_formal_event_creates_first_formal_record_plan_without_writing(self):
        _insert_record(self.conn)
        _insert_record_event(self.conn)
        before = self._achievement_count()

        result = career_backend.plan_record_derived_achievements(conn=self.conn)

        self.assertTrue(result["ok"])
        self.assertEqual(self._achievement_count(), before)
        plans = result["plans"]
        self.assertEqual([plan["achievement_type"] for plan in plans], ["record_first_formal_record"])
        plan = plans[0]
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["rule_id"], "record_first_formal_record")
        self.assertEqual(plan["source"], "record_derived")
        self.assertEqual(plan["trigger"], "first_formal_record")
        self.assertEqual(plan["record_ids"], ["record:running_5k"])
        self.assertEqual(plan["record_keys"], ["running_5k"])
        self.assertEqual(plan["source_event_ids"], ["record_event:activated:record:running_5k"])
        self.assertEqual(plan["sports"], ["running"])
        self.assertEqual(plan["families"], ["distance_time_pb"])
        self.assertTrue(plan["is_writable"])
        self.assertEqual(result["summary"]["planned"], 1)
        _assert_forbidden_keys_absent(self, result)

    def test_non_formal_events_candidates_and_analysis_records_do_not_trigger_plans(self):
        _insert_record(self.conn)
        for event_type in ("detected", "candidate_created", "ignored", "recalculated", "user_rejected"):
            _insert_record_event(
                self.conn,
                id=f"record_event:{event_type}",
                event_type=event_type,
            )
        _insert_candidate(self.conn)
        _insert_record(
            self.conn,
            id="record:analysis:curve",
            activity_id="activity-analysis",
            sport="trail_running",
            pb_type="trail_pace_curve",
            record_key="trail_pace_curve",
            record_family="analysis_curve",
            catalog_state="analysis_only",
        )
        _insert_record_event(
            self.conn,
            id="record_event:analysis:activated",
            record_id="record:analysis:curve",
            activity_id="activity-analysis",
            record_key="trail_pace_curve",
            pb_type="trail_pace_curve",
            event_type="activated",
        )

        result = career_backend.plan_record_derived_achievements(conn=self.conn)

        self.assertEqual(result["plans"], [])
        self.assertEqual(result["summary"], {"total": 0, "planned": 0, "already_active": 0, "unsupported": 0, "writable": 0})
        _assert_forbidden_keys_absent(self, result)

    def test_same_sport_three_active_record_keys_create_sport_coverage_plan(self):
        for index, record_key in enumerate(("running_5k", "running_10k", "running_half_marathon"), start=1):
            record_id = f"record:{record_key}"
            _insert_record(
                self.conn,
                id=record_id,
                activity_id=f"activity-running-{index}",
                pb_type=record_key,
                record_key=record_key,
                event_date=f"2026-05-{20 + index:02d}",
            )
            _insert_record_event(
                self.conn,
                id=f"record_event:activated:{record_key}",
                record_id=record_id,
                activity_id=f"activity-running-{index}",
                pb_type=record_key,
                record_key=record_key,
                event_at=f"2026-05-{20 + index:02d} 08:30:00",
            )

        result = career_backend.plan_record_derived_achievements(conn=self.conn)

        by_type = {plan["achievement_type"]: plan for plan in result["plans"]}
        self.assertIn("record_first_formal_record", by_type)
        self.assertIn("record_sport_coverage_3", by_type)
        sport_plan = by_type["record_sport_coverage_3"]
        self.assertEqual(sport_plan["status"], "planned")
        self.assertEqual(sport_plan["rule_id"], "record_sport_coverage_3:running")
        self.assertEqual(sport_plan["sports"], ["running"])
        self.assertEqual(
            sport_plan["record_keys"],
            ["running_10k", "running_5k", "running_half_marathon"],
        )
        self.assertGreaterEqual(len(sport_plan["source_event_ids"]), 3)

    def test_three_sports_create_multi_sport_coverage_plan(self):
        records = (
            ("record:running_5k", "activity-running", "running", "running_5k", "distance_time_pb"),
            ("record:cycling_longest_distance", "activity-cycling", "cycling", "cycling_longest_distance", "activity_total_record"),
            ("record:hiking_longest_distance", "activity-hiking", "hiking", "hiking_longest_distance", "activity_total_record"),
        )
        for index, (record_id, activity_id, sport, record_key, family) in enumerate(records, start=1):
            _insert_record(
                self.conn,
                id=record_id,
                activity_id=activity_id,
                sport=sport,
                pb_type=record_key,
                record_key=record_key,
                record_family=family,
                event_date=f"2026-06-{index:02d}",
            )
            _insert_record_event(
                self.conn,
                id=f"record_event:activated:{record_key}",
                record_id=record_id,
                activity_id=activity_id,
                pb_type=record_key,
                record_key=record_key,
                event_at=f"2026-06-{index:02d} 08:30:00",
            )

        result = career_backend.plan_record_derived_achievements(conn=self.conn)

        by_type = {plan["achievement_type"]: plan for plan in result["plans"]}
        multi_plan = by_type["record_multi_sport_coverage_3"]
        self.assertEqual(multi_plan["status"], "planned")
        self.assertEqual(multi_plan["rule_id"], "record_multi_sport_coverage_3")
        self.assertEqual(multi_plan["sports"], ["cycling", "hiking", "running"])
        self.assertEqual(result["summary"]["planned"], 2)

    def test_existing_active_record_derived_achievement_returns_already_active(self):
        _insert_record(self.conn)
        _insert_record_event(self.conn)
        _insert_achievement(self.conn)
        before = self._achievement_count()

        result = career_backend.plan_record_derived_achievements(conn=self.conn)

        self.assertEqual(self._achievement_count(), before)
        self.assertEqual(result["plans"][0]["achievement_type"], "record_first_formal_record")
        self.assertEqual(result["plans"][0]["status"], "already_active")
        self.assertFalse(result["plans"][0]["is_writable"])
        self.assertEqual(result["summary"]["planned"], 0)
        self.assertEqual(result["summary"]["already_active"], 1)

    def test_planner_is_stable_and_does_not_return_per_event_achievements(self):
        _insert_record(self.conn)
        for index, event_type in enumerate(("activated", "user_confirmed", "activated_from_rebuild"), start=1):
            _insert_record_event(
                self.conn,
                id=f"record_event:{event_type}:{index}",
                event_type=event_type,
                event_at=f"2026-05-21 08:3{index}:00",
            )

        first = career_backend.plan_record_derived_achievements(conn=self.conn)
        second = career_backend.plan_record_derived_achievements(conn=self.conn)

        self.assertEqual(first, second)
        self.assertEqual(len(first["plans"]), 1)
        self.assertEqual(first["plans"][0]["achievement_type"], "record_first_formal_record")
        self.assertNotIn("record_event_activated", json.dumps(first, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
