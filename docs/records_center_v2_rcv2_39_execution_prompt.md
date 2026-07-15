# RCV2-39 工程级执行提示词：V2 自动化测试矩阵与全量回归

## 任务目标

运行并修复 Records Center V2 自动化测试矩阵，证明多运动纪录扩展没有破坏 V1 跑步纪录、Records V2 API/Resolver/UI、安全边界和相邻 Activity 功能。

## 输入摘要

- 当前任务：`RCV2-39 V2 自动化测试矩阵与全量回归`。
- 前置条件：`RCV2-15` 至 `RCV2-38` 已完成。
- 最新基线：RCV2-38 安全/性能/日志/可观测性与兼容合并验证 `25 passed`；`career_backend.py` / `main.py` py_compile 通过；`docs/js_api_contract.json` JSON 解析通过。

## 冻结契约

- 不得为通过测试降低产品规则、删除断言或跳过失败用例。
- 不写真实库，不打包。
- 真实数据 apply 仍需用户明确授权。
- V1 跑步 PB 兼容、V2 多运动规则、candidate-only、analysis/model 边界和前端不计算事实等契约不能回退。

## 文件范围

- 以测试修复所需的最小代码/测试/doc 范围为准。
- 预期可能涉及：`career_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json`、相关 `tests/test_career_*` / activity 回归测试。
- 新增 `docs/records_center_v2_rcv2_39_completion_report.md`。
- 更新任务清单与滚动摘要。

## 非目标

- 不新增产品功能。
- 不重写 Resolver 规则。
- 不做真实数据 dry-run/apply（那是 RCV2-40）。
- 不打包。

## 验证矩阵

按失败定位优先级执行：

1. Records V2 定向矩阵：registry/schema/evidence/state/rebuild/API/各运动 resolver/frontend/snapshot/security。
2. 全部 `tests/test_career_*.py`。
3. Activity import/sync/delete/detail/refresh 相关回归。
4. Python compile、API JSON 解析、必要安全静态检查。

## 差异复核

- 每次修复后重跑失败组和相关邻近组。
- 确认没有降低断言或移除测试覆盖。
- 确认修复没有扩大真实写权限或泄露敏感字段。
- 若失败属于环境缺失或历史无关失败，记录证据与替代验证；只有连续修复失败或需要用户产品判断时停止。

## 完成定义

- 所有适用矩阵测试全绿，或环境性未执行项有明确替代证据。
- 完成报告写入。
- 任务清单标记 `RCV2-39 Done`、`RCV2-40 In Progress`。
- 滚动摘要刷新到 RCV2-40。
