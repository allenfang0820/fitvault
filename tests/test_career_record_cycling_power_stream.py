import json
from pathlib import Path
import unittest

import career_backend


FIXTURES = Path("tests/fixtures/records_center_v2/golden_manifest.json")


def fixture_case(case_id: str) -> dict:
    manifest = json.loads(FIXTURES.read_text())
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"missing fixture case: {case_id}")


def assert_safe_quality_summary(testcase: unittest.TestCase, summary: dict):
    text = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "clean_points",
        "normalized_points",
        "power_points",
        "raw_fit",
        "fit_records",
        "track_json",
        "file_path",
        "storage_ref",
        "device_serial",
        "serial_number",
        "weight_history",
        "/Users/",
        "file://",
    ):
        testcase.assertNotIn(forbidden, text)


class CareerRecordCyclingPowerStreamTest(unittest.TestCase):
    def test_clean_non_1hz_stream_keeps_zero_watts_and_time_weighting(self):
        case = fixture_case("cycling_power_clean_non_1hz")

        result = career_backend.normalize_cycling_power_stream_for_records(
            case["input"]["power_points"],
            activity=case["activity"],
        )
        repeated = career_backend.normalize_cycling_power_stream_for_records(
            case["input"]["power_points"],
            activity=case["activity"],
        )
        summary = career_backend.build_cycling_power_stream_quality_summary(result)

        self.assertEqual(result["quality"], "high")
        self.assertEqual(result["reason_codes"], [])
        self.assertEqual(summary["zero_power_count"], 1)
        self.assertEqual(summary["missing_power_count"], 0)
        self.assertEqual(summary["coverage_ratio"], 1.0)
        self.assertEqual(summary["time_weighted_avg_power_w"], 217.0)
        self.assertEqual(result["clean_points"][1]["power_w"], 0)
        self.assertEqual(
            json.dumps(result, ensure_ascii=False, sort_keys=True),
            json.dumps(repeated, ensure_ascii=False, sort_keys=True),
        )
        assert_safe_quality_summary(self, summary)

    def test_gap_missing_and_spike_become_candidate_quality(self):
        case = fixture_case("cycling_power_gap_missing_spike")

        result = career_backend.normalize_cycling_power_stream_for_records(
            case["input"]["power_points"],
            activity=case["activity"],
        )
        summary = career_backend.build_cycling_power_stream_quality_summary(result)

        self.assertEqual(result["quality"], "candidate")
        self.assertTrue(result["candidate_only"])
        self.assertEqual(summary["missing_power_count"], 1)
        self.assertEqual(summary["spike_times_sec"], [6.0])
        self.assertEqual(summary["gap_after_times_sec"], [7.0])
        self.assertNotIn(900, [point["power_w"] for point in result["clean_points"]])
        for code in ("missing_power_stream_sample", "power_spike_detected", "power_stream_gap"):
            self.assertIn(code, result["reason_codes"])
        assert_safe_quality_summary(self, summary)

    def test_ebike_is_hard_excluded_from_regular_cycling_power_records(self):
        case = fixture_case("cycling_power_ebike_excluded")

        result = career_backend.normalize_cycling_power_stream_for_records(
            case["input"]["power_points"],
            activity=case["activity"],
        )
        summary = career_backend.build_cycling_power_stream_quality_summary(result)

        self.assertFalse(result["ok"])
        self.assertEqual(result["quality"], "ignored")
        self.assertEqual(result["reason_codes"], ["ebike_scope_excluded"])
        self.assertEqual(result["scope"]["sport_scope"], "ebike_excluded")
        self.assertEqual(summary["valid_points_count"], 0)
        assert_safe_quality_summary(self, summary)

    def test_timestamp_and_power_aliases_are_supported(self):
        points = [
            {"timestamp": "2026-07-14T00:00:00Z", "watts": 100},
            {"timestamp": "2026-07-14T00:00:02Z", "Power": 120},
            {"timestamp": "2026-07-14T00:00:04Z", "enhanced_power": 140},
        ]

        result = career_backend.normalize_cycling_power_stream_for_records(
            points,
            activity={"sport_type": "road_cycling", "indoor_scope": "outdoor", "duration_sec": 4},
        )

        self.assertEqual(result["quality"], "high")
        self.assertEqual([point["t_sec"] for point in result["clean_points"]], [0.0, 2.0, 4.0])
        self.assertEqual(result["scope"]["indoor_scope"], "outdoor")


if __name__ == "__main__":
    unittest.main()
