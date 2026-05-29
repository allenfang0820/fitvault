首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T006

任务名称：ZIP/FIT 批量导入资源限制

目标文件：`main.py`

定位行号：`main.py:L3228-L3303`

执行目标：在现有 ZIP 路径穿越防护基础上，为 `safe_extract_zip()` 和 `batch_import_tracks()` 增加资源限制，防止超大文件、超多文件、压缩炸弹或非 FIT 垃圾文件导致磁盘和内存风险。

执行要求：增加 ZIP 成员数量上限、单成员解压大小上限、总解压大小上限、允许扩展名白名单；读取 ZIP 成员时避免一次性无限制 `src.read()`；返回结构化错误给调用方。

禁止事项：禁止恢复使用 `extractall()`；禁止无上限读取压缩文件内容；禁止将非 `.fit` 文件移动到 `TRACKS_DIR`。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`main.py`、`test_fit_sync.py`

允许修改范围：允许修改 `main.py` 中 `safe_extract_zip()`、`batch_import_tracks()` 及必要常量；允许新增或修改导入安全测试；不得改变 FIT 单文件正常导入行为。

推荐测试命令：`python3 -m pytest test_fit_sync.py test_duplicate_check.py`

完成后报告格式：输出“资源限制参数 / 危险 ZIP 拦截策略 / 正常导入兼容性 / 测试命令与结果 / 未覆盖风险”五段。

验收标准：测试覆盖正常 ZIP、路径穿越 ZIP、超数量 ZIP、超大小 ZIP、含非 FIT 文件 ZIP；危险 ZIP 不应写入受控目录外路径。
