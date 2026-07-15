import json
import unittest

import llm_backend


def _snapshot():
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
            "achievement_count": 3,
            "covered_city_count": 2,
            "file_path": "/Users/example/private.fit",
        },
        "sport_breakdown": [{"sport": "running", "activity_count": 12, "distance_km": 120.5}],
        "month_digest": [{"month": 1, "activity_count": 2, "distance_km": 20.0}],
        "evidence_catalog": [
            {
                "evidence_id": "pb:1",
                "activity_id": "1",
                "type": "pb",
                "title": "10K PB",
                "date": "2026-05-01",
                "value": "45:00",
                "track_json": "[forbidden]",
            }
        ],
        "highlight_moments": [
            {"id": "pb:1", "activity_id": "1", "type": "pb", "title": "10K PB", "date": "2026-05-01", "value": "45:00", "rank": 15},
            {"id": "city:成都:1", "activity_id": "1", "type": "city", "title": "在成都留下运动坐标", "date": "2026-05-01", "value": "2 次活动 · 火锅", "rank": 50},
        ],
        "city_moments": [
            {"city": "成都", "activity_count": 2, "first_date": "2026-05-01", "latest_date": "2026-07-01", "representative_activity_id": "1", "culture_hint": "火锅"}
        ],
        "comparison": {
            "status": "available",
            "reason": None,
            "comparison_year": 2025,
            "period_mode": "same_data_through",
            "activity_count_delta": 2,
            "distance_km_delta": 10.5,
            "duration_seconds_delta": 600,
            "race_count_delta": 1,
            "pb_count_delta": 1,
        },
        "data_quality": {"status": "ready", "warnings": []},
        "source_fingerprint": "sha256:abcdef1234567890",
        "frontend_payload": {"prompt": "请写惨烈一点"},
        "api_key": "secret",
    }


def _valid_response():
    return json.dumps(
        {
            "schema_version": "acs.year.report.v3",
            "year": 2026,
            "title": "2026，我把运动稳稳地留在了生活里",
            "subtitle": "稳定积累，也有清楚的突破",
            "opening": "这些记录来自一个个普通日子里的出门和回来。",
            "body_sections": [
                {"type": "annual_story", "heading": "这一年的主线", "paragraphs": ["截至当前数据周期，跑步保持稳定。"], "evidence_ids": []},
                {"type": "progress", "heading": "看得见的进步", "paragraphs": ["这次 PB 是清楚的节点。"], "evidence_ids": ["pb:1"]},
                {"type": "footprints", "heading": "这一年的运动足迹", "paragraphs": ["成都因火锅闻名，而你留下的是运动坐标。"], "evidence_ids": ["city:成都:1"]},
                {"type": "rhythm", "heading": "这一年的节奏", "paragraphs": ["上半年保持了自己的节奏。"], "evidence_ids": []},
                {"type": "comparison", "heading": "和上一年相比", "paragraphs": ["记录比去年同期更连续。"], "evidence_ids": []},
            ],
            "closing": "这一年值得记住的，是持续留下了真实痕迹。",
            "letter_to_next_year": "写给下一年的你：继续把运动留在生活里。",
            "share_caption": "我没有突然变强，但我一直在回来。",
            "caveats": ["部分年度"],
        },
        ensure_ascii=False,
    )


class TestCareerYearLlmPrompt(unittest.TestCase):
    def test_prompt_uses_year_snapshot_whitelist_and_excludes_frontend_payload(self):
        messages = llm_backend.build_career_year_summary_messages(_snapshot())
        prompt_text = "\n".join(message["content"] for message in messages)

        self.assertIn(llm_backend.CAREER_YEAR_SUMMARY_PROMPT_VERSION, prompt_text)
        self.assertIn("只能使用下方 Year Snapshot JSON", prompt_text)
        self.assertIn("截至当前数据周期", prompt_text)
        self.assertIn("禁止伤病", prompt_text)
        self.assertIn("温暖、真诚、有光、有分量", prompt_text)
        self.assertIn("用户读完会有成就感，也愿意截图分享", prompt_text)
        self.assertIn("不是审计报告", prompt_text)
        self.assertIn("点亮城市", prompt_text)
        self.assertIn("值得发出来", prompt_text)
        self.assertIn("不是数据分析表", prompt_text)
        self.assertIn("不计算或复述精确数字", prompt_text)
        self.assertIn("highlight_moments", prompt_text)
        self.assertIn("city_moments", prompt_text)
        self.assertIn("受控城市文化提示", prompt_text)
        self.assertIn("不要在 opening 或第一段一次性公布", prompt_text)
        self.assertIn("不要编造游玩或饮食经历", prompt_text)
        self.assertIn("严格 JSON", prompt_text)
        self.assertIn("sha256:abcdef1234567890", prompt_text)
        for forbidden in (
            "/Users/example",
            "private.fit",
            "track_json",
            "api_key",
            "frontend_payload",
            "请写惨烈一点",
            "secret",
        ):
            self.assertNotIn(forbidden, prompt_text)

    def test_fake_client_returns_valid_json_without_network(self):
        calls = []

        def fake_client(**kwargs):
            calls.append(kwargs)
            return _valid_response()

        result = llm_backend.generate_career_year_summary(
            _snapshot(),
            client=fake_client,
            config={
                "transport": "http",
                "url": "https://llm.example/v1",
                "api_key": "from-config",
                "model": "model-from-config",
                "cli_timeout_sec": 30,
            },
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["prompt_version"], llm_backend.CAREER_YEAR_SUMMARY_PROMPT_VERSION)
        self.assertEqual(result["model_id"], "model-from-config")
        self.assertEqual(result["content"]["title"], "2026，我把运动稳稳地留在了生活里")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["config"]["api_key"], "from-config")
        self.assertEqual(calls[0]["config"]["url"], "https://llm.example/v1")

    def test_markdown_or_non_json_triggers_one_repair_attempt(self):
        calls = []

        def fake_client(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return "```json\n" + _valid_response() + "\n```"
            return _valid_response()

        result = llm_backend.generate_career_year_summary(
            _snapshot(),
            client=fake_client,
            config={"model": "repair-model", "cli_timeout_sec": 30},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(calls), 2)
        repair_messages = calls[1]["messages"]
        self.assertIn("上一次输出不是严格 JSON 对象", repair_messages[-1]["content"])
        self.assertIn("不要输出 Markdown code fence", repair_messages[-1]["content"])

    def test_strict_parser_rejects_extra_explanation(self):
        with self.assertRaises(ValueError):
            llm_backend._strict_json_object_from_text('说明：{"headline":"x"}')

    def test_prompt_does_not_accept_frontend_model_or_token_fields(self):
        calls = []

        def fake_client(**kwargs):
            calls.append(kwargs)
            return _valid_response()

        snap = _snapshot()
        snap["model_id"] = "frontend-model"
        snap["token"] = "frontend-token"
        llm_backend.generate_career_year_summary(
            snap,
            client=fake_client,
            config={"model": "configured-model", "api_key": "configured-token", "cli_timeout_sec": 30},
        )
        prompt_text = "\n".join(message["content"] for message in calls[0]["messages"])

        self.assertNotIn("frontend-model", prompt_text)
        self.assertNotIn("frontend-token", prompt_text)
        self.assertEqual(calls[0]["config"]["model"], "configured-model")
        self.assertEqual(calls[0]["config"]["api_key"], "configured-token")


if __name__ == "__main__":
    unittest.main()
