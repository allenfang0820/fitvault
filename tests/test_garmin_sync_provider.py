import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import garmin_sync


class TestGarminSyncProvider(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir_obj.name)
        self.scripts_dir = self.base_dir / "skills" / "garmin-stats" / "scripts"
        self.scripts_dir.mkdir(parents=True)
        for name in ("get_garmin_stats.py", "download_fit.py", "login.py"):
            path = self.scripts_dir / name
            path.write_text("# test script\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def _completed(self, stdout="", stderr="", returncode=0):
        return subprocess.CompletedProcess(
            args=[sys.executable, "script.py"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_default_region_is_cn(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(garmin_sync.resolve_garmin_region(), "cn")

    def test_environment_region_is_used(self):
        with mock.patch.dict(os.environ, {"GARMIN_REGION": "global"}):
            self.assertEqual(garmin_sync.resolve_garmin_region(), "global")

    def test_invalid_region_raises_readable_error(self):
        with self.assertRaises(garmin_sync.GarminSyncError) as ctx:
            garmin_sync.resolve_garmin_region("eu")

        self.assertEqual(ctx.exception.code, "invalid_garmin_region")
        self.assertIn("仅支持", str(ctx.exception))

    def test_skill_paths_are_resolved_from_base_dir(self):
        paths = garmin_sync.get_garmin_skill_paths(self.base_dir)

        self.assertEqual(paths.skill_dir, self.base_dir.resolve() / "skills" / "garmin-stats")
        self.assertEqual(paths.get_stats.name, "get_garmin_stats.py")
        self.assertEqual(paths.download_fit.name, "download_fit.py")
        self.assertEqual(paths.login.name, "login.py")

    def test_app_base_dir_prefers_bundle_resources_for_packaged_skills(self):
        bundle = self.base_dir / "脉图.app" / "Contents"
        frameworks = bundle / "Frameworks"
        resources = bundle / "Resources"
        scripts = resources / "skills" / "garmin-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "get_garmin_stats.py").write_text("# packaged\n", encoding="utf-8")
        exe = bundle / "MacOS" / "FitVault"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(frameworks), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            self.assertEqual(garmin_sync.app_base_dir(), resources)

    def test_app_base_dir_supports_windows_onefile_meipass_skills(self):
        meipass = self.base_dir / "_MEI12345"
        scripts = meipass / "skills" / "garmin-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "get_garmin_stats.py").write_text("# packaged\n", encoding="utf-8")
        exe = self.base_dir / "FitVault.exe"
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            self.assertEqual(garmin_sync.app_base_dir(), meipass)

    def test_app_base_dir_supports_windows_onedir_internal_skills(self):
        exe_dir = self.base_dir / "dist" / "FitVault"
        internal = exe_dir / "_internal"
        scripts = internal / "skills" / "garmin-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "get_garmin_stats.py").write_text("# packaged\n", encoding="utf-8")
        exe = exe_dir / "FitVault.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        meipass = internal

        with mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(exe)):
            self.assertEqual(garmin_sync.app_base_dir(), internal)

    def test_missing_skill_script_raises(self):
        (self.scripts_dir / "download_fit.py").unlink()

        with self.assertRaises(garmin_sync.GarminSkillNotFoundError) as ctx:
            garmin_sync.get_garmin_skill_paths(self.base_dir)

        self.assertEqual(ctx.exception.code, "garmin_skill_not_found")
        self.assertIn("download_fit.py", str(ctx.exception))

    def test_run_script_uses_current_python_and_shell_false(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        with mock.patch.object(
            garmin_sync.subprocess,
            "run",
            return_value=self._completed(stdout="[]"),
        ) as run_mock:
            result = garmin_sync.run_garmin_script(script, ["sync"], timeout=12)

        self.assertEqual(result.stdout, "[]")
        command = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(command[:3], [sys.executable, str(script.resolve()), "sync"])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["cwd"], str(script.resolve().parent))

    def test_sync_profile_json_parses_array(self):
        payload = [{"metric": "username", "value": "runner"}]
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text(
            "def build_profile(args):\n"
            f"    assert args.region == 'cn'\n"
            f"    return {payload!r}\n",
            encoding="utf-8",
        )
        with mock.patch.object(garmin_sync.subprocess, "run", side_effect=AssertionError("profile sync must not spawn script")):
            parsed = garmin_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertEqual(parsed, payload)

    def test_sync_profile_json_adds_refresh_flag(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text(
            "def build_profile(args):\n"
            "    assert args.region == 'global'\n"
            "    assert args.refresh is True\n"
            "    return []\n",
            encoding="utf-8",
        )

        garmin_sync.sync_profile_json(base_dir=self.base_dir, region="global", refresh=True)

    def test_sync_profile_json_rejects_non_json(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text("def build_profile(args):\n    return 'not json'\n", encoding="utf-8")
        with self.assertRaises(garmin_sync.GarminJsonParseError) as ctx:
            garmin_sync.sync_profile_json(base_dir=self.base_dir)

        self.assertEqual(ctx.exception.code, "garmin_json_parse_error")
        self.assertIn("不是 JSON 数组", str(ctx.exception))

    def test_sync_profile_json_rejects_non_array(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text("def build_profile(args):\n    return {'ok': True}\n", encoding="utf-8")
        with self.assertRaisesRegex(garmin_sync.GarminJsonParseError, "不是 JSON 数组"):
            garmin_sync.sync_profile_json(base_dir=self.base_dir)

    def test_sync_profile_json_rejects_non_object_array_items(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text("def build_profile(args):\n    return ['bad']\n", encoding="utf-8")
        with self.assertRaisesRegex(garmin_sync.GarminJsonParseError, "数组元素必须是对象"):
            garmin_sync.sync_profile_json(base_dir=self.base_dir)

    def test_sync_profile_json_frozen_macos_does_not_launch_app_executable(self):
        payload = [{"metric": "username", "value": "runner"}]
        script = self.scripts_dir / "get_garmin_stats.py"
        script.write_text(f"def build_profile(args):\n    return {payload!r}\n", encoding="utf-8")
        app_exe = self.base_dir / "脉图.app" / "Contents" / "MacOS" / "FitVault"
        app_exe.parent.mkdir(parents=True)
        app_exe.write_text("", encoding="utf-8")

        with mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(app_exe)), \
             mock.patch.object(garmin_sync.subprocess, "run", side_effect=AssertionError("profile sync must not launch sys.executable")):
            parsed = garmin_sync.sync_profile_json(base_dir=self.base_dir)

        self.assertEqual(parsed, payload)

    def test_subprocess_nonzero_exit_raises_with_stderr_snippet(self):
        script = self.scripts_dir / "get_garmin_stats.py"
        with mock.patch.object(
            garmin_sync.subprocess,
            "run",
            return_value=self._completed(stderr="auth failed", returncode=2),
        ):
            with self.assertRaises(garmin_sync.GarminScriptFailed) as ctx:
                garmin_sync.run_garmin_script(script, ["sync"])

        self.assertEqual(ctx.exception.code, "garmin_script_failed")
        self.assertIn("exit 2", str(ctx.exception))
        self.assertIn("auth failed", str(ctx.exception))

    def test_subprocess_auth_failure_raises_auth_required_code(self):
        script = self.scripts_dir / "download_fit.py"
        stderr = "Garmin 认证失败（region=global）。请先运行 login.py 登录对应区域账号"
        with mock.patch.object(
            garmin_sync.subprocess,
            "run",
            return_value=self._completed(stderr=stderr, returncode=1),
        ):
            with self.assertRaises(garmin_sync.GarminAuthRequiredError) as ctx:
                garmin_sync.run_garmin_script(script, ["--json"])

        self.assertEqual(ctx.exception.code, "garmin_auth_required")
        self.assertIn("授权不可用", str(ctx.exception))

    def test_download_fit_json_builds_machine_readable_command(self):
        payload = {"ok": True, "downloaded": 1, "files": ["a.fit"]}
        output_dir = self.base_dir / "tracks"
        with mock.patch.object(
            garmin_sync.subprocess,
            "run",
            return_value=self._completed(stdout=json.dumps(payload)),
        ) as run_mock:
            parsed = garmin_sync.download_fit_json(
                base_dir=self.base_dir,
                start_date="2026-05-01",
                end_date="2026-05-31",
                output_dir=output_dir,
                region="cn",
            )

        self.assertEqual(parsed, payload)
        command = run_mock.call_args.args[0]
        self.assertIn("download_fit.py", command[1])
        self.assertEqual(
            command[2:],
            [
                "--from",
                "2026-05-01",
                "--to",
                "2026-05-31",
                "--region",
                "cn",
                "--output-dir",
                str(output_dir),
                "--json",
            ],
        )

    def test_download_fit_json_rejects_non_object(self):
        with mock.patch.object(
            garmin_sync.subprocess,
            "run",
            return_value=self._completed(stdout="[]"),
        ):
            with self.assertRaisesRegex(garmin_sync.GarminJsonParseError, "不是 JSON 对象"):
                garmin_sync.download_fit_json(
                    base_dir=self.base_dir,
                    start_date="2026-05-01",
                    end_date="2026-05-31",
                    output_dir=self.base_dir / "tracks",
                )

    def test_login_command_returns_command_without_running(self):
        with mock.patch.object(garmin_sync.subprocess, "run") as run_mock:
            command = garmin_sync.login_command(base_dir=self.base_dir, region="global")

        self.assertEqual(command[0], sys.executable)
        self.assertIn("login.py", command[1])
        self.assertEqual(command[2:], ["--region", "global"])
        run_mock.assert_not_called()

    def test_login_command_uses_internal_cli_mode_when_frozen(self):
        executable = str(self.base_dir / "脉图.app" / "Contents" / "MacOS" / "FitVault")
        with mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "executable", executable):
            command = garmin_sync.login_command(base_dir=self.base_dir, region="cn")

        self.assertEqual(command, [executable, "--garmin-login", "--region", "cn"])

    def test_login_command_uses_console_helper_when_windows_frozen(self):
        executable = self.base_dir / "FitVault.exe"
        cli_exe = self.base_dir / "FitVaultCLI.exe"
        executable.write_text("", encoding="utf-8")
        cli_exe.write_text("", encoding="utf-8")
        with mock.patch.object(garmin_sync.sys, "platform", "win32"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "executable", str(executable)):
            command = garmin_sync.login_command(base_dir=self.base_dir, region="cn")

        self.assertEqual(command, [str(cli_exe), "--garmin-login", "--region", "cn"])

    def test_default_tokenstore_uses_region_suffix(self):
        workspace = self.base_dir / "workspace"

        self.assertEqual(
            garmin_sync.default_tokenstore("cn", workspace),
            workspace / "garmin_auth_cn",
        )
        self.assertEqual(
            garmin_sync.default_tokenstore("global", workspace),
            workspace / "garmin_auth_global",
        )

    def test_default_tokenstore_uses_qclaw_workspace_env(self):
        workspace = self.base_dir / "custom_workspace"
        with mock.patch.dict(os.environ, {"QCLAW_WORKSPACE_DIR": str(workspace)}):
            self.assertEqual(
                garmin_sync.default_tokenstore("cn"),
                workspace / "garmin_auth_cn",
            )

    def test_check_auth_status_missing_token(self):
        workspace = self.base_dir / "workspace"

        status = garmin_sync.check_auth_status(
            base_dir=self.base_dir,
            workspace_dir=workspace,
            region="cn",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.region, "cn")
        self.assertEqual(status.status, "missing_token")
        self.assertEqual(status.token_path, str(workspace / "garmin_auth_cn"))
        self.assertIn("请先登录 Garmin", status.message)
        self.assertEqual(status.login_command[0], sys.executable)
        self.assertIn("login.py", status.login_command[1])

    def test_check_auth_status_authorized_when_token_file_exists(self):
        workspace = self.base_dir / "workspace"
        workspace.mkdir()
        token = workspace / "garmin_auth_cn"
        token.write_text("secret-token-content", encoding="utf-8")

        with mock.patch.object(Path, "read_text", side_effect=AssertionError("token content should not be read")):
            status = garmin_sync.check_auth_status(
                base_dir=self.base_dir,
                workspace_dir=workspace,
                region="cn",
            )

        self.assertTrue(status.ok)
        self.assertEqual(status.status, "authorized")
        self.assertIn("已检测到 Garmin 授权", status.message)
        self.assertEqual(status.token_path, str(token))

    def test_check_auth_status_authorized_when_token_directory_exists(self):
        workspace = self.base_dir / "workspace"
        token_dir = workspace / "garmin_auth_global"
        token_dir.mkdir(parents=True)
        (token_dir / "oauth1_token.json").write_text("{}", encoding="utf-8")
        (token_dir / "oauth2_token.json").write_text("{}", encoding="utf-8")

        status = garmin_sync.check_auth_status(
            base_dir=self.base_dir,
            workspace_dir=workspace,
            region="global",
        )

        self.assertTrue(status.ok)
        self.assertEqual(status.region, "global")
        self.assertEqual(status.status, "authorized")
        self.assertEqual(status.token_path, str(token_dir))

    def test_check_auth_status_rejects_incomplete_token_directory(self):
        workspace = self.base_dir / "workspace"
        token_dir = workspace / "garmin_auth_global"
        token_dir.mkdir(parents=True)

        status = garmin_sync.check_auth_status(
            base_dir=self.base_dir,
            workspace_dir=workspace,
            region="global",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.status, "missing_token")
        self.assertIn("token 不完整", status.message)

    def test_check_auth_status_invalid_region_returns_status(self):
        status = garmin_sync.check_auth_status(
            base_dir=self.base_dir,
            workspace_dir=self.base_dir / "workspace",
            region="eu",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.region, "eu")
        self.assertEqual(status.status, "invalid_region")
        self.assertEqual(status.login_command, [])
        self.assertIn("不支持的 Garmin 区域", status.message)

    def test_check_auth_status_skill_missing_returns_status(self):
        workspace = self.base_dir / "workspace"
        (self.scripts_dir / "login.py").unlink()

        status = garmin_sync.check_auth_status(
            base_dir=self.base_dir,
            workspace_dir=workspace,
            region="cn",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.status, "skill_missing")
        self.assertEqual(status.login_command, [])
        self.assertIn("未找到 Garmin skill 脚本", status.message)

    def test_check_auth_status_does_not_execute_login(self):
        workspace = self.base_dir / "workspace"
        with mock.patch.object(garmin_sync.subprocess, "run") as run_mock:
            status = garmin_sync.check_auth_status(
                base_dir=self.base_dir,
                workspace_dir=workspace,
                region="cn",
            )

        self.assertEqual(status.status, "missing_token")
        run_mock.assert_not_called()

    def test_start_login_uses_shell_false(self):
        with mock.patch.object(garmin_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 garmin_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout="ok"),
             ) as run_mock:
            result = garmin_sync.start_login(base_dir=self.base_dir, region="cn", timeout=9)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "completed")
        command = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(command[0], sys.executable)
        self.assertIn("login.py", command[1])
        self.assertEqual(command[2:], ["--region", "cn"])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 9)

    def test_start_login_on_macos_opens_terminal_without_blocking(self):
        with mock.patch.object(garmin_sync.sys, "platform", "darwin"), \
             mock.patch.object(garmin_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(garmin_sync.subprocess, "run") as run_mock:
            result = garmin_sync.start_login(base_dir=self.base_dir, region="global")

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "launched")
        self.assertIn("终端", result.message)
        popen_mock.assert_called_once()
        run_mock.assert_not_called()
        osa_command = popen_mock.call_args.args[0]
        self.assertIn("osascript", osa_command[0])

    def test_start_login_on_macos_frozen_uses_internal_cli_without_reopening_app_window(self):
        executable = str(self.base_dir / "脉图.app" / "Contents" / "MacOS" / "FitVault")
        with mock.patch.object(garmin_sync.sys, "platform", "darwin"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "executable", executable), \
             mock.patch.object(garmin_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(garmin_sync.subprocess, "run") as run_mock:
            result = garmin_sync.start_login(base_dir=self.base_dir, region="global")

        self.assertTrue(result.ok)
        self.assertEqual(result.command, [executable, "--garmin-login", "--region", "global"])
        osa_command = popen_mock.call_args.args[0]
        script = " ".join(osa_command)
        self.assertIn("--garmin-login", script)
        self.assertNotIn("login.py", script)
        run_mock.assert_not_called()

    def test_start_login_on_windows_opens_cmd_without_blocking(self):
        with mock.patch.object(garmin_sync.sys, "platform", "win32"), \
             mock.patch.object(garmin_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(garmin_sync.subprocess, "run") as run_mock:
            result = garmin_sync.start_login(base_dir=self.base_dir, region="global")

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "launched")
        self.assertIn("命令行窗口", result.message)
        popen_mock.assert_called_once()
        run_mock.assert_not_called()
        launcher = popen_mock.call_args.args[0]
        self.assertEqual(launcher[:4], ["cmd.exe", "/d", "/c", "start"])
        self.assertIn("cmd.exe", launcher)
        self.assertIn("pause", launcher[-1])
        self.assertIn("login.py", launcher[-1])

    def test_start_login_on_windows_frozen_uses_internal_cli_in_cmd(self):
        executable = str(self.base_dir / "FitVault.exe")
        cli_exe = str(self.base_dir / "FitVaultCLI.exe")
        Path(executable).write_text("", encoding="utf-8")
        Path(cli_exe).write_text("", encoding="utf-8")
        with mock.patch.object(garmin_sync.sys, "platform", "win32"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync.sys, "executable", executable), \
             mock.patch.object(garmin_sync.subprocess, "Popen") as popen_mock:
            result = garmin_sync.start_login(base_dir=self.base_dir, region="cn")

        self.assertTrue(result.ok)
        self.assertEqual(result.command, [cli_exe, "--garmin-login", "--region", "cn"])
        launcher_script = popen_mock.call_args.args[0][-1]
        self.assertIn("FitVaultCLI.exe", launcher_script)
        self.assertIn("--garmin-login", launcher_script)
        self.assertNotIn("login.py", launcher_script)

    def test_start_login_nonzero_returns_failed(self):
        with mock.patch.object(garmin_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 garmin_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout="", stderr="bad auth", returncode=3),
             ):
            result = garmin_sync.start_login(base_dir=self.base_dir, region="cn")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "failed")
        self.assertIn("exit 3", result.message)
        self.assertIn("bad auth", result.message)

    def test_start_login_timeout_returns_timeout(self):
        with mock.patch.object(garmin_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 garmin_sync.subprocess,
                 "run",
                 side_effect=subprocess.TimeoutExpired("login", 1, output="partial", stderr="waiting"),
             ):
            result = garmin_sync.start_login(base_dir=self.base_dir, region="cn", timeout=1)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.stdout, "partial")
        self.assertEqual(result.stderr, "waiting")

    def test_start_login_invalid_region_returns_status(self):
        result = garmin_sync.start_login(base_dir=self.base_dir, region="eu")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "invalid_region")
        self.assertEqual(result.command, [])

    def test_start_login_skill_missing_returns_status(self):
        (self.scripts_dir / "login.py").unlink()

        result = garmin_sync.start_login(base_dir=self.base_dir, region="cn")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "skill_missing")
        self.assertEqual(result.command, [])


if __name__ == "__main__":
    unittest.main()
