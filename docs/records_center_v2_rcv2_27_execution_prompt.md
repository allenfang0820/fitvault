# RCV2-27 工程级执行提示词：越野跑分类与整次活动纪录 Evidence

## 目标

严格识别 trail_running，并生成距离、爬升、历时、海拔和连续爬升 evidence。

## 契约边界

- road running/hiking/mountaineering 不得混入 trail。
- 标题只作弱证据。
- 不生成路线 PR 或标准距离最快成绩。
