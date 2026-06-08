"""
V9.4.4 Firstbeat TE 字段验证测试

依据:docs/training_effect_v1_contract.md v1.4 §6.5/§6.6/§6.7/§6.8

V9.4.0 错误用字段 219/218,fitparse 静默返回 None。
V9.4.4 正确字段:total_training_effect / total_anaerobic_training_effect
(均位于 session message,由 Garmin Firstbeat 私有算法产生,scale 0.1)

测试范围:
  1. fit_engine.py 静态扫描:必须读 total_training_effect(业务代码)
  2. fit_engine.py 静态扫描:不读错误的 219/218 字段
  3. Resolver:消费 aerobic_training_effect / anaerobic_training_effect 字段
  4. Resolver:双字段 None → 返回 None
  5. 端到端:四姑娘山/成都半马真实 FIT 字段值,经 Resolver 后与 Garmin Connect 一致
"""

from __future__ import annotations
import os
import re
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


def _read(rel: str) -> str:
    path = os.path.join(_PROJECT_ROOT, rel)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(text: str) -> str:
    """移除 Python 注释(docstring + 行内 #),只保留业务代码"""
    text = re.sub(r'"""[\s\S]*?"""', '', text)
    text = re.sub(r"'''[\s\S]*?'''", '', text)
    text = re.sub(r'#[^\n]*', '', text)
    return text


class TestV9_4_4FitEngineFirstbeat(unittest.TestCase):
    """V9.4.4:fit_engine.py 必须读 total_training_effect 业务字段"""

    def setUp(self):
        self.text = _read("fit_engine.py")
        self.cleaned = _strip_comments(self.text)

    def _session_info_body(self) -> str:
        idx = self.text.find("def _read_session_info(")
        self.assertGreater(idx, 0, "fit_engine.py 缺 _read_session_info")
        end = self.text.find("\n    @staticmethod", idx + 50)
        if end < 0:
            end = idx + 5000
        return self.text[idx:end]

    def _session_info_body_no_comments(self) -> str:
        return _strip_comments(self._session_info_body())

    def test_reads_total_training_effect(self):
        """V9.4.4:fit_engine 必须读 total_training_effect(有氧)"""
        body = self._session_info_body_no_comments()
        self.assertIn("total_training_effect", body,
                      "V9.4.4 FAIL: fit_engine 业务代码未读 total_training_effect")
        self.assertIn("total_anaerobic_training_effect", body,
                      "V9.4.4 FAIL: fit_engine 业务代码未读 total_anaerobic_training_effect")

    def test_does_not_read_wrong_219_218_fields(self):
        """V9.4.4:fit_engine 不能再读 V9.4.0 错误的 219/218 字段(input 端)"""
        body = self._session_info_body_no_comments()
        # V9.4.0 错误:用 get_value("training_effect_aerobic") / get_value("anaerobic_training_effect")
        # V9.4.4 正确:用 get_value("total_training_effect") / get_value("total_anaerobic_training_effect")
        self.assertNotIn('msg.get_value("training_effect_aerobic")', body,
                         "V9.4.4 FAIL: 仍在读错误的 training_effect_aerobic")
        self.assertNotIn('msg.get_value("anaerobic_training_effect")', body,
                         "V9.4.4 FAIL: 仍在读错误的 anaerobic_training_effect(应为 total_anaerobic_training_effect)")

    def test_maps_to_canonical_field_names(self):
        """V9.4.4:fit_engine 把 Firstbeat 字段映射到契约字段名 aerobic_training_effect"""
        body = self._session_info_body_no_comments()
        # 业务代码应包含: "aerobic_training_effect": msg.get_value("total_training_effect")
        self.assertIn("aerobic_training_effect", body)
        self.assertIn("total_training_effect", body)


class TestV9_4_4ResolverConsumes(unittest.TestCase):
    """V9.4.4:Resolver 消费契约字段名,无启发式估算"""

    def setUp(self):
        sys.path.insert(0, _PROJECT_ROOT)
        from metrics_resolver import build_training_effect
        self.build_training_effect = build_training_effect

    def test_no_heuristic_estimator(self):
        """V9.4.4:metrics_resolver 不应再含 _estimate_training_effect_from_hr"""
        text = _read("metrics_resolver.py")
        cleaned = _strip_comments(text)
        self.assertNotIn("_estimate_training_effect_from_hr", cleaned,
                         "V9.4.4 FAIL: V9.4.3 启发式估算函数未删除")

    def test_detail_api_whitelist_includes_te(self):
        """V9.4.4:修复:DETAIL_API_REQUIRED_COLUMNS 白名单必须包含 TE 字段
        否则详情 API 查不到 aerobic/anaerobic_training_effect,前端训练收益卡永远空态"""
        text = _read("main.py")
        # 找 DETAIL_API_REQUIRED_COLUMNS 元组定义
        idx = text.find("DETAIL_API_REQUIRED_COLUMNS")
        self.assertGreater(idx, 0, "main.py 缺 DETAIL_API_REQUIRED_COLUMNS")
        # 用下一个全局常量 API_CODE_EXTERNAL_SERVICE 作为结束标志(避开注释里的 ) 干扰)
        end = text.find("API_CODE_EXTERNAL_SERVICE", idx)
        if end < 0:
            end = idx + 5000
        body = text[idx:end]
        self.assertIn("aerobic_training_effect", body,
                      "V9.4.4 FAIL: DETAIL_API_REQUIRED_COLUMNS 缺 aerobic_training_effect,详情 API 取不到训练收益数据")
        self.assertIn("anaerobic_training_effect", body,
                      "V9.4.4 FAIL: DETAIL_API_REQUIRED_COLUMNS 缺 anaerobic_training_effect")

    def test_parse_fit_file_returns_te(self):
        """V9.4.4:修复回归:parse_fit_file 必须把 _read_session_info 写入的 TE 字段读出来
        之前 bug:_read_session_info 写 aerobic/anaerobic_training_effect,但 parse_fit_file
        还在用 total_training_effect 键名取,session_info.get() 静默返回 None"""
        import importlib
        try:
            from fit_engine import FITCoreEngine
        except Exception as e:
            self.skipTest(f"fit_engine 导入失败: {e}")
        fit_path = "/Users/fanglei/.fitvault/workspace/tracks/四姑娘山二峰登顶_240827288.fit"
        if not os.path.exists(fit_path):
            self.skipTest("FIT 文件不存在")
        result = FITCoreEngine.parse_fit_file(fit_path)
        basic = result.get("basic_info", {})
        self.assertEqual(basic.get("aerobic_training_effect"), 4.2,
                         "V9.4.4 FAIL: parse_fit_file 没把 session 的 TE 字段映射到 basic_info,前端训练收益卡空态")
        self.assertEqual(basic.get("anaerobic_training_effect"), 2.1)

    def test_parse_fit_activity_for_sync_returns_te(self):
        """V9.4.4:修复:_parse_fit_activity_for_sync 的 result dict 必须含 TE 字段
        之前 bug:_parse_fit_activity_for_sync 构造的 result dict 漏了 aerobic/anaerobic_training_effect,
        INSERT 写 None 进 DB,前端训练收益卡永远空态"""
        try:
            from main import _parse_fit_activity_for_sync
        except Exception as e:
            self.skipTest(f"main 导入失败: {e}")
        from pathlib import Path
        fit_path = "/Users/fanglei/.fitvault/workspace/tracks/四姑娘山二峰登顶_240827288.fit"
        if not os.path.exists(fit_path):
            self.skipTest("FIT 文件不存在")
        result = _parse_fit_activity_for_sync(Path(fit_path))
        self.assertEqual(result.get("aerobic_training_effect"), 4.2,
                         "V9.4.4 FAIL: _parse_fit_activity_for_sync result 缺 aerobic_training_effect")
        self.assertEqual(result.get("anaerobic_training_effect"), 2.1,
                         "V9.4.4 FAIL: _parse_fit_activity_for_sync result 缺 anaerobic_training_effect")

    def test_sichuan_real_fit_values(self):
        """V9.4.4:四姑娘山真实 FIT 字段 — total_training_effect=4.2, total_anaerobic=2.1
        验证:Resovler 消费后 4.2/2.1,完全对齐 Garmin Connect"""
        te = self.build_training_effect(
            {"aerobic_training_effect": 4.2, "anaerobic_training_effect": 2.1},
            "mountaineering",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertEqual(te["primary"]["score"], 4.2)
        self.assertEqual(te["secondary"]["score"], 2.1)

    def test_chengdu_real_fit_values(self):
        """V9.4.4:成都半马真实 FIT 字段 — total_training_effect=5.0, total_anaerobic=0.1"""
        te = self.build_training_effect(
            {"aerobic_training_effect": 5.0, "anaerobic_training_effect": 0.1},
            "running",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertEqual(te["primary"]["score"], 5.0)
        self.assertEqual(te["secondary"]["score"], 0.1)

    def test_both_none_returns_none_no_heuristic(self):
        """V9.4.4:双字段都 None + 任何 HR/zone 数据都不重算,直接返回 None"""
        te = self.build_training_effect(
            {
                "aerobic_training_effect": None,
                "anaerobic_training_effect": None,
                "avg_hr": 165,
                "max_hr": 188,
                "duration_sec": 7200,
                "hr_zone_distribution": '{"Z3": 100, "Z4": 200, "Z5": 50}',
            },
            "running",
        )
        self.assertIsNone(te,
                          "V9.4.4 FAIL: 有 HR/zone 数据时仍重算,违反不重算 Firstbeat 原则")


class TestV9_4_4EndToEndWithRealFit(unittest.TestCase):
    """V9.4.4:端到端用真实 FIT 文件 + Resolver 验证"""

    def setUp(self):
        sys.path.insert(0, _PROJECT_ROOT)
        from metrics_resolver import build_training_effect
        self.build_training_effect = build_training_effect
        import fitparse
        self.fitparse = fitparse

    def _read_fit_te(self, fit_path: str) -> tuple:
        """从真实 FIT 文件读 total_training_effect / total_anaerobic_training_effect"""
        fit = self.fitparse.FitFile(fit_path)
        for msg in fit.get_messages("session"):
            te = msg.get_value("total_training_effect")
            ate = msg.get_value("total_anaerobic_training_effect")
            return te, ate
        return None, None

    def test_sichuan_fit_file(self):
        """V9.4.4 端到端:四姑娘山 FIT 文件 → Resolver → 4.2/2.1"""
        fit_path = "/Users/fanglei/.fitvault/workspace/tracks/四姑娘山二峰登顶_240827288.fit"
        if not os.path.exists(fit_path):
            self.skipTest("FIT 文件不存在")
        te, ate = self._read_fit_te(fit_path)
        self.assertEqual(te, 4.2, "V9.4.4 FAIL: FIT 文件实际 TE != Garmin Connect 4.2")
        self.assertEqual(ate, 2.1, "V9.4.4 FAIL: FIT 文件实际 anaerobic TE != Garmin Connect 2.1")
        # Resolver 消费后必须与 Garmin 一致
        result = self.build_training_effect(
            {"aerobic_training_effect": te, "anaerobic_training_effect": ate},
            "mountaineering",
        )
        self.assertEqual(result["primary"]["score"], 4.2)
        self.assertEqual(result["secondary"]["score"], 2.1)

    def test_chengdu_fit_file(self):
        """V9.4.4 端到端:成都半马 FIT 文件 → Resolver → 5.0/0.1"""
        fit_path = "/Users/fanglei/.fitvault/workspace/tracks/2023成都马拉松半程_282801361.fit"
        if not os.path.exists(fit_path):
            self.skipTest("FIT 文件不存在")
        te, ate = self._read_fit_te(fit_path)
        self.assertEqual(te, 5.0, "V9.4.4 FAIL: FIT 文件实际 TE != Garmin Connect 5.0")
        self.assertEqual(ate, 0.1, "V9.4.4 FAIL: FIT 文件实际 anaerobic TE != Garmin Connect 0.1")
        result = self.build_training_effect(
            {"aerobic_training_effect": te, "anaerobic_training_effect": ate},
            "running",
        )
        self.assertEqual(result["primary"]["score"], 5.0)
        self.assertEqual(result["secondary"]["score"], 0.1)


if __name__ == "__main__":
    unittest.main()
