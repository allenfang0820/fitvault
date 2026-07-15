# RCV2-19 工程级执行提示词：骑行 Catalog、API、Curve ViewModel 与测试闭环

## 目标

补齐骑行记录中心后端只读表面：Catalog 分组和能力、当前纪录、历史、详情、PDC 曲线、W/kg 不可用状态、安全 API 与回归测试闭环。

## 输入摘要

- RCV2-14 已完成通用 Records API。
- RCV2-17 已完成固定功率锚点状态机。
- RCV2-18 已完成 W/kg gate 与骑行整次活动纪录。
- 前端不得读取 Activity raw data，不得自行判断 W/kg 或 PDC 可用性。

## 文件范围

- 允许修改：
  - `career_backend.py`
  - `docs/js_api_contract.json`
  - `tests/test_career_records_cycling_api_surface.py`
  - `docs/records_center_v2_rcv2_19_completion_report.md`
  - `docs/records_center_v2_rolling_contract_summary.md`
  - `docs/运动生涯记录中心V2（多运动纪录）开发任务清单.md`
- 不允许修改：
  - 前端
  - 真实数据库
  - 打包脚本或发布产物

## 契约边界

- 不新增写接口。
- 不返回 raw FIT、raw points、clean_points、power_points、本地路径、设备序列号或体重历史。
- 无逐点功率活动不得进入 PDC。
- model estimates 只能以 model-only 能力标签出现，不得成为 active record。

## 实施步骤

1. 补齐 cycling Catalog capabilities。
2. 用测试锁定 cycling_power / cycling_activity_total 分组。
3. 用测试锁定 Records API、Detail、History、Curve、Candidate 的骑行只读表面。
4. 更新 JS API contract 中 Catalog returns/description。
5. 跑骑行 Resolver/API/兼容回归。
