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
    "advanced_metrics",
    "shadow_diff_json",
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


def _insert_pb(conn: sqlite3.Connection, **overrides) -> None:
    data = {
        "id": "pb:running_5k:1",
        "activity_id": "1",
        "sport": "running",
        "pb_type": "running_5k",
        "value": "1500",
        "value_unit": "seconds",
        "improvement": None,
        "event_date": "2026-05-19",
        "confidence": 1.0,
        "source": "resolver",
        "status": "active",
        "display_metadata_json": json.dumps(
            {
                "resolver": "pb",
                "pb_type": "running_5k",
                "track_json": "[forbidden]",
                "nested": {"file_path": "/tmp/a.fit", "safe": True},
            },
            ensure_ascii=False,
        ),
    }
    data.update(overrides)
    columns = list(data)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO career_pb_records ({', '.join(columns)}) VALUES ({placeholders})",
        [data[column] for column in columns],
    )


class TestCareerOverviewPbSummary(unittest.TestCase):
    def test_empty_pb_overview_shape_is_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_overview(conn)

            self.assertIsNone(result["latest_pb"])
            self.assertEqual(result["representative_pb_records"], [])
            self.assertEqual(result["summary"]["pb_count"], 0)
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_active_pb_enters_latest_pb(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", event_date="2026-05-19")
            _insert_pb(conn, id="pb:running_10k:2", activity_id="2", pb_type="running_10k", event_date="2026-06-01", improvement="120")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["pb_count"], 2)
            self.assertTrue(result["status"]["data_ready"])
            self.assertEqual(result["latest_pb"]["id"], "pb:running_10k:2")
            self.assertEqual(result["latest_pb"]["improvement_sec"], 120)
            self.assertEqual(result["latest_pb"]["detail_link"], {"activity_id": "2", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_superseded_pb_is_excluded_from_overview_pb_summary(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", status="active", event_date="2026-05-19")
            _insert_pb(conn, id="pb:running_5k:2", activity_id="2", status="superseded", event_date="2026-06-19")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["pb_count"], 1)
            self.assertEqual(result["latest_pb"]["id"], "pb:running_5k:1")
            self.assertEqual([record["id"] for record in result["representative_pb_records"]], ["pb:running_5k:1"])
        finally:
            conn.close()

    def test_representative_pb_records_are_limited_to_four(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            for index, pb_type in enumerate(
                ["running_5k", "running_10k", "running_half_marathon", "running_marathon", "cycling_distance"],
                start=1,
            ):
                _insert_pb(
                    conn,
                    id=f"pb:{pb_type}:{index}",
                    activity_id=str(index),
                    pb_type=pb_type,
                    sport="cycling" if pb_type.startswith("cycling") else "running",
                    event_date=f"2026-05-{index:02d}",
                )

            result = career_backend.get_career_overview(conn)

            self.assertEqual(result["summary"]["pb_count"], 5)
            self.assertEqual(len(result["representative_pb_records"]), 4)
            self.assertNotIn(
                "pb:cycling_distance:5",
                [record["id"] for record in result["representative_pb_records"]],
            )
        finally:
            conn.close()

    def test_representative_pb_records_follow_standard_running_priority(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_marathon:4", activity_id="4", pb_type="running_marathon", event_date="2026-05-04")
            _insert_pb(conn, id="pb:running_10k:2-old", activity_id="20", pb_type="running_10k", event_date="2026-05-02")
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", pb_type="running_5k", event_date="2026-05-01")
            _insert_pb(conn, id="pb:running_half_marathon:3", activity_id="3", pb_type="running_half_marathon", event_date="2026-05-03")
            _insert_pb(conn, id="pb:running_10k:2-new", activity_id="2", pb_type="running_10k", event_date="2026-06-02")

            result = career_backend.get_career_overview(conn)

            self.assertEqual(
                [record["id"] for record in result["representative_pb_records"]],
                [
                    "pb:running_5k:1",
                    "pb:running_10k:2-new",
                    "pb:running_10k:2-old",
                    "pb:running_half_marathon:3",
                ],
            )
            self.assertEqual(result["latest_pb"]["id"], "pb:running_10k:2-new")
        finally:
            conn.close()

    def test_pb_summary_records_keep_safe_detail_links(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_half_marathon:10", activity_id="10", pb_type="running_half_marathon", event_date="2026-07-01")

            result = career_backend.get_career_overview(conn)

            record = result["representative_pb_records"][0]
            self.assertEqual(record["detail_link"], {"activity_id": "10", "source": "career"})
            self.assertEqual(result["latest_pb"]["detail_link"], {"activity_id": "10", "source": "career"})
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
