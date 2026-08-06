---
title: Garmin FIT SDK 设备型号升级后刷新契约摘要
version: v0.1
status: Active
type: Contract Summary
updated: 2026-08-07
source:
  - docs/Garmin_FIT_SDK_设备型号升级后刷新交付手册.md
  - docs/Garmin_FIT_SDK_设备型号升级后刷新任务清单.md
---

# Garmin FIT SDK 设备型号升级后刷新契约摘要

## 1. 目标

在 `garmin-fit-sdk` 升级后，后台刷新历史活动中的设备型号，让原本的 `Unknown Device`、旧 fallback 名称和未解析映射状态尽量被新版本恢复。

## 2. 不可改变的契约

1. 刷新只在 SDK 版本变化后触发。
2. 刷新必须后台执行，不能阻塞启动和前端 ready。
3. 刷新只改设备相关字段，不改标题、心率、功率、轨迹、复盘或其他运动事实。
4. Garmin 记录允许在原 FIT 文件存在时重解析 `file_id`。
5. 非 Garmin 记录优先走持久化字段和 `device_product_mappings`，不做 Garmin-only 例外。
6. 缺失 FIT 文件必须可跳过，不能把缺文件当成致命失败。
7. 不读取或上传真实用户私密数据到外部系统。

## 3. 版本门契约

当前已处理版本记录在 `profile_backend.sync_state.json` 的设备刷新子状态中。

当 `importlib.metadata.version("garmin-fit-sdk")` 与已处理版本不一致时，允许进入后台刷新。

## 4. 刷新契约

刷新流程：

```text
SDK 版本变更
  -> 延迟调度
  -> 设备产品映射回填
  -> Garmin unresolved FIT 重解析
  -> 写回摘要与已处理版本
```

## 5. 回归契约

必须验证：

- 版本变化才触发。
- 无文件时跳过。
- 已 resolved 记录不改写。
- COROS `product_name` 路径保留。
- `device_product_mappings` 回填仍可用。
- 不改标题、心率、功率、轨迹、复盘。

## 6. 执行门禁

每个任务开始前必须确认：

- 当前交付手册、任务清单和契约摘要一致。
- 当前工作区脏改动已识别。
- 允许改动文件与实际改动一致。
- 聚焦测试和 `git diff --check` 通过后才进入下一步。
