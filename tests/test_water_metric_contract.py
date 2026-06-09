from __future__ import annotations

import os
import unittest

from main import (
    WATER_METRIC_DISPLAY_TYPES,
    _resolve_display_sport_type,
    _resolve_water_metric,
    _resolve_water_metric_for_row,
    _read_water_metrics_from_fit,
    resolve_lap_columns,
)
from fit_engine import SPORT_TYPE_ALIASES


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(PROJECT_ROOT, "track.html")


class TestWaterMetricBackendContract(unittest.TestCase):
    def test_display_type_preserves_swim_sub_sports(self):
        self.assertEqual(_resolve_display_sport_type("swimming", "lap_swimming"), "lap_swimming")
        self.assertEqual(_resolve_display_sport_type("swimming", "open_water"), "open_water")
        self.assertEqual(
            _resolve_display_sport_type("swimming", "open_water_swimming"),
            "open_water_swimming",
        )

    def test_water_metric_labels_by_sub_sport(self):
        self.assertEqual(
            _resolve_water_metric("lap_swimming", "lap_swimming", 42),
            (42.0, "平均SWOLF", "swolf"),
        )
        self.assertEqual(
            _resolve_water_metric("open_water", "open_water", 2.3),
            (2.3, "平均划水距离", "stroke_distance"),
        )
        self.assertEqual(
            _resolve_water_metric("stand_up_paddleboarding", "unknown", 4.1),
            (4.1, "平均划水距离", "stroke_distance"),
        )
        self.assertEqual(
            _resolve_water_metric("paddling", "unknown", 4.1),
            (4.1, "平均划水距离", "stroke_distance"),
        )
        self.assertEqual(_resolve_water_metric("running", "unknown", 4.1), (None, None, None))

    def test_water_metric_dynamic_types_include_open_water(self):
        self.assertIn("lap_swimming", WATER_METRIC_DISPLAY_TYPES)
        self.assertIn("open_water", WATER_METRIC_DISPLAY_TYPES)
        self.assertIn("open_water_swimming", WATER_METRIC_DISPLAY_TYPES)
        self.assertIn("paddling", WATER_METRIC_DISPLAY_TYPES)

    def test_mixed_water_rows_share_one_column_with_row_subtitles(self):
        rows = [
            _resolve_water_metric_for_row("lap_swimming", "lap_swimming", 42),
            _resolve_water_metric_for_row("open_water", "open_water", 2.3),
            _resolve_water_metric_for_row("paddling", "unknown", 4.1),
        ]
        self.assertEqual(rows[0], (42.0, "平均SWOLF", "swolf"))
        self.assertEqual(rows[1], (2.3, "平均划水距离", "stroke_distance"))
        self.assertEqual(rows[2], (4.1, "平均划水距离", "stroke_distance"))

    def test_list_water_metric_does_not_parse_fit_when_db_metric_is_empty(self):
        def fake_reader(_file_path):
            raise AssertionError("活动列表不应同步解析 FIT 文件")

        import main

        original = main._read_water_metrics_from_fit
        main._read_water_metrics_from_fit = fake_reader
        try:
            self.assertEqual(
                _resolve_water_metric_for_row("lap_swimming", "lap_swimming", None, "x.fit"),
                (None, None, None),
            )
            self.assertEqual(
                _resolve_water_metric_for_row("stand_up_paddleboarding", "generic", None, "x.fit"),
                (None, None, None),
            )
        finally:
            main._read_water_metrics_from_fit = original

    def test_lap_columns_split_swolf_and_stroke_distance(self):
        self.assertIn("swolf", resolve_lap_columns("lap_swimming"))
        self.assertIn("stroke_distance", resolve_lap_columns("open_water"))
        self.assertIn("stroke_distance", resolve_lap_columns("open_water_swimming"))

    def test_fit_engine_preserves_paddling_tokens(self):
        self.assertEqual(SPORT_TYPE_ALIASES["paddling"], "paddling")
        self.assertEqual(SPORT_TYPE_ALIASES["sup"], "stand_up_paddleboarding")


class TestWaterMetricFrontendContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(TRACK_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_sport_hub_list_prefers_water_metric_fields(self):
        self.assertIn("item.water_metric_value", self.html)
        self.assertIn("item.water_metric_label", self.html)
        self.assertIn("item.stroke_distance", self.html)

    def test_sport_hub_uses_generic_metric_backfill_status(self):
        self.assertIn("data.list_metric_backfill", self.html)
        self.assertIn("scheduleListMetricBackfillRefresh", self.html)

    def test_activity_list_loading_does_not_label_import_button_as_importing(self):
        self.assertIn("const importing = sportHubState.recordsSyncing;", self.html)
        self.assertIn("btn.innerText = importing ? '导入中...' : '导入本地 FIT 文件';", self.html)
        self.assertNotIn("btn.innerText = busy ? '导入中...' : '导入本地 FIT 文件';", self.html)

    def test_activity_list_dynamic_columns_render_in_backend_order(self):
        self.assertIn("dynamicCols.forEach((col) =>", self.html)
        self.assertIn("dynamicColumnDefs[col].header", self.html)
        self.assertIn("dynamicColumnDefs[col].cell(item)", self.html)
        self.assertNotIn("if (showNp) baseHeaders.push", self.html)

    def test_lap_table_handles_open_water_units_and_fallback(self):
        self.assertIn("s === 'open_water'", self.html)
        self.assertIn("s === 'open_water_swimming'", self.html)
        self.assertIn("lap.avg_stroke_distance", self.html)


if __name__ == "__main__":
    unittest.main()
