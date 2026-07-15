# ACS-Year-AI-07B 完成报告：单飞控制、并发与原子切换

## 状态

Done。

## 实现摘要

- 新增进程内 single-flight 注册表，按 `year + source_fingerprint + prompt_version + model_id` 合并同一生成请求。
- 同一 key 的第二个请求等待 leader 结果，不再次调用 LLM。
- leader 锁定后再次检查完整缓存键，避免并发窗口重复生成。
- 不同年份使用独立 key，允许并行进入 LLM。
- ready 缓存写入保留原有事务切换，并对 SQLite locked 做小范围重试。
- LLM 期间若年度事实变化，旧 fingerprint 结果返回 `source_changed`，不写入 ready。
- 写入失败会回滚本次生成并保留旧 ready 报告。

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py -q
13 passed in 0.46s

.venv312/bin/python -m pytest tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
11 passed in 0.12s

.venv312/bin/python -m py_compile career_backend.py
passed
```

## Review 结论

通过。并发测试证明同一键只调用一次 LLM，不同年份不会共用锁；source fingerprint 变化和持久化失败均不污染当前 ready 报告。
