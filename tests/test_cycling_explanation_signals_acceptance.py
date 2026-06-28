from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")
MAIN_PY = os.path.join(_PROJECT_ROOT, "main.py")
LLM_BACKEND_PY = os.path.join(_PROJECT_ROOT, "llm_backend.py")
ACCEPTANCE_CHECKLIST = os.path.join(_PROJECT_ROOT, "docs", "cycling_fatigue_review_acceptance_checklist.md")
REALIGNMENT_PLAN = os.path.join(_PROJECT_ROOT, "docs", "fatigue_review_realignment_plan_v1.md")

_SIGNAL_KEYS = (
    "intensity_signal",
    "aerobic_drift_signal",
    "power_retention_signal",
    "pacing_signal",
    "cadence_signal",
)

_USER_VISIBLE_FORBIDDEN_COPY = (
    "pending_algorithm",
    "intensity_classification_not_enabled",
    "backend",
    "后端证据",
    "后端参考证据",
    "本阶段",
    "专项算法尚未完成",
    "尚未启用",
    "专用算法",
    "占位",
    "算法未完成",
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _assert_no_raw_detail_fields(testcase: unittest.TestCase, value: object) -> None:
    encoded = _json_text(value)
    for forbidden in ("points", "records", "raw_records", "track_points", "fit_records", "gpx_points", "shadow_diff", "diff"):
        testcase.assertNotIn(f'"{forbidden}"', encoded)


class TestP7CyclingExplanationSignalsAcceptance(unittest.TestCase):
    def _signals(self, *, sport_type: str = "cycling", summary=None, curves=None, metrics=None, ftp=None):
        import main

        return main._build_cycling_explanation_signals(
            sport_type,
            summary=summary or {},
            curves_snapshot=curves or {},
            metrics=metrics or {},
            profile_ftp_watts=ftp,
        )

    def test_power_hr_ftp_sample_stays_coach_like_without_training_load_claims(self):
        power = [210] * 80 + [205] * 80
        signals = self._signals(
            summary={
                "avg_power": 208,
                "max_power": 420,
                "normalized_power": 216,
                "avg_cadence": 86,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": len(power),
                "cadence_points_count": len(power),
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves={
                "hr": [138] * len(power),
                "power": power,
                "cadence": [86, 87, 85, 86] * 40,
                "speed": [9] * len(power),
                "time": list(range(len(power))),
            },
            metrics={
                "power_variability": {"vi": 1.04, "level": "good", "confidence": "high"},
                "durability": {"basis": "power_retention", "power_retention_pct": 98.0},
            },
            ftp=260,
        )

        self.assertEqual(signals["status"], "partial")
        self.assertEqual(signals["intensity_signal"]["status"], "available")
        self.assertEqual(signals["intensity_signal"]["level"], "tempo")
        self.assertEqual(signals["power_retention_signal"]["level"], "held")
        self.assertEqual(signals["pacing_signal"]["level"], "steady")
        self.assertEqual(signals["aerobic_drift_signal"]["status"], "available")
        self.assertEqual(signals["aerobic_drift_signal"]["level"], "stable")
        self.assertIn("effective_power_hr_decoupling", signals["aerobic_drift_signal"]["reasons"])

        encoded = _json_text(signals)
        for forbidden in ("IF", "TSS", "Pw:Hr", "W/kg", "CTL", "ATL", "TSB"):
            self.assertNotIn(forbidden, encoded)
        _assert_no_raw_detail_fields(self, signals)

    def test_signal_summaries_are_product_copy_not_engineering_placeholders(self):
        signals = self._signals(
            summary={
                "avg_power": 208,
                "max_power": 420,
                "normalized_power": 216,
                "avg_cadence": 86,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 160,
                "cadence_points_count": 160,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves={
                "hr": [138] * 160,
                "power": [210] * 80 + [205] * 80,
                "cadence": [86, 87, 85, 86] * 40,
                "speed": [9] * 160,
                "time": list(range(160)),
            },
            ftp=260,
        )

        for key in _SIGNAL_KEYS:
            summary = str(signals[key].get("summary") or "")
            for forbidden in _USER_VISIBLE_FORBIDDEN_COPY:
                self.assertNotIn(forbidden, summary, f"{key} summary leaked {forbidden}")

        self.assertIn("不是轻松骑", signals["intensity_signal"]["summary"])
        self.assertIn("暂未看到明显有氧漂移", signals["aerobic_drift_signal"]["summary"])
        self.assertIn("踏频节奏比较稳定", signals["cadence_signal"]["summary"])
        for forbidden in ("踩踏技术", "齿比", "扭矩", "左右平衡", "踩踏平滑度"):
            self.assertNotIn(forbidden, _json_text(signals["cadence_signal"]))

    def test_missing_ftp_does_not_personalize_intensity(self):
        signals = self._signals(
            summary={
                "avg_power": 180,
                "normalized_power": 205,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 120,
                "cadence_points_count": 120,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves={"hr": [132] * 120, "power": [180] * 120, "cadence": [84] * 120},
            ftp=None,
        )

        intensity = signals["intensity_signal"]
        self.assertEqual(intensity["status"], "unavailable")
        self.assertEqual(intensity["level"], "unknown")
        self.assertIn("missing_ftp", intensity["reasons"])
        self.assertIn("missing_ftp", signals["unavailable_reasons"])
        encoded = _json_text(intensity)
        for forbidden in ("阈值", "高强度", "低强度", "IF", "TSS", "训练负荷"):
            self.assertNotIn(forbidden, encoded)

    def test_missing_power_disables_power_intensity_retention_and_pacing_claims(self):
        signals = self._signals(
            summary={
                "power_available": False,
                "cadence_available": True,
                "power_points_count": 0,
                "cadence_points_count": 100,
                "power_data_quality": "missing",
                "cadence_data_quality": "available",
            },
            curves={"hr": [130] * 100, "cadence": [82] * 100},
            ftp=250,
        )

        self.assertEqual(signals["intensity_signal"]["status"], "unavailable")
        self.assertEqual(signals["power_retention_signal"]["status"], "unavailable")
        self.assertEqual(signals["pacing_signal"]["status"], "unavailable")
        for key in ("intensity_signal", "power_retention_signal", "pacing_signal", "aerobic_drift_signal"):
            self.assertTrue(any("power_data_unavailable:missing" == reason for reason in signals[key]["reasons"]))
        encoded = _json_text({
            "intensity_signal": signals["intensity_signal"],
            "power_retention_signal": signals["power_retention_signal"],
            "pacing_signal": signals["pacing_signal"],
        })
        for forbidden in ("功率保持稳定", "功率输出较平稳", "前段输出偏高", "后段功率出现回落", "高强度", "阈值"):
            self.assertNotIn(forbidden, encoded)

    def test_missing_hr_disables_aerobic_drift_claim(self):
        signals = self._signals(
            summary={
                "power_available": True,
                "cadence_available": True,
                "power_points_count": 80,
                "cadence_points_count": 80,
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves={"power": [190] * 80, "cadence": [84] * 80},
            ftp=250,
        )

        drift = signals["aerobic_drift_signal"]
        self.assertEqual(drift["status"], "unavailable")
        self.assertEqual(drift["level"], "unknown")
        self.assertIn("missing_hr", drift["reasons"])
        for forbidden in ("有氧漂移稳定", "显著漂移", "Pw:Hr", "功率-心率漂移结论"):
            self.assertNotIn(forbidden, _json_text(drift))

    def test_coasting_heavy_tail_is_not_mislabeled_as_fitness_drop(self):
        power = [210] * 90 + [0] * 90
        signals = self._signals(
            summary={
                "avg_power": 105,
                "power_available": True,
                "power_points_count": len(power),
                "power_data_quality": "available",
            },
            curves={
                "hr": [130] * len(power),
                "power": power,
                "speed": [11] * len(power),
                "time": list(range(len(power))),
            },
        )

        retention = signals["power_retention_signal"]
        self.assertEqual(retention["status"], "unavailable")
        self.assertEqual(retention["level"], "unknown")
        self.assertIn("insufficient_effective_pedaling_points", retention["reasons"])
        encoded = _json_text(retention)
        self.assertIn("coasting", encoded)
        for forbidden in ("clear_drop", "功率明显回落", "体能下降", "持续输出能力开始回落"):
            self.assertNotIn(forbidden, encoded)

    def test_short_power_sample_stays_unavailable_instead_of_guessing(self):
        signals = self._signals(
            summary={
                "power_available": True,
                "power_points_count": 12,
                "power_data_quality": "available",
            },
            curves={
                "hr": [130] * 12,
                "power": [205] * 12,
                "speed": [8] * 12,
                "time": list(range(12)),
            },
        )

        self.assertEqual(signals["power_retention_signal"]["status"], "unavailable")
        self.assertEqual(signals["pacing_signal"]["status"], "unavailable")
        self.assertIn("insufficient_effective_pedaling_points", signals["power_retention_signal"]["reasons"])
        self.assertIn("insufficient_power_points", signals["pacing_signal"]["reasons"])

    def test_non_cycling_gets_unavailable_cycling_explanation_only(self):
        signals = self._signals(
            sport_type="running",
            summary={"power_available": True, "power_data_quality": "available"},
            curves={"hr": [130] * 80, "power": [220] * 80},
            ftp=250,
        )

        self.assertEqual(signals["status"], "unavailable")
        self.assertIn("not_cycling_activity", signals["unavailable_reasons"])
        for key in _SIGNAL_KEYS:
            self.assertEqual(signals[key]["status"], "unavailable")
            self.assertIn("not_cycling_activity", signals[key]["reasons"])

    def test_evidence_never_exposes_raw_detail_fields_even_with_noisy_inputs(self):
        power = [230] * 50 + [180] * 50
        signals = self._signals(
            summary={
                "avg_power": 205,
                "normalized_power": 220,
                "power_available": True,
                "cadence_available": True,
                "power_points_count": len(power),
                "cadence_points_count": len(power),
                "power_data_quality": "available",
                "cadence_data_quality": "available",
            },
            curves={
                "hr": [130] * len(power),
                "power": power,
                "speed": [9] * len(power),
                "time": list(range(len(power))),
                "points": [{"should": "not leak"}],
                "raw_records": [{"should": "not leak"}],
                "shadow_diff": {"should": "not leak"},
            },
            metrics={
                "hr_drift": {"pct": 5.0, "level": "good", "records": [{"bad": True}]},
                "decoupling": {"pct": 4.8, "level": "good", "curves": [1, 2]},
                "power_variability": {"vi": 1.08, "level": "moderate", "raw_records": [{"bad": True}]},
                "durability": {"basis": "power_retention", "power_retention_pct": 87.8, "points": [1, 2]},
            },
            ftp=260,
        )

        for key in _SIGNAL_KEYS:
            _assert_no_raw_detail_fields(self, signals[key]["evidence"])

    def test_p4_trustworthy_acceptance_matrix_keeps_degradation_boundaries(self):
        cases = [
            {
                "name": "missing_ftp",
                "signals": self._signals(
                    summary={
                        "avg_power": 180,
                        "normalized_power": 205,
                        "power_available": True,
                        "power_points_count": 120,
                        "power_data_quality": "available",
                    },
                    curves={"hr": [132] * 120, "power": [180] * 120},
                    ftp=None,
                ),
                "expect": {"intensity_signal": ("unavailable", "missing_ftp")},
                "forbidden": ("阈值", "高强度", "低强度", "IF", "TSS", "训练负荷结论"),
            },
            {
                "name": "missing_power",
                "signals": self._signals(
                    summary={
                        "power_available": False,
                        "power_points_count": 0,
                        "power_data_quality": "missing",
                    },
                    curves={"hr": [130] * 100, "cadence": [82] * 100},
                    ftp=250,
                ),
                "expect": {
                    "intensity_signal": ("unavailable", "power_data_unavailable:missing"),
                    "power_retention_signal": ("unavailable", "power_data_unavailable:missing"),
                    "pacing_signal": ("unavailable", "power_data_unavailable:missing"),
                },
                "forbidden": ("功率保持良好", "输出较平稳", "前段偏猛", "后段回落", "功率强度"),
            },
            {
                "name": "missing_hr",
                "signals": self._signals(
                    summary={
                        "power_available": True,
                        "power_points_count": 100,
                        "power_data_quality": "available",
                    },
                    curves={"power": [190] * 100, "cadence": [84] * 100},
                    ftp=250,
                ),
                "expect": {"aerobic_drift_signal": ("unavailable", "missing_hr")},
                "forbidden": ("漂移不明显", "显著漂移", "Pw:Hr", "功率-心率漂移结论"),
            },
            {
                "name": "coasting_tail",
                "signals": self._signals(
                    summary={
                        "avg_power": 105,
                        "power_available": True,
                        "power_points_count": 180,
                        "power_data_quality": "available",
                    },
                    curves={
                        "hr": [130] * 180,
                        "power": [210] * 90 + [0] * 90,
                        "speed": [11] * 180,
                        "time": list(range(180)),
                    },
                ),
                "expect": {"power_retention_signal": ("unavailable", "insufficient_effective_pedaling_points")},
                "forbidden": ("clear_drop", "功率明显回落", "体能下降", "持续输出能力开始回落"),
            },
            {
                "name": "short_sample",
                "signals": self._signals(
                    summary={
                        "power_available": True,
                        "power_points_count": 12,
                        "power_data_quality": "available",
                    },
                    curves={
                        "hr": [130] * 12,
                        "power": [205] * 12,
                        "speed": [8] * 12,
                        "time": list(range(12)),
                    },
                ),
                "expect": {
                    "power_retention_signal": ("unavailable", "insufficient_effective_pedaling_points"),
                    "pacing_signal": ("unavailable", "insufficient_power_points"),
                },
                "forbidden": ("输出较平稳", "功率保持良好", "后程回落明显", "完整复盘"),
            },
            {
                "name": "non_cycling",
                "signals": self._signals(
                    sport_type="running",
                    summary={"power_available": True, "power_data_quality": "available"},
                    curves={"hr": [130] * 80, "power": [220] * 80},
                    ftp=250,
                ),
                "expect": {key: ("unavailable", "not_cycling_activity") for key in _SIGNAL_KEYS},
                "forbidden": ("骑行输出", "功率保持良好", "踩踏组织", "相对强度"),
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                signals = case["signals"]
                for key, (status, reason) in case["expect"].items():
                    self.assertEqual(signals[key]["status"], status)
                    self.assertIn(reason, signals[key]["reasons"])
                encoded = _json_text(signals)
                for forbidden in case["forbidden"]:
                    self.assertNotIn(forbidden, encoded)
                _assert_no_raw_detail_fields(self, signals)


class TestP7CyclingReviewFrontendAndAiAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.track_html = _read(TRACK_HTML)
        self.main_py = _read(MAIN_PY)
        self.llm_backend = _read(LLM_BACKEND_PY)
        self.acceptance_checklist = _read(ACCEPTANCE_CHECKLIST)
        self.realignment_plan = _read(REALIGNMENT_PLAN)

    def test_ui_minimal_entry_uses_backend_signals_without_signal_reconstruction(self):
        self.assertIn(
            "_renderFatigueReviewMetrics(data.metrics || {}, data.sport_type, data.cycling_explanation_signals || {})",
            self.track_html,
        )
        start = self.track_html.index("function _fatigueReviewCyclingSignal(")
        end = self.track_html.index("function _renderFatigueReviewMetrics(", start)
        helper = self.track_html[start:end]

        for expected in (
            "signals[key]",
            "signal['summary']",
            "signal.evidence",
            "signal.reasons",
            "_fatigueReviewCyclingSignalEvidenceItemText",
            "_fatigueReviewCyclingSignalReasonText",
            "_fatigueReviewCyclingSignalVisibility",
            "_fatigueReviewCyclingSignalCanOwnHeadline",
            "_fatigueReviewCyclingSignalHeadline",
            "_fatigueReviewCyclingSignalSummaryText",
            "canOwnHeadline: state === 'available'",
            "canShowAsReference: state === 'available' || state === 'partial'",
            "if (!_fatigueReviewCyclingSignalCanOwnHeadline(signal))",
            "依据：",
            "缺少个人 FTP",
            "当前只作为辅助依据",
            "可参考",
        ):
            self.assertIn(expected, helper)
        for forbidden_text in (
            "String(item.type).replace(/_/g, ' ')",
            "key.replace(/_/g, ' ')",
            "signal.reasons.join",
            "专项算法尚未完成",
            "后端证据",
            "本阶段",
            "后端未返回可展示",
            "谨慎参考",
        ):
            self.assertNotIn(forbidden_text, helper)
        for forbidden in (
            "curves.",
            "summary.avg_power",
            "metrics.",
            "querySelector",
            "getOption",
            "innerText",
            "powerVar.vi",
            "hrDrift.pct",
            "durCycling.power_retention_pct",
        ):
            self.assertNotIn(forbidden, helper)

    def test_ai_compact_snapshot_and_prompt_keep_backend_signal_boundary(self):
        start = self.main_py.index("def _build_fatigue_review_insight_snapshot(")
        end = self.main_py.index("def _build_fatigue_review_snapshot(", start)
        compact_builder = self.main_py[start:end]
        self.assertIn(
            '"cycling_explanation_signals": review_snapshot.get("cycling_explanation_signals") or {}',
            compact_builder,
        )
        self.assertNotIn("_build_cycling_explanation_signals(", compact_builder)

        for expected in (
            "骑行解释信号必须以该后端字段为唯一依据",
            "不得从 summary / metrics / curves_summary / DOM / ECharts / points 自行构造",
            "无 FTP 不得编造 FTP、IF、TSS、训练负荷或阈值强度",
            "无功率不得输出功率强度、后程功率保持或 pacing 结论",
            "无心率不得输出有氧漂移结论",
            "不得编造补给、天气、设备、路况",
        ):
            self.assertIn(expected, self.llm_backend)

    def test_p4_acceptance_checklist_defines_repeatable_real_sample_closure(self):
        for expected in (
            "P4 真实样本验收闭环记录",
            "有数据时说得具体",
            "缺数据时明确降级",
            "不用跑步口径解释骑行",
            "不把专业指标当 UI 主角",
            "有功率 + 有心率 + 有 FTP",
            "无 FTP",
            "无可用功率",
            "无心率",
            "滑行 / 下坡较多",
            "样本不足",
            "非骑行回归",
            "禁止输出或展示",
            "pending_algorithm",
            "后端证据",
            "本阶段",
            "占位",
            "算法未完成",
        ):
            self.assertIn(expected, self.acceptance_checklist)

    def test_p5_real_ui_visual_audit_records_power_and_downhill_boundaries(self):
        for expected in (
            "P5 真实 UI 截图/视觉验收记录",
            "304",
            "有功率 + 有心率 + 有 FTP",
            "298",
            "无可用功率",
            "246",
            "下坡比例高",
            "功率质量 `invalid_values`",
            "279",
            "有效踩踏证据充足",
            "不是直接把下坡或滑行说成体能下降",
            "未做跨浏览器截图回归",
        ):
            self.assertIn(expected, self.acceptance_checklist)

    def test_p7_final_freeze_records_release_boundaries_without_new_algorithms(self):
        for expected in (
            "P7 最终冻结结论",
            "最终验收与冻结，不新增科学算法、不改 UI 布局、不改 ECharts、不改 DB、不解冻 AI 入口",
            "get_fatigue_review(activity_id)",
            "data.cycling_explanation_signals",
            "review_snapshot.get(\"cycling_explanation_signals\")",
            "available` 可以作为用户可见主结论",
            "partial` 只能作为参考线索",
            "unavailable` 只能温和降级",
            "无 FTP 不判断个人化强度",
            "无功率不判断功率强度、后程功率保持或 pacing",
            "无心率不判断有氧漂移",
            "252 / 279",
            "跨浏览器或打包环境截图回归",
        ):
            self.assertIn(expected, self.acceptance_checklist)

        for expected in (
            "P7-cycling-trust-freeze",
            "骑行可信解释最终冻结",
            "不新增 FTP/IF/TSS/W/kg/Pw:Hr/CTL/ATL/TSB/CP/W′",
            "用户可见强结论只允许来自后端 `cycling_explanation_signals` 中 `status=available` 的 signal",
            "前端只做读取、可见性闸门和产品化中文映射",
            "AI compact snapshot 只透传 `review_snapshot.get(\"cycling_explanation_signals\")`",
            "专业指标只保留为 evidence 或辅助依据，不成为默认 UI 主结论",
        ):
            self.assertIn(expected, self.realignment_plan)


if __name__ == "__main__":
    unittest.main()
