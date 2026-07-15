# ACS 年度 AI 总结性能修复任务 3 完成报告

## 任务

前端按年份缓存与 AI 页面按需加载。

## 实现

- 年度 ViewModel 按年份缓存，`2026 -> 2025 -> 2026` 在缓存有效时不重复调用后端。
- 年度 NEW、stale 和本地已知事实更新会标记缓存需要刷新。
- 使用 `careerSourceVersion` 隔离事实更新期间的晚到响应，避免旧请求清除失效标记。
- Career 主 Tab 不再预加载全生涯 Snapshot；独立生涯总结模式随后已退役。
- Career 主页面增加 loaded、needsRefresh 和共享 loading promise，重复进入不重复加载。
- Overview 与 Seasons 错峰执行，年度报告更新计算不再并行争抢数据库。
- 新活动、同步、导入、删除、标题更新和赛事标记成功后统一失效年度缓存与 Career 页面数据。

## 验证

```text
50 passed
track.html inline scripts parsed: 3
git diff --check: passed
```

现有年度 request id、年份隔离、生成请求 `{ year }` 白名单和旧报告保护继续通过。
