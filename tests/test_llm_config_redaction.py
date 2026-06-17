import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import llm_backend
import main
from main import Api


class TestLLMConfigRedaction(unittest.TestCase):
    def test_redact_llm_config_masks_api_key(self):
        redacted = llm_backend.redact_llm_config({"api_key": "sk-secret-123456", "provider": "openai"})

        self.assertEqual(redacted["api_key"], "")
        self.assertTrue(redacted["has_api_key"])
        self.assertEqual(redacted["api_key_masked"], "****3456")
        self.assertNotIn("sk-secret-123456", str(redacted))

    def test_get_llm_config_does_not_return_full_api_key(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "openai",
            "url": "https://example.test/v1/chat/completions",
            "model": "gpt-test",
            "api_key": "sk-live-secret-value",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "local_dir": "/tmp/tracks",
        }):
            config = Api().get_llm_config()

        self.assertTrue(config["ok"])
        self.assertEqual(config["code"], 0)
        self.assertEqual(config["msg"], "ok")
        self.assertIn("data", config)
        self.assertIn("traceId", config)
        self.assertEqual(config["data"]["api_key"], "")
        self.assertTrue(config["data"]["has_api_key"])
        self.assertEqual(config["data"]["api_key_masked"], "****alue")
        self.assertNotIn("sk-live-secret-value", str(config))

    def test_test_llm_config_preserves_ai_notification_state(self):
        stored = {
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "stored-secret",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "local_dir": "/tmp/old-tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "test_llm_connection", return_value="连接成功"), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock, \
                mock.patch.object(main, "load_application_config", return_value={}), \
                mock.patch.object(main, "persist_application_config", return_value={}):
            res = Api().test_llm_config(
                "local_mcp",
                "http://localhost:3000/v1/chat/completions",
                "openclaw",
                "",
                "agent-2",
                "garmin",
            )

        self.assertTrue(res["ok"])
        save_mock.assert_called_once()
        kwargs = save_mock.call_args.kwargs
        self.assertTrue(kwargs["ai_notified"])
        self.assertEqual(kwargs["ai_notified_hash"], "abc")
        self.assertEqual(kwargs["api_key"], "stored-secret")

    def test_set_ai_notified_preserves_existing_hash(self):
        stored = {
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "stored-secret",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "local_dir": "/tmp/tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_ai_notified(False)

        self.assertTrue(res["ok"])
        save_mock.assert_called_once()
        kwargs = save_mock.call_args.kwargs
        self.assertFalse(kwargs["ai_notified"])
        self.assertEqual(kwargs["ai_notified_hash"], "abc")

    def test_config_file_uses_user_fitvault_in_dev_mode(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(llm_backend.Path, "home", return_value=Path(td)), \
                mock.patch.object(llm_backend, "_migrate_legacy_project_config"):
            path = llm_backend._config_file()

        self.assertEqual(path, Path(td) / ".fitvault" / "llm_config.json")

    def test_config_file_migrates_legacy_project_config_once(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            legacy = Path(td) / "legacy_llm_config.json"
            legacy.write_text(json.dumps({
                "provider": "local_mcp",
                "url": "http://127.0.0.1:28789/v1/chat/completions",
                "model": "openclaw",
                "api_key": "legacy-secret",
                "watch_brand": "garmin",
            }), encoding="utf-8")

            with mock.patch.object(llm_backend.Path, "home", return_value=home), \
                    mock.patch.object(llm_backend, "_legacy_project_config_file", return_value=legacy), \
                    mock.patch.object(llm_backend.sys, "frozen", False, create=True):
                target = llm_backend._config_file()

            self.assertTrue(target.exists())
            migrated = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(migrated["url"], "http://127.0.0.1:28789/v1/chat/completions")
            self.assertEqual(migrated["api_key"], "legacy-secret")
            self.assertTrue(legacy.exists())

    def test_config_file_does_not_overwrite_existing_user_config(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            target = home / ".fitvault" / "llm_config.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"provider": "custom", "url": "kept", "model": "kept"}), encoding="utf-8")
            legacy = Path(td) / "legacy_llm_config.json"
            legacy.write_text(json.dumps({"provider": "local_mcp", "url": "legacy", "model": "legacy"}), encoding="utf-8")

            with mock.patch.object(llm_backend.Path, "home", return_value=home), \
                    mock.patch.object(llm_backend, "_legacy_project_config_file", return_value=legacy), \
                    mock.patch.object(llm_backend.sys, "frozen", False, create=True):
                resolved = llm_backend._config_file()

            kept = json.loads(resolved.read_text(encoding="utf-8"))
            self.assertEqual(kept["url"], "kept")
            self.assertEqual(kept["model"], "kept")


if __name__ == "__main__":
    unittest.main()
