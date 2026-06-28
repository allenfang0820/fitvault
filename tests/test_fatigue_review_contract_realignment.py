from __future__ import annotations

import json
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestFatigueReviewP0ApiContract(unittest.TestCase):
    def _fatigue_review_contract(self) -> dict:
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        with open(contract_path, encoding="utf-8") as f:
            doc = json.load(f)
        for item in doc.get("methods", doc.get("apis", [])):
            if item.get("name") == "get_fatigue_review":
                return item
        self.fail("docs/js_api_contract.json 必须登记 get_fatigue_review")

    def test_contract_declares_authoritative_curves(self):
        item = self._fatigue_review_contract()
        returns = item.get("returns", "")
        for field in (
            "curves: {distance, time, hr, speed, altitude, grade, gap, efficiency, terrain_load, power, cadence, total_distance_m}",
            "curves.distance 为后端权威距离轴",
            "curves.time 为后端权威时间轴",
            "curves.total_distance_m 单位 m",
        ):
            self.assertIn(field, returns)

    def test_contract_declares_cycling_power_cadence_fields(self):
        item = self._fatigue_review_contract()
        returns = item.get("returns", "")
        for field in (
            "summary: {avg_power, max_power, normalized_power, avg_cadence, power_available, cadence_available, power_points_count, cadence_points_count, power_data_quality, cadence_data_quality}",
            "power_variability",
            "pedaling_stability",
            "efficiency: {score, level, confidence, delta_pct, sample_size, basis, power_per_hr, avg_power, avg_hr, power_data_quality, reasons}",
            "durability: {score, level, confidence, head_speed, tail_speed, basis, head_power, tail_power, power_retention_pct, power_points_count, power_data_quality, reasons}",
            "curves.power 为骑行功率曲线",
            "curves.cadence 为骑行踏频曲线",
            "cycling/road_cycling/mountain_biking",
            "power_data_quality",
        ):
            self.assertIn(field, returns)

    def test_contract_declares_cycling_power_efficiency_durability(self):
        item = self._fatigue_review_contract()
        returns = item.get("returns", "")
        contract = item.get("contract", "")
        for field in (
            "P3b-cycling",
            "efficiency.basis=power_hr",
            "durability.basis=power_retention",
            "power_per_hr",
            "head_power/tail_power/power_retention_pct",
            "不得用速度后程保持冒充功率耐力",
        ):
            self.assertIn(field, returns)
        for field in (
            "P3b-cycling 指标零推断",
            "efficiency/durability 只能由后端 avg_power/avg_hr 和同轴 power 曲线生成",
            "前端与 AI 均不得计算或补齐",
        ):
            self.assertIn(field, contract)

    def test_contract_declares_cycling_explanation_signals(self):
        item = self._fatigue_review_contract()
        returns = item.get("returns", "")
        contract = item.get("contract", "")
        description = item.get("description", "")
        for field in (
            "cycling_explanation_signals",
            "intensity_signal",
            "aerobic_drift_signal",
            "power_retention_signal",
            "pacing_signal",
            "cadence_signal",
            "status/level/summary/evidence/reasons",
        ):
            self.assertIn(field, returns)
        for field in (
            "P0-science 骑行解释信号零推断",
            "不得从 summary/curves/DOM/ECharts/points 自行推导",
            "无 FTP/功率/心率时不得输出",
            "个人强度解释信号只允许后端 intensity_signal",
            "P9 心率反应/有氧漂移解释信号只允许后端 aerobic_drift_signal",
            "有效功率+心率曲线摘要",
            "metrics.hr_drift/metrics.decoupling",
            "P3 有效踩踏段后程保持只允许后端 power_retention_signal",
            "过滤滑行/停顿/零功率/异常片段",
            "不得把下坡/滑行包装成后程功率下降",
            "P4 骑行 pacing / 功率波动解释只允许后端 pacing_signal",
            "VI 与功率曲线摘要",
            "不得把跑步配速策略包装成骑行功率 pacing",
            "P10 踏频节奏解释信号只允许后端 cadence_signal",
            "有效踏频曲线摘要",
            "pedaling_stability 参考 evidence",
            "不得从 curves/DOM/ECharts/points 自行判断踏频节奏",
            "无踏频或踏频样本不足时不得输出踩踏节奏确定性结论",
            "不得诊断齿比/扭矩/左右平衡/踩踏平滑度/真实踩踏技术",
            "不得输出 Pw:Hr",
            "不得推断补给/天气/恢复",
            "不得由前端或 AI 构造",
            "P5 现有复盘 UI 最小接入",
            "signal.summary/evidence/reasons",
            "不得从 summary/metrics/curves/DOM/ECharts/points 构造解释信号",
            "专业指标只作为依据副文本",
        ):
            self.assertIn(field, contract)
        self.assertIn("个人强度解释信号", description)
        self.assertIn("P2 有氧漂移解释信号", description)
        self.assertIn("P3 有效踩踏段后程保持", description)
        self.assertIn("P4 骑行 pacing / 功率波动解释", description)
        self.assertIn("P5 现有复盘 UI 最小接入", description)
        self.assertIn("前端现有骑行卡片优先展示后端 signal.summary", description)
        self.assertIn("不新增模块、不改 ECharts、不计算新指标", description)
        self.assertIn("不计算 IF/TSS/Pw:Hr", description)
        self.assertIn("不输出 Pw:Hr 专业缩写", description)
        self.assertIn("cycling_aerobic_drift", returns)
        self.assertIn("hr_drift_reference/review_decoupling_reference", returns)
        self.assertIn("不得推断补给/天气/恢复等 snapshot 未提供事实", returns)
        self.assertIn("level 支持 held/slight_drop/clear_drop/unknown", returns)
        self.assertIn("effective_pedaling_power_retention", returns)
        self.assertIn("steady/variable/front_loaded/late_fade/unknown", returns)
        self.assertIn("cycling_pacing_reference", returns)
        self.assertIn("P10 踏频节奏解释信号契约", returns)
        self.assertIn("steady/variable/low_cadence_bias/cadence_drop/interrupted/unknown", returns)
        self.assertIn("cycling_cadence_rhythm", returns)
        self.assertIn("pedaling_stability_metric_reference", returns)
        self.assertIn("avg_cadence/head_cadence/tail_cadence/cadence_cv/cadence_std/cadence_drop_pct/low_cadence_ratio/zero_cadence_ratio/effective_cadence_points_count/filter_reasons/confidence", returns)
        self.assertIn("不诊断齿比、扭矩、左右平衡、踩踏平滑度或真实踩踏技术", returns)
        self.assertIn("不得暴露 curves/points/records/raw_records/shadow_diff/diff", returns)
        self.assertIn("P10 踏频节奏解释信号", description)
        self.assertIn("cadence_signal", description)
        self.assertIn("不诊断齿比/扭矩/左右平衡/踩踏技术", description)

    def test_contract_declares_cycling_frontend_zero_inference(self):
        item = self._fatigue_review_contract()
        contract = item.get("contract", "")
        for field in (
            "P0-cycling 前端零推断",
            "curves.power 与 curves.cadence 必须由后端权威输出",
            "前端不得补算、推断、拉伸",
            "无功率或样本不足时必须按 power_data_quality",
            "cadence_data_quality",
        ):
            self.assertIn(field, contract)

    def test_contract_declares_frontend_zero_inference(self):
        item = self._fatigue_review_contract()
        contract = item.get("contract", "")
        for field in (
            "前端零推断",
            "curves.distance 必须由后端权威输出",
            "前端不得通过 _distanceFromSpeedTime 或 points 重建事实距离轴",
            "fatigue_zones.start_km/end_km",
            "collapse_events.trigger_km",
            "必须和 curves.distance 同源",
        ):
            self.assertIn(field, contract)

    def test_contract_forbids_debug_and_raw_fields(self):
        item = self._fatigue_review_contract()
        contract = item.get("contract", "")
        for forbidden in ("shadow_diff", "shadow_diff_json", "diff", "records", "全量 points"):
            self.assertIn(forbidden, contract)

    def test_contract_marks_ai_as_p6(self):
        item = self._fatigue_review_contract()
        description = item.get("description", "")
        self.assertIn("AI 洞察 __FATIGUE_REVIEW_INSIGHT__ 留到后续专项阶段", description)
        self.assertIn("后端快照回正", description)
        self.assertIn("P0-cycling", description)

    def test_ai_contract_declares_cycling_compact_snapshot(self):
        contract_path = os.path.join(_PROJECT_ROOT, "docs", "js_api_contract.json")
        with open(contract_path, encoding="utf-8") as f:
            doc = json.load(f)
        ai_contract = (doc.get("architectural_constraints") or {}).get("fatigue_review_ai_contract", "")
        for field in (
            "summary",
            "curves_summary.has_power",
            "has_cadence",
            "power_points_count",
            "cadence_points_count",
            "normalized_power",
            "avg_cadence",
            "power_data_quality",
            "cadence_data_quality",
            "cycling_explanation_signals",
            "review_snapshot.get(\"cycling_explanation_signals\")",
            "P6 起 AI 只能解释后端已有",
            "intensity_signal/aerobic_drift_signal/power_retention_signal/pacing_signal/cadence_signal",
            "不得补算或补造解释信号",
            "status=unavailable/partial 必须温和降级",
            "无 FTP 不得编造 FTP/IF/TSS/训练负荷",
            "无功率不得输出功率强度/后程功率保持/pacing 确定性结论",
            "无心率不得输出有氧漂移结论",
            "不得编造补给、天气、设备、路况",
            "禁止完整功率复盘口吻",
        ):
            self.assertIn(field, ai_contract)


class TestFatigueReviewP0SnapshotShape(unittest.TestCase):
    def test_empty_snapshot_contains_p0_curve_fields(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot()
        curves = snapshot.get("curves", {})
        for key in ("distance", "time", "hr", "speed", "altitude", "grade", "gap", "efficiency", "terrain_load", "power", "cadence", "total_distance_m"):
            self.assertIn(key, curves)
        self.assertEqual(curves["distance"], [])
        self.assertEqual(curves["time"], [])
        self.assertEqual(curves["altitude"], [])

    def test_empty_snapshot_contains_cycling_summary_placeholders(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot(sport_type="cycling")
        summary = snapshot.get("summary", {})
        for key in (
            "avg_power", "max_power", "normalized_power", "avg_cadence",
            "power_available", "cadence_available",
            "power_points_count", "cadence_points_count",
            "power_data_quality", "cadence_data_quality",
        ):
            self.assertIn(key, summary)
        self.assertFalse(summary["power_available"])
        self.assertFalse(summary["cadence_available"])
        self.assertEqual(summary["power_data_quality"], "missing")
        self.assertEqual(summary["cadence_data_quality"], "missing")

    def test_empty_snapshot_forbids_raw_debug_fields(self):
        from main import Api

        snapshot = Api._empty_fatigue_review_snapshot()
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in ("shadow_diff", "shadow_diff_json", '"diff"', '"records"'):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
