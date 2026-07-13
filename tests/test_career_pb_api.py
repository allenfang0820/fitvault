import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_backend
import main
import profile_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"

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
FORBIDDEN_METADATA_KEYS = FORBIDDEN_RESPONSE_KEYS | {
    "storage_ref",
    "path",
    "thumbnail_url",
    "detail_link",
}


def _assert_forbidden_keys_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_RESPONSE_KEYS)
            _assert_forbidden_keys_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_keys_absent(testcase, child)


def _assert_forbidden_metadata_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key), FORBIDDEN_METADATA_KEYS)
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_metadata_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("/tmp/", value)


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
                "distance_km": 5.0,
                "matched_range_km": [4.8, 5.3],
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


class TestCareerPbApi(unittest.TestCase):
    def test_backend_empty_state_returns_stable_shape(self):
        conn = sqlite3.connect(":memory:")
        try:
            result = career_backend.get_career_pb(conn=conn)

            self.assertEqual(result["pb_records"], [])
            self.assertEqual(result["summary"], {
                "total": 0,
                "by_pb_type": {},
                "by_sport": {},
                "by_year": {},
            })
            self.assertEqual(result["filters"], {
                "sport": "all",
                "year": None,
                "pb_type": "all",
                "source": "all",
            })
            self.assertTrue(result["status"]["schema_ready"])
            self.assertFalse(result["status"]["data_ready"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_returns_only_active_pb_records(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", status="active")
            _insert_pb(conn, id="pb:running_5k:2", activity_id="2", status="superseded")

            result = career_backend.get_career_pb(conn=conn)

            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(len(result["pb_records"]), 1)
            record = result["pb_records"][0]
            self.assertEqual(record["id"], "pb:running_5k:1")
            self.assertEqual(record["activity_id"], "1")
            self.assertEqual(record["pb_title"], "5K PB")
            self.assertEqual(record["pb_type_label"], "5K")
            self.assertEqual(record["sport_label"], "跑步")
            self.assertEqual(record["value"], 1500)
            self.assertEqual(record["value_unit"], "seconds")
            self.assertEqual(record["value_display"], "25:00")
            self.assertIsNone(record["improvement_sec"])
            self.assertEqual(record["improvement_display"], "首次记录")
            self.assertEqual(record["year"], 2026)
            self.assertEqual(record["month"], 5)
            self.assertEqual(record["display_date"], "2026-05-19")
            self.assertEqual(record["source_label"], "规则识别")
            self.assertEqual(record["source_mode"], "activity_total")
            self.assertEqual(record["source_mode_label"], "整场活动")
            self.assertEqual(record["resolver_version"], "legacy")
            self.assertEqual(record["status"], "active")
            self.assertEqual(record["confidence_label"], "高置信度")
            self.assertEqual(record["detail_link"], {"activity_id": "1", "source": "career", "record_id": "pb:running_5k:1"})
            self.assertIn("candidate_count", result["status"])
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_pb_archive_display_fields_are_stable(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(
                conn,
                id="pb:running_half_marathon:1",
                activity_id="9",
                pb_type="running_half_marathon",
                value="5415",
                improvement="75",
                event_date="2026-08-09",
                display_metadata_json=json.dumps({"confidence_level": "medium"}, ensure_ascii=False),
            )

            result = career_backend.get_career_pb(conn=conn)

            record = result["pb_records"][0]
            self.assertEqual(record["pb_title"], "半程马拉松 PB")
            self.assertEqual(record["pb_type_label"], "半程马拉松")
            self.assertEqual(record["value_display"], "1:30:15")
            self.assertEqual(record["improvement_display"], "提升 1:15")
            self.assertEqual(record["confidence_label"], "中置信度")
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_backend_returns_pb_detail_and_history(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(
                conn,
                id="pb:running_5k:old",
                activity_id="1",
                value="1600",
                event_date="2026-05-01",
                status="superseded",
                evidence_key="activity_total:1:running_5k:1600",
                resolver_version="records-v1",
            )
            _insert_pb(
                conn,
                id="pb:running_5k:new",
                activity_id="2",
                value="1500",
                improvement="100",
                event_date="2026-06-01",
                status="active",
                previous_record_id="pb:running_5k:old",
                evidence_key="activity_total:2:running_5k:1500",
                resolver_version="records-v1",
            )

            detail = career_backend.get_career_pb_detail("pb:running_5k:new", conn=conn)
            history = career_backend.get_career_pb_history("running_5k", conn=conn)

            self.assertTrue(detail["status"]["data_ready"])
            self.assertEqual(detail["record"]["previous_record_id"], "pb:running_5k:old")
            self.assertEqual(detail["record"]["resolver_version"], "records-v1")
            self.assertEqual([record["id"] for record in history["records"]], ["pb:running_5k:old", "pb:running_5k:new"])
            self.assertEqual(history["records"][0]["status"], "superseded")
            _assert_forbidden_keys_absent(self, detail)
            _assert_forbidden_keys_absent(self, history)
        finally:
            conn.close()

    def test_backend_filters_by_sport_year_pb_type_and_source(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", sport="running", pb_type="running_5k", source="resolver", event_date="2026-05-19")
            _insert_pb(conn, id="pb:running_10k:2", activity_id="2", sport="running", pb_type="running_10k", source="resolver", event_date="2026-06-01")
            _insert_pb(conn, id="pb:cycling_distance:3", activity_id="3", sport="cycling", pb_type="cycling_distance", source="manual", event_date="2025-04-01")

            result = career_backend.get_career_pb(
                {"sport": "running", "year": "2026", "pb_type": "running_10k", "source": "resolver"},
                conn=conn,
            )

            self.assertEqual(result["filters"], {
                "sport": "running",
                "year": 2026,
                "pb_type": "running_10k",
                "source": "resolver",
            })
            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(result["pb_records"][0]["id"], "pb:running_10k:2")
        finally:
            conn.close()

    def test_backend_summary_counts_returned_pb_records(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(conn, id="pb:running_5k:1", activity_id="1", sport="running", pb_type="running_5k", event_date="2026-05-19")
            _insert_pb(conn, id="pb:running_10k:2", activity_id="2", sport="running", pb_type="running_10k", event_date="2026-06-01", improvement="120")
            _insert_pb(conn, id="pb:cycling_distance:3", activity_id="3", sport="cycling", pb_type="cycling_distance", event_date="2025-04-01")

            result = career_backend.get_career_pb(conn=conn)

            self.assertEqual(result["summary"]["total"], 3)
            self.assertEqual(result["summary"]["by_pb_type"], {
                "running_10k": 1,
                "running_5k": 1,
                "cycling_distance": 1,
            })
            self.assertEqual(result["summary"]["by_sport"], {"running": 2, "cycling": 1})
            self.assertEqual(result["summary"]["by_year"], {"2026": 2, "2025": 1})
            self.assertEqual([record["id"] for record in result["pb_records"]], [
                "pb:running_10k:2",
                "pb:running_5k:1",
                "pb:cycling_distance:3",
            ])
            self.assertEqual(result["pb_records"][0]["improvement_sec"], 120)
        finally:
            conn.close()

    def test_backend_sanitizes_forbidden_metadata_keys(self):
        conn = sqlite3.connect(":memory:")
        try:
            career_backend.ensure_career_schema(conn)
            _insert_pb(
                conn,
                display_metadata_json=json.dumps(
                    {
                        "resolver": "pb",
                        "track_json": "[forbidden]",
                        "storage_ref": "/Users/private/pb.jpg",
                        "path": "/tmp/private.fit",
                        "thumbnail_url": "file:///Users/private/thumb.jpg",
                        "detail_link": {"activity_id": "999", "source": "leak"},
                        "nested": {
                            "file_path": "/tmp/a.fit",
                            "distance_km": 5.0,
                            "items": [
                                {"detail_link": {"activity_id": "2"}},
                                {"safe": "kept"},
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
            )

            result = career_backend.get_career_pb(conn=conn)

            metadata = result["pb_records"][0]["display_metadata"]
            self.assertEqual(
                metadata,
                {
                    "resolver": "pb",
                    "nested": {
                        "distance_km": 5.0,
                        "items": [{}, {"safe": "kept"}],
                    },
                },
            )
            _assert_forbidden_metadata_absent(self, metadata)
            _assert_forbidden_keys_absent(self, result)
        finally:
            conn.close()

    def test_main_api_get_career_pb_returns_unified_envelope(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-pb-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                    _insert_pb(conn, id="pb:running_half_marathon:10", activity_id="10", pb_type="running_half_marathon", event_date="2026-07-01")
                    conn.commit()
                finally:
                    conn.close()

                response = main.Api().get_career_pb({"pb_type": "running_half_marathon"})

                self.assertTrue(response["ok"])
                self.assertEqual(response["code"], main.API_CODE_OK)
                self.assertEqual(response["msg"], "ok")
                self.assertIsInstance(response["traceId"], str)
                self.assertEqual(response["data"]["summary"]["total"], 1)
                self.assertEqual(response["data"]["pb_records"][0]["activity_id"], "10")
                _assert_forbidden_keys_absent(self, response["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_pywebview_wrappers_return_pb_detail_and_history(self):
        original_db_path = profile_backend.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                profile_backend.DB_PATH = Path(tmpdir) / "career-pb-api.sqlite"
                conn = sqlite3.connect(str(profile_backend.DB_PATH))
                try:
                    career_backend.ensure_career_schema(conn)
                    _insert_pb(conn, id="pb:running_5k:1", activity_id="1")
                    conn.commit()
                finally:
                    conn.close()

                api = main.Api()
                detail = api.get_career_pb_detail("pb:running_5k:1")
                history = api.get_career_pb_history("running_5k")

                self.assertTrue(detail["ok"])
                self.assertEqual(detail["data"]["record"]["id"], "pb:running_5k:1")
                self.assertTrue(history["ok"])
                self.assertEqual(history["data"]["records"][0]["id"], "pb:running_5k:1")
                _assert_forbidden_keys_absent(self, detail["data"])
                _assert_forbidden_keys_absent(self, history["data"])
            finally:
                profile_backend.DB_PATH = original_db_path

    def test_js_api_contract_registers_get_career_pb(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        self.assertIn("get_career_pb", methods)
        self.assertIn("get_career_pb_detail", methods)
        self.assertIn("get_career_pb_history", methods)
        method = methods["get_career_pb"]
        self.assertEqual(method["category"], "career")
        self.assertFalse(method["high_risk"])
        self.assertTrue(method["readonly"])
        self.assertIn("pb_records", method["returns"])
        self.assertIn("value_display", method["returns"])
        self.assertIn("improvement_display", method["returns"])
        self.assertIn("source_mode", method["returns"])
        self.assertTrue(methods["get_career_pb_detail"]["readonly"])
        self.assertTrue(methods["get_career_pb_history"]["readonly"])


if __name__ == "__main__":
    unittest.main()
