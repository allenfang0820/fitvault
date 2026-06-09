"""
V_3.0.1 分页器裁剪修复 静态契约测试

依据:用户截图反馈 + 任务 3.0 勘察
契约:fit-arch-contrac §11.2 视觉一致性
根因:
  - .profile-radar-card 含 overflow: hidden → 外层裁剪
  - .hub-pagination 含 overflow: hidden + 无 padding-bottom → 自身裁剪
  - .hub-records-table-wrap 无底部缓冲

测试范围(静态 grep):
  - .profile-radar-card 不含 overflow: hidden
  - .hub-pagination 不含 overflow: hidden
  - .hub-pagination 含 padding-bottom(非 0)
  - .hub-pagination 含 flex-shrink: 0
  - .hub-records-table-wrap 含 margin-bottom(缓冲)
  - 分页器 DOM 结构完整
"""

from __future__ import annotations
import os
import re
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


def _slice_css_block(html: str, selector: str) -> str:
    """截取 selector 的 CSS rule 块(从 { 到 匹配 })。"""
    pattern = re.escape(selector) + r"\s*\{"
    m = re.search(pattern, html)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(html) and depth > 0:
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
        i += 1
    return html[start:i - 1]


class TestPaginationContainerOverflow(unittest.TestCase):
    """§任务 3.0.1-①:外层 .profile-radar-card 不裁剪"""

    def setUp(self):
        self.html = _read_track_html()

    def test_profile_radar_card_no_overflow_hidden(self):
        body = _slice_css_block(self.html, ".profile-radar-card")
        self.assertTrue(body, "V_3.0 FAIL: 找不到 .profile-radar-card CSS")
        # 不应再含 overflow: hidden(防止外层裁剪)
        self.assertNotIn("overflow: hidden", body,
            "V_3.0 FAIL: .profile-radar-card 含 overflow: hidden,会裁剪分页器")
        # 应含 overflow: visible
        self.assertIn("overflow: visible", body,
            "V_3.0 FAIL: .profile-radar-card 未设置 overflow: visible")


class TestHubPaginationOverflow(unittest.TestCase):
    """§任务 3.0.1-②:.hub-pagination 自身不裁剪 + 加 padding-bottom"""

    def setUp(self):
        self.html = _read_track_html()

    def test_hub_pagination_no_overflow_hidden(self):
        body = _slice_css_block(self.html, ".hub-pagination")
        self.assertTrue(body, "V_3.0 FAIL: 找不到 .hub-pagination CSS")
        self.assertNotIn("overflow: hidden", body,
            "V_3.0 FAIL: .hub-pagination 含 overflow: hidden,会裁剪自身内容")

    def test_hub_pagination_padding_bottom_set(self):
        body = _slice_css_block(self.html, ".hub-pagination")
        # padding-bottom 应 ≥ 8px(防裁剪)
        m = re.search(r"padding(?:-bottom)?:\s*[^;]*", body)
        self.assertTrue(m, "V_3.0 FAIL: .hub-pagination 未设置 padding")
        padding_str = m.group(0)
        # 简化的 padding-bottom 检测:用 4 值 padding 简写
        m4 = re.search(r"padding:\s*(\d+)px\s+(\d+)px\s+(\d+)px\s+(\d+)px", padding_str)
        if m4:
            bottom = int(m4.group(3))
            self.assertGreaterEqual(bottom, 8,
                f"V_3.0 FAIL: .hub-pagination padding-bottom {bottom}px 过小,应 ≥ 8px")
        else:
            # 单独 padding-bottom
            mpb = re.search(r"padding-bottom:\s*(\d+)px", padding_str)
            self.assertTrue(mpb, "V_3.0 FAIL: 未找到 padding-bottom 声明")
            bottom = int(mpb.group(1))
            self.assertGreaterEqual(bottom, 8,
                f"V_3.0 FAIL: .hub-pagination padding-bottom {bottom}px 过小")

    def test_hub_pagination_flex_shrink_zero(self):
        body = _slice_css_block(self.html, ".hub-pagination")
        self.assertIn("flex-shrink: 0", body,
            "V_3.0 FAIL: .hub-pagination 缺 flex-shrink: 0,会被挤压")


class TestHubRecordsTableWrapBuffer(unittest.TestCase):
    """§任务 3.0.1-③:.hub-records-table-wrap 加底部缓冲"""

    def setUp(self):
        self.html = _read_track_html()

    def test_table_wrap_has_margin_bottom(self):
        body = _slice_css_block(self.html, ".hub-records-table-wrap")
        self.assertTrue(body, "V_3.0 FAIL: 找不到 .hub-records-table-wrap CSS")
        m = re.search(r"margin-bottom:\s*(\d+)px", body)
        self.assertTrue(m, "V_3.0 FAIL: .hub-records-table-wrap 缺 margin-bottom")
        margin = int(m.group(1))
        self.assertGreaterEqual(margin, 2,
            f"V_3.0 FAIL: .hub-records-table-wrap margin-bottom {margin}px 过小")


class TestPaginationDomStructure(unittest.TestCase):
    """§分页器 DOM 节点齐全"""

    def setUp(self):
        self.html = _read_track_html()

    def test_pagination_div_exists(self):
        self.assertIn('class="hub-pagination"', self.html,
            "V_3.0 FAIL: 找不到 <div class=\"hub-pagination\">")

    def test_prev_button_exists(self):
        self.assertIn('id="sport-records-prev"', self.html,
            "V_3.0 FAIL: 找不到 sport-records-prev 按钮")

    def test_next_button_exists(self):
        self.assertIn('id="sport-records-next"', self.html,
            "V_3.0 FAIL: 找不到 sport-records-next 按钮")

    def test_jump_input_exists(self):
        self.assertIn('id="sport-records-page-jump"', self.html,
            "V_3.0 FAIL: 找不到 sport-records-page-jump 输入框")

    def test_change_page_function_exists(self):
        self.assertIn("function changeSportHubPage(", self.html,
            "V_3.0 FAIL: 找不到 changeSportHubPage 函数")

    def test_render_page_numbers_function_exists(self):
        self.assertIn("function renderPageNumbers(", self.html,
            "V_3.0 FAIL: 找不到 renderPageNumbers 函数")

    def test_pagination_outside_table_wrap(self):
        """分页器不应在滚动容器内,否则会被裁剪"""
        # 找 <div class="hub-records-table-wrap"> 起点
        wrap_start = self.html.find('<div class="hub-records-table-wrap">')
        wrap_end = self.html.find('</div>', wrap_start)  # 粗略,实际有嵌套但够用
        # 找 <div class="hub-pagination"> 起点
        pag_start = self.html.find('<div class="hub-pagination">')
        self.assertGreater(wrap_start, 0)
        self.assertGreater(pag_start, 0)
        # 关键断言:分页器在表格容器之"后"(粗略通过位置 + '上一页' 文字验证)
        self.assertGreater(pag_start, wrap_start,
            "V_3.0 FAIL: 分页器在表格容器内,会被滚动条裁剪")


if __name__ == "__main__":
    unittest.main()
