# RCV2-42 macOS runtime / pywebview / visual 验收报告

## 结论

当前 macOS 源码环境下，Records Center V2 的 pywebview bridge、API envelope、前端 Records V2 shell、响应式/a11y、视觉密度和数据边界测试均通过。本轮未运行 PyInstaller、DMG、签名、公证或发布包替换。

## Runtime / API bridge

- `pywebview` import 可用。
- `main.Api` 只读烟测通过：
  - `get_career_record_catalog`
  - `get_career_records`
  - `get_career_record_candidates`
  - `get_career_record_rebuild_status`
  - `get_latest_career_snapshot`
- 上述 API 均返回统一 envelope：`ok/code/msg/data/traceId`。
- 烟测摘要：`docs/records_center_v2_real_data/rcv2_42_macos_api_smoke_summary.json`

## 真实库不变证明

- main.Api 只读烟测前后：内容 hash 与关键计数不变。
- main.Api 烟测期间 DB 文件 mtime 发生变化，但后续 `sqlite mode=ro` 复核 hash/mtime/counts 均稳定。
- 结论：未观察到内容污染或业务表计数变化；默认连接可能触碰 SQLite 文件元数据，后续如需更严格“只读浏览不触碰 mtime”，需让源码只读路径避免 schema ensure/default write-capable connection。

## 视觉与前端边界

- Records V2 前端 shell、chart、detail/candidate、responsive/a11y 测试均通过。
- 视觉/边界测试覆盖：
  - 跨平台视觉契约
  - 前端 readiness
  - 视觉密度
  - Phase9 数据边界审计
- `track.html` 静态检查无 viewport 字号 `vw` 和负 `letter-spacing`。

## 打包状态

只读检查发现仓库中存在历史 `build/`、`dist/`、`.dmg`、`.app`、`.spec` 和 pyinstaller 可执行文件。本轮仅查看文件状态，没有生成、签名、公证或替换任何产物。

## 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_phase9_macos_closure.py tests/test_career_phase9_pywebview_envelope.py tests/test_response_envelope_contract.py -q
# 32 passed

.venv312/bin/python -m pytest tests/test_career_records_v2_frontend_shell.py tests/test_career_records_v2_chart_frontend.py tests/test_career_records_v2_detail_candidate_frontend.py tests/test_career_records_v2_responsive_a11y_frontend.py -q
# 21 passed

.venv312/bin/python -m pytest tests/test_career_phase8_cross_platform_visual_contract.py tests/test_career_phase8_frontend_readiness.py tests/test_career_phase8_visual_density.py tests/test_career_phase9_data_boundary_audit.py -q
# 20 passed

.venv312/bin/python -m py_compile career_backend.py main.py
# passed
```

## 风险清单

- 未执行真实 GUI 截图：沿用 RCV2-35 限制，当前 Browser 对本地 file URL 有安全策略限制；本轮使用静态/测试证据替代。
- 默认 main.Api 只读烟测会触碰 DB mtime，但内容 hash 和关键计数未变化；如发布前要求 mtime 也严格不变，需要对只读 API 的连接策略另立任务。
- Windows 真机验证尚未执行，进入 RCV2-43 后需要 Windows 环境。
