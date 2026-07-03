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


class TestGarminAuthScript(unittest.TestCase):
    def test_login_saves_tokens_when_post_login_validation_times_out(self):
        class FakeGarth:
            oauth1_token = object()
            oauth2_token = object()

            def configure(self, **kwargs):
                self.timeout = kwargs.get("timeout")

            def dump(self, path):
                token_dir = Path(path)
                token_dir.mkdir(parents=True, exist_ok=True)
                (token_dir / "oauth1_token.json").write_text("{}", encoding="utf-8")
                (token_dir / "oauth2_token.json").write_text("{}", encoding="utf-8")

        class FakeGarmin:
            def __init__(self, email=None, password=None, is_cn=False):
                self.email = email
                self.password = password
                self.is_cn = is_cn
                self.garth = FakeGarth()

            def login(self):
                raise TimeoutError("user-settings read timed out")

        fake_module = types.SimpleNamespace(Garmin=FakeGarmin)
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(sys.modules, {"garminconnect": fake_module}), \
             mock.patch.object(garmin_auth, "patch_garth_ssl_consumer"):
            token_path = garmin_auth.login_and_save(
                "runner@example.com",
                "secret",
                "global",
                Path(tmpdir) / "garmin_auth_global",
            )

            self.assertTrue((token_path / "oauth1_token.json").is_file())
            self.assertTrue((token_path / "oauth2_token.json").is_file())

    def test_client_timeout_uses_garmin_http_timeout_env(self):
        class FakeGarth:
            def __init__(self):
                self.timeout = None

            def configure(self, **kwargs):
                self.timeout = kwargs.get("timeout")

        fake_client = types.SimpleNamespace(garth=FakeGarth())
        with mock.patch.dict("os.environ", {"GARMIN_HTTP_TIMEOUT": "45"}):
            garmin_auth.configure_client_timeout(fake_client)

        self.assertEqual(fake_client.garth.timeout, 45)


if __name__ == "__main__":
    unittest.main()
