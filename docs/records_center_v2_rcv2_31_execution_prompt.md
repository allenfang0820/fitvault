# RCV2-31 工程级提示词：越野 Catalog、API、fixture 与测试闭环

## 目标

整合越野整次纪录、route/segment PR 和 Pace/GAP analysis curve 的 Catalog/API 可见性，让前端能准确区分正式当前纪录、候选路线 PR、候选赛段 PR 与分析曲线。

## 范围

- 增强 `trail_running` Catalog capabilities。
- 新增 route comparison 安全 ViewModel/API helper。
- 确认 `get_career_records`、detail/history、candidates、curve 能覆盖越野状态。
- 更新 `docs/js_api_contract.json`。
- 新增越野 API surface 测试。

## 约束

- 不因 fixture 全绿宣称真实数据 Verified。
- route/segment 在无真实样本时保持 `candidate_only`，不开放正式可用态。
- Pace/GAP 是 `analysis_only` 能力，不注册为正式 record。
- API 不返回 route signature 原文、raw track、GPS 点、polyline、路径、设备/账号/体重等敏感字段。
- 不写真实库；测试使用内存 SQLite。
- 不打包。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_trail_api_surface.py tests/test_career_record_trail_route_segment_resolver.py tests/test_career_record_trail_pace_gap_curve.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_record_registry.py tests/test_records_center_v2_golden_fixtures.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- Catalog 明确 whole-activity、route/segment、analysis curve 三类状态。
- Route comparison ViewModel 只返回安全匹配摘要。
- 越野 candidates/curve/detail/history API 均通过安全测试。
- API contract 更新并与后端行为一致。
