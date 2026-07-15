# RCV2-11 工程级执行提示词

任务：通用 Record Evidence 与 source_mode 扩展

目标：建立安全、可序列化、可 fingerprint 的 V2 Record Evidence 底座，使 `activity_total`、`best_effort_duration`、`best_effort_distance`、`route_total`、`segment` 五类 evidence 能用同一接口进入后续质量评分和状态机。

输入摘要：

- RCV2-09 已代码化 V2 Registry/Catalog，并保留 V1 running resolver 默认只匹配四项跑步。
- RCV2-10 已完成 V2 schema、scope hash、active/evidence 索引、Curve Cache 和 route 派生表。
- RCV2-03/04/05 冻结了 source_mode、scope dimensions、reason codes、安全边界和 evidence key 格式。

前置依赖：`RCV2-09`、`RCV2-10`。

文件范围：

- 可写：`career_backend.py`、Record Evidence 相关测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：真实库 apply、前端、API contract JSON、打包产物。

冻结契约：

- Activity 是唯一事实源，Evidence 只能描述 Activity 派生出的安全事实。
- Evidence helper 不切换 active，不写正式纪录，不创建候选，不触发 Achievement/Timeline。
- Evidence payload 不得包含 raw FIT、完整轨迹、原始功率流、真实 GPS 点、本地路径、未脱敏设备标识、账号/token 或体重历史。
- Evidence key 格式保持：`evidence:v2:{record_key}:{activity_id}:{source_mode}:{scope_hash}:{range_hash}:{metric_hash}:{rule_version}`。
- `source_mode` 必须来自 Registry 白名单。
- Scope 只能使用冻结维度，动态 route/segment 必须进入 scope。
- V1 `record_evidence_key()` 和 `build_record_candidate_decision()` 行为不得改变。

实施步骤：

1. 新增 Record Evidence dataclass/模型常量。
2. 新增通用 source_mode 校验、scope key 派生、range/quality canonicalization。
3. 新增安全 JSON 校验器，拒绝 raw stream/path/GPS/device/body-weight 等敏感字段。
4. 新增 `build_record_evidence()` 与 evidence key/fingerprint helper。
5. 覆盖五类 source_mode：activity_total、best_effort_duration、best_effort_distance、route_total、segment。
6. 增加单元测试：稳定 key、顺序无关、metric/range/scope 改变会改变 key、非法 source_mode、缺失 range/scope、敏感字段拒绝、V1 key 兼容。
7. 运行定向测试、V1 PB 兼容测试和 py_compile。

非目标：

- 不实现质量评分 V2 决策。
- 不把 Evidence 写入 `career_pb_records`。
- 不实现 route matching 或 curve 算法。
- 不修改前端 ViewModel。

验证：

- `.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_record_registry.py -q`
- `.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_record_state_migration.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- 五类 source_mode 均可生成安全、稳定、可序列化的 V2 Evidence。
- 同一事实在输入顺序变化时生成同一 evidence key；事实变化时 key 变化。
- 敏感/raw payload 被拒绝。
- V1 running PB resolver 和旧 PB API 无回归。

