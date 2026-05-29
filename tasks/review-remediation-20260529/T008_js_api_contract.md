首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T008

任务名称：建立 pywebview js_api 契约文档

目标文件：`main.py`、`track.html`、`docs/js_api_contract.json`

定位行号：`main.py:L2228-L2250`、`track.html:L2775-L2997`

执行目标：由于项目采用 pywebview 本地 API 而非 HTTP API，请建立等价的 `docs/js_api_contract.json`，记录 `window.pywebview.api.*` 暴露方法的名称、参数、返回结构、错误码和高风险标记。

执行要求：扫描 `class Api` 中对前端暴露的方法；优先纳入配置、LLM、FIT 导入、删除活动、活动列表、用户画像、AI snapshot 相关接口；契约文件必须纳入版本控制目录 `docs/`；格式应稳定可被后续脚本校验。

禁止事项：禁止为完成 OpenAPI 要求而擅自引入 FastAPI/Flask HTTP 服务；禁止记录真实密钥或用户隐私数据；禁止遗漏高风险接口标记。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`main.py`、`track.html`、`docs/CHANGELOG.md`

允许修改范围：允许新增 `docs/js_api_contract.json`、必要的契约说明文档或轻量校验脚本；允许最小范围调整 `main.py` 方法注解/说明以便契约提取；不得引入 HTTP 服务框架。

推荐测试命令：`python3 -m json.tool docs/js_api_contract.json >/dev/null && python3 -m pytest test_import.py`

完成后报告格式：输出“契约文件路径 / 覆盖接口清单 / 高风险接口标记 / 校验命令与结果 / 未覆盖风险”五段。

验收标准：`docs/js_api_contract.json` 存在且 JSON 可解析；每个高风险接口包含 `riskLevel` 或等价字段；契约中的方法名能在 `main.py` 中定位到对应实现。
