首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T004

任务名称：高风险删除接口安全加固

目标文件：`main.py`

定位行号：`main.py:L3179-L3224`

执行目标：为 `delete_activities()` 增加高风险操作防护，避免误删或越权删除本地文件；删除数据库记录和本地 FIT 文件前必须进行路径归属校验、二次确认参数校验和操作审计记录。

执行要求：仅允许删除 `TRACKS_DIR` 受控目录内的活动文件；增加明确的确认参数，例如 `confirm_token` 或等价二次确认字段；对 missing、file_errors、skipped_unsafe_paths 做结构化返回；保留数据库事务一致性。

禁止事项：禁止删除 `TRACKS_DIR` 外部路径；禁止静默忽略危险路径；禁止在文件删除失败时造成数据库与文件状态不可追踪。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`main.py`、`profile_backend.py`、`test_duplicate_check.py`

允许修改范围：允许修改 `main.py` 中删除接口及必要辅助函数、相关测试文件；如前端需要传递二次确认参数，可最小范围修改 `track.html` 对应调用点；不得放宽 `TRACKS_DIR` 归属约束。

推荐测试命令：`python3 -m pytest test_duplicate_check.py test_track_html_sync_logic.py`

完成后报告格式：输出“安全门禁说明 / 路径归属校验说明 / 事务与审计说明 / 测试命令与结果 / 未覆盖风险”五段；必须列明受控目录外路径的处理结果。

验收标准：新增或更新测试覆盖空 ID、找不到记录、受控目录内删除、受控目录外路径拒绝、文件删除失败但 DB 事务可追踪等场景。
