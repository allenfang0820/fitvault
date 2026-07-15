# ACS 赛事卡片手动判断入口恢复任务

## 项目契约刷新摘要

1. `Activity` 是赛事事实的单一来源，赛事人工确认或取消最终写入 `activities.is_race` 及用户覆盖字段。
2. 用户手动确认或取消赛事的优先级最高；用户取消后，Resolver、FIT、标题或距离规则不得再次覆盖。
3. 前端不得自行根据标题、距离、城市或日期判断赛事，只能展示后端 ViewModel 并调用既有写入 API。
4. 赛事档案只展示当前有效赛事；用户在卡片上取消赛事后，该卡片应在重新加载赛事档案后退出列表。
5. 本任务只恢复赛事卡片的人工判断入口，不修改 Race Resolver、赛事识别优先级、数据库结构或真实业务数据。

## 工程级提示词

### 目标

恢复运动生涯赛事档案卡片上的手动赛事判断入口，使系统识别赛事能够继续执行“是赛事 / 不是赛事”判断，同时使已经由用户确认或由高置信度来源确认的赛事仍可从卡片上撤销赛事标记。

### 范围

- 检查并修复 `track.html` 中 `careerRaceJudgementHtml(item)` 的显示条件和操作文案。
- 复用 `judgeCareerRaceFromCard(event, activityId, isRace)` 与 `set_activity_race_flag`，不得增加平行写入路径。
- 增加前端语义执行测试，验证渲染函数对不同赛事来源实际输出的按钮，而不是只检查源码中是否存在字符串。

### 交互规则

- Resolver 待确认赛事：显示“是赛事”和“不是赛事”。
- 已由用户确认的赛事：显示当前确认状态，并提供“取消赛事标记”。
- FIT 等无需二次确认但仍允许用户覆盖的正式赛事：提供“取消赛事标记”。
- 没有合法 `activity_id` 的卡片不显示操作入口。
- 点击按钮不得触发卡片的 Activity Detail 跳转，不弹确认框；写入成功后重新加载赛事档案。

### 约束

- 不修改真实数据库内容。
- 不修改赛事识别算法、来源优先级、API 契约或 schema。
- 不回退或整理当前工作区内与本任务无关的未提交更改。
- 不进行打包验证。

### 预计改动文件

- `track.html`
- `tests/test_career_archives_frontend_render.py`
- 本提示词文档

### 验证

```bash
.venv312/bin/python -m pytest \
  tests/test_career_archives_frontend_render.py \
  tests/test_career_races_api.py \
  tests/test_activity_race_flag_api.py -q
```

### 完成定义

- 待确认的系统赛事卡片实际渲染“是赛事 / 不是赛事”。
- 用户确认和其他正式赛事卡片实际渲染“取消赛事标记”。
- 所有按钮继续调用唯一的 `set_activity_race_flag` 写入链路。
- 定向测试全绿，diff review 未发现本任务范围内的阻断问题。

## 执行结果

- 已修复 `careerRaceJudgementHtml(item)` 的过窄显示条件。
- Resolver 待确认赛事继续显示“是赛事 / 不是赛事”。
- 用户确认赛事与其他正式赛事现在显示“取消赛事标记”。
- 新增 Node 语义执行测试，直接验证四种输入状态生成的操作 HTML。
- 最终定向验证：`43 passed in 0.53s`。
- 完整运动生涯回归：`729 passed, 55 subtests passed in 7.75s`。
- `git diff --check` 通过。
- 未打包、未提交、未写入真实业务数据。

## 下一个建议任务

执行一次运动生涯各二级页面的运行态逐页验收，重点检查“测试存在但真实界面入口不可见”的恢复缺口。建议覆盖总览、时间轴、赛事档案、记录中心、赛事足迹、赛事相册和年度 AI 总结，并为每个关键操作补充至少一个语义执行或浏览器可见性断言。
