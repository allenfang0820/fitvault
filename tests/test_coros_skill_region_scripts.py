import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "coros-stats" / "scripts" / "coros-mcp-keepalive.js"
RUNNER = ROOT / "skills" / "coros-stats" / "scripts" / "coros_runner_profile.py"
INSTALLER = ROOT / "skills" / "coros-stats" / "scripts" / "install_coros_mcp.sh"


class TestCorosSkillRegionScriptStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keepalive_source = SCRIPT.read_text(encoding="utf-8")
        cls.runner_source = RUNNER.read_text(encoding="utf-8")
        cls.installer_source = INSTALLER.read_text(encoding="utf-8")

    def test_keepalive_declares_all_region_endpoints(self):
        self.assertIn("REGION_CONFIG", self.keepalive_source)
        self.assertIn("https://mcpcn.coros.com/mcp", self.keepalive_source)
        self.assertIn("https://mcpus.coros.com/mcp", self.keepalive_source)
        self.assertIn("https://mcpeu.coros.com/mcp", self.keepalive_source)

    def test_keepalive_token_path_uses_selected_region(self):
        self.assertIn("COROS_REGION", self.keepalive_source)
        self.assertIn("process.env.COROS_REGION", self.keepalive_source)
        self.assertIn("'.coros-mcp-skill-gateway-ts', COROS_REGION, 'token.json'", self.keepalive_source)
        self.assertNotIn("'.coros-mcp-skill-gateway-ts', 'cn', 'token.json'", self.keepalive_source)

    def test_keepalive_supports_cli_region_and_safe_config_print(self):
        self.assertIn("--region", self.keepalive_source)
        self.assertIn("--print-config", self.keepalive_source)
        self.assertIn("不支持的 COROS 区域", self.keepalive_source)

    def test_runner_invokes_keepalive_without_hardcoded_region(self):
        self.assertIn('"node", str(KEEPALIVE), "call"', self.runner_source)
        self.assertNotIn('"--region"', self.runner_source)
        self.assertNotIn("COROS_REGION = 'cn'", self.runner_source)
        for forbidden in ("coros-url-fetch", "coros_traininghub_login", "teamcnapi", "t.coros.com"):
            self.assertNotIn(forbidden, self.runner_source)

    def test_profile_runner_declares_coros_profile_fields_used_by_provider(self):
        for field in (
            '"username"',
            '"resting_heart_rate"',
            '"max_heart_rate"',
            '"lactate_threshold_hr"',
            '"lactate_threshold_pace"',
            '"1km_pb"',
            '"5km_pb"',
            '"10km_pb"',
            '"race_predict_5k"',
            '"race_predict_10k"',
            '"race_predict_half"',
            '"race_predict_full"',
            '"avg_sleep_hours"',
            '"avg_bedtime"',
            '"hrv"',
        ):
            self.assertIn(field, self.runner_source)
        for tool in (
            "queryUserInfo",
            "queryFitnessAssessmentOverview",
            "queryRestingHeartRate",
            "querySleepHrv",
            "querySleepData",
            "querySportRecords",
        ):
            self.assertIn(tool, self.runner_source)

    def test_installer_injects_openclaw_runtime_and_keeps_login_success_nonfatal(self):
        self.assertIn("find_node_binary()", self.installer_source)
        self.assertIn("MAITU_BUNDLED_NODE_DIR", self.installer_source)
        self.assertIn("../../../node/bin/node", self.installer_source)
        self.assertIn("NPM_CONFIG_PREFIX", self.installer_source)
        self.assertIn("$HOME/.maitu/node-global", self.installer_source)
        self.assertIn("\"$HOME\"/.nvm/versions/node/*/bin/node", self.installer_source)
        self.assertIn("/opt/homebrew/bin/node", self.installer_source)
        self.assertIn("QCLAW_CLI_NODE_BINARY", self.installer_source)
        self.assertIn("QCLAW_CLI_OPENCLAW_MJS", self.installer_source)
        self.assertIn("prepare_openclaw_runtime", self.installer_source)
        self.assertIn("COROS 账号授权已成功，但 OpenClaw 注册失败或被跳过", self.installer_source)
        self.assertIn("exit 0", self.installer_source)

    def test_traininghub_helpers_are_not_part_of_coros_skill(self):
        for name in ("coros_traininghub_login.js", "coros-url-fetch.js", "start_chrome.sh"):
            self.assertFalse((ROOT / "skills" / "coros-stats" / "scripts" / name).exists())


@unittest.skipIf(shutil.which("node") is None, "node is required for COROS skill script checks")
class TestCorosSkillRegionScripts(unittest.TestCase):
    def _run_print_config(self, *args, env=None):
        with tempfile.TemporaryDirectory() as temp_home:
            cmd_env = dict(os.environ)
            cmd_env["HOME"] = temp_home
            if env:
                cmd_env.update(env)
            return subprocess.run(
                ["node", str(SCRIPT), *args, "--print-config"],
                capture_output=True,
                text=True,
                env=cmd_env,
                timeout=10,
                shell=False,
            )

    def test_keepalive_default_region_is_cn(self):
        result = self._run_print_config(env={"COROS_REGION": ""})

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["region"], "cn")
        self.assertEqual(data["mcpUrl"], "https://mcpcn.coros.com/mcp")
        self.assertTrue(data["tokenPath"].endswith("/.coros-mcp-skill-gateway-ts/cn/token.json"))

    def test_keepalive_uses_region_from_environment(self):
        result = self._run_print_config(env={"COROS_REGION": "eu"})

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["region"], "eu")
        self.assertEqual(data["mcpUrl"], "https://mcpeu.coros.com/mcp")
        self.assertTrue(data["tokenPath"].endswith("/.coros-mcp-skill-gateway-ts/eu/token.json"))

    def test_keepalive_cli_region_overrides_environment(self):
        result = self._run_print_config("--region", "us", env={"COROS_REGION": "eu"})

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["region"], "us")
        self.assertEqual(data["mcpUrl"], "https://mcpus.coros.com/mcp")
        self.assertTrue(data["tokenPath"].endswith("/.coros-mcp-skill-gateway-ts/us/token.json"))

    def test_keepalive_rejects_invalid_region_without_reading_token(self):
        result = self._run_print_config(env={"COROS_REGION": "global"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不支持的 COROS 区域", result.stderr)
        self.assertNotIn("token.json", result.stderr)

    def test_keepalive_node_syntax_is_valid(self):
        result = subprocess.run(
            ["node", "--check", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_invokes_keepalive_without_overriding_coros_region_env(self):
        spec = importlib.util.spec_from_file_location("coros_runner_profile_under_test", RUNNER)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='"Nickname: runner-user"',
            stderr="",
        )
        with mock.patch.dict(os.environ, {"COROS_REGION": "eu"}), \
             mock.patch.object(module.subprocess, "run", return_value=completed) as run_mock:
            output = module.call_keepalive("queryUserInfo", retries=1)

        self.assertEqual(output, '"Nickname: runner-user"')
        command = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(command[0], "node")
        self.assertEqual(Path(command[1]).name, "coros-mcp-keepalive.js")
        self.assertEqual(command[2:4], ["call", "queryUserInfo"])
        self.assertEqual(kwargs["env"]["COROS_REGION"], "eu")


if __name__ == "__main__":
    unittest.main()
