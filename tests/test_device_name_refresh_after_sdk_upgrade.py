from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
import profile_backend


class TestDeviceNameRefreshAfterSdkUpgrade(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)

        self.original_db_path = profile_backend.DB_PATH
        self.original_profile_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        self.original_sync_state_dir = profile_backend.SYNC_STATE_DIR
        self.original_sync_state_path = profile_backend.SYNC_STATE_PATH
        self.original_profile_cache_path = profile_backend.PROFILE_CACHE_PATH
        self.original_refresh_status = dict(main._DEVICE_NAME_REFRESH_STATUS)
        self.original_refresh_timer = main._DEVICE_NAME_REFRESH_TIMER
        self.original_refresh_thread = main._DEVICE_NAME_REFRESH_THREAD

        if self.original_refresh_timer is not None and self.original_refresh_timer.is_alive():
            self.original_refresh_timer.cancel()
        main._DEVICE_NAME_REFRESH_TIMER = None
        main._DEVICE_NAME_REFRESH_THREAD = None
        with main._DEVICE_NAME_REFRESH_LOCK:
            main._DEVICE_NAME_REFRESH_STATUS.update({
                "running": False,
                "scheduled": False,
                "current_sdk_version": "",
                "last_processed_sdk_version": "",
                "should_run": False,
                "mapping_refreshable_count": 0,
                "garmin_fit_reparse_candidate_count": 0,
                "coros_mapping_refreshable_count": 0,
                "missing_file_count": 0,
                "updated": 0,
                "mapping_updated": 0,
                "fit_reparse_updated": 0,
                "skipped_missing_file": 0,
                "failed": 0,
                "limited": False,
                "started_at": 0.0,
                "finished_at": 0.0,
                "scheduled_at": 0.0,
                "scheduled_delay_sec": 0.0,
                "error": "",
            })

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        profile_backend.SYNC_STATE_DIR = str(self.temp_dir / "sync_state")
        profile_backend.SYNC_STATE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "sync_state.json")
        profile_backend.PROFILE_CACHE_PATH = os.path.join(profile_backend.SYNC_STATE_DIR, "user_profile_cache.json")
        Path(profile_backend.SYNC_STATE_DIR).mkdir(parents=True, exist_ok=True)

        main.ensure_activity_sync_schema()

    def tearDown(self):
        timer = main._DEVICE_NAME_REFRESH_TIMER
        if timer is not None and timer.is_alive():
            timer.cancel()
        thread = main._DEVICE_NAME_REFRESH_THREAD
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_profile_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        profile_backend.SYNC_STATE_DIR = self.original_sync_state_dir
        profile_backend.SYNC_STATE_PATH = self.original_sync_state_path
        profile_backend.PROFILE_CACHE_PATH = self.original_profile_cache_path

        main._DEVICE_NAME_REFRESH_TIMER = self.original_refresh_timer
        main._DEVICE_NAME_REFRESH_THREAD = self.original_refresh_thread
        with main._DEVICE_NAME_REFRESH_LOCK:
            main._DEVICE_NAME_REFRESH_STATUS.clear()
            main._DEVICE_NAME_REFRESH_STATUS.update(self.original_refresh_status)

        self.temp_dir_obj.cleanup()

    def _write_processed_sdk_version(self, version: str) -> None:
        profile_backend.write_sync_state(
            {
                main.DEVICE_NAME_REFRESH_STATE_KEY: {
                    main.DEVICE_NAME_REFRESH_STATE_SDK_VERSION_KEY: version,
                }
            }
        )

    def _read_processed_sdk_version(self) -> str:
        state = profile_backend.read_sync_state()
        refresh = state.get(main.DEVICE_NAME_REFRESH_STATE_KEY) or {}
        return str(refresh.get(main.DEVICE_NAME_REFRESH_STATE_SDK_VERSION_KEY) or "")

    def _insert_activity(self, **overrides) -> int:
        values = {
            "title": "原始活动标题",
            "title_source": "filename",
            "filename": "activity.fit",
            "file_name": "activity.fit",
            "file_path": "",
            "source_type": "fit_sdk",
            "is_mock": 0,
            "deleted_at": None,
            "start_time": "2026-08-05T08:00:00Z",
            "updated_at": "2026-08-05T09:00:00Z",
            "sport_type": "cycling",
            "distance": 63050.0,
            "dist_km": 63.05,
            "duration": 8865,
            "duration_sec": 8865,
            "avg_hr": 129,
            "max_hr": 185,
            "avg_power": 189,
            "normalized_power": 230,
            "track_json": "[]",
            "points_json": "[]",
            "device_name": "Unknown Device",
            "device_vendor": "garmin",
            "device_product_key": "",
            "device_product_id": "",
            "device_product_name": "",
            "device_product_hint": "",
            "device_serial": "",
            "device_mapping_status": "unresolved",
        }
        values.update(overrides)
        conn = profile_backend._conn()
        try:
            columns = ", ".join(values.keys())
            placeholders = ", ".join("?" for _ in values)
            cur = conn.execute(
                f"INSERT INTO activities ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def _read_activity(self, activity_id: int) -> dict:
        conn = profile_backend._conn()
        try:
            row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def test_same_sdk_version_does_not_start_refresh(self):
        self._write_processed_sdk_version("21.212.0")
        self._insert_activity(device_name="Unknown Device", device_vendor="garmin")

        with mock.patch.object(main, "_current_garmin_fit_sdk_version", return_value="21.212.0"), \
             mock.patch.object(main, "_extract_device_resolution_from_fit_path") as extract_mock:
            result = main.run_device_name_refresh_after_sdk_upgrade_once(limit=10)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["should_run"])
        self.assertEqual(result["updated"], 0)
        extract_mock.assert_not_called()

    def test_cross_vendor_mapping_backfill_uses_coros_product_name(self):
        self._write_processed_sdk_version("21.208.0")
        activity_id = self._insert_activity(
            title="COROS 保留标题",
            avg_hr=148,
            avg_power=208,
            normalized_power=208,
            device_name="Unknown Device",
            device_vendor="coros",
            device_product_key="coros:861",
            device_product_id="861",
            device_product_name="COROS NOMAD",
            device_mapping_status="unresolved",
        )

        with mock.patch.object(main, "_current_garmin_fit_sdk_version", return_value="21.212.0"):
            result = main.run_device_name_refresh_after_sdk_upgrade_once(limit=10)

        row = self._read_activity(activity_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["coros_mapping_refreshable_count"], 1)
        self.assertEqual(result["mapping_updated"], 1)
        self.assertEqual(row["device_name"], "COROS NOMAD")
        self.assertEqual(row["device_vendor"], "coros")
        self.assertEqual(row["device_product_key"], "coros:861")
        self.assertEqual(row["device_product_name"], "COROS NOMAD")
        self.assertEqual(row["title"], "COROS 保留标题")
        self.assertEqual(row["avg_hr"], 148)
        self.assertEqual(row["avg_power"], 208)
        self.assertEqual(row["normalized_power"], 208)
        self.assertEqual(self._read_processed_sdk_version(), "21.212.0")

    def test_garmin_unresolved_record_reparses_existing_fit_file_only_for_device_fields(self):
        self._write_processed_sdk_version("21.208.0")
        fit_path = self.temp_dir / "garmin_unknown.fit"
        fit_path.write_bytes(b"fit")
        activity_id = self._insert_activity(
            title="不要改这个标题",
            file_path=str(fit_path),
            device_name="Unknown Device",
            device_vendor="garmin",
            device_product_key="",
            device_product_id="",
            device_mapping_status="unresolved",
        )

        resolution = {
            "device_name": "Fenix 8",
            "mapping_status": "resolved",
            "vendor": "garmin",
            "product_key": "garmin:4536",
            "product_id": "4536",
            "serial": "3510683807",
            "product_name": "",
            "product_hint": "fenix8",
            "source": "profile",
        }
        with mock.patch.object(main, "_current_garmin_fit_sdk_version", return_value="21.212.0"), \
             mock.patch.object(main, "_extract_device_resolution_from_fit_path", return_value=resolution) as extract_mock:
            result = main.run_device_name_refresh_after_sdk_upgrade_once(limit=10)

        row = self._read_activity(activity_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["fit_reparse_updated"], 1)
        extract_mock.assert_called_once_with(str(fit_path))
        self.assertEqual(row["device_name"], "Fenix 8")
        self.assertEqual(row["device_vendor"], "garmin")
        self.assertEqual(row["device_product_key"], "garmin:4536")
        self.assertEqual(row["device_product_id"], "4536")
        self.assertEqual(row["device_product_hint"], "fenix8")
        self.assertEqual(row["device_serial"], "3510683807")
        self.assertEqual(row["title"], "不要改这个标题")
        self.assertEqual(row["avg_hr"], 129)
        self.assertEqual(row["avg_power"], 189)
        self.assertEqual(row["normalized_power"], 230)

    def test_missing_garmin_fit_file_is_skipped_without_retrying_forever(self):
        self._write_processed_sdk_version("21.208.0")
        missing_path = self.temp_dir / "missing.fit"
        self._insert_activity(
            file_path=str(missing_path),
            device_name="Unknown Device",
            device_vendor="garmin",
            device_mapping_status="unresolved",
        )

        with mock.patch.object(main, "_current_garmin_fit_sdk_version", return_value="21.212.0"), \
             mock.patch.object(main, "_extract_device_resolution_from_fit_path") as extract_mock:
            result = main.run_device_name_refresh_after_sdk_upgrade_once(limit=10)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped_missing_file"], 1)
        self.assertFalse(result["limited"])
        extract_mock.assert_not_called()
        self.assertEqual(self._read_processed_sdk_version(), "21.212.0")

    def test_resolved_device_records_are_not_reparsed_or_rewritten(self):
        self._write_processed_sdk_version("21.208.0")
        fit_path = self.temp_dir / "resolved.fit"
        fit_path.write_bytes(b"fit")
        activity_id = self._insert_activity(
            file_path=str(fit_path),
            title="已解析活动",
            device_name="Fenix 8",
            device_vendor="garmin",
            device_product_key="garmin:4536",
            device_product_id="4536",
            device_mapping_status="resolved",
        )

        with mock.patch.object(main, "_current_garmin_fit_sdk_version", return_value="21.212.0"), \
             mock.patch.object(main, "_extract_device_resolution_from_fit_path") as extract_mock:
            result = main.run_device_name_refresh_after_sdk_upgrade_once(limit=10)

        row = self._read_activity(activity_id)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["updated"], 0)
        extract_mock.assert_not_called()
        self.assertEqual(row["device_name"], "Fenix 8")
        self.assertEqual(row["device_mapping_status"], "resolved")
        self.assertEqual(row["title"], "已解析活动")
        self.assertEqual(self._read_processed_sdk_version(), "21.212.0")


if __name__ == "__main__":
    unittest.main()
