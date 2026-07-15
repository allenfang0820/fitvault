"""Device name resolution contract tests.

FIT device metadata must be translated by MetricsResolver. Import code may
extract FIT file_id messages, but must not invent UI-facing device names.
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import main
from metrics_resolver import (
    MetricsResolver,
    ensure_device_product_mapping_seed,
    extract_device_identity_from_fit_file_id,
    is_device_name_unresolved,
    resolve_device_display_name,
)


class TestDeviceNameResolver(unittest.TestCase):
    def test_numeric_garmin_product_uses_product_mapping(self):
        self.assertEqual(
            MetricsResolver._resolve_device_name(
                {"file_id_mesgs": [{"garmin_product": 3515, "manufacturer": "garmin"}]},
                {},
            ),
            "Fenix6 Asia",
        )

    def test_numeric_garmin_product_string_uses_product_mapping(self):
        self.assertEqual(
            MetricsResolver._resolve_device_name(
                {"file_id_mesgs": [{"garmin_product": "4536", "manufacturer": "garmin"}]},
                {},
            ),
            "Fenix 8",
        )

    def test_unknown_numeric_garmin_product_does_not_expose_fallback_name(self):
        resolved = resolve_device_display_name(
            extract_device_identity_from_fit_file_id([{"garmin_product": 3089, "manufacturer": "garmin"}])
        )
        self.assertEqual(resolved["device_name"], "Unknown Device")
        self.assertEqual(resolved["mapping_status"], "unresolved")
        self.assertEqual(resolved["product_key"], "garmin:3089")

    def test_sdk_profile_resolves_known_product_without_mapping_table(self):
        resolved = resolve_device_display_name(
            extract_device_identity_from_fit_file_id([{"garmin_product": 4587, "manufacturer": "garmin"}])
        )
        self.assertEqual(resolved["device_name"], "Instinct3 Amoled 50mm")
        self.assertEqual(resolved["mapping_status"], "resolved")
        self.assertEqual(resolved["source"], "profile")
        self.assertEqual(resolved["product_key"], "garmin:4587")

    def test_mapping_table_can_resolve_unknown_profile_product(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE device_product_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor TEXT NOT NULL,
                    product_key TEXT NOT NULL,
                    product_id TEXT,
                    display_name TEXT NOT NULL,
                    display_brand TEXT,
                    source TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(vendor, product_key)
                )
                """
            )
            ensure_device_product_mapping_seed(conn)
            conn.execute(
                """
                INSERT INTO device_product_mappings
                    (vendor, product_key, product_id, display_name, display_brand, source, confidence, status, created_at, updated_at)
                VALUES ('garmin', 'garmin:3089', '3089', 'Forerunner Custom', 'Garmin', 'user', 'high', 'active', datetime('now'), datetime('now'))
                """
            )
            resolved = resolve_device_display_name(
                extract_device_identity_from_fit_file_id([{"garmin_product": 3089, "manufacturer": "garmin"}]),
                conn,
            )
        finally:
            conn.close()

        self.assertEqual(resolved["device_name"], "Forerunner Custom")
        self.assertEqual(resolved["mapping_status"], "resolved")
        self.assertEqual(resolved["source"], "user")

    def test_fallback_device_names_are_refresh_candidates(self):
        self.assertTrue(is_device_name_unresolved("Garmin Product 3515"))
        self.assertTrue(is_device_name_unresolved("Unknown Device", "unresolved"))
        self.assertFalse(is_device_name_unresolved("Fenix6 Asia", "resolved"))

    def test_extract_device_identity_from_fit_file_id(self):
        identity = extract_device_identity_from_fit_file_id(
            [{"manufacturer": "garmin", "garmin_product": "3515", "serial_number": 3365282831}]
        )
        self.assertEqual(identity["vendor"], "garmin")
        self.assertEqual(identity["product_key"], "garmin:3515")
        self.assertEqual(identity["product_id"], "3515")
        self.assertEqual(identity["serial"], "3365282831")

    def test_import_device_fallback_still_delegates_to_resolver(self):
        src = inspect.getsource(main._parse_fit_activity_for_sync)
        self.assertIn("from fitparse import FitFile", src)
        self.assertIn("_resolve_device_display_for_sync", src)
        self.assertIn("file_id_mesgs", src)
        self.assertNotIn('"Garmin Product"', src)


if __name__ == "__main__":
    unittest.main()
