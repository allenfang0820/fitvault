import unittest

import career_backend


def snapshot(activity_count=1, fingerprint="sha256:" + "1" * 64):
    return {
        "source_fingerprint": fingerprint,
        "summary": {
            "activity_count": activity_count,
        },
    }


def report(fingerprint="sha256:" + "1" * 64, status="success"):
    return {
        "source_fingerprint": fingerprint,
        "status": status,
        "content": {"headline": "cached"},
    }


class TestCareerYearReportState(unittest.TestCase):
    def test_core_persistent_state_table(self):
        cases = [
            ("no_data", snapshot(activity_count=0), None, True, "no_data", False, False, False),
            ("not_generated", snapshot(), None, True, "not_generated", True, False, False),
            ("ready", snapshot(), report(), True, "ready", False, False, False),
            ("stale", snapshot(fingerprint="sha256:" + "2" * 64), report(), True, "stale", False, True, True),
        ]
        for name, snap, cached_report, ai_available, expected, can_generate, can_refresh, has_changes in cases:
            with self.subTest(name=name):
                state = career_backend.resolve_career_year_report_state(snap, cached_report, ai_available=ai_available)
                self.assertEqual(state["status"], expected)
                self.assertEqual(state["base_status"], expected)
                self.assertEqual(state["can_generate"], can_generate)
                self.assertEqual(state["can_refresh"], can_refresh)
                self.assertEqual(state["has_source_changes"], has_changes)

    def test_no_data_has_priority_over_report_runtime_and_ai_unavailable(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(activity_count=0),
            report(),
            runtime={"state": "generating"},
            ai_available=False,
        )

        self.assertEqual(state["status"], "no_data")
        self.assertFalse(state["can_generate"])
        self.assertFalse(state["can_refresh"])

    def test_generating_preserves_old_report_and_disables_actions(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(fingerprint="sha256:" + "2" * 64),
            report(),
            runtime={"state": "generating"},
        )

        self.assertEqual(state["status"], "generating")
        self.assertEqual(state["base_status"], "stale")
        self.assertTrue(state["display_report"])
        self.assertTrue(state["preserve_report"])
        self.assertFalse(state["can_generate"])
        self.assertFalse(state["can_refresh"])
        self.assertTrue(state["has_source_changes"])

    def test_failed_update_preserves_old_report(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(fingerprint="sha256:" + "2" * 64),
            report(),
            runtime={"state": "failed"},
        )

        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["base_status"], "stale")
        self.assertTrue(state["display_report"])
        self.assertTrue(state["preserve_report"])
        self.assertFalse(state["can_generate"])
        self.assertFalse(state["can_refresh"])

    def test_ai_unavailable_keeps_existing_report_visible(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(),
            report(),
            ai_available=False,
        )

        self.assertEqual(state["status"], "ai_unavailable")
        self.assertEqual(state["base_status"], "ready")
        self.assertTrue(state["display_report"])
        self.assertTrue(state["preserve_report"])
        self.assertFalse(state["can_generate"])
        self.assertFalse(state["can_refresh"])

    def test_ai_unavailable_without_report_does_not_allow_generate(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(),
            None,
            ai_available=False,
        )

        self.assertEqual(state["status"], "ai_unavailable")
        self.assertEqual(state["base_status"], "not_generated")
        self.assertFalse(state["display_report"])
        self.assertFalse(state["can_generate"])

    def test_ready_cannot_be_made_generatable_by_extra_runtime_flags(self):
        state = career_backend.resolve_career_year_report_state(
            snapshot(),
            report(),
            runtime={"state": "ready", "force": True, "refresh": True},
        )

        self.assertEqual(state["status"], "ready")
        self.assertFalse(state["can_generate"])
        self.assertFalse(state["can_refresh"])


class TestCareerYearReportStatePurity(unittest.TestCase):
    def test_resolver_does_not_depend_on_frontend_or_llm(self):
        import inspect

        source = inspect.getsource(career_backend.resolve_career_year_report_state)
        self.assertNotIn("window", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("call_llm", source)
        self.assertNotIn("llm_backend", source)


if __name__ == "__main__":
    unittest.main()
