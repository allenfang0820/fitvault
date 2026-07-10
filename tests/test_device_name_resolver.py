"""Device name resolution contract tests.

FIT device metadata must be translated by MetricsResolver. Import code may
extract FIT file_id messages, but must not invent UI-facing device names.
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import main
from metrics_resolver import MetricsResolver


class TestDeviceNameResolver(unittest.TestCase):
    def test_numeric_garmin_product_uses_product_mapping(self):
        self.assertEqual(
            MetricsResolver._resolve_device_name(
                {"file_id_mesgs": [{"garmin_product": 4536, "manufacturer": "garmin"}]},
                {},
            ),
            "Fenix 8",
        )

    def test_numeric_garmin_product_string_uses_product_mapping(self):
        self.assertEqual(
            MetricsResolver._resolve_device_name(
                {"file_id_mesgs": [{"garmin_product": "4536", "manufacturer": "garmin"}]},
                {},
            ),
            "Fenix 8",
        )

    def test_import_device_fallback_still_delegates_to_resolver(self):
        src = inspect.getsource(main._parse_fit_activity_for_sync)
        self.assertIn("from fitparse import FitFile", src)
        self.assertGreaterEqual(
            src.count("MetricsResolver._resolve_device_name"),
            2,
            "导入层只能提取 FIT file_id，设备型号翻译必须交给 MetricsResolver",
        )


if __name__ == "__main__":
    unittest.main()
