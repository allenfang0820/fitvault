import json
import unittest
from pathlib import Path
from unittest import mock

import coros_sync
import llm_backend
from main import Api


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "js_api_contract.json"


class TestCorosAuthApi(unittest.TestCase):
    def test_set_coros_region_persists_without_dropping_garmin_region(self):
        current = {
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": "",
            "watch_brand": "coros",
            "garmin_region": "global",
            "coros_region": "cn",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=current), \
             mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_coros_region("eu")

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["coros_region"], "eu")
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["coros_region"], "eu")
        self.assertEqual(kwargs["garmin_region"], "global")

    def test_set_coros_region_rejects_invalid_region(self):
        with mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_coros_region("global")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], 1001)
        self.assertEqual(res["data"]["coros_region"], "global")
        save_mock.assert_not_called()

    def test_set_garmin_region_preserves_coros_region(self):
        current = {
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "watch_brand": "garmin",
            "garmin_region": "cn",
            "coros_region": "eu",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=current), \
             mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_garmin_region("global")

        self.assertTrue(res["ok"], res)
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["garmin_region"], "global")
        self.assertEqual(kwargs["coros_region"], "eu")

    def test_set_watch_brand_preserves_coros_region(self):
        current = {
            "provider": "local_mcp",
            "url": "",
            "model": "",
            "api_key": "",
            "watch_brand": "garmin",
            "garmin_region": "global",
            "coros_region": "us",
        }
        with mock.patch.object(llm_backend, "load_llm_config", return_value=current), \
             mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            res = Api().set_watch_brand("coros")

        self.assertTrue(res["ok"], res)
        kwargs = save_mock.call_args.kwargs
        self.assertEqual(kwargs["watch_brand"], "coros")
        self.assertEqual(kwargs["coros_region"], "us")

    def test_check_coros_auth_status_wraps_provider_success(self):
        status = coros_sync.CorosAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/coros/cn/token.json",
            message="已检测到 COROS 授权（cn）。",
            login_command=["bash", "install_coros_mcp.sh", "--region", "cn"],
            mcp_authorized=True,
            node_available=True,
            skill_available=True,
            node_path="/tmp/node/bin/node",
            openclaw_node_binary="/tmp/node/bin/node",
            openclaw_mjs="/tmp/openclaw.mjs",
            keepalive_region="cn",
            keepalive_mcp_url="https://mcpcn.coros.com/mcp",
            keepalive_token_path="/tmp/coros/cn/token.json",
            diagnostics=[{"name": "keepalive_config", "status": "ok", "message": "ok"}],
        )
        with mock.patch.object(coros_sync, "check_auth_status", return_value=status) as provider:
            res = Api().check_coros_auth_status("cn")

        provider.assert_called_once_with(region="cn")
        self.assertTrue(res["ok"])
        self.assertEqual(res["code"], 0)
        self.assertEqual(res["data"]["status"], "authorized")
        self.assertTrue(res["data"]["authorized"])
        self.assertTrue(res["data"]["mcp_authorized"])
        self.assertNotIn("traininghub_authorized", res["data"])
        self.assertNotIn("traininghub_token_path", res["data"])
        self.assertEqual(res["data"]["login_command"], status.login_command)
        self.assertTrue(res["data"]["skill_available"])
        self.assertEqual(res["data"]["node_path"], "/tmp/node/bin/node")
        self.assertEqual(res["data"]["openclaw_node_binary"], "/tmp/node/bin/node")
        self.assertEqual(res["data"]["openclaw_mjs"], "/tmp/openclaw.mjs")
        self.assertEqual(res["data"]["keepalive_region"], "cn")
        self.assertEqual(res["data"]["keepalive_mcp_url"], "https://mcpcn.coros.com/mcp")
        self.assertEqual(res["data"]["diagnostics"][0]["name"], "keepalive_config")

    def test_check_coros_auth_status_wraps_provider_failure(self):
        status = coros_sync.CorosAuthStatus(
            ok=False,
            region="cn",
            status="missing_token",
            token_path="/tmp/coros/cn/token.json",
            message="请先登录 COROS（cn），未检测到 MCP 授权 token。",
            login_command=["bash", "install_coros_mcp.sh", "--region", "cn"],
            mcp_authorized=False,
            node_available=True,
            skill_available=True,
            diagnostics=[{"name": "mcp_token", "status": "failed", "message": "missing"}],
        )
        with mock.patch.object(coros_sync, "check_auth_status", return_value=status):
            res = Api().check_coros_auth_status("cn")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], 3001)
        self.assertEqual(res["data"]["status"], "missing_token")
        self.assertFalse(res["data"]["authorized"])
        self.assertFalse(res["data"]["mcp_authorized"])
        self.assertEqual(res["data"]["diagnostics"][0]["name"], "mcp_token")

    def test_start_coros_login_wraps_provider_success(self):
        result = coros_sync.CorosLoginResult(
            ok=True,
            region="eu",
            status="completed",
            command=["bash", "install_coros_mcp.sh", "--region", "eu"],
            stdout="ok",
            stderr="",
            message="COROS 授权已完成（eu）。",
        )
        with mock.patch.object(coros_sync, "start_login", return_value=result) as provider:
            res = Api().start_coros_login("eu")

        provider.assert_called_once_with(region="eu")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["status"], "completed")
        self.assertEqual(res["data"]["stdout"], "ok")
        self.assertEqual(res["data"]["command"], result.command)

    def test_start_coros_login_wraps_provider_failure(self):
        result = coros_sync.CorosLoginResult(
            ok=False,
            region="cn",
            status="failed",
            command=["bash", "install_coros_mcp.sh", "--region", "cn"],
            stdout="",
            stderr="bad auth",
            message="COROS 授权失败 (exit 1): bad auth",
        )
        with mock.patch.object(coros_sync, "start_login", return_value=result):
            res = Api().start_coros_login("cn")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], 3001)
        self.assertEqual(res["data"]["status"], "failed")
        self.assertEqual(res["data"]["stderr"], "bad auth")

    def test_check_coros_auth_status_empty_region_uses_config_region(self):
        status = coros_sync.CorosAuthStatus(
            ok=True,
            region="us",
            status="authorized",
            token_path="/tmp/coros/us/token.json",
            message="ok",
            login_command=[],
            mcp_authorized=True,
            node_available=True,
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "us"}), \
             mock.patch.object(coros_sync, "check_auth_status", return_value=status) as provider:
            res = Api().check_coros_auth_status("")

        provider.assert_called_once_with(region="us")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["region"], "us")

    def test_start_coros_login_empty_region_uses_config_region(self):
        result = coros_sync.CorosLoginResult(
            ok=True,
            region="us",
            status="completed",
            command=["bash", "install_coros_mcp.sh", "--region", "us"],
            stdout="ok",
            stderr="",
            message="ok",
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "us"}), \
             mock.patch.object(coros_sync, "start_login", return_value=result) as provider:
            res = Api().start_coros_login("")

        provider.assert_called_once_with(region="us")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["region"], "us")

    def test_coros_auth_api_does_not_call_llm_backend(self):
        status = coros_sync.CorosAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/coros/cn/token.json",
            message="ok",
            login_command=[],
            mcp_authorized=True,
            node_available=True,
        )
        result = coros_sync.CorosLoginResult(
            ok=True,
            region="cn",
            status="completed",
            command=[],
            stdout="",
            stderr="",
            message="ok",
        )
        with mock.patch.object(coros_sync, "check_auth_status", return_value=status), \
             mock.patch.object(coros_sync, "start_login", return_value=result), \
             mock.patch.object(llm_backend, "generate_text") as generate_text, \
             mock.patch.object(llm_backend, "chat_completions") as chat_completions:
            Api().check_coros_auth_status("cn")
            Api().start_coros_login("cn")

        generate_text.assert_not_called()
        chat_completions.assert_not_called()

    def test_coros_account_api_contract_documents_provider_boundary(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        methods = {item["name"]: item for item in contract["methods"]}

        for name in ("set_coros_region", "check_coros_auth_status", "start_coros_login", "fetch_mcp_persona", "sync_remote_fit_activities"):
            self.assertIn(name, methods)
        self.assertNotIn("start_coros_traininghub_login", methods)

        fetch_contract = methods["fetch_mcp_persona"]
        self.assertIn("profile_sync_summary", fetch_contract["returns"])
        self.assertIn("provider_error_code", fetch_contract["returns"])
        self.assertIn("action_hint", fetch_contract["returns"])
        self.assertIn("独立 provider", fetch_contract["description"])
        self.assertIn("不走 LLM/OpenClaw", fetch_contract["description"])
        self.assertIn("纯 MCP", fetch_contract["description"])

        status_contract = methods["check_coros_auth_status"]
        self.assertIn("keepalive_mcp_url", status_contract["returns"])
        self.assertIn("node_path", status_contract["returns"])
        self.assertIn("openclaw_node_binary", status_contract["returns"])
        self.assertIn("openclaw_mjs", status_contract["returns"])
        self.assertIn("diagnostics", status_contract["returns"])
        self.assertNotIn("traininghub", status_contract["returns"].lower())
        self.assertIn("不读取 token 内容", status_contract["description"])
        self.assertIn("不联系 COROS", status_contract["description"])
        self.assertIn("nvm", status_contract["description"])


if __name__ == "__main__":
    unittest.main()
