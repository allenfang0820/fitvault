# ACS 年度 AI 总结切换性能修复完成报告

## 完成范围

1. 年度后端只读链路每请求只扫描一次 Activity 安全字段。
2. 当前 schema ensure 改为真正只读，修复 Snapshot 外层事务未提交和 SQLite 写锁竞争。
3. 前端增加按年份缓存、事实更新失效、Career 加载门禁和 AI 页面按需加载。

## 用户可见结果

- 已访问且无更新信号的年份可即时回切，不再重复请求后端。
- 年度总结按年份即时切换；独立生涯总结模式已在后续产品收敛中移除。
- 活动同步、导入、删除、标题修改、赛事标记或新活动出现后，缓存会在下一次访问时刷新。
- Overview 与 Seasons 不再同时触发年度报告更新计算。

## 后端结果

- `_overview_activity_rows()`：每次年度读取 1 次。
- Activity 列元数据：1 次 `PRAGMA table_info(activities)`。
- 当前 schema 的年度 query-only 读取：119 条只读 SQL，0 条写 SQL。
- 全生涯 Snapshot 事务修复已验证；其公开 pywebview 接口随后随生涯总结功能一并退役。

## 验证

```text
年度相关矩阵: 195 passed, 10 subtests passed
全部 Career 测试: 751 passed, 57 subtests passed
Python compile: passed
JS API JSON: passed
track.html inline JavaScript parse: passed
git diff --check: passed
```

## 性能证据

真实数据库 `/Users/fanglei/.fitvault/user_profile.db`：

- 修复前单次年度读取约 4.0-5.6 秒，Activity 安全行约读取 15 次，约 2822 条 SQL。
- 修复后每次年度读取 1 个 Activity read、119 条 SQL、无写语句。
- 热读约 0.29-0.40 秒。
- 首次冷读约 5.0 秒，残余成本是 1.4 GB 宽 Activity 表的一次磁盘扫描。

冷读残余没有通过跨请求后端缓存规避，以免 Activity 更新后返回陈旧 fingerprint。当前交互路径由 Career Overview 预热、后端单次扫描和前端年份缓存共同保证切换速度。
