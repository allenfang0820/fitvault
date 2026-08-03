# 力量训练 ST-01 真实 FIT 探针报告

> 日期：2026-07-28
> 结论：通过
> 数据处理：只读扫描本机受控 FIT 目录；仓库仅保存脱敏消息快照，不保存真实 FIT、路径、
> 时间、设备标识或原始未知字段值。

## 样本覆盖

初筛 196 个力量训练候选文件，其中 186 个包含 `set_mesgs`。本次验收选择四类匿名样本：

| 样本 | 结构化消息 | 有效动作组 | 有重量 | 无重量 | 结果 |
| --- | --- | ---: | ---: | ---: | --- |
| A 全重量 | 7 set / 1 title / 4 step | 2 | 2 | 0 | 结构化 |
| B 部分重量 | 46 set / 0 title / 0 step | 23 | 18 | 5 | 结构化 |
| C 自重训练 | 20 set / 5 title / 6 step | 19 | 0 | 19 | 结构化 |
| D 无动作组 | 0 set / 0 title / 0 step | 0 | 0 | 0 | 非结构化 |

有效动作组口径为 `set_type=active` 且 `repetitions > 0`。休息组、次数缺失和次数为 0 的
active 记录保留为原始事实。关联 step 明确标记为 warmup/cooldown/recovery 的有效动作组
不计入第一期工作组。

## 已验证字段

`set_mesgs`：

```text
message_index, set_type, repetitions, weight, duration,
category, category_subtype, wkt_step_index, weight_display_unit,
start_time, timestamp
```

`exercise_title_mesgs`：

```text
message_index, exercise_category, exercise_name, wkt_step_name
```

`workout_step_mesgs`：

```text
message_index, duration_type, duration_value, duration_reps,
exercise_category, exercise_name, exercise_weight, intensity,
target_type, target_value, weight_display_unit
```

部分训练计划还出现 `duration_step`、`repeat_time`。这些字段不属于第一期动作组展示必需事实，
暂不进入规范化合同。

## 关联规则

1. set 的 `wkt_step_index` 与 workout step 的 `message_index` 关联。
2. workout step 和 exercise title 通过 `exercise_category + exercise_name` 关联。
3. exercise title 自身的 `message_index` 不能当作 workout step index。本次样本已验证二者可不相等。
4. 无 workout step 时，只能从 set 的首个有效 `category` 获取动作类别；没有可靠 subtype 时，
   不得提升为具体动作名。
5. SDK 在多批真实文件中同时返回命名的 `category_subtype` 和未知数字字段 `2`。字段 `2` 只在
   探针报告出现，不直接作为具体动作事实；后续规范化优先使用命名字段。

## 数据边界

- `weight > 0` 才计入重量覆盖和训练容量；明确的 `weight=0` 与缺失重量均按无外部重量处理。
- FIT title 可以是用户可读动作名；缺失 title 时可使用 Garmin profile 的稳定枚举映射，映射失败
  则保留类别或“未识别动作”。
- 多 category/subtype 数组在不同年代文件中形态不稳定，第一期只使用首个可确认类别。
- 不根据文件名、活动标题、心率、热量或设备型号补动作与重量。

## 自动化验证

```text
5 passed in tests/test_strength_fit_parser.py
strength_fit_parser.py 与 scripts/probe_strength_fit.py py_compile 通过
git diff --check 通过
```
