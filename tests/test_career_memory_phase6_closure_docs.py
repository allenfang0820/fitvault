import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_LIST_PATH = PROJECT_ROOT / "docs" / "脉图运动生涯系统（ACS）开发任务清单.md"
CLOSURE_REPORT_PATH = PROJECT_ROOT / "docs" / "acs_phase6_05_memory_gallery_closure_report.md"


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestCareerMemoryPhase6ClosureDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task_list = TASK_LIST_PATH.read_text(encoding="utf-8")
        cls.report = CLOSURE_REPORT_PATH.read_text(encoding="utf-8")

    def test_task_list_distinguishes_done_and_follow_up_phase6_work(self):
        phase6 = extract_between(self.task_list, "## Phase 6：Memory Gallery", "## Phase 7：AI Career Insight")
        self.assertIn("### 已完成：轻量闭环", phase6)
        self.assertIn("### 后续增强：暂不阻塞 Phase 7", phase6)
        self.assertIn("- [x] 先做轻量版", phase6)
        self.assertIn("故事文本：已支持新增、原位编辑、软停用", phase6)
        self.assertIn("图片：已支持 `photo` 类型安全媒体引用", phase6)
        self.assertIn("轨迹截图：已支持 `track` 类型安全媒体引用", phase6)
        self.assertIn("单张赛事 Banner 图片选择器与受控复制已完成", phase6)
        self.assertIn("Memory Gallery 保持集中只读展示", phase6)
        self.assertIn("赛事 Activity Detail 多图相册、最多 5 张、拖拽排序、首图 Banner 规则已完成", phase6)
        self.assertIn("赛事照片删除采用软删除，媒体文件物理删除仍不执行", phase6)
        self.assertIn("- [ ] 未完成：复杂相册布局和媒体文件物理删除生命周期", phase6)

    def test_closure_report_exists_and_lists_memory_apis(self):
        self.assertTrue(CLOSURE_REPORT_PATH.exists())
        for api_name in (
            "get_career_memory",
            "save_career_memory_story",
            "update_career_memory_story",
            "deactivate_career_memory_item",
            "save_career_memory_media",
        ):
            self.assertIn(api_name, self.report)

    def test_closure_report_confirms_storage_and_local_paths_are_not_public(self):
        self.assertIn("不返回 `storage_ref`", self.report)
        self.assertIn("本地绝对路径", self.report)
        self.assertIn("不得读取 `storage_ref` 或本地路径", self.report)
        self.assertIn("公开返回值仍只包含", self.report)

    def test_closure_report_marks_upload_copy_delete_as_out_of_scope(self):
        for phrase in (
            "不做复杂相册上传器",
            "不做批量文件选择器",
            "不删除媒体文件",
            "不做复杂相册布局",
        ):
            self.assertIn(phrase, self.report)

    def test_closure_report_allows_phase7_with_boundary(self):
        self.assertIn("可以进入 Phase 7", self.report)
        self.assertIn("ACS-Phase7-01：Career Snapshot 生成器白名单骨架", self.report)
        self.assertIn("不调用 LLM", self.report)
        self.assertIn("representative memories", self.report)


if __name__ == "__main__":
    unittest.main()
