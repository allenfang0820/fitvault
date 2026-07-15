# RCV2-14 通用 Records API 与 V1 兼容包装器完成报告

日期：2026-07-15

## 任务目标

完成记录中心 V2 通用 API 与 V1 PB API 兼容边界确认，使旧前端可以继续使用 `get_career_pb*`，新前端可以完全由 Records ViewModel 驱动。

## 本次完成内容

- 确认 `career_backend.py` 已提供 V2 通用 API：
  - `get_career_records`
  - `get_career_record_detail`
  - `get_career_record_history`
  - `get_career_record_curve`
  - `get_career_record_candidates`
  - `decide_career_record_candidate`
  - `rebuild_career_records`
  - `get_career_record_rebuild_status`
- 确认 `get_career_record_catalog` 与 V2 Registry/Catalog 已接入通用 API 契约。
- 确认 ViewModel 由后端生成：
  - `metric`
  - `improvement`
  - `scope`
  - `range`
  - `quality`
  - `history_summary`
  - `chart.points`
  - `detail_link.source = "career"`
- 确认 API 安全出口统一经过 `_records_api_safe()`，阻止路径、schema、原始轨迹、原始功率流、设备标识和体重历史等敏感内容进入 Records API 响应。
- 确认 `get_career_record_curve` 只返回派生曲线缓存的安全 `points/anchors` 与哈希 `input_fingerprint`，不返回 raw FIT、track、power stream 或可还原路线的原始数据。
- 确认 `rebuild_career_records()` 默认 `dry_run=True`，且不把普通“继续开发”解释为真实库 apply 授权。
- 确认 `docs/js_api_contract.json` 已登记 RCV2-14 所需 API，且 readonly/high_risk 标记符合契约。

## 保持不变的兼容契约

- V1 `career_pb_records`、`career_record_events`、`career_event_candidates` 继续作为事实/事件/候选容器。
- V1 `get_career_pb*` 行为不因 RCV2-14 改变。
- `detail_link.source` 继续保持 `"career"`。
- 前端仍不得计算纪录事实、scope、confidence、improvement、history summary 或 y 轴方向。
- AI 只能消费后续安全 Records Snapshot，不得读取 API 内部 evidence payload、raw activity streams 或真实路径。

## 触碰文件

- `career_backend.py`：复核 V2 通用 API、ViewModel、安全出口、rebuild wrapper 与 V1 兼容路径。
- `docs/js_api_contract.json`：复核 Records V2 API contract。
- `tests/test_career_records_v2_api.py`：复核通用 API 覆盖。
- `tests/test_career_pb_api.py`：复核 V1 PB API 兼容。

## 验证结果

### 定向测试

```bash
.venv312/bin/python -m pytest tests/test_career_records_v2_api.py tests/test_career_pb_api.py -q
```

结果：

```text
16 passed in 0.21s
```

### Contract JSON 校验

使用 `docs/js_api_contract.json` 的实际 `methods` 结构校验以下 API：

- `get_career_record_catalog`
- `get_career_records`
- `get_career_record_detail`
- `get_career_record_history`
- `get_career_record_curve`
- `get_career_record_candidates`
- `decide_career_record_candidate`
- `rebuild_career_records`
- `get_career_record_rebuild_status`

结果：

```text
contract_ok True missing [] wrong_flags []
```

## 自适应差异复核

- 范围符合 RCV2-14：聚焦 API、ViewModel、V1 兼容和 contract。
- 未执行打包。
- 未写真实库。
- 未扩大到前端视觉改造或运动专项算法。
- 未清理 V1 前端冗余；该清理应随 RCV2-32 至 RCV2-34 前端替代路径落地后执行。
- 未发现阻塞问题。

## 后续任务提示

下一任务为 `RCV2-15 骑行功率流规范化与质量检测`。后续实现必须注意：

- 功率流规范化只能读取 Activity/解析后安全事实，不向 API 暴露 raw FIT、完整 points 或本地路径。
- 0W 是有效滑行，缺失不是 0W。
- 断点、采样率异常、尖峰和 e-bike 混入必须降级为候选/忽略原因，不得进入高置信曲线。
- 本任务只建立功率流 adapter 与质量 resolver，不生成正式骑行功率纪录；正式功率锚点写入在后续任务完成。
