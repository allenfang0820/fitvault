# ACS-Phase5-01 Timeline Engine 年月结构与筛选收口完成报告

## 任务范围

本任务对 ACS Timeline Engine 已有后端能力做 Phase 5 收口验证。

已完成：

- 新增集中回归测试 `tests/test_career_timeline_engine_closure.py`
- 验证 `get_career_timeline(type=all)` 聚合 race / pb / achievement
- 验证年份、月份与节点排序稳定
- 验证 `type`、`year`、`sport` 筛选边界
- 验证低置信度候选只计入 `candidates_count`，不进入正式 Timeline
- 验证所有 Timeline 节点保留 `detail_link`
- 验证 forbidden keys 不进入对外返回
- 更新 `docs/js_api_contract.json` 的 Timeline API 行为说明

未实现：

- Frontend Timeline UI
- Memory Timeline 节点
- Timeline 虚拟列表
- AI Snapshot / AI 洞察
- 新的 Race / PB / Achievement 识别规则

## 当前 Timeline Engine 契约

`get_career_timeline(filters)` 返回：

```json
{
  "filters": {
    "sport": "all",
    "year": null,
    "type": "all"
  },
  "years": [
    {
      "year": 2026,
      "months": [
        {
          "month": 5,
          "nodes": []
        }
      ]
    }
  ],
  "candidates_count": 0,
  "status": {
    "schema_ready": true,
    "data_ready": true,
    "message": "运动生涯时间轴已生成"
  }
}
```

支持的正式节点来源：

- `career_race_events WHERE status = 'active'`
- `career_pb_records WHERE status = 'active'`
- `career_achievement_events WHERE status = 'active'`

`career_event_candidates WHERE status = 'candidate'` 只进入 `candidates_count`。

## 筛选规则

已固化规则：

- `type=all`：返回 race / pb / achievement
- `type=race`：仅返回 race
- `type=pb`：仅返回 pb
- `type=achievement|achievements|milestone`：仅返回 achievement
- 未知 `type`：保留原输入 type，返回稳定空 `years`
- `year`：应用于 race / pb / achievement
- `sport`：只应用于 race / pb，不过滤 achievement

## 排序规则

Timeline 分组排序：

- 年份倒序
- 月份倒序
- 同月节点按 `date DESC, type DESC, id DESC`

当前排序由 `_group_timeline_nodes()` 集中处理。

## 安全边界

新增测试递归验证 Timeline 返回不包含：

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

所有正式节点必须包含：

```json
{
  "detail_link": {
    "activity_id": "<activity_id>",
    "source": "career"
  }
}
```

## macOS / Windows 兼容性

- 测试使用 `sqlite3.connect(":memory:")`
- 不依赖绝对路径
- 不依赖大小写敏感文件系统
- 中文标题与城市通过既有 Timeline 测试继续覆盖
- 不暴露本地路径给前端、AI 或 Snapshot
- pywebview API envelope 契约不变

## 修改文件

- `tests/test_career_timeline_engine_closure.py`
- `docs/js_api_contract.json`
- `docs/acs_phase5_01_timeline_engine_closure_completion_report.md`

本任务未修改 `career_backend.py`、`main.py` 或 `profile_backend.py` 的运行时代码。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_timeline_engine_closure.py
# 6 passed

python3 -m pytest tests/test_career_timeline_pb_nodes.py tests/test_career_timeline_achievement_nodes.py tests/test_career_overview_timeline_races.py
# 22 passed

python3 -m pytest tests/test_career_achievement_phase3_integration.py tests/test_career_api_skeleton.py tests/test_career_backend_schema.py
# 16 passed

python3 -m py_compile career_backend.py main.py profile_backend.py
# passed

python3 -m json.tool docs/js_api_contract.json
# passed
```

说明：pytest 期间存在 urllib3 / LibreSSL warning，为当前 macOS Python 环境提示，不影响本任务结果。

## 下一任务建议

建议进入：

`ACS-Phase5-02：Timeline 前端轻量渲染与筛选入口`

建议边界：

- 只消费 `get_career_timeline` API
- 新增运动生涯页中部时间轴轻量渲染
- 支持全部 / 赛事 / PB / 里程碑筛选
- 节点点击回跳 Activity Detail
- 不在前端计算赛事、PB 或成就事实
- 不实现 Memory Gallery
- 不生成 AI Snapshot
