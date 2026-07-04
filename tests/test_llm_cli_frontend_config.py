import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"


def extract_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"未找到函数签名: {signature}")
    brace_start = source.find("{", start + len(signature))
    if brace_start < 0:
        raise AssertionError(f"未找到函数体起始: {signature}")
    depth = 1
    index = brace_start + 1
    while index < len(source) and depth > 0:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth != 0:
        raise AssertionError(f"函数体括号不闭合: {signature}")
    return source[brace_start + 1:index - 1]


class TestLLMCliFrontendConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_settings_panel_exposes_transport_and_cli_fields(self):
        for token in (
            'id="llm-transport"',
            '<option value="http">HTTP 网关</option>',
            '<option value="cli">CLI</option>',
            'id="llm-cli-type"',
            '<option value="openclaw">OpenClaw CLI</option>',
            '<option value="codex">Codex CLI</option>',
            '<option value="claude">Claude Code</option>',
            'id="llm-agent-id-row"',
            'id="llm-agent-id-label"',
            'id="llm-cli-path"',
            'id="llm-cli-timeout"',
            'id="garmin-region"',
            '<option value="cn">Garmin 中国区</option>',
            '<option value="global">Garmin 国际区</option>',
            'id="garmin-auth-status-line"',
            'id="garmin-auth-dot"',
            'id="garmin-auth-check-btn"',
            'id="garmin-auth-login-btn"',
            'id="garmin-auth-disconnect-btn"',
            'id="garmin-account-email"',
            'id="garmin-account-password"',
            'id="garmin-account-mfa"',
            'id="coros-region"',
            '<option value="cn">COROS 中国区</option>',
            '<option value="us">COROS 北美区</option>',
            '<option value="eu">COROS 欧洲区</option>',
            'id="coros-auth-status-line"',
            'id="coros-auth-dot"',
            'id="coros-auth-check-btn"',
            'id="coros-auth-login-btn"',
            'id="coros-auth-disconnect-btn"',
            'id="account-connection-center-title"',
            "账号连接中心",
            "startGarminAuthorizationFromSettings()",
            "refreshGarminAuthStatus(true)",
            "continueGarminAuthorizationFromSettings()",
            "disconnectGarminAccountFromSettings()",
            "startCorosAuthorizationFromSettings()",
            "refreshCorosAuthStatus(true)",
            "disconnectCorosAccountFromSettings()",
            "list_account_connections",
            "check_account_connection",
            "start_account_connection",
            "continue_account_connection",
            "disconnect_account",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn("CLI 使用本机已登录的 AI 助手", self.source)
        self.assertNotIn("授权终端", self.source)

    def test_sync_config_reads_cli_fields(self):
        body = extract_function_body(self.source, "function syncLLMConfigFromFields()")
        for token in (
            "llm-transport",
            "llm-cli-type",
            "llm-cli-path",
            "llm-cli-args",
            "llm-cli-model",
            "llm-cli-timeout",
            "llm-agent-id",
            "garmin-region",
            "coros-region",
            "transport: transport",
            "agentId: agentId",
            "garminRegion: normalizeGarminRegion",
            "corosRegion: normalizeCorosRegion",
            "cliType: normalizeCLIType",
            "cliTimeoutSec: normalizeCLITimeout",
            "markLLMConfigDirtyIfNeeded()",
        ):
            self.assertIn(token, body)

    def test_frontend_tracks_dirty_llm_config_signature(self):
        signature_body = extract_function_body(self.source, "function buildLLMConfigSignature(config)")
        dirty_body = extract_function_body(self.source, "function markLLMConfigDirtyIfNeeded()")
        clean_body = extract_function_body(self.source, "function markLLMConfigClean(config)")
        test_body = extract_function_body(self.source, "async function testLLMConfig()")

        self.assertIn("savedLLMConfigSignature", self.source)
        self.assertIn("transport === 'cli'", signature_body)
        self.assertIn("cliType", signature_body)
        self.assertIn("cliPath", signature_body)
        self.assertIn("cliTimeoutSec", signature_body)
        self.assertIn("garminRegion", signature_body)
        self.assertIn("corosRegion", signature_body)
        self.assertIn("配置已修改，需重新测试", dirty_body)
        self.assertIn("buildLLMConfigSignature", clean_body)
        self.assertIn("markLLMConfigClean(currentLLMConfig)", test_body)

    def test_openclaw_cli_agent_id_row_is_only_shown_for_openclaw(self):
        render_body = extract_function_body(self.source, "function renderLLMConfigFields()")

        self.assertIn("llm-cli-openclaw-agent-row", self.source)
        self.assertIn("#panel-settings.llm-transport-cli #llm-agent-id-row.llm-cli-openclaw-agent-row", self.source)
        self.assertIn("const agentIdRow = document.getElementById('llm-agent-id-row')", render_body)
        self.assertIn("const agentIdLabel = document.getElementById('llm-agent-id-label')", render_body)
        self.assertIn("OpenClaw Agent ID（选填）", render_body)
        self.assertIn("留空则使用 main，例如 agent-8b65944a", render_body)
        self.assertIn("transport === 'cli' && normalizedCliType === 'openclaw'", render_body)

    def test_frontend_call_ready_helpers_support_cli_transport(self):
        cli_body = extract_function_body(self.source, "function isLLMTransportCLI()")
        ready_body = extract_function_body(self.source, "function isLLMReadyForFrontendCall()")

        self.assertIn("normalizeLLMTransport", cli_body)
        self.assertIn("currentLLMConfig && currentLLMConfig.transport", cli_body)
        self.assertIn("isLLMTransportCLI()", ready_body)
        self.assertIn("normalizeCLIType", ready_body)
        self.assertIn("currentLLMConfig && currentLLMConfig.cliType", ready_body)
        self.assertIn("currentLLMConfig && currentLLMConfig.url", ready_body)

    def test_ai_coach_does_not_require_http_url_for_cli_transport(self):
        body = extract_function_body(self.source, "async function sendAICoachMessage()")

        self.assertNotIn("if (!currentLLMConfig.url)", body)
        self.assertIn("isLLMReadyForFrontendCall()", body)
        self.assertIn("isLLMTransportCLI()", body)
        self.assertIn("CLI 尚未配置", body)
        self.assertIn("API 接口地址为空", body)

    def test_activity_advice_does_not_require_http_url_for_cli_transport(self):
        body = extract_function_body(self.source, "async function requestActivityAdvice()")

        self.assertNotIn("if (!currentLLMConfig.url)", body)
        self.assertIn("isLLMReadyForFrontendCall()", body)
        self.assertIn("isLLMTransportCLI()", body)
        self.assertIn("CLI 尚未配置", body)
        self.assertIn("请先在配置中填写 API 地址", body)

    def test_test_llm_config_passes_cli_contract_to_backend(self):
        body = extract_function_body(self.source, "async function testLLMConfig()")
        self.assertIn("transport === 'cli'", body)
        self.assertIn("cliType === 'custom' && !cliPath", body)
        self.assertIn("window.pywebview.api.test_llm_config(", body)
        self.assertIn("transport,", body)
        self.assertIn("cliType,", body)
        self.assertIn("cliPath,", body)
        self.assertIn("cliArgs,", body)
        self.assertIn("cliModel,", body)
        self.assertIn("cliTimeoutSec", body)
        self.assertIn("garminRegion", body)
        self.assertIn("corosRegion", body)
        self.assertIn("agentId,", body)
        self.assertNotIn("transport === 'cli' ? '' : agentId", body)

        cli_branch = body[body.find("if (transport === 'cli')"):body.find("} else if (!model || !url)")]
        self.assertNotIn("!model || !url", cli_branch)

    def test_silent_validation_and_heartbeat_do_not_ping_http_gateway_for_cli(self):
        silent_body = extract_function_body(self.source, "function runSilentGatewayValidation()")
        heartbeat_body = extract_function_body(self.source, "function startLLMHeartbeat()")

        self.assertIn("transport === 'cli'", silent_body)
        self.assertIn("'cli'", silent_body)
        self.assertIn("res.data.cli_type", silent_body)
        self.assertIn("res.data.agent_id || ''", silent_body)
        self.assertIn("静默验证大模型连接中", silent_body)
        self.assertIn("isBackendLLMConfigStillCurrent(res.data)", silent_body)
        self.assertIn("!backendConfigMatchesForm", silent_body)
        self.assertIn("!isCurrentLLMConfigDirty()", silent_body)
        self.assertIn("stopLLMHeartbeat()", silent_body)
        self.assertIn("normalizeLLMTransport(currentLLMConfig && currentLLMConfig.transport) === 'cli'", heartbeat_body)
        self.assertIn("stopLLMHeartbeat();", heartbeat_body)

        generic_status_idx = silent_body.find("静默验证大模型连接中")
        http_status_idx = silent_body.find("静默验证网关连接中")
        cli_branch_idx = silent_body.find("transport === 'cli'")
        self.assertGreaterEqual(generic_status_idx, 0)
        self.assertGreater(http_status_idx, cli_branch_idx)

    def test_frontend_persists_garmin_region_selection(self):
        persist_body = extract_function_body(self.source, "function persistGarminRegionSelection()")
        render_body = extract_function_body(self.source, "function renderLLMConfigFields()")
        select_body = extract_function_body(self.source, "function selectUserType(type)")

        self.assertIn("set_garmin_region", persist_body)
        self.assertIn("normalizeGarminRegion", persist_body)
        self.assertIn("refreshGarminAuthStatus", persist_body)
        self.assertIn("garmin-region-row", render_body)
        self.assertIn("watchBrand === 'garmin' ? 'flex' : 'none'", render_body)
        self.assertIn("refreshGarminAuthStatus", render_body)
        self.assertIn("garmin-region-row", select_body)
        self.assertIn("type === 'garmin' ? 'flex' : 'none'", select_body)
        self.assertIn("refreshGarminAuthStatus", select_body)

    def test_frontend_persists_coros_region_selection(self):
        persist_body = extract_function_body(self.source, "function persistCorosRegionSelection()")
        render_body = extract_function_body(self.source, "function renderLLMConfigFields()")
        select_body = extract_function_body(self.source, "function selectUserType(type)")

        self.assertIn("set_coros_region", persist_body)
        self.assertIn("normalizeCorosRegion", persist_body)
        self.assertIn("refreshCorosAuthStatus", persist_body)
        self.assertIn("coros-region-row", render_body)
        self.assertIn("watchBrand === 'coros' ? 'flex' : 'none'", render_body)
        self.assertIn("refreshCorosAuthStatus", render_body)
        self.assertIn("coros-region-row", select_body)
        self.assertIn("type === 'coros' ? 'flex' : 'none'", select_body)
        self.assertIn("refreshCorosAuthStatus", select_body)


if __name__ == "__main__":
    unittest.main()
