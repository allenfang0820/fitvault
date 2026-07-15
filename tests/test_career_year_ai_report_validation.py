import copy
import unittest

import career_backend


def _snapshot(comparison_status="available"):
    return {
        "snapshot_version": "acs.year.v2",
        "scope": "year",
        "year": 2026,
        "period": {
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "as_of_date": "2026-07-14",
            "data_through": "2026-07-01",
            "is_partial_year": True,
            "latest_activity_date": "2026-07-01",
        },
        "summary": {
            "activity_count": 12,
            "total_distance_km": 120.5,
            "total_duration_seconds": 36000,
            "race_count": 1,
            "pb_count": 2,
            "achievement_count": 1,
            "covered_city_count": 2,
        },
        "sport_breakdown": [],
        "month_digest": [
            {"month": month, "activity_count": 0, "distance_km": 0.0, "duration_seconds": 0, "primary_sport": ""}
            for month in range(1, 13)
        ],
        "evidence_catalog": [
            {"evidence_id": "race:1", "activity_id": "1", "type": "race", "title": "上海 10K", "date": "2026-05-01", "value": "10K"},
            {"evidence_id": "pb:1", "activity_id": "2", "type": "pb", "title": "10K PB", "date": "2026-06-01", "value": "45:00"},
        ],
        "highlight_moments": [
            {"id": "race:1", "activity_id": "1", "type": "race", "title": "上海 10K", "date": "2026-05-01", "value": "10K", "rank": 10},
            {"id": "city:成都:2", "activity_id": "2", "type": "city", "title": "在成都留下运动坐标", "date": "2026-06-01", "value": "2 次活动 · 火锅", "rank": 50},
        ],
        "city_moments": [
            {"city": "成都", "activity_count": 2, "first_date": "2026-06-01", "latest_date": "2026-07-01", "representative_activity_id": "2", "culture_hint": "火锅"}
        ],
        "comparison": {
            "status": comparison_status,
            "reason": None if comparison_status == "available" else "previous_year_no_data",
            "comparison_year": 2025,
            "period_mode": "same_data_through" if comparison_status == "available" else "none",
            "activity_count_delta": 2 if comparison_status == "available" else None,
            "distance_km_delta": 10.5 if comparison_status == "available" else None,
            "duration_seconds_delta": 600 if comparison_status == "available" else None,
            "race_count_delta": 1 if comparison_status == "available" else None,
            "pb_count_delta": 1 if comparison_status == "available" else None,
        },
        "data_quality": {"status": "ready", "warnings": []},
        "source_fingerprint": "sha256:abcdef",
    }


def _draft():
    return {
        "schema_version": "acs.year.report.v3",
        "year": 2026,
        "title": "2026，我把运动稳稳地留在了生活里",
        "subtitle": "稳定积累，也有清楚的突破",
        "opening": "这些记录来自一个个普通日子里的出门和回来。",
        "body_sections": [
            {"type": "annual_story", "heading": "这一年的主线", "paragraphs": ["截至当前数据周期，跑步保持稳定。"], "evidence_ids": []},
            {"type": "races", "heading": "你完成的比赛", "paragraphs": ["这场比赛成为一个清楚的节点。"], "evidence_ids": ["race:1"]},
            {"type": "progress", "heading": "看得见的进步", "paragraphs": ["这次 PB 留下了明确的进步证据。"], "evidence_ids": ["pb:1"]},
            {"type": "footprints", "heading": "这一年的运动足迹", "paragraphs": ["成都因火锅闻名，而运动坐标是这里真正可确认的事实。"], "evidence_ids": ["city:成都:2"]},
            {"type": "rhythm", "heading": "这一年的节奏", "paragraphs": ["上半年保持了自己的节奏。"], "evidence_ids": []},
            {"type": "comparison", "heading": "和上一年相比", "paragraphs": ["记录比去年同期更连续。"], "evidence_ids": []},
        ],
        "closing": "这一年值得记住的，是持续留下了真实痕迹。",
        "letter_to_next_year": "写给下一年的你：继续把运动留在生活里。",
        "share_caption": "我没有突然变强，但我一直在回来。",
        "caveats": ["部分年度，仅作阶段总结"],
    }


class TestCareerYearAiReportValidation(unittest.TestCase):
    def test_valid_report_uses_backend_facts_for_year_summary_and_key_moments(self):
        result = career_backend.validate_career_year_ai_report(_draft(), _snapshot())

        self.assertEqual(result["schema_version"], "acs.year.report.v3")
        self.assertEqual(result["year"], 2026)
        self.assertIn("积累成了 12 次运动", result["fact_lead"])
        self.assertIn("120.5 公里", result["fact_lead"])
        self.assertIn("fact_leads", result)
        self.assertGreaterEqual(len(result["fact_leads"]), 3)
        self.assertEqual([item["type"] for item in result["body_sections"]], ["annual_story", "races", "progress", "footprints", "rhythm", "comparison"])
        self.assertEqual(result["facts_summary"]["activity_count"], 12)
        self.assertEqual(result["facts_summary"]["total_distance_km"], 120.5)
        self.assertEqual(result["key_moments"][0]["title"], "上海 10K")
        self.assertEqual(result["key_moments"][0]["date"], "2026-05-01")
        self.assertEqual(result["key_moments"][0]["activity_id"], "1")
        self.assertEqual(result["key_moments"][0]["detail_link"], {"activity_id": "1", "source": "activity"})
        self.assertEqual(result["key_moments"][1]["value"], "45:00")
        self.assertEqual(result["key_moments"][2]["type"], "city")

    def test_rejects_non_object_wrong_schema_and_wrong_year(self):
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report("not-json", _snapshot())
        bad_schema = _draft()
        bad_schema["schema_version"] = "bad"
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(bad_schema, _snapshot())
        bad_year = _draft()
        bad_year["year"] = 2025
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(bad_year, _snapshot())

    def test_unknown_evidence_below_threshold_is_dropped_and_duplicates_are_removed(self):
        draft = _draft()
        draft["body_sections"][1]["evidence_ids"] = ["race:1", "race:1", "unknown:1"]
        draft["body_sections"][2]["evidence_ids"] = ["pb:1"]

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        self.assertEqual([item["evidence_id"] for item in result["key_moments"]], ["race:1", "pb:1", "city:成都:2"])

    def test_unknown_evidence_at_failure_threshold_rejects_report(self):
        draft = _draft()
        draft["body_sections"][1]["evidence_ids"] = ["unknown:1", "unknown:2"]

        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

    def test_cleaning_removes_scripts_code_fences_control_chars_and_limits_lengths(self):
        draft = _draft()
        draft["title"] = "<script>alert(1)</script>" + ("很长" * 80)
        draft["opening"] = "```json\n" + ("开篇" * 250) + "\n```"
        draft["body_sections"][0]["paragraphs"] = ["可见\x00文本<script>bad()</script>"]

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())
        serialized = repr(result)

        self.assertNotIn("<script", serialized)
        self.assertNotIn("```", serialized)
        self.assertNotIn("\x00", serialized)
        self.assertLessEqual(len(result["headline"]), 60)
        self.assertLessEqual(len(result["opening"]), 320)

    def test_unavailable_comparison_downgrades_ai_comparison_claim(self):
        draft = _draft()
        result = career_backend.validate_career_year_ai_report(draft, _snapshot(comparison_status="unavailable"))

        self.assertNotIn("comparison", [item["type"] for item in result["body_sections"]])
        self.assertEqual(result["comparison_summary"], "")

    def test_evidence_shortage_allows_fewer_than_three_key_moments(self):
        snap = copy.deepcopy(_snapshot())
        snap["evidence_catalog"] = snap["evidence_catalog"][:1]
        draft = _draft()
        draft["body_sections"][2]["evidence_ids"] = []

        result = career_backend.validate_career_year_ai_report(draft, snap)

        self.assertEqual([item["type"] for item in result["key_moments"]], ["race", "city"])

    def test_progress_section_accepts_backend_activity_highlight_moments(self):
        snap = copy.deepcopy(_snapshot())
        snap["highlight_moments"].append({
            "id": "longest_distance:3",
            "activity_id": "3",
            "type": "longest_distance",
            "title": "年度最长距离",
            "date": "2026-07-01",
            "value": "42.2 km",
            "rank": 30,
        })
        snap["highlight_moments"] = sorted(
            snap["highlight_moments"],
            key=lambda item: (int(item.get("rank") or 99), str(item.get("date") or ""), str(item.get("id") or "")),
        )
        draft = _draft()
        draft["body_sections"][2]["evidence_ids"] = ["pb:1", "longest_distance:3"]

        result = career_backend.validate_career_year_ai_report(draft, snap)

        self.assertIn("longest_distance", [item["type"] for item in result["key_moments"]])

    def test_footprints_section_accepts_first_city_achievement_evidence(self):
        draft = _draft()
        draft["body_sections"][3]["evidence_ids"] = ["achievement:first_city:海口市:99"]
        snap = copy.deepcopy(_snapshot())
        snap["evidence_catalog"].append({
            "evidence_id": "achievement:first_city:海口市:99",
            "activity_id": "4",
            "type": "achievement",
            "title": "首次点亮城市",
            "date": "2026-02-01",
            "value": "海口市",
        })
        snap["evidence_catalog"] = sorted(
            snap["evidence_catalog"],
            key=lambda item: (str(item.get("date") or ""), str(item.get("type") or ""), str(item.get("evidence_id") or "")),
        )

        result = career_backend.validate_career_year_ai_report(draft, snap)

        footprints = [section for section in result["body_sections"] if section["type"] == "footprints"][0]
        self.assertEqual(footprints["evidence"][0]["evidence_id"], "achievement:first_city:海口市:99")

    def test_missing_base_section_rejects_and_optional_sections_require_matching_facts(self):
        draft = _draft()
        draft["body_sections"] = [item for item in draft["body_sections"] if item["type"] != "rhythm"]
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

        snap = copy.deepcopy(_snapshot())
        snap["summary"]["race_count"] = 0
        snap["summary"]["pb_count"] = 0
        snap["summary"]["achievement_count"] = 0
        result = career_backend.validate_career_year_ai_report(_draft(), snap)
        self.assertEqual([item["type"] for item in result["body_sections"]], ["annual_story", "footprints", "rhythm", "comparison"])

    def test_drops_ai_authored_precise_numbers_and_keeps_backend_fact_lead(self):
        draft = _draft()
        draft["opening"] = "这一年完成了 99 次运动。这些记录来自一次次真实的出发。"
        result = career_backend.validate_career_year_ai_report(draft, _snapshot())
        self.assertNotIn("99", result["opening"])
        self.assertIn("这些记录来自一次次真实的出发", result["opening"])
        self.assertIn("积累成了 12 次运动", result["fact_lead"])

    def test_closing_and_letter_end_as_complete_sentences(self):
        draft = _draft()
        draft["closing"] = "这一年值得庆祝；"
        draft["letter_to_next_year"] = "继续出发，继续抵达："
        draft["share_caption"] = "值得发出来看看；"

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        self.assertEqual(result["closing"], "这一年值得庆祝。")
        self.assertEqual(result["letter_to_next_year"], "继续出发，继续抵达。")
        self.assertEqual(result["share_caption"], "值得发出来看看")


if __name__ == "__main__":
    unittest.main()
