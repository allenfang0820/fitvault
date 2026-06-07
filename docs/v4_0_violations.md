# V4.0 防腐层违规清单

> 状态：V4-1 静态审计完成
> 生成时间：V4-1 阶段
> 审计工具：`_audit_v4.py`（AST 启发式分类）

## 一、整体规模

| 维度 | 数值 |
|---|---|
| `main.py` 总行数 | 6780 |
| `metrics_resolver.py` 总行数 | 1866 |
| **比例** | **3.6 : 1**（main.py 业务计算冗余）|
| `main.py` 总函数/方法数 | 202 |
| `main.py` 业务计算违规数 | **25**（7 纯计算 + 18 mixed 拆分） |

## 二、6 个核心 V4.0 违规项（治理第二期目标）

| 序号 | 名称 | 位置 | 类型 | 下沉策略 |
|---|---|---|---|---|
| ① | `SemanticSportsEngine` | L6147-6245+ | 完整类 | **纯计算，整体下沉** |
| ② | `calculate_track_difficulty` | L101-160 | 模块级函数 | **纯计算，整体下沉** |
| ③ | `_build_ai_snapshot` | L2731-2830+ | 模块级函数 | 🟠 mixed（含 IO） |
| ④ | `_build_ai_snapshot_block` | L2833-2920+ | 模块级函数 | 🟠 mixed（含 IO） |
| ⑤ | `_build_activity_canonical` | L5897（嵌套 in L5889）| 嵌套函数 | **纯计算，整体下沉** |
| ⑥ | `_build_real_laps_from_row` | L6236 | 模块级函数 | **纯计算，整体下沉** |
| ⑦ | `_compute_advanced_metrics` | L1045-1399 | 模块级函数 | 🟠 mixed（含 IO） |

> **注**：原提示词列了 6 项，实际审计发现 `main.py` 中 V4.0 相关违规 7 项（含 `_build_ai_snapshot` 与 `_build_ai_snapshot_block` 两个独立函数）。所有 mixed 类型需按"**IO 隔离警告**"拆分：IO 查询留在 main.py，纯计算下沉。

## 三、6 个核心违规项详细审计

### ① `SemanticSportsEngine`（L6147）

**类型**：完整类（98 行，类内含纯数据 + 纯计算静态方法）

**审计结果**：
- 含 `METRICS` 字典（数据）
- 含 `SPORT_PROFILES` 字典（数据）
- 含 `build_display_metrics` / `get_layout` / `get_summary_keys` 等方法（**纯计算**）
- 无 IO 调用

**V4.0 策略**：**整体下沉**至 `MetricsResolver._build_display_metrics()` + `MetricsResolver._get_sport_layout()` + `MetricsResolver._get_summary_keys()`（拆分大类为多个独立方法）

**周边保护**：被 `_build_record_from_row` 在 line 6271 消费（`SemanticSportsEngine.build_display_metrics(display_type, raw_for_engine)`），下沉后**调用点不变**。

---

### ② `calculate_track_difficulty`（L101）

**类型**：模块级函数（约 60 行）

**审计结果**：
- 4 类难度等级（easy / moderate / hard / extreme）
- 纯计算（gain_m / distance_m / max_alt_m 输入 → 难度等级输出）
- 无 IO 调用

**V4.0 策略**：**整体下沉**至 `MetricsResolver._calculate_track_difficulty(gain_m, distance_m, max_alt_m, max_single_climb_m) -> dict`

**周边保护**：被多处调用（`_build_record_from_row` / 雷达图 / 轨迹报告），下沉后**调用点不变**。

---

### ③ `_build_ai_snapshot`（L2731）

**类型**：模块级函数（约 100 行），组装 7 段 AI Snapshot

**审计结果**：
- 含 **IO 查询**：`_fetch_efficiency_baseline(db_path=str(DB_PATH), ...)` → 含 SQLite 查询
- 含 **纯计算**：组装 7 段 metrics / tags / drift / decoupling / bonk / events
- 调用 `_build_ai_snapshot_block` (L2833)

**V4.0 策略**：**IO 隔离拆分**：
- main.py 保留：`_fetch_efficiency_baseline(db_path=...)` 调用（IO 查询）
- main.py 改造：`_build_ai_snapshot` 改为先查 `baseline_data`，再传给 Resolver 纯计算
- Resolver 新增：`MetricsResolver._build_ai_snapshot_block(row, sport_type, baseline_data)` 接收 baseline_data 而非 db_path

**IO 隔离警告落实**：
```python
# main.py - IO 层（保留）
baseline_data = MetricsResolver._fetch_efficiency_baseline(
    db_path=str(DB_PATH), sport_type=sport_type, current_activity_id=...
)
# 纯计算下沉
ai_snapshot = MetricsResolver._build_ai_snapshot_block(
    row=row, sport_type=sport_type, baseline_data=baseline_data
)
```

---

### ④ `_build_ai_snapshot_block`（L2833）

**类型**：模块级函数（约 90 行），AI Snapshot block 装配

**审计结果**：脚本识别为 mixed，但实际可能仅含纯计算（取决于 `snapshot` 入参）

**V4.0 策略**：与 ③ 合并处理，统一下沉至 `_build_ai_snapshot_block(row, sport_type, baseline_data)`

---

### ⑤ `_build_activity_canonical`（L5897）

**类型**：嵌套函数（在 `Api.load_activity_track` 内）

**审计结果**：
- 接收 `r: dict` 输入，组装轨迹报告 activity_canonical
- 纯计算（含 MTDI 难度映射、累计距离、海拔等）
- 无 IO 调用

**V4.0 策略**：**整体下沉**至 `MetricsResolver._build_activity_canonical(raw_data) -> dict`

**周边保护**：被 `Api.load_activity_track`（L5889）调用，下沉后**调用点不变**。

---

### ⑥ `_build_real_laps_from_row`（L6236）

**类型**：模块级函数（任务 1 已修改），消费 DB row 转换为前端 lap 格式

**审计结果**：
- 接收 row dict 输入
- 纯转换（DB row → UI 格式）
- 无 IO 调用

**V4.0 策略**：**整体下沉**至 `MetricsResolver._build_real_laps_for_ui(laps_json: str | list) -> list[dict]`

**周边保护**：被 `_build_record_from_row`（L6261）调用，**已通过任务 1 的 9 个测试**，下沉后调用语义不变。

---

### ⑦ `_compute_advanced_metrics`（L1045）

**类型**：模块级函数（约 350 行），训练负荷 / 解耦率 / 踏频稳定性 / 耐久性 / 功率等高级指标

**审计结果**：
- 含多次 `MetricsResolver._compute_*` 调用（**已被下沉**）
- 但 main.py 仍存有 wrapper
- 可能含 IO（待精确审计）

**V4.0 策略**：**整体下沉**至 `MetricsResolver._compute_advanced_metrics(record_data) -> dict`，移除 main.py wrapper

---

## 四、main.py 周边 metrics 白名单（**严禁误删**）

| 类别 | 关键字 |
|---|---|
| 计算调用 | `decoupling_pct` / `_fetch_historical_metrics_avg` / `bonk_risk` / `_detect_bonk_event` |
| 训练负荷 | `training_load` / `_compute_training_load` / `hr_zone_distribution` |
| 趋势 | `_fetch_efficiency_trend` / `_fetch_durability_trend` / `_fetch_cadence_stability_trend` |
| 比率 | `_fetch_load_ratio_7d_42d` / `_fetch_training_load_trend` |

> 这些**部分**已被 Resolver 内部方法实现，但 main.py 仍消费其结果。下沉过程中**必须保留**这些消费点，不得误删。

## 五、已下沉的 Resolver 内部方法（**避免重复实现**）

```
metrics_resolver.py 现有方法(L288-1680+):
  _build_storage_model / _build_view_model / _build_analysis_pack / _build_ai_context
  _calculate_calories_per_minute
  _calculate_fatigue_zones   ← V4-0 治理
  _normalize_laps             ← 任务 1
  _compute_efficiency_score
  _compute_training_load
  _compute_cadence_stability
  _compute_durability_index
  _compute_hr_drift
```

**下沉新方法时**：若 Resolver 已有同名/类似方法，**优先复用**，不重复实现。

## 六、V4.0 治理第二期执行计划

| 步骤 | 目标 | 预计减少 main.py 业务计算函数 |
|---|---|---|
| V4-1 审计 | 输出本清单 | 0（仅观察）|
| V4-2 周边保护 | 编写周边保护测试 | 0 |
| V4-3 calculate_track_difficulty | 下沉 | 1（25 → 24）|
| V4-4 SemanticSportsEngine | 下沉整个类 | 1（24 → 23，类内多个方法）|
| V4-5 _build_ai_snapshot(_block) | 下沉（IO 隔离）| 2（23 → 21）|
| V4-6 _build_activity_canonical | 下沉 | 1（21 → 20）|
| V4-7 _build_real_laps_from_row | 下沉 | 1（20 → 19）|
| V4-8 _compute_advanced_metrics | 下沉 | 1（19 → 18）|
| V4-9 整体回归 | 静态分析断言 | 0 |

## 七、关键风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 周边 metrics 白名单误删 | 🟠 中-高 | V4-2 周边保护测试 |
| `_build_ai_snapshot` IO 隔离不彻底 | 🟠 中-高 | 静态分析 + IO 隔离警告 |
| 端到端 envelope 破坏 | 🟡 中 | 集成测试 + 整体回归 |
| 任务 1-5 回归失败 | 🟡 中 | 复用既有测试 |
| Token 截断 / 烂尾 | 🔴 高 | 强制分步执行 |
