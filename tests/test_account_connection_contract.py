import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "js_api_contract.json"


class TestAccountConnectionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.methods = {item["name"]: item for item in cls.contract["methods"]}

    def test_unified_account_connection_methods_are_registered(self):
        for name in (
            "list_account_connections",
            "check_account_connection",
            "start_account_connection",
            "continue_account_connection",
            "disconnect_account",
        ):
            self.assertIn(name, self.methods)
            self.assertEqual(self.methods[name]["category"], "account_connection")

    def test_status_enum_and_regions_are_documented(self):
        contract_text = json.dumps(self.contract, ensure_ascii=False)
        for status in (
            "idle",
            "checking",
            "needs_credentials",
            "needs_mfa",
            "opening_browser",
            "waiting_callback",
            "authorized",
            "failed",
            "expired",
        ):
            self.assertIn(status, contract_text)
        for region_text in ("Garmin: cn/global", "COROS: cn/us/eu"):
            self.assertIn(region_text, contract_text)

    def test_garmin_and_coros_flow_boundaries_are_documented(self):
        start_contract = self.methods["start_account_connection"]
        continue_contract = self.methods["continue_account_connection"]

        self.assertIn("缺少账号或密码返回 needs_credentials", start_contract["description"])
        self.assertIn("needs_mfa + session_id", start_contract["description"])
        self.assertIn("官方 MCP/OAuth", start_contract["description"])
        self.assertIn("打开系统浏览器", start_contract["description"])
        self.assertIn("mfa_code", continue_contract["description"])
        self.assertIn("MCP token 文件状态", continue_contract["description"])

    def test_sensitive_fields_are_not_returned_by_unified_contract(self):
        for name in (
            "list_account_connections",
            "check_account_connection",
            "start_account_connection",
            "continue_account_connection",
        ):
            returns = self.methods[name]["returns"].lower()
            self.assertNotIn("password", returns)
            self.assertNotIn("mfa_code", returns)
            self.assertNotIn("access_token", returns)
            self.assertNotIn("refresh_token", returns)
        start_text = json.dumps(self.methods["start_account_connection"], ensure_ascii=False)
        continue_text = json.dumps(self.methods["continue_account_connection"], ensure_ascii=False)
        self.assertIn("禁止 API 返回值回显 password", start_text)
        self.assertIn("禁止返回值回显 MFA 验证码", continue_text)

    def test_disconnect_scope_and_legacy_login_boundary_are_documented(self):
        disconnect_contract = self.methods["disconnect_account"]
        self.assertIn("仅移除本地授权材料", disconnect_contract["description"])
        self.assertIn("不删除活动记录、FIT 文件、用户画像或同步配置", disconnect_contract["description"])

        for name in ("start_garmin_login", "start_coros_login"):
            legacy = self.methods[name]
            self.assertIn("legacy 兼容 API", legacy["description"])
            self.assertIn("账号连接中心不再使用此接口作为设置页主授权入口", legacy["description"])
            self.assertIn("start_account_connection/continue_account_connection", legacy["description"])


if __name__ == "__main__":
    unittest.main()
