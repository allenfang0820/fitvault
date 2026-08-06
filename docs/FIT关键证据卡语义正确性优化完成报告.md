# FIT关键证据卡语义正确性优化完成报告

> 日期：2026-08-06
> 任务清单：`docs/FIT关键证据卡语义正确性优化任务清单.md`
> 交付手册：`docs/FIT关键证据卡语义正确性优化交付手册.md`

## 1. 结论

这次问题属于通用代码语义和健壮性问题，不是百锐腾专属兼容问题。

百锐腾 FIT 更稀疏，会更容易触发旧逻辑的保守降级；但真正需要修的是：

- 缺失速度不能当作真实 0 速度。
- stopped 过滤必须依赖可信速度事实。
- near-zero distance 不能放大出异常坡度。
- 前端不能把已实现但不可用的指标说成“待接入”。

本次没有做品牌特供，也没有把稀碎 FIT 插值成连续曲线。

## 2. 已交付内容

| 项目 | 交付 |
| --- | --- |
| 事实边界冻结 | `docs/FIT关键证据卡语义正确性优化事实边界冻结.md` |
| 状态语义清理 | 关键证据卡运行时不再把已实现指标兜底成“待接入” |
| 前端文案对齐 | 关键证据 / 补充证据初始占位改为“待加载”，错误态风险改为“风险暂不可用” |
| 曲线稳健性验证 | missing speed、stopped 门禁、near-zero grade 均有自动化回归覆盖 |
| FIT 回归矩阵 | `docs/FIT关键证据卡语义正确性优化回归矩阵.md` |

## 3. 代码质量问题与数据质量问题的边界

### 属于代码质量问题，值得修

- 缺失速度被前端或后端语义误当成停顿。
- 已实现指标在 UI 中显示“待接入”。
- `unavailable / partial / missing` 被同一种“数据不足”文案盖掉。
- 坡度计算对重复距离或近零距离差不够稳健。

### 属于数据质量问题，不继续伪修

- FIT 本身心率、功率、踏频曲线稀疏。
- FIT 没有原生速度，只能由距离 / 时间派生。
- 大量滑行、停踩、0W 或零踏频片段导致低置信或保守降级。
- 无距离 / 时间轴时，速度只能保持 missing，不能补成连续曲线。

## 4. 验证结果

已执行：

```bash
.venv312/bin/python -m pytest tests/test_cycling_fatigue_review_acceptance.py -q
.venv312/bin/python -m pytest tests/test_bryton_cycling_no_speed_review.py tests/test_fatigue_review_core_audit_regression.py -q
git diff --check -- track.html tests/test_cycling_fatigue_review_acceptance.py docs/FIT关键证据卡语义正确性优化任务清单.md docs/FIT关键证据卡语义正确性优化事实边界冻结.md
```

结果：

- `11 passed`
- `24 passed, 6 subtests passed`
- `git diff --check` 通过

真实 FIT 只读矩阵：

- Garmin cycling：关键解释信号全部 `available`
- Magene cycling：关键解释信号全部 `available`
- Bryton sparse cycling：关键解释信号全部 `available`，速度语义为 `derived_distance_time / derived`

## 5. 剩余风险

- 如果 FIT 同时缺少原生速度和可用距离 / 时间轴，速度仍会保持 `missing`，相关判断应继续保守降级。
- 如果心率 / 功率 / 踏频覆盖非常稀疏，卡片仍可能显示低置信或不可用，这是正确行为。
- 本次未做桌面 UI 截图验收；已通过前端函数级回归约束文案和状态。
- 本次未提交任何真实 FIT 二进制。
