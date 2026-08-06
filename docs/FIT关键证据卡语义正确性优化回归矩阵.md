# FIT关键证据卡语义正确性优化回归矩阵

> 日期：2026-08-06
> 关联任务：OT-04
> 方法：本地真实 FIT 只读解析，不写入数据库，不提交 FIT 二进制。

## 样本矩阵

| 样本 | 本地文件 | sport | 距离 | records | 速度语义 | 功率 / 踏频 / 心率 | 关键信号状态 | 结论 |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- |
| Garmin cycling | `/Users/fanglei/Desktop/tracks/常州市 公路骑行_610080519.fit` | `road_cycling` | 67.05 km | 10459 | `observed / available`；observed 10391，derived 68，missing 0 | power 8212 / cadence 7738 / HR 10459，功率与踏频均 `available` | pacing / aerobic / retention / cadence / intensity 全部 `available` | 常见完整 FIT 不退化 |
| Magene cycling | `/Users/fanglei/Desktop/Magene_C706_1785880546_196852_1785889714943.fit` | `cycling` | 63.89 km | 7584 | `observed / available`；observed 7584，missing 0 | power 6933 / cadence 6933 / HR 7584，功率与踏频均 `available` | pacing / aerobic / retention / cadence / intensity 全部 `available` | 迈金样本不退化 |
| Bryton sparse cycling | `/Users/fanglei/Desktop/260805055744.fit` | `cycling` | 63.05 km | 6564 | `derived_distance_time / derived`；observed 0，derived 6563，missing 1 | power 3679 / cadence 4011 / HR 1312，功率与踏频均 `available` | pacing / aerobic / retention / cadence / intensity 全部 `available` | 稀疏 FIT 不再被误判成缺速度或未接入 |

## 关键边界

- Garmin / Magene 样本仍走原生或解析得到的可用速度轴，`stopped` 过滤可启用。
- Bryton 样本没有原生速度，但有距离 / 时间轴，因此后端标为 `derived_distance_time / derived`，不是观测 0，也不是 `missing`。
- 三个样本都没有出现“假待接入”或“已实现指标被说成未接入”。
- 坡度范围保持有限值：Garmin `-18.33% ~ 7.44%`，Magene `-34.94% ~ 24.63%`，Bryton `-53.19% ~ 35.71%`。

## 自动化回归

已执行：

```bash
.venv312/bin/python -m pytest tests/test_bryton_cycling_no_speed_review.py tests/test_fatigue_review_core_audit_regression.py -q
.venv312/bin/python -m pytest tests/test_cycling_fatigue_review_acceptance.py -q
```

结果：

- `24 passed, 6 subtests passed`
- `11 passed`
