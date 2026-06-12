"""活动建议 P3 cleanup 静态契约测试。"""
from __future__ import annotations

import os
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


class TestLegacyRiskAssessmentCleanup(unittest.TestCase):
    def test_production_code_has_no_legacy_risk_backend(self):
        for rel_path in ("main.py", "llm_backend.py"):
            text = _read(rel_path)
            for token in (
                "REPORT_RISK_ASSESSMENT",
                "__REPORT_RISK_ASSESSMENT__",
                "_build_risk_assessment_messages",
                "RISK_ASSESSMENT_OUTPUT_SCHEMA",
                "_risk_snapshot_payload",
                "build_risk_assessment_system_prompt",
                "build_risk_assessment_user_prompt",
                "empty_risk_assessment",
                "normalize_risk_assessment_json",
            ):
                self.assertNotIn(token, text, f"{rel_path} still contains {token}")

    def test_frontend_has_no_legacy_risk_symbols(self):
        text = _read("track.html")
        for token in (
            "PY_REPORT_RISK_ASSESSMENT",
            "requestRiskAssessment",
            "buildRiskAssessmentHTML",
            "resetRiskAssessmentState",
            "currentRiskAssessment",
            "riskAssessmentLoading",
            "risk-assessment",
        ):
            self.assertNotIn(token, text)

    def test_js_contract_no_longer_exposes_legacy_sentinel(self):
        text = _read("docs/js_api_contract.json")
        for token in (
            "__REPORT_RISK_ASSESSMENT__",
            "risk_assessment_contract",
            "旧风险预警兼容名",
            "待 cleanup 删除",
        ):
            self.assertNotIn(token, text)

    def test_activity_advice_chain_still_exists(self):
        main = _read("main.py")
        backend = _read("llm_backend.py")
        frontend = _read("track.html")
        contract = _read("docs/js_api_contract.json")
        self.assertIn("REPORT_ACTIVITY_ADVICE", main)
        self.assertIn("__REPORT_ACTIVITY_ADVICE__", contract)
        self.assertIn("activity_advice", main)
        self.assertIn("build_activity_advice_system_prompt", backend)
        self.assertIn("normalize_activity_advice_json", backend)
        self.assertIn("empty_activity_advice", backend)
        self.assertIn("requestActivityAdvice", frontend)


if __name__ == "__main__":
    unittest.main()
