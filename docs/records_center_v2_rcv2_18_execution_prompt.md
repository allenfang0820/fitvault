# RCV2-18 工程级执行提示词：骑行 W/kg 门禁与整次活动纪录

## 目标

实现骑行整次活动纪录 resolver：最长距离、最大爬升、最长 elapsed time、最大机械功；同时冻结 W/kg 门禁，确保无可靠历史体重时不创建 W/kg fact、candidate 或 active record。

## 输入摘要

- RCV2-17 已完成骑行固定功率锚点正式纪录。
- Registry 中骑行整次活动纪录包括：
  - `cycling_longest_distance`
  - `cycling_max_ascent`
  - `cycling_longest_elapsed_time`
  - `cycling_max_work`
- `cycling_max_work` 当前 `availability_state=validation_required`，不得 auto-confirm。
- W/kg 不在当前 active Registry 中，不得使用当前体重回填历史活动。

## 文件范围

- 允许修改：
  - `career_backend.py`
  - `tests/test_career_record_cycling_activity_total.py`
  - `docs/records_center_v2_rcv2_18_completion_report.md`
  - `docs/records_center_v2_rolling_contract_summary.md`
  - `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 不允许修改：
  - 前端
  - 真实数据库
  - 打包脚本或发布产物
  - W/kg active Registry

## 契约边界

- 不实现最快均速核心纪录。
- 不使用当前体重回填历史。
- 无可靠历史体重时不创建 W/kg fact 或候选。
- 室内无距离/爬升时返回 not applicable，不写 0。
- 默认 dry-run。

## 实施步骤

1. 新增骑行整次活动 facts 解析 helper。
2. 新增 W/kg gate helper。
3. 新增整次活动 evidence builder。
4. 新增默认 dry-run 的 apply wrapper。
5. 测试距离、爬升、历时、机械功、室内 not applicable、W/kg missing gate 和 e-bike 排除。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_cycling_activity_total.py tests/test_career_record_cycling_power_resolver.py -q
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```
