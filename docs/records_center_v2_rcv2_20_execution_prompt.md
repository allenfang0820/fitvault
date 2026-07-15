# RCV2-20 工程级执行提示词：徒步运动边界与 Activity-total Evidence

## 目标

实现 hiking 与 walking/mountaineering/trail_running 的严格分离，并生成徒步整次活动 evidence：最长距离、累计爬升、最长 elapsed time、最高海拔。

## 契约边界

- 只接收 hiking/hike/trekking。
- walking、mountaineering、trail_running 不得混入 hiking。
- 标题只能辅助，不得单独改变类型。
- 不实现连续爬升；留给 RCV2-21。
- 默认 dry-run，不写真实库。

## 验证

```bash
.venv312/bin/python -m pytest tests/test_career_record_hiking_activity_total.py tests/test_career_record_v2_rebuild.py -q
.venv312/bin/python -m pytest tests/test_career_record_evidence.py tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
.venv312/bin/python -m py_compile career_backend.py
```
