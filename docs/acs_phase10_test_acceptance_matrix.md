# ACS Phase10 测试与验收矩阵

## 范围

本文档整理 Athlete Career System（ACS）当前开发成果的自动化测试、人工验收与后置打包验证状态。矩阵只代表当前 macOS 工作区代码层结论；Windows 真机、Windows 打包与 macOS 打包产物验证仍需在后续阶段执行。

## 总体结论

- 自动化主链路已覆盖 Phase0-Phase9 与 ACS-Next-06B Timeline 的后端 resolver、API envelope、前端静态渲染、数据边界与代码层跨平台约束。
- ACS 仍保持 Activity 单一事实源；赛事、PB、成就、时间线事实由后端 resolver/API 生成，前端只渲染 view model。
- Career Snapshot / Insight 仍保持白名单与本地 fallback，未接入真实 LLM 调用。
- Windows 真机、Windows 打包、macOS 打包产物与完整人工视觉验收未完成，不得标记为已验收。

## 自动化验收矩阵

| 模块 / Phase | 能力范围 | 主要代码文件 | 测试文件 | 自动化状态 | 需要人工验证项 | Windows / 打包状态 | 风险备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Phase0 架构与 schema | ACS 架构基线、`career_backend.py`、schema migration、只读 API 骨架、一级导航空壳 | `career_backend.py`, `main.py`, `track.html`, `docs/js_api_contract.json` | `tests/test_career_backend_schema.py`, `tests/test_career_api_skeleton.py`, `tests/test_track_html_sync_logic.py` | 已覆盖 | 一级导航在真实应用窗口中的首屏观感 | 未打包验证 | 需持续防止 ACS 复制 Activity 原始事实字段 |
| Phase1 赛事识别与赛事档案 | FIT `sport_event` 入库、用户手动赛事标记、Race Resolver、赛事 API、Overview/Timeline 联动 | `fit_engine.py`, `main.py`, `career_backend.py`, `docs/js_api_contract.json` | `tests/test_fit_sport_event_race.py`, `tests/test_activity_race_flag_api.py`, `tests/test_career_race_resolver.py`, `tests/test_career_races_api.py`, `tests/test_career_overview_timeline_races.py` | 已覆盖 | 用户实际导入 FIT 后的赛事标记体验 | Windows 未验证 | Strava/第三方 FIT 不保证包含 Garmin `sport_event` |
| Phase2 PB Engine | PB Resolver、PB API、PB 时间线节点、Overview PB 摘要 | `career_backend.py`, `main.py`, `track.html` | `tests/test_career_pb_resolver.py`, `tests/test_career_pb_api.py`, `tests/test_career_timeline_pb_nodes.py`, `tests/test_career_overview_pb_summary.py` | 已覆盖 | PB 文案与排序是否符合产品感知 | 未打包验证 | 仅基于当前规则识别，不覆盖所有 PB 类型 |
| Phase3 Achievement Engine | 成就 Resolver、成就 API、成就时间线节点、Overview 代表成就、Phase3 闭环 | `career_backend.py`, `main.py`, `track.html` | `tests/test_career_achievement_resolver.py`, `tests/test_career_achievements_api.py`, `tests/test_career_timeline_achievement_nodes.py`, `tests/test_career_overview_representative_achievements.py`, `tests/test_career_achievement_phase3_integration.py` | 已覆盖 | 图标、标题、代表成就选择的产品细节 | 未打包验证 | 成就规则后续扩展时需保持可追溯 Activity |
| Phase4 Career Overview | Overview API 闭环、前端轻量渲染、活动详情回跳 | `career_backend.py`, `main.py`, `track.html` | `tests/test_career_overview_api_closure.py`, `tests/test_career_overview_frontend_integration.py`, `tests/test_career_overview_frontend_render.py`, `tests/test_career_overview_activity_detail_link.py` | 已覆盖 | Overview 在真实数据量下的信息密度与点击体验 | 未打包验证 | 回跳必须继续复用现有 Activity Detail，不新开事实 API |
| Phase5 Timeline Engine / ACS-Next-06B | Timeline 06B ViewModel、赛事 PB 皇冠、里程碑 Resolver MVP、年份胶囊、内容胶囊、月份横向双轨、更多入口、大数据量渲染 | `career_backend.py`, `track.html` | `tests/test_career_timeline_engine_closure.py`, `tests/test_career_timeline_milestone_nodes.py`, `tests/test_career_overview_timeline_races.py`, `tests/test_career_timeline_pb_nodes.py`, `tests/test_career_timeline_frontend_render.py`, `tests/test_career_timeline_frontend_visual_contract.py`, `tests/test_career_timeline_frontend_filters.py`, `tests/test_career_timeline_frontend_large_render.py` | 已覆盖代码层 | 宽屏/月轨道观感、窄窗口退化、真实数据月份拥挤体感、PB 皇冠识别感 | Windows 未验证，打包未验证 | 前端筛选只传控制参数，不本地重算事实；PB 不作为独立 Timeline 节点，记忆类暂不进入主轴 |
| Phase6 Memory Gallery | 记忆相册轻量契约、故事绑定、故事编辑/停用、媒体引用安全、闭环文档 | `career_backend.py`, `main.py`, `track.html` | `tests/test_career_memory_api.py`, `tests/test_career_memory_frontend_render.py`, `tests/test_career_memory_story_api.py`, `tests/test_career_memory_story_frontend.py`, `tests/test_career_memory_story_edit_api.py`, `tests/test_career_memory_story_edit_frontend.py`, `tests/test_career_memory_media_api.py`, `tests/test_career_memory_media_frontend.py`, `tests/test_career_memory_phase6_closure_docs.py` | 已覆盖 | 中文故事输入、停用操作的真实交互手感 | Windows 中文路径未验证 | API 不返回 `storage_ref`，媒体文件复制/删除尚非本阶段能力 |
| Phase7 Snapshot / Insight | Career Snapshot builder、持久化、Insight API 骨架、前端占位与视觉验收、Phase7 闭环 | `career_backend.py`, `main.py`, `track.html` | `tests/test_career_snapshot_builder.py`, `tests/test_career_snapshot_persistence.py`, `tests/test_career_insight_api_skeleton.py`, `tests/test_career_insight_frontend_render.py`, `tests/test_career_insight_frontend_visual_contract.py` | 已覆盖 | AI 洞察真实接入前的产品提示语 | 未接入真实 AI | 当前 Insight 为本地 fallback，不调用 LLM |
| Phase8 Frontend readiness / visual contract | ACS 页面审计与重排、视觉密度、Archives 只读列表、跨平台视觉契约代码层 | `track.html` | `tests/test_career_phase8_frontend_readiness.py`, `tests/test_career_phase8_visual_density.py`, `tests/test_career_archives_frontend_render.py`, `tests/test_career_phase8_cross_platform_visual_contract.py`, `tests/test_career_timeline_frontend_visual_contract.py`, `tests/test_career_insight_frontend_visual_contract.py` | 已覆盖代码层 | 真实应用窗口、不同宽度、滚动条、字体渲染 | Windows 真机未验证 | 视觉契约测试不能替代人工观感验收 |
| Phase9 跨平台代码层兼容与数据边界 | SQLite 路径、中文文件名、media_ref 安全、API envelope、数据边界、前端零推断、macOS 代码层收口 | `career_backend.py`, `main.py`, `track.html`, `docs/js_api_contract.json` | `tests/test_career_phase9_pywebview_envelope.py`, `tests/test_career_phase9_data_boundary_audit.py`, `tests/test_career_phase9_macos_closure.py`, `tests/test_career_backend_schema.py`, `tests/test_career_memory_media_api.py`, `tests/test_career_snapshot_persistence.py` | 已覆盖代码层 | macOS 打包产物运行、应用受控目录读写 | Windows 真机与打包未完成 | 不得把代码层通过等同于跨系统验收完成 |
| Phase10 测试与验收矩阵 | 测试覆盖梳理、验收边界沉淀、后续人工/打包验证入口 | `docs/acs_phase10_test_acceptance_matrix.md`, `docs/脉图运动生涯系统（ACS）开发任务清单.md` | `tests/test_career_phase10_acceptance_matrix_docs.py` | 已覆盖文档完整性 | 按矩阵执行人工验收 | Windows/打包后置 | 矩阵需随后续验收结果持续更新 |

## 自动化测试命令

推荐 ACS 主回归：

```bash
python3 -m pytest tests/test_career*.py tests/test_track_html_sync_logic.py
```

可选补充赛事/FIT 入口回归：

```bash
python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
```

## 已完成的自动化验收

- 后端 schema migration 幂等与中文/空格路径代码层验证。
- Race Resolver / PB Resolver / Achievement Resolver 规则与 API 输出验证。
- Overview / Timeline / Archives / Memory / Insight 前端静态渲染与 API 调用验证。
- Timeline 06B 核心浏览体验：年份胶囊、`全部 / 赛事 / 里程碑` 内容胶囊、月份横向双轨、PB 皇冠、里程碑白名单和轨道级“更多”入口。
- Activity Detail 回跳链路验证。
- Career Snapshot 白名单、持久化与历史脏内容清洗验证。
- pywebview API envelope `{ok, code, msg, data, traceId}` 验证。
- ACS public API、Snapshot、Insight 不泄露 raw FIT、points、track_json、file_path、storage_ref、SQLite schema、本地绝对路径。
- Career 前端不从原始轨迹、距离、配速、`sport_event` 或 `race_confidence` 推断赛事/PB/成就事实。

## 最新主回归记录

`ACS-Phase10-02` 已执行以下自动化回归：

```bash
python3 -m pytest tests/test_career*.py tests/test_track_html_sync_logic.py
```

结果：`323 passed`。

```bash
python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
```

结果：`14 passed`。

静态契约检查未发现 ACS 范围内的新风险。`track.html` 中命中的 `call_llm`、`file_path`、`points` 等字段属于既有非 ACS 轨迹、复盘或通用 AI 链路；ACS 相关入口仍由 Phase9 数据边界与前端零推断测试覆盖。

`ACS-Next-06B Timeline` 已执行以下代码级验收：

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_engine_closure.py tests/test_career_timeline_milestone_nodes.py tests/test_career_overview_timeline_races.py tests/test_career_timeline_pb_nodes.py -q
```

结果：通过。

```bash
.venv312/bin/python -m pytest tests/test_career_timeline_frontend_render.py tests/test_career_timeline_frontend_filters.py tests/test_career_timeline_frontend_visual_contract.py tests/test_career_timeline_frontend_large_render.py -q
```

结果：通过。

```bash
.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase9_data_boundary_audit.py -q
```

结果：通过。

06B 结论仅代表当前 macOS 工作区代码层闭环；真实用户数据人工浏览、Windows 真机、Windows 打包与 macOS 打包产物仍未验证。

## 仍需人工或打包验证

- macOS 打包产物验证：
  - 应用受控目录可读写。
  - 中文标题、中文文件名与图标渲染正常。
  - 深色 UI 对比度、滚动、窗口尺寸正常。
- Windows 打包后验证：
  - SQLite 可读写。
  - FIT 导入后 ACS 可刷新。
  - 中文文件名与中文标题编辑正常。
  - 时间轴滚动不卡顿。
- Windows 真机运动生涯页面验证：
  - 中文字体与 emoji/icon 混排正常。
  - 窄窗口无横向溢出。
  - pywebview 初始化慢或接口暂不可用时，各 Career 区块只显示局部错误态。
  - Overview / Timeline / Archives / Memory / Insight 滚动体验正常。
- 真实数据人工验收：
  - 导入 FIT 后生成 ACS 派生数据。
  - 删除 Activity 后 ACS 不显示孤儿事件。
  - 修改活动标题后，赛事命名与 Activity Detail 回跳体验符合预期。

## 验收红线

- 不影响现有个人运动数据、活动列表、活动详情与轨迹复盘。
- 所有 ACS 数据必须可追溯到 Activity。
- AI 不能修改事实数据，不能写回 canonical，不能绕过 Career Snapshot 白名单。
- 前端不能补算赛事、PB、成就、时间线事实。
- 未完成 Windows 真机/打包验证前，不得勾选 Windows 相关验收项。
