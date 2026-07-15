import unittest

import career_backend


class CareerRecordEvidenceTest(unittest.TestCase):
    def _build(self, **overrides):
        payload = {
            "record_key": "cycling_power_5s",
            "activity_id": "activity-42",
            "sport": "cycling",
            "source_mode": "best_effort_duration",
            "metric_name": "power_w",
            "metric_value": 612.4,
            "metric_unit": "watts",
            "event_date": "2026-07-14",
            "scope": {"sport_scope": "outdoor", "indoor_scope": "", "ignored": "x"},
            "range_data": {"start_sec": 10, "end_sec": 15, "duration_sec": 5},
            "quality": {"confidence": 0.97, "reason_codes": ["range_attached", "range_attached"]},
            "resolver_version": "cycling-power:v1",
        }
        payload.update(overrides)
        return career_backend.build_record_evidence(**payload).to_dict()

    def test_evidence_key_is_stable_for_same_fact_and_order_independent(self):
        first = self._build()
        second = self._build(
            scope={"ignored": "y", "sport_scope": "outdoor"},
            range_data={"duration_sec": 5, "end_sec": 15, "start_sec": 10},
            quality={"reason_codes": ["range_attached"], "confidence": 0.97001},
        )

        self.assertEqual(first["evidence_key"], second["evidence_key"])
        self.assertEqual(first["scope_json"], {"sport_scope": "outdoor"})
        self.assertEqual(first["scope_key"], "outdoor")
        self.assertRegex(first["evidence_key"], r"^evidence:v2:cycling_power_5s:activity-42:best_effort_duration:")
        self.assertRegex(first["evidence_fingerprint"], r"^evidence:sha256:[0-9a-f]{64}$")
        self.assertEqual(first["quality"]["reason_codes"], ["range_attached"])

    def test_evidence_key_changes_when_metric_range_or_scope_changes(self):
        baseline = self._build()
        changed_metric = self._build(metric_value=615)
        changed_range = self._build(range_data={"start_sec": 11, "end_sec": 16, "duration_sec": 5})
        changed_scope = self._build(scope={"sport_scope": "indoor", "indoor_scope": "trainer"})

        self.assertNotEqual(baseline["evidence_key"], changed_metric["evidence_key"])
        self.assertNotEqual(baseline["evidence_key"], changed_range["evidence_key"])
        self.assertNotEqual(baseline["evidence_key"], changed_scope["evidence_key"])

    def test_current_records_center_source_modes_can_build_safe_evidence(self):
        cases = [
            {
                "record_key": "cycling_longest_distance",
                "sport": "cycling",
                "source_mode": "activity_total",
                "metric_name": "distance_m",
                "metric_value": 102000,
                "metric_unit": "meters",
                "scope": {"sport_scope": "outdoor"},
                "range_data": {},
            },
            {
                "record_key": "cycling_power_20m",
                "sport": "cycling",
                "source_mode": "best_effort_duration",
                "metric_name": "power_w",
                "metric_value": 270,
                "metric_unit": "watts",
                "scope": {"sport_scope": "outdoor"},
                "range_data": {"start_sec": 100, "end_sec": 1300, "duration_sec": 1200},
            },
            {
                "record_key": "pool_swim_100m",
                "sport": "pool_swimming",
                "source_mode": "best_effort_distance",
                "metric_name": "elapsed_time_sec",
                "metric_value": 92,
                "metric_unit": "seconds",
                "scope": {"water_scope": "pool", "pool_length_scope": "25m", "stroke_scope": "freestyle"},
                "range_data": {"lap_start": 1, "lap_end": 4, "distance_m": 100},
            },
        ]

        for index, case in enumerate(cases):
            with self.subTest(source_mode=case["source_mode"]):
                evidence = career_backend.build_record_evidence(
                    activity_id=f"activity-{index}",
                    event_date="2026-07-14",
                    quality={"confidence": 0.91, "reason_codes": ["range_attached"]},
                    resolver_version="records-v2-test",
                    **case,
                ).to_dict()
                self.assertEqual(evidence["source_mode"], case["source_mode"])
                self.assertTrue(evidence["evidence_key"].startswith(f"evidence:v2:{case['record_key']}:activity-{index}:"))

    def test_source_mode_and_required_scope_or_range_are_validated(self):
        with self.assertRaisesRegex(ValueError, "unknown record_key"):
            self._build(record_key="free_form_record")

        with self.assertRaisesRegex(ValueError, "unsupported source_mode"):
            self._build(source_mode="model_estimate")

        with self.assertRaisesRegex(ValueError, "sport mismatch"):
            self._build(sport="running")

        with self.assertRaisesRegex(ValueError, "metric_name mismatch"):
            self._build(metric_name="w_per_kg")

        with self.assertRaisesRegex(ValueError, "requires an activity range"):
            self._build(range_data={})

        with self.assertRaisesRegex(ValueError, "unknown record_key"):
            career_backend.build_record_evidence(
                record_key="trail_route_best_time",
                activity_id="activity-route",
                sport="trail_running",
                source_mode="activity_total",
                metric_name="elapsed_time_sec",
                metric_value=3600,
                metric_unit="seconds",
                scope={"sport_scope": "trail"},
            )

        with self.assertRaisesRegex(ValueError, "unknown record_key"):
            career_backend.build_record_evidence(
                record_key="trail_segment_best_time",
                activity_id="activity-segment",
                sport="trail_running",
                source_mode="best_effort_duration",
                metric_name="elapsed_time_sec",
                metric_value=600,
                metric_unit="seconds",
                scope={"sport_scope": "trail"},
                range_data={"start_sec": 10, "end_sec": 610},
            )

    def test_sensitive_or_raw_evidence_payload_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "power_stream"):
            self._build(range_data={"start_sec": 1, "end_sec": 6, "power_stream": [1, 2, 3]})

        with self.assertRaisesRegex(ValueError, "device_serial"):
            self._build(quality={"confidence": 0.9, "device_serial": "ABC123"})

        with self.assertRaisesRegex(ValueError, "local path"):
            self._build(quality={"source": "/Users/fanglei/private.fit"})

    def test_legacy_record_evidence_key_is_unchanged(self):
        summary = {
            "activity_id": "1",
            "distance_m": 5000,
            "elapsed_time_sec": 1500,
            "source_mode": "activity_total",
        }
        match = {"record_key": "running_5k", "source_mode": "activity_total"}

        self.assertEqual(
            career_backend.record_evidence_key(summary, match),
            "activity_total:1:running_5k:5000:1500",
        )


if __name__ == "__main__":
    unittest.main()
