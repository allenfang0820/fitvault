import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import llm_backend


class TestLLMGenerateText(unittest.TestCase):
    def test_generate_text_uses_http_adapter_for_http_transport(self):
        messages = [{"role": "user", "content": "hello"}]
        config = {
            "transport": "http",
            "url": "https://example.test/v1/chat/completions",
            "api_key": "sk-test",
            "model": "gpt-test",
            "agent_id": "agent-1",
        }
        with mock.patch.object(llm_backend, "_chat_completions_http", return_value="ok") as http_mock:
            text = llm_backend.generate_text(
                config=config,
                messages=messages,
                session_id="sid-1",
                timeout=12,
            )

        self.assertEqual(text, "ok")
        http_mock.assert_called_once_with(
            url="https://example.test/v1/chat/completions",
            api_key="sk-test",
            model="gpt-test",
            messages=messages,
            session_id="sid-1",
            agent_id="agent-1",
            timeout=12,
        )

    def test_generate_text_defaults_missing_transport_to_http(self):
        with mock.patch.object(llm_backend, "_chat_completions_http", return_value="ok") as http_mock:
            text = llm_backend.generate_text(
                config={"url": "u", "model": "m"},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(text, "ok")
        self.assertEqual(http_mock.call_args.kwargs["url"], "u")
        self.assertEqual(http_mock.call_args.kwargs["model"], "m")

    def test_generate_text_cli_transport_uses_cli_runner(self):
        completed = subprocess.CompletedProcess(
            args=["codex", "exec", "prompt"],
            returncode=0,
            stdout="cli ok\n",
            stderr="",
        )
        with mock.patch.object(llm_backend, "_chat_completions_http") as http_mock:
            with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                text = llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex", "cli_timeout_sec": 45},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

        self.assertEqual(text, "cli ok")
        http_mock.assert_not_called()
        run_mock.assert_called_once()
        kwargs = run_mock.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        self.assertEqual(kwargs["timeout"], 45)
        self.assertEqual(run_mock.call_args.args[0][0:2], ["codex", "exec"])

    def test_chat_completions_remains_http_compatibility_wrapper(self):
        messages = [{"role": "user", "content": "hello"}]
        with mock.patch.object(llm_backend, "_chat_completions_http", return_value="ok") as http_mock:
            text = llm_backend.chat_completions(
                url="u",
                api_key="k",
                model="m",
                messages=messages,
                session_id="sid",
                agent_id="agent-1",
                timeout=9,
            )

        self.assertEqual(text, "ok")
        http_mock.assert_called_once_with(
            url="u",
            api_key="k",
            model="m",
            messages=messages,
            session_id="sid",
            agent_id="agent-1",
            timeout=9,
        )

    def test_serialize_messages_for_cli_preserves_role_boundaries(self):
        prompt = llm_backend.serialize_messages_for_cli([
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ])

        self.assertIn("[SYSTEM]\nsystem rules", prompt)
        self.assertIn("[USER]\nquestion", prompt)
        self.assertIn("[ASSISTANT]\nanswer", prompt)

    def test_serialize_messages_for_openclaw_cli_omits_role_markers(self):
        prompt = llm_backend.serialize_messages_for_openclaw_cli([
            {"role": "system", "content": "只回复连接成功"},
            {"role": "user", "content": "请回复连接成功"},
        ])

        self.assertEqual(prompt, "只回复连接成功\n\n请回复连接成功")
        self.assertNotIn("[SYSTEM]", prompt)
        self.assertNotIn("[USER]", prompt)

    def test_cli_nonzero_exit_raises_with_stderr_snippet(self):
        completed = subprocess.CompletedProcess(
            args=["claude"],
            returncode=2,
            stdout="",
            stderr="boom" * 400,
        )
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, r"CLI 调用失败 \(exit 2\).*boom"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "claude"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_cli_timeout_raises_runtime_error(self):
        with mock.patch.object(llm_backend.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 5)):
            with self.assertRaisesRegex(RuntimeError, "CLI 已启动但模型未在超时时间内返回"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex", "cli_timeout_sec": 5},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_cli_not_found_raises_readable_message_by_type(self):
        with mock.patch.object(llm_backend.subprocess, "run", side_effect=FileNotFoundError(2, "No such file")):
            with self.assertRaisesRegex(RuntimeError, "未找到 Codex CLI，请确认已安装或填写 CLI 路径"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_openclaw_cli_not_found_mentions_qclaw_or_path(self):
        with mock.patch.object(llm_backend.subprocess, "run", side_effect=FileNotFoundError(2, "No such file")):
            with self.assertRaisesRegex(RuntimeError, "未找到 OpenClaw CLI，请确认 QClaw 已安装或填写 CLI 路径"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "openclaw", "cli_path": "/missing/openclaw"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_openclaw_agent_unusable_error_is_readable(self):
        completed = subprocess.CompletedProcess(
            args=["openclaw"],
            returncode=2,
            stdout="",
            stderr="agent agent-missing not found",
        )
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "OpenClaw Agent 不存在或不可用"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "openclaw", "agent_id": "agent-missing"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_cli_empty_stdout_raises(self):
        completed = subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="  ", stderr="")
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "模型未返回内容"):
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

    def test_custom_cli_args_template_replaces_prompt_and_model(self):
        completed = subprocess.CompletedProcess(args=["custom"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            text = llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "custom",
                    "cli_path": "/bin/custom-ai",
                    "cli_args": "--model {model} --prompt {prompt}",
                    "cli_model": "m1",
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(text, "ok")
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "/bin/custom-ai")
        self.assertIn("m1", cmd)
        self.assertIn("[USER]\nhello", cmd)

    def test_cli_path_with_spaces_is_preserved_as_single_executable(self):
        completed = subprocess.CompletedProcess(args=["custom"], returncode=0, stdout="ok", stderr="")
        windows_path = r"C:\Program Files\OpenClaw\openclaw.exe"
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            text = llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "openclaw",
                    "cli_path": windows_path,
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(text, "ok")
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], windows_path)
        self.assertEqual(cmd[1:5], ["agent", "--agent", "main", "--timeout"])
        self.assertIn("--json", cmd)
        self.assertIn("hello", cmd)
        self.assertNotIn("[USER]\nhello", cmd)

    def test_openclaw_cli_uses_configured_agent_id(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "openclaw",
                    "agent_id": "agent-8b65944a",
                    "cli_timeout_sec": 120,
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        cmd = run_mock.call_args.args[0]
        self.assertIn("--agent", cmd)
        self.assertEqual(cmd[cmd.index("--agent") + 1], "agent-8b65944a")
        self.assertIn("--timeout", cmd)
        self.assertEqual(cmd[cmd.index("--timeout") + 1], "120")
        self.assertIn("--json", cmd)

    def test_windows_cli_run_hides_console_window(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend.sys, "platform", "win32"), \
             mock.patch.object(llm_backend.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             mock.patch.object(llm_backend.subprocess, "STARTUPINFO", None, create=True), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "openclaw"},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(run_mock.call_args.kwargs["creationflags"], 0x08000000)

    def test_openclaw_cli_empty_path_falls_back_to_qclaw_wrapper(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")

        def fake_is_file(path):
            return str(path) == "/Users/tester/Library/Application Support/QClaw/openclaw/config/bin/openclaw"

        with mock.patch.object(llm_backend.Path, "home", return_value=Path("/Users/tester")):
            with mock.patch.object(Path, "is_file", fake_is_file):
                with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                    llm_backend.generate_text(
                        config={"transport": "cli", "cli_type": "openclaw", "cli_path": ""},
                        messages=[{"role": "user", "content": "hello"}],
                        session_id="sid-1",
                    )

        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "/Users/tester/Library/Application Support/QClaw/openclaw/config/bin/openclaw")

    def test_openclaw_cli_path_accepts_qclaw_config_directory_on_windows(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        config_dir = Path("C:/Program Files/QClaw/resources/openclaw/config")
        wrapper = config_dir / "bin" / "openclaw.cmd"
        node = Path("C:/Program Files/QClaw/resources/node/node.exe")
        mjs = Path("C:/Program Files/QClaw/resources/openclaw/node_modules/openclaw/openclaw.mjs")

        def fake_is_file(path):
            return str(path) in {str(wrapper), str(node), str(mjs)}

        def fake_is_dir(path):
            return str(path) == str(config_dir)

        with mock.patch.object(Path, "is_file", fake_is_file), \
             mock.patch.object(Path, "is_dir", fake_is_dir), \
             mock.patch.object(Path, "exists", lambda path: fake_is_file(path) or fake_is_dir(path)), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            text = llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "openclaw",
                    "cli_path": str(config_dir),
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(text, "ok")
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[:2], [str(node), str(mjs)])
        self.assertIn("agent", cmd)
        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], str(node))
        self.assertEqual(env["QCLAW_CLI_OPENCLAW_MJS"], str(mjs))

    def test_openclaw_cli_empty_path_falls_back_to_windows_qclaw_wrapper(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        wrapper = Path("C:/Program Files/QClaw/resources/openclaw/config/bin/openclaw.cmd")
        node = Path("C:/Program Files/QClaw/resources/node/node.exe")

        def fake_is_file(path):
            return str(path) in {str(wrapper), str(node)}

        with mock.patch.object(Path, "is_file", fake_is_file), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "openclaw", "cli_path": ""},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(run_mock.call_args.args[0][0], str(wrapper))
        self.assertEqual(run_mock.call_args.kwargs["env"]["QCLAW_CLI_NODE_BINARY"], str(node))

    def test_openclaw_cli_finds_versioned_windows_qclaw_resources(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        qclaw_root = Path("C:/Program Files/QClaw")
        resources = qclaw_root / "v0.2.28.58" / "resources"
        wrapper = resources / "openclaw" / "config" / "bin" / "openclaw.cmd"
        node = resources / "node" / "node.exe"
        mjs = resources / "openclaw" / "openclaw.mjs"

        def fake_is_file(path):
            return str(path) in {str(wrapper), str(node), str(mjs)}

        def fake_is_dir(path):
            return str(path) == str(resources)

        def fake_glob(path, pattern):
            if str(path) == str(qclaw_root) and pattern == "v*":
                return [qclaw_root / "v0.2.28.58"]
            return []

        with mock.patch.object(Path, "home", return_value=Path("C:/Users/Allen")), \
             mock.patch.object(Path, "is_file", fake_is_file), \
             mock.patch.object(Path, "is_dir", fake_is_dir), \
             mock.patch.object(Path, "glob", fake_glob), \
             mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "openclaw", "cli_path": ""},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(run_mock.call_args.args[0][:2], [str(node), str(mjs)])
        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], str(node))
        self.assertEqual(env["QCLAW_CLI_OPENCLAW_MJS"], str(mjs))

    def test_codex_cli_empty_path_does_not_use_openclaw_wrapper(self):
        completed = subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend, "_default_openclaw_cli_path", return_value="/qclaw/openclaw"):
            with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "codex", "cli_path": ""},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

        self.assertEqual(run_mock.call_args.args[0][0], "codex")

    def test_openclaw_cli_json_output_extracts_final_assistant_text(self):
        completed = subprocess.CompletedProcess(
            args=["openclaw"],
            returncode=0,
            stdout=(
                "[proxy-bootstrap] ok\n"
                '{"result":{"finalAssistantVisibleText":"连接成功",'
                '"finalAssistantRawText":"raw"}}'
            ),
            stderr="",
        )
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed):
            text = llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "openclaw"},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertEqual(text, "连接成功")

    def test_openclaw_cli_injects_qclaw_runtime_env_when_available(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")

        def fake_is_file(path):
            return str(path) in {
                "/Applications/QClaw.app/Contents/Resources/node/node",
                "/Users/tester/Library/Application Support/QClaw/openclaw/node_modules/openclaw/openclaw.mjs",
            }

        with mock.patch.object(llm_backend.Path, "home", return_value=Path("/Users/tester")):
            with mock.patch.object(Path, "is_file", fake_is_file):
                with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                    text = llm_backend.generate_text(
                        config={
                            "transport": "cli",
                            "cli_type": "openclaw",
                            "cli_path": "/Users/tester/Library/Application Support/QClaw/openclaw/config/bin/openclaw",
                        },
                        messages=[{"role": "user", "content": "hello"}],
                        session_id="sid-1",
                    )

        self.assertEqual(text, "ok")
        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "/Applications/QClaw.app/Contents/Resources/node/node")
        self.assertEqual(
            env["QCLAW_CLI_OPENCLAW_MJS"],
            "/Users/tester/Library/Application Support/QClaw/openclaw/node_modules/openclaw/openclaw.mjs",
        )
        self.assertFalse(run_mock.call_args.kwargs["shell"])

    def test_openclaw_cli_injects_qclaw_launchagent_runtime_env(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        qclaw_env = {
            "OPENCLAW_STATE_DIR": "/Users/tester/.qclaw",
            "OPENCLAW_CONFIG_PATH": "/Users/tester/.qclaw/openclaw.json",
            "OPENCLAW_GATEWAY_PORT": "28789",
            "QCLAW_LLM_BASE_URL": "http://127.0.0.1:19000/proxy/llm",
            "QCLAW_LLM_API_KEY": "__QCLAW_AUTH_GATEWAY_MANAGED__",
        }
        with mock.patch.object(llm_backend, "_read_qclaw_launchagent_env", return_value=qclaw_env):
            with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "openclaw"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["OPENCLAW_STATE_DIR"], "/Users/tester/.qclaw")
        self.assertEqual(env["OPENCLAW_CONFIG_PATH"], "/Users/tester/.qclaw/openclaw.json")
        self.assertEqual(env["OPENCLAW_GATEWAY_PORT"], "28789")
        self.assertEqual(env["QCLAW_LLM_BASE_URL"], "http://127.0.0.1:19000/proxy/llm")
        self.assertEqual(env["QCLAW_LLM_API_KEY"], "__QCLAW_AUTH_GATEWAY_MANAGED__")

    def test_openclaw_cli_preserves_existing_qclaw_runtime_env(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        with mock.patch.dict(os.environ, {
            "QCLAW_CLI_NODE_BINARY": "/custom/node",
            "QCLAW_CLI_OPENCLAW_MJS": "/custom/openclaw.mjs",
        }, clear=False):
            with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                llm_backend.generate_text(
                    config={"transport": "cli", "cli_type": "openclaw"},
                    messages=[{"role": "user", "content": "hello"}],
                    session_id="sid-1",
                )

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["QCLAW_CLI_NODE_BINARY"], "/custom/node")
        self.assertEqual(env["QCLAW_CLI_OPENCLAW_MJS"], "/custom/openclaw.mjs")

    def test_openclaw_cli_preserves_existing_gateway_env_over_launchagent(self):
        completed = subprocess.CompletedProcess(args=["openclaw"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend, "_read_qclaw_launchagent_env", return_value={
            "OPENCLAW_GATEWAY_PORT": "28789",
            "QCLAW_LLM_BASE_URL": "http://127.0.0.1:19000/proxy/llm",
        }):
            with mock.patch.dict(os.environ, {
                "OPENCLAW_GATEWAY_PORT": "19999",
                "QCLAW_LLM_BASE_URL": "http://custom/proxy/llm",
            }, clear=False):
                with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
                    llm_backend.generate_text(
                        config={"transport": "cli", "cli_type": "openclaw"},
                        messages=[{"role": "user", "content": "hello"}],
                        session_id="sid-1",
                    )

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["OPENCLAW_GATEWAY_PORT"], "19999")
        self.assertEqual(env["QCLAW_LLM_BASE_URL"], "http://custom/proxy/llm")

    def test_codex_cli_does_not_receive_openclaw_env(self):
        completed = subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={"transport": "cli", "cli_type": "codex"},
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        self.assertIsNone(run_mock.call_args.kwargs["env"])

    def test_parse_last_json_object_ignores_proxy_logs(self):
        parsed = llm_backend._parse_last_json_object(
            "[proxy-bootstrap] no proxy env detected\n"
            "[proxy-bootstrap] undici global dispatcher set\n"
            '{"gateway": {"reachable": false}}'
        )

        self.assertEqual(parsed, {"gateway": {"reachable": False}})

    def test_parse_last_json_object_returns_none_without_json(self):
        self.assertIsNone(llm_backend._parse_last_json_object("[proxy-bootstrap] no json"))

    def test_diagnose_openclaw_cli_reports_gateway_port_mismatch(self):
        status = subprocess.CompletedProcess(
            args=["openclaw", "status", "--json"],
            returncode=0,
            stdout=(
                "[proxy-bootstrap] ok\n"
                '{"gateway":{"reachable":false,"url":"ws://127.0.0.1:18789"},'
                '"gatewayService":{"runtimeShort":"running (pid 85081, state active)",'
                '"layout":{"execStart":"/Applications/QClaw.app/Contents/Resources/node/node gateway --port 28789"}}}'
            ),
            stderr="",
        )
        with mock.patch.object(llm_backend.subprocess, "run", return_value=status):
            detail = llm_backend.diagnose_openclaw_cli(
                {"transport": "cli", "cli_type": "openclaw", "cli_path": "/bin/openclaw"}
            )

        self.assertIn("OpenClaw Gateway 当前不可达", detail)
        self.assertIn("18789", detail)
        self.assertIn("28789", detail)
        self.assertIn("端口不一致", detail)

    def test_diagnose_openclaw_cli_reports_missing_model_auth(self):
        status = subprocess.CompletedProcess(
            args=["openclaw", "status", "--json"],
            returncode=0,
            stdout='{"gateway":{"reachable":true}}',
            stderr="",
        )
        models = subprocess.CompletedProcess(
            args=["openclaw", "models", "status", "--json"],
            returncode=0,
            stdout=(
                '{"defaultModel":"openai/gpt-5.5",'
                '"auth":{"missingProvidersInUse":["openai"],'
                '"runtimeAuthRoutes":[{"provider":"openai","status":"missing"}]}}'
            ),
            stderr="",
        )
        with mock.patch.object(llm_backend.subprocess, "run", side_effect=[status, models]):
            detail = llm_backend.diagnose_openclaw_cli(
                {"transport": "cli", "cli_type": "openclaw", "cli_path": "/bin/openclaw"}
            )

        self.assertIn("OpenClaw 模型授权缺失", detail)
        self.assertIn("openai", detail)
        self.assertIn("openai/gpt-5.5", detail)

    def test_cli_path_rejects_command_arguments_in_path_field(self):
        with self.assertRaisesRegex(RuntimeError, "CLI 路径只能填写可执行文件路径"):
            llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "codex",
                    "cli_path": "codex exec",
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

    def test_custom_cli_args_without_prompt_appends_prompt_argument(self):
        completed = subprocess.CompletedProcess(args=["custom"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(llm_backend.subprocess, "run", return_value=completed) as run_mock:
            llm_backend.generate_text(
                config={
                    "transport": "cli",
                    "cli_type": "custom",
                    "cli_path": "/bin/custom-ai",
                    "cli_args": "--model {model}",
                    "cli_model": "m1",
                },
                messages=[{"role": "user", "content": "hello"}],
                session_id="sid-1",
            )

        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0:3], ["/bin/custom-ai", "--model", "m1"])
        self.assertEqual(cmd[-1], "[USER]\nhello")
        self.assertNotIn("{prompt}", cmd)


if __name__ == "__main__":
    unittest.main()
