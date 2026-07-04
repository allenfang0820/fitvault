import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import coros_sync


class TestCorosSyncProvider(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir_obj.name)
        self.scripts_dir = self.base_dir / "skills" / "coros-stats" / "scripts"
        self.scripts_dir.mkdir(parents=True)
        for name in (
            "coros_runner_profile.py",
            "install_coros_mcp.sh",
            "install_coros_mcp.cmd",
        ):
            path = self.scripts_dir / name
            path.write_text("# test script\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def _completed(self, stdout="", stderr="", returncode=0):
        return subprocess.CompletedProcess(
            args=["bash", "install_coros_mcp.sh"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_default_region_is_cn(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(coros_sync.resolve_coros_region(), "cn")

    def test_environment_region_is_used(self):
        with mock.patch.dict(os.environ, {"COROS_REGION": "eu"}):
            self.assertEqual(coros_sync.resolve_coros_region(), "eu")

    def test_invalid_region_raises_readable_error(self):
        with self.assertRaises(coros_sync.CorosSyncError) as ctx:
            coros_sync.resolve_coros_region("global")

        self.assertEqual(ctx.exception.code, "invalid_coros_region")
        self.assertIn("仅支持", str(ctx.exception))

    def test_skill_paths_are_resolved_from_base_dir(self):
        paths = coros_sync.get_coros_skill_paths(self.base_dir)

        self.assertEqual(paths.skill_dir, self.base_dir.resolve() / "skills" / "coros-stats")
        self.assertEqual(paths.profile_runner.name, "coros_runner_profile.py")
        self.assertEqual(paths.install_mcp.name, "install_coros_mcp.sh")

    def test_app_base_dir_prefers_bundle_resources_for_packaged_skills(self):
        bundle = self.base_dir / "脉图.app" / "Contents"
        frameworks = bundle / "Frameworks"
        resources = bundle / "Resources"
        scripts = resources / "skills" / "coros-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "coros_runner_profile.py").write_text("# packaged\n", encoding="utf-8")
        exe = bundle / "MacOS" / "FitVault"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(frameworks), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)):
            self.assertEqual(coros_sync.app_base_dir(), resources)

    def test_app_base_dir_supports_windows_onefile_meipass_skills(self):
        meipass = self.base_dir / "_MEI12345"
        scripts = meipass / "skills" / "coros-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "coros_runner_profile.py").write_text("# packaged\n", encoding="utf-8")
        exe = self.base_dir / "FitVault.exe"
        exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)):
            self.assertEqual(coros_sync.app_base_dir(), meipass)

    def test_app_base_dir_supports_windows_onedir_internal_skills(self):
        exe_dir = self.base_dir / "dist" / "FitVault"
        internal = exe_dir / "_internal"
        scripts = internal / "skills" / "coros-stats" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "coros_runner_profile.py").write_text("# packaged\n", encoding="utf-8")
        exe = exe_dir / "FitVault.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("", encoding="utf-8")
        meipass = internal

        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "_MEIPASS", str(meipass), create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(exe)):
            self.assertEqual(coros_sync.app_base_dir(), internal)

    def test_missing_skill_script_raises(self):
        (self.scripts_dir / "install_coros_mcp.sh").unlink()

        with self.assertRaises(coros_sync.CorosSkillNotFoundError) as ctx:
            coros_sync.get_coros_skill_paths(self.base_dir)

        self.assertEqual(ctx.exception.code, "coros_skill_not_found")
        self.assertIn("install_coros_mcp.sh", str(ctx.exception))

    def test_default_mcp_token_path_uses_region_suffix(self):
        root = self.base_dir / "tokens"

        self.assertEqual(
            coros_sync.default_mcp_token_path("cn", root),
            root / "cn" / "token.json",
        )
        self.assertEqual(
            coros_sync.default_mcp_token_path("eu", root),
            root / "eu" / "token.json",
        )

    def test_login_command_returns_command_without_running(self):
        with mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            command = coros_sync.login_command(base_dir=self.base_dir, region="us")

        self.assertEqual(command[0], "bash")
        self.assertIn("install_coros_mcp.sh", command[1])
        self.assertEqual(command[2:], ["--region", "us"])
        run_mock.assert_not_called()

    def test_login_command_uses_windows_cmd_installer_on_windows(self):
        with mock.patch.object(coros_sync.sys, "platform", "win32"):
            command = coros_sync.login_command(base_dir=self.base_dir, region="eu")

        self.assertEqual(Path(command[0]).name, "install_coros_mcp.cmd")
        self.assertEqual(command[1:], ["--region", "eu"])

    def test_login_command_on_windows_requires_cmd_installer(self):
        (self.scripts_dir / "install_coros_mcp.cmd").unlink()
        with mock.patch.object(coros_sync.sys, "platform", "win32"):
            with self.assertRaises(coros_sync.CorosSkillNotFoundError) as ctx:
                coros_sync.login_command(base_dir=self.base_dir, region="eu")

        self.assertIn("install_coros_mcp.cmd", str(ctx.exception))
        self.assertNotIn("install_coros_mcp.sh", str(ctx.exception))

    def test_discover_node_binary_uses_nvm_fallback(self):
        node_path = self.base_dir / ".nvm" / "versions" / "node" / "v24.18.0" / "bin" / "node"
        node_path.parent.mkdir(parents=True)
        node_path.write_text("#!/bin/sh\n", encoding="utf-8")
        node_path.chmod(0o755)

        with mock.patch.object(coros_sync.shutil, "which", return_value=None), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(coros_sync.discover_node_binary(home=self.base_dir), str(node_path))

    def test_discover_node_binary_prefers_bundled_node_runtime(self):
        node_path = self.base_dir / "node" / "bin" / "node"
        node_path.parent.mkdir(parents=True)
        node_path.write_text("#!/bin/sh\n", encoding="utf-8")
        node_path.chmod(0o755)

        with mock.patch.object(coros_sync, "app_base_dir", return_value=self.base_dir), \
             mock.patch.object(coros_sync.shutil, "which", return_value=None), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(coros_sync.discover_node_binary(home=self.base_dir), str(node_path))

    def test_discover_node_binary_supports_bundled_windows_runtime(self):
        node_path = self.base_dir / "node" / "node.exe"
        node_path.parent.mkdir(parents=True)
        node_path.write_text("test exe\n", encoding="utf-8")
        node_path.chmod(0o755)

        with mock.patch.object(coros_sync, "app_base_dir", return_value=self.base_dir), \
             mock.patch.object(coros_sync.shutil, "which", return_value=None), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(coros_sync.discover_node_binary(home=self.base_dir), str(node_path))

    def test_build_coros_runtime_env_injects_qclaw_runtime(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value="/tmp/openclaw.mjs"):
            env = coros_sync.build_coros_runtime_env({"PATH": "/usr/bin"})

        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "/tmp/node/bin/node")
        self.assertEqual(env["QCLAW_CLI_OPENCLAW_MJS"], "/tmp/openclaw.mjs")
        self.assertEqual(env["MAITU_BUNDLED_NODE_DIR"], "/tmp/node")
        self.assertTrue(env["PATH"].startswith("/tmp/node/bin:"))

    def test_build_coros_runtime_env_handles_windows_node_root(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="C:\\FitVault\\node\\node.exe"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value=""):
            env = coros_sync.build_coros_runtime_env({"PATH": "C:\\Windows"})

        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "C:\\FitVault\\node\\node.exe")
        self.assertEqual(env["MAITU_BUNDLED_NODE_DIR"], "C:\\FitVault\\node")
        self.assertTrue(env["PATH"].startswith("C:\\FitVault\\node"))

    def test_check_auth_status_invalid_region_returns_status(self):
        status = coros_sync.check_auth_status(
            base_dir=self.base_dir,
            token_root=self.base_dir / "tokens",
            region="global",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.region, "global")
        self.assertEqual(status.status, "invalid_region")
        self.assertEqual(status.login_command, [])
        self.assertFalse(status.skill_available)
        self.assertEqual(status.diagnostics[0]["name"], "region")
        self.assertIn("不支持的 COROS 区域", status.message)

    def test_check_auth_status_skill_missing_returns_status(self):
        (self.scripts_dir / "coros_runner_profile.py").unlink()

        status = coros_sync.check_auth_status(
            base_dir=self.base_dir,
            token_root=self.base_dir / "tokens",
            region="cn",
        )

        self.assertFalse(status.ok)
        self.assertEqual(status.status, "skill_missing")
        self.assertEqual(status.login_command, [])
        self.assertFalse(status.skill_available)
        self.assertEqual(status.diagnostics[-1]["name"], "skill")
        self.assertIn("未找到 COROS skill 脚本", status.message)

    def test_check_auth_status_node_missing(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value=""):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertFalse(status.ok)
        self.assertEqual(status.status, "node_missing")
        self.assertFalse(status.node_available)
        self.assertTrue(status.skill_available)
        self.assertIn("node", [item["name"] for item in status.diagnostics])
        self.assertIn("Node.js", status.message)

    def test_check_auth_status_reports_fallback_node_and_openclaw_runtime(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value="/tmp/openclaw.mjs"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout='{"region":"cn","mcpUrl":"https://mcpcn.coros.com/mcp","tokenPath":"/tmp/cn/token.json"}')):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertFalse(status.ok)
        self.assertEqual(status.node_path, "/tmp/node/bin/node")
        self.assertEqual(status.openclaw_node_binary, "/tmp/node/bin/node")
        self.assertEqual(status.openclaw_mjs, "/tmp/openclaw.mjs")
        self.assertIn("openclaw_runtime", [item["name"] for item in status.diagnostics])

    def test_check_auth_status_missing_token(self):
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertFalse(status.ok)
        self.assertEqual(status.region, "cn")
        self.assertEqual(status.status, "missing_token")
        self.assertEqual(status.token_path, str(self.base_dir / "tokens" / "cn" / "token.json"))
        self.assertIn("请先登录 COROS", status.message)
        self.assertEqual(status.login_command[0], "bash")
        self.assertTrue(status.skill_available)
        self.assertIn("keepalive_config", [item["name"] for item in status.diagnostics])

    def test_check_auth_status_authorized_when_mcp_token_exists(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "eu" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("token content should not be read")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="eu",
            )

        self.assertTrue(status.ok)
        self.assertEqual(status.status, "authorized")
        self.assertTrue(status.mcp_authorized)
        self.assertEqual(status.token_path, str(token_path))
        self.assertTrue(status.skill_available)

    def test_check_auth_status_has_no_traininghub_warning_when_mcp_authorized(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")

        with mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout='{"region":"cn","mcpUrl":"https://mcpcn.coros.com/mcp","tokenPath":"/tmp/cn/token.json"}')), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("token content should not be read")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="cn",
            )

        self.assertTrue(status.ok)
        self.assertTrue(status.mcp_authorized)
        self.assertNotIn("Training Hub", status.message)
        self.assertNotIn("traininghub_token", [item["name"] for item in status.diagnostics])

    def test_check_auth_status_does_not_execute_login_script(self):
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout='{"region":"cn","mcpUrl":"https://mcpcn.coros.com/mcp","tokenPath":"/tmp/cn/token.json"}'),
             ) as run_mock:
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertEqual(status.status, "missing_token")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/node")
        self.assertIn("--print-config", command)
        self.assertNotIn("install_coros_mcp.sh", " ".join(command))

    def test_check_auth_status_keepalive_config_success_is_reported(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "eu" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")
        stdout = json.dumps({
            "region": "eu",
            "mcpUrl": "https://mcpeu.coros.com/mcp",
            "tokenPath": str(token_path),
        })

        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout)), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("token content should not be read")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="eu",
            )

        self.assertTrue(status.ok)
        self.assertEqual(status.keepalive_region, "eu")
        self.assertEqual(status.keepalive_mcp_url, "https://mcpeu.coros.com/mcp")
        self.assertEqual(status.keepalive_token_path, str(token_path))
        self.assertIn("keepalive_config", [item["name"] for item in status.diagnostics])

    def test_check_auth_status_keepalive_non_json_is_diagnostic_not_crash(self):
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="not json")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertFalse(status.ok)
        keepalive = [item for item in status.diagnostics if item["name"] == "keepalive_config"][0]
        self.assertEqual(keepalive["status"], "failed")
        self.assertIn("合法 JSON", keepalive["message"])

    def test_start_login_uses_shell_false(self):
        with mock.patch.object(coros_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout="ok"),
             ) as run_mock:
            result = coros_sync.start_login(base_dir=self.base_dir, region="us", timeout=9)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "completed")
        command = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(command[0], "bash")
        self.assertIn("install_coros_mcp.sh", command[1])
        self.assertEqual(command[2:], ["--region", "us"])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 9)

    def test_start_login_on_macos_opens_terminal_without_blocking(self):
        with mock.patch.object(coros_sync.sys, "platform", "darwin"), \
             mock.patch.object(coros_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            result = coros_sync.start_login(base_dir=self.base_dir, region="cn")

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "launched")
        self.assertIn("终端", result.message)
        popen_mock.assert_called_once()
        run_mock.assert_not_called()

    def test_start_login_on_windows_opens_cmd_without_blocking(self):
        with mock.patch.object(coros_sync.sys, "platform", "win32"), \
             mock.patch.object(coros_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            result = coros_sync.start_login(base_dir=self.base_dir, region="us")

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "launched")
        self.assertIn("命令行", result.message)
        self.assertEqual(Path(result.command[0]).name, "install_coros_mcp.cmd")
        launcher = popen_mock.call_args.args[0]
        self.assertEqual(launcher[:4], ["cmd.exe", "/d", "/c", "start"])
        self.assertIn("cmd.exe", launcher)
        self.assertIn("pause", launcher[-1])
        self.assertIn("install_coros_mcp.cmd", launcher[-1])
        run_mock.assert_not_called()

    def test_start_login_nonzero_returns_failed(self):
        with mock.patch.object(coros_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout="", stderr="bad auth", returncode=3),
             ):
            result = coros_sync.start_login(base_dir=self.base_dir, region="cn")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "failed")
        self.assertIn("exit 3", result.message)
        self.assertIn("bad auth", result.message)

    def test_start_login_timeout_returns_timeout(self):
        with mock.patch.object(coros_sync.sys, "platform", "linux"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 side_effect=subprocess.TimeoutExpired("login", 1, output="partial", stderr="waiting"),
             ):
            result = coros_sync.start_login(base_dir=self.base_dir, region="cn", timeout=1)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.stdout, "partial")
        self.assertEqual(result.stderr, "waiting")

    def test_run_coros_script_uses_python_shell_false_and_script_cwd(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        with mock.patch.object(
            coros_sync.subprocess,
            "run",
            return_value=self._completed(stdout="[]"),
        ) as run_mock:
            result = coros_sync.run_coros_script(script, ["sync"], timeout=11, env={"COROS_REGION": "eu"})

        self.assertEqual(result.stdout, "[]")
        command = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(command[0], coros_sync.sys.executable)
        self.assertEqual(command[1], str(script.resolve()))
        self.assertEqual(command[2:], ["sync"])
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 11)
        self.assertEqual(kwargs["cwd"], str(script.resolve().parent))
        self.assertEqual(kwargs["env"]["COROS_REGION"], "eu")

    def test_run_coros_script_nonzero_raises_script_failed(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        with mock.patch.object(
            coros_sync.subprocess,
            "run",
            return_value=self._completed(stderr="Cannot find module coros-mcp", returncode=1),
        ):
            with self.assertRaises(coros_sync.CorosScriptFailed) as ctx:
                coros_sync.run_coros_script(script, ["sync"])

        self.assertEqual(ctx.exception.code, "coros_script_failed")
        self.assertIn("exit 1", str(ctx.exception))

    def test_run_coros_script_auth_failure_raises_auth_required(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        with mock.patch.object(
            coros_sync.subprocess,
            "run",
            return_value=self._completed(stderr="missing_token: 请先登录 COROS", returncode=2),
        ):
            with self.assertRaises(coros_sync.CorosAuthRequiredError) as ctx:
                coros_sync.run_coros_script(script, ["sync"])

        self.assertEqual(ctx.exception.code, "coros_auth_required")
        self.assertIn("配置页完成授权", str(ctx.exception))

    def test_run_coros_script_timeout_raises_script_failed(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        with mock.patch.object(
            coros_sync.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("sync", 1),
        ):
            with self.assertRaises(coros_sync.CorosScriptFailed) as ctx:
                coros_sync.run_coros_script(script, ["sync"], timeout=1)

        self.assertEqual(ctx.exception.code, "coros_script_failed")
        self.assertIn("超时", str(ctx.exception))

    def test_sync_profile_json_runs_profile_runner_with_region_env(self):
        payload = [{"metric": "username", "value": "coros-user"}]
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text(
            "import os\n"
            "def build_profile():\n"
            "    assert os.environ.get('COROS_REGION') == 'us'\n"
            f"    return {payload!r}\n",
            encoding="utf-8",
        )
        with mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=AssertionError("profile sync must not spawn script")):
            result = coros_sync.sync_profile_json(base_dir=self.base_dir, region="us", timeout=7)

        self.assertEqual(result, payload)

    def test_sync_profile_json_rejects_non_json_stdout(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return 'not json'\n", encoding="utf-8")
        with self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertEqual(ctx.exception.code, "coros_json_parse_error")

    def test_sync_profile_json_rejects_non_array_stdout(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return {'metric': 'username'}\n", encoding="utf-8")
        with self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertIn("不是 JSON 数组", str(ctx.exception))

    def test_sync_profile_json_rejects_non_object_array_items(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return ['bad']\n", encoding="utf-8")
        with self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertIn("数组元素必须是对象", str(ctx.exception))

    def test_sync_profile_json_restores_environment_after_imported_runner(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text(
            "import os\n"
            "def build_profile():\n"
            "    assert os.environ.get('COROS_REGION') == 'eu'\n"
            "    assert os.environ.get('QCLAW_CLI_NODE_BINARY') == '/tmp/node'\n"
            "    return []\n",
            encoding="utf-8",
        )
        with mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={"QCLAW_CLI_NODE_BINARY": "/tmp/node"}), \
             mock.patch.dict(os.environ, {"COROS_REGION": "cn"}, clear=False):
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="eu")
            self.assertEqual(os.environ.get("COROS_REGION"), "cn")
            self.assertNotEqual(os.environ.get("QCLAW_CLI_NODE_BINARY"), "/tmp/node")

    def test_sync_profile_json_frozen_windows_does_not_launch_app_executable(self):
        payload = [{"metric": "username", "value": "coros-user"}]
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text(f"def build_profile():\n    return {payload!r}\n", encoding="utf-8")
        app_exe = self.base_dir / "FitVault.exe"
        app_exe.write_text("", encoding="utf-8")

        with mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(app_exe)), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=AssertionError("profile sync must not launch sys.executable")):
            parsed = coros_sync.sync_profile_json(base_dir=self.base_dir)

        self.assertEqual(parsed, payload)

    def test_download_fit_json_limits_coros_range_download_to_ten(self):
        payload = {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "mimeType": "application/octet-stream",
                        "name": f"activity-{idx}.fit",
                        "blob": "Zml0",
                    },
                }
                for idx in range(12)
            ]
        }
        with mock.patch.object(coros_sync, "run_coros_mcp_tool", return_value=payload) as tool_mock:
            result = coros_sync.download_fit_json(
                start_date="2026-05-01",
                end_date="2026-05-31",
                output_dir=self.base_dir / "tracks",
                region="cn",
                limit=99,
            )

        tool_mock.assert_called_once()
        args, kwargs = tool_mock.call_args
        self.assertEqual(args[0], "downloadActivityFitFiles")
        self.assertEqual(args[1]["startDate"], "20260501")
        self.assertEqual(args[1]["endDate"], "20260531")
        self.assertEqual(args[1]["limit"], 10)
        self.assertEqual(result["provider"], "coros")
        self.assertEqual(result["downloaded"], 10)
        self.assertEqual(result["limit"], 10)

    def test_download_fit_json_falls_back_to_url_tool_when_binary_has_no_files(self):
        payloads = [
            {"content": [{"type": "text", "text": "no binary resources"}]},
            {"content": [{"type": "text", "text": json.dumps({"urls": ["https://example.com/a.fit"]})}]},
        ]
        with mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads) as tool_mock, \
             mock.patch.object(coros_sync, "_download_url_to_fit", return_value={"file": "/tmp/a.fit", "status": "downloaded", "bytes": 3, "url": "https://example.com/a.fit"}) as url_mock:
            result = coros_sync.download_fit_json(
                start_date="2026-05-01",
                end_date="2026-05-31",
                output_dir=self.base_dir / "tracks",
                region="eu",
                limit=5,
            )

        self.assertEqual([call.args[0] for call in tool_mock.call_args_list], ["downloadActivityFitFiles", "queryActivityFitFileDownloadUrls"])
        url_mock.assert_called_once()
        self.assertEqual(result["downloaded"], 1)
        self.assertEqual(result["region"], "eu")

    def test_download_fit_json_falls_back_to_sport_records_single_activity_binary(self):
        sport_records_text = json.dumps(
            "Sport Records — 2026-06-22 to 2026-07-02 (1 records)\n"
            "========================\n\n"
            "1. Outdoor Run — 2026-07-01\n"
            "   LabelId: 478587344962748420 | SportType: 100\n"
        )
        payloads = [
            {"content": [{"type": "text", "text": "no binary resources"}]},
            {"content": [{"type": "text", "text": "no urls"}]},
            {"content": [{"type": "text", "text": sport_records_text}]},
            {
                "content": [
                    {
                        "type": "resource",
                        "resource": {
                            "mimeType": "application/octet-stream",
                            "name": "single.fit",
                            "blob": "Zml0",
                        },
                    }
                ]
            },
        ]
        with mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads) as tool_mock:
            result = coros_sync.download_fit_json(
                start_date="2026-06-22",
                end_date="2026-07-02",
                output_dir=self.base_dir / "tracks",
                region="cn",
                limit=10,
            )

        self.assertEqual([call.args[0] for call in tool_mock.call_args_list], [
            "downloadActivityFitFiles",
            "queryActivityFitFileDownloadUrls",
            "querySportRecords",
            "downloadActivityFitFiles",
        ])
        self.assertEqual(tool_mock.call_args_list[3].args[1], {
            "labelId": "478587344962748420",
            "sportType": 100,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["strategy"], "sport_records_binary")
        self.assertEqual(result["searched"], 1)
        self.assertEqual(result["downloaded"], 1)
        self.assertEqual(result["files"][0]["labelId"], "478587344962748420")

    def test_download_fit_json_reports_failure_when_sport_records_exist_but_no_fit(self):
        sport_records_text = json.dumps(
            "Sport Records — 2026-06-22 to 2026-07-02 (1 records)\n"
            "========================\n\n"
            "1. Outdoor Run — 2026-07-01\n"
            "   LabelId: 478587344962748420 | SportType: 100\n"
        )
        payloads = [
            {"content": [{"type": "text", "text": "no binary resources"}]},
            {"content": [{"type": "text", "text": "no urls"}]},
            {"content": [{"type": "text", "text": sport_records_text}]},
            {"content": [{"type": "text", "text": "no binary for activity"}]},
            {"content": [{"type": "text", "text": "no url for activity"}]},
        ]
        with mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads):
            result = coros_sync.download_fit_json(
                start_date="2026-06-22",
                end_date="2026-07-02",
                output_dir=self.base_dir / "tracks",
                region="cn",
                limit=10,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["searched"], 1)
        self.assertGreaterEqual(result["failed"], 1)
        self.assertEqual(result["downloaded"], 0)
        self.assertEqual(result["strategy"], "sport_records_url")
        self.assertEqual(result["errors"][0]["labelId"], "478587344962748420")


if __name__ == "__main__":
    unittest.main()
