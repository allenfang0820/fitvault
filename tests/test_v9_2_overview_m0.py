"""
V9.2.3 契约测试:概览 Tab 2x2 grid 重构(头部去 × / 3x2 metric / 主视觉地图 / 4 张侧栏卡 / Tab Bar sticky / 滚动 + padding)

任务(V9.2.3): 用户确认草图后的最终布局
  - 2x2 grid:左列(2fr) Hero + Map 垂直堆叠,右列(1fr) 4 张卡垂直堆叠跨 Hero+Map 整个高度
  - Hero 区与 Map 区等宽
  - 启用 modal 垂直滚动(原 overflow:hidden 改为 overflow-y:auto)
  - 增大 modal padding 到 28px(原 22px)给最右列卡片留视觉缓冲

V9.2.2 继承:
  - Tab Bar sticky 固定
  - 4 张侧栏卡(环境/训练收益/身体状态/活动摘要)
  - 3 张新卡数据源延后解决,M0 占位文案
  - 圈速统计在 Map 下方(左列内)

V9.2 M0 保留:
  - 头部去 × 关闭按钮
  - 3x2 metric grid
  - 主视觉地图(放大版)

契约依据 (fit-arch-contrac):
- §3 统一响应结构 {code, msg, data, traceId}
- §5.4 AI 边界 / §五 UI 风格
- §六 shadow_diff 隔离(renderActivityDetailSidebar 渲染前校验)

策略: 静态 grep 测试 track.html 改动完整性 + 后端零变更校验。
"""

from __future__ import annotations

import os
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


class TestV9_2HeaderSimplification(unittest.TestCase):
    """§E01 头部去掉 × 关闭按钮(决策 1)"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_close_button_removed(self):
        """× 关闭按钮必须已删除(决策 1)"""
        self.assertNotIn('class="activity-detail-close"', self.html,
                         "V9.2 FAIL: × 关闭按钮应已删除")

    def test_back_button_preserved(self):
        """V9.2.1:返回按钮保留(移至标题左侧,仅 < 标识)"""
        self.assertIn('class="activity-detail-back"', self.html,
                      "V9.2.1 FAIL: 返回按钮 class 应保留")
        self.assertIn('&lt;', self.html,
                      "V9.2.1 FAIL: 返回按钮文案应为 < 字符")

    def test_back_button_moved_to_left(self):
        """V9.2.1:返回按钮应在标题左侧(head-row 内,不在 head-actions)"""
        # 整个详情 Modal head 不应再有 head-actions 容器
        self.assertNotIn('class="activity-detail-head-actions"', self.html,
                         "V9.2.1 FAIL: head-actions 容器应已删除")
        # 返回按钮应在 head-row 内(title="返回活动列表" 标记)
        self.assertIn('title="返回活动列表"', self.html,
                      "V9.2.1 FAIL: 返回按钮 title 应保留")

    def test_old_back_button_text_removed(self):
        """V9.2.1:旧「← 返回活动列表」长文案应已删除"""
        self.assertNotIn('← 返回活动列表', self.html,
                         "V9.2.1 FAIL: 旧 ← 返回活动列表 文案应已删除")

    def test_close_modal_function_preserved(self):
        """closeActivityDetailModal 函数应保留(ESC + backdrop 关闭依赖)"""
        self.assertIn("function closeActivityDetailModal(", self.html,
                      "V9.2 FAIL: closeActivityDetailModal 应保留")

    def test_overlay_backdrop_close_preserved(self):
        """backdrop 点击关闭逻辑应保留"""
        self.assertIn('if(event.target===this) closeActivityDetailModal()', self.html,
                      "V9.2 FAIL: backdrop 点击关闭应保留")


class TestV9_2MetricsGrid(unittest.TestCase):
    """§E05-E10 3x2 metric grid(6 个固定卡片)"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_overview_metrics_grid_class_exists(self):
        """.overview-metrics-grid 容器必须存在"""
        self.assertIn('class="overview-metrics-grid"', self.html,
                      "V9.2 FAIL: 缺少 .overview-metrics-grid 容器")

    def test_overview_metric_card_class_exists(self):
        """.overview-metric-card 必须存在"""
        self.assertIn('class="overview-metric-card"', self.html,
                      "V9.2 FAIL: 缺少 .overview-metric-card")

    def test_metrics_container_id_preserved(self):
        """#activity-detail-metrics 容器 id 应保留(兼容 V9.0)"""
        self.assertIn('id="activity-detail-metrics"', self.html,
                      "V9.2 FAIL: #activity-detail-metrics 容器 id 应保留")

    def test_six_metric_labels(self):
        """6 个 metric 标签必须就位"""
        labels = ['距离', '时长', '平均配速', '平均心率', '热量消耗', '累计爬升']
        for lbl in labels:
            self.assertIn(lbl, self.html,
                          f"V9.2 FAIL: 缺少 metric 标签 '{lbl}'")

    def test_no_old_detail_metric_class(self):
        """V9.0 旧 .detail-metric 类应被替换(M0 不再用)"""
        # 旧 class 仍可能出现在生成的 HTML 字符串里(renderActivityDetail 用)
        # 但 CSS 类应已被 .overview-metric-card 替代
        # 这里只检查 CSS 定义是否还存在
        self.assertNotIn('.detail-metric {', self.html,
                         "V9.2 FAIL: 旧 .detail-metric CSS 不应再定义")


class TestV9_2MainVisual(unittest.TestCase):
    """§E11 轨迹地图升级为主视觉"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_overview_main_visual_class(self):
        """.overview-main-visual 必须存在"""
        self.assertIn('class="overview-main-visual"', self.html,
                      "V9.2 FAIL: 缺少 .overview-main-visual")

    def test_overview_main_grid_class(self):
        """V9.2.3:.overview-2x2 2x2 grid 必须存在(替代 V9.2 的 .overview-main-grid)"""
        self.assertIn('class="overview-2x2"', self.html,
                      "V9.2.3 FAIL: 缺少 .overview-2x2 2x2 grid 容器")

    def test_track_section_in_main_visual(self):
        """#activity-detail-track-section 仍应保留(id 不变)"""
        self.assertIn('id="activity-detail-track-section"', self.html,
                      "V9.2 FAIL: #activity-detail-track-section id 应保留")
        self.assertIn('id="activity-detail-track-container"', self.html,
                      "V9.2 FAIL: #activity-detail-track-container id 应保留")

    def test_main_visual_click_to_trace(self):
        """主视觉点击触发 jumpToTraceFromActivityDetail"""
        # 验证 trackContainer 内的 onclick 包含该函数
        # renderActivityDetail 函数体内调用 jumpToTraceFromActivityDetail
        idx = self.html.find("function renderActivityDetail(")
        self.assertGreater(idx, 0, "缺少 renderActivityDetail 函数")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("jumpToTraceFromActivityDetail", body,
                      "V9.2 FAIL: 主视觉未绑定 jumpToTraceFromActivityDetail")


class TestV9_2SidebarEnvironment(unittest.TestCase):
    """§E12a 侧栏环境卡(温度 + 湿度 + 状况)"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_sidebar_container_exists(self):
        """#activity-detail-sidebar 必须存在"""
        self.assertIn('id="activity-detail-sidebar"', self.html,
                      "V9.2 FAIL: 缺少 #activity-detail-sidebar 容器")

    def test_render_activity_detail_weather_function(self):
        """renderActivityDetailWeather 函数必须存在"""
        self.assertIn("function renderActivityDetailWeather(", self.html,
                      "V9.2 FAIL: 缺少 renderActivityDetailWeather 函数")

    def test_sidebar_card_css_class(self):
        """.sidebar-card CSS 必须存在"""
        self.assertIn(".sidebar-card {", self.html,
                      "V9.2 FAIL: 缺少 .sidebar-card CSS")

    def test_weather_card_no_aqi_no_wind(self):
        """M0 不渲染 AQI / 风向(决策 2)"""
        idx = self.html.find("function renderActivityDetailWeather(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertNotIn("AQI", body, "V9.2 FAIL: M0 不应渲染 AQI(决策 2)")
        self.assertNotIn("wind_direction", body, "V9.2 FAIL: M0 不应渲染 wind_direction(决策 2)")
        self.assertNotIn("wind_level", body, "V9.2 FAIL: M0 不应渲染 wind_level(决策 2)")

    def test_weather_card_renders_temperature_humidity(self):
        """V9.2.4:环境卡应包含温度 + 湿度 + 风速 + 状况(4 字段,玻璃态 2x2)"""
        weather_card_idx = self.html.find("function _buildWeatherCard(")
        if weather_card_idx > 0:
            idx = weather_card_idx
        else:
            idx = self.html.find("function renderActivityDetailWeather(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("temperature_c", body, "V9.2.4 FAIL: 环境卡未渲染温度")
        self.assertIn("humidity", body, "V9.2.4 FAIL: 环境卡未渲染湿度")
        self.assertIn("wind_speed_kmh", body, "V9.2.4 FAIL: 环境卡未渲染风速")
        self.assertIn("weather_label", body, "V9.2.4 FAIL: 环境卡未渲染状况")

    def test_shadow_diff_isolation_in_weather_render(self):
        """环境卡渲染前应有 shadow_diff 校验(§六 隔离)
        V9.2.2:实现移入 renderActivityDetailSidebar,旧函数改为 shim"""
        sidebar_idx = self.html.find("function renderActivityDetailSidebar(")
        weather_idx = self.html.find("function renderActivityDetailWeather(")
        # 优先用新函数
        idx = sidebar_idx if sidebar_idx > 0 else weather_idx
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.2 FAIL: 环境卡渲染缺 §六 shadow_diff 校验")


class TestV9_2SubtitleInlineWeather(unittest.TestCase):
    """§E03 副标题内嵌天气(决策 4)"""

    def setUp(self) -> None:
        self.html = _read_track_html()

    def test_subtitle_inline_weather_when_available(self):
        """V9.2.5:副标题应读 record.weather(活动专属),不再读全局 appState 缓存"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # V9.2.5 数据源从全局切到 record.weather
        self.assertIn("record.weather", body,
                      "V9.2.5 FAIL: 副标题未读 record.weather(活动专属)")
        self.assertIn("normalizeWeatherData", body,
                      "V9.2.5 FAIL: 副标题未经过 normalizeWeatherData 标准化")
        self.assertNotIn("appState.currentWeather", body,
                         "V9.2.5 FAIL: 副标题仍读全局 weather 缓存(应改为 record.weather)")
        self.assertIn("temperature_c", body,
                      "V9.2 FAIL: 副标题未内嵌温度")

    def test_subtitle_uses_device_name(self):
        """副标题应包含设备名"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("device_name", body,
                      "V9.2 FAIL: 副标题未使用 device_name(决策 4)")

    def test_subtitle_uses_region_display(self):
        """副标题应使用 sportHubRegionDisplay 函数(优先于 record.region)"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("sportHubRegionDisplay", body,
                      "V9.2 FAIL: 副标题未用 sportHubRegionDisplay(地区降级)")

    def test_close_resets_subtitle(self):
        """closeActivityDetailModal 应重置副标题(防残留)"""
        idx = self.html.find("function closeActivityDetailModal(")
        self.assertGreater(idx, 0)
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 2000
        body = self.html[idx:end]
        self.assertIn("subtitle.innerText", body,
                      "V9.2 FAIL: closeActivityDetailModal 未重置副标题")


class TestV9_2NoBackendModification(unittest.TestCase):
    """M0 决策:0 改动 main.py / llm_backend.py"""

    def test_main_py_unchanged(self):
        with open(os.path.join(_PROJECT_ROOT, "main.py"), encoding="utf-8") as f:
            main = f.read()
        self.assertNotIn("V9.2", main,
                         "V9.2 FAIL: main.py 不应有 V9.2 标记(后端零变更)")

    def test_llm_backend_py_unchanged(self):
        with open(os.path.join(_PROJECT_ROOT, "llm_backend.py"), encoding="utf-8") as f:
            llm = f.read()
        self.assertNotIn("V9.2", llm,
                         "V9.2 FAIL: llm_backend.py 不应有 V9.2 标记")


# === V9.2.2 新增测试类 ===

class TestV9_2_2TabBarSticky(unittest.TestCase):
    """V9.2.2 §E-T1:Tab Bar sticky 固定"""

    def setUp(self):
        self.html = _read_track_html()

    def test_tab_bar_outside_head(self):
        """V9.2.2:Tab Bar 必须从 .activity-detail-head 抽出,作为 modal 直接子级"""
        # 1. Tab Bar 必须在 modal 内
        modal_idx = self.html.find("activity-detail-modal")
        tab_bar_idx = self.html.find('id="detail-tab-bar"')
        head_idx = self.html.find("activity-detail-head")
        # 顺序:modal 之后,head 关闭之后
        self.assertGreater(tab_bar_idx, modal_idx,
                           "V9.2.2 FAIL: Tab Bar 不在 modal 内")
        # 2. head 关闭标签在 Tab Bar 之前(Tab Bar 已抽出)
        head_close_idx = self.html.find("</div>", head_idx)
        # 检查 Tab Bar 是否在 head 关闭之前
        head_open_idx = self.html.find("<div class=\"activity-detail-head\"", head_idx)
        if head_open_idx < 0:
            head_open_idx = head_idx
        head_end = self.html.find("</div>", head_idx)
        # Tab Bar 必须在 head_end 之后
        self.assertGreater(tab_bar_idx, head_end,
                           "V9.2.2 FAIL: Tab Bar 仍嵌套在 .activity-detail-head 内")

    def test_tab_bar_sticky_css(self):
        """V9.2.2:.detail-tab-bar 必须含 sticky 定位(找 V9.2.2 新块,跳过 V9.1 旧块)"""
        # V9.2.2 新块有唯一注释标记 "V9.2.2:Tab Bar 提到 head 外,sticky 固定"
        # 旧 V9.1 块用 background: linear-gradient,新块用 backdrop-filter
        # 用注释锚点定位新块
        marker = "V9.2.2:Tab Bar 提到 head 外"
        marker_idx = self.html.find(marker)
        idx = -1
        if marker_idx >= 0:
            # 从 marker 之后找最近的 .detail-tab-bar {(新块在 marker 之后)
            idx = self.html.find(".detail-tab-bar {", marker_idx)
        if idx < 0:
            # 后备:找含 "position: sticky" 的 .detail-tab-bar 块
            search_from = 0
            while True:
                idx = self.html.find(".detail-tab-bar {", search_from)
                if idx < 0:
                    self.fail("V9.2.2 FAIL: 找不到任何 .detail-tab-bar CSS 块")
                end = self.html.find("}", idx + 50)
                body = self.html[idx:end]
                if "position: sticky" in body:
                    break
                search_from = idx + 1
        else:
            end = self.html.find("}", idx + 50)
            body = self.html[idx:end]
        self.assertIn("position: sticky", body,
                      "V9.2.2 FAIL: V9.2.2 新 .detail-tab-bar 块缺 position: sticky")
        self.assertIn("top:", body, "V9.2.2 FAIL: V9.2.2 新块缺 top")
        self.assertIn("z-index:", body, "V9.2.2 FAIL: V9.2.2 新块缺 z-index")


class TestV9_2_3LapStatsUnderMap(unittest.TestCase):
    """V9.2.3 §E-T2:圈速统计贴图(在 Map 区下方,左列内)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_map_area_wrapper_exists(self):
        """V9.2.3:必须新增 .overview-map-area 包裹层(图+圈速)"""
        self.assertIn("overview-map-area", self.html,
                      "V9.2.3 FAIL: 缺 .overview-map-area 包裹层")

    def test_laps_inside_map_area(self):
        """V9.2.3:.overview-laps 必须在 .overview-map-area 内(贴图)"""
        map_open = self.html.find('class="overview-map-area"')
        self.assertGreater(map_open, 0, "V9.2.3 FAIL: 缺 .overview-map-area")
        # 在 map-area 起始和 grid 结束之间,必须含 .overview-laps
        # 找 .overview-2x2 结束
        grid_block_end = self.html.find("</div>\n            </div>", map_open)  # 简化
        if grid_block_end < 0:
            grid_block_end = map_open + 3000
        block = self.html[map_open:grid_block_end]
        self.assertIn("overview-laps", block,
                      "V9.2.3 FAIL: .overview-laps 不在 .overview-map-area 内(贴图失败)")

    def test_map_area_flex_column(self):
        """V9.2.3:.overview-map-area 必须 flex column(图+圈速垂直堆叠)"""
        self.assertIn(".overview-map-area {", self.html,
                      "V9.2.3 FAIL: 缺 .overview-map-area CSS")
        idx = self.html.find(".overview-map-area {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("display: flex", body, "V9.2.3 FAIL: Map 区缺 flex")
        self.assertIn("flex-direction: column", body,
                      "V9.2.3 FAIL: Map 区缺 flex-direction: column")


class TestV9_2_2Sidebar4Cards(unittest.TestCase):
    """V9.2.2 §E-T3:侧栏 4 张卡(环境/训练收益/身体状态/活动摘要)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_render_sidebar_function_exists(self):
        """V9.2.2:必须有 renderActivityDetailSidebar 函数"""
        self.assertIn("function renderActivityDetailSidebar(", self.html,
                      "V9.2.2 FAIL: 缺 renderActivityDetailSidebar 函数")

    def test_placeholder_card_builder_exists(self):
        """V9.2.2:必须新增 _buildPlaceholderSidebarCard 占位函数"""
        self.assertIn("function _buildPlaceholderSidebarCard(", self.html,
                      "V9.2.2 FAIL: 缺 _buildPlaceholderSidebarCard 函数")

    def test_3_card_titles_in_sidebar_render(self):
        """V9.2.2:renderActivityDetailSidebar 必须输出 3 张卡的标题"""
        idx = self.html.find("function renderActivityDetailSidebar(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        for title in ['天气', '训练收益', '环境挑战']:
            self.assertIn(title, body,
                          f"V9.2.2 FAIL: renderActivityDetailSidebar 缺 {title} 卡")

    def test_training_effect_placeholder_message_includes_review_tab_hint(self):
        """V9.2.2:训练收益占位文案应提示需要 FIT 设备记录 Training Effect 字段
        占位文案在 _buildTrainingBenefitCard 的降级路径(不是 renderActivityDetailSidebar)
        """
        idx = self.html.find("function _buildTrainingBenefitCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 占位文案应提示需要 FIT 设备
        self.assertTrue('Training Effect' in body or 'FIT' in body,
                        "V9.2.2 FAIL: 训练收益占位卡未提示需要 FIT 设备")

    def test_shadow_diff_isolation_preserved(self):
        """V9.2.2:renderActivityDetailSidebar 必须保留 §六 shadow_diff 隔离"""
        idx = self.html.find("function renderActivityDetailSidebar(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.2.2 FAIL: renderActivityDetailSidebar 缺 shadow_diff 校验")


# === V9.2.3 新增测试类(2x2 grid + 滚动 + padding) ===

class TestV9_2_3Grid2x2(unittest.TestCase):
    """V9.2.3 §E-T4:2x2 grid 布局(用户确认草图)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_2x2_grid_container_exists(self):
        """V9.2.3:必须新增 .overview-2x2 2x2 grid 容器"""
        self.assertIn('class="overview-2x2"', self.html,
                      "V9.2.3 FAIL: 缺 .overview-2x2 容器")
        # 三个子区域必须存在
        for area in ['overview-hero-area', 'overview-sidebar-stack', 'overview-map-area']:
            self.assertIn(area, self.html,
                          f"V9.2.3 FAIL: 缺 {area} 子区域")

    def test_2x2_grid_template(self):
        """V9.2.3:.overview-2x2 必须有 grid-template-areas 2x2"""
        self.assertIn(".overview-2x2 {", self.html,
                      "V9.2.3 FAIL: 缺 .overview-2x2 CSS")
        idx = self.html.find(".overview-2x2 {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("grid-template-areas:", body,
                      "V9.2.3 FAIL: 缺 grid-template-areas")
        self.assertIn("hero", body, "V9.2.3 FAIL: grid-area 缺 hero")
        self.assertIn("map", body, "V9.2.3 FAIL: grid-area 缺 map")
        self.assertIn("sidebar", body, "V9.2.3 FAIL: grid-area 缺 sidebar")
        # 2 列布局:左 2fr 右 1fr
        self.assertIn("2fr 1fr", body, "V9.2.3 FAIL: grid-template-columns 缺 2fr 1fr")

    def test_hero_map_aligned_width(self):
        """V9.2.3:Hero 与 Map 应在 grid-areas 中共享同一列宽(2fr)"""
        idx = self.html.find(".overview-2x2 {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        # 验证 hero 和 map 都在 grid-template-areas 的第一列
        # 格式: "hero sidebar" 在第一行, "map sidebar" 在第二行
        # 第一行和第二行第一列都应是 hero/map(同列宽)
        self.assertIn('"hero sidebar"', body,
                      "V9.2.3 FAIL: grid 第一行未定义 hero+sidebar")
        self.assertIn('"map sidebar"', body,
                      "V9.2.3 FAIL: grid 第二行未定义 map+sidebar")

    def test_sidebar_spans_full_height(self):
        """V9.2.3:右栏(sidebar)必须跨 Hero+Map 两行(网格上 hero/map 各占 1 行,sidebar 占 2 行)"""
        # 通过 grid-template-rows: auto auto 验证
        idx = self.html.find(".overview-2x2 {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("grid-template-rows:", body,
                      "V9.2.3 FAIL: 缺 grid-template-rows")
        # 必须有 2 行让 sidebar 跨行
        self.assertIn("auto auto", body,
                      "V9.2.3 FAIL: grid-template-rows 应为 auto auto(2 行让 sidebar 跨行)")


class TestV9_2_3ModalScrollable(unittest.TestCase):
    """V9.2.3 §E-T5:modal 启用垂直滚动"""

    def setUp(self):
        self.html = _read_track_html()

    def test_modal_overflow_y_auto(self):
        """V9.2.3:.activity-detail-modal 必须 overflow-y: auto"""
        self.assertIn(".activity-detail-modal {", self.html,
                      "V9.2.3 FAIL: 缺 .activity-detail-modal CSS")
        idx = self.html.find(".activity-detail-modal {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("overflow-y: auto", body,
                      "V9.2.3 FAIL: .activity-detail-modal 缺 overflow-y: auto")
        self.assertIn("overflow-x: hidden", body,
                      "V9.2.3 FAIL: .activity-detail-modal 缺 overflow-x: hidden")
        # 不能有 overflow: hidden 单独(会被覆盖)
        self.assertNotIn("overflow: hidden;", body,
                         "V9.2.3 FAIL: .activity-detail-modal 不应有 overflow: hidden")

    def test_cockpit_body_overflow_visible(self):
        """V9.2.3:.detail-cockpit-body 必须让出滚动(由 modal 接管)"""
        idx = self.html.find(".detail-cockpit-body {")
        self.assertGreater(idx, 0, "V9.2.3 FAIL: 缺 .detail-cockpit-body CSS")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        # body 应该是 overflow: visible(让 modal 滚动)
        self.assertIn("overflow: visible", body,
                      "V9.2.3 FAIL: .detail-cockpit-body 应为 overflow: visible")
        self.assertNotIn("overflow: hidden", body,
                         "V9.2.3 FAIL: .detail-cockpit-body 不应再 overflow: hidden")


class TestV9_2_3ModalPadding(unittest.TestCase):
    """V9.2.3 §E-T6:modal padding 增大到 28px(给最右列卡片留视觉缓冲)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_modal_padding_at_least_24px(self):
        """V9.2.3:.activity-detail-modal padding-right 应 ≥ 24px"""
        idx = self.html.find(".activity-detail-modal {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        # 找 padding 声明
        import re as _re
        pad_match = _re.search(r"padding:\s*([^;]+);", body)
        self.assertIsNotNone(pad_match, "V9.2.3 FAIL: 缺 padding 声明")
        pad_str = pad_match.group(1).strip()
        # 提取所有数字
        nums = _re.findall(r"\d+", pad_str)
        self.assertGreaterEqual(len(nums), 2, "V9.2.3 FAIL: padding 应至少 2 个值")
        # 左右 padding 至少 24px
        right_pad = int(nums[1]) if len(nums) >= 2 else 0
        left_pad = int(nums[3]) if len(nums) >= 4 else int(nums[1])
        self.assertGreaterEqual(right_pad, 24,
                                f"V9.2.3 FAIL: padding-right {right_pad}px 应 ≥ 24px")
        self.assertGreaterEqual(left_pad, 24,
                                f"V9.2.3 FAIL: padding-left {left_pad}px 应 ≥ 24px")


# === V9.2.4 新增测试(天气卡玻璃态 + 轨迹报告移除) ===

class TestV9_2_4WeatherGlassCard(unittest.TestCase):
    """V9.2.4 §E-T7:概览页天气卡换玻璃态,标题改'🌦 历史天气',4 字段 2x2"""

    def setUp(self):
        self.html = _read_track_html()

    def test_uses_weather_glass_class(self):  # 16
        """V9.2.4:_buildWeatherCard 必须用 .weather-glass-card(非 .sidebar-card)"""
        idx = self.html.find("function _buildWeatherCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("weather-glass-card", body,
                      "V9.2.4 FAIL: _buildWeatherCard 未用 .weather-glass-card")
        self.assertIn("weather-glass-grid", body,
                      "V9.2.4 FAIL: _buildWeatherCard 未用 .weather-glass-grid(2x2)")
        # 不应再用 .sidebar-card(已废弃)
        # 注意:函数内只应输出 weather-glass-*;若输出 sidebar-card 即回归
        # 简化:函数 body 内不应含 "class=\"sidebar-card\""
        self.assertNotIn('class="sidebar-card"', body,
                         "V9.2.4 FAIL: _buildWeatherCard 仍用 .sidebar-card(应删除)")

    def test_new_title_historical_weather(self):  # 17
        """V9.2.4:标题必须为'🌦 历史天气'(不带'环境感知')"""
        idx = self.html.find("function _buildWeatherCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("🌦 历史天气", body,
                      "V9.2.4 FAIL: 标题应改为'🌦 历史天气'")
        # 旧标题不应再出现
        self.assertNotIn("历史天气环境感知", body,
                         "V9.2.4 FAIL: 仍含旧标题'历史天气环境感知'")

    def test_4_fields_in_grid(self):  # 18
        """V9.2.4:4 字段(温度/湿度/风速/状况)均应在 grid 中"""
        idx = self.html.find("function _buildWeatherCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 4 字段引用
        for field in ['temperature_c', 'humidity', 'wind_speed_kmh', 'weather_label']:
            self.assertIn(field, body, f"V9.2.4 FAIL: 缺 {field} 字段")
        # 4 个 weather-glass-item(item 计数)
        item_count = body.count("weather-glass-item")
        # 至少有 4 个 item(有数据时)+ 0 个(空态)→ 总数 ≥ 4
        self.assertGreaterEqual(item_count, 4,
                                f"V9.2.4 FAIL: weather-glass-item 应 ≥ 4,实际 {item_count}")

    def test_shadow_diff_isolation_in_glass_card(self):  # 19
        """V9.2.4:玻璃态天气卡必须保留 §六 shadow_diff 隔离"""
        idx = self.html.find("function _buildWeatherCard(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.2.4 FAIL: _buildWeatherCard 缺 §六 shadow_diff 校验")


class TestV9_2_4TraceReportWeatherRemoved(unittest.TestCase):
    """V9.2.4 §E-T8:轨迹报告 buildAIReportHTML 不再含天气卡 block"""

    def setUp(self):
        self.html = _read_track_html()

    def test_build_ai_report_no_weather_card(self):  # 20
        """V9.2.4:buildAIReportHTML 函数体内不应输出 .weather-glass-card"""
        idx = self.html.find("function buildAIReportHTML(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 8000
        body = self.html[idx:end]
        # 函数体内不应含 weather-glass-card 字面量
        self.assertNotIn("weather-glass-card", body,
                         "V9.2.4 FAIL: buildAIReportHTML 仍输出 .weather-glass-card(应移到概览页)")
        # 也不应再读 appState.currentWeather
        self.assertNotIn("appState.currentWeather", body,
                         "V9.2.4 FAIL: buildAIReportHTML 仍读 currentWeather(应删除)")

    def test_weather_glass_css_kept_for_overview(self):  # 21
        """V9.2.4:.weather-glass-* CSS 必须保留(供概览页复用)"""
        # CSS 不应被删除
        for css_class in ['.weather-glass-card', '.weather-glass-grid', '.weather-glass-item', '.weather-glass-title', '.weather-glass-subtitle', '.weather-glass-empty']:
            self.assertIn(css_class, self.html,
                          f"V9.2.4 FAIL: CSS {css_class} 被删除(概览页还需复用)")

    def test_remove_legacy_old_title_from_trace_report(self):  # 22
        """V9.2.4:buildAIReportHTML 不应再输出'历史天气环境感知'旧标题"""
        idx = self.html.find("function buildAIReportHTML(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 8000
        body = self.html[idx:end]
        self.assertNotIn("历史天气环境感知", body,
                         "V9.2.4 FAIL: 轨迹报告仍含旧标题'历史天气环境感知'")


# === V9.2.5 新增测试(天气数据从 record.weather 读,不用 appState.currentWeather) ===

class TestV9_2_5WeatherDataSource(unittest.TestCase):
    """V9.2.5 §E-T9:概览页天气数据源必须用 record.weather(活动专属),不再用 appState.currentWeather(全局)"""

    def setUp(self):
        self.html = _read_track_html()

    def test_overview_uses_record_weather_not_appstate(self):  # 23
        """V9.2.5:renderActivityDetail 内 _wx 必须从 record.weather 读,不能再读 appState.currentWeather"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 8000
        body = self.html[idx:end]
        # 必须从 record.weather 读(活动专属)
        self.assertIn("record.weather", body,
                      "V9.2.5 FAIL: renderActivityDetail 未读 record.weather")
        # 必须经过 normalizeWeatherData 标准化
        self.assertIn("normalizeWeatherData(record.weather)", body,
                      "V9.2.5 FAIL: record.weather 未经过 normalizeWeatherData 标准化")
        # 不能再用 appState.currentWeather
        self.assertNotIn("appState.currentWeather", body,
                         "V9.2.5 FAIL: 仍读 appState.currentWeather(全局态,会导致空态)")

    def test_weather_card_uses_provided_weather(self):  # 24
        """V9.2.5:renderActivityDetailSidebar 接收 weather 参数,必须透传给 _buildWeatherCard"""
        idx = self.html.find("function renderActivityDetailSidebar(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0:
            end = idx + 5000
        body = self.html[idx:end]
        # 必须有 _buildWeatherCard(weather, esc) 调用,weather 是入参
        self.assertIn("_buildWeatherCard(weather", body,
                      "V9.2.5 FAIL: renderActivityDetailSidebar 未透传 weather 给 _buildWeatherCard")


if __name__ == "__main__":
    unittest.main()
