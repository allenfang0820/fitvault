# P2 运动复盘后端快照回正完成报告

## 1. 本次目标

- 正式执行 `docs/p2_fatigue_review_snapshot_realignment_prompt.md`。
- 让 `get_fatigue_review(activity_id)` 的 `data` 成为前端复盘页面唯一权威快照。
- 在后端统一复盘曲线的单位、长度、空态和 forbidden 字段隔离。
- 保持 P2 边界：不改前端草图、不接 AI 洞察、不做 DB schema 迁移。

## 2. 修改文件

- `main.py`
- `metrics_resolver.py`
- `docs/js_api_contract.json`
- `tests/test_fatigue_review_snapshot_realignment.py`
- `tests/test_fatigue_review_contract_realignment.py`

## 3. 后端快照变更

- 新增 `_build_fatigue_review_curves_snapshot(bundle, resolved)`，作为 P2 曲线快照标准化出口。
- 新增 `_fatigue_review_numeric_curve()`，按后端权威 `distance_curve_m` 主轴校验曲线长度。
- 新增 `_strip_fatigue_review_forbidden_keys()`，递归移除 `records / points / raw_records / track_points / shadow_diff / shadow_diff_json / diff`。
- `_build_fatigue_review_snapshot(row)` 的 `curves` 改为统一走 P2 曲线标准化出口。
- `_build_resolved_payload_v81()` 的 Resolver 异常降级路径保留 bundle 中的真实 `distance/time/altitude`，避免整包空掉。
- `_build_fatigue_review_curve_bundle()` 增加距离轴清洗，确保 `distance_curve_m` 为数值、非负、单调。

## 4. 曲线策略

- `curves.distance` 单位 km，由后端真实轨迹点距离轴转换。
- `curves.time` 单位 sec。
- `curves.total_distance_m` 单位 m，优先使用活动标量中的总距离。
- `distance` 是主轴；`time/hr/speed/altitude/grade/gap/efficiency` 只有长度与主轴一致时才输出。
- 缺失或长度不匹配的曲线返回空数组，不由前端补齐、插值或重建。
- `fatigue_zones` 与 `collapse_events` 继续透传 P1/Resolver 同源算法结果，P2 不重新计算 UI 坐标。

## 5. Resolver 稳定性修复

- `metrics_resolver.py::_build_analysis_pack()` 保留距离 0 为合法值。
- 修复首点距离 `0` 被当作缺失写成 `None` 后，bonk / fatigue zone 路径可能在 `distance_curve[-1] - distance_curve[0]` 处异常的问题。

## 6. 测试变更

- 新增 `tests/test_fatigue_review_snapshot_realignment.py`，覆盖：
  - 快照曲线按权威距离轴长度对齐。
  - 缺 calories 时曲线仍返回，bonk risk 不触发。
  - 轨迹点字段不完整时结构完整且不抛异常。
  - forbidden 字段递归隔离。
  - `get_fatigue_review` 参数错误 / 活动不存在 envelope。
- 更新 `tests/test_fatigue_review_contract_realignment.py`，兼容当前 `docs/js_api_contract.json` 的 `methods` 顶层结构，并检查 P2 描述。

## 7. 验证结果

验证命令：

```bash
python3 -m pytest tests/test_fatigue_review_snapshot_realignment.py tests/test_fatigue_review_resolver_realignment.py tests/test_fatigue_review_contract_realignment.py tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_envelope.py
```

验证结果：

```text
58 passed, 1 warning
```

说明：

- warning 来自本机 urllib3 / LibreSSL 版本提示，与本次 P2 修改无关。
- 本机无 `python` 命令，使用 `python3` 完成验证。

## 8. 未处理事项

- P3：前端删除 `_distanceFromSpeedTime()` 事实推导，改为直接消费 `data.curves.distance`。
- P4：按 `docs/design/运动复盘系统_页面设计草图_v1.png` 升级 UI。
- P5：扩展前端静态门禁和手工测试清单。
- P6：复盘 AI 洞察最后接入，修复 `__FATIGUE_REVIEW_INSIGHT__` 分支。

## 9. 下一步建议

- 进入 P3 前端最小可用回正。
- P3 重点删除复盘链路中的 `_distanceFromSpeedTime()` 调用，让图表 X 轴、疲劳带和事件标记都使用后端权威距离来源。
