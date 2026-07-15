# FR-Core-11 真实活动回放矩阵与发布门禁完成报告

日期：2026-07-13  
任务源：`docs/fatigue_review_core_audit_fix_task_list.md`  
状态：已完成

## 1. 交付手册摘要刷新

- 真实活动 replay 是复盘核心功能发布门禁，不以单元测试替代。
- 常规门禁使用真实本地活动矩阵 smoke；全量门禁可通过 `FULL_FATIGUE_REPLAY=1` 开启。
- 回放报告只写匿名化统计，不写用户绝对路径或原始轨迹。

## 2. FR-Core-11 任务契约摘要

- replay 必须验证 snapshot 不变量：禁泄露、曲线同轴、mode 一致、不可用趋势门控、运动专项 basis 隔离。
- 现有复盘测试失败必须修复或明确隔离。
- macOS / Windows 打包 smoke 属于发布流程门禁；本任务完成代码层和本地 replay 门禁。

## 3. 工程级提示词

目标：建立复盘核心功能发布门禁，用真实活动矩阵覆盖前面 FR-Core 修复的关键不变量，并输出匿名化回放报告。

范围：
- 允许新增 `tests/test_fatigue_review_real_activity_replay.py`。
- 允许新增匿名化回放报告。
- 允许修复复盘核心测试暴露的静态门禁失败。
- 允许更新任务清单和最终报告。

边界：
- 不写入 activities 表。
- 不导出用户绝对路径或原始轨迹。
- 不执行 macOS/Windows 打包。
- 不修改算法公式。

验收：
- 真实本地活动 replay smoke 通过。
- 复盘 e2e/quality/detail 核心测试通过。
- 回放报告包含活动数量、sport matrix、测试命令、剩余发布说明。

## 4. 实现摘要

- 新增真实活动 replay smoke test，默认每个 sport family 选取代表活动。
- 支持 `FULL_FATIGUE_REPLAY=1` 扩展到全量非删除活动。
- 为 replay gate mock 历史趋势查询，避免常规测试因重复扫描历史窗口退化为 O(n²)。
- 修复 `track.html` 中 5 处 viewport 字号，满足复盘 UI 静态发布门禁。
- 新增 `docs/fatigue_review_real_activity_replay_report.md`。

## 5. 验证结果

通过：

```bash
.venv312/bin/python -m unittest discover -s tests -p 'test_fatigue_review_real_activity_replay.py'
.venv312/bin/python -m pytest -q tests/test_fatigue_review_e2e_contract.py tests/test_fatigue_review_quality_gate.py tests/test_v9_0_detail_tab_review.py
```

结果：

- 真实活动 replay smoke：1/1 通过。
- 复盘 e2e / quality gate / detail tab：185/185 通过。

## 6. 下一任务建议

任务清单 FR-Core-00 至 FR-Core-11 已全部完成。下一步建议运行最终总验证、检查 diff，并进入打包前 smoke / macOS / Windows 发布流程。
