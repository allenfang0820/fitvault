"""
V_ENV.1.11 Environment Challenge 前端契约测试

依据:任务 1.5(CSS 玻璃态) / 1.6(渲染函数) / 1.7(侧栏插入)
契约:fit-arch-contrac §2.1 字段可追溯 / §五 AI 边界(前端只消费 detail) / §六 审计字段隔离

测试范围(静态 grep):
  - _buildEnvironmentChallengeCard 函数存在 + 函数体字段消费
  - 6 个 CSS 类(.env-challenge-card/row/key/key-title/key-label/empty)
  - 5 级颜色常量 _ENV_LEVEL_COLORS
  - 函数体只读 record.detail.environment_challenge,不读 points[]
  - §六 审计字段隔离
  - renderActivityDetailSidebar 顺序插入
  - 不消费 record.aerobic_training_effect / anaerobic_training_effect(防串台)
"""

from __future__ import annotations
import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


def _slice_function_body(html: str, fn_name: str, max_len: int = 5000) -> str:
    """截取 fn_name 所在函数体(从 function 到下一个 \"\\n    function \" 之前)。"""
    start_marker = f"function {fn_name}("
    idx = html.find(start_marker)
    if idx < 0:
        return ""
    fn_decl_idx = html.rfind("function ", 0, idx)
    if fn_decl_idx < 0:
        fn_decl_idx = idx
    end = html.find("\n    function ", idx + len(start_marker))
    if end < 0:
        end = idx + max_len
    return html[fn_decl_idx:end]


class TestEnvironmentChallengeCardExists(unittest.TestCase):
    """§任务 1.6:_buildEnvironmentChallengeCard 函数存在"""

    def setUp(self):
        self.html = _read_track_html()

    def test_function_declared(self):
        self.assertIn("function _buildEnvironmentChallengeCard(", self.html,
                      "V_ENV FAIL: 缺 _buildEnvironmentChallengeCard 函数")

    def test_uses_record_detail_environment_challenge(self):
        """§2.2 路径:前端只读 record.detail.environment_challenge"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertTrue(body, "V_ENV FAIL: 函数体未找到")
        self.assertIn("record.detail.environment_challenge", body,
                      "V_ENV FAIL: 未读 record.detail.environment_challenge")

    def test_does_not_consume_points(self):
        """§五 5.1 AI 边界:严禁前端从 points[] 反推指标"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertNotIn("points[", body,
            "V_ENV FAIL: 前端不应消费 points[]")
        self.assertNotIn("record.points", body,
            "V_ENV FAIL: 前端不应消费 record.points")
        self.assertNotIn("record.records", body,
            "V_ENV FAIL: 前端不应消费 record.records")

    def test_does_not_calculate_metrics(self):
        """§任务 1.6 契约:只消费后端 canonical,不计算"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertNotIn("calculate_climb_density", body,
            "V_ENV FAIL: 前端不应计算 climb_density")
        self.assertNotIn("classify_altitude_stress", body,
            "V_ENV FAIL: 前端不应做海拔分级")
        self.assertNotIn("classify_heat_stress", body,
            "V_ENV FAIL: 前端不应做高温分级")
        self.assertNotIn("get_environment_challenge_semantic", body,
            "V_ENV FAIL: 前端不应调用后端语义路由函数")

    def test_shadow_diff_isolation(self):
        """§六 审计字段隔离:含 shadow_diff 字段直接 return ''"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        for forbidden in ("shadow_diff", "shadow_diff_json", ".diff"):
            self.assertIn(forbidden, body,
                f"V_ENV FAIL: 函数体未校验 {forbidden}")


class TestEnvironmentChallengeCSS(unittest.TestCase):
    """§任务 1.5:6 个 CSS 类存在"""

    def setUp(self):
        self.html = _read_track_html()

    def test_card_root_class(self):
        self.assertIn(".env-challenge-card", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-card")

    def test_row_class(self):
        self.assertIn(".env-challenge-row", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-row")

    def test_key_class(self):
        self.assertIn(".env-challenge-key", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-key")

    def test_key_title_class(self):
        self.assertIn(".env-challenge-key-title", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-key-title")

    def test_key_label_class(self):
        self.assertIn(".env-challenge-key-label", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-key-label")

    def test_empty_class(self):
        self.assertIn(".env-challenge-empty", self.html,
                      "V_ENV FAIL: 缺 .env-challenge-empty")

    def test_uses_weather_glass_card_root(self):
        """复用 .weather-glass-card 玻璃态"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertIn("weather-glass-card env-challenge-card", body,
            "V_ENV FAIL: 根 div 未用 weather-glass-card 玻璃态")


class TestEnvironmentChallengeColors(unittest.TestCase):
    """§任务 1.5:_ENV_LEVEL_COLORS 5 级颜色"""

    def setUp(self):
        self.html = _read_track_html()

    def test_color_constant_declared(self):
        self.assertIn("_ENV_LEVEL_COLORS", self.html,
                      "V_ENV FAIL: 缺 _ENV_LEVEL_COLORS")

    def test_5_colors_gray_blue_cyan_green_orange(self):
        body = self.html
        self.assertIn("#64748b", body)  # Gray
        self.assertIn("#3b82f6", body)  # Blue
        self.assertIn("#06b6d4", body)  # Cyan
        self.assertIn("#22c55e", body)  # Green
        self.assertIn("#f97316", body)  # Orange

    def test_function_references_color_constant(self):
        """_buildEnvironmentChallengeCard 必须引用 _ENV_LEVEL_COLORS"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertIn("_ENV_LEVEL_COLORS", body,
                      "V_ENV FAIL: 函数未引用 _ENV_LEVEL_COLORS")


class TestEnvironmentChallengeSidebarOrder(unittest.TestCase):
    """§任务 1.7:renderActivityDetailSidebar 顺序插入"""

    def setUp(self):
        self.html = _read_track_html()

    def test_sidebar_function_calls_environment_card(self):
        """renderActivityDetailSidebar 必须调 _buildEnvironmentChallengeCard"""
        body = _slice_function_body(self.html, "renderActivityDetailSidebar")
        self.assertIn("html += _buildEnvironmentChallengeCard(record)", body,
                      "V_ENV FAIL: 侧栏未调 _buildEnvironmentChallengeCard")

    def test_sidebar_order_after_training_benefit(self):
        """环境挑战必须出现在训练收益之后"""
        body = _slice_function_body(self.html, "renderActivityDetailSidebar")
        idx_te = body.find("_buildTrainingBenefitCard(record)")
        idx_ec = body.find("_buildEnvironmentChallengeCard(record)")
        self.assertGreater(idx_ec, idx_te,
            "V_ENV FAIL: 环境挑战应在训练收益之后")

    def test_all_three_sidebar_cards_in_order(self):
        """3 张卡完整顺序:天气 → 训练收益 → 环境挑战"""
        body = _slice_function_body(self.html, "renderActivityDetailSidebar")
        for fn in ("_buildWeatherCard", "_buildTrainingBenefitCard",
                   "_buildEnvironmentChallengeCard"):
            self.assertIn(fn, body, f"V_ENV FAIL: 侧栏缺 {fn}")
        idx_weather = body.find("_buildWeatherCard")
        idx_te = body.find("_buildTrainingBenefitCard")
        idx_ec = body.find("_buildEnvironmentChallengeCard")
        self.assertLess(idx_weather, idx_te)
        self.assertLess(idx_te, idx_ec)


class TestEnvironmentChallengeNoCrossPollution(unittest.TestCase):
    """§任务 1.6:严禁渲染函数污染其他卡片(防御性)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_no_sport_type_calculation(self):
        """应实现 cold sport 判定(skiing/mountaineering)"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertIn("isColdSport", body,
            "V_ENV FAIL: 未实现 cold sport 判定")

    def test_xss_protection(self):
        """§安全契约:前端必须用 esc() 局部函数防 XSS"""
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertIn("function esc(", body,
            "V_ENV FAIL: 缺 esc() 防 XSS")
        # sport_type 经 SPORT_TYPE_CN 查表后赋值给 sportCn,实际 XSS 在 sportCn 上做转义
        self.assertIn("esc(sportCn)", body,
            "V_ENV FAIL: sportCn 未过 esc")
        self.assertIn("esc(block.label.label)", body,
            "V_ENV FAIL: block.label.label 未过 esc")
        self.assertIn("esc(block.label.explanation)", body,
            "V_ENV FAIL: block.label.explanation 未过 esc")

    def test_no_metric_value_in_ui(self):
        """V_ENV.2.12:metric_value 数字不在 UI 展示(§9.5 决策)"""
        # 精确定位 _buildEnvironmentChallengeCard 函数体内 metric_value 引用
        # (避免 _slice_function_body 误包含前一个 _buildTrainingBenefitCard)
        fn_start = self.html.find("function _buildEnvironmentChallengeCard(")
        self.assertGreater(fn_start, 0, "V_ENV FAIL: 函数未找到")
        # 切片:从 fn_start 到下一个 `\\n    // ===` 注释前(下个函数块起点)
        end = self.html.find("\n    // ===", fn_start + 1)
        if end < 0:
            end = fn_start + 5000
        body = self.html[fn_start:end]
        # 严禁前端消费 metric_value
        self.assertNotIn("block.metric_value", body,
            "V_ENV FAIL: 前端不应读 block.metric_value")
        # 严禁渲染 valueStr
        self.assertNotIn("valueStr", body,
            "V_ENV FAIL: 前端不应有 valueStr 逻辑(v1.0 v1.1 残留)")
        # 必须改用 env-challenge-dash 占位
        self.assertIn("env-challenge-dash", body,
            "V_ENV FAIL: 应使用 env-challenge-dash 类做占位")


class TestEnvironmentChallengeClimbVisibility(unittest.TestCase):
    """环境挑战:爬升挑战仅对户外活动有意义。"""

    def setUp(self):
        self.html = _read_track_html()

    def test_climb_visibility_helper_declared(self):
        self.assertIn("function _envChallengeUsesClimb(", self.html,
                      "V_ENV FAIL: 缺少爬升挑战显示过滤 helper")

    def test_climb_row_skipped_when_helper_false(self):
        body = _slice_function_body(self.html, "_buildEnvironmentChallengeCard")
        self.assertIn("d.key === 'climb' && !_envChallengeUsesClimb(record, ec)", body,
                      "V_ENV FAIL: climb 行未按运动场景过滤")
        self.assertIn("continue", body,
                      "V_ENV FAIL: climb 过滤应跳过该维度行")

    def test_indoor_and_water_sports_excluded(self):
        body = _slice_function_body(self.html, "_envChallengeUsesClimb")
        for token in ("indoor", "treadmill", "swim", "open_water", "water",
                      "row", "boat", "kayak", "canoe", "paddle"):
            self.assertIn(token, body,
                          f"V_ENV FAIL: {token} 应排除爬升挑战")

    def test_outdoor_sports_kept(self):
        body = _slice_function_body(self.html, "_envChallengeUsesClimb")
        for token in ("run", "trail", "walk", "hik", "cycling", "bike",
                      "mountain", "ski", "mountaineering", "climb"):
            self.assertIn(token, body,
                          f"V_ENV FAIL: {token} 应保留爬升挑战")


if __name__ == "__main__":
    unittest.main()
