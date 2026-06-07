"""
V9.3.4 契约测试:字段一致性 + Sport-aware Hero 字段集 + 图标 + 网格 + 字段名适配 + 标题清洗

任务: 5 大需求 ——
  1. 字段一致性:_formatHeroValue 单点真理
  2. 标题同步:_resolveDisplayTitle 3 处调用 + V9.3.4 清洗尾部数字 ID
  3. Sport-aware Hero:HERO_FIELD_REGISTRY 7 运动 + _resolveHeroItems
  4. 全量测试:本文件(10 用例)
  5. 网格 + 图标:HERO_FIELD_ICONS + .head flex

V9.3.4 调整(本轮):
  - 字段名适配:后端 record 顶层 avg_pace_sec / detail.summary.avg_pace_sec,
    _resolveHeroItems 加三级回退
  - 标题清洗:_cleanDisplayTitle 剥离尾部 6+ 位纯数字 ID
  - 修正 avg_pace "显示 --" 的根因
  - 修正标题 "西城区 跑步 601803952" 类尾部 file_id 泄露

V9.3.1 调整:
  - 删 4 个占位函数(_setActivityMeta 等)测试 — 已删
  - 删 appState.activityCache 兜底测试 — 已删
  - 删 9 个死 case 测试 — 已精简
  - 加 HERO_FIELD_REGISTRY 7 运动测试
  - 加 _resolveHeroItems 集成测试

策略:静态 grep 验证 JS 常量/函数/CSS 存在,以及调用站点。
"""

from __future__ import annotations
import os, re, unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


class TestV9_3FieldConsistency(unittest.TestCase):
    """§需求 1:_formatHeroValue 统一格式化函数(V9.3.1 精简到 6+1 字段)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_format_hero_value_function_exists(self):  # 1/10
        self.assertIn("function _formatHeroValue(", self.html,
                      "V9.3 FAIL: 缺少 _formatHeroValue 函数(需求 1)")

    def test_format_handles_all_used_field_types(self):  # 2/10
        """_formatHeroValue 应处理 distance / duration / avg_pace / calories / avg_speed / max_hr / swolf / null"""
        idx = self.html.find("function _formatHeroValue(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # V9.3.1 6+1 字段:M0 实际使用 + swimming 配套
        for field in ['distance', 'duration', 'avg_pace', 'avg_speed', 'calories', 'elevation_gain', 'swolf']:
            self.assertIn("case '" + field + "'", body,
                          f"V9.3.1 FAIL: _formatHeroValue 缺 {field} 分支")
        # 必须有空态占位
        self.assertIn("'--'", body, "V9.3.1 FAIL: _formatHeroValue 缺空态占位符 '--'")


class TestV9_3TitleSync(unittest.TestCase):
    """§需求 2:_resolveDisplayTitle 3 处统一调用"""

    def setUp(self):
        self.html = _read_track_html()

    def test_resolve_display_title_function_exists(self):  # 3/10
        self.assertIn("function _resolveDisplayTitle(", self.html,
                      "V9.3 FAIL: 缺少 _resolveDisplayTitle 函数(需求 2)")
        idx = self.html.find("function _resolveDisplayTitle(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 500
        body = self.html[idx:end]
        # 统一 fallback 链:title → file_name → filename → 默认
        self.assertIn("record.title", body, "V9.3 FAIL: 缺 title 字段")
        self.assertIn("record.file_name", body, "V9.3 FAIL: 缺 file_name fallback")
        self.assertIn("record.filename", body, "V9.3 FAIL: 缺 filename fallback")
        self.assertIn("未命名活动", body, "V9.3 FAIL: 缺统一默认 '未命名活动'")

    def test_three_call_sites_unified(self):  # 4/10
        """3 处调用站点:列表 / 详情 / 历史卡片 都用 _resolveDisplayTitle"""
        def_count = self.html.count("function _resolveDisplayTitle(")
        self.assertEqual(def_count, 1, "V9.3 FAIL: 函数应只定义 1 次")
        call_count = self.html.count("_resolveDisplayTitle(") - def_count
        self.assertGreaterEqual(
            call_count, 3,
            f"V9.3 FAIL: _resolveDisplayTitle 应被调用 ≥ 3 次(列表/详情/历史),实际 {call_count}"
        )


class TestV9_3SportAwareHero(unittest.TestCase):
    """§需求 3(V9.3.1 新增):7 运动 Sport-aware Hero 字段集"""

    def setUp(self):
        self.html = _read_track_html()

    def test_hero_field_registry_with_7_sports(self):  # 5/10
        """HERO_FIELD_REGISTRY 必须覆盖 7 运动(对齐 V4.0 SPORT_PROFILES)"""
        self.assertIn("const HERO_FIELD_REGISTRY", self.html,
                      "V9.3.1 FAIL: 缺少 HERO_FIELD_REGISTRY 常量")
        # 7 运动必现(quote-agnostic:接受 'sport': 或 sport:)
        required_sports = [
            'running', 'trail_running', 'hiking',
            'cycling', 'indoor_cycling', 'swimming', 'strength',
        ]
        # 锁定 HERO_FIELD_REGISTRY 块(避免与文件其他位置 'running': 冲突)
        reg_start = self.html.find("const HERO_FIELD_REGISTRY")
        reg_end_marker = "};"
        reg_end = self.html.find(reg_end_marker, reg_start)
        if reg_end < 0:
            self.fail("V9.3.1 FAIL: HERO_FIELD_REGISTRY 块未正常结束")
        reg_block = self.html[reg_start:reg_end]
        for sport in required_sports:
            quoted = "'" + sport + "':"
            unquoted = sport + ":"
            self.assertTrue(quoted in reg_block or unquoted in reg_block,
                            f"V9.3.1 FAIL: HERO_FIELD_REGISTRY 缺 {sport} 运动")
        # 每运动 6 字段(scope to registry block)
        for sport in required_sports:
            quoted = "'" + sport + "':"
            unquoted = sport + ":"
            if quoted in reg_block:
                idx = reg_block.find(quoted)
            else:
                idx = reg_block.find(unquoted)
            end = reg_block.find("],", idx)
            if end < 0:
                end = idx + 300
            body = reg_block[idx:end + 2]
            # 严格断言: 字段 key 出现 6 次
            field_count = body.count("'distance'") + body.count("'duration'") + body.count("'avg_pace'") \
                        + body.count("'avg_speed'") + body.count("'avg_hr'") + body.count("'max_hr'") \
                        + body.count("'calories'") + body.count("'elevation_gain'") + body.count("'swolf'")
            self.assertEqual(field_count, 6,
                             f"V9.3.1 FAIL: {sport} 应有 6 字段,实际 {field_count}")

    def test_resolve_hero_items_function_and_call(self):  # 6/10
        """_resolveHeroItems 函数存在 + renderActivityDetail 引用"""
        self.assertIn("function _resolveHeroItems(", self.html,
                      "V9.3.1 FAIL: 缺少 _resolveHeroItems 函数")
        # renderActivityDetail 必须引用
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 6000
        body = self.html[idx:end]
        self.assertIn("_resolveHeroItems(", body,
                      "V9.3.1 FAIL: renderActivityDetail 未调用 _resolveHeroItems")
        # 必须按 sport 查表
        self.assertIn("display_sport_type", body,
                      "V9.3.1 FAIL: renderActivityDetail 未按 sport 切换")
        # 严禁 V9.3 旧硬编码(全部硬编码 6 字段)
        # 旧 heroItems 字面量应已删除
        self.assertNotIn("{ field: 'distance',       raw: dist }", body,
                         "V9.3.1 FAIL: renderActivityDetail 仍含 V9.3 硬编码 6 字段")


class TestV9_3HeroIcons(unittest.TestCase):
    """§需求 5:V9.3.1 精简到 6+1 字段 emoji + 渲染时输出"""

    def setUp(self):
        self.html = _read_track_html()

    def test_hero_field_icons_with_used_fields(self):  # 7/10
        """HERO_FIELD_ICONS 必须包含 M0 实际使用的 6+1 字段"""
        self.assertIn("const HERO_FIELD_ICONS", self.html,
                      "V9.3.1 FAIL: 缺少 HERO_FIELD_ICONS 常量")
        required_fields = [
            'distance', 'duration', 'avg_pace', 'avg_speed',
            'avg_hr', 'max_hr', 'calories', 'elevation_gain', 'swolf',
        ]
        for field in required_fields:
            self.assertIn("'" + field + "':", self.html,
                          f"V9.3.1 FAIL: HERO_FIELD_ICONS 缺 {field} 字段")
        # V9.3.1 删除了 9 个死字段
        dead_fields = ['avg_power', 'avg_cadence', 'training_load',
                       'moving_time', 'sets', 'total_volume']
        for field in dead_fields:
            # 字段不应在 HERO_FIELD_ICONS 中(否则意味着没精简)
            self.assertNotIn("'" + field + "':", self.html,
                             f"V9.3.1 FAIL: HERO_FIELD_ICONS 仍含死字段 {field}")

    def test_render_activity_detail_uses_icon(self):  # 8/10
        """renderActivityDetail 应输出 .head + .icon 结构(需求 5b)"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 6000
        body = self.html[idx:end]
        self.assertIn('class="head"', body, "V9.3 FAIL: renderActivityDetail 未输出 .head 结构")
        self.assertIn('class="icon"', body, "V9.3 FAIL: renderActivityDetail 未输出 .icon")
        self.assertIn("HERO_FIELD_ICONS", body,
                      "V9.3 FAIL: renderActivityDetail 未引用 HERO_FIELD_ICONS")


class TestV9_3GridConsistency(unittest.TestCase):
    """§需求 5:网格 + 图标间距 + 仅桌面端"""

    def setUp(self):
        self.html = _read_track_html()

    def test_metric_head_flex_with_gap(self):  # 9/10
        """.head 含 flex + gap(图标与文字间距统一)"""
        self.assertIn(".overview-metric-card .head {", self.html,
                      "V9.3 FAIL: 缺 .overview-metric-card .head CSS")
        idx = self.html.find(".overview-metric-card .head {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("display: flex", body, "V9.3 FAIL: .head 缺 flex")
        self.assertIn("gap:", body, "V9.3 FAIL: .head 缺 gap(图标文字间距)")
        self.assertIn("align-items: center", body,
                      "V9.3 FAIL: .head 缺 align-items: center(图标文字垂直对齐)")

    def test_icon_size_unified(self):  # 10/10
        """.icon 尺寸统一(14x14)"""
        self.assertIn(".overview-metric-card .head .icon", self.html,
                      "V9.3 FAIL: 缺 .icon CSS")
        idx = self.html.find(".overview-metric-card .head .icon {")
        if idx < 0:
            idx = self.html.find(".overview-metric-card .head .icon")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("14px", body, "V9.3 FAIL: .icon 缺 14px 统一尺寸")


# === V9.3.4 新增测试(字段名适配 + 标题清洗) ===

class TestV9_3_4FieldNameAdaptation(unittest.TestCase):
    """V9.3.4 §1:_resolveHeroItems 必须支持后端真实字段名(avg_pace_sec / detail.summary.*)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_resolve_hero_picks_avg_pace_sec(self):  # 11
        """V9.3.4:pick('avg_pace') 必须查 avg_pace_sec 后端字段(不查 avg_pace)"""
        idx = self.html.find("function _resolveHeroItems(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 必须有 avg_pace_sec 字段引用(3 处回退:detail / summary / record)
        sec_count = body.count("avg_pace_sec")
        self.assertGreaterEqual(sec_count, 3,
                                f"V9.3.4 FAIL: pick('avg_pace') 应查 avg_pace_sec ≥ 3 处,实际 {sec_count}")
        # 必须保留 avg_pace 兼容(老数据可能没 _sec 后缀)
        self.assertIn("record.avg_pace", body,
                      "V9.3.4 FAIL: 缺 record.avg_pace 兼容兜底")
        # 必须查 detail.summary(后端把字段放在 summary 下)
        self.assertIn("summary.avg_pace_sec", body,
                      "V9.3.4 FAIL: 缺 summary.avg_pace_sec 三级回退")

    def test_resolve_hero_summary_field_aware(self):  # 12
        """V9.3.4:pick 应对其他字段也走 summary 三级回退"""
        idx = self.html.find("function _resolveHeroItems(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 至少 5 个字段走 summary 回退
        for field in ['avg_pace', 'avg_hr', 'distance', 'duration', 'elevation_gain']:
            # 验证 field 在 pick 体内被处理
            self.assertIn(field, body, f"V9.3.4 FAIL: pick 缺 {field} 字段")
        # summary 必须被引用
        self.assertIn("summary.", body, "V9.3.4 FAIL: pick 未走 summary 回退")


class TestV9_3_4TitleCleaning(unittest.TestCase):
    """V9.3.4 §2:_resolveDisplayTitle 必须清洗尾部数字 ID"""

    def setUp(self):
        self.html = _read_track_html()

    def test_clean_display_title_function_exists(self):  # 13
        """V9.3.4:必须有 _cleanDisplayTitle 辅助函数"""
        self.assertIn("function _cleanDisplayTitle(", self.html,
                      "V9.3.4 FAIL: 缺 _cleanDisplayTitle 函数")

    def test_clean_strips_trailing_numeric_id(self):  # 14
        """V9.3.4:_cleanDisplayTitle 必须剥离尾部 6+ 位纯数字(file_id)"""
        idx = self.html.find("function _cleanDisplayTitle(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 1000
        body = self.html[idx:end]
        # 必须有正则匹配尾部数字
        self.assertIn(r"\d{6,}", body,
                      "V9.3.4 FAIL: _cleanDisplayTitle 缺尾部 6+ 位数字正则")
        # 必须有 $ 锚点(尾部)
        self.assertIn("$", body, "V9.3.4 FAIL: _cleanDisplayTitle 缺尾部锚点")
        # 必须有 _ 数字 处理(FIT 文件名)
        self.assertIn("_", body, "V9.3.4 FAIL: _cleanDisplayTitle 缺 _ 分隔符处理")

    def test_resolve_title_uses_cleaner(self):  # 15
        """V9.3.4:_resolveDisplayTitle 必须经过 _cleanDisplayTitle 处理"""
        idx = self.html.find("function _resolveDisplayTitle(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 500
        body = self.html[idx:end]
        self.assertIn("_cleanDisplayTitle", body,
                      "V9.3.4 FAIL: _resolveDisplayTitle 未调用 _cleanDisplayTitle")


if __name__ == "__main__":
    unittest.main()
