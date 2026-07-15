# RCV2-04 工程级执行提示词

任务：质量评分、置信度与原因码冻结

目标：统一多运动 Records V2 的自动确认、候选和忽略边界，保证增量、重建、API 与前端看到的原因一致且可解释。

输入摘要：

- `RCV2-03` 已冻结 V2 Registry、record keys、family、source_mode、Scope 和 Catalog 默认可用性。
- 跑步 V1 阈值必须继承：`>0.90` 自动确认，`0.70-0.90` 候选，`<0.70` 忽略；`0.70/0.90` 边界均为候选。
- Golden fixtures 已覆盖骑行功率断点/尖峰/e-bike、徒步海拔尖峰/连续爬升、泳池 pool length/泳姿、公开水域 GPS、越野路线方向/重合。

前置依赖：`RCV2-03`。

文件范围：

- 可写：本提示词、`docs/records_center_v2_rcv2_04_quality_confidence_contract.md`、完成报告、滚动摘要、V2 任务清单。
- 禁止：业务代码、schema migration、API contract、真实库、前端、打包产物。

冻结契约：

- 前端不解析技术 evidence，只展示后端 ViewModel 中的安全 reason 文案。
- 用户确认只能确认候选证据，不得修改事实值、成绩值、距离、时间、范围、record key 或 scope。
- candidate-only 的 Registry 状态优先于单条 evidence 高分：可进入候选，不自动 active。
- analysis/model 项不参与置信度状态机。
- reason codes 是稳定英文枚举；用户文案和日志安全映射必须由后端提供。

实施步骤：

1. 冻结 V2 质量评分对象、决策输出和阈值函数。
2. 定义全局 hard-block、降级、候选和自动确认规则。
3. 冻结通用 reason codes、运动专属 reason codes、用户文案和日志安全等级。
4. 按跑步、骑行、徒步、泳池、公开水域、越野路线/赛段列出质量维度和决策矩阵。
5. 冻结 candidate-only 样本不足规则和用户确认边界。
6. 写边界测试表和后续实现测试计划。
7. 更新滚动摘要和任务状态。

非目标：

- 不实现评分算法代码。
- 不修改 V1 状态机代码。
- 不迁移数据库或写入真实库。
- 不改前端展示。

验证：

- 文档检查：阈值边界、reason code 唯一性、fixture reason code 覆盖、敏感词禁止。
- 运行 golden fixture 测试，确保质量契约仍能引用现有 fixtures。

完成定义：

- 后续 Resolver 开发不需要临时决定某个质量问题是 auto-confirm、candidate 还是 ignored。
- 同一 evidence 在增量、重建和 API 路径中应得到相同 decision、confidence band、reason codes 和用户文案。
