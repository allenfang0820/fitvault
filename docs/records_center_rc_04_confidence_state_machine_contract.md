# RC-04 置信度、候选与状态机冻结

日期：2026-07-13

## 执行提示词

目标：冻结纪录从检测到候选、激活、替代、拒绝和失效的完整生命周期，以及每种状态的用户可见行为。

范围：状态机、置信度阈值、评分维度、reason codes、候选确认/拒绝、重新提示策略、active 失效回退。

约束：不实现 API，不改 schema，不写 Resolver，不调整 UI。

完成定义：后端、API 和前端对每种状态的含义一致，RC-11/RC-13/RC-18/RC-21 可直接按契约实现。

## 1. 状态定义

| status | 含义 | 是否 current | 是否进入历史 | 用户可见 |
| --- | --- | --- | --- | --- |
| `candidate` | 证据可能有效，但置信度不足或需要用户确认 | 否 | 否 | 候选页 |
| `active` | 当前正式纪录 | 是 | 是 | 当前纪录、详情、演进 |
| `superseded` | 曾经正式生效，后被更好成绩替代 | 否 | 是 | 历史演进 |
| `rejected` | 用户明确拒绝该候选 | 否 | 否 | 默认隐藏，可在审计/调试中查看 |
| `invalidated` | 来源 Activity 删除、损坏、关键字段改变或规则重算后失效 | 否 | 可作为失效历史展示 | 详情/历史中按策略弱展示 |

硬约束：

- 每个 `record_key + source_mode + sport_scope` 同一时刻最多一条 `active`。
- `candidate` 不得替换 current，不得触发 Achievement，不得发送新纪录通知。
- `rejected` 不得进入正式历史链。
- `invalidated` 不得继续作为 current。

## 2. 置信度阈值

| confidence | level | 处理 |
| ---: | --- | --- |
| `> 0.90` | `high` | 可自动确认，进入正式比较 |
| `0.70 <= confidence <= 0.90` | `candidate` | 生成候选，不替换 current |
| `< 0.70` | `low` | 不进入正式纪录，不生成用户候选；只记录跳过原因计数 |

边界冻结：

- `0.90` 属于 candidate，不自动确认。
- `0.70` 属于 candidate。
- 只有 `>0.90` 才能自动确认。

## 3. 评分维度

置信度必须由可解释信号组成，禁止只返回一个裸分数。

建议评分维度：

| 维度 | 权重建议 | 高置信条件 | 常见降级 |
| --- | ---: | --- | --- |
| sport | 0.15 | Sport Resolver 输出 `running` 且非越野/跑步机混比 | `trail_running`、`treadmill_running`、unknown |
| distance | 0.20 | `distance_m` 来自可靠 `dist_km/FIT total_distance` 且在 `±3%` 内 | 单位歧义、距离漂移、接近边界 |
| time | 0.30 | `elapsed_time_sec` 可靠，或 timer time 已与 elapsed 交叉校验 | `timer_time_only`、`semantics_unknown`、自动暂停 |
| activity_integrity | 0.15 | Activity 未删除、非 mock、解析完成、关键字段完整 | processing error、mock/test、关键字段缺失 |
| device_gps_quality | 0.10 | GPS/设备距离质量可接受，室内活动有可信校准 | 跑步机无校准、GPS 漂移 |
| plausibility | 0.10 | 成绩在合理边界内 | 明显异常速度或距离跳变 |

权重可在 RC-11 代码化时微调，但必须保持维度和 reason codes 完整。

## 4. Reason Codes

必须输出 `reason_codes`，并在 API/ViewModel 中可展示。

正向 reason codes：

- `sport_running`
- `activity_total_source`
- `distance_within_3_percent`
- `distance_from_dist_km`
- `distance_from_fit_total_distance`
- `elapsed_time_reliable`
- `track_elapsed_matches_timer_time`
- `activity_not_deleted`
- `activity_parse_ready`
- `plausibility_passed`

降级 reason codes：

- `sport_trail_running_excluded_v1`
- `sport_treadmill_requires_confirmation`
- `distance_unit_ambiguous`
- `distance_outside_3_percent`
- `duration_from_total_timer_time`
- `duration_semantics_unknown`
- `timer_time_less_than_elapsed`
- `elapsed_time_missing`
- `activity_deleted`
- `activity_processing_error`
- `activity_mock_or_test`
- `gps_quality_uncertain`
- `plausibility_outlier`
- `record_definition_conflict`
- `duplicate_evidence`

Reason code 要求：

- 每个降级必须至少有一个 reason code。
- reason code 是稳定英文枚举，前端只做翻译，不推导业务含义。
- 不允许把本地路径、raw FIT、轨迹点或 SQLite schema 放入 reason payload。

## 5. 状态迁移表

| 当前状态 | 事件 | 条件 | 新状态 | 事件记录 |
| --- | --- | --- | --- | --- |
| none | detected | confidence `> 0.90` 且优于 current 或 current 不存在 | `active` | `detected` + `activated` |
| none | detected | `0.70 <= confidence <= 0.90` | `candidate` | `detected` + `candidate_created` |
| none | detected | confidence `< 0.70` | none | skip counter |
| `candidate` | user confirm | 候选未处理，来源 Activity 有效 | 重新参与比较，可能 `active` 或不激活 | `user_confirmed`，必要时 `activated` |
| `candidate` | user reject | 候选未处理 | `rejected` | `user_rejected` |
| `active` | better record activated | 新成绩严格更快 | `superseded` | `superseded` |
| `active` | source invalid | Activity 删除/损坏/关键字段变化 | `invalidated` | `invalidated` |
| `superseded` | source invalid | 来源失效 | `invalidated` | `invalidated` |
| `rejected` | normal rerun | 同一 evidence，无规则实质变化 | `rejected` | no-op |
| `rejected` | resolver version changed | evidence 发生实质变化 | 可重新生成 `candidate` | `recalculated` + `candidate_created` |
| `invalidated` | rebuild | 证据重新有效且规则允许 | 作为新 evidence 重新检测 | `recalculated` |

## 6. 用户确认契约

允许操作：

```text
confirm
reject
```

确认：

- 只确认候选证据有效。
- 不允许修改成绩值、距离、时间、Activity 来源或 record key。
- 保留原始 confidence 和 reason codes。
- `source` 标记为 `user_confirmed`。
- 写 `confirmed_at` 和 Record Event。
- 确认后重新与 current 比较：更快才激活；不更快则可保留为确认过但未激活的历史候选状态，具体 schema 在 RC-05 冻结。

拒绝：

- 状态改为 `rejected`。
- 保存 `rejected_at` 和 Record Event。
- 不删除来源 Activity。
- 普通刷新不得再次出现同一候选。

幂等：

- 重复 confirm 已确认候选返回稳定结果，不重复写语义相同事件。
- 重复 reject 已拒绝候选返回稳定结果，不重复写事件。
- 对 active/superseded/invalidated 执行候选决策应返回明确错误码，不改状态。

## 7. Evidence Key 与重新提示

候选幂等键：

```text
record_key + activity_id + evidence_key + resolver_version
```

V1 `activity_total` evidence_key：

```text
activity_total:{activity_id}:{record_key}:{distance_m}:{elapsed_time_sec}
```

拒绝后重新提示条件：

- `resolver_version` 改变，且
- evidence 发生实质变化，例如 `elapsed_time_sec` 从 timer time 改为可靠 elapsed、距离单位修正、record definition 变化。

不得重新提示：

- 只因刷新页面、重启应用、重新运行同版本 Resolver。
- 只因展示文案、标题、地区、天气或非成绩字段变化。

## 8. Active 失效与回退

当 active 来源 Activity 被删除、损坏或关键字段改变：

1. 当前 active 标记为 `invalidated`。
2. 写 `invalidated` Record Event。
3. 对同一 `record_key + source_mode + sport_scope` 的剩余有效历史重新选择最优。
4. 选出的回退纪录标记为 `active`，写 `recalculated` 或 `activated_from_rebuild` 事件。
5. 回退不得触发新纪录通知或 Achievement。

若没有可回退纪录：

- current 为空。
- API status 保持 schema ready，但该 record_key 返回空态。
- 不伪造 placeholder record。

## 9. 候选样例矩阵

| 场景 | confidence | reason_codes | 处理 |
| --- | ---: | --- | --- |
| 标准 10K，可靠 elapsed | 0.96 | `distance_within_3_percent`, `elapsed_time_reliable` | 自动比较 |
| 9.53K 当前旧 10K | 0.62 | `distance_outside_3_percent`, `timer_time_less_than_elapsed` | 忽略正式 PB，记录跳过 |
| 跑步机 5K，无校准 | 0.82 | `sport_treadmill_requires_confirmation`, `gps_quality_uncertain` | candidate |
| 距离可靠，时间只有 timer | 0.86 | `duration_from_total_timer_time`, `duration_semantics_unknown` | candidate |
| Activity 已删除 | 0.20 | `activity_deleted` | ignore/invalidated |
| 相同 evidence 重跑 | unchanged | `duplicate_evidence` | no-op |

## 10. API/UI 行为输入

API 必须让前端区分：

- `active` 当前正式纪录。
- `candidate` 待确认。
- `rejected` 已处理，不默认展示。
- `invalidated` 失效，不作为当前纪录。

前端文案原则：

- candidate 写“待确认纪录”，不能写“刷新纪录”。
- rejected 从候选列表移除。
- invalidated 在历史中弱展示时写“来源已失效/规则已重算”，不能写成用户退步。
- rebuild/recalculated 不触发庆祝。

## 11. 测试用例表

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| CONF-001 | confidence `0.91` | 自动进入正式比较 |
| CONF-002 | confidence `0.90` | candidate |
| CONF-003 | confidence `0.70` | candidate |
| CONF-004 | confidence `0.69` | ignore |
| CONF-005 | 降级无 reason code | validation 失败 |
| STATE-001 | 首条高置信成绩 | active |
| STATE-002 | 中置信成绩更快 | candidate，不替换 current |
| STATE-003 | candidate confirm 后更快 | active，旧 active superseded |
| STATE-004 | candidate confirm 后不更快 | 不替换 current |
| STATE-005 | candidate reject | rejected，不进入历史 |
| STATE-006 | rejected 同版本重跑 | 不重新提示 |
| STATE-007 | rejected 且 evidence 实质变化 | 可重新 candidate |
| STATE-008 | active 来源删除 | invalidated，并回退下一最佳 |
| STATE-009 | 回退产生 active | 不触发新纪录通知 |
| STATE-010 | 同一 evidence 重复运行 | 不重复候选、纪录或事件 |
