首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T001

任务名称：修复 Resolver 平铺记录适配

目标文件：`metrics_resolver.py`

定位行号：`metrics_resolver.py:L220-L260`

执行目标：修复 `MetricsResolver` 对 FIT record 的读取逻辑，使其同时兼容现有 `fit_engine` 输出的平铺字段结构和历史 `{raw, geo}` 嵌套结构；确保 `heart_rate`、`speed`、`altitude`、`distance`、`lat/lon` 能稳定进入 `hr_curve`、`speed_curve`、`altitude_curve`、`distance_curve`、`lat_curve`、`lon_curve` 和 AI context 计算。

执行要求：新增最小范围的 record 取值适配函数或局部兼容逻辑；不得把 FIT 原始字段直接透传到 UI；不得改变 Resolver 作为唯一语义翻译层的职责；不得修改 `fit_engine.py` 的 canonical 输出结构，除非测试证明必须同步调整。

禁止事项：禁止在 UI 层补救该问题；禁止用前端 fallback 推断缺失指标；禁止吞掉异常后返回不透明空结果。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`fit_engine.py`、`metrics_resolver.py`、`test_fit_parser.py`、`test_fit_sync.py`

允许修改范围：优先仅修改 `metrics_resolver.py` 与相关测试文件；如必须调整输入契约，只允许在充分说明原因后最小范围修改 `fit_engine.py` 或测试夹具；不得修改 `track.html` 做 UI 兜底。

推荐测试命令：`python3 -m pytest test_fit_parser.py test_fit_sync.py`

完成后报告格式：输出“修改文件清单 / 契约遵循说明 / 测试命令与结果 / 未覆盖风险”四段；必须说明是否仍兼容平铺 record 与 `{raw, geo}` 嵌套 record。

验收标准：新增或更新测试覆盖平铺 record 与嵌套 record 两种输入；运行相关测试后，`hr_curve`、`speed_curve`、`distance_curve` 至少在包含对应原始数据时能输出非空有效数组；不得引入新的 `None.get(...)` 风险。
