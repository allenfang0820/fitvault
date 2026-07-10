# ACS 任务清单状态回填完成报告

## 任务目标

将 `docs/脉图运动生涯系统（ACS）开发任务清单.md` 从初始规划清单回填为当前真实开发基线，避免已完成基础能力继续显示为未开始，并明确后续仍未闭环的产品与验收任务。

## 回填依据

- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
- `docs/acs_*_completion_report.md`
- `docs/acs_phase10_test_acceptance_matrix.md`
- `docs/js_api_contract.json`
- `career_backend.py`
- `main.py`
- `track.html`
- `tests/test_career*.py`

## 已回填完成项

- Phase0：ACS 一级导航、荣誉墙降级入口、`career_backend.py`、schema migration、API 契约、Snapshot DB 路径修复、派生索引边界。
- Phase1：FIT `sport_event` 赛事识别、`activities.is_race` 入库、用户手动赛事标记、Race Resolver、赛事候选、`get_career_races`、ACS 派生刷新。
- Phase2：跑步 PB、骑行 PB 基础能力、improvement、`get_career_pb`、PB 回跳 Activity Detail。
- Phase3：Achievement V1、`get_career_achievements`、代表性排序。
- Phase4：`get_career_overview`、Overview V1、Overview V2 Banner 与全量运动统计。
- Phase5：Timeline API 与前端渲染、筛选、分段渲染。
- Phase6：Memory Gallery 轻量闭环。
- Phase7：Career Snapshot 与本地 fallback Insight 轻量闭环。
- Phase8：前端主页面、档案列表、代码层跨平台视觉约束。
- Phase9：代码层路径、SQLite、数据边界、pywebview envelope、macOS 工作区轻量验收。
- Phase10：测试矩阵与 ACS 主回归收口。

## 保留未完成项

- 真实图片上传器 / 文件选择器。
- 媒体文件复制、删除与生命周期管理。
- 真实缩略图渲染。
- 轨迹截图自动生成。
- Overview Banner 真实照片模式。
- Race Map / 赛事足迹完整能力。
- 真实 AI Career Insight。
- macOS 打包产物验证。
- Windows 打包验证。
- Windows 真机验证。
- 真实数据端到端人工验收。

## 后续任务顺序

1. `ACS-Next-01`：赛事照片上传与 Banner 真实照片模式。
2. `ACS-Next-02`：Memory Gallery 媒体生命周期闭环。
3. `ACS-Next-03`：Race Map / 赛事足迹。
4. `ACS-Next-04`：真实 AI Career Insight 安全接入设计。
5. `ACS-Next-05`：macOS 打包产物验证。
6. `ACS-Next-06`：Windows 打包与真机验证。
7. `ACS-Next-07`：真实数据端到端人工验收。

## 未执行验收声明

本次任务只做文档状态校准与文档测试，不做产品代码开发，不执行 Windows 真机操作，不执行打包，不执行真实 AI 接入，不执行真实图片上传器开发，也不执行完整人工视觉验收。

未完成项仍以 `[ ]` 保留，不得因为代码层测试通过而误标完成。
