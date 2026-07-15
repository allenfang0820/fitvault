# ACS-Year-AI-07A 完成报告：缓存命中、幂等与 ready 禁止重复生成

## 状态

Done。

## 实现摘要

- 生成前按完整缓存键查询 `career_ai_insights`。
- 精确命中已验证 `ready/superseded` 缓存时直接返回，不调用 LLM。
- 相同请求重复提交时保持同一 ready 报告，不创建第二条缓存，不二次调用 LLM。
- prompt/model 版本变化不会让用户可见状态变成 stale；无事实变化时生成入口仍被 ready 状态门拦截。
- 未验证 `candidate` 缓存不被直接激活，避免把不可信候选内容升为 ready。
- pywebview payload 白名单继续阻止前端构造额外参数绕过 ready。

## 验证结果

```text
.venv312/bin/python -m pytest tests/test_career_year_generate_api.py tests/test_career_ai_insights_repository.py tests/test_career_year_insight_service.py -q
20 passed in 0.30s

.venv312/bin/python -m pytest tests/test_career_year_insight_read_api.py tests/test_career_year_ai_report_validation.py -q
13 passed in 0.10s

.venv312/bin/python -m py_compile career_backend.py main.py
passed
```

## Review 结论

通过。fake LLM 调用计数锁定缓存命中行为；数据库唯一约束与服务层状态门均有测试覆盖；并发单飞留给 07B，没有提前扩大范围。
