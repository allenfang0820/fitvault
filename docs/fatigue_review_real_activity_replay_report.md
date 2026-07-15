# FR-Core-11 真实活动回放矩阵报告

日期：2026-07-13  
范围：本地非删除活动，只读统计，不写入用户轨迹或绝对路径。

## 1. 本地活动矩阵

非删除活动总数：253。

按 `sport_type` 统计：

| sport_type | 数量 |
| --- | ---: |
| running | 95 |
| cycling | 92 |
| walking | 38 |
| hiking | 7 |
| mountaineering | 5 |
| training | 3 |
| e_biking | 2 |
| swimming | 2 |
| road_cycling | 2 |
| 62 | 2 |
| stand_up_paddleboarding | 1 |
| strength_training | 1 |
| stair_climbing | 1 |
| cardio | 1 |
| 52 | 1 |

## 2. 发布门禁测试

新增 `tests/test_fatigue_review_real_activity_replay.py`。

默认门禁：

- 使用真实本地活动库。
- 每个 sport family 选取代表性活动。
- mock 历史趋势查询，避免常规测试因 253 条活动重复查询历史窗口而退化为 O(n²)。
- 验证 snapshot 不变量：
  - 不泄露 `shadow_diff / shadow_diff_json / records / points`。
  - `review_mode` 与后端 registry 一致。
  - 非空曲线与 `curves.distance` 同轴。
  - unavailable / not_applicable 指标不携带强趋势。
  - 非骑行活动不使用 `power_retention` durability basis。

全量门禁：

```bash
FULL_FATIGUE_REPLAY=1 .venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_real_activity_replay.py'
```

说明：全量门禁同样 mock 历史趋势查询，适合发布前快速覆盖全部真实活动 shape。未 mock 的逐条完整趋势查询当前会重复扫描历史活动，耗时显著，不作为常规 CI 步骤。

## 3. 本轮验证结果

通过：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_real_activity_replay.py'
.venv312/bin/python -m pytest -q tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：

- 真实活动 replay smoke：1/1 通过。
- 复盘 e2e / quality gate / detail tab：185/185 通过。

## 4. 剩余发布说明

- macOS / Windows 打包产物 smoke test 仍需在实际打包流程中执行；本任务仅增加代码层发布门禁。
- 若后续优化历史趋势查询性能，可把未 mock 的 253 条完整趋势回放纳入发布脚本。
