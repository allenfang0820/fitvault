# ACS-Phase1-05 Overview / Timeline 赛事联动完成报告

## 任务范围

本任务将 Race Resolver 与 `get_career_races` 已生成的正式赛事轻量接入现有 ACS 只读骨架：

- `get_career_overview()` 返回 `latest_race`
- `get_career_timeline()` 返回基础赛事时间轴节点
- 更新 `docs/js_api_contract.json`
- 新增后端测试

未实现：

- 前端 UI
- PB / Achievement / Memory
- AI Snapshot / AI 洞察
- 自动执行 Race Resolver
- low candidate 晋级正式节点

## 修改文件

- `career_backend.py`
- `docs/js_api_contract.json`
- `tests/test_career_overview_timeline_races.py`
- `docs/acs_phase1_05_overview_timeline_race_linkage_completion_report.md`

## Overview latest_race 结构

`get_career_overview()` 现在从 `career_race_events.status='active'` 读取最新赛事，返回：

```json
{
  "id": "race:123",
  "activity_id": "123",
  "name": "2026 成都半程马拉松",
  "event_type": "half_marathon",
  "sport": "running",
  "event_date": "2026-05-19",
  "city": "成都",
  "confidence": 1.0,
  "source": "user",
  "confidence_level": "high",
  "display_metadata": {},
  "detail_link": {
    "activity_id": "123",
    "source": "career"
  }
}
```

空状态继续返回：

```json
"latest_race": null
```

## Timeline years / months / nodes 结构

`get_career_timeline()` 现在在 `type == 'all'` 或 `type == 'race'` 时读取正式赛事，并组织为：

```json
{
  "years": [
    {
      "year": 2026,
      "months": [
        {
          "month": 5,
          "nodes": [
            {
              "id": "race:123",
              "type": "race",
              "activity_id": "123",
              "title": "2026 成都半程马拉松",
              "event_type": "half_marathon",
              "sport": "running",
              "date": "2026-05-19",
              "city": "成都",
              "confidence": 1.0,
              "source": "user",
              "detail_link": {
                "activity_id": "123",
                "source": "career"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

排序规则：

- 年份倒序
- 月份倒序
- 节点按 `date DESC, id DESC`

## filters 行为

`get_career_timeline(filters)` 保持既有 filters：

- `sport`
- `year`
- `type`

行为：

- `type == 'all'`：返回当前支持的赛事节点
- `type == 'race'`：返回赛事节点
- `type == 'pb'` 等其他类型：返回空 `years`
- `sport != 'all'`：只返回对应运动类型
- `year != None`：只返回对应年份

## low candidate 不进入 timeline

Timeline 只读取 `career_race_events.status='active'`。

`career_event_candidates.status='candidate'` 只影响 `candidates_count`，不会进入 `years[].months[].nodes[]`。

测试 `test_low_candidate_does_not_enter_timeline` 已覆盖。

## forbidden fields 验证

新增测试递归检查 overview / timeline 响应不包含：

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

## macOS / Windows 兼容性

- 默认连接继续使用 `profile_backend.DB_PATH`。
- 测试通过 `tempfile.TemporaryDirectory()` 与 `Path` 创建临时 SQLite 文件。
- 不硬编码系统路径。
- 不暴露本地绝对路径。
- 中文赛事名和城市继续沿用 JSON `ensure_ascii=False` 的数据。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_overview_timeline_races.py
# 9 passed

python3 -m pytest tests/test_career_races_api.py tests/test_career_race_resolver.py
# 15 passed

python3 -m pytest tests/test_career_backend_schema.py tests/test_career_api_skeleton.py
# 12 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed

python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
# 14 passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

原计划下一阶段建议进入：

`ACS-Phase2-01：PB Engine 后端 Resolver 骨架`

建议边界：

- 只从 Activity 安全摘要字段识别 PB。
- 优先支持跑步 5K / 10K / 半马 / 全马。
- 写入 `career_pb_records`。
- 不接前端 UI。
- 不生成 AI Snapshot。
