import ast
import json
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import coros_sync
import garmin_sync
import llm_backend
import subprocess_utils
from main import Api


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = None


def _called_names(fn) -> list[str]:
    tree = ast.parse(textwrap.dedent(__import__("inspect").getsource(fn)))
    calls: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):  # noqa: N802 - unittest helper
            calls.append(self._name(node.func))
            self.generic_visit(node)

        def _name(self, node):
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                parent = self._name(node.value)
                return f"{parent}.{node.attr}" if parent else node.attr
            return ""

    Visitor().visit(tree)
    return calls


class TestWindowsRegressionMatrix(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir_obj.name)
        self.coros_scripts = self.base_dir / "skills" / "coros-stats" / "scripts"
        self.coros_scripts.mkdir(parents=True)
        for name in ("coros_runner_profile.py", "install_coros_mcp.sh", "install_coros_mcp.cmd"):
            (self.coros_scripts / name).write_text("# test script\n", encoding="utf-8")
        self.garmin_scripts = self.base_dir / "skills" / "garmin-stats" / "scripts"
        self.garmin_scripts.mkdir(parents=True)
        for name in ("get_garmin_stats.py", "download_fit.py", "login.py"):
            (self.garmin_scripts / name).write_text("# test script\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def _completed(self, stdout="ok", stderr="", returncode=0):
        return subprocess.CompletedProcess(args=["tool"], returncode=returncode, stdout=stdout, stderr=stderr)

    def test_a_windows_subprocess_helper_hides_console_and_keeps_argv(self):
        command = [r"C:\Program Files\FitVault Tools\node.exe", "--version"]
        with mock.patch.object(subprocess_utils.os, "name", "nt"), \
             mock.patch.object(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "SW_HIDE", 0, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "run", return_value=self._completed()) as run_mock:
            subprocess_utils.run_hidden(command, text=True, creationflags=0x00000008)

        self.assertEqual(run_mock.call_args.args[0], command)
        self.assertFalse(run_mock.call_args.kwargs["shell"])
        self.assertEqual(run_mock.call_args.kwargs["creationflags"], 0x08000008)
        self.assertIsInstance(run_mock.call_args.kwargs["startupinfo"], FakeStartupInfo)

    def test_a_macos_subprocess_helper_does_not_inject_windows_flags(self):
        with mock.patch.object(subprocess_utils.os, "name", "posix"), \
             mock.patch.object(subprocess_utils.subprocess, "run", return_value=self._completed()) as run_mock:
            subprocess_utils.run_hidden(["/usr/local/bin/codex", "--version"])

        self.assertFalse(run_mock.call_args.kwargs["shell"])
        self.assertNotIn("creationflags", run_mock.call_args.kwargs)
        self.assertNotIn("startupinfo", run_mock.call_args.kwargs)

    def test_b_codex_windows_discovery_matrix_and_macos_guard(self):
        completed = self._completed(stdout="连接成功")

        with mock.patch.object(llm_backend.sys, "platform", "win32"), \
             mock.patch.object(llm_backend.shutil, "which", side_effect=lambda name: r"C:\Tools\codex.cmd" if name == "codex.cmd" else None), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex", "cli_path": ""},
                messages=[{"role": "user", "content": "hi"}],
                session_id="sid",
            )
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[:6], ["cmd.exe", "/d", "/c", r"C:\Tools\codex.cmd", "exec", "--skip-git-repo-check"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])

        with tempfile.TemporaryDirectory() as appdata, \
             mock.patch.object(llm_backend.sys, "platform", "win32"), \
             mock.patch.object(llm_backend.shutil, "which", return_value=None), \
             mock.patch.dict(llm_backend.os.environ, {"APPDATA": appdata}, clear=False), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            npm_dir = Path(appdata) / "npm"
            npm_dir.mkdir()
            (npm_dir / "codex.cmd").write_text("", encoding="utf-8")
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex"},
                messages=[{"role": "user", "content": "hi"}],
                session_id="sid",
            )
        self.assertEqual(run_mock.call_args.args[0][:4], ["cmd.exe", "/d", "/c", str(Path(appdata) / "npm" / "codex.cmd")])

        with mock.patch.object(llm_backend.sys, "platform", "darwin"), \
             mock.patch.object(llm_backend.shutil, "which") as which_mock, \
             mock.patch.dict(llm_backend.os.environ, {"APPDATA": r"C:\Users\Allen\AppData\Roaming"}, clear=False), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex"},
                messages=[{"role": "user", "content": "hi"}],
                session_id="sid",
            )
        self.assertEqual(run_mock.call_args.args[0][0], "codex")
        which_mock.assert_not_called()

    def test_b_codex_not_found_message_is_codex_specific(self):
        with mock.patch.object(llm_backend.subprocess, "run", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(RuntimeError) as ctx:
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex"},
                    messages=[{"role": "user", "content": "hi"}],
                    session_id="sid",
                )

        self.assertIn("未找到 Codex CLI", str(ctx.exception))
        self.assertNotIn("OpenClaw", str(ctx.exception))
        self.assertNotIn("QClaw", str(ctx.exception))

    def test_c_cli_test_connection_same_config_is_single_flight(self):
        api = Api()
        started = threading.Event()
        release = threading.Event()
        results = {}

        def slow_generate_text(**kwargs):
            started.set()
            release.wait(timeout=3)
            return "连接成功"

        with mock.patch.object(llm_backend, "generate_text", side_effect=slow_generate_text) as generate_mock, \
             mock.patch.object(llm_backend, "save_llm_config") as save_mock:
            first = threading.Thread(
                target=lambda: results.setdefault(
                    "first",
                    api.test_llm_config("cli_codex", "", "", "", "", "", "cli", "codex", "", "", "", 300),
                )
            )
            first.start()
            self.assertTrue(started.wait(timeout=2))
            second = api.test_llm_config("cli_codex", "", "", "", "", "", "cli", "codex", "", "", "", 300)
            release.set()
            first.join(timeout=3)

        self.assertFalse(second["ok"], second)
        self.assertIn("正在进行", second["msg"])
        self.assertEqual(generate_mock.call_count, 1)
        save_mock.assert_called_once()
        self.assertTrue(results["first"]["ok"], results["first"])

    def test_d_garmin_windows_source_error_is_incompatible_and_redacted(self):
        class AuthModule:
            @staticmethod
            def login_and_save_app(**kwargs):
                raise RuntimeError(
                    "could not get source code password=secret "
                    "access_token=abc refresh_token=def cookie=session api_key=k"
                )

        with mock.patch.object(garmin_sync.sys, "platform", "win32"), \
             mock.patch.object(garmin_sync.sys, "frozen", True, create=True), \
             mock.patch.object(garmin_sync, "_load_skill_module", return_value=AuthModule), \
             mock.patch.object(garmin_sync, "start_login") as terminal_login:
            result = garmin_sync.login_app(
                email="runner@example.com",
                password="secret",
                region="cn",
                base_dir=self.base_dir,
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.provider_error_code, "garmin_provider_api_incompatible")
        self.assertEqual(result.diagnostics, {"provider": "garmin", "cause": "packaged_callback_source_unavailable"})
        terminal_login.assert_not_called()
        serialized = str(result)
        for secret in ("could not get source code", "secret", "abc", "def", "session", "api_key", "runner@example.com"):
            self.assertNotIn(secret, serialized)

    def test_d_garmin_macos_app_login_success_remains_in_process(self):
        class AuthModule:
            @staticmethod
            def login_and_save_app(**kwargs):
                return kwargs["tokenstore"]

        with mock.patch.object(garmin_sync.sys, "platform", "darwin"), \
             mock.patch.object(garmin_sync, "_load_skill_module", return_value=AuthModule), \
             mock.patch.object(garmin_sync, "start_login") as terminal_login:
            result = garmin_sync.login_app(
                email="runner@example.com",
                password="secret",
                region="global",
                base_dir=self.base_dir,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "authorized")
        self.assertEqual(result.region, "global")
        terminal_login.assert_not_called()

    def test_e_coros_token_node_status_preflight_matrix(self):
        token_root = self.base_dir / "Coros Tokens"
        token_path = token_root / "cn" / "token.json"
        token_path.parent.mkdir(parents=True)
        token_path.write_text("secret token content must not be read", encoding="utf-8")
        node_path = str(self.base_dir / "Bundled Node" / "node.exe")

        def fake_print_config(paths, region, timeout=5, node_binary="node", token_root=None):
            expected = str(coros_sync.default_mcp_token_path(region, token_root))
            return region, "https://mcpcn.coros.com", expected, {
                "name": "keepalive_config",
                "status": "ok",
                "message": "ok",
            }

        with mock.patch.object(coros_sync.sys, "platform", "win32"), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value=node_path), \
             mock.patch.object(coros_sync, "_run_keepalive_print_config", side_effect=fake_print_config), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("token content must not be read")):
            status = coros_sync.check_auth_status(base_dir=self.base_dir, region="cn", token_root=token_root)
            preflight = coros_sync.ensure_auth_available(base_dir=self.base_dir, region="cn", token_root=token_root)

        self.assertTrue(status.ok)
        self.assertEqual(preflight.status, "authorized")
        self.assertEqual(Path(status.token_path), token_path)
        self.assertEqual(status.keepalive_token_path, str(token_path))
        self.assertEqual(status.node_path, node_path)

        with mock.patch.object(coros_sync, "discover_node_binary", return_value=""):
            with self.assertRaises(coros_sync.CorosSyncError) as ctx:
                coros_sync.ensure_auth_available(base_dir=self.base_dir, region="cn", token_root=token_root)
        self.assertEqual(ctx.exception.code, "coros_node_missing")

    def test_e_coros_runtime_prefers_qclaw_node_and_macos_home_stays_unmodified(self):
        qclaw_node = str(self.base_dir / "QClaw Runtime" / "node.exe")
        with mock.patch.dict(coros_sync.os.environ, {"QCLAW_CLI_NODE_BINARY": qclaw_node}, clear=False), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(coros_sync.os, "access", return_value=True), \
             mock.patch.object(coros_sync.shutil, "which", return_value=r"C:\Windows\node.exe"):
            self.assertEqual(coros_sync.discover_node_binary(), qclaw_node)

        with mock.patch.object(coros_sync.sys, "platform", "darwin"), \
             mock.patch.object(coros_sync, "discover_node_binary", return_value="/opt/homebrew/bin/node"), \
             mock.patch.object(coros_sync, "discover_openclaw_mjs", return_value=""):
            env = coros_sync.build_coros_runtime_env(
                {"HOME": "/Users/runner", "PATH": "/usr/bin"},
                token_root=self.base_dir / "tokens",
            )

        self.assertEqual(env["HOME"], "/Users/runner")
        self.assertNotIn("USERPROFILE", env)
        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "/opt/homebrew/bin/node")

    def test_f_error_normalization_redacts_sensitive_fields(self):
        payload = coros_sync.normalize_coros_error(
            coros_sync.CorosFitDownloadError(
                "Traceback stackTrace password=secret mfa_code=123456 "
                "access_token=abc refresh_token=def cookie=session api_key=k",
                code="coros_mcp_unavailable",
            ),
            {
                "operation": "download_fit",
                "region": "cn",
                "token_path": str(self.base_dir / "tokens" / "cn" / "token.json"),
            },
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        for secret in ("secret", "123456", "abc", "def", "session", "api_key", "Traceback"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(payload["provider_error_code"], "coros_mcp_unavailable")

    def test_g_data_sync_and_auth_do_not_use_llm_transport(self):
        sync_calls = _called_names(Api.sync_remote_fit_activities)
        start_calls = _called_names(Api.start_account_connection)
        continue_calls = _called_names(Api.continue_account_connection)

        self.assertIn("garmin_sync.download_fit_json", sync_calls)
        self.assertIn("coros_sync.download_fit_json", sync_calls)
        for calls in (sync_calls, start_calls, continue_calls):
            self.assertNotIn("llm_backend.generate_text", calls)
            self.assertNotIn("llm_backend.chat_completions", calls)
            self.assertNotIn("self._generate_llm_text", calls)


if __name__ == "__main__":
    unittest.main()
