# RCV2-03 工程级执行提示词

任务：V2 Record Registry、纪录族与 Scope 冻结

目标：把 V2 手册、真实数据审计和 golden fixtures 中的跑步、骑行、徒步、游泳、越野定义转成无歧义 Registry 契约，供后续 `RCV2-09` 代码化。

输入摘要：

- `RCV2-00` 确认当前代码只有 V1 跑步四项 Registry。
- `RCV2-01` 确认普通骑行 94 条、67 条有功率流；徒步/步行/登山可分离；游泳只有公开水域；越野跑 0 条；pool length 缺 canonical 字段。
- `RCV2-02` 已冻结合成 fixtures，覆盖功率、海拔、泳池、公开水域和越野路线边界。

前置依赖：`RCV2-01`、`RCV2-02`。

文件范围：

- 可写：本提示词、`docs/records_center_v2_rcv2_03_registry_scope_contract.md`、完成报告、滚动摘要、V2 任务清单。
- 禁止：业务代码、schema migration、API contract、真实库、前端、打包产物。

冻结契约：

- 不改变跑步四项 V1 定义。
- 不把模型估计、analysis curve、GAP/NGP/eFTP/CP/W′ 注册为正式 active record。
- 所有 scope 必须后端生成；前端不得拼 scope。
- 未实现或未真实验收的定义不得在 Catalog 中开放为 available。
- 动态 route/segment 使用稳定 `record_key + scope_key`，不把 route id 拼成新的 record type。

实施步骤：

1. 定义 V2 `RecordDefinition` 字段。
2. 冻结 family、source_mode、scope_dimensions、单位、比较方向和 priority。
3. 列出跑步、骑行、徒步、游泳、越野的静态 record keys。
4. 列出 route/segment 动态 scope 规则。
5. 冻结 Catalog 当前状态、目标状态、candidate-only 和 validation required 策略。
6. 写冲突矩阵和后续测试计划。
7. 更新滚动摘要和任务状态。

非目标：

- 不实现 Registry 代码。
- 不修改 `docs/js_api_contract.json`。
- 不新增或迁移数据库字段。

验证：

- 文档检查：record keys 唯一、比较方向/单位/source_mode 均来自白名单。
- 运行 fixture 测试，确保契约仍能引用 fixtures。

完成定义：

- 新增任何 V2 纪录时，开发者无需自行猜测值、单位、方向、Scope 或来源模式。
