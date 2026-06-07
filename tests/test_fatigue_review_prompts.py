"""
V7.3 LLM 提示词契约测试

契约依据 (fit-arch-contrac):
- §五 AI 边界 (DATA BOUNDARY / 4 维度 / sport 专项)
- §六 shadow_diff 隔离 (严禁在 prompt 数据段泄漏)
- §7.2 安全契约 (不触发真实 LLM 网络请求)

不修改生产代码,仅测试 build_fatigue_review_messages() 输出文本。
"""
from __future__ import annotations

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
    """LLM 必须输出 endurance / stability / bonk_risk / environment 4 维度。"""

    def test_four_dimensions_in_output_schema(self):
        from llm_backend import FATIGUE_REVIEW_OUTPUT_SCHEMA
        for dim in ["endurance", "stability", "bonk_risk", "environment"]:
            assert dim in FATIGUE_REVIEW_OUTPUT_SCHEMA, \
                f"FATIGUE_REVIEW_OUTPUT_SCHEMA 缺维度:{dim}"

    def test_four_dimensions_in_prompt(self, mock_snapshot):
        """系统 prompt 必须显式声明必须输出 4 维度。"""
        from llm_backend import build_fatigue_review_messages
        messages = build_fatigue_review_messages(mock_snapshot, "running", "跑步")
        system = messages[0]["content"]
        for dim in ["endurance", "stability", "bonk_risk", "environment"]:
            assert dim in system, f"system prompt 缺维度声明:{dim}"


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
        assert "功率" in system or "NP" in system
        assert "数据质量" in system or "功率" in system

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
        for dim in ["endurance", "stability", "bonk_risk", "environment"]:
            assert dim in FATIGUE_REVIEW_OUTPUT_SCHEMA, f"key_dimensions 缺:{dim}"


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
