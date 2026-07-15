import copy
import sqlite3
import sys
import unittest
from pathlib import Path

import career_backend

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_career_year_snapshot_evidence import (
    _create_tables,
    _insert_activity,
    _insert_pb,
    _insert_race,
)


class TestCareerYearSnapshotFingerprint(unittest.TestCase):
    def _snapshot(self, as_of_date: str = "2026-07-14") -> dict:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        _create_tables(conn)
        _insert_activity(conn, id=1, start_time="2026-07-11T07:00:00+08:00", dist_km=10.0, duration=3600)
        _insert_activity(conn, id=2, start_time="2025-07-11T07:00:00+08:00", dist_km=6.0, duration=2000)
        _insert_race(conn, id="race:2026", activity_id="1", event_date="2026-07-11")
        _insert_pb(conn, id="pb:2026", activity_id="1", event_date="2026-07-11")
        return career_backend.build_career_year_snapshot(2026, conn=conn, as_of_date=as_of_date)

    def test_fingerprint_format_and_canonical_json_are_stable(self):
        snapshot = self._snapshot()
        fingerprint = snapshot["source_fingerprint"]

        self.assertRegex(fingerprint, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(fingerprint, career_backend.compute_career_year_source_fingerprint(snapshot))
        canonical = career_backend.career_year_snapshot_canonical_json(
            career_backend.career_year_snapshot_report_source_fields(snapshot)
        )
        self.assertEqual(canonical, career_backend.career_year_snapshot_canonical_json(
            career_backend.career_year_snapshot_report_source_fields(copy.deepcopy(snapshot))
        ))

    def test_as_of_date_and_runtime_fields_do_not_change_fingerprint(self):
        first = self._snapshot(as_of_date="2026-07-14")
        second = self._snapshot(as_of_date="2026-07-20")
        dirty = copy.deepcopy(first)
        dirty["period"]["as_of_date"] = "2026-12-31"
        dirty["source_fingerprint"] = "sha256:" + "0" * 64
        dirty["generated_at"] = "2026-07-14T00:00:00Z"
        dirty["traceId"] = "trace-123"
        dirty["prompt_version"] = "prompt-v2"
        dirty["model_id"] = "model-x"

        self.assertEqual(first["source_fingerprint"], second["source_fingerprint"])
        self.assertEqual(first["source_fingerprint"], career_backend.compute_career_year_source_fingerprint(dirty))

    def test_allowed_activity_fact_change_changes_fingerprint(self):
        snapshot = self._snapshot()
        changed = copy.deepcopy(snapshot)
        changed["summary"]["total_distance_km"] += 1.0

        self.assertNotEqual(
            snapshot["source_fingerprint"],
            career_backend.compute_career_year_source_fingerprint(changed),
        )

    def test_resolver_evidence_change_changes_fingerprint(self):
        snapshot = self._snapshot()
        changed = copy.deepcopy(snapshot)
        changed["evidence_catalog"].append({
            "evidence_id": "achievement:1",
            "activity_id": "1",
            "type": "achievement",
            "title": "首次跑完 5K",
            "date": "2026-07-12",
            "value": "70",
        })

        self.assertNotEqual(
            snapshot["source_fingerprint"],
            career_backend.compute_career_year_source_fingerprint(changed),
        )

    def test_photo_ui_and_model_fields_do_not_change_fingerprint(self):
        snapshot = self._snapshot()
        changed = copy.deepcopy(snapshot)
        changed["ui_state"] = {"theme": "dark"}
        changed["model_version"] = "new-model"
        changed["prompt_version"] = "new-prompt"
        changed["data_quality"]["message"] = "展示文案变化"

        self.assertEqual(
            snapshot["source_fingerprint"],
            career_backend.compute_career_year_source_fingerprint(changed),
        )

    def test_ordering_and_equivalent_float_representation_are_stable(self):
        snapshot = self._snapshot()
        reordered = copy.deepcopy(snapshot)
        reordered["sport_breakdown"] = list(reversed(reordered["sport_breakdown"]))
        reordered["month_digest"] = list(reversed(reordered["month_digest"]))
        reordered["evidence_catalog"] = list(reversed(reordered["evidence_catalog"]))
        reordered["summary"] = dict(reversed(list(reordered["summary"].items())))
        reordered["summary"]["total_distance_km"] = float(reordered["summary"]["total_distance_km"])

        self.assertEqual(
            snapshot["source_fingerprint"],
            career_backend.compute_career_year_source_fingerprint(reordered),
        )


if __name__ == "__main__":
    unittest.main()
