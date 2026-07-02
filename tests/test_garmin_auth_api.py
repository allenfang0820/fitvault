import unittest
from unittest import mock

import garmin_sync
import llm_backend
from main import Api


class TestGarminAuthApi(unittest.TestCase):
    def test_check_garmin_auth_status_wraps_provider_success(self):
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="已检测到 Garmin 授权（cn）。",
            login_command=["python", "login.py", "--region", "cn"],
        )
        with mock.patch.object(garmin_sync, "check_auth_status", return_value=status) as provider:
            res = Api().check_garmin_auth_status("cn")

        provider.assert_called_once_with(region="cn")
        self.assertTrue(res["ok"])
        self.assertEqual(res["code"], 0)
        self.assertEqual(res["data"]["status"], "authorized")
        self.assertTrue(res["data"]["authorized"])
        self.assertEqual(res["data"]["login_command"], status.login_command)

    def test_check_garmin_auth_status_wraps_provider_failure(self):
        status = garmin_sync.GarminAuthStatus(
            ok=False,
            region="cn",
            status="missing_token",
            token_path="/tmp/garmin_auth_cn",
            message="请先登录 Garmin（cn），未检测到授权 token。",
            login_command=["python", "login.py", "--region", "cn"],
        )
        with mock.patch.object(garmin_sync, "check_auth_status", return_value=status):
            res = Api().check_garmin_auth_status("cn")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], 3001)
        self.assertEqual(res["data"]["status"], "missing_token")
        self.assertFalse(res["data"]["authorized"])

    def test_start_garmin_login_wraps_provider_success(self):
        result = garmin_sync.GarminLoginResult(
            ok=True,
            region="global",
            status="completed",
            command=["python", "login.py", "--region", "global"],
            stdout="ok",
            stderr="",
            message="Garmin 登录授权已完成（global）。",
        )
        with mock.patch.object(garmin_sync, "start_login", return_value=result) as provider:
            res = Api().start_garmin_login("global")

        provider.assert_called_once_with(region="global")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["status"], "completed")
        self.assertEqual(res["data"]["stdout"], "ok")
        self.assertEqual(res["data"]["command"], result.command)

    def test_start_garmin_login_wraps_provider_failure(self):
        result = garmin_sync.GarminLoginResult(
            ok=False,
            region="cn",
            status="failed",
            command=["python", "login.py", "--region", "cn"],
            stdout="",
            stderr="bad auth",
            message="Garmin 登录授权失败 (exit 1): bad auth",
        )
        with mock.patch.object(garmin_sync, "start_login", return_value=result):
            res = Api().start_garmin_login("cn")

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], 3001)
        self.assertEqual(res["data"]["status"], "failed")
        self.assertEqual(res["data"]["stderr"], "bad auth")

    def test_check_garmin_auth_status_empty_region_uses_config_region(self):
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="global",
            status="authorized",
            token_path="/tmp/garmin_auth_global",
            message="ok",
            login_command=[],
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "global"}), \
             mock.patch.object(garmin_sync, "check_auth_status", return_value=status) as provider:
            res = Api().check_garmin_auth_status("")

        provider.assert_called_once_with(region="global")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["region"], "global")

    def test_start_garmin_login_empty_region_uses_config_region(self):
        result = garmin_sync.GarminLoginResult(
            ok=True,
            region="global",
            status="completed",
            command=["python", "login.py", "--region", "global"],
            stdout="ok",
            stderr="",
            message="ok",
        )
        with mock.patch.object(llm_backend, "load_llm_config", return_value={"garmin_region": "global"}), \
             mock.patch.object(garmin_sync, "start_login", return_value=result) as provider:
            res = Api().start_garmin_login("")

        provider.assert_called_once_with(region="global")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["region"], "global")

    def test_garmin_auth_api_does_not_call_llm_backend(self):
        status = garmin_sync.GarminAuthStatus(
            ok=True,
            region="cn",
            status="authorized",
            token_path="/tmp/garmin_auth_cn",
            message="ok",
            login_command=[],
        )
        result = garmin_sync.GarminLoginResult(
            ok=True,
            region="cn",
            status="completed",
            command=[],
            stdout="",
            stderr="",
            message="ok",
        )
        with mock.patch.object(garmin_sync, "check_auth_status", return_value=status), \
             mock.patch.object(garmin_sync, "start_login", return_value=result), \
             mock.patch.object(llm_backend, "generate_text") as generate_text, \
             mock.patch.object(llm_backend, "chat_completions") as chat_completions:
            Api().check_garmin_auth_status("cn")
            Api().start_garmin_login("cn")

        generate_text.assert_not_called()
        chat_completions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
