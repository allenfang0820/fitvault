import unittest
from pathlib import Path


TRACK_HTML_PATH = Path("/Users/fanglei/应用开发/AI track/track.html")


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
        self.assertIn("const refreshSnapshot = options.refreshSnapshot !== false && (!!options.refreshSnapshot || !sportHubState.recordsReady);", body)
        self.assertIn("if (!refreshSnapshot)", body)
        local_branch = body[body.find("if (!refreshSnapshot)"):body.find("sportHubState.recordsLoading = true;")]
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

    def test_report_panel_renders_weather_card_and_syncs_weather_context(self):
        self.assertIn("历史天气环境感知", self.source)
        self.assertIn("setCurrentWeather(data.weather || null);", self.source)
        self.assertIn("weather: appState.currentWeather", self.source)

    def test_ai_report_uses_dynamic_sport_labels_instead_of_fixed_hiking(self):
        self.assertIn("function getDynamicSportMeta(typeStr)", self.source)
        self.assertIn("getDynamicSportMeta(appState.sportType)", self.source)

    def test_activity_records_support_selection_and_batch_delete(self):
        self.assertIn("selectedIds: new Set()", self.source)
        self.assertIn("sport-records-select-all", self.source)
        self.assertIn("function toggleSportHubRecordSelection", self.source)
        self.assertIn("function deleteSelectedSportHubRecords", self.source)
        self.assertIn("delete_activities", self.source)

    def test_activity_records_support_remote_date_range_sync(self):
        self.assertIn('id="sport-sync-start-date"', self.source)
        self.assertIn('id="sport-sync-end-date"', self.source)
        self.assertIn('id="sport-records-remote-sync-btn"', self.source)
        self.assertIn("function initSportHubSyncDateRange", self.source)
        self.assertIn("function isGarminWatchBrand", self.source)
        body = extract_function_body(self.source, "async function syncRemoteSportHubActivities()")
        self.assertIn("if (!isGarminWatchBrand())", body)
        self.assertIn("sync_remote_fit_activities(startDate, endDate)", body)
        self.assertIn("syncAndLoadSportHubRecords({ sync: true, resetPage: true })", body)
        self.assertIn("开始日期不能晚于结束日期", body)
        self.assertIn("OpenClaw", body)
        self.assertIn("导入本地 FIT 文件", body)

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
        self.assertIn("const garminReady = isGarminWatchBrand();", body)
        self.assertIn("remoteBtn.disabled = busy || !garminReady", body)
        self.assertIn("btn.disabled = busy", body)
        self.assertIn("当前手表品牌暂不支持按时间同步活动", body)

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
