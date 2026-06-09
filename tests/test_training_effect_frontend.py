"""
V9.4.0 训练收益(Training Effect)前端契约测试

依据:docs/training_effect_v1_contract.md
- §2.2 数据路径:record.detail.training_effect
- §7 前端契约:只消费,不计算
- §6.7 实施决策:8 运动 + 6 等级颜色渲染

测试范围(静态 grep):
  - _buildTrainingBenefitCard 函数存在
  - _TE_LEVEL_COLORS 6 颜色(Gray/Blue/Cyan/Green/Orange/Red)
  - _TE_LEVEL_LABELS_CN 6 中文标签
  - 8 运动覆盖(_resolveHeroItems registry)
  - 玻璃态 CSS .training-benefit-card / .training-effect-grid
  - 渲染消费 record.detail.training_effect 字段
  - 不消费 record.aerobic_training_effect / anaerobic_training_effect 直接计算
  - §六 shadow_diff 隔离
  - V9.2.2 占位文案被替换
"""

from __future__ import annotations
import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


class TestV9_4BuildTrainingBenefitCard(unittest.TestCase):
    """§7 前端契约:_buildTrainingBenefitCard 存在 + 必现字段"""

    def setUp(self):
        self.html = _read_track_html()

    def test_function_exists(self):
        self.assertIn("function _buildTrainingBenefitCard(", self.html,
                      "V9.4 FAIL: 缺 _buildTrainingBenefitCard")

    def test_uses_record_detail_training_effect(self):
        """§2.2 路径:前端只读 record.detail.training_effect"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("record.detail.training_effect", body,
                      "V9.4 FAIL: 未读 record.detail.training_effect")
        # 不应直接读 FIT 字段
        self.assertNotIn("aerobic_training_effect", body,
                         "V9.4 FAIL: 前端不应直接读 aerobic_training_effect")
        self.assertNotIn("anaerobic_training_effect", body,
                         "V9.4 FAIL: 前端不应直接读 anaerobic_training_effect")


class TestV9_4LevelColors(unittest.TestCase):
    """§3 + §6.7:6 等级颜色渲染"""

    def setUp(self):
        self.html = _read_track_html()

    def test_te_level_colors_6_levels(self):
        self.assertIn("_TE_LEVEL_COLORS", self.html,
                      "V9.4 FAIL: 缺 _TE_LEVEL_COLORS 颜色表")
        # 必须有 6 等级(用户原 §三 6 颜色)— quote-agnostic
        for level in ["recovery", "activation", "maintenance", "improvement", "overload", "extreme"]:
            quoted = "'" + level + "':"
            unquoted = level + ":"
            self.assertTrue(quoted in self.html or unquoted in self.html,
                            f"V9.4 FAIL: _TE_LEVEL_COLORS 缺 {level}")

    def test_te_level_labels_cn_6_levels(self):
        self.assertIn("_TE_LEVEL_LABELS_CN", self.html,
                      "V9.4 FAIL: 缺 _TE_LEVEL_LABELS_CN 中文标签")
        for cn in ["恢复", "激活", "维持", "提升", "高负荷", "极限"]:
            self.assertIn(cn, self.html,
                          f"V9.4 FAIL: _TE_LEVEL_LABELS_CN 缺「{cn}」")


class TestV9_4EightSportRegistry(unittest.TestCase):
    """§4 + §6.7:HERO_FIELD_REGISTRY 扩 8 运动(契约 §11.1)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_hiit_added(self):
        """V9.4.0:HERO_FIELD_REGISTRY 必须含 hiit(原 7 → 8 运动)"""
        idx = self.html.find("const HERO_FIELD_REGISTRY")
        end = self.html.find("};", idx)
        body = self.html[idx:end + 2]
        # 8 运动必现
        for sport in ["running", "trail_running", "hiking",
                      "cycling", "indoor_cycling", "swimming",
                      "strength", "hiit"]:
            quoted = "'" + sport + "':"
            unquoted = sport + ":"
            self.assertTrue(quoted in body or unquoted in body,
                            f"V9.4 FAIL: HERO_FIELD_REGISTRY 缺 {sport}")


class TestV9_4ShadowDiffIsolation(unittest.TestCase):
    """§六 shadow_diff 隔离:训练收益卡必须保留"""

    def setUp(self):
        self.html = _read_track_html()

    def test_shadow_diff_check(self):
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.4 FAIL: 训练收益卡缺 §六 shadow_diff 校验")


class TestV9_4FrontendNoCalculation(unittest.TestCase):
    """§7 禁做:前端不计算 TE 数值/等级/标签/拼接 overall_summary"""

    def setUp(self):
        self.html = _read_track_html()

    def test_no_te_score_calculation(self):
        """前端不读 FIT 字段,不算 TE 分数"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        # 不应出现「算 TE 数值」的特征(查表 toFixed 是允许的:消费 display)
        # 关键是 FIT 字段不在前端出现
        self.assertNotIn("aerobic_training_effect", body)
        self.assertNotIn("anaerobic_training_effect", body)

    def test_overall_summary_just_consumes(self):
        """overall_summary 必须从 record.detail.training_effect 直接读,前端不拼接"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        # 应该有 te.overall_summary 的引用(读而非拼)
        self.assertIn("te.overall_summary", body,
                      "V9.4 FAIL: 训练收益卡未消费 te.overall_summary")
        # 不应有"本次训练"字符串拼接(这是 Resolver 的责任)
        self.assertNotIn("本次训练{", body,
                         "V9.4 FAIL: 前端不应拼接 overall_summary")


class TestV9_4GlassCardCss(unittest.TestCase):
    """§7 + §6.7:训练收益卡复用玻璃态 + 新增 CSS"""

    def setUp(self):
        self.html = _read_track_html()

    def test_training_benefit_card_css(self):
        """CSS 块: 复用 .weather-glass-card + 新增 .training-effect-grid"""
        for css_class in [".training-benefit-card", ".training-effect-grid", ".training-effect-row",
                          ".training-effect-key", ".training-effect-key-title",
                          ".training-effect-key-label", ".training-effect-score"]:
            self.assertIn(css_class, self.html,
                          f"V9.4 FAIL: CSS 缺 {css_class}")


class TestV9_4PlaceholderReplaced(unittest.TestCase):
    """V9.4.0:V9.2.2 占位卡(训练收益)被 _buildTrainingBenefitCard 替换"""

    def setUp(self):
        self.html = _read_track_html()

    def test_old_placeholder_text_gone(self):
        """旧占位文案"有氧收益 / 无氧刺激将在「复盘」Tab"应已替换"""
        # renderActivityDetailSidebar 内不再有 _buildPlaceholderSidebarCard('训练收益', ...)
        idx = self.html.find("function renderActivityDetailSidebar(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 旧占位卡不应再针对「训练收益」
        self.assertNotIn("_buildPlaceholderSidebarCard('训练收益'", body,
                         "V9.4 FAIL: renderActivityDetailSidebar 仍含旧训练收益占位")
        # 应有新函数调用
        self.assertIn("_buildTrainingBenefitCard(record)", body,
                      "V9.4 FAIL: renderActivityDetailSidebar 未调 _buildTrainingBenefitCard")


class TestV9_4_4SportCnAndSummarySize(unittest.TestCase):
    """V9.4.4:训练收益卡两个小调整
    1) 副标题运动类型英文 → 中文(统一调 getDynamicSportMeta 真理源,16+ 运动覆盖)
    2) 总结字号从 weather-glass-empty 0.72rem 改用专属 .training-effect-summary 0.85rem"""

    def setUp(self):
        self.html = _read_track_html()

    def test_subtitle_uses_sport_type_cn(self):
        """V9.4.4:副标题里 te.sport_type 被包了一层 getDynamicSportMeta 映射"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("getDynamicSportMeta", body,
                      "V9.4.4 FAIL: 副标题未用 getDynamicSportMeta 中文映射,会显示英文 sport_type")
        # V9.4.4 已删除 SPORT_TYPE_CN 重复真理源
        self.assertNotIn("SPORT_TYPE_CN[", body,
                         "V9.4.4 FAIL: 仍引用 SPORT_TYPE_CN[V9.4.4 已删], 应统一调 getDynamicSportMeta")
        # 不应再裸用 te.sport_type 进副标题
        self.assertNotIn("+ esc(te.sport_type) +", body,
                         "V9.4.4 FAIL: 副标题仍裸用 te.sport_type(英文),未走中文映射")

    def test_summary_uses_dedicated_class(self):
        """V9.4.4:总结用 .training-effect-summary 而非 .weather-glass-empty(字号 0.72rem 太小)"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        # 必须有 .training-effect-summary 类
        self.assertIn('"training-effect-summary"', body,
                      "V9.4.4 FAIL: 总结未用 .training-effect-summary 专属类(仍用 .weather-glass-empty 0.72rem 太小)")
        # 函数体内不应再用 .weather-glass-empty
        self.assertNotIn("weather-glass-empty", body,
                         "V9.4.4 FAIL: 训练收益总结仍用 .weather-glass-empty(0.72rem),与 UI 语义不一致")

    def test_summary_css_class_defined(self):
        """V9.4.4:.training-effect-summary CSS 必须存在且字号 ≥ 0.8rem"""
        self.assertIn(".training-effect-summary {", self.html,
                      "V9.4.4 FAIL: 缺 .training-effect-summary CSS 定义")
        idx = self.html.find(".training-effect-summary {")
        end = self.html.find("}", idx + 50)
        css = self.html[idx:end]
        # 提取 font-size
        import re
        m = re.search(r"font-size:\s*([\d.]+)\s*rem", css)
        self.assertIsNotNone(m, "V9.4.4 FAIL: .training-effect-summary 未定义 font-size")
        size = float(m.group(1))
        self.assertGreaterEqual(size, 0.8,
                                f"V9.4.4 FAIL: .training-effect-summary 字号 {size}rem 太小,应 ≥ 0.8rem 与主标签同级")

    def test_sport_type_cn_object_removed(self):
        """V9.4.4:SPORT_TYPE_CN 重复真理源已删除,统一调 getDynamicSportMeta(16+ 运动)"""
        # 全文不应再有 SPORT_TYPE_CN 对象定义
        self.assertNotIn("const SPORT_TYPE_CN = {", self.html,
                         "V9.4.4 FAIL: SPORT_TYPE_CN 对象未删除,应统一调 getDynamicSportMeta(type).label")
        # getDynamicSportMeta 必须存在
        self.assertIn("function getDynamicSportMeta(", self.html,
                      "V9.4.4 FAIL: 缺 getDynamicSportMeta 真理源函数")


class TestV9_4_4LevelLabelColorTruthSource(unittest.TestCase):
    """V9.4.4:6 等级 label/color 真理源收敛(后端 metrics_resolver + 前端 fallback)"""

    def setUp(self):
        self.html = _read_track_html()
        # 读 metrics_resolver.py(后端真理源)
        resolver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "metrics_resolver.py")
        with open(resolver_path, encoding="utf-8") as f:
            self.resolver_text = f.read()

    def test_backend_te_level_labels_cn_exists(self):
        """V9.4.4:后端 metrics_resolver._TE_LEVEL_LABELS_CN 真理源存在且 6 单元完整"""
        self.assertIn("_TE_LEVEL_LABELS_CN: dict[str, str] = {", self.resolver_text,
                      "V9.4.4 FAIL: 后端缺 _TE_LEVEL_LABELS_CN 真理源")
        for level in ("recovery", "activation", "maintenance", "improvement", "overload", "extreme"):
            self.assertIn(f'"{level}":', self.resolver_text,
                          f"V9.4.4 FAIL: _TE_LEVEL_LABELS_CN 缺 {level}")

    def test_backend_te_level_colors_exists(self):
        """V9.4.4:后端 metrics_resolver._TE_LEVEL_COLORS 真理源存在且 6 单元完整"""
        self.assertIn("_TE_LEVEL_COLORS: dict[str, str] = {", self.resolver_text,
                      "V9.4.4 FAIL: 后端缺 _TE_LEVEL_COLORS 真理源")
        for color in ("#64748b", "#3b82f6", "#06b6d4", "#22c55e", "#f97316", "#ef4444"):
            self.assertIn(color, self.resolver_text,
                          f"V9.4.4 FAIL: _TE_LEVEL_COLORS 缺色 {color}")

    def test_backend_build_training_effect_returns_truth_source(self):
        """V9.4.4:build_training_effect 返回 dict 含 level_labels_cn / level_colors"""
        try:
            import sys
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from metrics_resolver import build_training_effect
        except Exception as e:
            self.skipTest(f"metrics_resolver 导入失败: {e}")
        result = build_training_effect(
            {"aerobic_training_effect": 4.2, "anaerobic_training_effect": 2.1},
            "running",
        )
        self.assertIsNotNone(result, "V9.4.4 FAIL: TE 数据应为非 None")
        self.assertIn("level_labels_cn", result, "V9.4.4 FAIL: build_training_effect 缺 level_labels_cn 透传")
        self.assertIn("level_colors", result, "V9.4.4 FAIL: build_training_effect 缺 level_colors 透传")
        self.assertEqual(len(result["level_labels_cn"]), 6, "V9.4.4 FAIL: level_labels_cn 必须 6 单元")
        self.assertEqual(len(result["level_colors"]), 6, "V9.4.4 FAIL: level_colors 必须 6 单元")

    def test_frontend_consumes_backend_truth_source_with_fallback(self):
        """V9.4.4:前端 _buildTrainingBenefitCard 优先读 te.level_colors / te.level_labels_cn,fallback 到本地"""
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("te.level_colors", body,
                      "V9.4.4 FAIL: 前端未优先读后端透传的 te.level_colors")
        self.assertIn("te.level_labels_cn", body,
                      "V9.4.4 FAIL: 前端未优先读后端透传的 te.level_labels_cn")
        # fallback 真理源必须保留(防老 API 退化)
        self.assertIn("_TE_LEVEL_COLORS", body,
                      "V9.4.4 FAIL: 前端 _TE_LEVEL_COLORS fallback 已删, 老 API 退化会黑屏")
        self.assertIn("_TE_LEVEL_LABELS_CN", body,
                      "V9.4.4 FAIL: 前端 _TE_LEVEL_LABELS_CN fallback 已删, 老 API 退化会黑屏")


if __name__ == "__main__":
    unittest.main()
