"""MDT-00: freeze the multi-sport activity-detail contract before implementation."""
from __future__ import annotations

import json
import os
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_PATH = os.path.join(PROJECT_ROOT, "docs", "js_api_contract.json")


class TestActivityDetailMultiSportContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CONTRACT_PATH, encoding="utf-8") as f:
            cls.contract = json.load(f)["activity_detail_multi_sport_contract"]

    def test_frozen_enums_are_complete_and_unique(self):
        self.assertEqual(
            set(self.contract["detail_surface_mode_enum"]),
            {
                "endurance_outdoor",
                "endurance_indoor",
                "swim_pool",
                "swim_open_water",
                "strength",
                "mobility_recovery",
                "skill_session",
                "generic_session",
                "not_supported",
            },
        )
        self.assertEqual(
            set(self.contract["review_profile_enum"]),
            {
                "endurance_outdoor",
                "endurance_indoor",
                "swim",
                "strength_limited",
                "recovery_limited",
                "generic_limited",
                "not_applicable",
            },
        )
        self.assertEqual(
            set(self.contract["not_applicable_reason_enum"]),
            {
                "structured_strength_data_missing",
                "recovery_activity_limited",
                "generic_activity_limited",
                "unsupported_activity_type",
            },
        )

    def test_overview_capabilities_are_minimal_fact_flags(self):
        self.assertEqual(
            set(self.contract["overview_capabilities_minimum_fields"]),
            {
                "has_track_visual",
                "has_laps",
                "has_structured_sets",
                "has_swim_lengths",
                "has_power",
                "has_cadence",
                "has_hr",
                "has_weather",
            },
        )

    def test_required_samples_have_explicit_detail_and_review_routes(self):
        expected = {
            "running": ("endurance_outdoor", "endurance_outdoor"),
            "trail_running": ("endurance_outdoor", "endurance_outdoor"),
            "treadmill_running": ("endurance_indoor", "endurance_indoor"),
            "cycling": ("endurance_outdoor", "endurance_outdoor"),
            "indoor_cycling": ("endurance_indoor", "endurance_indoor"),
            "lap_swimming": ("swim_pool", "swim"),
            "open_water": ("swim_open_water", "swim"),
            "strength_training": ("strength", "strength_limited"),
            "yoga": ("mobility_recovery", "recovery_limited"),
            "breathing": ("mobility_recovery", "recovery_limited"),
            "cardio": ("generic_session", "generic_limited"),
            "unknown": ("not_supported", "not_applicable"),
        }
        routes = self.contract["sample_routes"]
        for sport, (surface_mode, review_profile) in expected.items():
            with self.subTest(sport=sport):
                self.assertEqual(routes[sport]["detail_surface_mode"], surface_mode)
                self.assertEqual(routes[sport]["review_profile"], review_profile)

    def test_limited_and_unsupported_routes_expose_reason_codes(self):
        routes = self.contract["sample_routes"]
        self.assertEqual(
            routes["strength_training"]["not_applicable_reason"],
            "structured_strength_data_missing",
        )
        self.assertEqual(routes["unknown"]["not_applicable_reason"], "unsupported_activity_type")
        self.assertNotEqual(routes["unknown"]["review_profile"], "endurance_outdoor")

    def test_strength_boundary_forbids_unparsed_structured_claims(self):
        boundary = self.contract["strength_boundary"]
        for forbidden_claim in ("exercise names", "muscle groups", "set counts", "weights", "volume"):
            with self.subTest(forbidden_claim=forbidden_claim):
                self.assertIn(forbidden_claim, boundary)

    def test_registry_implements_all_frozen_routes(self):
        from metrics_registry import get_detail_surface_mode, get_review_profile

        for sport, route in self.contract["sample_routes"].items():
            with self.subTest(sport=sport):
                self.assertEqual(
                    get_detail_surface_mode(sport),
                    route["detail_surface_mode"],
                )
                self.assertEqual(
                    get_review_profile(sport),
                    route["review_profile"],
                )

    def test_detail_capability_defaults_never_fabricate_record_facts(self):
        from metrics_registry import get_detail_capabilities

        expected_fields = set(self.contract["overview_capabilities_minimum_fields"])
        for sport in self.contract["sample_routes"]:
            with self.subTest(sport=sport):
                capabilities = get_detail_capabilities(sport)
                self.assertEqual(set(capabilities), expected_fields)
                self.assertTrue(all(value is False for value in capabilities.values()))

    def test_registry_returns_limited_reason_codes(self):
        from metrics_registry import get_not_applicable_reason

        for sport, route in self.contract["sample_routes"].items():
            with self.subTest(sport=sport):
                self.assertEqual(
                    get_not_applicable_reason(sport),
                    route.get("not_applicable_reason"),
                )

    def test_explicit_surface_override_uses_the_same_profile_contract(self):
        from metrics_registry import get_review_profile

        self.assertEqual(
            get_review_profile("unknown", {"detail_surface_mode": "endurance_indoor"}),
            "endurance_indoor",
        )

    def test_overview_view_model_uses_record_facts_and_surface_mode(self):
        from main import _build_multi_sport_overview_view_model

        def build(sport_type, **row_values):
            row = {"sport_type": sport_type, **row_values}
            return _build_multi_sport_overview_view_model(
                row,
                points=row_values.pop("points", []),
                laps=row_values.pop("laps", []),
                distance_km=row_values.pop("distance_km", 0.0),
                duration_sec=row_values.pop("duration_sec", 0),
                avg_hr=row_values.pop("avg_hr", None),
                pace_sec=row_values.pop("pace_sec", None),
                calories=row_values.pop("calories", 0),
                water_metric_value=row_values.pop("water_metric_value", None),
            )

        indoor = build(
            "indoor_cycling",
            duration_sec=3600,
            avg_hr=145,
            calories=620,
            avg_power=180,
            avg_cadence=85,
        )
        self.assertEqual(indoor["detail_surface_mode"], "endurance_indoor")
        self.assertEqual(indoor["primary_visual"], "indoor_summary")
        self.assertEqual(indoor["overview_empty_states"]["primary_visual"], "indoor_no_track")
        self.assertTrue(indoor["overview_capabilities"]["has_power"])
        self.assertTrue(indoor["overview_capabilities"]["has_cadence"])
        self.assertFalse(indoor["overview_capabilities"]["has_track_visual"])

        swim = build(
            "lap_swimming",
            laps=[{"distance_km": 0.1}],
            distance_km=1.5,
            duration_sec=2100,
            pace_sec=95,
            water_metric_value=38.0,
        )
        self.assertEqual(swim["detail_surface_mode"], "swim_pool")
        self.assertEqual(swim["primary_visual"], "swim_summary")
        self.assertEqual(swim["split_section"], "swim_lengths")
        self.assertTrue(swim["overview_capabilities"]["has_swim_lengths"])

        open_water = build(
            "swimming",
            sub_sport_type="open_water",
            points=[{"lat": 1.0, "lon": 2.0}],
            distance_km=1.5,
            duration_sec=2100,
        )
        self.assertEqual(open_water["detail_surface_mode"], "swim_open_water")
        self.assertTrue(open_water["overview_capabilities"]["has_track_visual"])
        self.assertEqual(open_water["primary_visual"], "track_map")

        strength = build("strength_training", duration_sec=1800, avg_hr=120, calories=260)
        self.assertEqual(strength["primary_visual"], "strength_limited")
        self.assertEqual(strength["split_section"], "strength_unavailable")
        self.assertFalse(strength["overview_capabilities"]["has_structured_sets"])
        self.assertNotIn(
            "distance_km",
            {item["field"] for item in strength["overview_metrics"]},
        )

        outdoor = build(
            "running",
            points=[{"lat": 1.0, "lon": 2.0}],
            laps=[{"distance_km": 1.0}],
            distance_km=8.0,
            duration_sec=2400,
            pace_sec=300,
            avg_hr=150,
        )
        self.assertEqual(outdoor["primary_visual"], "track_map")
        self.assertEqual(outdoor["split_section"], "laps")
        self.assertTrue(outdoor["overview_capabilities"]["has_track_visual"])

    def test_detail_summary_keeps_power_and_cadence_as_backend_facts(self):
        from main import _build_activity_detail_summary_from_row

        record = _build_activity_detail_summary_from_row({
            "id": 101,
            "sport_type": "indoor_cycling",
            "duration_sec": 3600,
            "avg_hr": 145,
            "avg_power": 180,
            "avg_cadence": 85,
            "calories": 620,
        })
        summary = record["detail"]["summary"]
        self.assertEqual(summary["avg_power"], 180.0)
        self.assertEqual(summary["avg_cadence"], 85.0)
        self.assertEqual(record["detail"]["primary_visual"], "indoor_summary")


if __name__ == "__main__":
    unittest.main()
