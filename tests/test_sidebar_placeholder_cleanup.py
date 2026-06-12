"""活动详情侧栏占位卡清理回归测试。固化占位契约边界。

§4.1 删除后侧栏结构契约 + §4.2 函数留存契约 + §4.4 注释契约。
"""
import os
import re
import unittest


class TestSidebarPlaceholderCleanup(unittest.TestCase):
    """V_PLC P0: 身体状态/活动摘要两张占位卡必须已从 renderActivityDetailSidebar 删除。"""

    @classmethod
    def setUpClass(cls):
        track_html_path = os.path.join(
            os.path.dirname(__file__), "..", "track.html"
        )
        with open(track_html_path, "r", encoding="utf-8") as f:
            cls.html = f.read()

    def _extract_render_sidebar_body(self):
        """提取 renderActivityDetailSidebar 函数体(到下一个 function 定义前)。"""
        idx = self.html.find("function renderActivityDetailSidebar(")
        self.assertGreater(idx, 0, "缺 renderActivityDetailSidebar 函数")
        end = self.html.find("\n    function ", idx + 50)
        return self.html[idx:end]

    def test_no_body_state_in_sidebar_render(self):
        """§4.1 删除后侧栏结构契约:身体状态不应出现在 renderActivityDetailSidebar。"""
        body = self._extract_render_sidebar_body()
        self.assertNotIn("身体状态", body, "身体状态 占位卡仍存在于 renderActivityDetailSidebar")

    def test_no_activity_summary_in_sidebar_render(self):
        """§4.1 删除后侧栏结构契约:活动摘要不应出现在 renderActivityDetailSidebar。"""
        body = self._extract_render_sidebar_body()
        self.assertNotIn("活动摘要", body, "活动摘要 占位卡仍存在于 renderActivityDetailSidebar")

    def test_placeholder_builder_function_still_exists(self):
        """§4.2 函数留存契约:_buildPlaceholderSidebarCard 仍存在(供训练收益/环境挑战空态用)。"""
        self.assertIn(
            "function _buildPlaceholderSidebarCard(",
            self.html,
            "_buildPlaceholderSidebarCard 函数定义已被误删",
        )

    def test_training_effect_placeholder_still_uses_builder(self):
        """§4.2 函数留存契约:训练收益空态仍调 _buildPlaceholderSidebarCard。"""
        idx_te = self.html.find("function _buildTrainingBenefitCard(")
        self.assertGreater(idx_te, 0)
        end = self.html.find("\n    function ", idx_te + 50)
        te_body = self.html[idx_te:end]
        self.assertIn(
            "_buildPlaceholderSidebarCard('训练收益'",
            te_body,
            "训练收益空态降级路径被误删",
        )

    def test_environment_challenge_placeholder_still_uses_builder(self):
        """§4.2 函数留存契约:环境挑战空态仍调 _buildPlaceholderSidebarCard。"""
        idx_ec = self.html.find("function _buildEnvironmentChallengeCard(")
        self.assertGreater(idx_ec, 0)
        end = self.html.find("\n    function ", idx_ec + 50)
        ec_body = self.html[idx_ec:end]
        self.assertIn(
            "_buildPlaceholderSidebarCard('环境挑战'",
            ec_body,
            "环境挑战空态降级路径被误删",
        )

    def test_no_4_card_phrase_in_track_html(self):
        """§4.4 注释契约:历史 '4 张卡(...身体状态...)' 文案不应再出现。"""
        pattern = re.compile(r"4\s*张卡[^)\n]*身体状态")
        self.assertNotRegex(
            self.html, pattern,
            "track.html 仍含历史 '4 张卡(...身体状态...)' 注释",
        )
        pattern2 = re.compile(r"4\s*张卡[^)\n]*活动摘要")
        self.assertNotRegex(
            self.html, pattern2,
            "track.html 仍含历史 '4 张卡(...活动摘要...)' 注释",
        )

    def test_render_order_preserved(self):
        """§4.1 删除后侧栏结构契约:渲染顺序 weather → te → ec 必须保持。"""
        body = self._extract_render_sidebar_body()
        idx_weather = body.find("_buildWeatherCard(")
        idx_te = body.find("_buildTrainingBenefitCard(")
        idx_ec = body.find("_buildEnvironmentChallengeCard(")
        self.assertGreater(idx_weather, 0)
        self.assertGreater(idx_te, 0)
        self.assertGreater(idx_ec, 0)
        self.assertLess(idx_weather, idx_te, "天气卡应在训练收益之前")
        self.assertLess(idx_te, idx_ec, "训练收益应在环境挑战之前")


if __name__ == "__main__":
    unittest.main()
