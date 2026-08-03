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
            "record_milestone_count": 0,
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
        "record_milestones": {
            "count": 0,
            "items": [],
            "record_keys": [],
            "by_record_key": [],
            "largest_breakthrough": None,
            "representative_breakthrough": None,
            "first_breakthroughs": [],
        },
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
        self.assertIn("12 次运动", result["fact_lead"])
        self.assertIn("120.5 公里", result["fact_lead"])
        self.assertIn("覆盖了 2 座城市", result["fact_lead"])
        self.assertIn("成都", result["fact_lead"])
        self.assertIn("fact_leads", result)
        self.assertGreaterEqual(len(result["fact_leads"]), 2)
        self.assertLessEqual(len(result["fact_leads"]), 3)
        for forbidden in ("其中真正发亮的部分", "它们让这一年的高光变得更具体", "这些普通日子已经积累成了", "时间也留下了痕迹"):
            self.assertNotIn(forbidden, result["fact_lead"])
        self.assertEqual([item["type"] for item in result["body_sections"]], ["annual_story", "races", "progress", "footprints", "rhythm", "comparison"])
        self.assertEqual(result["facts_summary"]["activity_count"], 12)
        self.assertEqual(result["facts_summary"]["total_distance_km"], 120.5)
        self.assertEqual(result["facts_summary"]["record_milestone_count"], 0)
        self.assertEqual(result["key_moments"][0]["title"], "上海 10K")
        self.assertEqual(result["key_moments"][0]["date"], "2026-05-01")
        self.assertEqual(result["key_moments"][0]["activity_id"], "1")
        self.assertEqual(result["key_moments"][0]["detail_link"], {"activity_id": "1", "source": "activity"})
        self.assertEqual(result["key_moments"][1]["value"], "45:00")
        self.assertNotIn("city", [item["type"] for item in result["key_moments"]])

    def test_preserves_all_llm_body_paragraphs_without_truncation_or_reordering(self):
        draft = _draft()
        annual_paragraphs = [
            "第一段：这一年的主线从春天开始。",
            "第二段：夏天的运动坐标继续展开。",
            "第三段：秋天仍然有稳定的节奏。",
            "第四段：这一段过去会被 max_items 裁掉，现在必须保留。",
        ]
        rhythm_paragraphs = [
            "一月留下开局。",
            "二月继续衔接。",
            "三月短暂停顿。",
            "四月重新回来。",
        ]
        draft["body_sections"][0]["paragraphs"] = annual_paragraphs
        draft["body_sections"][4]["paragraphs"] = rhythm_paragraphs
        draft["body_sections"][3]["paragraphs"] = ["第一段足迹。", "第二段足迹。", "第三段足迹。", "第四段足迹。"]
        draft["caveats"] = ["提示一", "提示二", "提示三", "提示四", "提示五"]

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        self.assertEqual(result["body_sections"][0]["paragraphs"], annual_paragraphs)
        self.assertEqual(result["body_sections"][4]["paragraphs"], rhythm_paragraphs)
        self.assertEqual(result["body_sections"][3]["paragraphs"], draft["body_sections"][3]["paragraphs"])
        self.assertEqual(result["caveats"], draft["caveats"])

    def test_preserves_user_2025_llm_report_content_shape(self):
        snap = copy.deepcopy(_snapshot())
        snap["year"] = 2025
        snap["period"] = {
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "as_of_date": "2025-12-31",
            "data_through": "2025-12-31",
            "is_partial_year": False,
            "latest_activity_date": "2025-12-31",
        }
        snap["summary"].update({
            "activity_count": 98,
            "race_count": 0,
            "pb_count": 2,
            "achievement_count": 10,
            "record_milestone_count": 0,
            "covered_city_count": 10,
        })
        snap["evidence_catalog"] = [
            {"evidence_id": "pb:running_10k:108", "activity_id": "108", "type": "pb", "title": "10K PB", "date": "2025-05-03", "value": "10K"},
            {"evidence_id": "pb:record:v2:965e2ed6ee1c476934c6", "activity_id": "406", "type": "pb", "title": "5K PB", "date": "2025-05-03", "value": "5K"},
        ]
        snap["evidence_catalog"] = sorted(
            snap["evidence_catalog"],
            key=lambda item: (str(item.get("date") or ""), str(item.get("type") or ""), str(item.get("evidence_id") or "")),
        )
        snap["city_moments"] = [
            {"city": city, "activity_count": 1, "first_date": "2025-01-01", "latest_date": "2025-01-01", "representative_activity_id": str(index), "culture_hint": ""}
            for index, city in enumerate(["北京市", "奉节县", "忠县", "宜昌市", "大阪市", "宇治市", "神户市", "汕头市", "岳麓区", "福建省"], start=1)
        ]
        snap["city_moments"] = sorted(
            snap["city_moments"],
            key=lambda item: (-int(item.get("activity_count") or 0), str(item.get("first_date") or ""), str(item.get("city") or "")),
        )
        snap["comparison"]["comparison_year"] = 2024
        draft = {
            "schema_version": "acs.year.report.v3",
            "year": 2025,
            "title": "跑到新纪录的这一年",
            "subtitle": "两个距离刷新，十座城市坐标，一次跨国的运动抵达",
            "opening": "2025年，有一件事值得被记住：5月，同一天内刷新了5公里和10公里两项个人纪录。",
            "body_sections": [
                {"type": "annual_story", "heading": "跑步是这一年的主角，5月最亮", "paragraphs": ["2025年全年以跑步为核心。", "2月有一趟特别的出发。", "下半年，跑步节奏逐渐稳定。"], "evidence_ids": []},
                {"type": "progress", "heading": "5月，同一天，两项新纪录", "paragraphs": ["5月3日，同一次跑步，两项个人纪录同时刷新。", "从全年看，2项新纪录这个数字不大，但它们的重量不取决于个数。"], "evidence_ids": ["pb:running_10k:108", "pb:record:v2:965e2ed6ee1c476934c6"]},
                {"type": "footprints", "heading": "十座城市，十个不同的坐标", "paragraphs": ["北京是全年的运动主战场。", "重庆的奉节县和忠县是5月的收获。", "日本的轨迹集中在2月：大阪、宇治、神户。"], "evidence_ids": []},
                {"type": "rhythm", "heading": "运动节奏：开局稳，5月冲高，下半年持续在线", "paragraphs": ["1月8次跑步开局，2月活动总量更高但以步行为主。\n\n整体来看，这一年大部分时间都在跑步。"], "evidence_ids": []},
                {"type": "comparison", "heading": "和去年相比：跑得少了，但跑得更快了", "paragraphs": ["和2024年相比，活动次数和总里程都有所下降。", "这不是一个以量取胜的年份，是一个以内核驱动的年份。"], "evidence_ids": []},
            ],
            "closing": "2025年最值得记住的，是5月那一次跑步。",
            "letter_to_next_year": "如果2025是跑到新纪录的一年，2026可以把稳定和探索继续并行。",
            "share_caption": "2025年，两项个人纪录，十座城市，一个值得记住的跑步年份",
            "caveats": ["全年未参与正式比赛", "record_milestones 为空，后端未判定突破性里程碑", "十月后活动量明显下降"],
        }

        result = career_backend.validate_career_year_ai_report(draft, snap)

        self.assertEqual(result["title"], draft["title"])
        self.assertEqual(result["subtitle"], draft["subtitle"])
        self.assertEqual(result["opening"], draft["opening"])
        self.assertEqual(
            [(section["type"], section["heading"], section["paragraphs"]) for section in result["body_sections"]],
            [(section["type"], section["heading"], section["paragraphs"]) for section in draft["body_sections"]],
        )
        self.assertEqual(result["closing"], draft["closing"])
        self.assertEqual(result["letter_to_next_year"], draft["letter_to_next_year"])
        self.assertEqual(result["share_caption"], draft["share_caption"])
        self.assertEqual(result["caveats"], draft["caveats"])

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

    def test_duplicate_evidence_is_removed_without_dropping_body_text(self):
        draft = _draft()
        draft["body_sections"][1]["evidence_ids"] = ["race:1", "race:1"]
        draft["body_sections"][2]["evidence_ids"] = ["pb:1"]

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        self.assertEqual([item["evidence_id"] for item in result["key_moments"]], ["race:1", "pb:1"])
        self.assertEqual(result["body_sections"][1]["paragraphs"], ["这场比赛成为一个清楚的节点。"])

    def test_unknown_evidence_at_failure_threshold_rejects_report(self):
        draft = _draft()
        draft["body_sections"][1]["evidence_ids"] = ["unknown:1"]

        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

    def test_unknown_evidence_in_non_evidence_sections_is_ignored(self):
        draft = _draft()
        draft["body_sections"][0]["evidence_ids"] = [
            "pb:1",
            "achievement:first_city:大阪市:563",
            "achievement:first_city:宇治市:679",
            "achievement:first_city:神户市:125",
        ]
        draft["body_sections"][3]["evidence_ids"] = ["achievement:first_city:成都:2"]
        draft["body_sections"][4]["evidence_ids"] = ["missing:rhythm"]
        draft["body_sections"][5]["evidence_ids"] = ["missing:comparison"]

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        annual_story = [section for section in result["body_sections"] if section["type"] == "annual_story"][0]
        rhythm = [section for section in result["body_sections"] if section["type"] == "rhythm"][0]
        comparison = [section for section in result["body_sections"] if section["type"] == "comparison"][0]
        self.assertEqual(annual_story["evidence"], [])
        self.assertEqual(rhythm["evidence"], [])
        self.assertEqual(comparison["evidence"], [])
        self.assertEqual([item["evidence_id"] for item in result["key_moments"]], ["race:1", "pb:1"])

    def test_progress_unknown_evidence_still_rejects_report(self):
        draft = _draft()
        draft["body_sections"][2]["evidence_ids"] = ["unknown:1", "unknown:2"]

        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

    def test_dangerous_or_oversized_body_text_rejects_instead_of_silent_rewrite(self):
        draft = _draft()
        draft["body_sections"][0]["paragraphs"] = ["可见\x00文本<script>bad()</script>"]

        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

        draft = _draft()
        draft["opening"] = "```json\n这不是纯正文\n```"
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

        draft = _draft()
        draft["opening"] = "开篇" * 5000
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

    def test_unavailable_comparison_preserves_llm_comparison_body(self):
        draft = _draft()
        result = career_backend.validate_career_year_ai_report(draft, _snapshot(comparison_status="unavailable"))

        self.assertIn("comparison", [item["type"] for item in result["body_sections"]])
        self.assertEqual(result["comparison_summary"], "记录比去年同期更连续。")

    def test_evidence_shortage_allows_fewer_than_three_key_moments(self):
        snap = copy.deepcopy(_snapshot())
        snap["evidence_catalog"] = snap["evidence_catalog"][:1]
        draft = _draft()
        draft["body_sections"][2]["evidence_ids"] = []

        result = career_backend.validate_career_year_ai_report(draft, snap)

        self.assertEqual([item["type"] for item in result["key_moments"]], ["race"])

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

    def test_progress_section_accepts_record_milestones_without_pb_or_achievement(self):
        snap = copy.deepcopy(_snapshot())
        snap["summary"]["pb_count"] = 0
        snap["summary"]["achievement_count"] = 0
        snap["summary"]["record_milestone_count"] = 1
        snap["record_milestones"] = {
            "count": 1,
            "items": [
                {
                    "id": "record_milestone:5k:1",
                    "activity_id": "5",
                    "sport": "running",
                    "sport_label": "跑步",
                    "record_key": "running_5k",
                    "display_name": "5K",
                    "title": "刷新纪录：5K",
                    "date": "2026-06-20",
                    "activity_title": "朝阳公园晨跑",
                    "location": {"city": "北京", "country": "", "display": "北京"},
                    "location_label": "北京",
                    "new_record": {"value": 1700.0, "unit": "seconds", "display": "28:20"},
                    "previous_record": {"value": 1800.0, "unit": "seconds", "display": "30:00"},
                    "improvement": {"value": 100.0, "unit": "seconds", "display": "01:40", "relative_delta_ratio": 0.055556, "relative_delta_percent": 5.56, "direction": "lower_is_better"},
                }
            ],
            "record_keys": ["running_5k"],
            "by_record_key": [{"record_key": "running_5k", "display_name": "5K", "sport": "running", "sport_label": "跑步", "count": 1, "first_date": "2026-06-20", "latest_date": "2026-06-20"}],
            "largest_breakthrough": None,
            "representative_breakthrough": {
                "id": "record_milestone:5k:1",
                "activity_id": "5",
                "sport": "running",
                "sport_label": "跑步",
                "record_key": "running_5k",
                "display_name": "5K",
                "title": "刷新纪录：5K",
                "date": "2026-06-20",
                "activity_title": "朝阳公园晨跑",
                "location": {"city": "北京", "country": "", "display": "北京"},
                "location_label": "北京",
                "new_record": {"value": 1700.0, "unit": "seconds", "display": "28:20"},
                "previous_record": {"value": 1800.0, "unit": "seconds", "display": "30:00"},
                "improvement": {"value": 100.0, "unit": "seconds", "display": "01:40", "relative_delta_ratio": 0.055556, "relative_delta_percent": 5.56, "direction": "lower_is_better"},
            },
            "first_breakthroughs": [],
        }
        snap["evidence_catalog"] = [
            {
                "evidence_id": "record_milestone:5k:1",
                "activity_id": "5",
                "type": "record_milestone",
                "title": "刷新纪录：5K",
                "date": "2026-06-20",
                "value": "28:20 / 上一纪录 30:00",
            }
        ]
        snap["highlight_moments"] = [
            {
                "id": "record_milestone:5k:1",
                "activity_id": "5",
                "type": "record_milestone",
                "title": "刷新纪录：5K",
                "date": "2026-06-20",
                "value": "28:20 / 上一纪录 30:00",
                "rank": 14,
            }
        ]
        draft = _draft()
        draft["body_sections"] = [
            section for section in draft["body_sections"]
            if section["type"] not in {"races", "comparison"}
        ]
        progress = next(section for section in draft["body_sections"] if section["type"] == "progress")
        progress["paragraphs"] = ["这一年的刷新纪录，是后端确认过的清楚突破。"]
        progress["evidence_ids"] = ["record_milestone:5k:1"]

        result = career_backend.validate_career_year_ai_report(draft, snap)

        self.assertEqual([item["type"] for item in result["body_sections"]], ["annual_story", "progress", "footprints", "rhythm"])
        self.assertEqual(result["key_moments"][0]["type"], "record_milestone")
        self.assertEqual(result["key_moments"][0]["detail_link"], {"activity_id": "5", "source": "activity"})
        self.assertEqual(result["facts_summary"]["record_milestone_count"], 1)
        self.assertIn("刷新纪录", result["fact_lead"])
        self.assertIn("2026-06-20", result["fact_lead"])
        self.assertIn("北京", result["fact_lead"])
        self.assertIn("朝阳公园晨跑", result["fact_lead"])
        self.assertIn("从 30:00 提升到 28:20", result["fact_lead"])

    def test_distance_record_milestone_fact_lead_uses_kilometers_not_raw_meters(self):
        snap = copy.deepcopy(_snapshot())
        snap["summary"]["record_milestone_count"] = 1
        milestone = {
            "id": "record_milestone:cycling-distance:1",
            "activity_id": "7",
            "sport": "cycling",
            "sport_label": "骑行",
            "record_key": "cycling_longest_distance",
            "display_name": "最长骑行距离",
            "title": "刷新纪录：最长骑行距离",
            "date": "2026-05-31",
            "activity_title": "名山区骑行",
            "location": {"city": "名山区", "country": "", "display": "名山区"},
            "location_label": "名山区",
            "new_record": {"value": 128838.0, "unit": "meters", "display": "128838 m"},
            "previous_record": {"value": 29977.0, "unit": "meters", "display": "29977 m"},
            "improvement": {"value": 98861.0, "unit": "meters", "display": "98861 m", "relative_delta_ratio": 3.2979, "relative_delta_percent": 329.79, "direction": "higher_is_better"},
        }
        snap["record_milestones"] = {
            "count": 1,
            "items": [milestone],
            "record_keys": ["cycling_longest_distance"],
            "by_record_key": [{"record_key": "cycling_longest_distance", "display_name": "最长骑行距离", "sport": "cycling", "sport_label": "骑行", "count": 1, "first_date": "2026-05-31", "latest_date": "2026-05-31"}],
            "largest_breakthrough": milestone,
            "representative_breakthrough": milestone,
            "first_breakthroughs": [milestone],
        }

        result = career_backend.validate_career_year_ai_report(_draft(), snap)

        self.assertIn("最长骑行距离", result["fact_lead"])
        self.assertIn("从 30 公里 提升到 128.8 公里", result["fact_lead"])
        self.assertNotIn("29977 m", result["fact_lead"])
        self.assertNotIn("128838 m", result["fact_lead"])

    def test_footprints_section_ignores_first_city_achievement_evidence(self):
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
        self.assertEqual(footprints["evidence"], [])
        self.assertNotIn("achievement:first_city:海口市:99", [item.get("evidence_id") for item in result["key_moments"]])

    def test_missing_base_section_rejects_and_optional_sections_keep_llm_body(self):
        draft = _draft()
        draft["body_sections"] = [item for item in draft["body_sections"] if item["type"] != "rhythm"]
        with self.assertRaises(ValueError):
            career_backend.validate_career_year_ai_report(draft, _snapshot())

        snap = copy.deepcopy(_snapshot())
        snap["summary"]["race_count"] = 0
        snap["summary"]["pb_count"] = 0
        snap["summary"]["achievement_count"] = 0
        result = career_backend.validate_career_year_ai_report(_draft(), snap)
        self.assertEqual([item["type"] for item in result["body_sections"]], ["annual_story", "races", "progress", "footprints", "rhythm", "comparison"])

    def test_preserves_ai_authored_numbers_and_keeps_backend_fact_lead_separate(self):
        draft = _draft()
        draft["opening"] = "这一年完成了 99 次运动。这些记录来自一次次真实的出发。"
        result = career_backend.validate_career_year_ai_report(draft, _snapshot())
        self.assertIn("99", result["opening"])
        self.assertEqual(result["opening"], draft["opening"])
        self.assertIn("12 次运动", result["fact_lead"])

    def test_closing_letter_and_share_caption_are_preserved(self):
        draft = _draft()
        draft["closing"] = "这一年值得庆祝；"
        draft["letter_to_next_year"] = "继续出发，继续抵达："
        draft["share_caption"] = "值得发出来看看；"

        result = career_backend.validate_career_year_ai_report(draft, _snapshot())

        self.assertEqual(result["closing"], "这一年值得庆祝；")
        self.assertEqual(result["letter_to_next_year"], "继续出发，继续抵达：")
        self.assertEqual(result["share_caption"], "值得发出来看看；")


if __name__ == "__main__":
    unittest.main()
