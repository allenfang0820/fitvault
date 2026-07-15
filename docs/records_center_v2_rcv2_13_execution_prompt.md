# RCV2-13 工程级执行提示词

任务：增量分发、删除回退、重建与回滚闭环

目标：建立 Records Center V2 通用增量/重建框架，让 Activity 变化能够按 sport 分发到可用 definitions，并提供 Activity 删除/修改导致的 record/cache/route 失效、同 Scope fallback 回退、rebuild dry-run/apply 摘要和事务回滚能力。

输入摘要：

- RCV2-12 已提供 V2 scoped state service。
- 具体骑行/徒步/游泳/越野 resolver 尚未开始，因此本任务只做通用框架，不生成伪 evidence。
- RCV2-40/41 前仍不得对真实库 apply。

前置依赖：`RCV2-12`。

文件范围：

- 可写：`career_backend.py`、V2 增量/重建/失效测试、本文、完成报告、滚动摘要、任务清单。
- 禁止：真实库 apply、具体运动算法、前端、API contract JSON、打包产物。

冻结契约：

- 默认只分发 `available` definitions；`candidate_only/validation_required` 只进入计划摘要，不自动 apply。
- Activity 删除/修改必须失效相关 active record、curve cache、route signature/match，并尝试同 Scope fallback。
- Rebuild dry-run 不写库。
- Apply 必须在 savepoint 内执行；失败回滚，旧 active 保持可读。
- Rebuild summary 必须包含 sport/family/scope/reason。
- 不扫描未启用定义；不读取 raw FIT、完整轨迹、功率流、路径或设备标识。

实施步骤：

1. 新增安全 Activity sport 归一与 V2 definition dispatch plan。
2. 新增 Activity 影响范围计划：records/cache/route。
3. 新增 `invalidate_career_record_state_for_activity()`，支持 dry-run/apply、cache/route 失效、同 Scope fallback。
4. 新增 `plan_career_records_v2_rebuild()` 与 `rebuild_career_records_v2()`，输出 versioned run_id、批处理 summary、cancel/limit 支持和事务回滚。
5. 增加测试：dispatch available-only、dry-run 不写、删除失效+fallback、cache/route 失效、apply 回滚、batch/cancel、重复执行幂等、V1 回归。
6. 运行定向测试和 py_compile。

非目标：

- 不实现骑行功率曲线、徒步海拔、游泳 lap、越野路线匹配等算法。
- 不接真实库。
- 不修改前端或 pywebview API。

验证：

- `.venv312/bin/python -m pytest tests/test_career_record_v2_rebuild.py tests/test_career_record_v2_state.py -q`
- `.venv312/bin/python -m pytest tests/test_career_record_rebuild.py tests/test_career_record_lifecycle.py tests/test_career_record_incremental_evaluation.py -q`
- `.venv312/bin/python -m py_compile career_backend.py`

完成定义：

- 重复导入、更新、删除、rebuild dry-run/apply 不产生重复 active 或孤立事件。
- dry-run 不写库。
- apply 失败可回滚。
- V1 rebuild/lifecycle/incremental 测试无回归。

