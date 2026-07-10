import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL_PATH = PROJECT_ROOT / "docs" / "脉图运动生涯系统（ACS）开发团队交付手册.md"


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestAcsDeliveryManualOverviewV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manual = MANUAL_PATH.read_text(encoding="utf-8")

    def test_manual_version_and_overview_v2_definition_are_updated(self):
        self.assertIn("version: v1.1.0", self.manual)
        overview = extract_between(self.manual, "## 3.2 Career Overview", "## 3.3 Timeline Engine")
        self.assertIn("运动生涯封面页", overview)
        self.assertIn("赛事记忆 Banner", overview)
        self.assertIn("标题生成艺术字 Banner", overview)
        self.assertIn("全量运动统计", overview)
        self.assertIn("年度结构", overview)
        self.assertIn("年度统计摘要", overview)
        self.assertIn("覆盖全部已有运动年份", overview)
        self.assertIn("不展示“高光年 / 赛事年 / 记录年 / 空白年”", overview)
        self.assertIn("不再恢复三问卡片作为总览首屏 UI", overview)

    def test_manual_no_longer_uses_three_questions_as_overview_ui(self):
        overview = extract_between(self.manual, "## 3.2 Career Overview", "## 3.3 Timeline Engine")
        self.assertNotIn("1. 我是谁？", overview)
        self.assertNotIn("2. 我走了多久？", overview)
        self.assertNotIn("3. 我经历过什么？", overview)

    def test_overview_api_contract_documents_current_view_model(self):
        overview_api = extract_between(self.manual, "## 5.2 Overview API", "## 5.3 Timeline API")
        for token in (
            "hero_banner",
            "sport_totals",
            "career_stats",
            "best_pb",
            "title_art",
            "strength_total_weight_status",
            "max_altitude_m",
            "image_ref",
            "不得是本地绝对路径",
            "不返回 raw FIT",
        ):
            self.assertIn(token, overview_api)

    def test_frontend_and_boundary_sections_cover_banner_fallbacks(self):
        frontend = extract_between(self.manual, "## 6.5 页面布局原则", "### 节点样式")
        boundary = extract_between(self.manual, "# 7. 异常与边界", "# 8. 缓存、性能与安全")
        for token in (
            "赛事记忆 Banner 为第一视觉",
            "活动标题艺术字 fallback",
            "后端 ViewModel",
            "photo",
            "title_art",
            "empty",
        ):
            self.assertIn(token, frontend)
        for token in (
            "无 Activity 数据",
            "无赛事数据",
            "无赛事照片",
            "标题艺术字 fallback",
            "不返回本地图片路径",
        ):
            self.assertIn(token, boundary)


if __name__ == "__main__":
    unittest.main()
