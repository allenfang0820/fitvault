import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import main


class TestDemSessionCache(unittest.TestCase):
    def test_startup_removes_stale_sessions_without_creating_current_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache" / "dem-session"
            stale = root / "session_stale"
            stale.mkdir(parents=True)
            (stale / "terrain.bin").write_bytes(b"stale")
            keep = root / "not-a-session"
            keep.mkdir()

            cache = main.DemSessionCache(root=root, session_id="session_current")

            self.assertFalse(stale.exists())
            self.assertTrue(keep.exists())
            self.assertFalse(cache.session_dir.exists())

    def test_user_preparation_creates_only_current_session_with_buffered_bbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache" / "dem-session"
            cache = main.DemSessionCache(root=root, session_id="session_current", buffer_meters=1500)

            bbox = cache.prepare_route_bbox([
                {"lon": 116.391, "lat": 39.907, "alt": 43},
                {"lon": 116.401, "lat": 39.917, "alt": 45},
            ])

            self.assertTrue(cache.session_dir.exists())
            self.assertLess(bbox["west"], 116.391)
            self.assertGreater(bbox["east"], 116.401)
            self.assertLess(bbox["south"], 39.907)
            self.assertGreater(bbox["north"], 39.917)
            self.assertEqual(bbox["buffer_meters"], 1500)
            metadata = json.loads((cache.session_dir / "route-bbox.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["bbox"], bbox)

    def test_cleanup_current_session_removes_only_current_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache" / "dem-session"
            cache = main.DemSessionCache(root=root, session_id="session_current")
            cache.prepare_route_bbox([
                {"lon": 120.0, "lat": 30.0},
                {"lon": 120.01, "lat": 30.01},
            ])
            other = root / "session_other"
            other.mkdir()

            self.assertTrue(cache.cleanup_current_session())
            self.assertFalse(cache.session_dir.exists())
            self.assertTrue(other.exists())

    def test_api_uses_unified_response_and_never_writes_activity_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cache" / "dem-session"
            with mock.patch.object(main, "DEM_SESSION_CACHE_ROOT", root):
                api = main.Api()
                response = api.prepare_dem_session_cache(json.dumps([
                    {"lon": 121.4737, "lat": 31.2304},
                    {"lon": 121.4837, "lat": 31.2404},
                ]))

            self.assertTrue(response["ok"], response)
            self.assertEqual(response["code"], main.API_CODE_OK)
            self.assertTrue(response["data"]["prepared"])
            self.assertFalse((Path(temp) / "workspace" / "tracks").exists())
            api.cleanup_dem_session_cache()
            self.assertFalse((root / api._dem_session_cache.session_id).exists())

    def test_invalid_route_is_rejected_without_creating_session_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = main.DemSessionCache(
                root=Path(temp) / "cache" / "dem-session",
                session_id="session_invalid",
            )
            with self.assertRaisesRegex(ValueError, "有效 GPS"):
                cache.prepare_route_bbox([{"lon": "bad", "lat": None}])
            self.assertFalse(cache.session_dir.exists())

    def test_main_cleans_current_dem_session_when_webview_exits(self):
        class EventHook:
            def __iadd__(self, callback):
                self.callback = callback
                return self

        class FakeWindow:
            def __init__(self):
                self.events = types.SimpleNamespace(loaded=EventHook())

        fake_api = mock.Mock()
        fake_webview = types.SimpleNamespace(
            create_window=mock.Mock(return_value=FakeWindow()),
            start=mock.Mock(),
        )
        fake_watch = mock.Mock()

        try:
            with mock.patch.dict(sys.modules, {"webview": fake_webview}), \
                 mock.patch.object(main, "Api", return_value=fake_api), \
                 mock.patch.object(main, "FITFolderWatchService", return_value=fake_watch), \
                 mock.patch.object(main, "set_runtime_app_icon"), \
                 mock.patch.object(main, "_get_schema_version", return_value=main.CURRENT_SCHEMA_VERSION), \
                 mock.patch.object(main, "html_file", return_value=Path("/tmp/track.html")):
                main.main()
        finally:
            main._APP_SHUTTING_DOWN.clear()

        fake_api.cleanup_dem_session_cache.assert_called_once_with()
        fake_watch.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
