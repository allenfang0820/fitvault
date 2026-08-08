---
title: FIT 活动标题统一治理任务清单
version: v0.2.0
status: Implemented
type: Ordered Remediation Task List
updated: 2026-08-08
scope:
  - FIT / provider 活动标题的统一分类与构建
  - 技术文件名、真实文件名、自动标题、用户标题的边界冻结
  - 旧库已入库技术标题的升级自动修复
non_goals:
  - 不覆盖用户手动标题
  - 不把所有 filename 来源一刀切改成地区+运动
  - 不用单个 provider 文件名或 activity id 写特例
  - 不改变活动去重、地区回填、天气或记录中心算法
---

# FIT 活动标题统一治理任务清单

## 0. 背景与目标

标题规则已经经历多轮局部修补：COROS 技术文件名、纯数字文件名、设备型号+时间文件名、地区回填标题保护等。当前 Zwift 样本 `23811652091_ACTIVITY.fit` 暴露了同类根因仍未收束：标题是否可保留，散落在 source 名称、正则、导入末尾修复、地区回填和旧库回填中分别判断。

本轮目标不是再补一个 `_ACTIVITY` 后缀正则，而是把标题逻辑收束为一个统一后端契约：

- source 只描述来源，不单独决定是否覆盖。
- 统一决策器同时接收 `session_label`、`filename`、`file_name`、`fit_title` 等证据。
- 内容分类决定标题是否是技术占位。
- 用户标题永远受保护。
- 真实可读文件名保留。
- 技术文件名统一替换为“地区 + 运动”或“运动”。
- 旧版本已入库技术标题在升级后自动修复。

## 1. 已确认问题

当前 DB 中 Zwift 样本：

```text
file_name = 23811652091_ACTIVITY.fit
title = 23811652091_ACTIVITY.fit
title_source = file_name
sport_type = cycling
sub_sport_type = virtual_activity
region_display = Temotu/所罗门群岛
```

当前 `_is_technical_activity_title("23811652091_ACTIVITY.fit") == False`，且 `build_activity_display_title()` 只对 `source == "filename"` 做 filename-like 清洗，未把历史来源 `file_name` 等价纳入。最终技术文件名被误判为可读标题。

## 2. 统一标题契约

### 2.1 source 分类

- 保护来源：`manual`、`user`、`edited`
- 自动来源：`auto`、`auto_sport`、`auto_region_sport`、`garmin_auto`、`coros_auto`、`region_auto`
- filename-like 来源：`filename`、`file_name`、`file`、`path`、`fit`
- 其他来源：按内容分类判断；source 本身不得成为覆盖依据

### 2.2 内容分类

必须判为技术标题：

- 空标题
- 纯长数字或长 hash
- provider 临时路径 / 临时文件名，例如 `activity-fit-files`
- 长数字 + provider 动作后缀，例如 `23811652091_ACTIVITY.fit`
- provider 动作前缀 + 长 id，例如 `activity_23811652091`
- 设备型号 + 日期 / 时间 / 长 id，例如 `MAGENE_C706_2026-06-28_154456_196852.fit`

必须保留为可读标题：

- 用户手动标题
- 真实赛事 / 路线 / 地名文件名，例如 `都江堰半程马拉松.fit`
- 带真实语义的标题后接 provider id 后缀，例如 `雅安市 骑行_23535321841-1-1.fit`，应清洗为 `雅安市 骑行`
- 包含年份但不是 provider 技术结构的赛事名，例如 `2026成都马拉松.fit`

### 2.3 输出规则

```text
protected user title -> 原样保留
readable filename-like title -> 清洗扩展名 / 尾部 provider id 后保留
technical title + region_display -> 地区前缀 + 运动中文名
technical title + no region -> 运动中文名
auto title + region_display -> 地区前缀 + 运动中文名
auto title + no region -> 运动中文名
```

Zwift `virtual_activity` 不新增独立“虚拟活动”中文标题；使用主运动 `cycling -> 骑行`。因此样本期望：

```text
23811652091_ACTIVITY.fit + Temotu/所罗门群岛 + cycling -> Temotu 骑行
```

## 3. 允许修改范围

- `profile_backend.py`
  - 标题 source 分类 helper。
  - 技术标题内容分类 helper。
  - `build_activity_display_title()`。
  - `_can_region_update_activity_title()`。
  - 旧库标题修复 migration。
- `main.py`
  - 启动时接入独立标题修复 migration。
- `tests/test_fit_sync.py`
  - 标题分类、导入修复、地区回填、旧库升级回归测试。
- `docs/`
  - 本任务清单和执行记录。

## 4. 非目标

- 不把所有 `title_source='filename'` 都覆盖。
- 不覆盖 `manual/user/edited`。
- 不让前端根据文件名推导标题。
- 不改变真实活动文件名的展示语义。
- 不要求用户重新导入 FIT。

## 5. 任务总览

| 顺序 | 任务 | 类型 | 状态 | 发布门槛 |
| --- | --- | --- | --- | --- |
| 1 | TITLE-GOV-01 冻结 source/content 分类契约 | 契约 | Done | 标题保留和覆盖规则不再散落 |
| 2 | TITLE-GOV-02 实现统一标题分类 helper | 后端 | Done | `file_name` 与 `filename` 等价进入 filename-like 分类 |
| 3 | TITLE-GOV-03 修复 build 与地区回填标题决策 | 后端 | Done | 技术标题统一输出地区+运动或运动 |
| 4 | TITLE-GOV-04 实现旧库标题升级 migration | 后端迁移 | Done | 老用户升级后自动修技术标题 |
| 5 | TITLE-GOV-05 聚焦测试与真实样本 dry-run | 测试 | Done | Zwift、COROS、Magene、真实赛事名均有覆盖 |

## 6. 验收矩阵

| 输入标题 | source | 地区 | 期望 |
| --- | --- | --- | --- |
| `23811652091_ACTIVITY.fit` | `file_name` | `Temotu/所罗门群岛` | `Temotu 骑行` |
| `260805055744.fit` | `file_name` | 空 | `骑行` |
| `MAGENE_C706_2026-06-28_154456_196852.fit` | `filename` | 空 | `骑行` |
| `Magene C706 1785880546 196852` | `filename` | `名山区/中国` | `名山区 骑行` |
| `都江堰半程马拉松.fit` | `filename` | `成都市/中国` | `都江堰半程马拉松` |
| `2026成都马拉松.fit` | `filename` | `成都市/中国` | `2026成都马拉松` |
| `雅安市 骑行_23535321841-1-1.fit` | `filename` | `雅安市/中国` | `雅安市 骑行` |
| `我的晨骑` | `user` | 任意 | `我的晨骑` |

## 7. 执行记录

- 文档创建时间：2026-08-08
- 当前状态：`Implemented`
- 实现说明：
  - `session_label` 与可读 filename 进入同一个标题决策器。
  - `file_name` / `filename` 通过同一套内容分类进入 filename-like 处理。
  - 技术文件名会统一回落到地区+运动或运动。
  - 旧库标题通过 `activity_title_canonical_repair_v1` 自动修复。
- 真实样本验证：
  - `23811652091_ACTIVITY.fit` 最终标题为 `Temotu 骑行`
  - `title_source = auto_region_sport`
- 测试结果：
  - `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_parser.py -q`：17 passed，3 skipped，13 subtests passed
  - `PYTHONPATH=. .venv312/bin/python -m pytest tests/test_fit_sync.py -q`：172 passed，4 subtests passed
  - `PYTHONPATH=. .venv312/bin/python -m py_compile fit_engine.py profile_backend.py main.py tests/test_fit_parser.py tests/test_fit_sync.py`：通过
