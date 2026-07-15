# RCV2-15 工程级执行提示词：骑行功率流规范化与质量检测

## 目标

实现 Records Center V2 专用的骑行功率流规范化与质量检测能力，把不同设备、不同采样频率的骑行功率点转换为后续 Power Duration Curve 可消费的稳定内部结构，并输出安全质量摘要与 reason codes。

## 输入摘要

- RCV2-14 已完成通用 Records API 与 V1 兼容包装器。
- Activity 仍是唯一事实源；Resolver/状态迁移服务是正式纪录唯一写入口。
- RCV2-15 不生成正式骑行功率纪录，不写真实库，不接入 `apply_record_evidence_state()`。
- 骑行功率契约：
  - 0W 是有效滑行值。
  - 缺失功率不是 0W。
  - 非 1Hz 采样必须按时间权重处理。
  - 窗口不得跨长暂停、断点、缺失流段或无效时间戳。
  - e-bike 不进入普通骑行功率纪录。
  - 汇总 `avg/max/NP` 不能替代逐点功率流。

## 文件范围

- 允许修改：
  - `career_backend.py`
  - `tests/test_career_record_cycling_power_stream.py`
  - `docs/records_center_v2_rcv2_15_completion_report.md`
  - `docs/records_center_v2_rolling_contract_summary.md`
  - `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 不允许修改：
  - 前端 `track.html`
  - 打包脚本或发布产物
  - 真实数据库
  - 与记录中心 V2 无关的年度总结、疲劳复盘或平台代码

## 契约边界

- 只实现 Power Stream Adapter 与质量 Resolver。
- 不创建 `career_pb_records` active 纪录。
- 不创建用户候选。
- 不把 W/kg、NP、eFTP、CP、W′、MAP、PMax 注册为正式纪录。
- API、日志、完成报告不得暴露 raw FIT、完整 points、原始 power stream、本地路径、设备序列号或体重历史。
- 内部规范化点可供后续算法使用，但对外只暴露安全质量摘要。

## 实施步骤

1. 在 `career_backend.py` 新增 Records V2 骑行功率流配置与 helper。
2. 支持从 `t/time/timestamp` 与 `power_w/power/watts/enhanced_power` 读取点。
3. 对时间戳做稳定归一：排序、去重/跳过无效、相对活动起点秒数。
4. 区分 0W、缺失值、负值/非数值、短时尖峰。
5. 按 `max_gap_sec` 识别不可跨越断点。
6. 按相邻采样间隔计算 time-weighted average、覆盖率和采样摘要。
7. 输出：
   - 内部 `clean_points`
   - 安全 `quality_summary`
   - `quality/confidence/reason_codes/candidate_only`
   - `scope`：`sport_scope/indoor_scope/power_metric_scope`
8. 用 golden fixture 中骑行功率 case 建立单测。

## 验证

优先运行：

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_power_stream.py tests/test_records_center_v2_golden_fixtures.py -q
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```

必要时加宽到 Registry/State/Rebuild 相关测试。

## 完成标准

- 相同功率流重复规范化输出稳定。
- 0W 被保留为有效值。
- 缺失功率、断点、尖峰和 e-bike 均输出冻结 reason code。
- 异常功率流不会得到高置信质量。
- 安全质量摘要不包含 raw point list、raw FIT、路径、设备序列号或体重历史。
- V1 PB 和 RCV2-14 API 测试无回归。
