import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PROJECT_ROOT / "docs" / "acs_phase10_test_acceptance_matrix.md"
TASK_LIST_PATH = PROJECT_ROOT / "docs" / "脉图运动生涯系统（ACS）开发任务清单.md"


class TestCareerPhase10AcceptanceMatrixDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = MATRIX_PATH.read_text(encoding="utf-8")
        cls.task_list = TASK_LIST_PATH.read_text(encoding="utf-8")

    def test_matrix_covers_all_acs_phases(self):
        self.assertIn("# ACS Phase10 测试与验收矩阵", self.matrix)
        for phase in (
            "Phase0 架构与 schema",
            "Phase1 赛事识别与赛事档案",
            "Phase2 PB Engine",
            "Phase3 Achievement Engine",
            "Phase4 Career Overview",
            "Phase5 Timeline Engine",
            "Phase6 Memory Gallery",
            "Phase7 Snapshot / Insight",
            "Phase8 Frontend readiness / visual contract",
            "Phase9 跨平台代码层兼容与数据边界",
            "Phase10 测试与验收矩阵",
        ):
            self.assertIn(phase, self.matrix)

    def test_matrix_lists_core_regression_tests_and_boundaries(self):
        for token in (
            "tests/test_career_backend_schema.py",
            "tests/test_fit_sport_event_race.py",
            "tests/test_activity_race_flag_api.py",
            "tests/test_career_race_resolver.py",
            "tests/test_career_pb_resolver.py",
            "tests/test_career_achievement_resolver.py",
            "tests/test_career_snapshot_persistence.py",
            "tests/test_career_phase9_data_boundary_audit.py",
            "tests/test_track_html_sync_logic.py",
            "Activity 单一事实源",
            "AI 不能修改事实数据",
            "前端不能补算赛事、PB、成就、时间线事实",
        ):
            self.assertIn(token, self.matrix)

    def test_windows_and_packaging_validation_remain_deferred(self):
        self.assertIn("Windows 真机与打包未完成", self.matrix)
        self.assertIn("未完成 Windows 真机/打包验证前，不得勾选 Windows 相关验收项", self.matrix)
        self.assertIn("- [ ] Windows 打包后验证：", self.task_list)
        self.assertIn("- [ ] Windows 真机验证运动生涯页面：", self.task_list)


if __name__ == "__main__":
    unittest.main()
