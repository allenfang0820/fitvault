import json
import types
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import packaging_diagnostics as diag


class TestPackagingDiagnostics(unittest.TestCase):
    def _version_lookup(self, versions):
        return lambda name: versions.get(name)

    def test_requirements_and_constraints_lock_garmin_contract(self):
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        constraints = (root / "constraints.txt").read_text(encoding="utf-8")
        shell_script = (root / "scripts" / "install_packaging_deps.sh").read_text(encoding="utf-8")
        ps_script = (root / "scripts" / "install_packaging_deps.ps1").read_text(encoding="utf-8")

        self.assertIn("garminconnect==0.3.6", requirements)
        self.assertIn("curl_cffi>=0.6", requirements)
        self.assertIn("garminconnect==0.3.6", constraints)
        self.assertIn("curl_cffi>=0.6", constraints)
        self.assertIn("requests==2.34.2", constraints)
        self.assertIn("urllib3==2.7.0", constraints)
        self.assertIn("certifi==2026.6.17", constraints)
        self.assertIn("-r requirements.txt -c constraints.txt", shell_script)
        self.assertIn("-r requirements.txt -c constraints.txt", ps_script)

    def test_garmin_dependency_check_accepts_036_api(self):
        class Garmin:
            def __init__(self, email=None, password=None, is_cn=False, prompt_mfa=None, return_on_mfa=False):
                pass

        module = types.SimpleNamespace(Garmin=Garmin)

        result = diag.check_garmin_dependencies(
            version_lookup=self._version_lookup({"garminconnect": "0.3.6", "curl_cffi": "0.6.1"}),
            import_module=lambda name: module,
        )

        self.assertEqual(result["garminconnect"], "0.3.6")
        self.assertEqual(result["curl_cffi"], "0.6.1")

    def test_garmin_dependency_check_fails_old_version(self):
        with self.assertRaisesRegex(diag.PackagingCheckError, "仅兼容 garminconnect 0.3.6"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup({"garminconnect": "0.2.8", "curl_cffi": "0.6.1"}),
                import_module=lambda name: types.SimpleNamespace(Garmin=object),
            )

    def test_garmin_dependency_check_fails_missing_curl_cffi(self):
        with self.assertRaisesRegex(diag.PackagingCheckError, "curl_cffi"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup({"garminconnect": "0.3.6"}),
                import_module=lambda name: types.SimpleNamespace(Garmin=object),
            )

    def test_garmin_dependency_check_fails_missing_mfa_api(self):
        class OldGarmin:
            def __init__(self, email=None, password=None, is_cn=False):
                pass

        with self.assertRaisesRegex(diag.PackagingCheckError, "prompt_mfa"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup({"garminconnect": "0.3.6", "curl_cffi": "0.6.1"}),
                import_module=lambda name: types.SimpleNamespace(Garmin=OldGarmin),
            )

    def _make_zip(self, path: Path, members: dict[str, str]):
        with zipfile.ZipFile(path, "w") as archive:
            for name, body in members.items():
                archive.writestr(name, body)

    def test_skill_zip_check_accepts_correct_root(self):
        with TemporaryDirectory() as temp:
            zip_path = Path(temp) / "coros-stats.zip"
            self._make_zip(
                zip_path,
                {"coros-stats/scripts/coros-mcp-keepalive.js": "console.log('ok')"},
            )

            result = diag.check_skill_zip(
                zip_path,
                root_name="coros-stats",
                required_members=["coros-stats/scripts/coros-mcp-keepalive.js"],
            )

        self.assertTrue(result["zip_present"])

    def test_skill_zip_check_rejects_nested_root(self):
        with TemporaryDirectory() as temp:
            zip_path = Path(temp) / "coros-stats.zip"
            self._make_zip(
                zip_path,
                {"skills/coros-stats/scripts/coros-mcp-keepalive.js": "bad"},
            )

            with self.assertRaisesRegex(diag.PackagingCheckError, "nested"):
                diag.check_skill_zip(
                    zip_path,
                    root_name="coros-stats",
                    required_members=["coros-stats/scripts/coros-mcp-keepalive.js"],
                )

    def test_skill_zip_check_rejects_cache_and_missing_script(self):
        with TemporaryDirectory() as temp:
            zip_path = Path(temp) / "garmin-stats.zip"
            self._make_zip(zip_path, {"garmin-stats/__pycache__/garmin_auth.cpython-312.pyc": "bad"})

            with self.assertRaisesRegex(diag.PackagingCheckError, "cache"):
                diag.check_skill_zip(
                    zip_path,
                    root_name="garmin-stats",
                    required_members=["garmin-stats/scripts/garmin_auth.py"],
                )

            clean_zip = Path(temp) / "garmin-stats-clean.zip"
            self._make_zip(clean_zip, {"garmin-stats/scripts/login.py": "missing auth"})
            with self.assertRaisesRegex(diag.PackagingCheckError, "garmin_auth.py"):
                diag.check_skill_zip(
                    clean_zip,
                    root_name="garmin-stats",
                    required_members=["garmin-stats/scripts/garmin_auth.py"],
                )

    def test_windows_runtime_check_requires_node_and_npm(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(diag.PackagingCheckError, "node.exe"):
                diag.check_windows_runtime(root, system="windows")

            runtime = root / "runtimes" / "node-win-x64"
            runtime.mkdir(parents=True)
            (runtime / "node.exe").write_text("", encoding="utf-8")
            (runtime / "npm.cmd").write_text("", encoding="utf-8")

            result = diag.check_windows_runtime(root, system="windows")

        self.assertTrue(result["required"])
        self.assertTrue(result["node"])
        self.assertTrue(result["npm"])

    def test_manifest_contains_contract_fields_and_redacts_sensitive_values(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills" / "garmin-stats" / "scripts").mkdir(parents=True)
            (root / "skills" / "coros-stats" / "scripts").mkdir(parents=True)
            (root / "skills" / "garmin-stats" / "scripts" / "garmin_auth.py").write_text("# ok\n", encoding="utf-8")
            (root / "skills" / "coros-stats" / "scripts" / "coros-mcp-keepalive.js").write_text("// ok\n", encoding="utf-8")

            def fake_version(name):
                return {
                    "garminconnect": "0.3.6",
                    "curl_cffi": "0.6.1",
                    "requests": "2.32.0",
                    "urllib3": "2.2.0",
                    "certifi": "2026.1.1",
                    "garth": None,
                }.get(name)

            with mock.patch.object(diag, "package_version", side_effect=fake_version):
                manifest = diag.build_dependency_manifest(root)

        serialized = json.dumps(manifest, ensure_ascii=False)
        self.assertEqual(manifest["packages"]["garminconnect"], "0.3.6")
        self.assertEqual(manifest["compatibility"]["garmin_api"], "0.3.x-tokenstore-client")
        self.assertTrue(manifest["compatibility"]["codex_cli_windows_shim_supported"])
        self.assertTrue(manifest["skills"]["garmin-stats"]["script_present"])
        self.assertNotIn("password=", serialized.lower())
        self.assertNotIn("authorization=", serialized.lower())


if __name__ == "__main__":
    unittest.main()
