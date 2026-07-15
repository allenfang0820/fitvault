# RCV2-42 工程级执行提示词：macOS 当前环境、pywebview 与视觉验收

## 任务目标

在当前 macOS 源码环境验证 Records Center V2 的运行时、pywebview API bridge、视觉/响应式和数据边界，同时确认不执行任何打包动作。

## 输入摘要

- 当前任务：`RCV2-42 macOS 当前环境、pywebview 与视觉验收`。
- 前置：`RCV2-39` 自动化矩阵全绿，`RCV2-41` no-apply / keep-candidate 决策已记录。
- 用户仍未授权打包。

## 冻结契约

- 不运行 PyInstaller、DMG、签名、公证或发布包替换。
- 只允许源码/测试/只读 API 验证。
- 真实库不得因只读浏览被污染。
- 前端不得计算纪录事实、scope、confidence、improvement、axis direction。
- API/log/docs/UI 不得泄露 raw FIT、轨迹、路径、schema、体重详情或 candidate evidence。

## 文件范围

- 新增 `docs/records_center_v2_rcv2_42_macos_runtime_visual_report.md`
- 新增 `docs/records_center_v2_rcv2_42_completion_report.md`
- 如测试暴露问题，最小范围修复相关代码/测试。
- 更新任务清单与滚动摘要。

## 非目标

- 不打包。
- 不执行真实库 apply。
- 不要求 Windows 真机验证（RCV2-43）。

## 实施步骤

1. 检查 pywebview/import 和 main.Api bridge 可用性。
2. 通过 main.Api 只读调用验证 Records V2 Catalog、records、candidates、rebuild status、snapshot read envelope。
3. 记录真实库只读调用前后 hash/mtime/关键计数不变。
4. 运行 macOS/pywebview/envelope/frontend/视觉相关测试。
5. 检查打包脚本/产物状态，但不生成新包。
6. 若 Browser/GUI 截图不可用，记录限制并引用静态/测试证据。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_phase9_macos_closure.py tests/test_career_phase9_pywebview_envelope.py tests/test_response_envelope_contract.py -q
.venv312/bin/python -m pytest tests/test_career_records_v2_frontend_shell.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_responsive_a11y_frontend.py -q
.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase8_frontend_readiness.py tests/test_career_phase8_visual_density.py tests/test_career_phase9_data_boundary_audit.py -q
.venv312/bin/python -m py_compile career_backend.py main.py
```

## 完成定义

- macOS/pywebview/front-end/visual/data-boundary tests 通过。
- main.Api 只读 smoke 证明 envelope 可用且真实库不变。
- 完成报告写入。
- 任务清单标记 `RCV2-42 Done`、`RCV2-43 In Progress`。
