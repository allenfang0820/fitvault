# RCV2-12 工程级执行提示词

任务：Scope 感知的状态迁移、事件与候选闭环

目标：扩展 Records Center 状态服务底座，使 V2 Evidence 可以按 `record_key + source_mode + scope_hash` 独立比较、候选、确认、拒绝、替代和事件留痕，同时保持 V1 跑步 PB 状态迁移结果不变。

输入摘要：

- RCV2-10 已完成 V2 schema、scope hash、active/evidence 索引。
- RCV2-11 已完成安全 Record Evidence 模型和稳定 `evidence:v2:*` key。
- V1 `apply_record_candidate_decision()` 仍负责旧 running PB 路径，本任务不得改变其默认行为。

前置依赖：`RCV2-04`、`RCV2-10`、`RCV2-11`。

文件范围：

- 可写：`career_backend.py`、状态机测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：真实库 apply、前端、API contract JSON、打包产物。

冻结契约：

- V2 active 唯一性以 `record_key + source_mode + scope_hash` 为准；兼容旧 V1 索引时不得让不同 Scope 互相冲突。
- lower/higher 两种比较方向都必须支持。
- tie 或未提升不得替换 active。
- candidate 只能确认或拒绝，用户不能改值、range、scope 或 reason。
- rejected 同证据不得重复提示。
- Event payload 与 candidate evidence 必须安全，不得包含 raw FIT、完整轨迹、功率流、真实 GPS、路径、设备标识、账号/token 或体重历史。
- analysis/model record 不进入状态机。
- 本任务不接真实 Resolver 扫描，不写真实库。

实施步骤：

1. 新增 V2 metric comparison helper。
2. 新增 V2 active 查询和事件写入 helper。
3. 新增 V2 candidate upsert 和用户 confirm/reject helper。
4. 新增 `apply_record_evidence_state()`，只消费 RCV2-11 的安全 Evidence。
5. 写入 `career_pb_records` 时同步 legacy 兼容列和 V2 列。
6. 增加测试：同 Scope 替代、不同 Scope 共存、higher/lower/tie、candidate 幂等、reject 不重复、confirm 重新比较、事件 payload 安全、V1 状态迁移不变。
7. 运行定向测试和 py_compile。

非目标：

- 不实现 sport resolver。
- 不实现增量分发或 rebuild。
- 不修改前端候选处理 API。
- 不触发真实库执行。

验证：

- `.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_state_migration.py -q`
- `.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_record_schema_migration.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- 同一 `record_key/source_mode/scope_hash` 最多一个 active。
- 不同 Scope 不互相替代。
- candidate confirm/reject 闭环幂等。
- V1 running PB 状态迁移测试无回归。

