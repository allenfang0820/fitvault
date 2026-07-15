# RCV2-06 工程级执行提示词

任务：通用 Records API、Catalog 与 ViewModel 冻结

目标：冻结 Records Center V2 的前后端 API/ViewModel 契约，同时保持 V1 `get_career_pb*` 兼容。

输入摘要：

- `RCV2-03` 冻结了 Registry、record keys、Scope、availability。
- `RCV2-04` 冻结了质量、confidence、reason codes、candidate-only/validation-required 优先级。
- `RCV2-05` 冻结了 schema、scope_hash、curve cache、route signature、migration/dry-run。
- 当前 `docs/js_api_contract.json` 已有 PB API：`get_career_pb`、`get_career_pb_detail`、`get_career_pb_history`、`decide_career_pb_candidate`、`rebuild_career_pb_records`、`get_career_record_events`、`get_career_event_candidates`；尚无 V2 通用 Records API。

前置依赖：`RCV2-05`。

文件范围：

- 可写：本提示词、`docs/records_center_v2_rcv2_06_api_viewmodel_contract.md`、完成报告、滚动摘要、V2 任务清单。
- 禁止：业务代码、`docs/js_api_contract.json` 实际修改、真实库、前端、打包产物。

冻结契约：

- V1 `get_career_pb*` 与 `detail_link.source="career"` 必须保持兼容。
- 通用 V2 API 不返回 raw points、轨迹、功率流、路径、schema、传感器序列号或体重详情。
- 前端不计算纪录事实、Scope、置信度、improvement、history summary 或轴方向。
- Catalog 是前端运动页签和灰态可用性的唯一来源。
- Curve API 只返回安全摘要和可绘制 ViewModel，不返回原始采样。

实施步骤：

1. 冻结统一 envelope、status、error code 和安全白名单。
2. 冻结新通用 API 名称、请求和返回 ViewModel：Catalog、Records、Detail、History、Curve、Candidates、Candidate Decision、Rebuild Status。
3. 冻结 V1 API 到 V2 通用 API 的包装关系。
4. 冻结 Catalog `available/candidate_only/validation_required/unavailable/analysis_only/model_only` 前端行为。
5. 冻结 History Summary、axis direction、improvement timeline 字段。
6. 冻结 Partial、Validation Required、Rebuilding、Empty 和 Error 状态。
7. 列出 `docs/js_api_contract.json` 后续计划变更。
8. 写 mock fixture 和测试计划。
9. 更新滚动摘要和任务状态。

非目标：

- 不实现 API。
- 不修改 `docs/js_api_contract.json`。
- 不改前端。
- 不写真实库。

验证：

- 文档检查：API 名称、旧 API 兼容、禁止字段、安全状态、Catalog 状态和 planned contract changes。
- 运行 golden fixture 测试。

完成定义：

- 前端设计不依赖未定义字段；旧调用方无需理解 V2 Scope；后续 `RCV2-14` 可按本文实现通用 API 与兼容包装器。
