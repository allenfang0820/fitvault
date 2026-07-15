# RCV2-33 工程级提示词：多运动演进图、功率/Pace Curve 与路线对比

## 目标

在 Records Center V2 shell 中接入统一分析面板：历史演进、派生曲线和越野路线对比。不同运动使用各自后端 ViewModel，前端只负责展示，不反推纪录事实。

## 范围

- 在 `track.html` 新增通用 records chart engine。
- 接入 `get_career_record_history`、`get_career_record_curve`、`get_trail_route_comparison`。
- 提供 ECharts 可用时的图表渲染与不可用时的可访问列表 fallback。
- 覆盖 resize、隐藏/显示、切换、销毁的实例管理。
- 新增前端契约测试。

## 约束

- 只使用后端 Curve/History/Route Comparison ViewModel。
- 不解析 raw stream/track，不从 DOM/ECharts/curve 反算 PB。
- Pace/GAP analysis curve 不得标为 PB。
- 不引入外部 CDN。
- 不打包。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
.venv312/bin/python -m pytest tests/test_career_records_trail_api_surface.py tests/test_career_records_v2_api.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- 当前纪录选中后可加载 history/curve/route comparison。
- 图表模式按后端 axis direction 和 curve type 展示。
- 有可访问历史节点列表。
- ECharts 实例可 resize/dispose，不泄漏。
