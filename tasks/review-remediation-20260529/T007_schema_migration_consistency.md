首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

任务编号：T007

任务名称：数据库 Schema 迁移一致性校验

目标文件：`profile_backend.py`、`main.py`

定位行号：`profile_backend.py:L390-L553`、`main.py:L388-L541`

执行目标：建立 activities 与 user_profile 关键表的 schema 版本/列一致性校验，确保旧数据库启动后能幂等补齐代码所需字段，避免代码定义 36+ 列但实际数据库缺列。

执行要求：梳理 `activities` 当前建表字段、ALTER TABLE 字段、`main.py` 补列字段，合并成单一迁移定义源或明确的迁移函数；启动时执行幂等迁移；输出可审计的迁移结果；确保 `user_profile_snapshots` 表能被创建并验证存在。

禁止事项：禁止删除用户已有数据；禁止通过重建数据库解决缺列；禁止继续在多个位置维护互相冲突的字段列表。

必读文件：`ARCHITECTURE.md`、`docs/DIR_SPEC.md`、`profile_backend.py`、`main.py`、`test_fit_sync.py`、`test_import.py`

允许修改范围：允许修改 `profile_backend.py` 与 `main.py` 中 schema 初始化/迁移逻辑，允许新增迁移测试；如需记录 schema 版本，可新增文档或轻量元数据表；不得删除或重建用户数据库。

推荐测试命令：`python3 -m pytest test_fit_sync.py test_import.py test_duplicate_check.py`

完成后报告格式：输出“统一迁移源说明 / 补齐字段列表 / 幂等性验证 / 测试命令与结果 / 未覆盖风险”五段。

验收标准：新增测试在旧 schema 临时库上运行迁移后检查所有必需列存在；迁移可重复执行；`user_profile_snapshots` 表存在且字段符合设计。
