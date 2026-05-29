首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T005

任务名称：统一 API 响应与错误码

目标文件：`main.py`

定位行号：`main.py:L2415-L2503`、`main.py:L3179-L3303`、`main.py:L3444-L3530`

执行目标：为 pywebview 暴露 API 建立统一响应封装，逐步替换散落的 `{"ok": False, "error": str(e)}` 和非统一成功结构，使返回结构满足 `{code,msg,data,traceId}` 契约，同时兼容现有前端必要字段。

执行要求：新增统一成功/失败响应辅助函数；定义稳定错误码分类；优先改造配置、删除、导入、活动列表等高风险/高频接口；如需兼容前端，可在过渡期保留 `ok` 字段，但必须同时提供 `code`、`msg`、`data`、`traceId`。

禁止事项：禁止继续新增只有 `error: str(e)` 的响应；禁止把内部异常堆栈直接返回前端；禁止一次性大范围破坏前端调用契约。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`main.py`、`track.html`、`docs/CHANGELOG.md`

允许修改范围：允许修改 `main.py` 中响应辅助函数和目标 API；允许最小范围修改 `track.html` 以兼容统一响应；允许新增 `docs/js_api_contract.json` 或错误码文档；不得一次性重写所有 pywebview API。

推荐测试命令：`python3 -m pytest test_track_html_sync_logic.py test_watchdog_bridge.py test_import.py`

完成后报告格式：输出“统一响应结构 / 错误码列表 / 已改造接口 / 前端兼容策略 / 测试命令与结果 / 未覆盖风险”六段。

验收标准：被改造接口成功和失败响应均包含 `code`、`msg`、`data`、`traceId`；错误码稳定可枚举；现有前端调用不因响应结构变更而失效。
