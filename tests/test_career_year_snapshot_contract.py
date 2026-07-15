import copy
import sqlite3
import unittest

import career_backend


FORBIDDEN_YEAR_SNAPSHOT_KEYS = {
    "raw_fit",
    "points",
    "points_json",
    "track_json",
    "file_path",
    "storage_ref",
    "thumbnail_url",
    "preview_url",
    "representative_memories",
    "memory_count",
    "token",
    "provider",
    "sql",
}


def _assert_forbidden_absent(testcase, value):
    if isinstance(value, dict):
        for key, child in value.items():
            testcase.assertNotIn(str(key).lower(), FORBIDDEN_YEAR_SNAPSHOT_KEYS)
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_absent(testcase, child)
    elif isinstance(value, str):
        testcase.assertNotIn("/Users/", value)
        testcase.assertNotIn("\\Users\\", value)
        testcase.assertNotIn("file://", value)


def rich_year_snapshot_fixture():
    return {
        "snapshot_version": "acs.year.v2",
        "scope": "year",
        "year": 2026,
        "period": {
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "as_of_date": "2026-07-13",
            "data_through": "2026-07-11",
            "is_partial_year": True,
            "latest_activity_date": "2026-07-11",
        },
        "summary": {
            "activity_count": 128,
            "total_distance_km": 1840.5,
            "total_duration_seconds": 482000,
            "race_count": 3,
            "pb_count": 2,
            "achievement_count": 5,
            "covered_city_count": 8,
        },
        "sport_breakdown": [
            {
                "sport": "cycling",
                "sport_label": "骑行",
                "activity_count": 46,
                "distance_km": 920.1,
                "duration_seconds": 196000,
            },
            {
                "sport": "running",
                "sport_label": "跑步",
                "activity_count": 82,
                "distance_km": 920.4,
                "duration_seconds": 286000,
            },
        ],
        "month_digest": [
            {
                "month": month,
                "activity_count": 18 if month == 1 else 0,
                "distance_km": 210.2 if month == 1 else 0.0,
                "duration_seconds": 52000 if month == 1 else 0,
                "primary_sport": "running" if month == 1 else "",
            }
            for month in range(1, 13)
        ],
        "evidence_catalog": [
            {
                "evidence_id": "race:123",
                "activity_id": "123",
                "type": "race",
                "title": "上海半程马拉松",
                "date": "2026-04-19",
                "value": "01:28:20",
            },
            {
                "evidence_id": "pb:456",
                "activity_id": "456",
                "type": "pb",
                "title": "5K PB",
                "date": "2026-06-01",
                "value": "00:19:20",
            },
        ],
        "highlight_moments": [
            {
                "id": "race:123",
                "activity_id": "123",
                "type": "race",
                "title": "上海半程马拉松",
                "date": "2026-04-19",
                "value": "01:28:20",
                "rank": 10,
            }
        ],
        "city_moments": [
            {
                "city": "成都",
                "activity_count": 3,
                "first_date": "2026-03-01",
                "latest_date": "2026-05-01",
                "representative_activity_id": "123",
                "culture_hint": "火锅",
            }
        ],
        "comparison": {
            "status": "available",
            "reason": "",
            "comparison_year": 2025,
            "period_mode": "same_date_range",
            "activity_count_delta": 12,
            "distance_km_delta": 136.4,
            "duration_seconds_delta": 24800,
            "race_count_delta": 1,
            "pb_count_delta": 1,
        },
        "data_quality": {
            "status": "ready",
            "warnings": [],
        },
        "source_fingerprint": "sha256:sample",
    }


def light_year_snapshot_fixture():
    snapshot = rich_year_snapshot_fixture()
    snapshot["summary"] = {
        "activity_count": 1,
        "total_distance_km": 5.0,
        "total_duration_seconds": 1800,
        "race_count": 0,
        "pb_count": 0,
        "achievement_count": 0,
        "covered_city_count": 1,
    }
    snapshot["sport_breakdown"] = [
        {
            "sport": "running",
            "sport_label": "跑步",
            "activity_count": 1,
            "distance_km": 5.0,
            "duration_seconds": 1800,
        }
    ]
    snapshot["month_digest"] = [
        {
            "month": month,
            "activity_count": 1 if month == 3 else 0,
            "distance_km": 5.0 if month == 3 else 0.0,
            "duration_seconds": 1800 if month == 3 else 0,
            "primary_sport": "running" if month == 3 else "",
        }
        for month in range(1, 13)
    ]
    snapshot["evidence_catalog"] = []
    snapshot["comparison"] = {
        "status": "unavailable",
        "reason": "insufficient_previous_year",
        "comparison_year": 2025,
        "period_mode": "insufficient_previous_year",
        "activity_count_delta": None,
        "distance_km_delta": None,
        "duration_seconds_delta": None,
        "race_count_delta": None,
        "pb_count_delta": None,
    }
    snapshot["data_quality"] = {"status": "limited", "warnings": ["light_activity_year"]}
    snapshot["source_fingerprint"] = "sha256:light"
    return snapshot


def current_partial_year_snapshot_fixture():
    snapshot = rich_year_snapshot_fixture()
    snapshot["period"]["is_partial_year"] = True
    snapshot["period"]["as_of_date"] = "2026-07-14"
    snapshot["period"]["data_through"] = "2026-07-11"
    return snapshot


class TestCareerYearSnapshotContract(unittest.TestCase):
    def test_empty_year_snapshot_has_frozen_shape_and_no_data_semantics(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        snapshot = career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date="2026-07-13")

        self.assertEqual(tuple(snapshot), career_backend.CAREER_YEAR_SNAPSHOT_TOP_LEVEL_FIELDS)
        self.assertEqual(snapshot["snapshot_version"], "acs.year.v2")
        self.assertEqual(snapshot["scope"], "year")
        self.assertEqual(snapshot["year"], 2026)
        self.assertEqual(snapshot["period"]["start_date"], "2026-01-01")
        self.assertEqual(snapshot["period"]["end_date"], "2026-12-31")
        self.assertIsNone(snapshot["period"]["data_through"])
        self.assertEqual(snapshot["summary"]["activity_count"], 0)
        self.assertEqual(len(snapshot["month_digest"]), 12)
        self.assertEqual(snapshot["highlight_moments"], [])
        self.assertEqual(snapshot["city_moments"], [])
        self.assertEqual([item["month"] for item in snapshot["month_digest"]], list(range(1, 13)))
        self.assertEqual(snapshot["data_quality"]["status"], "no_data")
        self.assertRegex(snapshot["source_fingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(snapshot["source_fingerprint"], career_backend.compute_career_year_source_fingerprint(snapshot))
        self.assertTrue(career_backend.validate_career_year_snapshot_contract(snapshot))
        _assert_forbidden_absent(self, snapshot)

    def test_schema_expresses_manual_rich_light_and_current_year_fixtures(self):
        for snapshot in (
            rich_year_snapshot_fixture(),
            light_year_snapshot_fixture(),
            current_partial_year_snapshot_fixture(),
        ):
            self.assertTrue(career_backend.validate_career_year_snapshot_contract(snapshot))
            _assert_forbidden_absent(self, snapshot)

    def test_activity_and_resolver_whitelists_are_explicit(self):
        self.assertEqual(
            career_backend.CAREER_YEAR_SNAPSHOT_ACTIVITY_FIELDS,
            ("activity_id", "date", "sport", "sport_label", "distance_km", "duration_seconds", "city"),
        )
        self.assertEqual(
            career_backend.CAREER_YEAR_SNAPSHOT_RESOLVER_FIELDS,
            ("evidence_id", "activity_id", "type", "title", "date", "value"),
        )
        self.assertIn("representative_memories", career_backend.CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS)
        self.assertIn("memory_count", career_backend.CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS)
        self.assertIn("token", career_backend.CAREER_YEAR_SNAPSHOT_FORBIDDEN_KEYS)

    def test_recursive_forbidden_key_guard_checks_nested_keys_and_paths(self):
        snapshot = rich_year_snapshot_fixture()
        dirty = copy.deepcopy(snapshot)
        dirty["evidence_catalog"][0]["metadata"] = {"points_json": "[hidden]"}
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_snapshot_contract(dirty)

        dirty = copy.deepcopy(snapshot)
        dirty["data_quality"]["warnings"] = ["file:///Users/example/private.fit"]
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_snapshot_contract(dirty)

    def test_legal_year_range_is_enforced(self):
        for bad_year in (1899, 2101, "not-a-year"):
            with self.assertRaises(ValueError):
                career_backend.build_career_year_snapshot(bad_year)

    def test_stable_sorting_contract_is_validated(self):
        snapshot = rich_year_snapshot_fixture()
        snapshot["sport_breakdown"] = list(reversed(snapshot["sport_breakdown"]))
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_snapshot_contract(snapshot)

        snapshot = rich_year_snapshot_fixture()
        snapshot["month_digest"] = list(reversed(snapshot["month_digest"]))
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_snapshot_contract(snapshot)

        snapshot = rich_year_snapshot_fixture()
        snapshot["evidence_catalog"] = list(reversed(snapshot["evidence_catalog"]))
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_snapshot_contract(snapshot)


class TestCareerYearSnapshotNonGoals(unittest.TestCase):
    def test_year_snapshot_contract_does_not_persist_or_call_llm(self):
        import inspect

        source = inspect.getsource(career_backend.build_career_year_snapshot)
        self.assertNotIn("INSERT INTO", source)
        self.assertNotIn("career_snapshots", source)
        self.assertNotIn("career_ai_insights", source)
        self.assertNotIn("call_llm", source)
        self.assertNotIn("llm_backend", source)


if __name__ == "__main__":
    unittest.main()
