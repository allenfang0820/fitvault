"""
V7.3 LLM 提示词契约测试

契约依据 (fit-arch-contrac):
- §五 AI 边界 (DATA BOUNDARY / 4 维度 / sport 专项)
- §六 shadow_diff 隔离 (严禁在 prompt 数据段泄漏)
- §7.2 安全契约 (不触发真实 LLM 网络请求)

不修改生产代码,仅测试 build_fatigue_review_messages() 输出文本。
"""
from __future__ import annotations

import json
import os
import sys
import pytest

# 把项目根加到 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# === Fixture: 模拟复盘 snapshot(§2.2 source_type='mock' 标记)===
@pytest.fixture
def mock_snapshot():
    return {
        "sport_type": "running",
        "metrics": {
            "hr_drift":   {"pct": 6.2, "level": "warn"},
            "decoupling": {"pct": 6.2, "level": "warn"},
            "bonk_risk":  {"is_at_risk": True, "confidence": "medium"},
        },
        "collapse_events": [
            {"event_id": "ce_00", "type": "BONK_WARNING", "trigger_km": 12.5,
             "value_y": 0.043, "description": "效率断崖"},
        ],
        "curves": {
            "efficiency": [0.05, 0.052, 0.048, 0.043, 0.038, 0.032, 0.025],
            "gap":        [3.2, 3.3, 3.1, 2.9, 2.6, 2.3, 2.0],
            "grade":      [0.5, 1.2, 2.8, 4.5, 5.6, 6.2, 7.1],
            "hr":         [142, 148, 155, 161, 168, 172, 175],
            "speed":      [3.1, 3.2, 3.0, 2.8, 2.5, 2.2, 1.9],
        },
        "context_tags": {
            "热应激 (Heat Stress)": "High (28.5°C) - 会导致散热受阻...",
        },
        "environment_context": {
            "has_weather": True,
            "weather_label": "阴",
            "temperature_c": 17.1,
            "humidity": 77,
            "wind_speed_kmh": 0.8,
            "pressure_level": "none",
            "summary": "天气阴，17.1°C，湿度77%，风速0.8km/h；未识别到明显外部环境压力。",
        },
        "ai_insight": None,
        "advice": "下次类似路线...",
        "disclaimer": "AI 生成仅供参考...",
    }


def _extract_payload(system: str) -> str:
    """从 system 文本中提取【权威快照】 JSON 段(payload 实际数据)。"""
    import re
    m = re.search(r"```json\s*\n(.*?)\n```", system, re.DOTALL)
    return m.group(1) if m else ""


# === 测试 1: DATA BOUNDARY 强约束(§五)===
class TestDataBoundaryConstraint:
    """LLM prompt 必须显式声明 DATA BOUNDARY 强约束。"""

    def test_data_boundary_keywords_present(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "数据边界" in system or "DATA BOUNDARY" in system
        assert "权威" in system or "canonical" in system
        assert "禁止" in system or "MUST NOT" in system

    def test_no_recalculation_clause(self, mock_snapshot):
        """§五 强约束:禁止重新计算距离/时间/心率/爬升等。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        # 生产代码在 MUST NOT 段合并成一行,这里拆成独立关键词
        forbidden_keywords = ["重新计算", "心率", "爬升",
                             "有氧解耦", "Bonk", "per-point 曲线"]
        for kw in forbidden_keywords:
            assert kw in system, f"DATA BOUNDARY 缺约束关键词:{kw}"

    def test_canonical_writeback_forbidden(self, mock_snapshot):
        """§5.6.2 规则 6:严禁写回 canonical 指标或字段建议。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        # 生产代码在 MUST NOT 段合并成一行,这里拆成独立关键词
        forbidden_writes = ["写回", "canonical"]
        for w in forbidden_writes:
            assert w in system, f"§5.6.2 规则 6 缺约束:禁止{w}"


# === 测试 2: 4 维度强制(§5.4)===
class TestFourDimensionsMandatory:
    """LLM 必须输出 P8.3 新四维。"""

    NEW_DIMS = ["overall_stability", "fatigue_progression", "risk_triggers", "context_impact"]
    OLD_DIMS = ["endurance", "stability", "bonk_risk", "environment"]

    def test_four_dimensions_in_output_schema(self):
        from llm_backend import FATIGUE_REVIEW_OUTPUT_SCHEMA
        for dim in self.NEW_DIMS:
            assert dim in FATIGUE_REVIEW_OUTPUT_SCHEMA, \
                f"FATIGUE_REVIEW_OUTPUT_SCHEMA 缺维度:{dim}"
        assert "endurance|stability|bonk_risk|environment" not in FATIGUE_REVIEW_OUTPUT_SCHEMA
        for old_label in ("耐力|心肺稳定|撞墙风险|环境压力",):
            assert old_label not in FATIGUE_REVIEW_OUTPUT_SCHEMA, \
                f"FATIGUE_REVIEW_OUTPUT_SCHEMA 不应继续要求旧维度:{old_label}"

    def test_four_dimensions_in_prompt(self, mock_snapshot):
        """系统 prompt 必须显式声明必须输出 4 维度。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        for dim in self.NEW_DIMS:
            assert dim in system, f"system prompt 缺维度声明:{dim}"
        assert "endurance / stability / bonk_risk / environment" not in system
        for label in ["全程稳定性", "疲劳阶段", "风险触发", "外部影响"]:
            assert label in system, f"system prompt 缺中文维度:{label}"


# === 测试 3: sport 专项约束(§五)===
class TestSportSpecificConstraints:
    """不同 sport_type 触发不同专项约束。"""

    @pytest.mark.parametrize("sport_type,sport_cn,expected_keyword", [
        ("running",          "跑步", "running"),
        ("trail_running",    "越野跑", "running"),
        ("treadmill_running", "跑步机", "running"),
        ("hiking",           "徒步", "general"),
        ("mountaineering",   "登山", "general"),
        ("cycling",          "骑行", "cycling"),
        ("road_cycling",     "公路骑行", "cycling"),
        ("mountain_biking",  "山地车", "cycling"),
        ("swimming",         "游泳", "swimming"),
        ("lap_swimming",     "泳池", "swimming"),
    ])
    def test_sport_mode_mapping(self, mock_snapshot, sport_type, sport_cn, expected_keyword):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, sport_type, sport_cn)
        system = messages[0]["content"]
        assert expected_keyword in system, \
            f"sport_type={sport_type} 应对应 {expected_keyword} 专项约束"

    def test_running_specific_decoupling(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "解耦" in system or "decoupling" in system

    def test_cycling_specific_power(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for keyword in ["功率", "NP", "avg_power", "normalized_power", "power_data_quality", "avg_cadence", "踏频"]:
            assert keyword in system, f"cycling prompt 缺少关键词:{keyword}"
        for quality in ["missing", "insufficient_points", "invalid_values", "length_mismatch", "unavailable"]:
            assert quality in system, f"cycling prompt 缺少降级枚举:{quality}"
        assert "必须依赖功率(NP)评估" not in system
        assert "配速" not in system or "不得把\"配速\"" in system

    def test_cycling_specific_bounded_degradation(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for phrase in [
            "无功率或功率质量不足",
            "稳定性判断受限",
            "不能输出完整功率复盘",
            "不能写\"功率稳定\"",
            "踏频缺失或质量不足",
            "无法评估踩踏组织",
        ]:
            assert phrase in system, f"cycling prompt 缺少边界语句:{phrase}"

    def test_cycling_specific_running_words_are_not_core_frame(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for keyword in ["配速", "步频", "跑姿", "触地", "步幅", "跑步节奏", "恢复跑", "跑步赛道"]:
            assert keyword in system, f"cycling prompt 应明确禁止跑步化表达:{keyword}"
        assert "不得把\"配速\"" in system or "骑行不得把\"配速\"" in system
        assert "overall_stability / 全程稳定性:按运动类型解释整体稳定性" in system

    def test_swimming_specific_endurance(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "swimming", "游泳")
        system = messages[0]["content"]
        assert "耐力" in system or "持续性" in system


# === 测试 4: shadow_diff 隔离(§六 强约束必须存在)===
class TestShadowDiffClauseInPrompt:
    """§六 强约束:LLM prompt 必须显式声明严禁使用 shadow_diff 字段。"""

    def test_shadow_diff_forbidden_clause_present(self, mock_snapshot):
        """prompt 必须在"强行约束"段显式点名 shadow_diff 等 debug 字段。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        # 生产代码在 MUST NOT 段会点名这些字段
        assert "shadow_diff" in system, "§六 强约束:必须显式禁止 shadow_diff"
        assert "shadow_diff_json" in system, "§六 强约束:必须显式禁止 shadow_diff_json"
        assert "diff" in system, "§六 强约束:必须显式禁止 diff"

    def test_payload_segment_does_not_leak_clean_snapshot_data(self, mock_snapshot):
        """干净 mock_snapshot(无 shadow_diff)产出的 prompt 数据段不含 shadow_diff。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        payload = _extract_payload(system)
        # 干净 snapshot 序列化结果不应含 shadow_diff
        assert "shadow_diff" not in payload, \
            "§六 违规:干净 snapshot 不应在 payload 中出现 shadow_diff"


# === 测试 5: snapshot 数据透传 ===
class TestSnapshotDataPassthrough:
    """snapshot 中的关键数字必须出现在 prompt 文本中(§2.1 全链路可追溯)。"""

    def test_metrics_values_in_prompt(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "6.2" in system, "decoupling pct=6.2 必须出现在 prompt"
        assert "12.5" in system or "12.50" in system, "trigger_km=12.5 必须出现"
        assert "0.043" in system or "0.04" in system, "value_y=0.043 必须出现"

    def test_context_tags_in_prompt(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "热应激" in system
        assert "28.5" in system

    def test_environment_context_prevents_false_missing_environment_claim(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "environment_context" in system
        assert "已有天气快照" in system
        assert "未识别到明显外部环境压力" in system
        assert "不得写\"未提供环境标签数据\"" in system

    def test_collapse_event_descriptions_in_prompt(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        assert "效率断崖" in system


# === 测试 6: schema 输出契约 ===
class TestOutputSchemaContract:
    """FATIGUE_REVIEW_OUTPUT_SCHEMA 必须含 5 段。"""

    def test_schema_has_five_segments(self):
        from llm_backend import FATIGUE_REVIEW_OUTPUT_SCHEMA
        for seg in ["summary", "key_dimensions", "event_interpretation",
                    "training_advice", "disclaimer"]:
            assert seg in FATIGUE_REVIEW_OUTPUT_SCHEMA, f"schema 缺段:{seg}"

    def test_schema_key_dimensions_has_four_keys(self):
        from llm_backend import FATIGUE_REVIEW_OUTPUT_SCHEMA
        for dim in ["overall_stability", "fatigue_progression", "risk_triggers", "context_impact"]:
            assert dim in FATIGUE_REVIEW_OUTPUT_SCHEMA, f"key_dimensions 缺:{dim}"


class TestFatigueReviewDimensionNormalizer:
    """P8.3:normalizer 必须把 AI 维度统一为新四维固定顺序。"""

    ORDER = ["overall_stability", "fatigue_progression", "risk_triggers", "context_impact"]

    def test_normalizer_keeps_new_dimensions_in_order(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "测试",
            "key_dimensions": [
                {"key": "risk_triggers", "label": "风险触发", "level": "warn", "comment": "风险线索"},
                {"key": "overall_stability", "label": "全程稳定性", "level": "good", "comment": "整体稳定"},
                {"key": "context_impact", "label": "外部影响", "level": "unknown", "comment": "环境有限"},
                {"key": "fatigue_progression", "label": "疲劳阶段", "level": "bad", "comment": "后段疲劳"},
            ],
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        assert [d["key"] for d in result["key_dimensions"]] == self.ORDER
        assert [d["label"] for d in result["key_dimensions"]] == ["全程稳定性", "疲劳阶段", "风险触发", "外部影响"]

    def test_normalizer_maps_legacy_keys_to_new_dimensions(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "测试",
            "key_dimensions": [
                {"key": "endurance", "label": "耐力", "level": "good", "comment": "旧耐力"},
                {"key": "stability", "label": "心肺稳定", "level": "warn", "comment": "旧稳定"},
                {"key": "bonk_risk", "label": "撞墙风险", "level": "bad", "comment": "旧风险"},
                {"key": "environment", "label": "环境压力", "level": "excellent", "comment": "旧环境"},
            ],
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        dims = result["key_dimensions"]
        assert [d["key"] for d in dims] == self.ORDER
        assert [d["label"] for d in dims] == ["全程稳定性", "疲劳阶段", "风险触发", "外部影响"]
        assert dims[0]["comment"] == "旧稳定"
        assert dims[1]["comment"] == "旧耐力"
        assert dims[2]["comment"] == "旧风险"
        assert dims[3]["comment"] == "旧环境"

    def test_normalizer_fills_missing_dimensions_and_dedupes(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "测试",
            "key_dimensions": [
                {"key": "overall_stability", "level": "good", "comment": "保留第一条"},
                {"key": "overall_stability", "level": "bad", "comment": "重复忽略"},
            ],
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        dims = result["key_dimensions"]
        assert len(dims) == 4
        assert dims[0]["comment"] == "保留第一条"
        assert dims[1]["level"] == "unknown"
        assert dims[1]["comment"] == "暂无足够数据"

    def test_normalizer_invalid_level_downgrades_to_unknown(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "测试",
            "key_dimensions": [
                {"key": "risk_triggers", "level": "great", "comment": "非法 level"},
            ],
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        assert result["key_dimensions"][2]["level"] == "unknown"

    def test_normalizer_localizes_user_visible_ai_text(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "Bonk risk is good but load ratio is caution",
            "key_dimensions": [
                {
                    "key": "risk_triggers",
                    "level": "warn",
                    "comment": "Bonk风险 low, collapse_events 0, 7/42 is caution",
                },
                {
                    "key": "overall_stability",
                    "level": "good",
                    "comment": "efficiency declining, CV high",
                },
            ],
            "event_interpretation": "collapse event not found",
            "training_advice": "Keep Z3 short and avoid high HR",
            "disclaimer": "AI generated from snapshot",
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        visible = " ".join([
            result["summary"],
            result["event_interpretation"],
            result["training_advice"],
            result["disclaimer"],
            *[d["comment"] for d in result["key_dimensions"]],
        ])
        for forbidden in ("Bonk", "good", "warn", "declining", "caution", "collapse_events"):
            assert forbidden not in visible
        for expected in ("能量断档", "良好", "需谨慎", "下降", "状态下滑事件"):
            assert expected in visible

    def test_normalizer_localizes_event_codes_and_metric_abbreviations(self):
        from llm_backend import normalize_fatigue_review_json
        raw = {
            "summary": "BONK_WARNING risk window",
            "key_dimensions": [
                {
                    "key": "risk_triggers",
                    "level": "warn",
                    "comment": "EI dropped, HRR high, warning",
                },
            ],
            "event_interpretation": "唯一事件为 BONK_WARNING, EI 下降且 HRR 偏高",
            "training_advice": "Reduce risk window",
            "disclaimer": "snapshot",
        }
        result = normalize_fatigue_review_json(json.dumps(raw, ensure_ascii=False))
        visible = " ".join([
            result["summary"],
            result["event_interpretation"],
            result["training_advice"],
            *[d["comment"] for d in result["key_dimensions"]],
        ])
        for text in ("能量断档风险线索", "效率指标", "心率储备占用", "风险区间"):
            assert text in visible
        for forbidden in ("BONK_WARNING", "EI", "HRR", "risk window"):
            assert forbidden not in visible

    def test_prompt_requires_localized_user_visible_text(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        prompt = "\n".join(m["content"] for m in build_fatigue_review_messages(mock_snapshot, "running", "跑步"))
        assert "用户可见文本不得直接输出 good / warn / bad / unknown / declining / caution / Bonk / collapse" in prompt
        assert "良好 / 需关注 / 风险较高 / 数据不足 / 下降 / 需谨慎 / 能量断档 / 状态下滑" in prompt


# === 测试 7: message 数量 + role ===
class TestMessagesStructure:
    """messages 结构必须符合 OpenAI chat_completions 格式。"""

    def test_messages_is_list(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        assert isinstance(messages, list)
        assert len(messages) == 2, "messages 必须是 [system, user] 2 段"

    def test_system_role_present(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_user_message_brief(self, mock_snapshot):
        """user 消息应当简洁(避免 prompt injection / 前端拼接)。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        user = messages[1]["content"]
        assert len(user) < 500, f"user 消息过长({len(user)}),可能含冗余"
        assert "JSON" in user or "json" in user

    def test_cycling_prompt_mentions_summary_fields_and_curve_summary(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for keyword in [
            "summary.power_data_quality",
            "summary.normalized_power",
            "summary.avg_power",
            "summary.power_points_count",
            "summary.cadence_data_quality",
            "summary.avg_cadence",
            "curves_summary.has_power",
            "curves_summary.has_cadence",
        ]:
            assert keyword in system, f"cycling prompt 缺少字段约束:{keyword}"

    def test_cycling_prompt_bans_cycle_specific_metrics_not_present(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for keyword in ["VI", "FTP", "IF", "TSS", "W/kg", "左右平衡", "扭矩", "齿比"]:
            assert keyword in system, f"cycling prompt 应明确禁止/不计算:{keyword}"

    def test_cycling_prompt_uses_backend_explanation_signals_only(self, mock_snapshot):
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "cycling", "骑行")
        system = messages[0]["content"]
        for keyword in [
            "cycling_explanation_signals",
            "唯一依据",
            "intensity_signal",
            "aerobic_drift_signal",
            "power_retention_signal",
            "pacing_signal",
            "cadence_signal",
            "不得从 summary / metrics / curves_summary / DOM / ECharts / points 自行构造",
            "status=unavailable 或 partial",
            "无 FTP 不得编造 FTP、IF、TSS、训练负荷",
            "无功率不得输出功率强度、后程功率保持或 pacing 结论",
            "无心率不得输出有氧漂移结论",
            "不得编造补给、天气、设备、路况",
        ]:
            assert keyword in system, f"cycling prompt 缺少 P6 AI 输入约束:{keyword}"


# === 测试 8: empty / error 态不调 LLM ===
class TestLLMNotCalledOnEmpty:
    """empty / error 态下,后端不调用 LLM(§5.6.2 规则 6 严禁浪费 token)。"""

    def test_empty_fatigue_review_structure(self):
        """empty_fatigue_review_insight 错误时,前端不调 call_llm 即可。"""
        from llm_backend import empty_fatigue_review_insight
        err = empty_fatigue_review_insight("test")
        assert err.get("error") == "test"
        assert err.get("summary")
        assert err.get("disclaimer")
