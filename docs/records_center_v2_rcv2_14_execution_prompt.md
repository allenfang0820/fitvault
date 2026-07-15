# RCV2-14 工程级执行提示词

任务：通用 Records API 与 V1 兼容包装器

目标：实现 Records Center V2 的通用只读 API、统一 envelope、Catalog/Records/Detail/History/Curve/Candidates/Rebuild 状态入口，并保证 V1 `get_career_pb*` API 和旧前端兼容。

输入摘要：

- RCV2-06 已冻结 API/ViewModel 契约。
- RCV2-09 已实现 Registry/Catalog 底座。
- RCV2-10 已实现 V2 schema/cache/route 表。
- RCV2-11 已实现安全 Evidence。
- RCV2-12 已实现 scoped state service。
- RCV2-13 已实现 V2 dispatch/rebuild/invalidation 框架。

前置依赖：`RCV2-06`、`RCV2-12`、`RCV2-13`。

文件范围：

- 可写：`career_backend.py`、`docs/js_api_contract.json`、API 测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：真实库 apply、前端视觉重构、具体多运动 resolver 算法、打包产物。

冻结契约：

- 前端只消费 ViewModel，不计算 record fact、scope、confidence、improvement、history summary 或 axis direction。
- API 不返回 raw FIT、完整轨迹、功率流、路径、SQLite schema、设备标识、账号/token、体重历史。
- `get_career_pb*` 兼容旧调用方。
- `detail_link.source="career"` 保持。
- Rebuild API 默认 dry-run；真实库不得 apply。
- Catalog 是运动页签、可用性和灰态说明唯一来源。

实施步骤：

1. 实现统一 Records API envelope helper。
2. 实现 `get_career_records()` 通用列表 ViewModel。
3. 实现 `get_career_record_detail()`、`get_career_record_history()`。
4. 实现 `get_career_record_curve()` 安全读取派生 curve cache。
5. 实现 `get_career_record_candidates()` 和 candidate 决策只读/动作包装。
6. 实现 `get_career_record_rebuild_status()` 与 `rebuild_career_records` V2 包装，默认 dry-run。
7. 保持/适配 V1 `get_career_pb*` 包装兼容。
8. 更新 `docs/js_api_contract.json`。
9. 增加 API 测试和安全黑名单测试。

非目标：

- 不实现前端页面。
- 不生成多运动 evidence。
- 不运行真实库 apply。
- 不打包。

验证：

- `.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q`
- `.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_record_v2_rebuild.py tests/test_career_record_evidence.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- 旧 PB API 兼容测试通过。
- 新 Records API 返回安全 ViewModel。
- `docs/js_api_contract.json` 与实现一致。
- API 不泄漏敏感/raw 字段。

