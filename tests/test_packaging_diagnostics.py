import json
import subprocess
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
        pyinstaller_spec = (root / "HikingTrackAnalyzer.spec").read_text(encoding="utf-8")

        self.assertIn("garminconnect==0.3.6", requirements)
        self.assertIn("garmin-fit-sdk==21.205.0", requirements)
        self.assertIn("curl_cffi>=0.6", requirements)
        self.assertIn("garminconnect==0.3.6", constraints)
        self.assertIn("garmin-fit-sdk==21.205.0", constraints)
        self.assertIn("curl_cffi>=0.6", constraints)
        self.assertIn("requests==2.34.2", constraints)
        self.assertIn("urllib3==2.7.0", constraints)
        self.assertIn("certifi==2026.6.17", constraints)
        self.assertIn("-r requirements.txt -c constraints.txt", shell_script)
        self.assertIn("-r requirements.txt -c constraints.txt", ps_script)
        self.assertIn("${PYTHON:-}", shell_script)
        self.assertIn(".venv312/bin/python", shell_script)
        self.assertIn("sys.executable", shell_script)
        self.assertIn("garmin_fit_sdk", shell_script)
        self.assertIn("param(", ps_script)
        self.assertIn("$env:PYTHON", ps_script)
        self.assertIn(".venv312\\Scripts\\python.exe", ps_script)
        self.assertIn("sys.executable", ps_script)
        self.assertIn("garmin_fit_sdk", ps_script)
        self.assertNotIn("python3 -m pip install -r requirements.txt -c constraints.txt", shell_script)
        self.assertNotIn("python -m pip install -r requirements.txt -c constraints.txt", ps_script)
        self.assertIn('collect_submodules("garmin_fit_sdk")', pyinstaller_spec)

    def test_python_environment_check_records_non_blocking_runtime_context(self):
        info = diag.check_python_environment()

        self.assertIn("executable", info)
        self.assertIn("version", info)
        self.assertIn("version_info", info)
        self.assertIsInstance(info["warnings"], list)
        self.assertGreaterEqual(info["version_info"]["major"], 3)

    def test_python312_runtime_script_accepts_ok_report(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            script = root / "scripts" / "check_python312_runtime.py"
            script.write_text("# ok\n", encoding="utf-8")
            report = {
                "ok": True,
                "python_executable": "/tmp/python",
                "errors": [],
                "checked_modules": {"garmin_fit_sdk": {"status": "ok"}},
            }
            calls = []

            def fake_runner(command, **kwargs):
                calls.append((command, kwargs))
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(report), stderr="")

            result = diag.check_python312_runtime_script(root, runner=fake_runner)

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0][0][0], diag.sys.executable)
        self.assertIn("check_python312_runtime.py", calls[0][0][1])
        self.assertEqual(calls[0][1]["cwd"], str(root))
        self.assertFalse(calls[0][1]["check"])

    def test_python312_runtime_script_blocks_failed_report(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "check_python312_runtime.py").write_text("# ok\n", encoding="utf-8")
            report = {
                "ok": False,
                "errors": [
                    "Missing required distribution: garmin-fit-sdk",
                    "Cannot import garmin_fit_sdk: ModuleNotFoundError",
                ],
            }

            def fake_runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 1, stdout=json.dumps(report), stderr="")

            with self.assertRaisesRegex(diag.PackagingCheckError, "garmin-fit-sdk"):
                diag.check_python312_runtime_script(root, runner=fake_runner)

    def test_python312_runtime_script_blocks_invalid_json(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "check_python312_runtime.py").write_text("# ok\n", encoding="utf-8")

            def fake_runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 1, stdout="not-json", stderr="boom")

            with self.assertRaisesRegex(diag.PackagingCheckError, "invalid JSON"):
                diag.check_python312_runtime_script(root, runner=fake_runner)

    def test_python312_runtime_script_blocks_missing_script(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(diag.PackagingCheckError, "check_python312_runtime.py"):
                diag.check_python312_runtime_script(Path(temp), runner=lambda *args, **kwargs: None)

    def test_garmin_dependency_check_accepts_036_api(self):
        class Garmin:
            def __init__(self, email=None, password=None, is_cn=False, prompt_mfa=None, return_on_mfa=False):
                pass

        module = types.SimpleNamespace(Garmin=Garmin)

        def fake_import(name):
            if name == "garminconnect":
                return module
            if name == "garmin_fit_sdk":
                return types.SimpleNamespace()
            raise ModuleNotFoundError(name)

        result = diag.check_garmin_dependencies(
            version_lookup=self._version_lookup(
                {"garminconnect": "0.3.6", "curl_cffi": "0.6.1", "garmin-fit-sdk": "21.205.0"}
            ),
            import_module=fake_import,
        )

        self.assertEqual(result["garminconnect"], "0.3.6")
        self.assertEqual(result["curl_cffi"], "0.6.1")
        self.assertEqual(result["garmin-fit-sdk"], "21.205.0")

    def test_garmin_dependency_check_fails_old_version(self):
        with self.assertRaisesRegex(diag.PackagingCheckError, "仅兼容 garminconnect 0.3.6"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup(
                    {"garminconnect": "0.2.8", "curl_cffi": "0.6.1", "garmin-fit-sdk": "21.205.0"}
                ),
                import_module=lambda name: types.SimpleNamespace(Garmin=object),
            )

    def test_garmin_dependency_check_fails_missing_curl_cffi(self):
        with self.assertRaisesRegex(diag.PackagingCheckError, "curl_cffi"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup({"garminconnect": "0.3.6"}),
                import_module=lambda name: types.SimpleNamespace(Garmin=object),
            )

    def test_garmin_dependency_check_fails_missing_fit_sdk_distribution(self):
        with self.assertRaisesRegex(diag.PackagingCheckError, "garmin-fit-sdk"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup({"garminconnect": "0.3.6", "curl_cffi": "0.6.1"}),
                import_module=lambda name: types.SimpleNamespace(Garmin=object),
            )

    def test_garmin_dependency_check_fails_missing_fit_sdk_import(self):
        class Garmin:
            def __init__(self, email=None, password=None, is_cn=False, prompt_mfa=None, return_on_mfa=False):
                pass

        def fake_import(name):
            if name == "garminconnect":
                return types.SimpleNamespace(Garmin=Garmin)
            if name == "garmin_fit_sdk":
                raise ModuleNotFoundError("No module named 'garmin_fit_sdk'")
            raise ModuleNotFoundError(name)

        with self.assertRaisesRegex(diag.PackagingCheckError, "Cannot import garmin_fit_sdk"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup(
                    {"garminconnect": "0.3.6", "curl_cffi": "0.6.1", "garmin-fit-sdk": "21.205.0"}
                ),
                import_module=fake_import,
            )

    def test_garmin_dependency_check_fails_missing_mfa_api(self):
        class OldGarmin:
            def __init__(self, email=None, password=None, is_cn=False):
                pass

        with self.assertRaisesRegex(diag.PackagingCheckError, "prompt_mfa"):
            diag.check_garmin_dependencies(
                version_lookup=self._version_lookup(
                    {"garminconnect": "0.3.6", "curl_cffi": "0.6.1", "garmin-fit-sdk": "21.205.0"}
                ),
                import_module=lambda name: types.SimpleNamespace(Garmin=OldGarmin),
            )

    def _make_zip(self, path: Path, members: dict[str, str]):
        with zipfile.ZipFile(path, "w") as archive:
            for name, body in members.items():
                archive.writestr(name, body)

    def test_packaging_prerequisites_runs_python312_runtime_gate(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills" / "garmin-stats" / "scripts").mkdir(parents=True)
            (root / "skills" / "coros-stats" / "scripts").mkdir(parents=True)
            (root / "skills" / "garmin-stats" / "scripts" / "garmin_auth.py").write_text("# ok\n", encoding="utf-8")
            (root / "skills" / "coros-stats" / "scripts" / "coros-mcp-keepalive.js").write_text("// ok\n", encoding="utf-8")
            self._make_zip(
                root / "skills" / "garmin-stats.zip",
                {"garmin-stats/scripts/garmin_auth.py": "# ok\n"},
            )
            self._make_zip(
                root / "skills" / "coros-stats.zip",
                {"coros-stats/scripts/coros-mcp-keepalive.js": "// ok\n"},
            )

            with mock.patch.object(
                diag,
                "check_python312_runtime_script",
                return_value={"ok": True, "python_executable": "/tmp/python"},
            ) as runtime_check, mock.patch.object(
                diag,
                "check_garmin_dependencies",
                return_value={"garminconnect": "0.3.6", "curl_cffi": "0.6.1", "garmin-fit-sdk": "21.205.0"},
            ):
                result = diag.check_packaging_prerequisites(root)

        runtime_check.assert_called_once_with(root)
        self.assertEqual(result["python_runtime"]["python_executable"], "/tmp/python")
        self.assertEqual(result["packages"]["garmin-fit-sdk"], "21.205.0")

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
                    "garmin-fit-sdk": "21.205.0",
                    "curl_cffi": "0.6.1",
                    "requests": "2.32.0",
                    "urllib3": "2.2.0",
                    "certifi": "2026.1.1",
                    "garth": None,
                }.get(name)

            with mock.patch.object(diag, "package_version", side_effect=fake_version):
                manifest = diag.build_dependency_manifest(root)

        serialized = json.dumps(manifest, ensure_ascii=False)
        self.assertEqual(manifest["python_executable"], diag.sys.executable)
        self.assertEqual(manifest["python_version"], diag.sys.version.split()[0])
        self.assertEqual(manifest["python_version_info"]["major"], diag.sys.version_info.major)
        self.assertEqual(manifest["python_version_info"]["minor"], diag.sys.version_info.minor)
        self.assertIsInstance(manifest["python_warnings"], list)
        self.assertEqual(manifest["packages"]["garminconnect"], "0.3.6")
        self.assertEqual(manifest["packages"]["garmin-fit-sdk"], "21.205.0")
        self.assertEqual(manifest["compatibility"]["garmin_fit_sdk_expected"], "21.205.0")
        self.assertEqual(manifest["compatibility"]["garmin_api"], "0.3.x-tokenstore-client")
        self.assertTrue(manifest["compatibility"]["codex_cli_windows_shim_supported"])
        self.assertTrue(manifest["skills"]["garmin-stats"]["script_present"])
        self.assertNotIn("password=", serialized.lower())
        self.assertNotIn("authorization=", serialized.lower())


if __name__ == "__main__":
    unittest.main()
