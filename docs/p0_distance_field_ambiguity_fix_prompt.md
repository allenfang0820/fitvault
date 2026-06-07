# 任务：修复 activities.distance 字段单位歧义（P0-A / P0-B）

## 🎯 任务目标

消除 `activities.distance` 字段在主流程中的**单位歧义**。当前 `main.py:1495-1496` 错误地将 `distance_km`（公里值）写入 `distance` 字段（语义暗示米），导致复盘覆盖层 ECharts X 轴距离仅 0.008 km 而非真实 ~12 km 距离。

**违反契约**：
- §2.1 字段全链路可追溯 — 字段名 `distance` 暗示米但存 km
- §V4.0 防腐层 — `distance` 与 `dist_km` 双字段并存，构成"双真相源"风险

**修复策略**：**方案 2（最小改动）** — 修正 `distance` 字段为**真存米**，与 `dist_km` 形成明确语义区分（米/公里双字段并存，无歧义）。

---

## 🛠️ 具体执行动作（4 步）

### Step 1：修正 `distance` 字段单位（DB 写入源头）

**位置**：`main.py:1495-1496`

**现状**：
```python
result["distance"] = distance_km   # ❌ 暗示米，实际存 km
result["dist_km"] = distance_km    # ✓ 正确单位
```

**改为**：
```python
# V8.x 修复 distance 字段歧义:distance = 米,dist_km = 公里
# §2.1 字段全链路可追溯,严禁双字段同值
result["distance"] = distance_km * 1000.0  # 米(与 dist_km 形成语义对偶)
result["dist_km"] = distance_km             # 公里
```

**注意**：若 `distance_km` 可能是 `None`/0，请先 `distance_km or 0` 防护。

---

### Step 2：修正 `_build_fatigue_review_snapshot` 的 `total_distance_m` 计算

**位置**：`main.py:5259-5261`

**现状**：
```python
total_distance_m = _safe_float(row.get("distance") or row.get("dist_km"))
if (row.get("distance") is None) and (row.get("dist_km") is not None):
    total_distance_m = _safe_float(row.get("dist_km")) * 1000.0
```

**改为**：
```python
# V8.x 修复:distance 字段已对齐米单位,无需 fallback
# 防御性双源读取:优先 distance(米),降级 dist_km(公里)*1000
dist_m_field = _safe_float(row.get("distance"))
dist_km_field = _safe_float(row.get("dist_km"))
if dist_m_field and dist_m_field > 0:
    total_distance_m = dist_m_field
elif dist_km_field and dist_km_field > 0:
    total_distance_m = dist_km_field * 1000.0
else:
    total_distance_m = 0.0
```

---

### Step 3：修正其他两处 `distance` 消费点

**位置 A**：`main.py:3545`（detail API 距离）
**位置 B**：`main.py:5932`（`_build_record_from_row`）

**现状（两处类似）**：
```python
dist_km = _safe_float(row.get("distance") if row.get("distance") is not None else row.get("dist_km"))
```

**改为**：
```python
# V8.x 修复: distance 已对齐米单位,需 / 1000 转公里
dist_m_field = _safe_float(row.get("distance"))
dist_km_field = _safe_float(row.get("dist_km"))
if dist_m_field and dist_m_field > 0:
    dist_km = dist_m_field / 1000.0
else:
    dist_km = dist_km_field or 0.0
```

---

### Step 4：L1041 兼容性检查（无需改但需确认）

**位置**：`main.py:1038-1042`

**现状**：
```python
dist_km = _safe_float(row.get("dist_km"), 0.0)
if dist_km <= 0:
    # 兼容 distance(米)字段
    dist_m = _safe_float(row.get("distance"), 0.0)
    if dist_m > 0:
        # 此处 dist_m 实际可能是 km(因歧义),但因为 dist_km<=0 时这分支仅作兜底
        ...
```

**约束**：本次修复**不改 L1041**（其原本就期望 `distance` 是米，修复后语义终于对齐）。但请确认该函数下游是否对 dist_m 做了 `/ 1000` 转 km，若是则需调整。**阅读后判定**。

---

## ⚠️ 检查与约束

### 必须验证

1. **DB 迁移**：现有 DB 中已存在的 `activities.distance` 字段都是 km 值（错值）。修复代码后：
   - **老数据**：新代码会读 `distance`（错值 km 当米）→ `total_distance_m = 12.5`（应 12500）→ 仍错
   - **新数据**：导入新活动后 `distance = distance_km * 1000`（正确）
   - **结论**：修复后**老活动**的复盘 ECharts X 轴仍异常（但前端已用 `curves.total_distance_m` 透传，**前端 X 轴来自后端 `_build_fatigue_review_snapshot` 的 total_distance_m，不直接读 row.distance**，所以老数据可能正常！）
   - **进一步验证**：需在测试中跑一个老活动快照，确认 X 轴正常

2. **回滚脚本**：
   ```sql
   -- 旧数据:把 distance (km 错值) 重新写为 distance(米 正确)
   -- 这是修正 DB 错值的迁移(可推迟,前端不会直接读 distance 字段)
   -- 不在本次代码修复范围,留作后续 migration 任务
   ```

3. **不在本次范围**：
   - 不修改前端 `track.html` 的 `Cesium.Cartesian3.distance()`（几何 API 与字段无关）
   - 不修改 `metrics_resolver.py`（无 distance 字段引用）
   - 不修改 DB schema（沿用 `distance` 字段名，仅修正写入语义）

### 修复后预期

- 复盘 ECharts X 轴：跑步 12 km → 显示 `0` `3` `6` `9` `12` km ✓
- 折线 `hr` / `speed` / `gap` 全程显示 ✓
- 疲劳带 `fatigue_zones` 不受影响（已为 V8.11 fix） ✓
- 30+ 个 "等效速度 (GAP)" legend 重复项 → 消失（因为 X 轴正确后 tooltip 正常）

---

## 📋 实施前检查清单

- [ ] 已阅读 `main.py:1038-1042`（Step 4）确认是否需调整
- [ ] 已搜全部 `row.get("distance")` / `row["distance"]` 引用（已确认 4 处）
- [ ] 已确认 `track.html` 几何 API 与本次修复无关
- [ ] 已确认 `metrics_resolver.py` 无 `distance` 字段引用
- [ ] 已规划"老数据 DB 迁移"为后续任务（不在本次范围）

## 📋 实施后验证清单

- [ ] Step 1 修改后，运行：
      `python3 -m pytest tests/test_real_laps_resolver.py tests/test_activity_canonical_resolver.py -v`
      （确认无回归）
- [ ] Step 2-3 修改后，运行：
      `python3 -m pytest tests/test_fatigue_review_e2e_contract.py -v`
      （确认 E2E 联调测试仍 32/32 通过）
- [ ] 整体回归：
      `python3 -m pytest tests/ -q`
      （确认 705 tests 全部通过）
- [ ] 启动 pywebview + 打开老活动 + 复盘覆盖层：
      - 视觉验证 X 轴距离合理（5-20 km 量级）
      - 视觉验证 GAP legend 不再重复 30+ 次
      - 视觉验证疲劳带 markArea 显示

## 完成定义

- 4 处 `distance` 消费点全部修正
- 705 tests 全过
- 手工冒烟 X 轴显示正常
- 完成后请回复："distance 字段单位歧义已修复,前端契约对齐"。
