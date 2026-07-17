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


def _flatten_nodes(timeline: dict):
    nodes = []
    for year in timeline["years"]:
        for month in year["months"]:
            nodes.extend(month["nodes"])
    return nodes


def _insert_record(conn: sqlite3.Connection, **overrides) -> None:
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "record:running_5k:1",
        "activity_id": "activity-1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-20",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": "{}",
        "record_key": "running_5k",
        "record_family": "distance_time_pb",
        "source_mode": "activity_total",
        "scope_hash": "scope:v2:running",
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
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "record_event:activated:1",
        "record_id": "record:running_5k:1",
        "activity_id": "activity-1",
        "pb_type": "running_5k",
        "event_type": "activated",
        "event_at": "2026-05-21 08:30:00",
        "evidence_key": "evidence:1",
        "resolver_version": "records-v2-test",
        "source": "resolver",
        "record_key": "running_5k",
        "scope_hash": "scope:v2:running",
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


def _insert_candidate(conn: sqlite3.Connection, **overrides) -> None:
    career_backend.ensure_career_schema(conn)
    data = {
        "id": "race_candidate:1",
        "activity_id": "activity-candidate",
        "candidate_type": "race",
        "title": "疑似赛事",
        "evidence_json": json.dumps({"reason": "title"}, ensure_ascii=False),
        "confidence": 0.5,
        "status": "candidate",
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_event_candidates ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerTimelineRecordEventNodes(unittest.TestCase):
    def test_type_record_returns_only_formal_record_event_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            _insert_record_event(conn)
            _insert_record_event(
                conn,
                id="record_event:user_confirmed:1",
                event_type="user_confirmed",
                decision="confirm",
                event_at="2026-05-21 08:31:00",
            )
            _insert_record_event(
                conn,
                id="record_event:detected:1",
                event_type="detected",
                event_at="2026-05-21 08:32:00",
            )

            result = career_backend.get_career_timeline({"type": "record"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(result["filters"], {"year": None, "type": "record"})
            self.assertEqual(result["available_years"], [2026])
            self.assertEqual(len(nodes), 2)
            self.assertEqual({node["type"] for node in nodes}, {"record"})
            self.assertEqual({node["event_type"] for node in nodes}, {"activated", "user_confirmed"})
            for node in nodes:
                self.assertEqual(node["track"], "record")
                self.assertEqual(node["record_id"], "record:running_5k:1")
                self.assertEqual(node["record_key"], "running_5k")
                self.assertEqual(node["sport"], "running")
                self.assertEqual(node["family"], "distance_time_pb")
                self.assertEqual(node["detail_link"], {
                    "activity_id": "activity-1",
                    "source": "career",
                    "record_id": "record:running_5k:1",
                })
                self.assertEqual(node["value"], "25:00")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_type_all_includes_record_nodes_without_reintroducing_pb_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            _insert_record_event(conn)

            result = career_backend.get_career_timeline({"type": "all"}, conn)
            nodes = _flatten_nodes(result)

            self.assertIn("record", {node["type"] for node in nodes})
            self.assertNotIn("pb", {node["type"] for node in nodes})
            self.assertIn("record_event:activated:1", {node["id"] for node in nodes})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_non_formal_events_and_race_candidates_do_not_enter_record_timeline(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            for event_type in ("detected", "candidate_created", "ignored", "recalculated", "user_rejected"):
                _insert_record_event(
                    conn,
                    id=f"record_event:{event_type}:1",
                    event_type=event_type,
                )
            _insert_candidate(conn)

            result = career_backend.get_career_timeline({"type": "record"}, conn)

            self.assertEqual(result["candidates_count"], 1)
            self.assertEqual(_flatten_nodes(result), [])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_year_filter_applies_to_record_nodes(self):
        conn = sqlite3.connect(":memory:")
        try:
            _insert_record(conn)
            _insert_record_event(conn, id="record_event:2026", event_at="2026-05-21 08:30:00")
            _insert_record_event(conn, id="record_event:2025", event_at="2025-05-21 08:30:00")

            result = career_backend.get_career_timeline({"type": "record", "year": "2026"}, conn)
            nodes = _flatten_nodes(result)

            self.assertEqual(result["available_years"], [2026, 2025])
            self.assertEqual([year["year"] for year in result["years"]], [2026])
            self.assertEqual([node["id"] for node in nodes], ["record_event:2026"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
