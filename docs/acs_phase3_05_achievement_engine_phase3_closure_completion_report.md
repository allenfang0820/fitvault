# ACS-Phase3-05 Achievement Engine Phase 3 收口与回归完成报告

## 任务范围

本任务对 Achievement Engine Phase 3 已完成能力做集成收口，验证：

- Achievement Resolver
- `get_career_achievements`
- Achievement Timeline 节点
- Overview 代表成就

已完成：

- 新增 `tests/test_career_achievement_phase3_integration.py`
- 验证 Resolver → API → Timeline → Overview 只读链路
- 验证过滤、排序、代表成就一致性
- 验证空状态与 inactive / superseded 降级
- 验证 forbidden keys 不进入对外返回

未实现：

- Frontend UI
- 新成就类型
- Achievement Resolver 识别规则调整
- Race / PB 规则调整
- Memory Gallery
- AI Snapshot / AI 洞察

## Phase 3 已完成能力

### Achievement Resolver

- 从 Activity 安全摘要派生成就事件
- 写入 `career_achievement_events`
- 只保留 active 成就进入消费端
- 支持首次距离、最长跑步、最长骑行、最大爬升、首次城市等 V1 成就
- 不读取 raw FIT、points、track_json、file_path 或 SQLite schema

### Achievements API

- `get_career_achievements` 只读返回 active achievements
- 支持 `achievement_type` / `type` / `year` / `source` / `min_score`
- 排序规则：

```text
score DESC
event_date DESC
id DESC
```

- 返回 `summary`
- 每条成就包含 `detail_link`

### Timeline

- `get_career_timeline(type=all)` 包含 race / pb / achievement
- `get_career_timeline(type=achievement|achievements|milestone)` 只返回 achievement
- achievement node 保留 Activity Detail 回跳

### Overview

- `summary.achievement_count` 统计 active achievements
- `representative_achievements` 取 API 排名前 4 条
- 空状态稳定可用

## 集成链路验证结果

新增集成测试覆盖：

1. 构造内存 SQLite `activities` 表与多条可触发成就的 Activity。
2. 调用 `ensure_career_schema(conn)`。
3. 调用 `resolve_achievement_events(conn)`。
4. 调用：
   - `get_career_achievements(conn=conn)`
   - `get_career_timeline({"type": "achievement"}, conn)`
   - `get_career_timeline({"type": "all"}, conn)`
   - `get_career_overview(conn)`
5. 断言：
   - API active achievements 数量大于 0
   - Timeline achievement node 数量与 API active achievements 一致
   - Overview `summary.achievement_count` 与 API active achievements 一致
   - Overview `representative_achievements` 等于 API 前 4 条
   - 所有成就、Timeline 节点、Overview 代表成就都包含：

```json
{
  "detail_link": {
    "activity_id": "<activity_id>",
    "source": "career"
  }
}
```

## 过滤与排序验证

已验证：

- `get_career_achievements({"year": "2026"})` 只返回 2026 成就
- `get_career_timeline({"type": "achievement", "year": "2026"})` 与 API 的 2026 成就集合一致
- `min_score` 只影响 `get_career_achievements`
- Overview / Timeline 不受 `min_score` 影响
- API 排序保持 `score DESC, event_date DESC, id DESC`
- Overview representatives 等于 API 前 4 条

## 安全边界验证

对 API、Timeline、Overview 返回结果递归检查，确认不包含：

- `points`
- `points_json`
- `track_json`
- `raw_records`
- `fit_records`
- `file_path`
- `advanced_metrics`
- `shadow_diff_json`
- `sqlite_schema`
- `schema`

测试活动表中刻意包含 forbidden 原始字段，Phase 3 对外链路未返回这些字段。

## 空状态与降级

已验证：

- 无 `activities` 表时 resolver 不报错
- 无 achievements 时 API / Timeline / Overview 稳定返回空结构
- 只有 inactive / superseded achievements 时：
  - API 不返回 achievements
  - Timeline 不生成 achievement nodes
  - Overview `achievement_count = 0`
  - Overview `representative_achievements = []`

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不硬编码系统路径
- 不依赖大小写敏感文件系统
- 不暴露本地绝对路径
- pywebview API envelope 契约不变
- 中文 title / description 已由 Phase 3 既有测试覆盖

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_achievement_phase3_integration.py
# 4 passed

python3 -m pytest tests/test_career_achievement_resolver.py tests/test_career_achievements_api.py tests/test_career_timeline_achievement_nodes.py tests/test_career_overview_representative_achievements.py
# 30 passed

python3 -m pytest tests/test_career_overview_pb_summary.py tests/test_career_overview_timeline_races.py tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 27 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase4-01：Career Overview API 完整总览收口`

建议边界：

- 收口 Overview 后端聚合字段
- 明确 Race / PB / Achievement / Activity summary 的组合契约
- 不做前端 UI
- 不生成 AI Snapshot
