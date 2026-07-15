# RC-02 完成报告

## 任务目标

用只读方式评估从当前硬编码距离区间切换到统一 `±3%` 后，真实用户 PB 会新增、移除或替换哪些结果。

## 实际改动

- 新增 `scripts/records_center_rc_02_rule_diff.py` 只读审计脚本。
- 新增 `docs/records_center_rc_02_real_db_rule_diff.md`。
- 更新 `docs/records_center_rolling_contract_summary.md`。
- 更新 `docs/运动生涯记录中心（PB功能）开发任务清单.md` 中 `RC-02` 状态和当前下一任务。
- 未修改业务逻辑，未写入真实数据库。

## 契约决定

- 真实库迁移到 `±3%` 会改变 `running_10k` 当前 active：从活动 `108` 变为活动 `150`。
- 新规则不会新增候选，只会移除偏离标准距离过大的旧候选。
- 活动 `108` 同时存在 timer time 小于轨迹 elapsed 的口径风险，应作为迁移人工复核重点。
- 半马 active 的 `event_date` 与 Activity 本地日期存在一天差异，后续契约需要冻结日期来源。

## 测试与结果

只读脚本：

```bash
.venv312/bin/python scripts/records_center_rc_02_rule_diff.py --db /Users/fanglei/.fitvault/user_profile.db
```

回归验证：

```bash
.venv312/bin/python -m pytest tests/test_career_pb_resolver.py tests/test_career_pb_api.py tests/test_career_timeline_pb_nodes.py -q
```

结果：

```text
22 passed
```

## 真实数据或人工验证

已使用真实库只读 dry-run。未执行用户确认、migration 或正式重建。

## 未完成项与残余风险

- 迁移替换 10K active 需要后续 RC-15/RC-27 的 dry-run 应用计划和人工确认。
- 半马日期口径差异需要在契约任务中明确。
- 本脚本为审计工具，不是正式 Resolver；正式实现仍需由 Registry、Performance Summary 和状态迁移服务承载。

## 下一任务

进入 `RC-03：Record Registry 与比较规则冻结`。
