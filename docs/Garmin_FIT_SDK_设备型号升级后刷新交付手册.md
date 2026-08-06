---
title: Garmin FIT SDK 设备型号升级后刷新交付手册
version: v0.1
status: Active
type: Development Delivery Manual
updated: 2026-08-07
scope: Garmin FIT SDK 升级后设备型号后台刷新、未知设备回填、低优先级调度与回归门禁
source:
  - docs/Garmin_FIT_SDK_设备型号升级后刷新契约摘要.md
  - docs/Garmin_FIT_SDK_设备型号升级后刷新任务清单.md
  - main.py
  - metrics_resolver.py
  - profile_backend.py
  - tests/test_device_name_resolver.py
  - tests/test_fit_sync.py
---

# Garmin FIT SDK 设备型号升级后刷新交付手册

## 0. 文档用途

本文冻结“SDK 升级后后台刷新 unknown device”的成熟路径，目标不是重跑所有 FIT，也不是改运动事实，而是把旧记录里可恢复的设备型号重新补全。

本文用于后续实现、测试和回滚判断。具体执行顺序以 `docs/Garmin_FIT_SDK_设备型号升级后刷新任务清单.md` 为准。

## 1. 问题定义

当前 `garmin-fit-sdk` 升级后，历史活动里可能仍保留旧版本解析出的 `Unknown Device`、`Garmin Product xxx` 或未解析映射状态。

这类问题分两类：

- Garmin 记录：SDK 升级后，原 FIT 文件存在时可后台重解析 `file_id`，把设备型号刷新成新版本可识别的名称。
- 非 Garmin 记录：如果 `file_id.product_name` 或持久化字段已足够，优先走设备产品映射表回填，不依赖 Garmin 专属重解析。

## 2. 成熟路径

成熟做法不是“升级后立刻扫全库”，而是“版本变更后低优先级、延迟、幂等地刷新可恢复记录”。

核心原则：

- 只在 SDK 版本变化后触发。
- 后台执行，不阻塞启动。
- 只回填设备字段，不改心率、功率、标题、轨迹、复盘。
- Garmin 走 FIT 重解析；其他厂商优先用持久化事实和映射表。
- 缺失 FIT 文件直接跳过，不报启动级失败。

## 3. 目标架构

### 3.1 版本门

用当前安装的 `garmin-fit-sdk` 版本和 `profile_backend.sync_state.json` 中记录的已处理版本做比较。

只有当前版本与已处理版本不一致时，才进入后台刷新。

### 3.2 两段式刷新

1. 先做设备产品映射回填，覆盖已持久化但仍可解析的历史记录。
2. 再对 Garmin 且文件存在的 unresolved 记录做 FIT 重解析。

### 3.3 低负载执行

刷新必须：

- 延迟启动；
- 小批量处理；
- 可重复运行；
- 不抢主线程；
- 不做联网操作；
- 不触碰用户可见业务事实。

## 4. 推荐实现面

建议改动控制在：

- `main.py`
- `metrics_resolver.py`
- `profile_backend.py`
- `tests/test_device_name_resolver.py`
- `tests/test_fit_sync.py`
- 必要时新增极少量状态/回归测试

## 5. 更新流程

建议流程如下：

1. 用户更新应用并启动。
2. 前端 ready 后，后台延迟触发设备型号刷新。
3. 先回填可由映射表解决的历史记录。
4. 再重解析 Garmin unresolved 且文件仍存在的记录。
5. 写回处理版本和摘要。
6. 下次同版本启动不重复跑。

## 6. 非目标

- 不在启动时联网检查或安装 SDK。
- 不重算心率、功率、距离、轨迹、标题、热环境、复盘结论。
- 不做 Garmin 专属例外以外的业务推断。
- 不把 device refresh 变成全库强制重建。

## 7. 验收标准

- SDK 升级后，历史 `Unknown Device` 能按规则后台刷新。
- Garmin 记录能在文件存在时重解析设备型号。
- COROS / 其他厂商不被 Garmin 逻辑误伤。
- 刷新过程不阻塞启动，不影响主线程体验。
- 刷新只改设备字段，不动其他活动事实。

## 8. 执行记录

- 文档创建时间：2026-08-07
- 当前状态：`Active`
