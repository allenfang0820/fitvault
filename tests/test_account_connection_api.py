import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import coros_sync
import garmin_sync
import llm_backend
from main import Api


class TestAccountConnectionApi(unittest.TestCase):
    def _garmin_status(self, *, ok=False, status="missing_token", message="missing"):
        return garmin_sync.GarminAuthStatus(
            ok=ok,
            region="cn",
            status=status,
            token_path="/tmp/garmin_auth_cn",
            message=message,
            login_command=["python", "login.py", "--region", "cn"],
        )

    def _coros_status(self, *, ok=False, status="missing_token", message="missing", node_available=True):
        return coros_sync.CorosAuthStatus(
            ok=ok,
            region="cn",
            status=status,
            token_path="/tmp/coros/cn/token.json",
            message=message,
            login_command=["bash", "install_coros_mcp.sh", "--region", "cn"],
            mcp_authorized=ok,
            node_available=node_available,
            skill_available=True,
            diagnostics=[{"name": "mcp_token", "status": "ok" if ok else "failed", "message": "checked"}],
        )

    def test_list_account_connections_returns_two_sanitized_cards(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn", "coros_region": "cn"}), \
             mock.patch.object(garmin_sync, "check_auth_status", return_value=self._garmin_status()), \
             mock.patch.object(coros_sync, "check_auth_status", return_value=self._coros_status()):
            res = Api().list_account_connections()

        self.assertTrue(res["ok"], res)
        connections = res["data"]["connections"]
        self.assertEqual([item["provider"] for item in connections], ["garmin", "coros"])
        self.assertEqual(connections[0]["status"], "idle")
        self.assertEqual(connections[1]["status"], "idle")
        self.assertNotIn("login_command", str(res["data"]))

    def test_coros_sync_error_payload_is_stable_and_redacted(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "cn"}):
            payload = Api()._coros_sync_error_payload(
                provider_error_code="coros_fit_download_failed",
                message="raw access_token=abc123 password=secret",
                start_date="2026-05-01",
                end_date="2026-05-31",
                exc=coros_sync.CorosFitDownloadError(
                    "Session not found\nstackTrace refresh_token=def456 cookie=session-secret",
                    code="coros_mcp_unavailable",
                ),
                download={
                    "errors": [
                        {
                            "error": "access_token=abc123 refresh_token=def456 password=secret cookie=session-secret",
                        }
                    ]
                },
            )

        serialized = str(payload)
        self.assertEqual(payload["provider"], "coros")
        self.assertEqual(payload["provider_error_code"], "coros_fit_download_failed")
        self.assertIn("action_hint", payload)
        self.assertIn("diagnostics", payload)
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("def456", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("session-secret", serialized)

    def test_check_account_connection_validates_provider_and_region(self):
        api = Api()

        provider_res = api.check_account_connection("strava", "cn")
        self.assertFalse(provider_res["ok"])
        self.assertEqual(provider_res["code"], 1001)

        region_res = api.check_account_connection("garmin", "eu")
        self.assertFalse(region_res["ok"])
        self.assertEqual(region_res["code"], 1001)

    def test_check_account_connection_uses_config_region_and_strips_command(self):
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="global",
            status="authorized",
            token_path="/tmp/garmin_auth_global",
            message="ok password=secret token=abc123",
            login_command=["python", "login.py", "--region", "global"],
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "global"}), \
             mock.patch.object(garmin_sync, "check_auth_status", return_value=status) as provider:
            res = Api().check_account_connection("garmin", "")

        provider.assert_called_once_with(region="global")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["region"], "global")
        self.assertEqual(res["data"]["status"], "authorized")
        serialized = str(res["data"])
        self.assertNotIn("login_command", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("abc123", serialized)

    def test_start_account_connection_garmin_missing_credentials(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}):
            res = Api().start_account_connection("garmin", "", {})

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["status"], "needs_credentials")
        self.assertFalse(res["data"]["authorized"])
        self.assertNotIn("password", str(res["data"]).lower())

    def test_start_account_connection_garmin_app_login_success(self):
        result = garmin_sync.GarminAppLoginResult(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 授权成功。",
        )
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="已检测到 Garmin 授权。",
            login_command=["SHOULD_NOT_RETURN"],
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", return_value=result) as login_mock, \
             mock.patch.object(garmin_sync, "check_auth_status", return_value=status), \
             mock.patch.object(garmin_sync, "start_login") as terminal_login:
            res = Api().start_account_connection("garmin", "", {"email": "runner@example.com", "password": "secret-password"})

        login_mock.assert_called_once_with(email="runner@example.com", password="secret-password", region="cn")
        terminal_login.assert_not_called()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["status"], "authorized")
        self.assertTrue(res["data"]["authorized"])
        serialized = str(res["data"])
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("runner@example.com", serialized)
        self.assertNotIn("SHOULD_NOT_RETURN", serialized)

    def test_start_account_connection_garmin_windows_does_not_need_fitvault_cli(self):
        result = garmin_sync.GarminAppLoginResult(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 授权成功。",
        )
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="已检测到 Garmin 授权。",
            login_command=[],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "FitVault.exe"
            exe.write_text("", encoding="utf-8")
            with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
                 mock.patch.object(garmin_sync.sys, "platform", "win32"), \
                 mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
                 mock.patch.object(garmin_sync.sys, "executable", str(exe)), \
                 mock.patch.object(garmin_sync, "login_app", return_value=result) as login_mock, \
                 mock.patch.object(garmin_sync, "check_auth_status", return_value=status), \
                 mock.patch.object(garmin_sync, "start_login") as terminal_login:
                res = Api().start_account_connection("garmin", "cn", {"email": "runner@example.com", "password": "secret-password"})

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["status"], "authorized")
        login_mock.assert_called_once_with(email="runner@example.com", password="secret-password", region="cn")
        terminal_login.assert_not_called()
        self.assertNotIn("FitVaultCLI.exe", str(res["data"]))

    def test_start_and_continue_garmin_mfa_flow(self):
        api = Api()
        needs_mfa = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="needs_mfa",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 账号需要 MFA 验证码。",
            mfa_state={"mfa": "state"},
        )
        success = garmin_sync.GarminAppLoginResult(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 授权成功。",
        )
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="ok",
            login_command=[],
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", side_effect=[needs_mfa, success]) as login_mock, \
             mock.patch.object(garmin_sync, "check_auth_status", return_value=status):
            start = api.start_account_connection("garmin", "", {"email": "runner@example.com", "password": "secret-password"})
            self.assertTrue(start["ok"], start)
            self.assertEqual(start["data"]["status"], "needs_mfa")
            session_id = start["data"]["session_id"]
            self.assertIn(session_id, api._account_connection_sessions)

            cont = api.continue_account_connection(session_id, {"mfa_code": "123456"})

        self.assertEqual(login_mock.call_args_list[0].kwargs, {
            "email": "runner@example.com",
            "password": "secret-password",
            "region": "cn",
        })
        self.assertEqual(login_mock.call_args_list[1].kwargs, {
            "email": "runner@example.com",
            "password": "secret-password",
            "region": "cn",
            "mfa_code": "123456",
            "mfa_state": {"mfa": "state"},
        })
        self.assertTrue(cont["ok"], cont)
        self.assertEqual(cont["data"]["status"], "authorized")
        self.assertNotIn(session_id, api._account_connection_sessions)
        serialized = str(cont["data"])
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("123456", serialized)
        self.assertNotIn("mfa_state", serialized)

    def test_continue_garmin_mfa_requires_code_without_dropping_session(self):
        api = Api()
        needs_mfa = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="needs_mfa",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 账号需要 MFA 验证码。",
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", return_value=needs_mfa):
            start = api.start_account_connection("garmin", "", {"email": "runner@example.com", "password": "secret-password"})
            session_id = start["data"]["session_id"]
            cont = api.continue_account_connection(session_id, {})

        self.assertTrue(cont["ok"], cont)
        self.assertEqual(cont["data"]["status"], "needs_mfa")
        self.assertIn(session_id, api._account_connection_sessions)
        self.assertNotIn("secret-password", str(cont["data"]))

    def test_start_account_connection_garmin_failure_is_redacted(self):
        result = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="failed",
            token_path="/tmp/garmin_auth_cn",
            message="bad password=secret-password token=abc123 email runner@example.com",
            provider_error_code="garmin_auth_failed",
            action_hint="请回配置页重新连接 Garmin 账号。",
            diagnostics={"provider": "garmin", "error_summary": "bad password=*** token=***"},
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", return_value=result):
            res = Api().start_account_connection("garmin", "", {"email": "runner@example.com", "password": "secret-password"})

        self.assertFalse(res["ok"])
        self.assertEqual(res["data"]["provider_error_code"], "garmin_auth_failed")
        self.assertIn("action_hint", res["data"])
        self.assertIn("diagnostics", res["data"])
        serialized = str(res)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("runner@example.com", serialized)

    def test_start_account_connection_garmin_windows_source_error_is_stable(self):
        result = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="failed",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin provider 依赖与应用不兼容，请更新应用后重试。",
            provider_error_code="garmin_provider_api_incompatible",
            action_hint="Garmin provider 依赖与应用不兼容，请重新安装或更新应用。",
            diagnostics={"provider": "garmin", "cause": "packaged_callback_source_unavailable"},
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync.sys, "platform", "win32"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync, "login_app", return_value=result), \
             mock.patch.object(garmin_sync, "start_login") as terminal_login:
            res = Api().start_account_connection(
                "garmin",
                "cn",
                {"email": "runner@example.com", "password": "secret-password"},
            )

        self.assertFalse(res["ok"])
        self.assertEqual(res["data"]["status"], "failed")
        self.assertEqual(res["data"]["provider_error_code"], "garmin_provider_api_incompatible")
        self.assertEqual(res["data"]["diagnostics"]["cause"], "packaged_callback_source_unavailable")
        terminal_login.assert_not_called()
        serialized = str(res)
        self.assertNotIn("could not get source code", serialized)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("runner@example.com", serialized)
        self.assertNotIn("FitVaultCLI.exe", serialized)

    def test_continue_account_connection_garmin_mfa_failure_is_stable_and_redacted(self):
        api = Api()
        needs_mfa = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="needs_mfa",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 账号需要 MFA 验证码。",
        )
        failed = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="failed",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin MFA 验证失败，请重新输入验证码。",
            provider_error_code="garmin_mfa_failed",
            action_hint="请重新输入 Garmin MFA 验证码，或回配置页重新连接 Garmin 账号。",
            diagnostics={"provider": "garmin", "error_summary": "MFA failed"},
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", side_effect=[needs_mfa, failed]):
            start = api.start_account_connection(
                "garmin",
                "",
                {"email": "runner@example.com", "password": "secret-password"},
            )
            session_id = start["data"]["session_id"]
            cont = api.continue_account_connection(session_id, {"mfa_code": "123456"})

        self.assertFalse(cont["ok"])
        self.assertEqual(cont["data"]["provider_error_code"], "garmin_mfa_failed")
        serialized = str(cont)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("123456", serialized)
        self.assertNotIn("runner@example.com", serialized)

    def test_garmin_app_login_401_message_is_actionable_without_cli_hint(self):
        message = garmin_sync._garmin_app_login_failure_message(
            "cn",
            "Garmin 认证失败（region=cn, tokenstore=/tmp/garmin_auth_cn）。"
            "请先运行 login.py 登录对应区域账号；国际区账号使用 --region global。"
            " 原始错误：Error in request: 401 Client Error: Unauthorized for url: "
            "https://sso.garmin.cn/sso/signin?id=gauth-widget&embedWidget=true",
        )

        self.assertIn("Garmin 中国区 授权失败", message)
        self.assertIn("账号区域", message)
        self.assertNotIn("login.py", message)
        self.assertNotIn("https://", message)
        self.assertNotIn("tokenstore", message)

    def test_start_and_continue_coros_session_then_expire(self):
        api = Api()
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "cn"}), \
             mock.patch.object(Api, "_run_coros_connection_worker") as worker_mock:
            start = api.start_account_connection("coros", "", {})

        self.assertTrue(start["ok"], start)
        self.assertEqual(start["data"]["status"], "checking")
        session_id = start["data"]["session_id"]
        worker_mock.assert_called_once_with(session_id, "cn")

        polled = api.continue_account_connection(session_id, {})
        self.assertTrue(polled["ok"], polled)
        self.assertEqual(polled["data"]["session_id"], session_id)
        self.assertEqual(polled["data"]["status"], "checking")

        api._account_connection_sessions[session_id]["expires_at"] = time.time() - 1
        expired = api.continue_account_connection(session_id, {})
        self.assertTrue(expired["ok"], expired)
        self.assertEqual(expired["data"]["status"], "expired")

    def test_start_coros_connection_does_not_call_terminal_login(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"coros_region": "cn"}), \
             mock.patch.object(Api, "_run_coros_connection_worker"), \
             mock.patch.object(coros_sync, "start_login") as terminal_login:
            res = Api().start_account_connection("coros", "", {})

        self.assertTrue(res["ok"], res)
        terminal_login.assert_not_called()
        serialized = str(res["data"])
        self.assertNotIn("cmd.exe", serialized)
        self.assertNotIn("osascript", serialized)
        self.assertNotIn("install_coros_mcp", serialized)

    def test_coros_worker_marks_node_missing_failed(self):
        api = Api()
        session = api._create_account_session(
            provider="coros",
            region="cn",
            status="checking",
            message="start",
            progress=[],
        )
        failed = coros_sync.CorosConnectionStepResult(
            ok=False,
            status="failed",
            message="未检测到 Node.js",
            diagnostics=[{"name": "node", "status": "failed", "message": "missing"}],
        )
        with mock.patch.object(coros_sync, "prepare_coros_connection_runtime", return_value=failed), \
             mock.patch.object(coros_sync, "start_coros_oauth_login") as oauth_mock:
            api._run_coros_connection_worker(session["session_id"], "cn")

        oauth_mock.assert_not_called()
        polled = api.continue_account_connection(session["session_id"], {})
        self.assertTrue(polled["ok"], polled)
        self.assertEqual(polled["data"]["status"], "failed")
        self.assertIn("diagnostics", polled["data"])

    def test_coros_worker_starts_oauth_and_waits_for_callback(self):
        api = Api()
        session = api._create_account_session(
            provider="coros",
            region="cn",
            status="checking",
            message="start",
            progress=[],
        )
        runtime = coros_sync.CorosConnectionStepResult(
            ok=True,
            status="checking",
            message="ready",
            node_path="/tmp/node",
            npm_path="/tmp/npm",
            coros_mcp_path="/tmp/coros-mcp",
            token_path="/tmp/coros/cn/token.json",
            diagnostics=[{"name": "node", "status": "ok", "message": "ok"}],
        )
        oauth = coros_sync.CorosConnectionStepResult(
            ok=True,
            status="waiting_callback",
            message="已打开系统浏览器，请在 COROS 页面完成 OAuth 授权。",
            coros_mcp_path="/tmp/coros-mcp",
            token_path="/tmp/coros/cn/token.json",
            diagnostics=[{"name": "oauth", "status": "waiting", "message": "waiting"}],
        )
        waiting = coros_sync.CorosConnectionStepResult(
            ok=True,
            status="waiting_callback",
            message="等待你在浏览器中完成 COROS OAuth 授权...",
            coros_mcp_path="/tmp/coros-mcp",
            token_path="/tmp/coros/cn/token.json",
        )
        with mock.patch.object(coros_sync, "prepare_coros_connection_runtime", return_value=runtime), \
             mock.patch.object(coros_sync, "start_coros_oauth_login", return_value=oauth) as oauth_mock, \
             mock.patch.object(coros_sync, "finish_coros_oauth_login", return_value=waiting):
            api._run_coros_connection_worker(session["session_id"], "cn")
            polled = api.continue_account_connection(session["session_id"], {})

        oauth_mock.assert_called_once_with(region="cn", coros_mcp_path="/tmp/coros-mcp")
        self.assertEqual(polled["data"]["status"], "waiting_callback")
        self.assertEqual(polled["data"]["node_path"], "/tmp/node")

    def test_coros_continue_authorizes_when_token_file_appears(self):
        api = Api()
        with tempfile.TemporaryDirectory() as temp_dir:
            token = Path(temp_dir) / "cn" / "token.json"
            token.parent.mkdir(parents=True)
            token.write_text('{"access_token":"secret-token"}', encoding="utf-8")
            session = api._create_account_session(
                provider="coros",
                region="cn",
                status="waiting_callback",
                message="waiting",
                progress=[],
            )
            api._account_connection_sessions[session["session_id"]]["token_path"] = str(token)
            api._account_connection_sessions[session["session_id"]]["coros_mcp_path"] = "/tmp/coros-mcp"
            with mock.patch.object(coros_sync, "apply_coros_openclaw_optional", return_value={"name": "openclaw", "status": "warning", "message": "skipped"}):
                res = api.continue_account_connection(session["session_id"], {})

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["status"], "authorized")
        self.assertTrue(res["data"]["authorized"])
        self.assertEqual(res["data"]["diagnostics"][-1]["status"], "warning")
        serialized = str(res["data"])
        self.assertNotIn("secret-token", serialized)

    def test_start_account_connection_does_not_return_garmin_secret_payload(self):
        result = garmin_sync.GarminAppLoginResult(
            ok=False,
            region="cn",
            status="needs_mfa",
            token_path="/tmp/garmin_auth_cn",
            message="Garmin 账号需要 MFA 验证码。",
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "cn"}), \
             mock.patch.object(garmin_sync, "login_app", return_value=result):
            res = Api().start_account_connection("garmin", "", {"email": "runner@example.com", "password": "super-secret"})

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["data"]["status"], "needs_mfa")
        serialized = str(res["data"])
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("runner@example.com", serialized)

    def test_disconnect_garmin_removes_only_tokenstore(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            token_dir = root / "garmin_auth_cn"
            token_dir.mkdir()
            (token_dir / "garmin_tokens.json").write_text("{}", encoding="utf-8")
            keep_file = root / "activity.fit"
            keep_file.write_text("fit", encoding="utf-8")

            with mock.patch.dict(os.environ, {"QCLAW_WORKSPACE_DIR": str(root)}):
                res = Api().disconnect_account("garmin", "cn")

            self.assertTrue(res["ok"], res)
            self.assertFalse(token_dir.exists())
            self.assertTrue(keep_file.exists())
            self.assertEqual(res["data"]["status"], "idle")

    def test_disconnect_coros_removes_token_file_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            token_file = root / "cn" / "token.json"
            token_file.parent.mkdir(parents=True)
            token_file.write_text('{"access_token":"secret"}', encoding="utf-8")
            keep_file = root / "cn" / "notes.txt"
            keep_file.write_text("keep", encoding="utf-8")

            with mock.patch.dict(os.environ, {"COROS_MCP_TOKEN_ROOT": str(root)}):
                res = Api().disconnect_account("coros", "cn")

            self.assertTrue(res["ok"], res)
            self.assertFalse(token_file.exists())
            self.assertTrue(keep_file.exists())
            self.assertEqual(res["data"]["status"], "idle")


if __name__ == "__main__":
    unittest.main()
