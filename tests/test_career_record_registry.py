from dataclasses import replace
import unittest

import career_backend


class CareerRecordRegistryTest(unittest.TestCase):
    def test_v1_running_definitions_are_frozen(self):
        definitions = career_backend.iter_record_definitions(sport="running", source_mode="activity_total")

        self.assertEqual(
            [definition.key for definition in definitions],
            [
                "running_5k",
                "running_10k",
                "running_half_marathon",
                "running_marathon",
            ],
        )
        self.assertEqual([definition.standard_distance_m for definition in definitions], [5000.0, 10000.0, 21097.5, 42195.0])
        self.assertTrue(all(definition.metric == "elapsed_time_sec" for definition in definitions))
        self.assertTrue(all(definition.canonical_unit == "seconds" for definition in definitions))
        self.assertTrue(all(definition.comparison == "lower_is_better" for definition in definitions))
        self.assertTrue(all(definition.tolerance_ratio == 0.03 for definition in definitions))
        self.assertTrue(all(definition.family == "distance_time_pb" for definition in definitions))

    def test_registry_lookup_and_display_helpers_use_definitions(self):
        definition = career_backend.get_record_definition("running_10k")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.display_name, "10K")
        self.assertEqual(career_backend._pb_type_label("running_10k"), "10K")
        self.assertEqual(career_backend._pb_timeline_title("running_10k"), "10K PB")
        self.assertLess(
            career_backend.PB_OVERVIEW_TYPE_PRIORITY["running_10k"],
            career_backend.PB_OVERVIEW_TYPE_PRIORITY["running_half_marathon"],
        )

    def test_registry_validation_rejects_duplicate_keys(self):
        base = career_backend.RUNNING_RECORD_DEFINITIONS[0]

        with self.assertRaisesRegex(ValueError, "Duplicate record definition key"):
            career_backend.validate_record_registry((base, base))

    def test_registry_validation_rejects_invalid_unit_comparison_and_source_mode(self):
        base = career_backend.RUNNING_RECORD_DEFINITIONS[0]

        with self.assertRaisesRegex(ValueError, "Unsupported record unit"):
            career_backend.validate_record_registry((replace(base, canonical_unit="sec"),))
        with self.assertRaisesRegex(ValueError, "Unsupported record comparison"):
            career_backend.validate_record_registry((replace(base, comparison="faster_is_better"),))
        with self.assertRaisesRegex(ValueError, "Unsupported record source mode"):
            career_backend.validate_record_registry((replace(base, source_mode="best_effort_segment"),))
        with self.assertRaisesRegex(ValueError, "Unsupported record scope dimension"):
            career_backend.validate_record_registry((replace(base, scope_dimensions=("front_end_scope",)),))
        with self.assertRaisesRegex(ValueError, "Unsupported record availability"):
            career_backend.validate_record_registry((replace(base, availability_state="verified"),))

    def test_registry_validation_rejects_overlapping_ranges(self):
        base = career_backend.RUNNING_RECORD_DEFINITIONS[0]
        overlap = replace(base, key="running_5k_overlap", standard_distance_m=5100.0)

        with self.assertRaisesRegex(ValueError, "Overlapping record definition ranges"):
            career_backend.validate_record_registry((base, overlap))

    def test_match_record_definition_uses_inclusive_three_percent_boundary(self):
        cases = [
            (4850, "running_5k"),
            (5000, "running_5k"),
            (5150, "running_5k"),
            (9700, "running_10k"),
            (10300, "running_10k"),
            (21097.5, "running_half_marathon"),
            (42195, "running_marathon"),
        ]

        for distance_m, expected_key in cases:
            with self.subTest(distance_m=distance_m):
                match = career_backend.match_record_definition({
                    "sport": "running",
                    "source_mode": "activity_total",
                    "distance_m": distance_m,
                })
                self.assertIsNotNone(match)
                self.assertEqual(match["record_key"], expected_key)

    def test_v1_matcher_does_not_activate_v2_non_running_definitions(self):
        match = career_backend.match_record_definition({
            "sport": "open_water_swimming",
            "source_mode": "activity_total",
            "distance_m": 750,
        })

        self.assertIsNone(match)

    def test_match_record_definition_rejects_outside_boundary(self):
        for distance_m in (4849.99, 5150.01, 9699.99, 10300.01):
            with self.subTest(distance_m=distance_m):
                match = career_backend.match_record_definition({
                    "sport": "running",
                    "source_mode": "activity_total",
                    "distance_m": distance_m,
                })
                self.assertIsNone(match)

    def test_match_record_definition_raises_on_runtime_conflict(self):
        base = career_backend.RUNNING_RECORD_DEFINITIONS[0]
        overlap = replace(base, key="running_5k_overlap", standard_distance_m=5000.0)

        with self.assertRaisesRegex(ValueError, "Record definition conflict"):
            career_backend.match_record_definition(
                {"sport": "running", "source_mode": "activity_total", "distance_m": 5000},
                definitions=(base, overlap),
            )

    def test_compare_record_performance_handles_first_faster_tie_and_slower(self):
        self.assertEqual(
            career_backend.compare_record_performance(3278, None),
            {"is_valid": True, "is_new_record": True, "improvement_sec": None, "reason": "first_record"},
        )
        self.assertEqual(
            career_backend.compare_record_performance(3278, 3300),
            {"is_valid": True, "is_new_record": True, "improvement_sec": 22, "reason": "faster"},
        )
        self.assertEqual(
            career_backend.compare_record_performance(3278, 3278),
            {"is_valid": True, "is_new_record": False, "improvement_sec": 0, "reason": "tie"},
        )
        self.assertEqual(
            career_backend.compare_record_performance(3300, 3278),
            {"is_valid": True, "is_new_record": False, "improvement_sec": None, "reason": "slower"},
        )

    def test_compare_record_performance_rejects_non_positive_candidate(self):
        self.assertEqual(
            career_backend.compare_record_performance(0, 3278),
            {
                "is_valid": False,
                "is_new_record": False,
                "improvement_sec": None,
                "reason": "invalid_candidate_value",
            },
        )

    def test_record_confidence_auto_confirms_reliable_activity_total(self):
        summary = {
            "activity_id": "42",
            "sport": "running",
            "source_mode": "activity_total",
            "event_date": "2026-07-01",
            "distance_m": 10026,
            "elapsed_time_sec": 3278,
            "distance_quality": "reliable_distance",
            "time_quality": "reliable_elapsed",
            "reason_codes": ("distance_from_dist_km",),
        }
        match = career_backend.match_record_definition(summary)

        decision = career_backend.build_record_candidate_decision(summary, match)

        self.assertEqual(decision["decision"], "auto_confirm")
        self.assertEqual(decision["confidence_level"], "high")
        self.assertGreater(decision["confidence"], 0.90)
        self.assertEqual(decision["record_key"], "running_10k")
        self.assertEqual(decision["evidence_key"], "activity_total:42:running_10k:10026:3278")

    def test_record_confidence_downgrades_legacy_timer_semantics_to_candidate(self):
        summary = {
            "activity_id": "42",
            "sport": "running",
            "source_mode": "activity_total",
            "event_date": "2026-07-01",
            "distance_m": 10026,
            "elapsed_time_sec": 3278,
            "distance_quality": "reliable_distance",
            "time_quality": "semantics_unknown",
            "reason_codes": ("duration_from_total_timer_time", "duration_semantics_unknown"),
        }
        match = career_backend.match_record_definition(summary)

        decision = career_backend.build_record_candidate_decision(summary, match)

        self.assertEqual(decision["decision"], "candidate")
        self.assertEqual(decision["confidence_level"], "medium")
        self.assertGreaterEqual(decision["confidence"], 0.70)
        self.assertLessEqual(decision["confidence"], 0.90)
        self.assertIn("duration_semantics_unknown", decision["reason_codes"])

    def test_record_confidence_ignores_missing_distance_or_time(self):
        cases = [
            {
                "activity_id": "missing-distance",
                "sport": "running",
                "source_mode": "activity_total",
                "event_date": "2026-07-01",
                "distance_m": None,
                "elapsed_time_sec": 1500,
                "distance_quality": "missing_distance",
                "time_quality": "reliable_elapsed",
                "reason_codes": (),
                "expected_reason": "distance_missing",
            },
            {
                "activity_id": "missing-time",
                "sport": "running",
                "source_mode": "activity_total",
                "event_date": "2026-07-01",
                "distance_m": 5000,
                "elapsed_time_sec": None,
                "distance_quality": "reliable_distance",
                "time_quality": "missing_time",
                "reason_codes": (),
                "expected_reason": "elapsed_time_missing",
            },
        ]

        for summary in cases:
            with self.subTest(activity_id=summary["activity_id"]):
                decision = career_backend.build_record_candidate_decision(summary)

                self.assertEqual(decision["decision"], "ignored")
                self.assertEqual(decision["confidence_level"], "low")
                self.assertLess(decision["confidence"], 0.70)
                self.assertIn(summary["expected_reason"], decision["reason_codes"])

    def test_record_confidence_ignores_outside_standard_distance(self):
        summary = {
            "activity_id": "43",
            "sport": "running",
            "source_mode": "activity_total",
            "event_date": "2026-07-01",
            "distance_m": 8000,
            "elapsed_time_sec": 1800,
            "distance_quality": "reliable_distance",
            "time_quality": "reliable_elapsed",
            "reason_codes": (),
        }

        decision = career_backend.build_record_candidate_decision(summary)

        self.assertEqual(decision["decision"], "ignored")
        self.assertLess(decision["confidence"], 0.70)
        self.assertIsNone(decision["record_key"])
        self.assertIn("record_definition_not_matched", decision["reason_codes"])

    def test_record_evidence_key_is_stable_and_idempotent(self):
        summary = {
            "activity_id": "42",
            "sport": "running",
            "source_mode": "activity_total",
            "event_date": "2026-07-01",
            "distance_m": 10026,
            "elapsed_time_sec": 3278,
            "distance_quality": "reliable_distance",
            "time_quality": "semantics_unknown",
            "reason_codes": ("duration_semantics_unknown",),
        }
        match = career_backend.match_record_definition(summary)

        first = career_backend.build_record_candidate_decision(summary, match)
        second = career_backend.build_record_candidate_decision(dict(summary), match)

        self.assertEqual(first["evidence_key"], second["evidence_key"])
        self.assertEqual(first["confidence"], second["confidence"])
        self.assertEqual(first["reason_codes"], second["reason_codes"])

    def test_v2_registry_contains_multisport_catalog_definitions(self):
        definitions_by_key = {definition.key: definition for definition in career_backend.RECORD_DEFINITIONS}

        for key in [
            "cycling_fastest_40k",
            "cycling_power_10m",
            "cycling_power_20m",
            "cycling_power_30m",
            "cycling_power_2h",
            "cycling_longest_distance",
            "hiking_max_single_climb",
            "pool_swim_100m",
            "open_water_swim_1500m",
            "trail_max_single_climb",
        ]:
            self.assertIn(key, definitions_by_key)

        self.assertEqual(definitions_by_key["cycling_power_20m"].source_mode, "best_effort_duration")
        self.assertEqual(definitions_by_key["cycling_power_20m"].canonical_unit, "watts")
        self.assertEqual(definitions_by_key["cycling_fastest_40k"].source_mode, "best_effort_distance")
        self.assertEqual(definitions_by_key["cycling_fastest_40k"].comparison, "lower_is_better")
        self.assertEqual(definitions_by_key["cycling_fastest_40k"].availability_state, "validation_required")
        self.assertIn("distance_scope", definitions_by_key["cycling_fastest_40k"].scope_dimensions)
        self.assertEqual(definitions_by_key["cycling_power_10m"].standard_duration_sec, 600)
        self.assertEqual(definitions_by_key["cycling_power_30m"].standard_duration_sec, 1800)
        self.assertEqual(definitions_by_key["cycling_power_2h"].standard_duration_sec, 7200)
        self.assertEqual(definitions_by_key["pool_swim_100m"].availability_state, "validation_required")
        self.assertEqual(definitions_by_key["open_water_swim_1500m"].availability_state, "candidate_only")
        self.assertEqual(definitions_by_key["trail_max_single_climb"].source_mode, "activity_total")
        self.assertFalse(definitions_by_key["trail_max_single_climb"].dynamic_scope)
        self.assertIsNone(career_backend.get_record_definition("trail_route_best_time"))
        self.assertIsNone(career_backend.get_record_definition("trail_segment_best_time"))

    def test_v2_registry_excludes_model_and_analysis_as_active_record_definitions(self):
        families = {definition.family for definition in career_backend.RECORD_DEFINITIONS}

        self.assertNotIn("analysis_curve", families)
        self.assertNotIn("model_estimate", families)
        self.assertIsNone(career_backend.get_record_definition("estimated_ftp"))
        self.assertIsNone(career_backend.get_record_definition("trail_gap_curve"))
        self.assertIsNone(career_backend.get_record_definition("trail_pace_curve"))

    def test_v2_catalog_is_derived_from_registry(self):
        catalog = career_backend.get_career_record_catalog({"sport": "all", "include_unavailable": True})
        sports = {sport["sport"]: sport for sport in catalog["sports"]}

        self.assertIn("cycling", sports)
        self.assertIn("pool_swimming", sports)
        self.assertIn("trail_running", sports)

        cycling_records = [
            record
            for group in sports["cycling"]["groups"]
            for record in group["records"]
        ]
        record_by_key = {record["record_key"]: record for record in cycling_records}
        self.assertEqual(record_by_key["cycling_fastest_40k"]["axis_direction"], "lower")
        self.assertEqual(record_by_key["cycling_fastest_40k"]["source_mode"], "best_effort_distance")
        self.assertEqual(record_by_key["cycling_fastest_40k"]["availability_state"], "validation_required")
        self.assertEqual(record_by_key["cycling_power_20m"]["axis_direction"], "higher")
        self.assertEqual(record_by_key["cycling_power_20m"]["source_mode"], "best_effort_duration")
        self.assertEqual(record_by_key["cycling_power_20m"]["scope_dimensions"], ["sport_scope", "indoor_scope", "power_metric_scope"])

        pool_records = [
            record
            for group in sports["pool_swimming"]["groups"]
            for record in group["records"]
        ]
        self.assertTrue(all(record["availability_state"] == "validation_required" for record in pool_records))

        trail_records = [
            record
            for group in sports["trail_running"]["groups"]
            for record in group["records"]
        ]
        self.assertFalse(any(record["dynamic_scope"] for record in trail_records))
        self.assertTrue(all(record["availability_state"] == "candidate_only" for record in trail_records))


if __name__ == "__main__":
    unittest.main()
