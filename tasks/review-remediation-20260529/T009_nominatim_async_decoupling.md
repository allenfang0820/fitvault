首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T009

任务名称：Nominatim 地区查询完全解耦

目标文件：`profile_backend.py`、`test_fit_sync.py`

定位行号：`profile_backend.py:L21`、`profile_backend.py:L1154-L1288`、`test_fit_sync.py:L216-L360`

执行目标：确保 FIT 入库主链路不发生同步 Nominatim 网络请求，地区查询只能通过缓存命中或后台异步补全完成；无 GPS 活动必须稳定返回室内/无 GPS 状态。

执行要求：保留 `resolve_activity_region()` 的缓存读取能力，但避免在 FIT 解析/入库同步路径中直接触发网络请求；将 `reverse_geocode()` 限定在后台补全函数中执行；完善 `region_status`、`region_error`、`region_attempt_count` 状态写入。

禁止事项：禁止在 `_parse_fit_activity_for_sync` 或同步导入路径中等待外部网络；禁止因 Nominatim 失败阻断 FIT 入库；禁止移除已有缓存表能力。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`profile_backend.py`、`main.py`、`utils/geocoding.py`、`test_fit_sync.py`

允许修改范围：允许修改 `profile_backend.py` 地区缓存/后台补全逻辑、`main.py` 入库调用点及相关测试；允许最小范围调整 `utils/geocoding.py` 错误处理；不得让 FIT 同步路径直接依赖外部网络成功。

推荐测试命令：`python3 -m pytest test_fit_sync.py test_watchdog_bridge.py`

完成后报告格式：输出“同步链路解耦说明 / 后台补全链路说明 / region 状态字段说明 / 测试命令与结果 / 未覆盖风险”五段。

验收标准：现有 `test_fit_sync.py` 中 mock `resolve_activity_region` 抛错的测试仍通过；新增测试验证网络失败时活动仍可入库，且地区状态可被后续后台任务补全。
