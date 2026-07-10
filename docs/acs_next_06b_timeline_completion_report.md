---
title: ACS-Next-06B Timeline 核心浏览体验完成报告
status: Code-Level Complete
completed: 2026-07-10
source:
  - docs/acs_next_06b_timeline_design_guidance.md
  - docs/acs_next_06b_timeline_task_list.md
---

# ACS-Next-06B Timeline 核心浏览体验完成报告

## 结论

ACS-Next-06B Timeline 已完成代码级闭环。当前实现已从旧 Phase5 纵向节点列表迁移为 06B 核心浏览体验：

- 顶部年份胶囊：`全部 / 年份...`
- 顶部内容胶囊：`全部 / 赛事 / 里程碑`
- 后端 Timeline ViewModel 使用 `race / milestone`
- PB 不再作为独立 Timeline 节点，赛事 PB 以 `pb_badge_scope` 皇冠表达
- 月份内按横向日期轴展示
- 月份内分为赛事轨道和里程碑轨道
- 同月同轨高优先级节点直接展示，超量节点进入“更多”入口
- 里程碑使用 06B 白名单与 Timeline 专用派生层

本报告只代表当前 macOS 工作区代码层完成，不代表 Windows 真机、Windows 打包、macOS 打包产物或真实用户数据人工浏览已完成。

## 已完成任务

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| ACS-Next-06B-00 | 已完成 | 冻结 06B 契约与偏差基线，形成工程提示词执行记录 |
| ACS-Next-06B-01 | 已完成 | Timeline API ViewModel 迁移为 `race / milestone`，移除正式 PB node 和 Timeline Season 依赖 |
| ACS-Next-06B-02 | 已完成 | race node 增加 `pb_badge_scope`，前端渲染人生 PB / 当年 PB 皇冠 |
| ACS-Next-06B-03 | 已完成 | 建立 06B Timeline Milestone Resolver MVP，过滤旧 `first_city` / PB / Memory |
| ACS-Next-06B-04 | 已完成 | 前端迁移为年份胶囊、内容胶囊、月份横向双轨 |
| ACS-Next-06B-05 | 已完成 | 增加轨道级拥挤策略、错层和“更多”入口 |
| ACS-Next-06B-06 | 已完成 | 视觉、安全、验收矩阵和完成报告收口 |

## 自动化验收

已执行：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py -q
.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase9_data_boundary_audit.py -q
.venv312/bin/python -m py_compile career_backend.py main.py profile_backend.py
```

验收覆盖：

- Timeline API 不返回 PB 独立节点
- `type=all / race / milestone` 筛选稳定
- `achievement / achievements` 兼容映射到 `milestone`
- `type=pb` 稳定空结果
- `available_years / day / days_in_month / track / priority` 字段可用
- 赛事 PB 皇冠由后端 `pb_badge_scope` 驱动
- 里程碑排除 `first_city`、PB、Memory 和普通活动流水
- 前端不出现 PB 筛选、年份 select、运动类型 select 或 Season Summary 调用
- 前端存在横向月份 band、赛事/里程碑双轨、卡片定位、更多入口和错层
- ACS API 与前端渲染路径不暴露 raw FIT、points、track_json、file_path、storage_ref、本地绝对路径或 SQLite schema

## 未验证项

以下项目仍需后续人工或打包验收，不能在本报告中标记完成：

- Windows 真机运动生涯页面浏览
- Windows 打包产物运行
- macOS 打包产物运行
- 真实用户数据人工浏览
- 宽屏 / 窄屏实际窗口观感
- 大量真实月份节点下的滚动体感

## 后续建议

下一步建议进入人工视觉验收和真实数据浏览：

1. 使用真实运动数据打开 Timeline，检查年份胶囊、内容胶囊和月份双轨。
2. 检查人生 PB / 当年 PB 皇冠是否容易识别。
3. 检查同月同轨节点拥挤时“更多”入口和展开体验。
4. 分别在宽屏和窄窗口确认文字不溢出、卡片不遮挡关键内容。
