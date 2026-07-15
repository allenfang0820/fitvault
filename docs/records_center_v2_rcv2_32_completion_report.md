# RCV2-32 完成报告：多运动页面外壳、Catalog 页签与当前纪录视图

## 结果

已在现有“运动生涯 > 记录中心”中加入 Records Center V2 多运动外壳。新视图消费后端 Catalog、当前纪录和候选 ViewModel，能区分当前纪录、演进、候选三个视图，并展示 Catalog 驱动的运动页签、分组和当前纪录卡。

## 实现内容

- 新增 Records Center V2 DOM：
  - `career-records-v2-shell`
  - `career-record-sport-tabs`
  - `career-record-view-tabs`
  - `career-record-groups`
  - `career-record-current-list`
- 新增视觉样式：
  - 多运动卡片式外壳。
  - Catalog sport tab。
  - 左侧分组卡。
  - 当前纪录卡、candidate/analysis 状态徽标。
- 新增前端 ViewModel 函数：
  - `normalizeCareerRecordCatalog()`
  - `normalizeCareerRecordV2()`
  - `normalizeCareerRecordCandidateV2()`
  - `renderCareerRecordsCenter()`
  - `loadCareerRecordsCenter()`
  - `setCareerRecordSport()`
  - `setCareerRecordView()`
- 加载流程：
  - `loadCareerData()` 会并行加载 Records Center V2。
  - 切到 `pb` / 记录中心页时会刷新 V2 shell。
- 移除旧记录筛选中的未实现骑行 `cycling_avg_speed / 最快均速` 占位。

## 契约确认

- 前端运动页签从 `get_career_record_catalog()` 渲染，不硬编码开放未验收运动。
- 前端不计算 PB/纪录事实、总提升、可用性、置信度或轴方向。
- 当前纪录卡只展示后端 `metric.display`、`scope.labels`、`improvement.display`、`catalog_state` 等 ViewModel 字段。
- 候选不会渲染为当前纪录。
- 保留现有运动生涯全局导航，没有复制参考稿独立顶栏。
- 未打包。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_frontend_shell.py tests/test_career_archives_frontend_render.py tests/test_career_phase8_frontend_readiness.py -q
# 26 passed

.venv312/bin/python -m pytest tests/test_career_records_trail_api_surface.py tests/test_career_records_cycling_api_surface.py tests/test_career_records_hiking_api_surface.py tests/test_career_records_swim_api_surface.py tests/test_career_records_v2_api.py -q
# 15 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 后续

RCV2-33 可在 V2 shell 基础上接入多运动演进图、功率/Pace Curve 与路线对比；前端仍只能读取后端 ViewModel 和 curve API。
