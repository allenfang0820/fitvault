# FR-Core-09 HR 传感器来源与置信度契约完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- HR 来源默认 `unknown`，不得默认胸带。
- 只有显式来源字段能证明外置胸带时，才能标记 `chest_strap`。
- 明确腕式/光电证据时标记 `optical`。
- 不根据 `device_name` 推断用户佩戴胸带；`unknown/optical` 必须保守降级置信度。

## 2. FR-Core-09 任务契约摘要

- 删除 `hr_source="chest_strap"` 写死逻辑。
- Fenix 8 等手表设备名不是胸带证据。
- source unknown 不影响指标值，只影响置信度和解释强度。
- 当前版本不做破坏性 DB 迁移；只消费已有/未来显式来源字段。

## 3. 工程级提示词

目标：修复复盘指标中 HR 来源默认胸带的问题，避免手表光电或未知 HR 来源获得胸带级置信度。

范围：
- 允许修改 `metrics_resolver.py` 默认参数和置信度判定。
- 允许修改 `main.py` HR 来源解析和调用传参。
- 允许更新测试、契约文档和任务清单。

边界：
- 不根据设备名称推断胸带。
- 不新增破坏性 schema migration。
- 不修改 efficiency/training load 公式。
- 不修改前端 UI 样式。

验收：
- 默认 HR 来源为 `unknown` 时 confidence 降为 `medium`。
- 显式 `hr_source=chest_strap` 时仍允许 high。
- 显式 `hr_source=optical` 时为 medium。
- `device_name="Garmin Fenix 8"` 不会被推断为 chest strap。

## 4. 实现摘要

- `MetricsResolver._compute_training_load()` 和 `evaluate_efficiency()` 默认 `hr_source="unknown"`。
- 新增 HR source 规范化，支持 `chest_strap / optical / unknown`。
- training load 对 unknown 来源追加 `hr_source_unknown` reason。
- `main._resolve_activity_hr_source()` 只读取显式来源字段，不读设备名。
- `main.py` efficiency 和 training load 调用改为传入解析后的 HR source。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m pytest -q tests/test_resolver_sport_isolation.py::TestEfficiencyScore::test_optical_hr_medium_confidence tests/test_resolver_sport_isolation.py::TestEfficiencyScore::test_unknown_hr_source_medium_confidence tests/test_resolver_sport_isolation.py::TestTrainingLoad::test_running_zone_distribution_complete_high_load tests/test_resolver_sport_isolation.py::TestTrainingLoad::test_unknown_hr_source_demotes_zone_distribution_confidence tests/test_resolver_sport_isolation.py::TestTrainingLoad::test_optical_hr_medium_confidence
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_core_audit_regression.py'
.venv312/bin/python -m pytest -q tests/test_resolver_sport_isolation.py
.venv312/bin/python -m pytest -q tests/test_fit_sync.py::TestFitSync::test_training_load_uses_unified_profile_hrr
```

结果：

- FR-Core-09 窄测：5/5 通过。
- 核心红线回归：11/11 通过。
- Resolver 专项隔离：89/89 通过。
- Fit sync 训练负荷用例：1/1 通过。

## 6. 下一任务建议

按清单顺序，下一任务是 `FR-Core-10：历史派生曲线与 baseline 版本化`。
