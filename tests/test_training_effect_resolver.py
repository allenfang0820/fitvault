"""
V9.4.0 训练收益(Training Effect)Resolver 单元测试

依据:docs/training_effect_v1_contract.md
- §3 全局 6 等级标尺
- §4 运动 × 维度 × 标题 映射(8 运动)
- §5 运动 × 维度 × 6 TE 范围 完整映射(8 运动 × 2 维度 × 6 范围 = 96 单元)
- §6.5 FIT 字段映射(aerobic/anaerobic)
- §6.6 Resolver 极简实现契约

测试范围:
  - 8 运动可解析
  - 6 等级边界(0.0 / 1.0 / 2.0 / 3.0 / 4.0 / 4.5)
  - global_level = max(primary, secondary)
  - 老 FIT 文件(双字段都缺)→ 返回 None
  - 单字段(只 aerobic)→ 不返回 None,secondary 走 0.0 fallback
  - 未知 sport_type 走 running fallback
"""

from __future__ import annotations
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from metrics_resolver import (
    build_training_effect,
    _TE_SPORT_MATRIX,
    _TE_SPORT_TITLE,
    _TE_LEVEL_IDS,
    _te_to_index,
    _TE_LEVEL_ORDER,
)


class TestV9_4SportCoverage(unittest.TestCase):
    """§4 字段映射 8 运动全覆盖"""

    def test_8_sports_in_matrix(self):
        self.assertEqual(len(_TE_SPORT_MATRIX), 8,
                         "V9.4 FAIL: _TE_SPORT_MATRIX 必须 8 运动")

    def test_8_sports_in_title_map(self):
        self.assertEqual(len(_TE_SPORT_TITLE), 8,
                         "V9.4 FAIL: _TE_SPORT_TITLE 必须 8 运动")

    def test_required_8_sports(self):
        required = ["running", "trail_running", "hiking",
                    "cycling", "indoor_cycling", "swimming",
                    "strength", "hiit"]
        for s in required:
            self.assertIn(s, _TE_SPORT_MATRIX, f"V9.4 FAIL: 缺 {s}")
            self.assertIn(s, _TE_SPORT_TITLE, f"V9.4 FAIL: 缺 {s}")


class TestV9_4TitleMapping(unittest.TestCase):
    """§4 用户原标题逐字保留"""

    def test_titles_match_user_design(self):
        """§4 逐字对照:primary_title / secondary_title"""
        expected = {
            "running":         ("有氧收益", "速度刺激"),
            "trail_running":   ("耐力收益", "高强度刺激"),
            "hiking":          ("耐力收益", "高强度刺激"),
            "cycling":         ("耐力输出", "冲刺刺激"),
            "indoor_cycling":  ("有氧输出", "功率刺激"),
            "swimming":        ("耐力收益", "速度刺激"),
            "strength":        ("肌肉刺激", "爆发负荷"),
            "hiit":            ("心肺刺激", "爆发刺激"),
        }
        for sport, (p, s) in expected.items():
            self.assertEqual(_TE_SPORT_TITLE[sport], (p, s),
                             f"V9.4 FAIL: {sport} 标题不符用户原 §四")

    def test_strength_uses_unique_language(self):
        """§5.7:力量训练必须用「肌肉刺激 / 爆发负荷」(不叫有氧/无氧)"""
        self.assertEqual(_TE_SPORT_TITLE["strength"][0], "肌肉刺激")
        self.assertEqual(_TE_SPORT_TITLE["strength"][1], "爆发负荷")


class TestV9_4MatrixIntegrity(unittest.TestCase):
    """§5 96 单元矩阵完整性(8 运动 × 2 维度 × 6 范围)"""

    def test_each_sport_has_6_entries_per_dimension(self):
        for sport, m in _TE_SPORT_MATRIX.items():
            self.assertIn("primary", m, f"{sport} 缺 primary")
            self.assertIn("secondary", m, f"{sport} 缺 secondary")
            self.assertEqual(len(m["primary"]), 6, f"{sport} primary 不足 6 范围")
            self.assertEqual(len(m["secondary"]), 6, f"{sport} secondary 不足 6 范围")
            # 每条目是 (label, summary) tuple
            for entry in m["primary"] + m["secondary"]:
                self.assertIsInstance(entry, tuple)
                self.assertEqual(len(entry), 2)

    def test_labels_non_empty(self):
        for sport, m in _TE_SPORT_MATRIX.items():
            for dim in ("primary", "secondary"):
                for label, summary in m[dim]:
                    self.assertTrue(len(label) > 0, f"{sport}/{dim} 缺 label")
                    self.assertTrue(len(summary) > 0, f"{sport}/{dim} 缺 summary")


class TestV9_4TeRangeBoundaries(unittest.TestCase):
    """§3 6 等级边界"""

    def test_te_to_index_boundaries(self):
        # 6 边界
        self.assertEqual(_te_to_index(0.0), 0)   # recovery
        self.assertEqual(_te_to_index(0.9), 0)
        self.assertEqual(_te_to_index(1.0), 1)   # activation
        self.assertEqual(_te_to_index(1.9), 1)
        self.assertEqual(_te_to_index(2.0), 2)   # maintenance
        self.assertEqual(_te_to_index(2.9), 2)
        self.assertEqual(_te_to_index(3.0), 3)   # improvement
        self.assertEqual(_te_to_index(3.9), 3)
        self.assertEqual(_te_to_index(4.0), 4)   # overload
        self.assertEqual(_te_to_index(4.4), 4)
        self.assertEqual(_te_to_index(4.5), 5)   # extreme
        self.assertEqual(_te_to_index(5.0), 5)

    def test_none_score_defaults_to_recovery(self):
        self.assertEqual(_te_to_index(None), 0)  # 0~0.9 recovery

    def test_level_ids_order(self):
        self.assertEqual(_TE_LEVEL_IDS[0], "recovery")
        self.assertEqual(_TE_LEVEL_IDS[1], "activation")
        self.assertEqual(_TE_LEVEL_IDS[2], "maintenance")
        self.assertEqual(_TE_LEVEL_IDS[3], "improvement")
        self.assertEqual(_TE_LEVEL_IDS[4], "overload")
        self.assertEqual(_TE_LEVEL_IDS[5], "extreme")

    def test_level_order_ascending(self):
        """§6.1:max() 优先级必须按 _TE_LEVEL_ORDER 升序"""
        levels = list(_TE_LEVEL_ORDER.keys())
        # 字典保序(Python 3.7+),levels 顺序应 = [recovery, activation, ..., extreme]
        expected_order = ["recovery", "activation", "maintenance",
                          "improvement", "overload", "extreme"]
        self.assertEqual(levels, expected_order,
                         "V9.4 FAIL: _TE_LEVEL_ORDER 必须按等级严格升序")


class TestV9_4BuildTrainingEffect(unittest.TestCase):
    """§6.6 极简实现:读 FIT 数值 + 查表 + 字符串拼接"""

    # ─── 跑步 TE 3.5(用户示例)───
    def test_running_example_from_contract(self):
        """§2.1 JSON 示例验证:跑步 3.5 aerobic + 2.4 anaerobic"""
        te = build_training_effect(
            {"aerobic_training_effect": 3.5, "anaerobic_training_effect": 2.4},
            "running",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["sport_type"], "running")
        self.assertEqual(te["primary"]["title"], "有氧收益")
        self.assertEqual(te["primary"]["score"], 3.5)
        self.assertEqual(te["primary"]["level"], "improvement")
        self.assertEqual(te["primary"]["label"], "提升有氧耐力")
        self.assertEqual(te["primary"]["summary"], "有效增强基础耐力")
        self.assertEqual(te["secondary"]["title"], "速度刺激")
        self.assertEqual(te["secondary"]["score"], 2.4)
        self.assertEqual(te["secondary"]["level"], "maintenance")
        # §5.1 running secondary 2~3 范围 = "提升速度能力" / "形成一定爆发刺激"
        # (用户 §2.1 示例的 "轻度提升" 与 §5.1 表不一致;以 §5.1 表为准,见 Resolver 注释)
        self.assertEqual(te["secondary"]["label"], "提升速度能力")
        self.assertEqual(te["secondary"]["summary"], "形成一定爆发刺激")
        # global_level = max(improvement=3, maintenance=2) = improvement
        self.assertEqual(te["global_level"], "improvement")
        self.assertIn("本次训练", te["overall_summary"])

    # ─── 老 FIT 文件降级 ───
    def test_no_te_no_hr_returns_none(self):
        """V9.4.1:无 FIT 字段 + 无 HR 字段 → 返回 None(走前端占位)"""
        self.assertIsNone(build_training_effect({}, "running"))
        self.assertIsNone(build_training_effect(
            {"aerobic_training_effect": None, "anaerobic_training_effect": None},
            "running",
        ))

    # ─── V9.4.4:不重算,只消费 FIT Firstbeat ───
    def test_both_fields_none_returns_none(self):
        """V9.4.4:双字段都 None → 走前端占位(不再做启发式估算)"""
        te = build_training_effect(
            {
                "aerobic_training_effect": None,
                "anaerobic_training_effect": None,
                "avg_hr": 135,
                "max_hr": 165,
                "duration_sec": 2520,
                "hr_zone_distribution": '{"Z3": 30, "Z4": 20, "Z5": 5}',
            },
            "running",
        )
        self.assertIsNone(te,
                          "V9.4.4 FAIL: 双字段都 None 应走占位,不重算")

    def test_single_field_consumed_with_zero_fallback(self):
        """V9.4.4:仅一个 FIT TE 字段存在 → 消费存在的,缺失维度走 0.0 fallback(标 fit_sdk)"""
        te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": None},
            "running",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertEqual(te["primary"]["score"], 3.0)
        self.assertEqual(te["secondary"]["score"], 0.0)

    def test_fit_sdk_path_marks_data_source(self):
        """V9.4.4:有 FIT 字段时 data_source='fit_sdk'"""
        te = build_training_effect(
            {"aerobic_training_effect": 3.5, "anaerobic_training_effect": 2.4},
            "running",
        )
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertNotIn("估算", te["overall_summary"])

    def test_real_garmin_field_names_sichuan(self):
        """V9.4.4:四姑娘山真实 FIT 字段 — total_training_effect=4.2, total_anaerobic_training_effect=2.1
        验证 Resolver 消费 Firstbeat 字段(标 fit_sdk),与 Garmin Connect 完全一致"""
        te = build_training_effect(
            {"aerobic_training_effect": 4.2, "anaerobic_training_effect": 2.1},
            "mountaineering",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertEqual(te["primary"]["score"], 4.2)
        self.assertEqual(te["secondary"]["score"], 2.1)

    def test_real_garmin_field_names_chengdu(self):
        """V9.4.4:成都半马真实 FIT 字段 — total_training_effect=5.0, total_anaerobic_training_effect=0.1"""
        te = build_training_effect(
            {"aerobic_training_effect": 5.0, "anaerobic_training_effect": 0.1},
            "running",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["data_source"], "fit_sdk")
        self.assertEqual(te["primary"]["score"], 5.0)
        self.assertEqual(te["secondary"]["score"], 0.1)

    # ─── 未知 sport fallback ───
    def test_unknown_sport_falls_back_to_running(self):
        te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 2.0},
            "unknown_sport",
        )
        self.assertIsNotNone(te)
        self.assertEqual(te["primary"]["title"], "有氧收益")
        self.assertEqual(te["secondary"]["title"], "速度刺激")

    # ─── 8 运动全跑通(每个运动 × 3 个 TE 范围)───
    def test_all_8_sports_te_matrix_complete(self):
        for sport in _TE_SPORT_MATRIX.keys():
            # 取 3 个代表性 TE 范围
            for aero in (0.5, 3.0, 4.7):
                te = build_training_effect(
                    {"aerobic_training_effect": aero, "anaerobic_training_effect": 1.5},
                    sport,
                )
                self.assertIsNotNone(te, f"{sport} @ TE {aero} 返回 None")
                self.assertEqual(te["sport_type"], sport)
                # 必有 title/label/summary
                self.assertTrue(len(te["primary"]["title"]) > 0)
                self.assertTrue(len(te["primary"]["label"]) > 0)
                self.assertTrue(len(te["primary"]["summary"]) > 0)

    # ─── 力量训练特殊语言(§5.7 约束)───
    def test_strength_uses_unique_vocabulary(self):
        """§5.7 力量训练不走有氧/无氧,而是肌肉刺激/爆发负荷"""
        te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 2.0},
            "strength",
        )
        self.assertEqual(te["primary"]["title"], "肌肉刺激")
        self.assertEqual(te["secondary"]["title"], "爆发负荷")
        # 跑步 primary 是 "有氧收益",力量是 "肌肉刺激" — 绝不能一样
        running_te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 2.0},
            "running",
        )
        self.assertNotEqual(te["primary"]["title"], running_te["primary"]["title"],
                            "V9.4 FAIL: 力量训练和跑步不应有相同的 primary title")

    # ─── global_level = max(primary, secondary) ───
    def test_global_level_picks_higher(self):
        # primary=4.0 overload, secondary=2.0 maintenance → global = overload
        te = build_training_effect(
            {"aerobic_training_effect": 4.0, "anaerobic_training_effect": 2.0},
            "running",
        )
        self.assertEqual(te["primary"]["level"], "overload")
        self.assertEqual(te["secondary"]["level"], "maintenance")
        self.assertEqual(te["global_level"], "overload")

        # 反之:primary=2.0, secondary=4.0 → global=overload
        te2 = build_training_effect(
            {"aerobic_training_effect": 2.0, "anaerobic_training_effect": 4.0},
            "running",
        )
        self.assertEqual(te2["global_level"], "overload")

    # ─── overall_summary 拼接 ───
    def test_overall_summary_format(self):
        te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 2.0},
            "running",
        )
        self.assertTrue(te["overall_summary"].startswith("本次训练"))
        self.assertIn(te["primary"]["summary"], te["overall_summary"])
        self.assertIn(te["secondary"]["summary"], te["overall_summary"])

    # ─── 入参校验 ───
    def test_non_dict_record_returns_none(self):
        self.assertIsNone(build_training_effect(None, "running"))
        self.assertIsNone(build_training_effect("not_a_dict", "running"))
        self.assertIsNone(build_training_effect(42, "running"))

    def test_empty_sport_defaults_to_running(self):
        te = build_training_effect(
            {"aerobic_training_effect": 3.0, "anaerobic_training_effect": 2.0},
            "",
        )
        self.assertEqual(te["sport_type"], "running")


if __name__ == "__main__":
    unittest.main()
