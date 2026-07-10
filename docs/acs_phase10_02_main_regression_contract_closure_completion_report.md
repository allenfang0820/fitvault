# ACS-Phase10-02 完成报告：主回归与契约测试收口

## 任务范围

- 执行 ACS 主回归。
- 执行赛事/FIT 入口补充回归。
- 检查 ACS 关键契约风险。
- 更新测试验收矩阵与开发任务清单。

## 执行的测试命令

```bash
python3 -m pytest tests/test_career*.py tests/test_track_html_sync_logic.py
```

结果：`323 passed`。

```bash
python3 -m pytest tests/test_fit_sport_event_race.py tests/test_activity_race_flag_api.py
```

结果：`14 passed`。

测试过程中仅出现本机环境级 `urllib3 / LibreSSL` warning，与本次 ACS 代码和契约无关。

## 契约检查结论

已检查以下风险点：

- Career API 是否保持 `{ok, code, msg, data, traceId}` envelope。
- Career 前端是否绕过 `requireCareerApiData()`。
- Career Snapshot / Insight 是否泄露 raw FIT、points、track_json、file_path、storage_ref、SQLite schema 或本地绝对路径。
- Career 前端是否计算赛事、PB、成就或时间线事实。
- Windows 真机与打包未执行项是否被误勾选。

结论：

- 未发现 ACS 范围内的新契约风险。
- `track.html` 中命中的 `call_llm`、`file_path`、`points`、`dist_km` 等字段属于既有非 ACS 轨迹、复盘、活动详情或通用 AI 链路。
- ACS 相关入口仍由 Phase9 数据边界、pywebview envelope 与前端零推断测试覆盖。
- Windows 打包、Windows 真机与 macOS 打包产物验收仍保持未完成状态。

## 文档更新

- 更新 `docs/acs_phase10_test_acceptance_matrix.md`
  - 新增 `ACS-Phase10-02` 最新主回归记录。
  - 记录主回归与赛事/FIT 入口补充回归结果。
- 更新 `docs/脉图运动生涯系统（ACS）开发任务清单.md`
  - 勾选 `ACS-Phase10-02`。
  - 保留 Windows/打包/人工验收未完成项。

## 未完成验收

- Windows 真机验证未执行。
- Windows 打包验证未执行。
- macOS 打包产物验证未执行。
- 完整应用人工视觉验收未执行。
- 真实数据导入后的端到端人工验收未执行。

## 下一步建议任务

`ACS-Phase10-03`：ACS 人工验收清单与打包前冻结说明。

