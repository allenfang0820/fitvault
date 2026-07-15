# RCV2-35 工程级提示词：页面状态、响应式、无障碍与视觉截图

## 目标

完善 Records Center V2 的非理想状态、跨尺寸布局、键盘/无障碍体验，并产出可复验的视觉验收证据。该任务不改变纪录事实、算法或 API 语义。

## 范围

- `track.html`：
  - 增加 Records V2 状态条，覆盖 Loading、Empty、Partial、Candidate、Rebuilding、Error、Validation Required。
  - 左侧 group selector 支持键盘和窄屏横向选择器/单列下钻。
  - 当前纪录、候选、详情、图表和操作按钮补齐焦点样式、aria-label、aria-live、reduced motion。
  - 补齐 1100、980、720、520 窗口响应式规则；长中文、长成绩、多 Scope、大量候选不截断、不横向溢出。
- 新增前端静态测试，覆盖状态、响应式、a11y 和敏感字段边界。
- 尝试生成桌面/窄窗口截图；如浏览器工具不可用，在完成报告中记录限制与替代证据。

## 约束

- 不通过 `overflow:hidden` 掩盖布局问题；必要时使用 wrapping、grid/flex 自适应和 `overflow-wrap:anywhere`。
- 不在前端计算纪录事实、scope、confidence、improvement、axis direction 或候选状态。
- 不引入外部 CDN，不打包，不写真实库。
- 不修改 Records API 或 Resolver 语义。

## 预期文件

- `track.html`
- `tests/test_career_records_v2_responsive_a11y_frontend.py`
- `docs/records_center_v2_rcv2_35_visual_acceptance.md`
- `docs/records_center_v2_rcv2_35_completion_report.md`
- `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- `docs/records_center_v2_rolling_contract_summary.md`

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_responsive_a11y_frontend.py tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_frontend_shell.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- 状态、响应式和无障碍均有代码级测试覆盖。
- 宽/窄窗口视觉验收有截图或明确工具限制与替代证据。
- 不引入 raw FIT、track、power stream、GPS、路径、schema、设备或体重历史泄露。
