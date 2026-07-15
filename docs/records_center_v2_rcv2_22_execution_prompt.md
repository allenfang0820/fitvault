# RCV2-22 工程级执行提示词：徒步正式纪录、Catalog、API 与测试闭环

## 目标

完成徒步五项纪录的 Catalog、状态机和只读 API 闭环：距离、累计爬升、历时、最高海拔、最大连续爬升。

## 契约边界

- `hiking_max_single_climb` 仍为 candidate-only，不进入 current active。
- walking/mountaineering 不显示为 hiking 占位。
- 不实现通用最快 5K/10K 或 VAM。
- 不写真实库。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_records_hiking_api_surface.py tests/test_career_record_hiking_elevation_climb.py tests/test_career_record_hiking_activity_total.py -q
.venv312/bin/python -m pytest tests/test_career_record_v2_state.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```
