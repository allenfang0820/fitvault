---
title: Garmin FIT SDK 设备型号升级后刷新任务清单
version: v0.1
status: Planning
type: Ordered Engineering Task List
updated: 2026-08-07
source:
  - docs/Garmin_FIT_SDK_设备型号升级后刷新交付手册.md
  - docs/Garmin_FIT_SDK_设备型号升级后刷新契约摘要.md
  - main.py
  - metrics_resolver.py
  - profile_backend.py
  - tests/test_device_name_resolver.py
  - tests/test_fit_sync.py
---

# Garmin FIT SDK 设备型号升级后刷新任务清单

本清单把“SDK 升级后后台刷新设备型号”拆成可独立执行、可验证、可回滚的任务。

本轮目标是让历史 unknown device 在 SDK 升级后尽量被后台补全，而不是修改 FIT 解析业务事实。

## 0. 执行规则

- 唯一上位基线是 `docs/Garmin_FIT_SDK_设备型号升级后刷新交付手册.md`。
- 每个任务开始前执行 `git status --short`，阅读将要修改文件的当前 diff。
- 不得 stash、reset、clean、覆盖、格式化或提交无关改动。
- 每个任务只修改允许改动文件列出的范围；必须扩大范围时，先更新本清单和交付手册。
- 每个任务完成后运行聚焦测试和 `git diff --check`。
- 刷新只改设备字段，不得混入标题、运动事实、复盘或 UI 大改。

## 1. 任务总览

| 顺序 | 任务 | 性质 | 优先级 | 前置 | 状态 | 主要交付物 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 设备刷新契约冻结 | 审计 / 契约 | P0 | 无 | `Planned` | 版本门、刷新边界、回归约束 |
| 1 | 后台刷新调度与状态落地 | 依赖治理 / 后台任务 | P0 | 任务 0 | `In Progress` | 延迟调度、状态记录、版本门 |
| 2 | 设备字段回填与 Garmin 重解析 | 业务修复 | P0 | 任务 1 | `Planned` | 映射回填、Garmin FIT 重解析 |
| 3 | 聚焦测试与真实样本验收 | 回归 / 发布 | P0 | 任务 1、2 | `Planned` | 单测、回归命令、样本验收 |

## 2. 全局非目标

- 不在启动时联网检查或安装 SDK。
- 不把刷新做成全库强制重建。
- 不改标题规则、心率规则、功率规则、轨迹规则。
- 不把 Garmin SDK 升级扩展成全量依赖升级。

---

## 3. 任务 0：设备刷新契约冻结

优先级：P0
性质：审计 / 契约
前置：无

### 目标

冻结升级后设备型号刷新机制的边界：只在 SDK 版本变化后触发，只改设备字段，不碰其他运动事实。

### 允许改动文件

- 本任务清单。
- 交付手册。
- 契约摘要。
- 必要时新增基线审计报告。

### 必做

- 记录当前工作区状态。
- 确认版本门的状态存储位置。
- 确认 Garmin 重解析和非 Garmin 映射回填的边界。
- 确认刷新不阻塞启动路径。

### 验证

```bash
git status --short
rg -n "DEVICE_NAME_REFRESH|device_product_mappings|Unknown Device|garmin-fit-sdk" main.py metrics_resolver.py profile_backend.py tests docs
git diff --check
```

### 完成标准

- 边界清晰。
- 不引入业务语义漂移。
- 后续任务拥有可回读的契约依据。

---

## 4. 任务 1：后台刷新调度与状态落地

优先级：P0
性质：依赖治理 / 后台任务
前置：任务 0

### 目标

让应用在前端 ready 后，低优先级延迟调度设备型号刷新，并把处理版本、最后运行时间和摘要持久化。

### 允许改动文件

- `main.py`
- `profile_backend.py`
- 必要时新增状态测试

### 必做

- 版本变化才触发。
- 延迟启动，不阻塞前端 ready。
- 幂等调度，避免重复创建后台线程。
- 持久化处理版本和摘要。

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_device_name_resolver.py
.venv312/bin/python -m py_compile main.py profile_backend.py
git diff --check
```

### 完成标准

- 启动路径无明显额外阻塞。
- 同版本不会重复刷新。
- 状态可读、可回溯。

---

## 5. 任务 2：设备字段回填与 Garmin 重解析

优先级：P0
性质：业务修复
前置：任务 1

### 目标

优先用持久化事实和映射表回填可恢复记录；对 Garmin unresolved 且文件存在的记录，使用当前 SDK 重解析设备型号。

### 允许改动文件

- `main.py`
- `metrics_resolver.py`
- `tests/test_device_name_resolver.py`
- `tests/test_fit_sync.py`

### 必做

- Garmin 仅对可重解析记录做 FIT 重解析。
- 非 Garmin 依赖 `product_name` 和 `device_product_mappings`。
- 缺失文件跳过。
- 只更新设备字段。

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q tests/test_device_name_resolver.py tests/test_fit_sync.py
.venv312/bin/python -m py_compile main.py metrics_resolver.py
git diff --check
```

### 完成标准

- 历史 unknown device 可被尽量刷新。
- COROS / 迈金 / 其他厂商不被 Garmin 专属逻辑误伤。
- 设备字段之外无副作用。

---

## 6. 任务 3：聚焦测试与真实样本验收

优先级：P0
性质：回归 / 发布
前置：任务 1、2

### 目标

用聚焦测试验证版本门、幂等性、缺文件跳过、已 resolved 不改写，以及设备字段之外不变。

### 允许改动文件

- 新增或更新聚焦测试
- 本任务清单

### 验证

```bash
PYTHONPATH=. .venv312/bin/python -m pytest -q \
  tests/test_device_name_resolver.py \
  tests/test_fit_sync.py
.venv312/bin/python -m py_compile main.py metrics_resolver.py profile_backend.py
git diff --check
```

### 完成标准

- 规则明确。
- 回归可重复。
- 真实样本验收有结论。
