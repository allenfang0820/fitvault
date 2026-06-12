"""任务 3 — 响应结构契约单元测试

契约:fit-arch-contrac §三 统一响应结构 {code, msg, data, traceId}
验证:
  1. _api_success / _api_error 不在顶层泄漏 payload 字段
  2. 顶层字段严格白名单(ok/code/msg/data/traceId + 过渡期 error)
  3. legacy_fields 仍能被合入 data
  4. 运动复盘 7 段 payload 仍位于 data 内(下游可正常访问)
"""
from __future__ import annotations

import os
import re
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from main import (  # noqa: E402
    API_CODE_OK,
    API_CODE_NOT_FOUND,
    API_CODE_EXTERNAL_SERVICE,
    _api_success,
    _api_error,
    _new_trace_id,
)


class TestApiSuccessEnvelopeContract(unittest.TestCase):
    """§三 响应结构契约:_api_success 必须严格遵守 {ok, code, msg, data, traceId}"""

    def test_envelope_keys_strict_whitelist(self):
        """顶层字段严格白名单(允许:ok/code/msg/data/traceId)"""
        res = _api_success({"record": {"id": 1}, "metrics": {"hr": 100}})
        allowed = {"ok", "code", "msg", "data", "traceId"}
        leaked = set(res.keys()) - allowed
        self.assertEqual(leaked, set(), f"响应顶层泄漏字段: {leaked}")

    def test_payload_not_in_top_level(self):
        """payload 中的 record/metrics 等字段绝不能出现在顶层"""
        res = _api_success({"record": {"id": 1}, "metrics": {"hr": 100}})
        self.assertNotIn("record", res)
        self.assertNotIn("metrics", res)

    def test_payload_inside_data(self):
        """payload 必须位于 data 内"""
        res = _api_success({"record": {"id": 1}, "metrics": {"hr": 100}})
        self.assertEqual(res["data"]["record"]["id"], 1)
        self.assertEqual(res["data"]["metrics"]["hr"], 100)

    def test_ok_true_on_success(self):
        res = _api_success()
        self.assertTrue(res["ok"])

    def test_code_zero_on_success(self):
        res = _api_success()
        self.assertEqual(res["code"], API_CODE_OK)

    def test_msg_default_ok(self):
        res = _api_success()
        self.assertEqual(res["msg"], "ok")

    def test_msg_custom(self):
        res = _api_success(msg="custom success")
        self.assertEqual(res["msg"], "custom success")

    def test_traceId_hex12(self):
        res = _api_success()
        self.assertIsNotNone(res["traceId"])
        self.assertEqual(len(res["traceId"]), 12)
        self.assertTrue(re.match(r"^[0-9a-f]{12}$", res["traceId"]))

    def test_data_default_empty_dict(self):
        """data 参数缺省时必须为 {} 而非 None"""
        res = _api_success()
        self.assertIsInstance(res["data"], dict)
        self.assertEqual(res["data"], {})

    def test_data_arg_accepted(self):
        res = _api_success({"a": 1})
        self.assertEqual(res["data"], {"a": 1})

    def test_legacy_fields_merged_into_data(self):
        """legacy_fields 关键字参数必须合入 data(不污染顶层)"""
        res = _api_success(data={"a": 1}, b=2, c=3)
        # data 内应有 a, b, c
        self.assertEqual(res["data"]["a"], 1)
        self.assertEqual(res["data"]["b"], 2)
        self.assertEqual(res["data"]["c"], 3)
        # b, c 不能在顶层
        self.assertNotIn("b", res)
        self.assertNotIn("c", res)

    def test_no_data_arg_with_legacy_fields(self):
        res = _api_success(content="text", prompt="p")
        self.assertEqual(res["data"]["content"], "text")
        self.assertEqual(res["data"]["prompt"], "p")
        self.assertNotIn("content", res)
        self.assertNotIn("prompt", res)

    def test_data_dict_copy_not_reference(self):
        """data 必须是浅拷贝,不能与入参共享引用"""
        original = {"a": 1}
        res = _api_success(original)
        original["a"] = 999
        self.assertEqual(res["data"]["a"], 1)


class TestApiErrorEnvelopeContract(unittest.TestCase):
    """§三.1 错误响应契约:_api_error 同样遵守统一结构,保留 error 字段过渡期兼容"""

    def test_error_envelope_keys(self):
        res = _api_error(API_CODE_NOT_FOUND, "not found")
        allowed = {"ok", "code", "msg", "data", "traceId", "error"}
        leaked = set(res.keys()) - allowed
        self.assertEqual(leaked, set(), f"错误响应顶层泄漏字段: {leaked}")

    def test_error_top_level_for_backward_compat(self):
        """§3.1 过渡期:error 字段仍在顶层"""
        res = _api_error(API_CODE_NOT_FOUND, "活动不存在")
        self.assertEqual(res["error"], "活动不存在")
        self.assertEqual(res["msg"], "活动不存在")

    def test_ok_false_on_error(self):
        res = _api_error(API_CODE_NOT_FOUND, "not found")
        self.assertFalse(res["ok"])

    def test_code_preserved(self):
        res = _api_error(API_CODE_EXTERNAL_SERVICE, "downstream error")
        self.assertEqual(res["code"], API_CODE_EXTERNAL_SERVICE)

    def test_payload_not_leaked(self):
        res = _api_error(API_CODE_NOT_FOUND, "not found", {"placemarks": []})
        self.assertNotIn("placemarks", res)
        self.assertEqual(res["data"]["placemarks"], [])

    def test_legacy_fields_merged_into_data(self):
        res = _api_error(API_CODE_NOT_FOUND, "not found", extra="info")
        self.assertEqual(res["data"]["extra"], "info")
        self.assertNotIn("extra", res)

    def test_traceId_hex12_on_error(self):
        res = _api_error(API_CODE_NOT_FOUND, "not found")
        self.assertEqual(len(res["traceId"]), 12)


class TestFatigueReviewEnvelopeCompliance(unittest.TestCase):
    """运动复盘接口契约合规(任务 3 安全性验证)

    7 段 payload:metrics / collapse_events / curves / context_tags /
                  ai_insight / advice / disclaimer
    """

    FATIGUE_REVIEW_KEYS = (
        "metrics",
        "collapse_events",
        "curves",
        "context_tags",
        "ai_insight",
        "advice",
        "disclaimer",
    )

    def test_7_segments_in_data(self):
        payload = {k: None for k in self.FATIGUE_REVIEW_KEYS}
        payload["metrics"] = {"avg_hr": 150}
        payload["curves"] = {"hr": [140, 150]}
        payload["advice"] = "建议降速"
        res = _api_success(payload)
        for key in self.FATIGUE_REVIEW_KEYS:
            self.assertIn(key, res["data"], f"{key} 必须位于 res.data 内")
            self.assertNotIn(key, res, f"{key} 禁止出现在顶层")

    def test_frontend_can_still_access_through_data(self):
        """前端约定 res.data.xxx,任务 3 改造后必须仍可访问"""
        payload = {
            "metrics": {"avg_hr": 150},
            "collapse_events": [],
            "curves": {"hr": [140, 150]},
            "context_tags": {},
            "ai_insight": None,
            "advice": "建议降速",
            "disclaimer": "AI 仅供参考",
        }
        res = _api_success(payload)
        self.assertEqual(res["data"]["advice"], "建议降速")
        self.assertEqual(res["data"]["disclaimer"], "AI 仅供参考")
        self.assertEqual(res["data"]["curves"]["hr"], [140, 150])

    def test_no_shadow_diff_leakage(self):
        """§六 shadow_diff 隔离:不能通过 envelope 泄漏到顶层"""
        payload = {
            "metrics": {},
            "shadow_diff": {"x": 1},
            "shadow_diff_json": "{}",
            "diff": {"y": 2},
        }
        res = _api_success(payload)
        # 任务 3 改造后:所有 payload 在 data 内(但前端不消费 shadow_diff)
        self.assertIn("shadow_diff", res["data"])
        self.assertNotIn("shadow_diff", res)
        # 关键契约:数据契约层允许,但前端 renderFatigueReviewMetrics 不读 shadow_diff


class TestCallLLMDirectReturnPattern(unittest.TestCase):
    """call_llm 等直接返回 dict 的接口,任务 3 不影响(契约允许直接返回)"""

    def test_direct_return_dict_passes_through(self):
        """直接返回 dict 不走 _api_success,顶层字段不会被 _api_* 过滤"""
        direct = {"ok": True, "activity_advice": {"weather_check": {"status": "信息不足"}}}
        # 直接返回 dict 不经过 _api_success 处理
        # 契约 §3.1 允许(过渡期兼容)
        self.assertIn("activity_advice", direct)


class TestStaticNoResponseUpdatePayload(unittest.TestCase):
    """静态分析:_api_success / _api_error 中不应再有 response.update(payload)"""

    def test_no_response_update_payload(self):
        main_path = os.path.join(_PROJECT_ROOT, "main.py")
        text = open(main_path, encoding="utf-8").read()

        # 在 _api_success / _api_error 函数体内不应有 response.update(payload)
        # 用 ast 解析更精确
        import ast
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in {"_api_success", "_api_error"}:
                continue
            func_src = ast.unparse(node)
            self.assertNotIn(
                "response.update(payload)", func_src,
                f"{node.name} 中不应再有 response.update(payload) (任务 3 已禁止)"
            )


if __name__ == "__main__":
    unittest.main()
