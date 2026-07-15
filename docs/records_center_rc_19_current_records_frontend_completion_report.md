# RC-19 “记录”导航与当前纪录页面完成报告

完成日期：2026-07-13

## 本轮目标

将现有 PB 档案入口升级为记录中心的当前纪录视图入口，保持现有 DOM 与加载链路兼容。

## 实现范围

- `track.html`
  - 顶部运动生涯导航：`PB` 改为 `记录`。
  - PB 页面标题映射：`PB 成就` 改为 `记录中心`。
  - PB 区块可见标题：`PB 记录` 改为 `记录中心`。
  - 筛选 aria-label 与选项文案改为记录中心语义。
  - 当前纪录摘要显示 `待确认 N 项`，消费后端 `status.candidate_count`。
  - PB 卡片继续展示后端 `pb_title/value_display/improvement_display/confidence_label`，新增展示 `source_mode_label`。
  - 空态文案改为 `暂无当前纪录` / `暂无当前纪录数据`。
- `tests/test_career_archives_frontend_render.py`
  - 更新记录中心文案与当前纪录断言。
  - 增加 `pb` 页面标题映射与导航文案测试。
- `tests/test_career_phase8_frontend_readiness.py`
  - 更新主页面必备标签断言。

## 约束

- 内部 page key 仍保留 `pb`，避免扩大前端路由改动。
- 本轮只做当前纪录视图入口，不实现详情演进图与候选交互。
- 前端不计算 PB、improvement、confidence 或 record type。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py tests/test_career_phase8_frontend_readiness.py -q
# 18 passed

.venv312/bin/python -m pytest tests/test_career_archives_frontend_render.py tests/test_career_phase8_frontend_readiness.py tests/test_career_record_maintenance_api.py tests/test_career_pb_api.py tests/test_career_record_lifecycle.py tests/test_career_record_rebuild.py tests/test_career_record_incremental_evaluation.py tests/test_career_record_state_migration.py tests/test_career_record_schema_migration.py tests/test_career_record_registry.py tests/test_career_pb_resolver.py tests/test_career_timeline_pb_nodes.py -q
# 84 passed, 13 subtests passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 复核结论

RC-19 已完成“记录中心”的当前纪录前端入口。后续 RC-20 进入纪录详情与演进视图。

