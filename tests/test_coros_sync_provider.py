import json
import os
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import coros_sync


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COROS_PROFILE_RUNNER = PROJECT_ROOT / "skills" / "coros-stats" / "scripts" / "coros_runner_profile.py"


def load_coros_profile_runner():
    spec = importlib.util.spec_from_file_location("_test_coros_runner_profile", COROS_PROFILE_RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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

    def _auth_available_patch(self):
        return mock.patch.object(coros_sync, "ensure_auth_available")

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

    def test_default_mcp_token_root_prefers_environment(self):
        root = self.base_dir / "env-tokens"
        with mock.patch.dict(os.environ, {"COROS_MCP_TOKEN_ROOT": str(root)}):
            self.assertEqual(coros_sync.default_mcp_token_root(), root)
            self.assertEqual(coros_sync.default_mcp_token_path("us"), root / "us" / "token.json")

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
        prefix = self.base_dir / "node-global"
        with mock.patch.dict(os.environ, {"MAITU_NODE_GLOBAL_PREFIX": str(prefix)}), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value="/tmp/openclaw.mjs"):
            env = coros_sync.build_coros_runtime_env({"PATH": "/usr/bin"})

        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "/tmp/node/bin/node")
        self.assertEqual(env["QCLAW_CLI_OPENCLAW_MJS"], "/tmp/openclaw.mjs")
        self.assertEqual(env["MAITU_BUNDLED_NODE_DIR"], "/tmp/node")
        self.assertEqual(env["NPM_CONFIG_PREFIX"], str(prefix))
        self.assertTrue(env["PATH"].startswith(f"/tmp/node/bin:{prefix / 'bin'}:"))

    def test_build_coros_runtime_env_handles_windows_node_root(self):
        with mock.patch.dict(os.environ, {"MAITU_NODE_GLOBAL_PREFIX": "C:\\Users\\runner\\.maitu\\node-global"}), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="C:\\FitVault\\node\\node.exe"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value=""):
            env = coros_sync.build_coros_runtime_env({"PATH": "C:\\Windows"})

        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "C:\\FitVault\\node\\node.exe")
        self.assertEqual(env["MAITU_BUNDLED_NODE_DIR"], "C:\\FitVault\\node")
        self.assertTrue(env["PATH"].startswith("C:\\FitVault\\node"))
        self.assertIn("C:\\Users\\runner\\.maitu\\node-global", env["PATH"])
        self.assertEqual(env["COROS_MCP_TOKEN_ROOT"], str(coros_sync.default_mcp_token_root().resolve()))

    def test_build_coros_runtime_env_preserves_explicit_token_root(self):
        token_root = self.base_dir / "custom coros tokens"
        with mock.patch.object(coros_sync, "discover_node_binary", return_value=""), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value=""):
            env = coros_sync.build_coros_runtime_env({
                "PATH": "/usr/bin",
                "COROS_MCP_TOKEN_ROOT": str(token_root),
            })

        self.assertEqual(env["COROS_MCP_TOKEN_ROOT"], str(token_root.resolve()))

    def test_discover_coros_mcp_binary_checks_node_global_prefix(self):
        prefix = self.base_dir / "node-global"
        bin_dir = prefix / "bin"
        bin_dir.mkdir(parents=True)
        cli = bin_dir / "coros-mcp"
        cli.write_text("#!/usr/bin/env node\n", encoding="utf-8")
        cli.chmod(0o755)

        with mock.patch.dict(os.environ, {"MAITU_NODE_GLOBAL_PREFIX": str(prefix)}), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"):
            found = coros_sync.discover_coros_mcp_binary({"PATH": "/usr/bin"})

        self.assertEqual(found, str(cli))

    def test_coros_issuer_for_region(self):
        self.assertEqual(coros_sync.coros_issuer_for_region("cn"), "https://mcpcn.coros.com")
        self.assertEqual(coros_sync.coros_issuer_for_region("us"), "https://mcpus.coros.com")
        self.assertEqual(coros_sync.coros_issuer_for_region("eu"), "https://mcpeu.coros.com")

    def test_prepare_coros_connection_runtime_node_missing(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value=""):
            result = coros_sync.prepare_coros_connection_runtime(region="cn")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "failed")
        self.assertIn("Node", result.message)
        self.assertEqual(result.diagnostics[-1]["name"], "node")

    def test_prepare_coros_connection_runtime_uses_existing_coros_mcp(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync, "discover_npm_binary", return_value="/tmp/node/bin/npm"), \
             mock.patch.object(coros_sync, "discover_coros_mcp_binary", return_value="/tmp/node/bin/coros-mcp"), \
             mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            result = coros_sync.prepare_coros_connection_runtime(region="eu")

        self.assertTrue(result.ok)
        self.assertEqual(result.coros_mcp_path, "/tmp/node/bin/coros-mcp")
        self.assertTrue(result.token_path.endswith("/.coros-mcp-skill-gateway-ts/eu/token.json"))
        run_mock.assert_not_called()

    def test_prepare_coros_connection_runtime_installs_coros_mcp_when_missing(self):
        calls = ["", "/tmp/node/bin/coros-mcp"]
        prefix = self.base_dir / "node-global"
        with mock.patch.dict(os.environ, {"MAITU_NODE_GLOBAL_PREFIX": str(prefix)}), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync, "discover_npm_binary", return_value="/tmp/node/bin/npm"), \
             mock.patch.object(coros_sync, "discover_coros_mcp_binary", side_effect=lambda env=None: calls.pop(0)), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="ok")) as run_mock:
            result = coros_sync.prepare_coros_connection_runtime(region="cn")

        self.assertTrue(result.ok)
        self.assertEqual(result.coros_mcp_path, "/tmp/node/bin/coros-mcp")
        self.assertTrue((prefix / "bin").is_dir())
        command = run_mock.call_args.args[0]
        self.assertEqual(command, ["/tmp/node/bin/npm", "install", "-g", "coros-mcp"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])
        self.assertEqual(run_mock.call_args.kwargs["env"]["NPM_CONFIG_PREFIX"], str(prefix))
        self.assertIn(str(prefix / "bin"), run_mock.call_args.kwargs["env"]["PATH"])

    def test_start_coros_oauth_login_creates_browser_session_without_terminal_wrapper(self):
        with mock.patch.object(coros_sync, "discover_coros_mcp_binary", return_value="/tmp/coros-mcp"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="Open this link:\nhttps://mcpus.coros.com/cli/login/session\n")) as run_mock, \
             mock.patch.object(coros_sync, "open_url_in_system_browser", return_value=True) as open_mock:
            result = coros_sync.start_coros_oauth_login(region="us")

        self.assertTrue(result.ok, result)
        self.assertEqual(result.status, "waiting_callback")
        command = run_mock.call_args.args[0]
        self.assertEqual(command, ["/tmp/coros-mcp", "--issuer", "https://mcpus.coros.com", "login-start"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])
        open_mock.assert_called_once_with("https://mcpus.coros.com/cli/login/session")
        self.assertNotIn("cmd.exe", command)
        self.assertNotIn("osascript", command)

    def test_start_coros_oauth_login_returns_fallback_link_when_browser_open_fails(self):
        url = "https://mcpus.coros.com/cli/login/session"
        with mock.patch.object(coros_sync, "discover_coros_mcp_binary", return_value="/tmp/coros-mcp"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=f"Open this link:\n{url}\n")), \
             mock.patch.object(coros_sync, "open_url_in_system_browser", return_value=False):
            result = coros_sync.start_coros_oauth_login(region="us")

        self.assertTrue(result.ok, result)
        self.assertEqual(result.status, "waiting_callback")
        self.assertIn("未能自动打开浏览器", result.message)
        self.assertIn(url, result.message)

    def test_open_url_in_system_browser_uses_macos_open(self):
        with mock.patch.object(coros_sync.sys, "platform", "darwin"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="")) as run_mock:
            opened = coros_sync.open_url_in_system_browser("https://example.test/login")

        self.assertTrue(opened)
        self.assertEqual(run_mock.call_args.args[0], ["open", "https://example.test/login"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])

    def test_finish_coros_oauth_login_waits_when_cli_poll_times_out(self):
        with mock.patch.object(coros_sync, "discover_coros_mcp_binary", return_value="/tmp/coros-mcp"), \
             mock.patch.dict(os.environ, {"COROS_MCP_TOKEN_ROOT": str(self.base_dir / "tokens")}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=subprocess.TimeoutExpired(["coros-mcp"], 1)):
            result = coros_sync.finish_coros_oauth_login(region="cn", timeout=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "waiting_callback")

    def test_apply_coros_openclaw_optional_warning_does_not_raise(self):
        with mock.patch.object(coros_sync.shutil, "which", return_value=None), \
             mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            diag = coros_sync.apply_coros_openclaw_optional(region="cn", coros_mcp_path="/tmp/coros-mcp")

        self.assertEqual(diag["status"], "warning")
        run_mock.assert_not_called()

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
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        stdout = json.dumps({
            "region": "cn",
            "mcpUrl": "https://mcpcn.coros.com/mcp",
            "tokenPath": str(token_path),
        })
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout)):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="cn",
            )

        self.assertFalse(status.ok)
        self.assertEqual(status.region, "cn")
        self.assertEqual(status.status, "missing_token")
        self.assertEqual(status.token_path, str(token_path))
        self.assertIn("请先登录 COROS", status.message)
        self.assertEqual(status.login_command[0], "bash")
        self.assertTrue(status.skill_available)
        self.assertIn("keepalive_config", [item["name"] for item in status.diagnostics])

    def test_check_auth_status_authorized_when_mcp_token_exists(self):
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
        self.assertEqual(status.status, "authorized")
        self.assertTrue(status.mcp_authorized)
        self.assertEqual(status.token_path, str(token_path))
        self.assertTrue(status.skill_available)

    def test_check_auth_status_has_no_traininghub_warning_when_mcp_authorized(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")
        stdout = json.dumps({
            "region": "cn",
            "mcpUrl": "https://mcpcn.coros.com/mcp",
            "tokenPath": str(token_path),
        })

        with mock.patch.object(coros_sync, "discover_node_binary", return_value="/tmp/node/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout)), \
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
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        stdout = json.dumps({
            "region": "cn",
            "mcpUrl": "https://mcpcn.coros.com/mcp",
            "tokenPath": str(token_path),
        })
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout=stdout),
             ) as run_mock:
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="cn",
            )

        self.assertEqual(status.status, "missing_token")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/node")
        self.assertIn("--print-config", command)
        self.assertNotIn("install_coros_mcp.sh", " ".join(command))
        self.assertEqual(run_mock.call_args.kwargs["env"]["COROS_MCP_TOKEN_ROOT"], str((self.base_dir / "tokens").resolve()))

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

    def test_check_auth_status_reports_keepalive_token_path_mismatch(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")
        wrong_token_path = self.base_dir / "other" / "cn" / "token.json"
        stdout = json.dumps({
            "region": "cn",
            "mcpUrl": "https://mcpcn.coros.com/mcp",
            "tokenPath": str(wrong_token_path),
        })

        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout)), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("token content should not be read")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=token_root,
                region="cn",
            )

        keepalive = [item for item in status.diagnostics if item["name"] == "keepalive_config"][-1]
        self.assertEqual(keepalive["status"], "failed")
        self.assertIn("路径不一致", keepalive["message"])
        self.assertEqual(status.keepalive_token_path, str(wrong_token_path))

    def test_check_auth_status_keepalive_non_json_is_diagnostic_not_crash(self):
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="not json")):
            status = coros_sync.check_auth_status(
                base_dir=self.base_dir,
                token_root=self.base_dir / "tokens",
                region="cn",
            )

        self.assertFalse(status.ok)
        self.assertEqual(status.status, "keepalive_invalid")
        keepalive = [item for item in status.diagnostics if item["name"] == "keepalive_config"][0]
        self.assertEqual(keepalive["status"], "failed")
        self.assertIn("合法 JSON", keepalive["message"])

    def test_ensure_auth_available_maps_missing_token_to_auth_required(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        stdout = json.dumps({
            "region": "cn",
            "mcpUrl": "https://mcpcn.coros.com/mcp",
            "tokenPath": str(token_path),
        })
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout)):
            with self.assertRaises(coros_sync.CorosAuthRequiredError) as ctx:
                coros_sync.ensure_auth_available(base_dir=self.base_dir, token_root=token_root, region="cn")

        self.assertEqual(ctx.exception.code, "coros_auth_required")

    def test_ensure_auth_available_maps_node_missing(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value=""):
            with self.assertRaises(coros_sync.CorosSyncError) as ctx:
                coros_sync.ensure_auth_available(base_dir=self.base_dir, token_root=self.base_dir / "tokens", region="cn")

        self.assertEqual(ctx.exception.code, "coros_node_missing")

    def test_ensure_auth_available_maps_keepalive_invalid(self):
        token_root = self.base_dir / "tokens"
        token_path = token_root / "cn" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret-token-content", encoding="utf-8")
        with mock.patch.object(coros_sync.shutil, "which", return_value="/usr/bin/node"), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout="not json")):
            with self.assertRaises(coros_sync.CorosSyncError) as ctx:
                coros_sync.ensure_auth_available(base_dir=self.base_dir, token_root=token_root, region="cn")

        self.assertEqual(ctx.exception.code, "coros_keepalive_invalid")

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

    def test_start_login_on_windows_legacy_entry_is_disabled_without_console(self):
        with mock.patch.object(coros_sync.sys, "platform", "win32"), \
             mock.patch.object(coros_sync.subprocess, "Popen") as popen_mock, \
             mock.patch.object(coros_sync.subprocess, "run") as run_mock:
            result = coros_sync.start_login(base_dir=self.base_dir, region="us")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "unsupported_legacy_login")
        self.assertIn("账号连接中心", result.message)
        self.assertEqual(Path(result.command[0]).name, "install_coros_mcp.cmd")
        popen_mock.assert_not_called()
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
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=AssertionError("profile sync must not spawn script")):
            result = coros_sync.sync_profile_json(base_dir=self.base_dir, region="us", timeout=7)

        self.assertEqual(result, payload)

    def test_sync_profile_json_stops_before_runner_when_auth_missing(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    raise AssertionError('runner should not execute')\n", encoding="utf-8")
        with mock.patch.object(coros_sync, "ensure_auth_available", side_effect=coros_sync.CorosAuthRequiredError("missing")):
            with self.assertRaises(coros_sync.CorosAuthRequiredError):
                coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

    def test_sync_profile_json_rejects_non_json_stdout(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return 'not json'\n", encoding="utf-8")
        with self._auth_available_patch(), self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertEqual(ctx.exception.code, "coros_json_parse_error")

    def test_sync_profile_json_rejects_non_array_stdout(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return {'metric': 'username'}\n", encoding="utf-8")
        with self._auth_available_patch(), self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertIn("不是 JSON 数组", str(ctx.exception))

    def test_sync_profile_json_rejects_non_object_array_items(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text("def build_profile():\n    return ['bad']\n", encoding="utf-8")
        with self._auth_available_patch(), self.assertRaises(coros_sync.CorosJsonParseError) as ctx:
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="cn")

        self.assertIn("数组元素必须是对象", str(ctx.exception))

    def test_sync_profile_json_restores_environment_after_imported_runner(self):
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text(
            "import os\n"
            "def build_profile():\n"
            "    assert os.environ.get('COROS_REGION') == 'eu'\n"
            "    assert os.environ.get('QCLAW_CLI_NODE_BINARY') == '/tmp/node'\n"
            "    assert os.environ.get('COROS_MCP_TOKEN_ROOT') == '/tmp/coros-tokens'\n"
            "    return []\n",
            encoding="utf-8",
        )
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={"QCLAW_CLI_NODE_BINARY": "/tmp/node", "COROS_MCP_TOKEN_ROOT": "/tmp/coros-tokens"}), \
             mock.patch.dict(os.environ, {"COROS_REGION": "cn"}, clear=False):
            coros_sync.sync_profile_json(base_dir=self.base_dir, region="eu")
            self.assertEqual(os.environ.get("COROS_REGION"), "cn")
            self.assertNotEqual(os.environ.get("QCLAW_CLI_NODE_BINARY"), "/tmp/node")
            self.assertNotEqual(os.environ.get("COROS_MCP_TOKEN_ROOT"), "/tmp/coros-tokens")

    def test_sync_profile_json_frozen_windows_does_not_launch_app_executable(self):
        payload = [{"metric": "username", "value": "coros-user"}]
        script = self.scripts_dir / "coros_runner_profile.py"
        script.write_text(f"def build_profile():\n    return {payload!r}\n", encoding="utf-8")
        app_exe = self.base_dir / "FitVault.exe"
        app_exe.write_text("", encoding="utf-8")

        with self._auth_available_patch(), \
             mock.patch.object(coros_sync.sys, "frozen", True, create=True), \
             mock.patch.object(coros_sync.sys, "executable", str(app_exe)), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=AssertionError("profile sync must not launch sys.executable")):
            parsed = coros_sync.sync_profile_json(base_dir=self.base_dir)

        self.assertEqual(parsed, payload)

    def test_run_coros_mcp_tool_returns_text_content_for_non_json_stdout(self):
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="node"), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(
                     stdout="Tool call anomalies detected. High risk of session context pollution.\n",
                     returncode=0,
                 ),
             ):
            result = coros_sync.run_coros_mcp_tool(
                "downloadActivityFitFiles",
                {"startDate": "20260622", "endDate": "20260702", "limit": 10},
                region="cn",
            )

        self.assertEqual(result["content"][0]["type"], "text")
        self.assertIn("Tool call anomalies", result["content"][0]["text"])

    def test_parse_json_stdout_accepts_markdown_fence_and_trailing_logs(self):
        stdout = (
            "[debug] keepalive connected\n"
            "```json\n"
            "{\"ok\":true,\"data\":[{\"metric\":\"username\",\"value\":\"runner\"}]}\n"
            "```\n"
            "[debug] done\n"
        )

        parsed = coros_sync._parse_json_stdout(stdout)

        self.assertEqual(parsed["ok"], True)
        self.assertEqual(parsed["data"][0]["metric"], "username")

    def test_coros_profile_runner_unwraps_keepalive_envelope_user_info(self):
        runner = load_coros_profile_runner()
        stdout = json.dumps({
            "ok": True,
            "tool": "queryUserInfo",
            "content_type": "text",
            "text": (
                "User Profile Information\n"
                "========================\n"
                "Height: 170.0 cm\n"
                "Weight: 73.8 kg\n"
                "Birthday: 1979-08-20 (Age: 46)\n"
                "Gender: Male\n"
                "Nickname: 户外大叔MrFang"
            ),
            "raw_summary": "Nickname: 户外大叔MrFang",
        }, ensure_ascii=False)

        parsed = runner.parse_user_info(stdout)

        self.assertEqual(parsed["username"], "户外大叔MrFang")
        self.assertEqual(parsed["gender"], "男")
        self.assertEqual(parsed["age"], 46)
        self.assertEqual(parsed["height_cm"], 170.0)
        self.assertEqual(parsed["weight_kg"], 73.8)
        self.assertNotIn("raw_summary", parsed["username"])

    def test_coros_profile_runner_unwraps_keepalive_envelope_json_data(self):
        runner = load_coros_profile_runner()
        stdout = json.dumps({
            "ok": True,
            "tool": "queryUserInfo",
            "content_type": "json",
            "data": {
                "nickname": "runner",
                "height": 1.71,
                "weight": 70.5,
                "gender": "male",
                "birthday": "1980-01-02",
            },
            "raw_summary": "{\"nickname\":\"runner\"}",
        }, ensure_ascii=False)

        parsed = runner.parse_user_info(stdout)

        self.assertEqual(parsed["username"], "runner")
        self.assertEqual(parsed["height_cm"], 171.0)
        self.assertEqual(parsed["weight_kg"], 70.5)
        self.assertEqual(parsed["gender"], "男")

    def test_run_coros_mcp_tool_unwraps_keepalive_envelope_data(self):
        stdout = json.dumps({
            "ok": True,
            "tool": "queryUserInfo",
            "content_type": "json",
            "data": {"nickname": "runner"},
            "raw_summary": "{\"nickname\":\"runner\"}",
        })
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="node"), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout, returncode=0)):
            result = coros_sync.run_coros_mcp_tool("queryUserInfo", {}, region="cn")

        self.assertEqual(result, {"nickname": "runner"})

    def test_run_coros_mcp_tool_error_envelope_raises_stable_error(self):
        stdout = json.dumps({
            "ok": False,
            "tool": "queryUserInfo",
            "error": {"message": "tool failed authorization Bearer abc123"},
            "raw_summary": "authorization Bearer abc123",
        })
        with mock.patch.object(coros_sync, "discover_node_binary", return_value="node"), \
             mock.patch.object(coros_sync, "build_coros_runtime_env", return_value={}), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stdout=stdout, returncode=0)):
            with self.assertRaises(coros_sync.CorosFitDownloadError) as ctx:
                coros_sync.run_coros_mcp_tool("queryUserInfo", {}, region="cn")

        self.assertEqual(ctx.exception.code, "coros_mcp_tool_failed")
        normalized = coros_sync.normalize_coros_error(ctx.exception, {"operation": "download_fit", "failed_tool_name": "queryUserInfo"})
        self.assertEqual(normalized["provider_error_code"], "coros_mcp_tool_failed")
        self.assertNotIn("abc123", json.dumps(normalized, ensure_ascii=False))

    def test_extract_download_error_summary_detects_daily_limit_and_redacts(self):
        summary = {
            "errors": [
                {
                    "status": "failed",
                    "error": "Daily FIT download limit reached Authorization: Bearer abc123 access_token=secret",
                }
            ]
        }

        extracted = coros_sync.extract_download_error_summary(summary)

        serialized = json.dumps(extracted, ensure_ascii=False)
        self.assertEqual(extracted["provider_error_code"], "coros_fit_daily_download_limit")
        self.assertIn("Daily FIT download limit reached", extracted["provider_detail"])
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("secret", serialized)

    def test_extract_download_error_summary_detects_chinese_limit_and_nested_envelope(self):
        envelope = json.dumps({
            "ok": False,
            "error": {"message": "今日 FIT 下载次数已达上限，请明日再试"},
            "raw_summary": "fallback",
        }, ensure_ascii=False)

        extracted = coros_sync.extract_download_error_summary({"errors": [{"error": envelope}]})

        self.assertEqual(extracted["provider_error_code"], "coros_fit_daily_download_limit")
        self.assertIn("今日 FIT 下载次数已达上限", extracted["provider_detail"])

    def test_extract_download_error_summary_keeps_generic_fit_failure(self):
        extracted = coros_sync.extract_download_error_summary({
            "errors": [{"status": "failed", "error": "未返回 FIT blob 或下载 URL"}]
        })

        self.assertEqual(extracted["provider_error_code"], "coros_fit_download_failed")
        self.assertIn("未返回 FIT blob", extracted["provider_detail"])

    def test_extract_sport_records_accepts_markdown_chinese_and_snake_case(self):
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "- 户外跑步 - 2026-07-01\n"
                        "  label_id：478587344962748420\n"
                        "  sport_type：100\n"
                        "- Ride - 2026-07-02 labelId: abc-2 SportType: 200\n"
                    ),
                }
            ]
        }

        records = coros_sync._extract_sport_records(payload, limit=10)

        self.assertEqual(records[0]["labelId"], "478587344962748420")
        self.assertEqual(records[0]["sportType"], 100)
        self.assertEqual(records[1]["labelId"], "abc-2")
        self.assertEqual(records[1]["sportType"], 200)

    def test_run_coros_mcp_tool_passes_unified_token_env(self):
        token_root = self.base_dir / "mcp-tokens"
        with mock.patch.dict(os.environ, {"COROS_MCP_TOKEN_ROOT": str(token_root)}), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="node"), \
             mock.patch.object(
                 coros_sync.subprocess,
                 "run",
                 return_value=self._completed(stdout='{"ok":true}', returncode=0),
             ) as run_mock:
            coros_sync.run_coros_mcp_tool("queryUserInfo", {}, region="eu")

        self.assertEqual(run_mock.call_args.kwargs["env"]["COROS_MCP_TOKEN_ROOT"], str(token_root.resolve()))

    def test_run_coros_mcp_tool_oserror_maps_to_node_missing_and_redacts(self):
        command = ["/tmp/FitVault Node/node", str(self.scripts_dir / "coros-mcp-keepalive.js"), "call"]
        with mock.patch.object(coros_sync, "_coros_mcp_command", return_value=command), \
             mock.patch.object(coros_sync.subprocess, "run", side_effect=FileNotFoundError("node missing password=secret access_token=abc123")):
            with self.assertRaises(coros_sync.CorosFitDownloadError) as ctx:
                coros_sync.run_coros_mcp_tool("queryUserInfo", {}, region="cn")

        self.assertEqual(ctx.exception.code, "coros_node_missing")
        normalized = coros_sync.normalize_coros_error(ctx.exception, {"operation": "download_fit", "region": "cn"})
        serialized = json.dumps(normalized, ensure_ascii=False)
        self.assertEqual(normalized["provider_error_code"], "coros_node_missing")
        self.assertIn("Node.js", normalized["message"])
        self.assertNotIn("secret", serialized)
        self.assertNotIn("abc123", serialized)

    def test_run_coros_mcp_tool_session_not_found_maps_to_mcp_unavailable(self):
        command = ["/tmp/node", str(self.scripts_dir / "coros-mcp-keepalive.js"), "call"]
        stderr = "Session not found\nError: stackTrace access_token=abc123 refresh_token=def456"
        with mock.patch.object(coros_sync, "_coros_mcp_command", return_value=command), \
             mock.patch.object(coros_sync.subprocess, "run", return_value=self._completed(stderr=stderr, returncode=1)):
            with self.assertRaises(coros_sync.CorosFitDownloadError) as ctx:
                coros_sync.run_coros_mcp_tool("downloadActivityFitFiles", {}, region="cn")

        self.assertEqual(ctx.exception.code, "coros_mcp_unavailable")
        normalized = coros_sync.normalize_coros_error(ctx.exception, {"failed_tool_name": "downloadActivityFitFiles"})
        serialized = json.dumps(normalized, ensure_ascii=False)
        self.assertEqual(normalized["provider_error_code"], "coros_mcp_unavailable")
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("def456", serialized)

    def test_normalize_coros_error_redacts_nested_diagnostics_and_truncates(self):
        noisy = "Traceback\n" + ("stack line\n" * 200) + "cookie=session-secret password=pw123"
        exc = coros_sync.CorosSyncError(noisy, code="coros_keepalive_invalid")

        normalized = coros_sync.normalize_coros_error(
            exc,
            {
                "operation": "check_auth_status",
                "region": "cn",
                "token_path": str(self.base_dir / "tokens" / "cn" / "token.json"),
                "access_token": "should-not-return",
            },
        )

        serialized = json.dumps(normalized, ensure_ascii=False)
        self.assertEqual(normalized["provider_error_code"], "coros_keepalive_invalid")
        self.assertIn("token.json", serialized)
        self.assertNotIn("session-secret", serialized)
        self.assertNotIn("pw123", serialized)
        self.assertNotIn("should-not-return", serialized)
        self.assertLess(len(normalized["diagnostics"]["error_summary"]), 900)

    def test_normalize_coros_profile_plain_exception_is_not_unknown(self):
        exc = RuntimeError("ordinary parser crash access_token=abc123")

        normalized = coros_sync.normalize_coros_error(
            exc,
            {"operation": "fetch_mcp_persona", "region": "cn", "raw_stdout_summary": "password=secret"},
        )

        serialized = json.dumps(normalized, ensure_ascii=False)
        self.assertEqual(normalized["provider_error_code"], "coros_profile_sync_failed")
        self.assertEqual(normalized["diagnostics"]["raw_stdout_summary"], "[redacted]")
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("secret", serialized)

    def test_profile_backend_coros_plain_exception_payload_is_normalized(self):
        import profile_backend

        payload = profile_backend._provider_failure_payload(
            "coros",
            RuntimeError("plain crash access_token=abc123"),
            "COROS 画像同步失败。",
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["provider_error_code"], "coros_profile_sync_failed")
        self.assertIn("diagnostics", payload)
        self.assertNotIn("abc123", serialized)

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
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", return_value=payload) as tool_mock:
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

    def test_download_fit_json_stops_before_mcp_when_auth_missing(self):
        with mock.patch.object(coros_sync, "ensure_auth_available", side_effect=coros_sync.CorosAuthRequiredError("missing")), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=AssertionError("MCP tool should not run")):
            with self.assertRaises(coros_sync.CorosAuthRequiredError):
                coros_sync.download_fit_json(
                    start_date="2026-05-01",
                    end_date="2026-05-31",
                    output_dir=self.base_dir / "tracks",
                    region="cn",
                )

    def test_download_fit_json_falls_back_to_url_tool_when_binary_has_no_files(self):
        payloads = [
            {"content": [{"type": "text", "text": "no binary resources"}]},
            {"content": [{"type": "text", "text": json.dumps({"urls": ["https://example.com/a.fit"]})}]},
        ]
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads) as tool_mock, \
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
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads) as tool_mock:
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

    def test_download_fit_json_tolerates_text_mcp_outputs(self):
        sport_records_text = (
            "Sport Records — 2026-06-22 to 2026-07-02 (1 records)\n"
            "========================\n\n"
            "1. Outdoor Run — 2026-07-01\n"
            "   LabelId: 478587344962748420 | SportType: 100\n"
        )
        payloads = [
            "Tool call anomalies detected. High risk of session context pollution.",
            "Tool call anomalies detected. High risk of session context pollution.",
            sport_records_text,
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
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads):
            result = coros_sync.download_fit_json(
                start_date="2026-06-22",
                end_date="2026-07-02",
                output_dir=self.base_dir / "tracks",
                region="cn",
                limit=10,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["strategy"], "sport_records_binary")
        self.assertEqual(result["downloaded"], 1)
        self.assertEqual(result["searched"], 1)

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
        with self._auth_available_patch(), \
             mock.patch.object(coros_sync, "run_coros_mcp_tool", side_effect=payloads):
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
