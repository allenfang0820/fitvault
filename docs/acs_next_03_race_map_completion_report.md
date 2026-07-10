# ACS-Next-03 Race Map / 赛事足迹完整能力完成报告

## 任务范围

- 新增 `get_career_race_map` 只读 API。
- 赛事足迹仅使用 Race Resolver 生成的 active 赛事与 Activity 安全起点坐标。
- 前端足迹页展示年份/运动筛选、摘要指标、轻量点位视图和缺坐标赛事列表。
- 每个点位或列表项通过 `detail_link.activity_id` 返回 Activity Detail。

## 契约遵守

- `Activity` 仍是唯一事实源。
- ACS 只组织派生展示和安全媒体/地点引用。
- 前端不推断赛事、PB、成就、训练事实或坐标。
- Race Map 不返回完整路线 points、raw FIT、`points_json`、`track_json`、`file_path`、`storage_ref`、本地绝对路径或 SQLite schema。
- `without_coordinates` 只说明缺失或异常，不从标题、城市、日期补坐标。

## 非目标

- 不接入复杂地图引擎。
- 不做路线回放。
- 不做地理编码、逆地理编码或城市推断坐标。
- 不执行 macOS 打包产物验证。
- 不执行 Windows 打包或 Windows 真机验证。
- 不执行真实数据端到端人工验收。

## 验证记录

- 新增 `tests/test_career_race_map_api.py` 覆盖后端安全返回、缺坐标、非法坐标、筛选、删除活动排除、pywebview envelope 和 JS API contract。
- 新增 `tests/test_career_race_map_frontend.py` 覆盖足迹页 DOM、API 调用、白名单归一化、Activity Detail 点击回流与 `loadCareerData` 接入。
- 更新 `tests/test_career_phase9_macos_closure.py` 与任务清单状态测试。
