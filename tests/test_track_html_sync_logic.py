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


def extract_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise AssertionError(f"未找到起始标记: {start_marker}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise AssertionError(f"未找到结束标记: {end_marker}")
    return source[start:end]


class TestTrackHtmlSyncLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TRACK_HTML_PATH.read_text(encoding="utf-8")

    def test_page_size_change_does_not_trigger_sync(self):
        body = extract_function_body(self.source, "async function onSportHubPageSizeChange()")
        self.assertNotIn("syncAndLoadSportHubRecords", body)
        self.assertNotIn("sync_local_fit_files", body)
        self.assertIn("refreshSnapshot: false", body)
        self.assertIn("loadSportHubActivityList", body)

    def test_local_pagination_short_circuits_without_refreshing_snapshot(self):
        body = extract_function_body(self.source, "async function loadSportHubActivityList(options = {})")
        self.assertIn("const forceRefresh = options.refreshSnapshot !== false && (!!options.refreshSnapshot || !sportHubState.recordsReady);", body)
        self.assertIn("if (!forceRefresh &&", body)
        local_branch = body[body.find("if (!forceRefresh &&"):body.find("sportHubState.recordsLoading = true;")]
        self.assertIn("applySportHubRecordFilters(resetPage);", local_branch)
        self.assertIn("renderSportHubRecords();", local_branch)
        self.assertIn("renderCurrentSportHubTab();", local_branch)
        self.assertNotIn("recordsLoading = true", local_branch)
        self.assertIn("get_activity_list_snapshot", body)

    def test_sync_job_has_failure_timeout_and_state_reset(self):
        poll_body = extract_function_body(self.source, "async function pollSportHubSyncJob(jobId)")
        self.assertIn("timeoutMs", poll_body)
        self.assertIn("['failed', 'error', 'cancelled', 'timeout']", poll_body)
        sync_body = extract_function_body(self.source, "async function syncAndLoadSportHubRecords(options = {})")
        self.assertNotIn("if (sportHubState.activeTab === 'records') renderSportHubRecords()", sync_body)
        self.assertIn("sportHubState.recordsSyncing = false;", sync_body)
        self.assertIn("sportHubState.recordsLoading = false;", sync_body)
        self.assertIn("sportHubState.syncPromise = null;", sync_body)

    def test_filter_change_does_not_trigger_sync(self):
        body = extract_function_body(self.source, "function onSportHubFilterChange()")
        self.assertNotIn("syncAndLoadSportHubRecords", body)
        self.assertNotIn("sync_local_fit_files", body)
        self.assertIn("refreshSnapshot: false", body)
        self.assertIn("loadSportHubActivityList", body)

    def test_sport_type_filter_matches_display_type_key(self):
        body = extract_function_body(self.source, "function applySportHubRecordFilters(resetPage = false)")
        self.assertIn("sportHubRecordTypeKey(record)", body)
        self.assertNotIn("String(record.sport_type || '') === filterType", body)

    def test_snapshot_refresh_re_renders_records_after_filtering(self):
        body = extract_function_body(self.source, "async function loadSportHubActivityList(options = {})")
        finally_branch = body[body.find("} finally {"):body.rfind("}")]
        self.assertIn("renderSportHubFilterOptions();", finally_branch)
        self.assertIn("renderSportHubRecords();", finally_branch)
        self.assertNotIn("if (sportHubState.activeTab === 'records')", finally_branch)

    def test_activity_detail_renders_weather_card_and_syncs_weather_context(self):
        self.assertIn("🌦 历史天气", self.source)
        self.assertIn("活动发生时段的历史环境快照", self.source)
        self.assertIn("setCurrentWeather(data.weather || null);", self.source)
        self.assertIn("weather: appState.currentWeather", self.source)
        self.assertIn("setCurrentWeather((res.data && res.data.weather) || (res.activity && res.activity.weather) || null);", self.source)

    def test_ai_report_uses_dynamic_sport_labels_instead_of_fixed_hiking(self):
        self.assertIn("function getDynamicSportMeta(typeStr)", self.source)
        self.assertIn("getDynamicSportMeta(data.sport_type)", self.source)
        self.assertIn("getDynamicSportMeta(sportType)", self.source)

    def test_activity_records_support_selection_and_batch_delete(self):
        self.assertIn("selectedIds: new Set()", self.source)
        self.assertIn("sport-records-select-all", self.source)
        self.assertIn("function toggleSportHubRecordSelection", self.source)
        self.assertIn("function deleteSelectedSportHubRecords", self.source)
        self.assertIn("delete_activities", self.source)

    def test_acs_career_has_first_level_navigation_and_shell(self):
        self.assertIn('class="bookmark-tab" data-panel="career"', self.source)
        self.assertIn('<span class="tab-label">运动生涯</span>', self.source)
        self.assertIn('id="panel-career" class="tab-panel"', self.source)
        self.assertIn('data-acs-shell="phase0"', self.source)

        switch_body = extract_function_body(self.source, "function switchTab(tabBtn)")
        self.assertIn("['profile', 'career', 'trace', 'settings', 'help', 'about']", switch_body)

        career_panel = extract_between(
            self.source,
            '<div id="panel-career" class="tab-panel">',
            '<!-- ========== 【轨迹分析工具】面板 ========== -->',
        )
        self.assertIn('data-career-section="overview"', career_panel)
        self.assertIn('data-career-section="timeline"', career_panel)
        self.assertIn('data-career-section="archives"', career_panel)
        self.assertIn('每个节点都必须携带 activity_id', career_panel)
        for forbidden in ("window.pywebview.api", "points", "track_json", "raw FIT", "get_career_"):
            self.assertNotIn(forbidden, career_panel)

    def test_legacy_honor_wall_is_career_entry_not_acs_primary_surface(self):
        self.assertIn('data-hub-tab="honors" onclick="switchSportHubTab(\'honors\')">运动生涯入口</button>', self.source)
        self.assertIn('data-legacy-honor-entry="career-link"', self.source)
        self.assertIn('function switchToCareerFromHonorWall()', self.source)
        self.assertNotIn('id="sport-honor-wall"', self.source)

        honors_body = extract_function_body(self.source, "async function onSwitchToHonors()")
        self.assertIn("isHonorsInitialized = true;", honors_body)
        self.assertNotIn("loadPersonSportHubData", honors_body)
        self.assertNotIn("renderSportHubHonors", honors_body)

        render_tab_body = extract_function_body(self.source, "function renderCurrentSportHubTab()")
        self.assertIn("new Set(['results', 'reserved'])", render_tab_body)
        self.assertNotIn("['results', 'honors', 'reserved']", render_tab_body)

    def test_career_tab_refreshes_derived_events_before_loading_modules(self):
        switch_body = extract_function_body(self.source, "function switchTab(tabBtn)")
        load_body = extract_function_body(self.source, "async function loadCareerData()")

        self.assertIn("loadCareerData().catch", switch_body)
        self.assertIn("refresh_career_derived_events", load_body)
        self.assertLess(load_body.find("refresh_career_derived_events"), load_body.find("loadCareerOverview()"))
        for token in (
            "loadCareerOverview().catch",
            "loadCareerSeasons().catch",
            "loadCareerTimeline().catch",
            "loadCareerArchives().catch",
        ):
            self.assertIn(token, load_body)

    def test_activity_list_has_medal_race_flag_column(self):
        title_body = extract_function_body(self.source, "function renderSportHubTitleCell(item)")
        race_body = extract_function_body(self.source, "function renderSportHubRaceMedalButton(item)")
        render_body = extract_function_body(self.source, "function renderSportHubRecords()")
        toggle_body = extract_function_body(self.source, "async function toggleSportHubRaceFlag(event, activityId)")

        self.assertNotIn("renderSportHubRaceMedalButton(item)", title_body)
        self.assertIn("hub-race-medal-cell", self.source)
        self.assertIn("hub-race-medal-toggle", race_body)
        self.assertIn("is-race", race_body)
        self.assertIn("is-not-race", race_body)
        self.assertIn("🏅", race_body)
        self.assertIn("aria-hidden=\"true\"", race_body)
        self.assertIn("toggleSportHubRaceFlag(event", race_body)
        self.assertNotIn("hub-race-flag-trigger", self.source)
        self.assertNotIn("标为赛事", race_body)
        self.assertLess(render_body.find("<th>时间</th>"), render_body.find("<th>赛事</th>"))
        self.assertLess(render_body.find("<th>赛事</th>"), render_body.find("<th>标题</th>"))
        self.assertLess(render_body.find("${safeHtml(item.date_label || '--')}"), render_body.find("renderSportHubRaceMedalButton(item)"))
        self.assertLess(render_body.find("renderSportHubRaceMedalButton(item)"), render_body.find("renderSportHubTitleCell(item)"))
        self.assertIn("set_activity_race_flag", toggle_body)
        self.assertIn("loadCareerData().catch", toggle_body)
        self.assertNotIn("modal", toggle_body.lower())

    def test_activity_records_support_remote_date_range_sync(self):
        self.assertIn('id="sport-sync-start-date"', self.source)
        self.assertIn('id="sport-sync-end-date"', self.source)
        self.assertIn('id="sport-records-remote-sync-btn"', self.source)
        self.assertIn("function initSportHubSyncDateRange", self.source)
        self.assertIn("function isGarminWatchBrand", self.source)
        self.assertIn("function isCorosWatchBrand", self.source)
        body = extract_function_body(self.source, "async function syncRemoteSportHubActivities()")
        self.assertIn("const isSupportedProvider = isGarminWatchBrand() || isCorosWatchBrand();", body)
        self.assertIn("if (!isSupportedProvider)", body)
        self.assertIn("ensureGarminAuthorizedForRemoteSync", body)
        self.assertIn("ensureCorosAuthorizedForRemoteSync", body)
        self.assertIn("sync_remote_fit_activities(startDate, endDate)", body)
        self.assertIn("loadSportHubActivityList({ resetPage: true, refreshSnapshot: true })", body)
        self.assertIn("开始日期不能晚于结束日期", body)
        self.assertIn("providerLabel", body)
        self.assertIn("formatProviderRemoteSyncSummary", body)
        self.assertIn("formatProviderRemoteSyncError", body)
        self.assertNotIn("res.data && res.data.content", body)
        self.assertNotIn("OpenClaw", body)
        self.assertIn("导入本地 FIT 文件", body)

    def test_provider_remote_sync_error_surfaces_download_error_detail(self):
        error_body = extract_function_body(self.source, "function formatProviderRemoteSyncError(res, providerLabel)")
        self.assertIn("data.provider_detail", error_body)
        self.assertIn("firstProviderDownloadErrorDetail(data.download)", error_body)
        self.assertIn("data.action_hint", error_body)
        self.assertIn("data.provider_error_code", error_body)
        self.assertIn("formatProviderRemoteSyncSummary(data, providerLabel)", error_body)

        detail_body = extract_function_body(self.source, "function firstProviderDownloadErrorDetail(download)")
        self.assertIn("download.errors", detail_body)
        self.assertIn("item.error", detail_body)
        self.assertIn("item.raw_summary", detail_body)

        sanitize_body = extract_function_body(self.source, "function sanitizeProviderErrorDetail(value)")
        self.assertIn("bearer", sanitize_body.lower())
        self.assertIn("access_token", sanitize_body)
        self.assertIn("300", sanitize_body)

    def test_garmin_remote_sync_checks_auth_and_routes_to_settings(self):
        auth_body = extract_function_body(self.source, "async function ensureGarminAuthorizedForRemoteSync()")
        self.assertIn("check_garmin_auth_status", auth_body)
        self.assertIn("normalizeGarminRegion", auth_body)
        self.assertIn("openGarminSettingsForAuthorization", auth_body)
        self.assertNotIn("start_garmin_login", auth_body)
        settings_prompt_body = extract_function_body(self.source, "function openGarminSettingsForAuthorization(authRes, message)")
        self.assertIn('data-panel="settings"', settings_prompt_body)
        self.assertIn("refreshGarminAuthStatus(false)", settings_prompt_body)
        login_body = extract_function_body(self.source, "function showGarminLoginPrompt(authRes)")
        self.assertIn("openGarminSettingsForAuthorization(authRes)", login_body)
        settings_login_body = extract_function_body(self.source, "async function startGarminAuthorizationFromSettings()")
        self.assertIn("start_account_connection('garmin'", settings_login_body)
        self.assertIn("garmin-account-email", settings_login_body)
        self.assertIn("garmin-account-password", settings_login_body)
        self.assertIn("resetGarminSecretFields", settings_login_body)
        self.assertNotIn("start_garmin_login", settings_login_body)
        self.assertIn("set_garmin_region", settings_login_body)
        self.assertIn("garmin-auth-login-btn", settings_login_body)
        mfa_body = extract_function_body(self.source, "async function continueGarminAuthorizationFromSettings()")
        self.assertIn("continue_account_connection", mfa_body)
        self.assertIn("mfa_code", mfa_body)
        disconnect_body = extract_function_body(self.source, "async function disconnectGarminAccountFromSettings()")
        self.assertIn("disconnect_account('garmin'", disconnect_body)
        summary_body = extract_function_body(self.source, "function formatGarminRemoteSyncSummary(data)")
        self.assertIn("payload.download", summary_body)
        self.assertIn("payload.import", summary_body)
        error_body = extract_function_body(self.source, "function formatGarminRemoteSyncError(res)")
        self.assertIn("data.action_hint", error_body)
        self.assertIn("data.provider_error_code", error_body)
        self.assertIn("formatGarminRemoteSyncSummary(data)", error_body)
        self.assertNotIn("stdout", error_body)
        self.assertNotIn("stderr", error_body)
        sync_body = extract_function_body(self.source, "async function syncRemoteSportHubActivities()")
        self.assertIn("isGarminAuthRequiredResponse(res)", sync_body)
        self.assertIn("openGarminSettingsForAuthorization(res", sync_body)
        self.assertNotIn("showGarminLoginPrompt(res)", sync_body)

    def test_coros_settings_auth_controls_are_separate_from_garmin_sync(self):
        for token in (
            'id="coros-region-row"',
            'id="coros-region"',
            'id="coros-auth-check-btn"',
            'id="coros-auth-login-btn"',
            'id="coros-auth-disconnect-btn"',
            "function normalizeCorosRegion",
            "async function refreshCorosAuthStatus",
            "async function startCorosAuthorizationFromSettings",
            "function pollCorosAccountConnection",
            "function persistCorosRegionSelection",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn('id="coros-traininghub-login-btn"', self.source)
        self.assertNotIn("startCorosTrainingHubFromSettings", self.source)
        refresh_body = extract_function_body(self.source, "async function refreshCorosAuthStatus(showToastOnDone = false)")
        self.assertIn("check_account_connection('coros'", refresh_body)
        self.assertNotIn("check_coros_auth_status", refresh_body)
        self.assertIn("normalizeCorosRegion", refresh_body)
        self.assertIn("formatCorosAuthDiagnosticMessage", refresh_body)
        diag_body = extract_function_body(self.source, "function formatCorosAuthDiagnosticMessage(data, fallback)")
        self.assertIn("diagnostics", diag_body)
        self.assertIn("node_available === false", diag_body)
        self.assertIn("!data.mcp_authorized", diag_body)
        self.assertNotIn("traininghub", diag_body.lower())
        login_body = extract_function_body(self.source, "async function startCorosAuthorizationFromSettings()")
        self.assertIn("set_coros_region", login_body)
        self.assertIn("start_account_connection('coros'", login_body)
        self.assertIn("pollCorosAccountConnection", login_body)
        self.assertNotIn("start_coros_login", login_body)
        self.assertIn("coros-auth-login-btn", login_body)
        poll_body = extract_function_body(self.source, "function pollCorosAccountConnection(sessionId, region)")
        self.assertIn("continue_account_connection", poll_body)
        self.assertIn("waiting_callback", poll_body)
        disconnect_body = extract_function_body(self.source, "async function disconnectCorosAccountFromSettings()")
        self.assertIn("disconnect_account('coros'", disconnect_body)
        select_body = extract_function_body(self.source, "function selectUserType(type)")
        self.assertIn("type === 'coros' ? 'flex' : 'none'", select_body)
        self.assertIn("refreshCorosAuthStatus(false)", select_body)
        sync_body = extract_function_body(self.source, "async function syncRemoteSportHubActivities()")
        self.assertIn("ensureCorosAuthorizedForRemoteSync()", sync_body)
        self.assertIn("showCorosLoginPrompt(res)", sync_body)
        self.assertNotIn("start_coros_login", sync_body)
        self.assertNotIn("startCorosAuthorizationFromSettings", sync_body)

    def test_coros_profile_sync_auth_failure_routes_to_settings_without_starting_login(self):
        event_body = extract_function_body(self.source, "window.onProfileSyncEvent = async function(eventName, payload)")
        self.assertIn("isCorosWatchBrand()", event_body)
        self.assertIn("provider_error_code: payload.provider_error_code", event_body)
        self.assertIn("action_hint: payload.action_hint", event_body)
        self.assertIn("isCorosAuthRequiredResponse(authPayload)", event_body)
        self.assertIn("showCorosLoginPrompt(authPayload)", event_body)
        self.assertNotIn("start_coros_login", event_body)
        self.assertNotIn("startCorosAuthorizationFromSettings", event_body)
        auth_body = extract_function_body(self.source, "function isCorosAuthRequiredResponse(res)")
        self.assertNotIn("traininghub", auth_body.lower())
        self.assertNotIn("chrome devtools", auth_body)
        self.assertNotIn("t.coros.com", auth_body)
        self.assertNotIn("function isCorosTrainingHubRequiredResponse", self.source)
        prompt_body = extract_function_body(self.source, "function showCorosLoginPrompt(authRes)")
        self.assertIn('data-panel="settings"', prompt_body)
        self.assertIn("coros-region-row", prompt_body)
        self.assertIn("refreshCorosAuthStatus(false)", prompt_body)
        self.assertNotIn("Training Hub", prompt_body)
        self.assertNotIn("start_coros_login", prompt_body)

    def test_account_connection_center_uses_unified_frontend_contract(self):
        for token in (
            "账号连接中心",
            "list_account_connections",
            "check_account_connection",
            "start_account_connection",
            "continue_account_connection",
            "disconnect_account",
            'id="garmin-account-email"',
            'id="garmin-account-password"',
            'id="garmin-account-mfa"',
            'id="garmin-auth-disconnect-btn"',
            'id="coros-auth-disconnect-btn"',
            "needs_credentials",
            "needs_mfa",
            "opening_browser",
            "waiting_callback",
            "authorized",
            "expired",
            "failed",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn("授权终端", self.source)
        self.assertNotIn("start_garmin_login", self.source)
        self.assertNotIn("start_coros_login", self.source)

    def test_coros_synced_max_hr_disables_manual_override_only_when_not_preserved(self):
        body = extract_function_body(self.source, "function updateProfilePanel(profile, syncMeta)")
        self.assertIn("const profileSourcePlatform = String(syncMeta.current_profile_source_platform || syncMeta.source_platform || '').toLowerCase();", body)
        self.assertIn("const preservedFields = Array.isArray(syncMeta.preserved_fields) ? syncMeta.preserved_fields : [];", body)
        self.assertIn("profileSourcePlatform === 'coros' && hasProfileMaxHr && preservedFields.indexOf('max_hr') < 0", body)
        self.assertIn("maxHrInput.disabled = isCorosSyncedMaxHr", body)
        self.assertIn("maxHrSaveBtn.disabled = isCorosSyncedMaxHr", body)
        self.assertNotIn("isGarminWatchBrand() && hasProfileMaxHr", body)

    def test_coros_profile_and_status_paths_do_not_use_llm_config_prompts(self):
        for signature in (
            "window.onProfileSyncEvent = async function(eventName, payload)",
            "async function refreshCorosAuthStatus(showToastOnDone = false)",
            "async function startCorosAuthorizationFromSettings()",
            "function showCorosLoginPrompt(authRes)",
            "function isCorosAuthRequiredResponse(res)",
        ):
            body = extract_function_body(self.source, signature)
            self.assertNotIn("LLM URL 未配置", body)
            self.assertNotIn("模型名未配置", body)
            self.assertNotIn("test_llm_config", body)

    def test_garmin_remote_sync_no_longer_depends_on_ai_storage_prompt(self):
        body = extract_function_body(self.source, "async function syncRemoteSportHubActivities()")
        button_body = extract_function_body(self.source, "function updateMovementRecordsSyncButton()")
        self.assertNotIn("_validate_storage_notification", body)
        self.assertNotIn("_validate_storage_notification", button_body)
        for token in (
            "_validate_storage_notification",
            "notifyAIAssistant",
            "setAIStorageNotifyButtonState",
            "setNotifyIndicator",
            "BTN_AI_TEXT_IDLE",
            "btn-notify-ai",
            "btn-notify-indicator",
            "告诉AI助手存储规范",
            "告诉 AI 助手存储规范",
            "存储规范同步中",
            "已成功告知 AI 助手存储规范",
        ):
            self.assertNotIn(token, self.source)

    def test_activity_records_import_local_fit_files_uses_local_import_api(self):
        self.assertIn("导入本地 FIT 文件", self.source)
        self.assertNotIn("🔄 同步本地数据", self.source)
        self.assertIn("function importLocalFitFiles", self.source)
        body = extract_function_body(self.source, "async function importLocalFitFiles()")
        self.assertIn("pick_and_import_fit_files", body)
        self.assertIn("loadSportHubActivityList({ resetPage: true, refreshSnapshot: true })", body)
        self.assertNotIn("sync_remote_fit_activities", body)
        self.assertNotIn("call_llm", body)

    def test_remote_sync_button_is_brand_gated_but_local_import_is_not(self):
        body = extract_function_body(self.source, "function updateMovementRecordsSyncButton()")
        self.assertIn("const providerReady = isGarminWatchBrand() || isCorosWatchBrand();", body)
        self.assertIn("remoteBtn.disabled = busy || !providerReady", body)
        self.assertIn("btn.disabled = busy", body)
        self.assertIn("当前手表品牌暂不支持按时间同步活动", body)
        self.assertIn("COROS MCP 同步活动 FIT 文件", body)
        self.assertIn("直接同步 Garmin 活动 FIT 文件", body)
        self.assertNotIn("storageValidated", body)

    def test_batch_delete_uses_blocker_modal_and_deletes_local_files(self):
        body = extract_function_body(self.source, "async function deleteSelectedSportHubRecords()")
        self.assertNotIn("confirm(", body, "不得使用浏览器原生 confirm")
        self.assertIn("blocker-modal", body)
        self.assertIn("确认删除运动记录", body)
        self.assertIn("物理删除", body)
        self.assertIn("btnEl.onclick = async function()", body)
        self.assertIn("const confirmToken = `DELETE:${ids.length}`;", body)
        self.assertIn("delete_activities(ids, confirmToken)", body)
        self.assertIn("files_deleted", body)
        self.assertIn("file_errors", body)
        self.assertIn("skipped_unsafe_paths", body)
        self.assertIn("loadSportHubActivityList", body)
        self.assertIn("closeBlockerModal()", body)

    def test_trace_toolbar_has_no_sport_type_selector(self):
        self.assertNotIn('id="sport-type-selector"', self.source)


if __name__ == "__main__":
    unittest.main()
