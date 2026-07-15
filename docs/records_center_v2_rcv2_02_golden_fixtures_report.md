# RCV2-02 Golden Fixtures 与算法可行性报告

完成时间：2026-07-14

## 1. 交付内容

新增 golden manifest：

```text
tests/fixtures/records_center_v2/golden_manifest.json
```

新增测试 helper：

```text
tests/test_records_center_v2_golden_fixtures.py
```

manifest 版本：

```text
records-center-v2-golden-fixtures-v1
```

所有 fixture 均为合成数据，坐标使用 `synthetic_xy_meters`，不含真实轨迹、真实 GPS、文件路径、设备序列号、账号信息或体重历史。

## 2. Fixture 覆盖矩阵

| case_id | 覆盖领域 | 关键边界 | 后续任务 |
| --- | --- | --- | --- |
| `cycling_power_clean_non_1hz` | 骑行功率 | 非 1Hz、时间加权、0W 有效、活动短于窗口 | RCV2-15、16 |
| `cycling_power_gap_missing_spike` | 骑行功率质量 | 缺失功率、长断点、尖峰、不跨 gap | RCV2-15、16 |
| `cycling_power_ebike_excluded` | 骑行 Scope | 电助力排除 | RCV2-15、17 |
| `hiking_elevation_spike_single_climb` | 徒步海拔 | GPS 尖峰、连续爬升、不能用总爬升冒充单段爬升 | RCV2-21 |
| `pool_swim_25m_freestyle_with_rest` | 泳池游泳 | 25m、自由泳、连续 Length、休息中断、50m best effort | RCV2-23、24 |
| `pool_swim_missing_pool_length_unknown_stroke` | 泳池质量 | 缺 pool length、未知泳姿、不得默认 25m | RCV2-23、24 |
| `open_water_750m_boundary_and_gps_jump` | 公开水域 | 750m `±5%` 包含边界、GPS 跳点候选 | RCV2-25 |
| `trail_route_same_reverse_low_overlap` | 越野路线 | 同向匹配、反向拒绝、低重合拒绝、真实样本缺失 candidate-only | RCV2-28、29 |

## 3. Golden output 约定

- `expected.quality` 只表达 fixture 预期质量等级，不替代最终评分矩阵。
- `reason_codes` 是后续 resolver 测试必须保留的稳定英文原因码输入。
- `candidate_only=true` 表示该样本即使算法可计算，也不能自动开放为真实数据 Verified。
- `range_required=true` 表示后续证据必须包含 Activity 内起止范围。
- 越野 route case 的 `same_direction` 仍为 candidate-only，因为真实库没有越野样本。

## 4. 更新流程

允许：

- 为已冻结规则新增合成 case。
- 为后续 Resolver 增加 expected 字段。
- 语义变化时 bump `manifest_version`。

禁止：

- 从真实库复制 raw track、功率流、文件名、路径或设备标识。
- 把 fixture 全绿当作真实数据验收。
- 为了测试方便放宽 V2 手册规则。

## 5. 可行性结论

- 骑行功率算法具备可测试输入，可以在无真实异常样本时覆盖关键质量分支。
- 徒步最大连续爬升需要基于轨迹范围生成，fixture 已防止用整次累计爬升冒充。
- 泳池游泳缺少真实样本，fixture 只能支持算法开发；Catalog 必须 validation required 或 unavailable，直到真实样本验收。
- 公开水域可先用真实样本和本 fixture 验证 `±5%` 边界与 GPS 质量，但样本量仍不足以证明全部距离族稳定。
- 越野路线/赛段可用 fixture 开发匹配算法，但无真实样本前必须 candidate-only。
