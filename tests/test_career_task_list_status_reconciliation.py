import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_LIST_PATH = PROJECT_ROOT / "docs" / "脉图运动生涯系统（ACS）开发任务清单.md"
REPORT_PATH = PROJECT_ROOT / "docs" / "acs_task_list_status_reconciliation_completion_report.md"


class TestCareerTaskListStatusReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task_list = TASK_LIST_PATH.read_text(encoding="utf-8")
        cls.report = REPORT_PATH.read_text(encoding="utf-8")

    def test_task_list_is_reconciled_baseline(self):
        self.assertIn("version: v0.2.0", self.task_list)
        self.assertIn("Status Reconciled Baseline", self.task_list)
        self.assertIn("状态标记说明", self.task_list)

    def test_completed_core_phases_are_backfilled(self):
        for token in (
            "代码闭环：新增一级导航「运动生涯」",
            "代码闭环：读取 FIT `session.sport_event` 字段",
            "代码闭环：支持用户手动标记/取消赛事",
            "代码闭环：实现 `get_career_races` API",
            "代码闭环：实现 `get_career_pb` API",
            "代码闭环：实现 `get_career_achievements` API",
            "代码闭环：实现 `get_career_overview` API",
            "代码闭环：实现年份 × 月份时间轴",
        ):
            self.assertIn(token, self.task_list)

    def test_overview_v2_is_recorded(self):
        for token in (
            "Overview V2 已完成首屏结构重构",
            "顶部赛事记忆 Banner",
            "无赛事照片时使用活动标题艺术字 fallback",
            "跑步 / 骑行 / 徒步步行 / 游泳距离统计",
            "力量训练总重量仅在 Activity 存在可靠总重量字段时聚合",
            "城市 / 国家足迹、最高海拔、最长单次、最大爬升、活跃年份等统计接入",
            "年度卡片仅在 Overview 展示",
            "覆盖后端返回的全部已有运动年份",
            "不展示“高光年 / 赛事年 / 记录年 / 空白年”",
            "年度结构保留在 Banner 与统计区之后",
        ):
            self.assertIn(token, self.task_list)

    def test_unfinished_product_tasks_remain_unchecked(self):
        for token in (
            "- [ ] 未完成：复杂相册布局和媒体文件物理删除生命周期。",
            "- [ ] 未完成：接入真实 AI Career Insight 前，必须新增独立任务与安全审查。",
            "- [ ] Windows 打包后验证：",
            "- [ ] Windows 真机验证运动生涯页面：",
            "- [ ] macOS 打包产物验证：",
            "- [ ] 未完成：真实数据端到端人工验收：",
        ):
            self.assertIn(token, self.task_list)

    def test_media_safe_preview_is_recorded(self):
        for token in (
            "`ACS-Next-04`：媒体缩略图与安全预览闭环",
            "真实缩略图与安全预览代码闭环已完成",
            "后端仅从应用受控媒体目录转换 `data:image` 预览",
            "Memory Gallery 仍只读展示",
        ):
            self.assertIn(token, self.task_list)

    def test_next_task_order_is_explicit(self):
        expected_order = [
            "ACS-Next-02",
            "ACS-Next-03",
            "ACS-Next-04",
            "ACS-Next-05",
            "ACS-Next-06",
            "ACS-Next-07",
        ]
        positions = [self.task_list.index(token) for token in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("ACS-Next-01` 真实赛事照片上传与 Banner 真实照片模式", self.task_list)
        self.assertIn("赛事照片上传与 Banner 真实照片模式", self.task_list)
        self.assertIn("ACS-Next-03`：Race Map / 赛事足迹完整能力", self.task_list)
        self.assertIn("ACS-Next-05`：真实数据端到端人工验收准备与验收清单", self.task_list)

    def test_do_not_mark_deferred_validation_done(self):
        forbidden_checked_patterns = (
            r"- \[x\].*真实 AI Career Insight 未完成",
            r"- \[x\].*Windows 打包后验证",
            r"- \[x\].*Windows 真机验证运动生涯页面",
            r"- \[x\].*macOS 打包产物验证",
            r"- \[x\].*真实数据端到端人工验收",
        )
        for pattern in forbidden_checked_patterns:
            self.assertIsNone(re.search(pattern, self.task_list))

    def test_completion_report_records_scope_and_non_goals(self):
        for token in (
            "ACS 任务清单状态回填完成报告",
            "本次任务只做文档状态校准与文档测试",
            "不执行 Windows 真机操作",
            "不执行打包",
            "不执行真实 AI 接入",
            "不执行真实图片上传器开发",
        ):
            self.assertIn(token, self.report)


if __name__ == "__main__":
    unittest.main()
