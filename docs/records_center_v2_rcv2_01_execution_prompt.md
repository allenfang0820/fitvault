# RCV2-01 工程级执行提示词

任务：多运动 Activity 事实源与真实数据审计

目标：确认骑行、徒步、游泳和越野所需 canonical 字段、时间语义、采样完整度和真实数据覆盖，为后续 Registry、质量评分、schema、fixture 和 Resolver 任务提供事实依据。

输入摘要：

- `RCV2-00` 已建立 V2 滚动摘要，确认 Activity 是唯一事实源，Resolver/状态迁移服务是正式纪录唯一写入口。
- V2 规则要求骑行读取逐点功率流，徒步读取距离/elapsed/爬升/海拔/轨迹，游泳区分泳池/公开水域并读取 pool length、stroke、Length/Lap，越野跑需要明确 `trail_running` 和轨迹质量。
- 当前代码已有 `activities` 表、`track_json/points_json/laps_json`、功率汇总字段、海拔字段和 FIT session/lap/record 解析链路，但不代表全部字段已满足 V2 正式纪录条件。

前置依赖：`RCV2-00`。

文件范围：

- 只读：`profile_backend.py`、`fit_engine.py`、`metrics_resolver.py`、`main.py`、`career_backend.py`、真实 SQLite 库。
- 可写：本提示词、`docs/records_center_v2_rcv2_01_activity_fact_source_audit.md`、`docs/records_center_v2_rcv2_01_completion_report.md`、V2 滚动摘要、V2 任务清单状态。
- 禁止：业务代码、真实库写入、staging apply、打包产物。

冻结契约：

- 不得从文件名或标题直接提升运动类型置信度。
- 只读审计，真实库必须使用只读连接或等价方式。
- 审计结论必须区分“字段存在”“字段语义可作为正式纪录”“只能候选/不可用”。
- 旧数据口径未知时标记为 candidate-only 或后续待验证，不能写成已正式支持。

实施步骤：

1. 读取滚动摘要、当前任务条目和 `RCV2-00` 完成报告。
2. 审计 FIT/GPX/provider 到 Activity 的事实链路，包括距离、时间、功率、海拔、Lap、泳姿、pool length 和轨迹。
3. 用真实库只读查询统计各运动数量、字段覆盖、功率流/Lap/轨迹/海拔质量和历史体重可关联性。
4. 标记无真实泳池样本、无真实越野样本、功率流缺失、pool length 缺失、stroke 缺失和时间语义不明等风险。
5. 形成多运动事实源审计报告和字段矩阵。
6. 刷新 V2 滚动摘要，更新任务清单状态。

非目标：

- 不实现 V2 Registry、schema migration、Resolver、API 或前端。
- 不生成 fixtures。
- 不确认候选，不写正式纪录。

验证：

- SQLite 只读查询成功且不改变数据库修改时间。
- 报告覆盖骑行、徒步、游泳、越野和历史体重。
- 运行与事实源相关的轻量回归：

```bash
.venv312/bin/python -m pytest tests/test_fit_sync.py -k "normalized_power or laps_json or activity_list" -q
.venv312/bin/python -m py_compile profile_backend.py fit_engine.py metrics_resolver.py main.py career_backend.py
```

完成定义：

- 每个 V2 Registry 方向都能指向明确 canonical 输入，或被标记为 unavailable/candidate-only/需要 fixture。
- 报告可直接作为 `RCV2-02` 和 `RCV2-03` 的输入。
