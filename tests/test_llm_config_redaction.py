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

    def test_redact_llm_config_keeps_cli_fields(self):
        redacted = llm_backend.redact_llm_config({
            "api_key": "sk-secret-123456",
            "transport": "cli",
            "cli_type": "codex",
            "cli_path": "/usr/local/bin/codex",
            "cli_model": "gpt-5",
            "cli_timeout_sec": 120,
        })

        self.assertEqual(redacted["api_key"], "")
        self.assertEqual(redacted["transport"], "cli")
        self.assertEqual(redacted["cli_type"], "codex")
        self.assertEqual(redacted["cli_path"], "/usr/local/bin/codex")
        self.assertEqual(redacted["cli_model"], "gpt-5")
        self.assertEqual(redacted["cli_timeout_sec"], 120)

    def test_get_llm_config_does_not_return_full_api_key(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "transport": "http",
            "provider": "openai",
            "url": "https://example.test/v1/chat/completions",
            "model": "gpt-test",
            "api_key": "sk-live-secret-value",
            "agent_id": "agent-1",
            "cli_type": "",
            "cli_path": "",
            "cli_args": "",
            "cli_model": "",
            "cli_timeout_sec": 300,
            "watch_brand": "garmin",
            "garmin_region": "global",
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
        self.assertEqual(config["data"]["transport"], "http")
        self.assertEqual(config["data"]["cli_timeout_sec"], 300)
        self.assertEqual(config["data"]["garmin_region"], "global")
        self.assertNotIn("sk-live-secret-value", str(config))

    def test_load_llm_config_defaults_legacy_config_to_http_transport(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(llm_backend.Path, "home", return_value=Path(td)), \
                mock.patch.object(llm_backend, "_migrate_legacy_project_config"):
            target = Path(td) / ".fitvault" / "llm_config.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                "provider": "custom",
                "url": "https://example.test/v1/chat/completions",
                "model": "legacy-model",
                "api_key": "legacy-secret",
            }), encoding="utf-8")

            cfg = llm_backend.load_llm_config()

        self.assertEqual(cfg["transport"], "http")
        self.assertEqual(cfg["provider"], "custom")
        self.assertEqual(cfg["url"], "https://example.test/v1/chat/completions")
        self.assertEqual(cfg["model"], "legacy-model")
        self.assertEqual(cfg["cli_type"], "")
        self.assertEqual(cfg["cli_timeout_sec"], 300)
        self.assertEqual(cfg["garmin_region"], "cn")

    def test_save_and_load_cli_config_fields(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(llm_backend.Path, "home", return_value=Path(td)), \
                mock.patch.object(llm_backend, "_migrate_legacy_project_config"):
            llm_backend.save_llm_config(
                provider="cli_codex",
                url="",
                model="",
                api_key="",
                transport="cli",
                cli_type="codex",
                cli_path="/usr/local/bin/codex",
                cli_args="exec --json",
                cli_model="gpt-5",
                cli_timeout_sec=120,
                garmin_region="global",
            )
            cfg = llm_backend.load_llm_config()

        self.assertEqual(cfg["transport"], "cli")
        self.assertEqual(cfg["provider"], "cli_codex")
        self.assertEqual(cfg["cli_type"], "codex")
        self.assertEqual(cfg["cli_path"], "/usr/local/bin/codex")
        self.assertEqual(cfg["cli_args"], "exec --json")
        self.assertEqual(cfg["cli_model"], "gpt-5")
        self.assertEqual(cfg["cli_timeout_sec"], 120)
        self.assertEqual(cfg["garmin_region"], "global")

    def test_load_llm_config_normalizes_invalid_cli_values(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(llm_backend.Path, "home", return_value=Path(td)), \
                mock.patch.object(llm_backend, "_migrate_legacy_project_config"):
            target = Path(td) / ".fitvault" / "llm_config.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                "transport": "socket",
                "cli_type": "danger",
                "cli_timeout_sec": 999999,
            }), encoding="utf-8")

            cfg = llm_backend.load_llm_config()

        self.assertEqual(cfg["transport"], "http")
        self.assertEqual(cfg["cli_type"], "")
        self.assertEqual(cfg["cli_timeout_sec"], 1800)

    def test_test_llm_config_preserves_ai_notification_state(self):
        stored = {
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "stored-secret",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "garmin_region": "global",
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
        self.assertEqual(kwargs["transport"], "http")
        self.assertEqual(kwargs["garmin_region"], "global")

    def test_test_llm_config_cli_success_saves_cli_fields_and_preserves_state(self):
        stored = {
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "stored-secret",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "garmin_region": "global",
            "local_dir": "/tmp/old-tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "generate_text", return_value="连接成功") as generate_mock, \
                mock.patch.object(llm_backend, "test_llm_connection") as http_test_mock, \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock, \
                mock.patch.object(main, "load_application_config", return_value={}), \
                mock.patch.object(main, "persist_application_config", return_value={}):
            res = Api().test_llm_config(
                "cli_codex",
                "",
                "",
                "",
                "",
                "garmin",
                "cli",
                "codex",
                "/usr/local/bin/codex",
                "exec {prompt}",
                "gpt-5",
                120,
            )

        self.assertTrue(res["ok"])
        http_test_mock.assert_not_called()
        generate_mock.assert_called_once()
        self.assertEqual(generate_mock.call_args.kwargs["config"]["agent_id"], "")
        save_mock.assert_called_once()
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["transport"], "cli")
        self.assertEqual(kwargs["provider"], "cli_codex")
        self.assertEqual(kwargs["cli_type"], "codex")
        self.assertEqual(kwargs["cli_path"], "/usr/local/bin/codex")
        self.assertEqual(kwargs["cli_args"], "exec {prompt}")
        self.assertEqual(kwargs["cli_model"], "gpt-5")
        self.assertEqual(kwargs["cli_timeout_sec"], 120)
        self.assertTrue(kwargs["ai_notified"])
        self.assertEqual(kwargs["ai_notified_hash"], "abc")
        self.assertEqual(kwargs["garmin_region"], "global")

    def test_test_llm_config_openclaw_cli_success_passes_and_saves_agent_id(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={}), \
                mock.patch.object(llm_backend, "generate_text", return_value="连接成功") as generate_mock, \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock, \
                mock.patch.object(main, "load_application_config", return_value={}), \
                mock.patch.object(main, "persist_application_config", return_value={}):
            res = Api().test_llm_config(
                "local_mcp",
                "",
                "",
                "",
                "agent-8b65944a",
                "garmin",
                "cli",
                "openclaw",
                "/bin/openclaw",
                "",
                "",
                300,
            )

        self.assertTrue(res["ok"])
        self.assertEqual(generate_mock.call_args.kwargs["config"]["agent_id"], "agent-8b65944a")
        self.assertEqual(
            generate_mock.call_args.kwargs["messages"],
            [{"role": "user", "content": "请只回复这四个字：连接成功"}],
        )
        self.assertEqual(save_mock.call_args.kwargs["agent_id"], "agent-8b65944a")

    def test_test_llm_config_cli_failure_does_not_save(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={}), \
                mock.patch.object(llm_backend, "generate_text", side_effect=RuntimeError("cli failed")), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock, \
                mock.patch.object(main, "load_application_config", return_value={}), \
                mock.patch.object(main, "persist_application_config", return_value={}):
            res = Api().test_llm_config(
                "cli_codex",
                "",
                "",
                "",
                "",
                "",
                "cli",
                "codex",
            )

        self.assertFalse(res["ok"])
        save_mock.assert_not_called()
        self.assertIn("CLI 连接测试失败", res["msg"])
        self.assertIn("cli failed", res["msg"])
        self.assertNotIn("网关", res["msg"])

    def test_test_llm_config_openclaw_cli_failure_includes_diagnosis(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={}), \
                mock.patch.object(llm_backend, "generate_text", side_effect=RuntimeError("agent failed")), \
                mock.patch.object(llm_backend, "diagnose_openclaw_cli", return_value="OpenClaw Gateway 当前不可达：端口不一致"), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock, \
                mock.patch.object(main, "load_application_config", return_value={}), \
                mock.patch.object(main, "persist_application_config", return_value={}):
            res = Api().test_llm_config(
                "local_mcp",
                "",
                "",
                "",
                "",
                "",
                "cli",
                "openclaw",
                "/bin/openclaw",
            )

        self.assertFalse(res["ok"])
        save_mock.assert_not_called()
        self.assertIn("大模型 CLI 连接测试失败", res["msg"])
        self.assertIn("OpenClaw Gateway 当前不可达", res["msg"])
        self.assertIn("端口不一致", res["msg"])

    def test_test_llm_config_custom_cli_requires_path(self):
        with mock.patch.object(llm_backend, "generate_text") as generate_mock, \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().test_llm_config(
                "cli_custom",
                "",
                "",
                "",
                "",
                "",
                "cli",
                "custom",
                "",
            )

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_VALIDATION)
        generate_mock.assert_not_called()
        save_mock.assert_not_called()

    def test_set_ai_notified_preserves_existing_hash(self):
        stored = {
            "transport": "cli",
            "provider": "local_mcp",
            "url": "http://localhost:3000/v1/chat/completions",
            "model": "openclaw",
            "api_key": "stored-secret",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "garmin_region": "global",
            "local_dir": "/tmp/tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
            "cli_type": "codex",
            "cli_path": "/usr/local/bin/codex",
            "cli_args": "exec {prompt}",
            "cli_model": "gpt-5",
            "cli_timeout_sec": 120,
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_ai_notified(False)

        self.assertTrue(res["ok"])
        save_mock.assert_called_once()
        kwargs = save_mock.call_args.kwargs
        self.assertFalse(kwargs["ai_notified"])
        self.assertEqual(kwargs["ai_notified_hash"], "abc")
        self.assertEqual(kwargs["transport"], "cli")
        self.assertEqual(kwargs["cli_type"], "codex")
        self.assertEqual(kwargs["cli_path"], "/usr/local/bin/codex")
        self.assertEqual(kwargs["cli_args"], "exec {prompt}")
        self.assertEqual(kwargs["cli_model"], "gpt-5")
        self.assertEqual(kwargs["cli_timeout_sec"], 120)
        self.assertEqual(kwargs["garmin_region"], "global")

    def test_set_watch_brand_preserves_cli_config_fields(self):
        stored = {
            "transport": "cli",
            "provider": "cli_codex",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "garmin",
            "garmin_region": "global",
            "local_dir": "/tmp/tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
            "cli_type": "codex",
            "cli_path": "/usr/local/bin/codex",
            "cli_args": "exec {prompt}",
            "cli_model": "gpt-5",
            "cli_timeout_sec": 120,
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_watch_brand("coros")

        self.assertTrue(res["ok"])
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["transport"], "cli")
        self.assertEqual(kwargs["cli_type"], "codex")
        self.assertEqual(kwargs["cli_path"], "/usr/local/bin/codex")
        self.assertEqual(kwargs["cli_args"], "exec {prompt}")
        self.assertEqual(kwargs["cli_model"], "gpt-5")
        self.assertEqual(kwargs["cli_timeout_sec"], 120)
        self.assertEqual(kwargs["watch_brand"], "coros")
        self.assertEqual(kwargs["garmin_region"], "global")

    def test_set_garmin_region_preserves_existing_config_fields(self):
        stored = {
            "transport": "cli",
            "provider": "cli_codex",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "garmin_region": "cn",
            "local_dir": "/tmp/tracks",
            "ai_notified": True,
            "ai_notified_hash": "abc",
            "cli_type": "codex",
            "cli_path": "/usr/local/bin/codex",
            "cli_args": "exec {prompt}",
            "cli_model": "gpt-5",
            "cli_timeout_sec": 120,
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=stored), \
                mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_garmin_region("global")

        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["garmin_region"], "global")
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["transport"], "cli")
        self.assertEqual(kwargs["provider"], "cli_codex")
        self.assertEqual(kwargs["agent_id"], "agent-1")
        self.assertEqual(kwargs["watch_brand"], "garmin")
        self.assertEqual(kwargs["cli_type"], "codex")
        self.assertEqual(kwargs["cli_timeout_sec"], 120)
        self.assertEqual(kwargs["garmin_region"], "global")

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
