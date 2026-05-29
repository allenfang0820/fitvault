首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T010

任务名称：main.py 职责拆分方案落地

目标文件：`main.py`、`docs/DIR_SPEC.md`

定位行号：`main.py:L2228-L3308`、`main.py:L3444-L3590`

执行目标：在不改变 pywebview 本地桌面应用形态的前提下，按目录规范逐步拆分 `main.py` 的高耦合职责，将 API 响应、活动导入/删除、配置、AI Snapshot、活动列表查询等逻辑迁移到清晰模块中。

执行要求：先阅读并遵守 `docs/DIR_SPEC.md`；采用小步迁移方式，保留 `class Api` 作为 pywebview 暴露门面；迁移后由 `class Api` 调用新模块函数；每次迁移必须有测试或静态验证。

禁止事项：禁止一次性大规模重写；禁止改变前端 `window.pywebview.api.*` 方法名；禁止引入 Web 服务替代 pywebview；禁止破坏现有启动入口。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`main.py`、`track.html`、`requirements.txt`、相关测试文件

允许修改范围：允许新增符合目录规范的 Python 模块并从 `main.py` 调用；允许修改 `main.py` import 与薄门面调用；允许新增或调整测试；不得改变 pywebview 对外方法名和启动入口。

推荐测试命令：`python3 -m pytest test_import.py test_track_html_sync_logic.py test_watchdog_bridge.py test_fit_sync.py`

完成后报告格式：输出“拆分模块清单 / 保持不变的外部 API / 迁移前后职责对比 / 测试命令与结果 / 未覆盖风险”五段。

验收标准：至少完成一个高风险职责域的模块化迁移；迁移后相关 API 方法行为保持一致；`main.py` 行数和职责范围有可观察收敛；目录结构符合 `docs/DIR_SPEC.md`。
