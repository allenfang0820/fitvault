# ACS-Next-01A 赛事奖牌列与用户覆盖闭环完成报告

## 完成内容

- 活动列表新增独立「赛事」列，位置位于「时间」与「标题」之间。
- 移除标题旁「标为赛事 / 赛事」文字按钮，标题区域只保留标题文本与编辑入口。
- 赛事入口改为奖牌按钮：
  - 点亮 `🏅`：当前活动为赛事。
  - 灰阶未点亮 `🏅`：当前活动不是赛事。
  - 点击后立即调用 `set_activity_race_flag` 写入后端，不弹窗。
- 前端只使用后端返回的 `item.is_race` 渲染赛事状态，不根据标题、距离、城市或时间自行推断。
- Race Resolver 补充测试：城市 / 时间信息单独存在时，不生成正式赛事，也不生成赛事候选。

## 契约边界

- 后端仍是赛事事实唯一来源。
- 用户手动确认 / 取消保持最高优先级。
- 用户取消赛事后，不得被 FIT、标题、距离或 Resolver 自动覆盖。
- V1 不接入网络开放赛事库；城市 / 时间仅作为展示信息或弱辅助证据。
- API 返回结构继续保持 `{ok, code, msg, data, traceId}`。
- 本任务不暴露 raw FIT、轨迹点、`track_json`、本地路径或 SQLite 结构。

## 修改文件

- `track.html`
- `tests/test_track_html_sync_logic.py`
- `tests/test_career_race_resolver.py`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`

## 验证

```bash
python3 -m pytest tests/test_activity_race_flag_api.py tests/test_fit_sport_event_race.py tests/test_career_race_resolver.py tests/test_track_html_sync_logic.py -q
```

结果：`50 passed`

## 下一个任务建议

继续 `ACS-Next-03`：Race Map / 赛事足迹。该任务应基于已确认赛事事件与安全展示字段，做赛事城市 / 国家足迹统计和只读地图或列表展示，不从前端重新推断赛事事实。
