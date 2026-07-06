import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "garmin-stats" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import garmin_auth


class FakeApiClient:
    def __init__(self):
        self.loaded = ""
        self.dumped = ""

    def dump(self, path):
        token_dir = Path(path)
        token_dir.mkdir(parents=True, exist_ok=True)
        (token_dir / "garmin_tokens.json").write_text('{"di_token":"ok","di_refresh_token":"ok","di_client_id":"ok"}', encoding="utf-8")
        self.dumped = str(path)

    def load(self, path):
        self.loaded = str(path)

    def connectapi(self, path, **kwargs):
        if path == "/userprofile-service/socialProfile":
            return {"displayName": "runner", "fullName": "Runner Example"}
        return {"ok": True}


class FakeGarmin:
    instances = []
    resumed = []

    def __init__(self, email=None, password=None, is_cn=False, prompt_mfa=None, return_on_mfa=False):
        self.email = email
        self.password = password
        self.is_cn = is_cn
        self.prompt_mfa = prompt_mfa
        self.return_on_mfa = return_on_mfa
        self.client = FakeApiClient()
        self.display_name = "runner"
        self.full_name = "Runner Example"
        FakeGarmin.instances.append(self)

    def login(self, tokenstore=None):
        if tokenstore and not self.email:
            self.client.load(tokenstore)
            return None, None
        if self.return_on_mfa and not getattr(self, "force_no_mfa", False):
            return "needs_mfa", {"mfa": "state"}
        if self.prompt_mfa:
            self.prompt_mfa()
        self.client.dump(tokenstore)
        return None, None

    def resume_login(self, client_state, mfa_code):
        FakeGarmin.resumed.append((client_state, mfa_code))
        return None, None

    def connectapi(self, path, **kwargs):
        return self.client.connectapi(path, **kwargs)


class TestGarminAuthScript(unittest.TestCase):
    def setUp(self):
        FakeGarmin.instances = []
        FakeGarmin.resumed = []

    def _fake_module(self, cls=FakeGarmin):
        return types.SimpleNamespace(Garmin=cls)

    def test_login_app_saves_036_tokenstore_when_mfa_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(sys.modules, {"garminconnect": self._fake_module()}), \
             mock.patch.object(garmin_auth, "_garminconnect_version", return_value="0.3.6"):
            token_path = garmin_auth.login_and_save_app(
                "runner@example.com",
                "secret",
                "global",
                Path(tmpdir) / "garmin_auth_global",
                mfa_code="123456",
            )
            token_exists = (token_path / "garmin_tokens.json").is_file()

        self.assertTrue(token_exists)
        self.assertFalse(FakeGarmin.instances[-1].is_cn)

    def test_login_app_without_mfa_returns_mfa_required(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(sys.modules, {"garminconnect": self._fake_module()}), \
             mock.patch.object(garmin_auth, "_garminconnect_version", return_value="0.3.6"):
            with self.assertRaises(garmin_auth.GarminStatsMFARequired) as ctx:
                garmin_auth.login_and_save_app(
                    "runner@example.com",
                    "secret",
                    "cn",
                    Path(tmpdir) / "garmin_auth_cn",
                )

        self.assertEqual(ctx.exception.client_state, {"mfa": "state"})

    def test_login_app_resumes_036_mfa_state_and_saves_tokenstore(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(sys.modules, {"garminconnect": self._fake_module()}), \
             mock.patch.object(garmin_auth, "_garminconnect_version", return_value="0.3.6"):
            token_path = garmin_auth.login_and_save_app(
                "runner@example.com",
                "secret",
                "cn",
                Path(tmpdir) / "garmin_auth_cn",
                mfa_code="123456",
                mfa_state={"mfa": "state"},
            )
            token_exists = (token_path / "garmin_tokens.json").is_file()

        self.assertEqual(FakeGarmin.resumed, [({"mfa": "state"}, "123456")])
        self.assertTrue(token_exists)

    def test_build_client_loads_036_tokenstore(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(sys.modules, {"garminconnect": self._fake_module()}), \
             mock.patch.object(garmin_auth, "_garminconnect_version", return_value="0.3.6"):
            token_dir = Path(tmpdir) / "garmin_auth_cn"
            token_dir.mkdir()
            (token_dir / "garmin_tokens.json").write_text("{}", encoding="utf-8")
            client, token_path = garmin_auth.build_client("cn", token_dir)

        self.assertEqual(token_path, token_dir)
        self.assertTrue(client.is_cn)
        self.assertEqual(client.client.loaded, str(token_dir))

    def test_provider_version_mismatch_is_explicit(self):
        with mock.patch.dict(sys.modules, {"garminconnect": self._fake_module()}), \
             mock.patch.object(garmin_auth, "_garminconnect_version", return_value="0.3.2"):
            with self.assertRaises(garmin_auth.GarminStatsProviderIncompatible) as ctx:
                garmin_auth.login_and_save_app("runner@example.com", "secret", "cn")

        self.assertIn("0.3.2", str(ctx.exception))
        self.assertIn("0.3.6", str(ctx.exception))

    def test_script_has_no_direct_legacy_session_api(self):
        source = (SCRIPTS_DIR / "garmin_auth.py").read_text(encoding="utf-8")

        self.assertNotIn("import garth", source)
        self.assertNotIn(".garth", source)
        self.assertNotIn("garth.sso", source)


if __name__ == "__main__":
    unittest.main()
