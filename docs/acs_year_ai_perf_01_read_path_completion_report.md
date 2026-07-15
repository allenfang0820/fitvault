# ACS 年度 AI 总结性能修复任务 1 完成报告

## 任务

年度只读热路径与全表扫描收敛。

## 实现

- `get_career_year_insight()` 每次请求只读取一次 Activity 安全字段。
- 同一份请求级 Activity rows 被可用年份、年度 NEW 徽标、目标 Year Snapshot 和上一年同期比较复用。
- `_overview_activity_rows()` 一次读取 activities 列元数据，不再逐列重复执行 `PRAGMA table_info`。
- 未增加跨请求缓存，Activity 更新后仍会重新计算 Snapshot 与 fingerprint。

## 契约结果

- 年度 API payload 未改变。
- Year Snapshot 字段、排序、同期比较和 `source_fingerprint` 语义未改变。
- 已有 ready 报告的年度 NEW 徽标继续按事实变化准确计算。
- 未读取或缓存 raw FIT、`points_json`、`track_json`、文件路径或媒体字段。

## 验证

```text
34 passed
python -m py_compile career_backend.py: passed
git diff --check: passed
```

真实库 `/Users/fanglei/.fitvault/user_profile.db` 只读 benchmark：

- `_overview_activity_rows`：1 次。
- SQL：97 条，其中 SELECT 96、PRAGMA 1。
- 热读：约 0.38-0.47 秒。
- 冷读：约 4.6 秒。

冷读残余成本来自 1.4 GB 宽 Activity 表的一次磁盘扫描。该风险保留给后续架构性优化评估，本任务不通过跨请求长期缓存牺牲 fingerprint 新鲜度。
