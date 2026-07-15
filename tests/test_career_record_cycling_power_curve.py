import json
import sqlite3
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


def anchor_by_duration(curve: dict, duration_sec: int) -> dict:
    for anchor in curve["anchors"]:
        if anchor["duration_sec"] == duration_sec:
            return anchor
    raise AssertionError(f"missing anchor: {duration_sec}")


class CareerRecordCyclingPowerCurveTest(unittest.TestCase):
    def test_clean_non_1hz_curve_computes_time_weighted_anchors(self):
        case = fixture_case("cycling_power_clean_non_1hz")

        result = career_backend.resolve_cycling_power_duration_curve(
            case["input"]["power_points"],
            activity=case["activity"],
            windows_sec=(5, 30),
            use_cache=False,
        )

        five = anchor_by_duration(result["curve"], 5)
        thirty = anchor_by_duration(result["curve"], 30)
        self.assertEqual(five["value"], 280)
        self.assertEqual(five["range"], {"start_sec": 14.0, "end_sec": 19.0})
        self.assertEqual(five["quality"]["state"], "ready")
        self.assertIsNone(thirty["value"])
        self.assertIn("activity_shorter_than_window", thirty["quality"]["reason_codes"])
        self.assertEqual(result["cache"]["hit"], False)

    def test_gap_missing_spike_curve_does_not_bridge_pause(self):
        case = fixture_case("cycling_power_gap_missing_spike")

        result = career_backend.resolve_cycling_power_duration_curve(
            case["input"]["power_points"],
            activity=case["activity"],
            windows_sec=(5, 20),
            use_cache=False,
        )

        five = anchor_by_duration(result["curve"], 5)
        twenty = anchor_by_duration(result["curve"], 20)
        self.assertEqual(five["quality"]["state"], "candidate")
        self.assertFalse(five["range"]["start_sec"] < 20 < five["range"]["end_sec"])
        self.assertIsNone(twenty["value"])
        self.assertIn("power_stream_gap", result["quality"]["reason_codes"])
        self.assertNotIn("clean_points", json.dumps(result["curve"], ensure_ascii=False))

    def test_curve_cache_miss_then_hit_without_raw_stream(self):
        case = fixture_case("cycling_power_clean_non_1hz")
        conn = sqlite3.connect(":memory:")
        try:
            first = career_backend.resolve_cycling_power_duration_curve(
                case["input"]["power_points"],
                activity=case["activity"],
                windows_sec=(5, 30),
                conn=conn,
            )
            second = career_backend.resolve_cycling_power_duration_curve(
                case["input"]["power_points"],
                activity=case["activity"],
                windows_sec=(5, 30),
                conn=conn,
            )
            cached = career_backend.get_career_record_curve_cache(
                activity_id=case["activity"]["activity_id"],
                curve_type="cycling_power_duration_curve",
                source_mode="best_effort_duration",
                scope=first["curve"]["scope"],
                input_fingerprint=first["cache"]["input_fingerprint"],
                algorithm_version=career_backend.CYCLING_POWER_DURATION_CURVE_ALGORITHM_VERSION,
                conn=conn,
            )

            self.assertFalse(first["cache"]["hit"])
            self.assertTrue(second["cache"]["hit"])
            self.assertIsNotNone(cached)
            text = json.dumps(cached, ensure_ascii=False, sort_keys=True)
            for forbidden in ("clean_points", "power_points", "power_stream", "raw_fit", "track_json", "/Users/"):
                self.assertNotIn(forbidden, text)
        finally:
            conn.close()

    def test_tie_prefers_earlier_range(self):
        points = [
            {"t": 0, "power_w": 100},
            {"t": 5, "power_w": 100},
            {"t": 10, "power_w": 100},
        ]

        result = career_backend.resolve_cycling_power_duration_curve(
            points,
            activity={"activity_id": "fixture:cycling:tie", "sport_type": "cycling", "duration_sec": 10},
            windows_sec=(5,),
            use_cache=False,
        )

        five = anchor_by_duration(result["curve"], 5)
        self.assertEqual(five["value"], 100)
        self.assertEqual(five["range"], {"start_sec": 0.0, "end_sec": 5.0})


if __name__ == "__main__":
    unittest.main()
