首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T002

任务名称：实现 shadow_diff 持久化闭环

目标文件：`profile_backend.py`、`main.py`

定位行号：`profile_backend.py:L448-L520`、`main.py:L1094-L1216`、`main.py:L3444-L3530`

执行目标：将 Resolver 与 Legacy 差异结果以稳定字段持久化到 `activities` 表，并在活动写入、更新、查询链路中形成闭环；建议字段名使用 `shadow_diff_json`，字段内容必须为可序列化 JSON 字符串。

执行要求：在 schema 初始化与幂等 ALTER TABLE 中补充字段；在 `_insert_activity_sync_row` 和 `_update_activity_sync_row` 中写入该字段；在活动列表或详情查询中按契约返回必要的调试/审计信息；保持字段来源明确，禁止将 shadow diff 混入 canonical 指标字段。

禁止事项：禁止仅打印日志不落库；禁止将 diff 内容作为 UI 展示字段默认参与业务计算；禁止破坏已有 activities 写入参数顺序。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`profile_backend.py`、`main.py`、`metrics_resolver.py`、`test_fit_sync.py`

允许修改范围：允许修改 `profile_backend.py`、`main.py` 与相关测试文件；如需新增契约说明，可修改 `docs/` 下相关文档；不得修改 UI 默认展示逻辑，除非仅用于审计/调试入口且明确标记非业务字段。

推荐测试命令：`python3 -m pytest test_fit_sync.py test_duplicate_check.py`

完成后报告格式：输出“新增字段与迁移说明 / 写入与查询链路说明 / 契约边界说明 / 测试命令与结果 / 未覆盖风险”五段；必须说明 shadow diff 不参与 canonical 指标计算。

验收标准：新增或更新测试验证新字段可被创建、写入、更新、查询；旧数据库启动后能自动补列；不存在 `shadow_diff` 仅内存流转但无法追踪的情况。
