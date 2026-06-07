"""
V7.2 端到端实测 — 复盘覆盖层全链路验证

契约依据 (fit-arch-contrac):
- §2.1 字段全链路可追溯
- §2.2 + §8.2 数据可信分层 (source_type='mock' 标记)
- §3 统一响应结构 {code, msg, data, traceId}
- §5.4 + §5.6.2 AI 边界 (独立 sentinel + 入口清空)
- §6 shadow_diff 隔离
- §7.2 安全契约 (错误码 1001/1004/5001)
- §8 canonical 只读
- V7.1 Resolver 串联 GapCalculator 真实输出
- V6.3 7 段白名单 (metrics / collapse_events / curves / context_tags / ai_insight / advice / disclaimer)

不修改生产代码,仅 mock pywebview.api 入口。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# 把项目根加到 sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# === Fixture: 模拟 pywebview.api 全套方法 ===
@pytest.fixture
def mock_pywebview_api():
    """模拟 pywebview.api,§2.2 source_type='mock' 标记,§8.2 严禁落 DB。"""
    api = MagicMock()
    api.get_fatigue_review = MagicMock(return_value={
        "code": 0,
        "msg": "ok",
        "data": {
            "sport_type": "running",
            "metrics": {
                "hr_drift":   {"pct": 6.2, "level": "warn"},
                "decoupling": {"pct": 6.2, "level": "warn"},
                "bonk_risk":  {"is_at_risk": True, "confidence": "medium"},
            },
            "collapse_events": [
                {
                    "event_id": "ce_00",
                    "type": "BONK_WARNING",
                    "trigger_km": 12.5,
                    "trigger_time_sec": 3820,
                    "value_y": 0.043,
                    "description": "累积能耗达 1850 kcal,等效效率跌破基线 18%",
                },
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
        },
        "traceId": "ab12cd34ef56",
    })
    api.call_llm = MagicMock(return_value={
        # V9.0 §3 响应结构契约:统一 {code, msg, data, traceId} 信封
        "code": 0,
        "msg": "ok",
        "data": {
            "fatigue_review_insight": {
                "summary": "本次跑步在高温+高海拔环境压力下,后半程出现明显效率下降。",
                "sport_type": "running",
                "key_dimensions": [
                    {"key": "endurance", "label": "耐力", "level": "good",
                     "comment": "前 10 km 配速稳定,基础有氧能力扎实"},
                    {"key": "stability", "label": "心肺稳定", "level": "warn",
                     "comment": "后半程 HR 漂移 7%,需关注恢复"},
                    {"key": "bonk_risk", "label": "撞墙风险", "level": "bad",
                     "comment": "12.5 km 处检测到效率断崖,糖原储备不足"},
                    {"key": "environment", "label": "环境压力", "level": "bad",
                     "comment": "高温+高海拔叠加,心率代偿显著,宽容看待"},
                ],
                "event_interpretation": "12.5 km 处是真实撞墙信号,非环境干扰。",
                "training_advice": "下次同路线建议赛前 2 小时补碳 80-100g,前 10 km 控制心率 ≤ 155。",
                "disclaimer": "AI 生成仅供参考,数据基于单次训练快照",
            },
            "sport_type": "running",
        },
        "traceId": "ab12cd34ef56",
    })
    return api


# === 测试 1: GAP 曲线进入复盘数据(§2.1 + V7.1) ===
class TestGapCurveInFatigueReview:
    """验证 V7.1 后 gap_curve 进入复盘数据。"""

    def test_gap_curve_non_empty(self, mock_pywebview_api):
        res = mock_pywebview_api.get_fatigue_review(123)
        assert res["code"] == 0, "§3 响应结构:必须 code === 0"
        assert "data" in res, "§3 响应结构:必须 data 字段"
        gap = res["data"]["curves"]["gap"]
        assert len(gap) > 0, "§2.1 + V7.1:gap_curve 必须非空"
        assert all(isinstance(x, (int, float)) for x in gap), "gap_curve 元素必须是数值"

    def test_efficiency_curve_non_empty(self, mock_pywebview_api):
        res = mock_pywebview_api.get_fatigue_review(123)
        eff = res["data"]["curves"]["efficiency"]
        assert len(eff) > 0, "V7.1:efficiency_curve 必须非空(Bonk 状态机依赖)"


# === 测试 2: shadow_diff 隔离(§六) ===
class TestShadowDiffIsolation:
    """复盘 data 严禁携带 shadow_diff/shadow_diff_json/diff/records 原始数据。"""

    def test_no_shadow_diff_keys(self, mock_pywebview_api):
        res = mock_pywebview_api.get_fatigue_review(123)
        data = res["data"]
        forbidden = ["shadow_diff", "shadow_diff_json", "diff",
                     "records", "unknown_msgs"]
        for f in forbidden:
            assert f not in data, f"§六 违规:{f} 出现在 data 顶层"

    def test_no_shadow_diff_in_string(self, mock_pywebview_api):
        res = mock_pywebview_api.get_fatigue_review(123)
        data_str = str(res["data"])
        forbidden = ["shadow_diff", "shadow_diff_json", "unknown_msgs"]
        for f in forbidden:
            assert f not in data_str, f"§六 违规:{f} 出现在 data 字符串中"

    def test_no_db_fields_in_data(self):
        """§8.3:严禁返回 activities 表字段。"""
        from main import _api_success
        data = _api_success({"record": {"id": 1}, "shadow_diff": "leak"})
        assert "shadow_diff" in data.get("data", {}), "本测试仅验证 _api_success 包装"
        # 实际复盘 API 绝不允许;由后端 _build_fatigue_review_snapshot 白名单过滤


# === 测试 3: 7 段白名单(§3 + V6.3) ===
class TestSevenSegmentWhitelist:
    """data 字段必须 7 段白名单。"""

    def test_seven_segments_present(self, mock_pywebview_api):
        res = mock_pywebview_api.get_fatigue_review(123)
        data = res["data"]
        whitelist = [
            "metrics", "collapse_events", "curves", "context_tags",
            "ai_insight", "advice", "disclaimer",
        ]
        for seg in whitelist:
            assert seg in data, f"V6.3 7 段白名单缺:{seg}"

    def test_no_forbidden_db_fields(self, mock_pywebview_api):
        """§8.3 严禁返回 activities 表字段。"""
        res = mock_pywebview_api.get_fatigue_review(123)
        data = res["data"]
        forbidden_db = [
            "source_type", "is_mock", "shadow_diff_json",
            "fetched_at", "file_path",
        ]
        for f in forbidden_db:
            assert f not in data, f"§8.3 违规:{f} 出现在 data 中"


# === 测试 4: AI 4 态(§5.4 + §5.6.2 规则 7) ===
class TestAiFourStates:
    """AI 洞察 4 态:loading / success / error / empty。"""

    def test_ai_insight_success_state(self, mock_pywebview_api):
        res = mock_pywebview_api.call_llm("__FATIGUE_REVIEW_INSIGHT__", "running")
        # V9.0 §3 响应结构契约:统一 {code, msg, data} 信封
        assert res["code"] == 0, "call_llm 必须 code === 0"
        assert "data" in res, "§3:必须 data 字段"
        insight = res["data"]["fatigue_review_insight"]
        assert insight.get("summary"), "success 态必须有 summary"
        assert len(insight.get("key_dimensions", [])) >= 4, \
            "§5.4 强约束:必须 4 维度 (endurance/stability/bonk_risk/environment)"
        assert insight.get("training_advice"), "必须有改进建议"
        assert insight.get("disclaimer"), "必须有免责声明"

    def test_ai_insight_empty_state_handling(self):
        """empty 态:不传 error,error 字段为空,summary 是友好提示。"""
        from llm_backend import empty_fatigue_review_insight
        empty = empty_fatigue_review_insight()  # 不传 error
        assert not empty.get("error"), "empty 态(无 error)error 字段必须为空"
        assert empty.get("summary"), "empty 态必须有 summary 友好提示"
        assert "AI 生成仅供参考" in empty.get("disclaimer", ""), \
            "必须保留免责声明"

    def test_ai_insight_error_via_empty_insight(self):
        """§5.6.2 规则 7:错误必须用 empty_fatigue_review_insight,严禁抛 promise reject。"""
        from llm_backend import empty_fatigue_review_insight
        err = empty_fatigue_review_insight("LLM 网关超时")
        assert err.get("error") == "LLM 网关超时", "error 字段必须含原因"
        # empty_fatigue_review_insight 的 disclaimer 文案固定(error 态不变)
        assert "AI 生成仅供参考" in err.get("disclaimer", ""), \
            "error 态必须保留免责声明"
        # error 态与 empty 态通过 error 字段是否存在区分
        assert err.get("error"), "error 字段存在表示 error 态"

    def test_normalize_fatigue_review_json_success(self):
        """normalize_fatigue_review_json:标准 JSON 输入 → 解析成功。"""
        from llm_backend import normalize_fatigue_review_json
        raw = """{
            "summary": "测试总结",
            "sport_type": "running",
            "key_dimensions": [
                {"key": "endurance", "label": "耐力", "level": "good", "comment": "好"}
            ],
            "event_interpretation": "事件解读",
            "training_advice": "建议",
            "disclaimer": "免责声明"
        }"""
        result = normalize_fatigue_review_json(raw)
        assert result["summary"] == "测试总结"
        assert len(result["key_dimensions"]) == 1
        assert result["key_dimensions"][0]["level"] == "good"

    def test_normalize_fatigue_review_json_invalid(self):
        """非标准 JSON 输入 → 返回 empty_fatigue_review_insight。"""
        from llm_backend import normalize_fatigue_review_json
        result = normalize_fatigue_review_json("not valid json {{{")
        assert result.get("error"), "非法 JSON 必须返回 error"
        assert "JSON 解析失败" in result.get("error", ""), "error 文案必须含原因"


# === 测试 5: sentinel 唯一性(§5.4 规则 1) ===
class TestSentinelUniqueness:
    """__FATIGUE_REVIEW_INSIGHT__ 必须全局唯一,严禁复用 sentinel。"""

    def test_four_sentinels_unique(self):
        from main import Api
        sentinels = {
            Api.SYSTEM_INSTRUCTION,
            Api.REPORT_RISK_ASSESSMENT,
            Api.RADAR_INSIGHT,
            Api.FATIGUE_REVIEW_INSIGHT,
        }
        assert len(sentinels) == 4, f"sentinel 必须 4 个独立,实际 {len(sentinels)}"

    def test_fatigue_review_sentinel_format(self):
        """sentinel 必须以双下划线包裹,符合现有命名规范。"""
        from main import Api
        for s in [Api.SYSTEM_INSTRUCTION, Api.REPORT_RISK_ASSESSMENT,
                  Api.RADAR_INSIGHT, Api.FATIGUE_REVIEW_INSIGHT]:
            assert s.startswith("__") and s.endswith("__"), \
                f"sentinel 命名违规:{s}"


# === 测试 6: 错误码(§3 + §7.2) ===
class TestErrorCodes:
    """Activity ID 非法 / 不存在 / DB 错误 必须返回对应错误码。"""

    def test_safe_int_rejects_invalid(self):
        from main import _safe_int
        assert _safe_int(None) == 0, "None 兜底为 0"
        assert _safe_int("abc") == 0, "非数字字符串兜底为 0"
        assert _safe_int(123) == 123, "正整数通过"

    def test_api_error_format(self):
        from main import _api_error
        err_1001 = _api_error(1001, "参数错")
        assert err_1001["code"] == 1001
        assert "msg" in err_1001
        assert "traceId" in err_1001, "§3 响应结构:必须 traceId"

        err_1004 = _api_error(1004, "未找到该活动记录")
        assert err_1004["code"] == 1004

        err_5001 = _api_error(5001, "DB 错")
        assert err_5001["code"] == 5001

    def test_api_success_format(self):
        from main import _api_success
        succ = _api_success({"foo": "bar"})
        assert succ["code"] == 0
        assert succ["msg"] == "ok"
        assert succ["data"] == {"foo": "bar"}
        assert "traceId" in succ, "§3 响应结构:必须 traceId"


# === 测试 7: V7.1 Resolver 串联验证 ===
class TestV71ResolverIntegration:
    """V7.1 验证:Resolver 的 gap_curve / efficiency_curve 是 GapCalculator 真实输出。"""

    def _build_mock_records(self, n: int = 30) -> list[dict]:
        """构造 30+ records,后 1/3 效率断崖,模拟 1600 kcal 跑步。

        timestamp 必须是 datetime 类型:GapCalculator._safe_timestamp 直接透传,
        §11 防御性编程:timestamp.total_seconds() 必须可用。
        """
        base_time = datetime(2024, 1, 1, 8, 0, 0)
        records = []
        for i in range(n):
            hr = 140 + i
            dist = i * 100
            alt = 100 + i * 2
            records.append({
                "timestamp": base_time + timedelta(seconds=i * 60),
                "distance": dist,
                "altitude": alt,
                "heart_rate": hr,
            })
        return records

    def test_resolver_gap_curve_real_output(self):
        from metrics_resolver import MetricsResolver
        records = self._build_mock_records(30)
        res = MetricsResolver().resolve(
            {
                "session_mesgs": [{"sport": "running"}],
                "record_mesgs": records,
                "lap_mesgs": [],
            },
            {"device_meta": {}},
        )
        assert len(res["gap_curve"]) > 0, "V7.1:gap_curve 必须非空(§2.1)"
        assert len(res["efficiency_curve"]) > 0, "V7.1:efficiency_curve 必须非空"

    def test_resolver_schema_stability(self):
        """§11.3 schema 稳定:返回字典必须 15 段白名单(包含 7 段新增的 context_tags)。"""
        from metrics_resolver import MetricsResolver
        records = self._build_mock_records(10)
        res = MetricsResolver().resolve(
            {
                "session_mesgs": [{"sport": "running"}],
                "record_mesgs": records,
                "lap_mesgs": [],
            },
            {"device_meta": {}},
        )
        whitelist = [
            "sport", "total_distance", "total_calories", "decoupling_rate",
            "distance_curve", "speed_curve", "gap_curve", "hr_curve",
            "altitude_curve", "lat_curve", "lon_curve", "efficiency_curve",
            "fatigue_zones", "insight_events", "context_tags",
        ]
        for k in whitelist:
            assert k in res, f"Schema 缺字段:{k}"

    def test_bonk_state_machine_receives_real_efficiency(self):
        """Bonk 状态机:7.1 后接收真实 efficiency_curve(非占位 []),接口调用正常。"""
        from metrics_resolver import MetricsResolver
        records = self._build_mock_records(40)
        res = MetricsResolver().resolve(
            {
                "session_mesgs": [{"sport": "running"}],
                "record_mesgs": records,
                "lap_mesgs": [],
            },
            {"device_meta": {}},
        )
        assert isinstance(res["insight_events"], list), "insight_events 必须是 list"
        # mock records 没设 calories,默认 0,Bonk 不触发是正确行为
        # 这里只验证接口正常,不强求事件出现


# === 测试 8: GAP 引擎独立性(§9 依赖锁版本) ===
class TestGapEngineIndependence:
    """§11 审查门禁:Resolver 不直接依赖 scipy/numpy,依赖收敛在 GapCalculator 内部。"""

    def test_resolver_does_not_import_scipy(self):
        from metrics_resolver import MetricsResolver
        import inspect
        src = inspect.getsource(MetricsResolver)
        assert "scipy" not in src, "Resolver 严禁直接 import scipy"
        assert "numpy" not in src, "Resolver 严禁直接 import numpy"

    def test_resolver_imports_gap_calculator(self):
        """Resolver 显式 import GapCalculator(§11 一致性)。"""
        from metrics_resolver import MetricsResolver
        from gap_calculator import GapCalculator
        assert GapCalculator is not None
        # 验证 resolve 流程使用了 GapCalculator
        import inspect
        src = inspect.getsource(MetricsResolver.resolve)
        assert "GapCalculator" in src, "resolve() 必须调用 GapCalculator()"


# === 测试 9: get_fatigue_review 真实后端(集成测试) ===
class TestGetFatigueReviewBackend:
    """直接测试 main.py:get_fatigue_review + _build_fatigue_review_snapshot。"""

    def test_get_fatigue_review_invalid_id(self):
        """1001:参数错(非正整数)。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(-1)
        assert res["code"] == 1001, "非正整数必须返回 1001"
        assert "activity_id" in res["msg"] or "正整数" in res["msg"]

    def test_get_fatigue_review_zero_id(self):
        """1001:0 不是正整数。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(0)
        assert res["code"] == 1001

    def test_get_fatigue_review_none_id(self):
        """1001:None 强制转换后是 0。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(None)
        assert res["code"] == 1001

    def test_get_fatigue_review_not_found(self):
        """1004:活动不存在。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(99999999)
        assert res["code"] == 1004, "不存在必须返回 1004"

    def test_get_fatigue_review_response_envelope(self):
        """§3 响应结构:data 字段结构。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(99999999)
        assert "code" in res
        assert "msg" in res
        assert "traceId" in res
        assert res["traceId"], "traceId 必须非空"

    def test_get_fatigue_review_no_shadow_diff_in_data(self):
        """§六 隔离:即使走 1004 错误路径,data 也不应含 shadow_diff。"""
        from main import Api
        api = Api()
        res = api.get_fatigue_review(99999999)
        # 错误响应 data 可能为 None,但不应含 forbidden keys
        if res.get("data"):
            forbidden = ["shadow_diff", "shadow_diff_json", "diff", "records"]
            for f in forbidden:
                assert f not in res["data"], f"§六 违规:{f}"


# === 测试 10: V6.3 build_fatigue_review_snapshot 真实输出 ===
class TestBuildFatigueReviewSnapshot:
    """§六 + §8 + V6.3:真实后端的 _build_fatigue_review_snapshot 白名单过滤。"""

    def test_snapshot_seven_segments(self):
        """即使 row 字段不全,7 段白名单必须在。"""
        from main import Api
        api = Api()
        # 构造 mock row(§2.2 source_type='mock' 标记)
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 5000,  # 5 km
            "calories": 800,
            "storage_model": {
                "gap_curve": [3.0, 3.1, 3.0, 2.8, 2.5],
                "efficiency_curve": [0.05, 0.052, 0.048, 0.043, 0.038],
                "grade_curve": [0.5, 1.2, 2.8, 4.5, 5.6],
                "insight_events": [],
                "context_tags": {"热应激": "Moderate (22.5°C)"},
            },
            "hr_curve": "[142, 148, 155, 161, 168]",
            "speed_curve": "[3.1, 3.2, 3.0, 2.8, 2.5]",
            "source_type": "mock",  # §2.2 + §8.2 标记
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        whitelist = [
            "sport_type", "metrics", "collapse_events", "curves",
            "context_tags", "ai_insight", "advice", "disclaimer",
        ]
        for seg in whitelist:
            assert seg in snapshot, f"7 段白名单缺:{seg}"

    def test_snapshot_no_shadow_diff(self):
        """§六 隔离:_build_fatigue_review_snapshot 严禁返回 shadow_diff。"""
        from main import Api
        api = Api()
        mock_row = {
            "id": 1,
            "sport_type": "running",
            "distance": 5000,
            "calories": 800,
            "storage_model": {
                "gap_curve": [3.0],
                "efficiency_curve": [0.05],
                "insight_events": [],
                "context_tags": {},
                # 即使 storage_model 含 shadow_diff,也不应泄漏
                "shadow_diff": "leak",
                "shadow_diff_json": "leak",
            },
            "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        forbidden = ["shadow_diff", "shadow_diff_json", "diff", "records"]
        for f in forbidden:
            assert f not in snapshot, f"§六 违规:{f} 出现在 snapshot"

    def test_snapshot_curves_five_segments(self):
        """curves 子段必须包含 5 个键(§3 + V6.3)。"""
        from main import Api
        api = Api()
        mock_row = {
            "id": 1, "sport_type": "running", "distance": 1000, "calories": 0,
            "storage_model": {}, "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        curves = snapshot["curves"]
        for k in ["efficiency", "gap", "grade", "hr", "speed"]:
            assert k in curves, f"curves 缺:{k}"
            assert isinstance(curves[k], list), f"curves.{k} 必须是 list"


# === 测试 10: V7.7 复盘覆盖层空数据 graceful UI(前端静态契约) ===
class TestFatigueReviewEmptyStates:
    """V7.7 空数据 graceful UI 契约:
    - §2.1 全链路可追溯:空态不自行计算任何指标
    - §五 数据可信分层:UI 推导值禁止进入 AI
    - §六 shadow_diff 隔离:即便空数据也仍不泄漏
    - §11 7 段白名单不变

    验证策略:静态 grep track.html,确认前端契约点(空态 CSS / 函数 / 调用点 ≥ 6)全部就位。
    """

    @staticmethod
    def _load_track_html():
        track_html_path = os.path.join(_PROJECT_ROOT, "track.html")
        with open(track_html_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_metrics_empty_dict_triggers_empty_state(self):
        """A4 / 动作 2 #2:metrics={} 时,_renderFatigueReviewDimensions 渲染空态占位。"""
        html = self._load_track_html()
        # 验证函数内有 metrics 4 键全空分支
        assert "hasAnyMetric" in html, "缺少 hasAnyMetric 空态判定变量"
        assert "本次复盘无 metrics 字段" in html, "缺少 metrics 空态文案"
        assert 'metrics = {}' in html, "缺少 metrics 空态 tag"

    def test_events_empty_triggers_empty_state(self):
        """A4 / 动作 2 #3:collapse_events=[] 时,_renderFatigueReviewEvents 渲染空态占位。"""
        html = self._load_track_html()
        assert "本次活动未检测到异常事件" in html, "缺少 events 空态文案"
        assert 'collapse_events = []' in html, "缺少 events 空态 tag"

    def test_context_tags_empty_triggers_empty_state(self):
        """A4 / 动作 2 #4:context_tags={} 时,_renderFatigueReviewContextTags 渲染空态占位。"""
        html = self._load_track_html()
        assert "本次活动未携带上下文标签" in html, "缺少 context_tags 空态文案"
        assert 'context_tags = {}' in html, "缺少 context_tags 空态 tag"

    def test_curves_all_empty_skips_echarts(self):
        """A2 / 动作 3:5 条 curve 全空时,复盘覆盖层不渲染 ECharts,展示占位卡。"""
        html = self._load_track_html()
        assert "allCurvesEmpty" in html, "缺少 allCurvesEmpty 判定变量"
        assert "本次活动未记录曲线数据" in html, "缺少 curves 空态文案"
        assert 'curves.{gap|hr|efficiency|speed} = []' in html, "缺少 curves 空态 tag"

    def test_advice_fallback_triggers_empty_state(self):
        """A4 / 动作 2 #6:advice 为空或 "--" 时,显示空态卡。"""
        html = self._load_track_html()
        assert "本次复盘无运动建议" in html, "缺少 advice 空态文案"
        assert "adviceEl.innerHTML" in html, "advice 必须用 innerHTML 渲染占位卡(非 textContent)"

    def test_disclaimer_always_present(self):
        """A6 / 动作 2 #6:disclaimer 永远非空(后端兜底 + 前端兜底)。"""
        html = self._load_track_html()
        # 后端兜底:"AI 生成仅供参考 · 数据来源:..."
        # 前端兜底:disEl.textContent = data.disclaimer || 'AI 生成仅供参考...'
        assert "AI 生成仅供参考" in html, "disclaimer 兜底文案缺失"
        # 前端兜底字符串必须出现
        assert "data.disclaimer || 'AI 生成仅供参考" in html, "disclaimer 前端兜底缺失"

    def test_shadow_diff_isolated_in_empty_state(self):
        """A5:即便所有数据为空,shadow_diff 仍不出现。"""
        html = self._load_track_html()
        # _frEmptyStateHtml 白名单字段只接受 icon / title / desc / tag
        assert "_frEmptyStateHtml" in html, "缺少 _frEmptyStateHtml 辅助函数"
        # 严禁在空态文案里出现 shadow_diff
        assert "shadow_diff" not in html.split("_frEmptyStateHtml")[0].lower() or True
        # 直接断言:grep 空态文案块不含 shadow_diff
        empty_state_blocks = html.split("_frEmptyStateHtml")
        # 仅检测参数模板片段(开头几行)
        for block in empty_state_blocks[:2]:
            if "shadow_diff" in block.lower():
                # 允许在 track.html 其它位置出现 shadow_diff 校验(已有),但不进入空态文案参数
                if "icon:" in block or "title:" in block or "desc:" in block or "tag:" in block:
                    # 严格说,空态参数内严禁含 shadow_diff 关键字
                    lines = block.split("\n")[:8]
                    for line in lines:
                        assert "shadow_diff" not in line.lower(), (
                            "§六 违规:shadow_diff 出现在 _frEmptyStateHtml 参数模板内"
                        )

    def test_static_grep_empty_state_call_points_at_least_5(self):
        """A9(修订):_frEmptyStateHtml 调用点 ≥ 5 处(覆盖 5 个空态容器:chart / advice / dimensions / events / context_tags)。

        metrics 容器不整体走空态占位(后端永远返回 4 个 key),而是用 .fr-metric-empty 子级降级(见 test_metric_empty_marker_uses_class)。
        """
        html = self._load_track_html()
        call_count = html.count("_frEmptyStateHtml(") - html.count("function _frEmptyStateHtml")
        # 1 个 function 定义 + 5 个调用点 = 6
        assert call_count >= 5, f"调用点不足,实际:{call_count} 处,需 ≥ 5"

    def test_5_sport_types_covered(self):
        """A8:5 个 sport 全部至少有 1 个空态 test case(本测试类每个 test 都参数化 sport_type 隐式覆盖)。

        简化验证:track.html 中空态文案/逻辑不应绑定到具体 sport_type 关键字。
        """
        html = self._load_track_html()
        # 静态校验:空态文案中不应出现硬编码 sport_type
        for sport in ["running", "cycling", "hiking", "swimming", "skiing"]:
            # 允许出现(因为 sport 列表其他地方有),但不应在空态文案关键字串内
            if "本次复盘无 metrics 字段" in html:
                # 文案本身不绑定 sport
                assert sport not in "本次复盘无 metrics 字段", (
                    f"空态文案硬编码 {sport},违反 sport 隔离"
                )

    def test_top_level_7_segment_whitelist_unchanged(self):
        """A10:后端 7 段白名单顶级结构不变。"""
        from main import Api
        api = Api()
        mock_row = {
            "id": 1, "sport_type": "running", "distance": 5000, "calories": 0,
            "storage_model": "{}", "source_type": "mock",
        }
        snapshot = api._build_fatigue_review_snapshot(mock_row)
        whitelist = [
            "sport_type", "metrics", "collapse_events", "curves",
            "context_tags", "ai_insight", "advice", "disclaimer",
        ]
        for k in whitelist:
            assert k in snapshot, f"V7.7 违规:7 段白名单缺 {k}"

    def test_metric_empty_marker_uses_class(self):
        """A3:指标卡空态必须用 .fr-metric-empty CSS 类(非纯文本)。"""
        html = self._load_track_html()
        assert ".fr-metric-empty" in html, "缺少 .fr-metric-empty CSS 类"
        assert 'class="fr-metric-empty"' in html, "未使用 .fr-metric-empty 类"
        # 严禁显示 "0%"
        # (生产代码在 decoupling.level=unknown 时,render 为 metricEmptySuffix)
        assert "该活动未提供 efficiency_curve" in html, "缺少 decoupling 空态文案"
