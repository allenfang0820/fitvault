from __future__ import annotations

import json
import os
import unittest
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CONTRACT_PATH = os.path.join(PROJECT_ROOT, "docs", "js_api_contract.json")
SUMMARY_PATH = os.path.join(PROJECT_ROOT, "docs", "fatigue_review_environment_factors_contract_summary.md")


FORBIDDEN_KEYS = (
    "points",
    "records",
    "raw_records",
    "track_points",
    "fit_records",
    "gpx_points",
    "shadow_diff",
    "shadow_diff_json",
    "diff",
)

ENVIRONMENT_FACTOR_KEYS = {
    "key",
    "category",
    "severity",
    "label",
    "comment",
    "basis",
    "confidence",
}


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestEnvironmentFactorsContractDocs(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(_read(CONTRACT_PATH))
        self.contract_text = json.dumps(self.contract, ensure_ascii=False)
        self.summary = _read(SUMMARY_PATH)

    def test_js_api_contract_registers_environment_factors_in_both_snapshots(self):
        self.assertIn("environment_factors", self.contract_text)
        self.assertIn("普通 get_fatigue_review(activity_id) snapshot 必须返回 environment_factors", self.contract_text)
        self.assertIn("__FATIGUE_REVIEW_INSIGHT__ compact snapshot 必须包含 environment_factors", self.contract_text)

    def test_js_api_contract_freezes_three_layer_semantics(self):
        for required in (
            "environment_context 是中性事实层",
            "context_tags 是压力/宽容标签层",
            "environment_factors 是后端生成",
            "前端和 AI 只能消费",
            "不得补算 canonical 环境事实",
        ):
            self.assertIn(required, self.contract_text)

    def test_js_api_contract_forbids_dom_and_raw_sources_for_environment_factors(self):
        for forbidden_source in (
            "DOM",
            "ECharts",
            "截图",
            "活动标题",
            "设备",
            "天气卡",
            "points",
            "records",
            "curves",
        ):
            self.assertIn(forbidden_source, self.contract_text)

    def test_contract_summary_records_followup_refresh_rules(self):
        for required in (
            "后续每个任务开始前，不必默认全文阅读所有原始合同文档",
            "最近刷新记录",
            "只有出现重要偏离时",
            "重新全文阅读相关原始契约文件",
        ):
            self.assertIn(required, self.summary)

    def test_contract_summary_keeps_environment_challenge_out_of_scope(self):
        self.assertIn("不重构、不迁移、不替代 `environment_challenge`", self.summary)
        self.assertIn("不修改 `classify_heat_stress()`", self.summary)


class TestEnvironmentFactorsSnapshotContract(unittest.TestCase):
    def test_regular_snapshot_contract_allows_environment_factors(self):
        snapshot = {
            "sport_type": "cycling",
            "summary": {},
            "metrics": {},
            "collapse_events": [],
            "fatigue_zones": [],
            "curves": {},
            "context_tags": {},
            "environment_context": {"has_weather": True, "temperature_c": 21.7, "humidity": 89.0},
            "environment_factors": [
                {
                    "key": "humidity",
                    "category": "weather",
                    "severity": "mild",
                    "label": "湿度偏高",
                    "comment": "温度本身不高,但湿度偏高,体感可能偏闷。",
                    "basis": {"temperature_c": 21.7, "humidity": 89.0, "wind_speed_kmh": 7.6},
                    "confidence": "medium",
                }
            ],
            "cycling_explanation_signals": {},
            "ai_insight": None,
            "advice": "",
            "disclaimer": "AI 生成仅供参考",
        }

        self.assertIn("environment_factors", snapshot)
        factor = snapshot["environment_factors"][0]
        self.assertEqual(set(factor), ENVIRONMENT_FACTOR_KEYS)
        self.assertNotIn("温度偏高", factor["comment"])
        encoded_basis = json.dumps(factor["basis"], ensure_ascii=False)
        for forbidden in FORBIDDEN_KEYS:
            self.assertNotIn('"' + forbidden + '"', encoded_basis)

    def test_compact_snapshot_contract_allows_environment_factors_and_strips_forbidden_keys(self):
        from main import _strip_fatigue_review_forbidden_keys

        compact_snapshot = _strip_fatigue_review_forbidden_keys({
            "activity_id": 42,
            "sport_type": "cycling",
            "summary": {"power_available": False},
            "metrics": {},
            "fatigue_zones": [],
            "collapse_events": [],
            "curves_summary": {"has_hr": True, "points": [{"bad": True}]},
            "context_tags": {"heat": "legacy", "track_points": [{"bad": True}]},
            "environment_context": {"has_weather": True, "temperature_c": 21.7},
            "environment_factors": [
                {
                    "key": "humidity",
                    "category": "weather",
                    "severity": "mild",
                    "label": "湿度偏高",
                    "comment": "温度本身不高,但湿度偏高。",
                    "basis": {"humidity": 89.0, "records": [{"bad": True}]},
                    "confidence": "medium",
                    "shadow_diff": {"bad": True},
                }
            ],
            "cycling_explanation_signals": {},
            "advice": "",
            "disclaimer": "AI 生成仅供参考",
        })

        encoded = json.dumps(compact_snapshot, ensure_ascii=False)

        self.assertIn("environment_factors", compact_snapshot)
        for forbidden in FORBIDDEN_KEYS:
            self.assertNotIn('"' + forbidden + '"', encoded)

    def test_environment_factor_shape_does_not_mix_three_layers(self):
        factor = {
            "key": "humidity",
            "category": "weather",
            "severity": "mild",
            "label": "湿度偏高",
            "comment": "温度不高,湿度偏高。",
            "basis": {"temperature_c": 21.7, "humidity": 89.0},
            "confidence": "medium",
        }
        self.assertEqual(set(factor), ENVIRONMENT_FACTOR_KEYS)
        self.assertNotIn("has_weather", factor)
        self.assertNotIn("weather_label", factor)
        self.assertNotIn("pressure_level", factor)
        self.assertNotIn("context_tags", factor)
        self.assertNotIn("environment_context", factor)

    def test_outdoor_swimming_contract_excludes_pool_swimming(self):
        summary = _read(SUMMARY_PATH)
        self.assertIn("只覆盖开放水域/户外游泳，不处理泳池游泳", summary)
        self.assertIn("无 `water_temperature_c` 不得推断水温压力", summary)


class TestEnvironmentFactorsBackendGeneration(unittest.TestCase):
    def test_running_mild_weather_does_not_create_pressure_factor(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 17.0, "humidity": 77, "weather_label": "阴"},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="running",
            environment_context=env,
        )

        self.assertEqual(factors, [])

    def test_running_high_humidity_under_25c_uses_humidity_not_heat(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 21.7, "humidity": 89, "wind_speed_kmh": 7.6},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="running",
            environment_context=env,
        )
        encoded = json.dumps(factors, ensure_ascii=False)

        self.assertTrue(factors)
        self.assertEqual(factors[0]["key"], "humidity")
        self.assertIn("湿度偏高", encoded)
        self.assertNotIn("温度偏高", encoded)
        self.assertNotIn("热应激", encoded)

    def test_cycling_high_humidity_under_25c_is_conservative(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 21.7, "humidity": 89, "wind_speed_kmh": 7.6},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="cycling",
            environment_context=env,
        )
        encoded = json.dumps(factors, ensure_ascii=False)

        self.assertTrue(factors)
        self.assertEqual(factors[0]["key"], "humidity")
        self.assertIn("体感偏闷", encoded)
        self.assertNotIn("温度偏高", encoded)

    def test_hiking_high_humidity_mentions_long_exposure(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 24.0, "humidity": 90},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="hiking",
            environment_context=env,
            row={"duration_sec": 7200},
        )
        encoded = json.dumps(factors, ensure_ascii=False)

        self.assertIn("长时间暴露", encoded)
        self.assertNotIn("配速", encoded)

    def test_mountaineering_cold_wind_uses_wind_chill_not_heat(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 5.0, "wind_speed_kmh": 28},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="mountaineering",
            environment_context=env,
        )
        encoded = json.dumps(factors, ensure_ascii=False)

        self.assertIn("风寒", encoded)
        self.assertNotIn("热应激", encoded)

    def test_open_water_swimming_without_water_temperature_does_not_infer_water_pressure(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 21.0, "humidity": 89},
            context_tags={},
        )
        factors = _build_fatigue_review_environment_factors(
            sport_type="open_water_swimming",
            environment_context=env,
            row={"sub_sport_type": "open_water"},
        )
        encoded = json.dumps(factors, ensure_ascii=False)

        self.assertTrue(factors)
        self.assertIn("缺少水温", encoded)
        self.assertNotIn("温度偏高", encoded)
        self.assertNotIn("水温偏高", encoded)

    def test_open_water_low_water_temperature_without_weather_is_preserved(self):
        from main import _build_fatigue_review_environment_factors

        factors = _build_fatigue_review_environment_factors(
            sport_type="open_water_swimming",
            environment_context={"has_weather": False},
            row={"sub_sport_type": "open_water", "water_temperature_c": 14.0},
        )

        self.assertEqual(len(factors), 1)
        self.assertEqual(factors[0]["key"], "water_temperature_low")
        self.assertEqual(factors[0]["basis"], {"water_temperature_c": 14.0})
        self.assertTrue(all(isinstance(value, (int, float, str, bool)) for value in factors[0]["basis"].values()))

    def test_open_water_without_weather_or_water_temperature_uses_low_confidence_missing_factor(self):
        from main import _build_fatigue_review_environment_factors

        factors = _build_fatigue_review_environment_factors(
            sport_type="open_water_swimming",
            environment_context={"has_weather": False},
            row={"sub_sport_type": "open_water"},
        )

        self.assertEqual(len(factors), 1)
        self.assertEqual(factors[0]["key"], "water_temperature_missing")
        self.assertEqual(factors[0]["confidence"], "low")
        self.assertIn("不推断水温压力", factors[0]["comment"])

    def test_pool_swimming_does_not_generate_environment_factors(self):
        from main import _build_fatigue_review_environment_factors

        self.assertEqual(
            _build_fatigue_review_environment_factors(
                sport_type="lap_swimming",
                environment_context={"has_weather": False},
                row={"sub_sport_type": "lap_swimming", "water_temperature_c": 14.0},
            ),
            [],
        )

    def test_invalid_weather_values_are_filtered_to_empty_factors(self):
        from main import (
            _build_fatigue_review_environment_context,
            _build_fatigue_review_environment_factors,
        )

        env = _build_fatigue_review_environment_context(
            weather={"temperature_c": 180, "humidity": 900, "wind_speed_kmh": -4},
            context_tags={},
        )

        self.assertFalse(env["has_weather"])
        self.assertEqual(
            _build_fatigue_review_environment_factors(
                sport_type="running",
                environment_context=env,
            ),
            [],
        )

    def test_empty_snapshot_and_compact_snapshot_include_environment_factors(self):
        from main import Api

        api = Api()
        empty = api._empty_fatigue_review_snapshot("running")
        self.assertEqual(empty["environment_factors"], [])

        api._fetch_activity_row = lambda activity_id: {"id": activity_id, "sport_type": "running"}
        api._build_fatigue_review_snapshot = lambda row: {
            **empty,
            "environment_factors": [
                {
                    "key": "humidity",
                    "category": "weather",
                    "severity": "mild",
                    "label": "湿度偏高",
                    "comment": "温度不高,湿度偏高。",
                    "basis": {"humidity": 89.0},
                    "confidence": "medium",
                }
            ],
        }
        compact = api._build_fatigue_review_insight_snapshot(7, "running")

        self.assertIn("environment_factors", compact)
        self.assertEqual(compact["environment_factors"][0]["key"], "humidity")


if __name__ == "__main__":
    unittest.main()
