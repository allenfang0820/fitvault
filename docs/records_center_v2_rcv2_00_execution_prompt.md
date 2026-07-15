# RCV2-00 工程级执行提示词

任务：V2 基线审计与滚动摘要初始化

目标：建立记录中心 V2 的唯一可信起点，让后续任务可以优先阅读滚动摘要，而不是反复全文重读交付手册、旧任务清单和代码。

输入摘要：

- V2 交付手册冻结记录中心 V2 为多运动纪录体系，继承 V1 跑步四项，新增骑行、徒步、游泳和越野跑。
- V1 交付手册和滚动摘要显示 RC-00 至 RC-27 已完成，RC-28 至 RC-30 的发布门禁已被 V2 新清单取代。
- 当前代码仍以 `career_pb_records`、`career_record_events`、`career_event_candidates` 和 `get_career_pb*` 为兼容核心。
- 用户决策仍是：不确定跑步结果保持候选，不写真实库；暂时不要打包。

前置依赖：无。

文件范围：

- 只读：`career_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json`、V1/V2 手册和任务清单、V1 滚动摘要。
- 可写：`docs/records_center_v2_rolling_contract_summary.md`、`docs/records_center_v2_rcv2_00_baseline_audit_completion_report.md`、本提示词、V2 任务清单状态。
- 禁止：业务代码、真实数据库、打包产物、无关工作区改动。

冻结契约：

- Activity 是唯一事实源。
- Resolver/状态迁移服务是正式纪录唯一写入口。
- 前端只渲染 ViewModel，不计算纪录、Scope、提升量或置信度。
- AI 只消费安全 Snapshot，不读取 raw FIT、功率流、轨迹、路径、schema 或体重历史。
- `career_pb_records`、`career_record_events`、`career_event_candidates` 继续兼容。
- `get_career_pb*` 和 `detail_link.source = "career"` 继续兼容。
- 置信度阈值为 `>0.90` 自动确认，`0.70-0.90` 候选，`<0.70` 忽略，边界 `0.70/0.90` 均为候选。
- 跑步 V1 四项结果不得因 V2 改变。
- 未通过真实数据验收的运动必须在 Catalog 中 `available=false` 或 validation required。
- 没有用户批准不得 apply 真实库；没有用户解除限制不得打包。

实施步骤：

1. 全文阅读 V2 手册、V2 任务清单、V1 手册、V1 任务清单、V1 滚动摘要和 Career API 契约片段。
2. 审计当前核心代码状态，区分已完成 V1、V2 目标、遗留 UI 占位和无关工作区改动。
3. 运行基线验证：Career/Records 定向测试、Python compile、API JSON 校验。
4. 创建 V2 滚动摘要，记录后续任务的读取规则、任务顺序、全局硬约束、当前代码事实、数据决策和遗留清理队列。
5. 创建完成报告，记录验证命令、结果、diff 范围和下一任务。
6. 更新 V2 任务清单：`RCV2-00` 标记为 Done，当前下一任务改为 `RCV2-01`。

非目标：

- 不实现 Registry V2。
- 不修改 schema、Resolver、API 或前端。
- 不写真实库，不执行 staging apply。
- 不启动 macOS/Windows 打包。

验证：

```bash
.venv312/bin/python -m pytest tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python -m json.tool docs/js_api_contract.json
```

完成定义：

- V2 滚动摘要能准确复述事实源、规则、任务顺序、当前风险和文件边界。
- 完成报告包含测试结果和 diff 复核结论。
- 任务清单状态进入 `RCV2-01`。
