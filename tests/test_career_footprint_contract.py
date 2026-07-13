import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DELIVERY_MANUAL = PROJECT_ROOT / "docs" / "acs_next_footprint_memory_gallery_delivery_manual.md"
TASK_LIST = PROJECT_ROOT / "docs" / "acs_next_footprint_memory_gallery_task_list.md"


class TestCareerFootprintContractDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delivery = DELIVERY_MANUAL.read_text(encoding="utf-8")
        cls.task_list = TASK_LIST.read_text(encoding="utf-8")
        cls.combined = cls.delivery + "\n" + cls.task_list

    def test_footprint_view_model_shape_is_frozen(self):
        for token in (
            "get_career_footprint(filters?)",
            '"map_mode"',
            '"regions"',
            '"without_region"',
            '"summary"',
            '"filters"',
            '"status"',
            "regions[].region_key",
        ):
            self.assertIn(token, self.combined)

    def test_map_mode_rules_are_explicit(self):
        for token in (
            "只有中国足迹时，只显示中国地区地图，并包含台湾区域",
            "存在海外足迹时，显示世界地图",
            "`map_mode = china` 表示只渲染中国地区地图",
            "`map_mode = world` 表示渲染世界地图",
            "地图模式由后端根据地理事实判断并返回，前端不得自行判断",
        ):
            self.assertIn(token, self.combined)

    def test_region_granularity_and_activity_scope_are_explicit(self):
        for token in (
            "地图按省份 / 州 / 行政区域点亮，而不是散点图",
            "生涯足迹应覆盖所有有可靠地理信息的运动 Activity，而不只限赛事",
            "普通 Activity 可进入生涯足迹，不依赖赛事身份",
            "没有可靠地理信息的 Activity 进入 `without_region`，不参与地图点亮",
        ):
            self.assertIn(token, self.combined)

    def test_security_boundaries_are_part_of_contract(self):
        for token in (
            "前端不得根据标题、城市、日期或 DOM 文本推断地理区域",
            "前端不得读取 raw FIT、`points_json`、`track_json`、本地路径、`storage_ref` 或 SQLite schema",
            "API 不返回 raw FIT、完整路线 points、本地路径、SQLite schema",
        ):
            self.assertIn(token, self.combined)


if __name__ == "__main__":
    unittest.main()
