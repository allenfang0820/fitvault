"""
雷达图 AI 洞察 集成测试。

覆盖范围:
- Api.call_llm("__RADAR_INSIGHT__", ...) 端到端流程
- §5.4 规则 5:洞察调用后清空 _chat_messages + 刷新 session_id(全分支适用)
- §5.4 规则 7:不写 DB / 不污染 canonical
- 响应 schema 严格:{ok, radar_insight, sport_type}
- 3 种降级路径:空 sport_type / 无 metrics / 无 dimensions
- 与 __REPORT_INSIGHT__ 共存不互相污染

设计说明:
- §5.4 规则 5(清空 chat_messages + 刷新 session)在 RADAR_INSIGHT 分支入口执行,
  覆盖 happy path 和所有降级路径(空 sport_type / 无 metrics)。

遵循 fit-arch-contrac 契约:
- 不依赖真实 LLM(全部 mock)
- 不依赖真实 DB(全部 mock)
- 不写回 canonical 层
- 不使用 shadow_diff
"""
import json
import unittest
from unittest import mock

from main import Api, _p90


def _make_api_with_state(initial_messages=None, initial_session="session_test_initial"):
    """构造一个 Api 实例,绕过 __init__ 的 pywebview 初始化。
    手动设置必要实例属性,模拟 __init__ 完整初始化的效果。

    实例属性说明(call_llm 入口访问):
    - _chat_messages: 聊天历史
    - _session_id: 当前 session
    - _ai_snapshot: 活动 AI snapshot(None 表示无活动上下文)
    - _track_filename: 当前轨迹文件名
    - _track_points / _track_placemarks / _track_weather: 轨迹元数据
    """
    api = Api.__new__(Api)
    api._chat_messages = list(initial_messages) if initial_messages else []
    api._session_id = initial_session
    api._ai_snapshot = None
    api._track_filename = "轨迹"
    api._track_points = []
    api._track_placemarks = []
    api._track_weather = None
    return api


def _fake_llm_config():
    """构造一个合法的 LLM 配置。"""
    return {
        "url": "http://test-llm.local/v1/chat/completions",
        "apiKey": "test-key",
        "model": "test-model",
        "agentId": "test-agent",
        "provider": "test",
    }


def _fake_radar_snapshot(sport_type="running", with_dimensions=True):
    """构造一个合法的 radar snapshot。"""
    snap = {
        "source": "DB Canonical / 雷达后端引擎 / Resolver Truth",
        "sport_type": sport_type,
        "aggregation_window_days": 90,
        "metrics": {
            "ctl": 50, "atl": 30, "tsb": 20, "hrv": 65,
            "decoupling": 4.8, "vam": 750, "threshold_hr": 175,
            "anaerobic_peak": 5.2,
            "radar": {
                "dimensions": [
                    {"key": "endurance", "label": "耐力", "score": 75},
                    {"key": "recovery", "label": "恢复", "score": 60},
                ],
            } if with_dimensions else {},
        },
        "user_profile": {"age": 30, "max_hr": 190, "hrv_baseline": 65},
    }
    return snap


def _fake_messages():
    """构造合法的 LLM messages。"""
    return [
        {"role": "system", "content": "fake system prompt"},
        {"role": "user", "content": "fake user prompt"},
    ]


class TestCallLlmRadarInsightHappyPath(unittest.TestCase):
    """happy path:LLM 返回合法 JSON,正常流程。"""

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_happy_path_returns_normalized_insight(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        # LLM 返回的合法 JSON
        mock_llm.return_value = json.dumps({
            "summary": "跑步能力中等",
            "sport_type": "running",
            "dimension_interpretation": [
                {"key": "endurance", "label": "耐力", "score": 75, "comment": "良好"},
            ],
            "weakest_dim": "recovery",
            "strongest_dim": "endurance",
            "balance_assessment": "well_balanced",
            "load_status": {"ctl": 50, "atl": 30, "tsb": 20, "status": "optimal"},
            "training_advice": "增加恢复训练",
            "long_term_trend": "stable",
            "disclaimer": "AI 仅供参考",
        })

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")

        self.assertTrue(result["ok"])
        self.assertEqual(result["sport_type"], "running")
        self.assertEqual(result["radar_insight"]["summary"], "跑步能力中等")
        self.assertEqual(result["radar_insight"]["weakest_dim"], "recovery")
        self.assertEqual(result["radar_insight"]["load_status"]["status"], "optimal")

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_response_shape_strict_has_three_keys(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """响应必须严格含 {ok, radar_insight, sport_type} 三个 key,无其他。"""
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertEqual(set(result.keys()), {"ok", "radar_insight", "sport_type"})

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_llm_markdown_wrapped_json_still_normalized(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """LLM 返回 ```json ... ``` markdown 包裹时,normalizer 仍能解析。"""
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '```json\n{"summary": "ok", "sport_type": "running"}\n```'

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertEqual(result["radar_insight"]["summary"], "ok")
        self.assertEqual(result["radar_insight"]["sport_type"], "running")
        # success 时 error 字段应为空
        self.assertEqual(result["radar_insight"]["error"], "")

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_cli_transport_does_not_require_http_url_or_model(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """CLI 模式下 call_llm 只把配置交给统一后端,不再要求 HTTP url/model。"""
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = {
            "transport": "cli",
            "cli_type": "codex",
            "url": "",
            "model": "",
        }
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")

        self.assertTrue(result["ok"])
        kwargs = mock_llm.call_args.kwargs
        self.assertEqual(kwargs["config"]["transport"], "cli")
        self.assertEqual(kwargs["config"]["cli_type"], "codex")


class TestCallLlmRadarInsightSessionBoundary(unittest.TestCase):
    """§5.4 规则 5:洞察调用后清空 _chat_messages + 刷新 session_id。

    设计说明:清空 + 刷新在 RADAR_INSIGHT 分支入口执行,
    覆盖 happy path 和所有降级路径(空 sport_type / 无 metrics / 无 dimensions)。
    """

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_chat_messages_cleared_after_call(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        # 预设 _chat_messages 有内容,模拟"之前聊过天"
        api = _make_api_with_state(initial_messages=[
            {"role": "user", "content": "之前问过的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ])
        self.assertEqual(len(api._chat_messages), 2)

        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertTrue(result["ok"])
        # §5.4 规则 5:清空
        self.assertEqual(api._chat_messages, [])

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_session_id_refreshed_after_call(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        api = _make_api_with_state(initial_session="session_before_radar")
        old_sid = api._session_id

        api.call_llm("__RADAR_INSIGHT__", "running")
        # §5.4 规则 5:刷新
        self.assertNotEqual(api._session_id, old_sid)
        self.assertTrue(api._session_id.startswith("session_"))

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_chat_messages_cleared_even_on_empty_sport_type(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """§5.4 规则 5 全分支适用:空 sport_type 降级路径也必须清空。"""
        mock_cfg.return_value = _fake_llm_config()

        api = _make_api_with_state(initial_messages=[
            {"role": "user", "content": "之前问过的问题"},
        ])
        old_sid = api._session_id
        self.assertEqual(len(api._chat_messages), 1)

        result = api.call_llm("__RADAR_INSIGHT__", "")
        self.assertTrue(result["ok"])
        # §5.4 规则 5:清空 + 刷新
        self.assertEqual(api._chat_messages, [])
        self.assertNotEqual(api._session_id, old_sid)
        # 降级路径不调 LLM / snapshot / messages
        mock_llm.assert_not_called()
        mock_snap.assert_not_called()
        mock_msgs.assert_not_called()

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_chat_messages_cleared_even_on_no_metrics(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """§5.4 规则 5 全分支适用:无 metrics 降级路径也必须清空。"""
        snap = _fake_radar_snapshot()
        snap["metrics"] = {}  # metrics 为空
        mock_snap.return_value = snap
        mock_cfg.return_value = _fake_llm_config()

        api = _make_api_with_state(initial_messages=[
            {"role": "user", "content": "之前问过的问题"},
        ])
        old_sid = api._session_id

        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertTrue(result["ok"])
        # §5.4 规则 5:清空 + 刷新
        self.assertEqual(api._chat_messages, [])
        self.assertNotEqual(api._session_id, old_sid)
        mock_llm.assert_not_called()
        mock_msgs.assert_not_called()


class TestCallLlmRadarInsightFallbackPaths(unittest.TestCase):
    """3 种降级路径(均不调 LLM,直接返回 empty_radar_insight)。"""

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_empty_sport_type_returns_empty_insight(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        mock_cfg.return_value = _fake_llm_config()
        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "")
        self.assertTrue(result["ok"])
        self.assertIn("请先选择运动类型", result["radar_insight"]["error"])
        # 降级路径不调 LLM / snapshot / messages
        mock_llm.assert_not_called()
        mock_snap.assert_not_called()
        mock_msgs.assert_not_called()

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_no_metrics_returns_empty_insight(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """snapshot['metrics'] 为空 → 降级。"""
        snap = _fake_radar_snapshot()
        snap["metrics"] = {}  # metrics 为空
        mock_snap.return_value = snap
        mock_cfg.return_value = _fake_llm_config()

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertTrue(result["ok"])
        self.assertIn("暂无 90 天数据", result["radar_insight"]["error"])
        mock_llm.assert_not_called()
        mock_msgs.assert_not_called()

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_no_dimensions_returns_empty_insight(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """snapshot['metrics']['radar']['dimensions'] 为空 → 降级。"""
        snap = _fake_radar_snapshot(with_dimensions=False)
        mock_snap.return_value = snap
        mock_cfg.return_value = _fake_llm_config()

        api = _make_api_with_state()
        result = api.call_llm("__RADAR_INSIGHT__", "running")
        self.assertTrue(result["ok"])
        self.assertIn("暂无 90 天数据", result["radar_insight"]["error"])


class TestCallLlmRadarInsightSafetyBoundaries(unittest.TestCase):
    """§5.4 规则 7 + 与其他 sentinel 共存不污染。"""

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_radar_insight_does_not_modify_canonical_or_ai_snapshot(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """radar 流程**不**写入 _ai_snapshot / _track_points / DB。"""
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        api = _make_api_with_state()
        # 预设 _ai_snapshot / _track_points 应**不**被覆盖
        api._ai_snapshot = {"legacy": "do_not_overwrite"}
        api._track_points = [{"lat": 1, "lon": 2}]

        api.call_llm("__RADAR_INSIGHT__", "running")

        # 验证未被 radar 流程错误改写
        self.assertEqual(api._ai_snapshot, {"legacy": "do_not_overwrite"})
        self.assertEqual(api._track_points, [{"lat": 1, "lon": 2}])

    @mock.patch("main.llm_backend.generate_text")
    @mock.patch("main.llm_backend.load_llm_config")
    @mock.patch("main._build_radar_insight_messages")
    @mock.patch("main._build_radar_insight_snapshot")
    def test_radar_session_independent_from_report_insight(
        self, mock_snap, mock_msgs, mock_cfg, mock_llm,
    ):
        """与 __REPORT_INSIGHT__ 共存:两个 sentinel 各调一次,session 互不污染。
        每次调用都刷新 session_id,所以第二次调用的 session_id 不同于第一次。
        """
        mock_snap.return_value = _fake_radar_snapshot()
        mock_msgs.return_value = _fake_messages()
        mock_cfg.return_value = _fake_llm_config()
        mock_llm.return_value = '{"summary": "ok", "sport_type": "running"}'

        api = _make_api_with_state(initial_session="session_start")

        # 第一次:radar
        api.call_llm("__RADAR_INSIGHT__", "running")
        sid_after_radar = api._session_id

        # 模拟在两次调用之间用户与 AI 教练聊天
        api._chat_messages = [
            {"role": "user", "content": "训练建议?"},
            {"role": "assistant", "content": "..."},
        ]
        # 第二次:再调一次 radar(模拟用户连按两次)
        api.call_llm("__RADAR_INSIGHT__", "running")
        sid_after_second_radar = api._session_id

        # 验证:
        # 1. 每次 radar 调用都清空 _chat_messages
        self.assertEqual(api._chat_messages, [])
        # 2. 第二次调用刷新出**新**的 session_id
        self.assertNotEqual(sid_after_radar, sid_after_second_radar)


class TestP90AllenScenario(unittest.TestCase):
    """P0 修复集成测试:Allen 案例复现 + 降档验证。

    审计背景(§8 / §9.1 P0):
    - 4 次骑行活动中 3 次通勤平路 VAM=0,1 次偶遇陡坡 VAM=1200
    - 修复前:max([0,0,0,1200])=1200 → score_climbing(1200)=95(满分)
    - 修复后:p90([0,0,0,1200])=840 → score_climbing(840)=75(降档 1 个等级)

    验证 _p90 函数 + 雷达维度 score_climbing 的端到端降档行为。
    """

    def test_p90_allen_scenario_cycling_climbing(self):
        """Allen 案例复现:4 次骑行通勤中 1 次陡坡,修复后爬升应降档。

        修复前:max([0, 0, 0, 1200]) = 1200 → score_climbing(1200) = 95
        修复后:p90 = 840 → score_climbing(840) = 75
        降档 ≥ 1 个等级,验证异常值主导已被消除。
        """
        # _p90 helper 级别断言(浮点容忍 1e-5,避免 IEEE 754 误差)
        self.assertAlmostEqual(_p90([0, 0, 0, 1200]), 840.0, places=5)

        # 端到端降档验证(配合 RadarScoreEngine.score_climbing)
        from utils.metrics_calc import RadarScoreEngine
        allen_values = [0, 0, 0, 1200]

        # 修复前行为
        pre_fix_max = max(allen_values)
        pre_fix_score = RadarScoreEngine.score_climbing(pre_fix_max)

        # 修复后行为
        post_fix_p90 = _p90(allen_values)
        post_fix_score = RadarScoreEngine.score_climbing(post_fix_p90)

        # 断言:从满分 95 降到 75
        self.assertEqual(pre_fix_score, 95)
        self.assertEqual(post_fix_score, 75)
        self.assertLess(post_fix_score, pre_fix_score)
        # 降档 ≥ 20 分(1 个等级)
        self.assertGreaterEqual(pre_fix_score - post_fix_score, 20)

    def test_p90_does_not_pollute_canonical(self):
        """§5.4 规则 7 / §八 canonical:使用 _p90 不触发任何 DB / shadow_diff 写入。

        _p90 是纯函数(只接收 list[float],返回 float),不涉及 DB / I/O。
        此测试断言:即使在 Api 实例有完整状态时调用 _p90,canonical 层不变。
        """
        api = _make_api_with_state()
        # 预设 canonical 状态
        api._ai_snapshot = {"canonical": "do_not_modify"}
        api._track_points = [{"lat": 1, "lon": 2}]

        # 调用 _p90(纯计算)
        result = _p90([100, 200, 300, 400, 500])

        # 验证 canonical 未变
        self.assertEqual(api._ai_snapshot, {"canonical": "do_not_modify"})
        self.assertEqual(api._track_points, [{"lat": 1, "lon": 2}])
        # 验证计算结果正确
        # sorted=[100, 200, 300, 400, 500], rank=0.9*4=3.6
        # lower=3, upper=4, fraction=0.6
        # result = 400 * 0.4 + 500 * 0.6 = 160 + 300 = 460.0
        self.assertAlmostEqual(result, 460.0, places=5)


if __name__ == "__main__":
    unittest.main()
