from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP0ApiContract(unittest.TestCase):
    def _fatigue_review_contract(self) -> dict:
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        with open(contract_path, encoding="utf-8") as f:
            doc = json.load(f)
        for item in doc.get("methods", doc.get("apis", [])):
            if item.get("name") == "get_fatigue_review":
                return item
        self.fail("docs/js_api_contract.json 必须登记 get_fatigue_review")

    def test_contract_declares_authoritative_curves(self):
        item = self._fatigue_review_contract()
        returns = item.get("returns", "")
        for field in (
            "curves: {distance, time, hr, speed, altitude, grade, gap, efficiency, terrain_load, total_distance_m}",
            "curves.distance 为后端权威距离轴",
            "curves.time 为后端权威时间轴",
            "curves.total_distance_m 单位 m",
        ):
            self.assertIn(field, returns)

    def test_contract_declares_frontend_zero_inference(self):
        item = self._fatigue_review_contract()
        contract = item.get("contract", "")
        for field in (
            "前端零推断",
            "curves.distance 必须由后端权威输出",
            "前端不得通过 _distanceFromSpeedTime 或 points 重建事实距离轴",
            "fatigue_zones.start_km/end_km",
            "collapse_events.trigger_km",
            "必须和 curves.distance 同源",
        ):
            self.assertIn(field, contract)

    def test_contract_forbids_debug_and_raw_fields(self):
        item = self._fatigue_review_contract()
        contract = item.get("contract", "")
        for forbidden in ("shadow_diff", "shadow_diff_json", "diff", "records", "全量 points"):
            self.assertIn(forbidden, contract)

    def test_contract_marks_ai_as_p6(self):
        item = self._fatigue_review_contract()
        description = item.get("description", "")
        self.assertIn("AI 洞察 __FATIGUE_REVIEW_INSIGHT__ 留到 P6", description)
        self.assertIn("后端快照回正", description)


class TestFatigueReviewP0SnapshotShape(unittest.TestCase):
    def test_empty_snapshot_contains_p0_curve_fields(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot()
        curves = snapshot.get("curves", {})
        for key in ("distance", "time", "hr", "speed", "altitude", "grade", "gap", "efficiency", "terrain_load", "total_distance_m"):
            self.assertIn(key, curves)
        self.assertEqual(curves["distance"], [])
        self.assertEqual(curves["time"], [])
        self.assertEqual(curves["altitude"], [])

    def test_empty_snapshot_forbids_raw_debug_fields(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot()
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in ("shadow_diff", "shadow_diff_json", '"diff"', '"records"'):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
