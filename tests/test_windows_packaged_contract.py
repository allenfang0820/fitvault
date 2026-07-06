import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import coros_sync
import garmin_sync
import llm_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "HikingTrackAnalyzer.spec"


class TestWindowsPackagedContract(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir_obj.name)

    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def _write_coros_skill(self, root: Path) -> Path:
        scripts = root / "skills" / "coros-stats" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        for name in (
            "coros-mcp-keepalive.js",
            "coros_runner_profile.py",
            "install_coros_mcp.cmd",
            "install_coros_mcp.sh",
        ):
            (scripts / name).write_text("# packaged test\n", encoding="utf-8")
        return scripts

    def _write_garmin_skill(self, root: Path) -> Path:
        scripts = root / "skills" / "garmin-stats" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        for name in ("get_garmin_stats.py", "download_fit.py", "login.py"):
            (scripts / name).write_text("# packaged test\n", encoding="utf-8")
        return scripts

    def _completed(self, stdout="ok", stderr="", returncode=0):
        return subprocess.CompletedProcess(args=["tool"], returncode=returncode, stdout=stdout, stderr=stderr)

    def test_a_spec_includes_account_skill_and_node_runtime_contract(self):
        spec = SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn("skills/garmin-stats", spec)
        self.assertIn("skills/coros-stats", spec)
        self.assertIn("skills/garmin-stats.zip", spec)
        self.assertIn("skills/coros-stats.zip", spec)
        self.assertIn("MAITU_NODE_RUNTIME_DIR", spec)
        self.assertIn("runtimes", spec)
        self.assertIn("node-win-x64", spec)
        self.assertIn('return [(runtime_dir, "node")]', spec)
        self.assertIn("FITVAULT_INCLUDE_LEGACY_CONSOLE_HELPER", spec)
        self.assertIn("_include_legacy_console_helper", spec)
        self.assertIn('name="FitVaultCLI"', spec.replace("'", '"'))
        self.assertIn('if platform.system().lower() == "windows" and _include_legacy_console_helper', spec)

    def test_b_windows_frozen_meipass_and_internal_skill_paths(self):
        meipass = self.base_dir / "Program Files" / "FitVault" / "_MEI12345"
        self._write_coros_skill(meipass)
        self._write_garmin_skill(meipass)
        exe = self.base_dir / "Program Files" / "FitVault" / "FitVault.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            coros_paths = coros_sync.get_coros_skill_paths()
            garmin_paths = garmin_sync.get_garmin_skill_paths()

        self.assertEqual(coros_paths.profile_runner, meipass / "skills" / "coros-stats" / "scripts" / "coros_runner_profile.py")
        self.assertEqual(coros_paths.install_mcp_cmd, meipass / "skills" / "coros-stats" / "scripts" / "install_coros_mcp.cmd")
        self.assertEqual(garmin_paths.get_stats, meipass / "skills" / "garmin-stats" / "scripts" / "get_garmin_stats.py")

        internal = self.base_dir / "Program Files" / "FitVault" / "_internal"
        self._write_coros_skill(internal)
        self._write_garmin_skill(internal)
        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(internal), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(internal), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            self.assertEqual(coros_sync.app_base_dir(), internal)
            self.assertEqual(garmin_sync.app_base_dir(), internal)

    def test_c_windows_bundled_node_candidates_cover_packaged_layouts_with_spaces(self):
        app_root = self.base_dir / "Program Files" / "FitVault"
        exe = app_root / "FitVault.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        meipass = app_root / "_MEI12345"
        self._write_coros_skill(meipass)

        node_locations = [
            meipass / "node" / "node.exe",
            app_root / "_internal" / "node" / "node.exe",
            app_root / "Resources" / "node" / "node.exe",
        ]
        for expected_node in node_locations:
            for existing in app_root.rglob("node.exe"):
                existing.unlink()
            expected_node.parent.mkdir(parents=True, exist_ok=True)
            expected_node.write_text("", encoding="utf-8")
            expected_node.chmod(0o755)
            with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
                 mock.patch.object(coros_sync.sys, "_MEIPASS", str(meipass), create=True), \
                 mock.patch.object(coros_sync.sys, "executable", str(exe)), \
                 mock.patch.object(coros_sync.os, "access", return_value=True), \
                 mock.patch.object(coros_sync.shutil, "which", return_value=None), \
                 mock.patch.dict(coros_sync.os.environ, {}, clear=True):
                found = coros_sync.discover_node_binary()
                self.assertEqual(Path(found).resolve(), expected_node.resolve())
                self.assertIn("Program Files", found)

    def test_d_packaged_coros_profile_sync_does_not_launch_fitvault_exe(self):
        app_root = self.base_dir / "Program Files" / "FitVault"
        scripts = self._write_coros_skill(app_root)
        (scripts / "coros_runner_profile.py").write_text(
            "def build_profile():\n    return [{'metric': 'username', 'value': 'runner'}]\n",
            encoding="utf-8",
        )
        exe = app_root / "FitVault.exe"
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "platform", "win32"), \
             mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)), \
             mock.patch.object(coros_sync, "ensure_auth_available"), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=AssertionError("must not spawn FitVault.exe")):
            profile = coros_sync.sync_profile_json(base_dir=app_root, region="cn")

        self.assertEqual(profile[0]["metric"], "username")

    def test_e_packaged_coros_and_codex_commands_keep_argv_split(self):
        app_root = self.base_dir / "Program Files" / "FitVault"
        scripts = self._write_coros_skill(app_root)
        keepalive = scripts / "coros-mcp-keepalive.js"
        node = app_root / "node" / "node.exe"
        node.parent.mkdir(parents=True)
        node.write_text("", encoding="utf-8")
        node.chmod(0o755)

        with mock.patch.object(coros_sync, "app_base_dir", return_value=app_root), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value=str(node)), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout='{"ok":true}')) as run_mock:
            coros_sync.run_coros_mcp_tool("queryUserInfo", {}, region="cn")

        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], str(node))
        self.assertEqual(command[1], str(keepalive))
        self.assertFalse(run_mock.call_args.kwargs["shell"])
        self.assertIn("Program Files", command[0])

        codex = self.base_dir / "Users" / "Runner" / "AppData" / "Roaming" / "npm" / "codex.cmd"
        codex.parent.mkdir(parents=True)
        codex.write_text("", encoding="utf-8")
        with mock.patch.object(llm_backend.sys, "platform", "win32"), \
             mock.patch.object(llm_backend.sys, "frozen", True, create=True), \
             mock.patch.object(llm_backend.sys, "executable", str(app_root / "FitVault.exe")), \
             mock.patch.object(llm_backend.shutil, "which", return_value=str(codex)), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=self._completed()) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex", "cli_path": ""},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid",
            )

        command = run_mock.call_args.args[0]
        self.assertEqual(command[:3], [str(codex), "exec", "--skip-git-repo-check"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])
        self.assertNotIn("openclaw", " ".join(command).lower())
        self.assertIsNone(run_mock.call_args.kwargs.get("env"))

    def test_f_macos_packaged_resources_and_runtime_fallbacks_are_unchanged(self):
        bundle = self.base_dir / "脉图.app" / "Contents"
        resources = bundle / "Resources"
        frameworks = bundle / "Frameworks"
        self._write_coros_skill(resources)
        self._write_garmin_skill(resources)
        exe = bundle / "MacOS" / "FitVault"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "platform", "darwin"), \
             mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(frameworks), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)), \
             mock.patch.object(garmin_sync.sys, "platform", "darwin"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(frameworks), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            self.assertEqual(coros_sync.app_base_dir(), resources)
            self.assertEqual(garmin_sync.app_base_dir(), resources)

        nvm_node = self.base_dir / ".nvm" / "versions" / "node" / "v22.0.0" / "bin" / "node"
        nvm_node.parent.mkdir(parents=True)
        nvm_node.write_text("#!/bin/sh\n", encoding="utf-8")
        nvm_node.chmod(0o755)
        with mock.patch.object(coros_sync.sys, "platform", "darwin"), \
             mock.patch.object(coros_sync, "app_base_dir", return_value=resources), \
             mock.patch.object(coros_sync.shutil, "which", return_value=None), \
             mock.patch.dict(coros_sync.os.environ, {"APPDATA": "C:/Users/Runner/AppData/Roaming"}, clear=False):
            self.assertEqual(coros_sync.discover_node_binary(home=self.base_dir), str(nvm_node))
            self.assertEqual(coros_sync.default_mcp_token_root(), Path.home() / ".coros-mcp-skill-gateway-ts")

        with mock.patch.object(llm_backend.sys, "platform", "darwin"), \
             mock.patch.object(llm_backend.shutil, "which") as which_mock, \
             mock.patch.dict(llm_backend.os.environ, {"APPDATA": "C:/Users/Runner/AppData/Roaming"}, clear=False), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=self._completed()) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex", "cli_path": ""},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid",
            )

        self.assertEqual(run_mock.call_args.args[0][0], "codex")
        which_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
