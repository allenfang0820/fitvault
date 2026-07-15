# RCV2-21 工程级执行提示词：海拔质量与最大连续爬升 Resolver

## 目标

实现徒步海拔质量与最大连续爬升 resolver，防止 GPS 高度尖峰污染纪录，并保证最大连续爬升有 Activity 内 range。

## 契约边界

- 不能用整次累计爬升冒充最大连续爬升。
- 无轨迹时不生成 `hiking_max_single_climb`。
- 异常高度只能 candidate/ignored。
- 不写路线速度纪录。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py -q
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```
