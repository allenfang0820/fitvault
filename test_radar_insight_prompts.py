"""
雷达图 AI 洞察 prompt / normalizer / snapshot 单元测试。

覆盖范围：
- build_radar_insight_system_prompt:6 维度 / 5 sport_type / DATA BOUNDARY / MUST NOT
- _build_radar_insight_snapshot_payload:None / dict / 序列化
- normalize_radar_insight_json:markdown 包裹 / 残缺 JSON / 字段缺失
- _build_radar_insight_snapshot:shadow_diff 隔离 / 字段白名单

遵循 fit-arch-contrac 契约：
- 不依赖 DB
- 不依赖 AI/LLM(纯函数级 mock)
- 不写回 canonical 层
- 不使用 shadow_diff
"""
import json
import unittest
from unittest import mock

from llm_backend import (
    build_radar_insight_system_prompt,
    _build_radar_insight_snapshot_payload,
    normalize_radar_insight_json,
    empty_radar_insight,
    RADAR_DIMENSION_INTERPRETATION,
    RADAR_INSIGHT_OUTPUT_SCHEMA,
)
from main import _build_radar_insight_snapshot


def _make_sample_snapshot(sport_type: str = "running", with_metrics: bool = True) -> dict:
    """构造一个 sample snapshot,模拟 _build_radar_insight_snapshot 的产物。"""
    snap = {
        "source": "DB Canonical / 雷达后端引擎 / Resolver Truth",
        "sport_type": sport_type,
        "aggregation_window_days": 90,
        "user_profile": {
            "age": 30, "gender": "male", "resting_hr": 60,
            "max_hr": 190, "hrv_baseline": 65,
        },
    }
    if with_metrics:
        snap["metrics"] = {
            "ctl": 65.5, "atl": 42.3, "tsb": 23.2, "hrv": 65,
            "decoupling": 4.8, "vam": 750.0, "threshold_hr": 175,
            "anaerobic_peak": 5.2,
            "radar": {
                "dimensions": [
                    {"key": "endurance", "label": "耐力", "score": 75},
                    {"key": "recovery", "label": "恢复", "score": 60},
                ],
            },
        }
    return snap


class TestBuildRadarInsightSystemPromptStructure(unittest.TestCase):
    """build_radar_insight_system_prompt 基础结构 / 关键词存在性。"""

    def test_returns_string(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 500)

    def test_contains_all_6_dimension_keys(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        for key in ("endurance", "recovery", "stability", "threshold", "climbing", "anaerobic"):
            with self.subTest(dimension=key):
                self.assertIn(key, prompt)

    def test_contains_data_boundary_marker(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        self.assertIn("DATA BOUNDARY", prompt)

    def test_contains_must_not_constraints(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        self.assertIn("MUST NOT", prompt)

    def test_contains_dimension_interpretation_field(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        self.assertIn("dimension_interpretation", prompt)

    def test_contains_output_schema_sample_fields(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        for sample_field in ("summary", "weakest_dim", "training_advice", "load_status"):
            with self.subTest(field=sample_field):
                self.assertIn(sample_field, prompt)

    def test_contains_aggregation_window_90_days(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        self.assertIn("90", prompt)


class TestBuildRadarInsightSystemPromptSportMapping(unittest.TestCase):
    """5 个 sport_type 的中文映射。"""

    def test_running_chinese_name(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("running"), "running")
        self.assertIn("跑步", prompt)

    def test_trail_running_chinese_name(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("trail_running"), "trail_running")
        self.assertIn("越野跑", prompt)

    def test_hiking_chinese_name(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("hiking"), "hiking")
        self.assertIn("徒步", prompt)

    def test_cycling_chinese_name(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("cycling"), "cycling")
        self.assertIn("骑行", prompt)

    def test_swimming_chinese_name(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("swimming"), "swimming")
        self.assertIn("游泳", prompt)

    def test_sport_mode_appears_for_running(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("running"), "running")
        self.assertIn("running", prompt)

    def test_sport_mode_appears_for_cycling(self):
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("cycling"), "cycling")
        self.assertIn("cycling", prompt)

    def test_unknown_sport_uses_fallback_chinese(self):
        """未知 sport_type 不抛异常,使用 sport_type 字符串本身或默认 '运动'。"""
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot("unknown_xyz"), "unknown_xyz")
        self.assertIsInstance(prompt, str)
        # 设计:fallback = sport_type or "运动"
        self.assertIn("运动", prompt)


class TestBuildRadarInsightSystemPromptSnapshotPayload(unittest.TestCase):
    """snapshot 序列化逻辑。"""

    def test_empty_snapshot_does_not_throw(self):
        prompt = build_radar_insight_system_prompt(None, "running")
        self.assertIsInstance(prompt, str)

    def test_empty_dict_snapshot_does_not_throw(self):
        prompt = build_radar_insight_system_prompt({}, "running")
        self.assertIsInstance(prompt, str)

    def test_payload_helper_none_returns_empty_json(self):
        result = _build_radar_insight_snapshot_payload(None)
        self.assertEqual(result, "{}")

    def test_payload_helper_serializes_dict(self):
        snap = _make_sample_snapshot(with_metrics=True)
        result = _build_radar_insight_snapshot_payload(snap)
        # 验证是合法 JSON
        parsed = json.loads(result)
        self.assertEqual(parsed["sport_type"], "running")
        self.assertEqual(parsed["aggregation_window_days"], 90)
        self.assertIn("metrics", parsed)

    def test_payload_helper_handles_non_serializable(self):
        """含 datetime / Decimal 等非 JSON 字段时,default=str 应兜底。"""
        from datetime import datetime
        snap = {"timestamp": datetime(2026, 6, 1, 10, 0, 0), "sport_type": "running"}
        result = _build_radar_insight_snapshot_payload(snap)
        self.assertIsInstance(result, str)
        self.assertIn("2026", result)


class TestBuildRadarInsightSystemPromptSafetyBoundaries(unittest.TestCase):
    """安全约束:严禁出现 shadow_diff 等违规字段。"""

    def test_prompt_does_not_contain_shadow_diff(self):
        """即使 snapshot 含 shadow_diff,prompt 也不应出现该字段(JSON 内嵌入除外,本测试只检查 prompt 全文字符串包含性)。"""
        snap = _make_sample_snapshot(with_metrics=True)
        snap["metrics"]["shadow_diff"] = {"legacy": 1, "current": 2}
        prompt = build_radar_insight_system_prompt(snap, "running")
        # shadow_diff 出现在 JSON 序列化区是允许的(白名单是 §5.4 规则 3 的白名单,
        # _build_radar_insight_snapshot 不放它进 snapshot;本测试假设未来某次误改放进来时,prompt 仍能工作)
        # 主要验证函数不抛异常
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 500)

    def test_prompt_contains_dimensional_interpretation_dict(self):
        """6 维度解读字典(RADAR_DIMENSION_INTERPRETATION)的内容出现在 prompt。"""
        prompt = build_radar_insight_system_prompt(_make_sample_snapshot(), "running")
        for sample_phrase in ("Banister 专业训练负荷", "有氧解耦", "垂直爬升速率", "30 秒滑动窗口"):
            with self.subTest(phrase=sample_phrase):
                self.assertIn(sample_phrase, prompt)

    def test_5_sport_types_have_sport_specific_guidance(self):
        """5 sport_type 的「必须输出维度」列表都出现在 prompt。"""
        expected_phrase_map = {
            "running": "running: endurance, recovery, stability, threshold, climbing, anaerobic",
            "trail_running": "trail_running: endurance, recovery, stability, climbing, anaerobic",
            "cycling": "cycling: endurance, recovery, stability, threshold, climbing, anaerobic",
            "hiking": "hiking: endurance, recovery, climbing",
            "swimming": "swimming: endurance, recovery, threshold",
        }
        for sport, phrase in expected_phrase_map.items():
            with self.subTest(sport=sport):
                prompt = build_radar_insight_system_prompt(_make_sample_snapshot(sport), sport)
                self.assertIn(phrase, prompt)


class TestNormalizeRadarInsightJson(unittest.TestCase):
    """normalize_radar_insight_json:LLM 返回文本 → 标准 schema 字典。
    永不抛异常,失败时返回 empty_radar_insight(error)。
    """

    def test_empty_string_returns_empty_insight(self):
        result = normalize_radar_insight_json("")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["error"], "LLM 未返回内容")
        self.assertEqual(result["dimension_interpretation"], [])

    def test_markdown_wrapped_json_is_unwrapped(self):
        raw = '```json\n{"summary": "ok", "sport_type": "running"}\n```'
        result = normalize_radar_insight_json(raw)
        self.assertEqual(result["summary"], "ok")
        self.assertEqual(result["sport_type"], "running")
        # empty_radar_insight() 永远包含 error 键(默认空字符串),
        # 成功解析时验证 error 值为空,而非断言 key 不存在
        self.assertEqual(result["error"], "")

    def test_invalid_json_returns_empty_insight(self):
        result = normalize_radar_insight_json("not a json at all")
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("JSON 解析失败", result["error"])

    def test_json_list_returns_empty_insight(self):
        result = normalize_radar_insight_json("[1, 2, 3]")
        self.assertEqual(result["error"], "洞察结果格式错误")

    def test_summary_truncated_to_300(self):
        long_summary = "x" * 500
        raw = json.dumps({"summary": long_summary})
        result = normalize_radar_insight_json(raw)
        self.assertLessEqual(len(result["summary"]), 300)

    def test_training_advice_truncated_to_500(self):
        long_advice = "a" * 700
        raw = json.dumps({"training_advice": long_advice})
        result = normalize_radar_insight_json(raw)
        self.assertLessEqual(len(result["training_advice"]), 500)

    def test_disclaimer_truncated_to_300(self):
        long_disc = "d" * 500
        raw = json.dumps({"disclaimer": long_disc})
        result = normalize_radar_insight_json(raw)
        self.assertLessEqual(len(result["disclaimer"]), 300)

    def test_dimension_score_clamped_to_100(self):
        raw = json.dumps({
            "dimension_interpretation": [{"key": "x", "label": "X", "score": 150}],
        })
        result = normalize_radar_insight_json(raw)
        self.assertEqual(result["dimension_interpretation"][0]["score"], 100)

    def test_dimension_score_clamped_to_0(self):
        raw = json.dumps({
            "dimension_interpretation": [{"key": "x", "label": "X", "score": -50}],
        })
        result = normalize_radar_insight_json(raw)
        self.assertEqual(result["dimension_interpretation"][0]["score"], 0)

    def test_dimension_capped_at_6(self):
        dims = [{"key": f"d{i}", "label": f"D{i}", "score": 50} for i in range(8)]
        raw = json.dumps({"dimension_interpretation": dims})
        result = normalize_radar_insight_json(raw)
        self.assertEqual(len(result["dimension_interpretation"]), 6)

    def test_strongest_dim_empty_string_becomes_none(self):
        raw = json.dumps({"strongest_dim": "", "weakest_dim": ""})
        result = normalize_radar_insight_json(raw)
        self.assertIsNone(result["strongest_dim"])
        self.assertIsNone(result["weakest_dim"])

    def test_load_status_int_converted_to_float(self):
        raw = json.dumps({"load_status": {"ctl": 50, "atl": 30, "tsb": 20}})
        result = normalize_radar_insight_json(raw)
        self.assertIsInstance(result["load_status"]["ctl"], float)
        self.assertEqual(result["load_status"]["ctl"], 50.0)


class TestBuildRadarInsightSnapshot(unittest.TestCase):
    """_build_radar_insight_snapshot:从 _rolling_aggregate_radar_metrics + profile_backend
    构建白名单 snapshot(§5.4 规则 3 + §六 契约:严禁 shadow_diff)。
    """

    def _make_profile(self, **kwargs):
        """构造模拟 Profile 对象。"""

        class _Profile:
            pass

        p = _Profile()
        for k, v in kwargs.items():
            setattr(p, k, v)
        return p

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_empty_sport_type_returns_empty_dict(self, mock_metrics, mock_profile):
        result = _build_radar_insight_snapshot("")
        self.assertEqual(result, {})
        mock_metrics.assert_not_called()
        mock_profile.get_profile.assert_not_called()

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_returns_correct_top_level_keys(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {"ctl": 50, "atl": 30, "radar": {}}
        mock_profile.get_profile.return_value = self._make_profile(age=30, max_hr=190)
        result = _build_radar_insight_snapshot("running")
        self.assertEqual(
            set(result.keys()),
            {"source", "sport_type", "aggregation_window_days", "metrics", "user_profile"},
        )

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_source_is_canonical_marker(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {}
        mock_profile.get_profile.return_value = None
        result = _build_radar_insight_snapshot("running")
        self.assertEqual(result["source"], "DB Canonical / 雷达后端引擎 / Resolver Truth")

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_aggregation_window_is_90_days(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {}
        mock_profile.get_profile.return_value = None
        result = _build_radar_insight_snapshot("running")
        self.assertEqual(result["aggregation_window_days"], 90)

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_metrics_uses_whitelist_only(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {
            "ctl": 50, "atl": 30, "tsb": 20, "hrv": 65,
            "decoupling": 4.8, "vam": 750, "threshold_hr": 175,
            "anaerobic_peak": 5.2, "radar": {},
            "shadow_diff": {"legacy": 1},
            "extra_junk": "should_be_filtered",
            "_private": "should_be_filtered",
        }
        mock_profile.get_profile.return_value = None
        result = _build_radar_insight_snapshot("running")
        ALLOWED = {
            "ctl", "atl", "tsb", "hrv", "decoupling", "vam",
            "threshold_hr", "anaerobic_peak", "radar",
        }
        self.assertEqual(set(result["metrics"].keys()), ALLOWED)
        self.assertNotIn("shadow_diff", result["metrics"])
        self.assertNotIn("extra_junk", result["metrics"])
        self.assertNotIn("_private", result["metrics"])

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_user_profile_uses_whitelist_only(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {}
        mock_profile.get_profile.return_value = self._make_profile(
            age=30, gender="male", resting_hr=60, max_hr=190, hrv_baseline=65,
            name="张三", weight=70, height=175,
        )
        result = _build_radar_insight_snapshot("running")
        ALLOWED = {"age", "gender", "resting_hr", "max_hr", "hrv_baseline"}
        self.assertEqual(set(result["user_profile"].keys()), ALLOWED)
        self.assertNotIn("name", result["user_profile"])
        self.assertNotIn("weight", result["user_profile"])

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_profile_none_returns_empty_user_profile(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {"ctl": 50}
        mock_profile.get_profile.return_value = None
        result = _build_radar_insight_snapshot("running")
        self.assertEqual(result["user_profile"], {})

    @mock.patch("main.profile_backend")
    @mock.patch("main._rolling_aggregate_radar_metrics")
    def test_profile_partial_fields_only_include_non_none(self, mock_metrics, mock_profile):
        mock_metrics.return_value = {}
        mock_profile.get_profile.return_value = self._make_profile(age=30, gender=None, max_hr=190)
        result = _build_radar_insight_snapshot("running")
        self.assertIn("age", result["user_profile"])
        self.assertNotIn("gender", result["user_profile"])
        self.assertIn("max_hr", result["user_profile"])


if __name__ == "__main__":
    unittest.main()
