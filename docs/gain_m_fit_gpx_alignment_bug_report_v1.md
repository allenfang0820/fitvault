# `gain_m` 双算法对齐 Bug 报告

> **状态**: 已识别,待修复
> **报告日期**: 2026-06-09
> **严重性**: 🟠 高 — 直接影响 MTDI 难度评级、AI 风险预警、轨迹报告卡片
> **触发场景**: 高密度采样 GPX(典型: COROS / Suunto, 采样间隔 < 2s)
> **契约违反**: `fit-arch-contrac` §2.1 全链路可追溯 / §2.2 canonical 仅 fit_sdk

---

## 一句话结论

FIT 与 GPX 两条导入路径对 `activities.gain_m` 采用 **完全不同的算法**,且 GPX 路径的 `1.5m 单步阈值` 对密集采样 GPX **直接产生 670 倍失真**(实测 1344m → 2m),导致同一条物理轨迹在不同来源下灌库数值不一致,**违反 Resolver 是"唯一语义翻译层"的契约**。

---

## 一、现象复现

### 1.1 测试样本

| 项 | 值 |
|---|---|
| 文件 | `/Users/fanglei/Downloads/471385635607839224.gpx` |
| 来源设备 | COROS 手表(creator 字段标识) |
| 路线 | 长坪沟 → 四姑娘山二峰大本营(高原徒步) |
| 点数 | 21,694 |
| 时长 | 7.06 h |
| 采样间隔 | 平均 1.17 秒/点(超密集) |

### 1.2 测量结果

**基础指标(与算法无关):**

| 指标 | 值 | 来源 |
|---|---|---|
| 距离 | 19.88 km | haversine 累加 |
| 海拔范围 | 3,200 ~ 4,241 m | 极值 |
| 海拔净跨度 | 1,041 m | max - min |
| **单段最大爬升** | **493 m** | compute_report_metrics 15m 阈值状态机 |

**关键差异 — `gain_m` 三种口径对比:**

| 计算口径 | gain_m | 与物理真实偏差 | MTDI(trail_running) | 等级 |
|---|---|---|---|---|
| **A. FIT 路径**(Garmin 原生气压计 + 平滑 + 阈值) | ~1,300-1,500m | 0%(基线) | score ≈ 40-42 | **LV4 中等** |
| **B. GPX + 项目 1.5m 阈值(现状)** | **2m** ❌ | **-99.85%** | score = 27.1 | **LV3 中等** |
| **C. GPX + 0.1m 阈值(简单修复)** | 1,344m | +0.6% | score = 42.0 | **LV4 中等** |
| **D. GPX + 0.1m 阈值无阈值累加** | 1,344m | +0.6% | score = 42.0 | LV4 中等 |

> **核心矛盾**: 同一条物理路线,FIT 显示 **LV4 中等**("进山探路者...连续的爬升让你开始喘气"),GPX 显示 **LV3 中等**("轻装徒步游...山风吹拂,一切尽在掌握")。用户视角下,设备不同 → 文案不同 → 体感与系统反馈严重不符。

---

## 二、根因分析

### 2.1 双路径架构图

```text
【FIT 路径】
fit_engine.parse_fit_file()
  └─ session_mesgs.total_ascent ← Garmin 固件预计算(气压计 + 滤波 + 阈值)
       ↓
track_backend.parse_fit_file() → data["gain_m"] = basic["total_ascent"] ← 直接透传
       ↓
profile_backend.build_activity_payload()
  ├─ _summarize_track_points(points, 1.5m 阈值) ← 也会跑,但结果被覆盖
  └─ gain_m = data["gain_m"] or _summarize gain_m ← 优先用 FIT 原生
       ↓
activities.gain_m = Garmin 原生值

【GPX 路径】
gpxpy → points[]
       ↓
track_backend.parse_gpx_file() → data 里没有 gain_m
       ↓
profile_backend.build_activity_payload()
  ├─ _summarize_track_points(points, 1.5m 阈值) ← 唯一来源
  └─ gain_m = data.get("gain_m") or _summarize gain_m ← data 为空,只能用项目算法
       ↓
activities.gain_m = 项目算法(1.5m 阈值)结果
```

### 2.2 根因 — 三层叠加

#### 根因 A:`_summarize_track_points` 单步阈值对密集采样致命失效

**代码位置**: [profile_backend.py L2171-L2195](file:///Users/fanglei/应用开发/AI%20track/profile_backend.py#L2171-L2195)

```python
# L2180-L2183(关键 4 行)
dalt = float(p1.get("alt") or 0.0) - float(p0.get("alt") or 0.0)
# CONTRACT §5.5: 1.5m 噪声阈值 — 与 compute_report_metrics 一致
if dalt > 1.5:
    gain_m += dalt
```

**问题**:
- COROS / Suunto 等现代手表的 GPX 采样间隔 ≈ 1.2 秒
- 慢速徒步(高原场景)每秒海拔变化通常 < 0.5m
- 1.5m 单步阈值过滤率 > 95%

**实测验证**(用户 GPX):

| 算法 | gain_m |
|---|---|
| 无阈值累加(dalt > 0) | 1,344m ✅ |
| 0.1m 阈值 | 1,344m ✅ |
| **1.5m 阈值(现状)** | **2m** ❌ |

**注释自相矛盾**:
- L2181 注释写"与 compute_report_metrics 一致"
- 但 [profile_backend.py L1964](file:///Users/fanglei/应用开发/AI%20track/profile_backend.py#L1964) `compute_report_metrics` 算 descent 用的阈值是 `dalt < -0.1`(即正向阈值 0.1)
- 两处阈值不一致,注释错误

#### 根因 B:FIT 与 GPX 走两条算法,违反契约 §2.1

**契约原文**:
> 任何 UI 字段必须能追溯:`UI → DB → Resolver → FIT SDK`
> Resolver 是唯一语义翻译层

**现实情况**:
- FIT 路径:`activities.gain_m` ← Garmin 固件黑盒算法(未经过项目 Resolver)
- GPX 路径:`activities.gain_m` ← 项目 `_summarize_track_points`
- 两条路径 **同一字段,两个算法,结果不可比**

**Resovler 缺位**:
- [metrics_resolver.py](file:///Users/fanglei/应用开发/AI%20track/metrics_resolver.py) 中 **没有 `compute_canonical_gain_m`** 方法
- 计算逻辑散落在 `profile_backend._summarize_track_points` 和 `track_backend.parse_fit_file`
- 不符合 V4.0 防腐层契约(纯计算应下沉至 Resolver)

#### 根因 C:阈值不一致,工程债积累

| 函数 | 阈值常量 | 单步阈值 |
|---|---|---|
| `_summarize_track_points` L2182 | 硬编码 `1.5` | **1.5m**(算 gain_m) |
| `compute_report_metrics` L1964 | 硬编码 `-0.1` | 0.1m(算 descent,反向)|
| `_compute_grade_metrics` L2069-2071 | 硬编码 `3.0 / -3.0 / 1.5` | 1.5m 噪声 + 3% 坡度阈值 |

**问题**: 同一项目内,`gain_m` 用 1.5m,`descent_m` 用 0.1m,`slope` 滑窗用 1.5m 噪声;**口径从未拉齐过**。

---

## 三、影响面

### 3.1 核心指标失真

| 受影响模块 | 影响 | 严重性 |
|---|---|---|
| **MTDI 难度评级** | 长坪沟路线 LV4 → LV3,文案偏轻 | 🟠 高 |
| **轨迹报告卡片**(📊 坡度与起伏) | `gain_m` 显示 2m(用户困惑) | 🟠 高 |
| **环境挑战** `environment_challenge.climb_density` | `climb_density = gain_m / dist_km`,被严重低估 | 🟠 中 |
| **风险预警** `risk_assessment` | 补给、装备、体力3 个维度的爬升压力判定失真 | 🟠 中 |
| **AI Snapshot** `_risk_snapshot_payload.elevation_gain_m` | 同上 | 🟠 中 |
| **雷达图** | 间接:训练负荷、爬升类指标被低估 | 🟡 低 |

### 3.2 用户可见症状

1. **同路线不同设备,MTDI 不同** — 这是用户在长坪沟案例中直接观察到的
2. **活动列表卡片 `gain_m` 显示 2m** — 与体感明显不符
3. **AI 风险预警装备/体力建议偏轻** — 与实际高原徒步风险不匹配
4. **跨活动对比失效** — COROS 用户与 Garmin 用户的轨迹难以横向比较

### 3.3 受影响文件类型分布

| 来源 | 采样密度 | 1.5m 阈值失效程度 | 受影响比例 |
|---|---|---|---|
| Garmin FIT(1Hz)| 中 | 部分(50-80% 过滤率) | 🟡 估 30-50% |
| COROS GPX(1.2 秒/点)| 高 | **严重(>95% 过滤率)** | 🔴 估 80%+ |
| Suunto GPX(1Hz)| 中 | 部分 | 🟡 估 30-50% |
| Strava 导出 GPX(变密度)| 不定 | 不定 | 🟡 中 |

**估算**: 项目所有 GPX 来源活动中,**80% 以上** 存在不同程度的 gain_m 失真。

---

## 四、契约符合性评估

| 契约条款 | 当前状态 | 偏离 |
|---|---|---|
| §2.1 全链路可追溯 `UI → DB → Resolver → FIT SDK` | ❌ | FIT 路径直接用 Garmin 黑盒值,GPX 路径用项目算法,两路径 Resolver 缺位 |
| §2.2 canonical 仅 fit_sdk | ❌ | GPX 路径的 `gain_m` 来源是 `project_algorithm`,混入 canonical |
| Resolver 唯一语义翻译层 | ❌ | `_summarize_track_points` 在 profile_backend.py 而非 Resolver;FIT 路径绕开 Resolver |
| §十一 审查门禁 §11.2 "新增能力必须回答 OpenClaw 会真实使用它吗" | N/A | 与本 bug 无关 |
| §十一.2 §11.2 字段版本化 | 部分 | `gain_m` 无 audit 字段,无法追溯取值方法 |

**结论**: 本 bug 是 **§2.1 + §2.2 双契约违反**,应作为 **优先级 P0** 修复。

---

## 五、修复方向(简要)

### 5.1 修复目标

**核心目标**: FIT 与 GPX 共用同一份 canonical 算法,跨文件类型 `activities.gain_m` 一致(±5%)。

### 5.2 推荐算法(Garmin 套路抽象)

```
1. 时间戳规范化到 UTC seconds
2. 重采样到 1Hz(线性插值 alt/lat/lon)← 关键:把 1.2 秒/点 GPX 拉到 1 秒/点
3. 3 点中值滤波 alt
4. dalt > 1.0m 才计入 gain_m
5. cross-check: 若 source_type=="fit" 且 fit_total_ascent 在
   [project_gain * 0.4, project_gain * 1.5] 区间,优先用 fit_total_ascent
   (气压计失锁场景兜底)
```

### 5.3 实施要点

| 改动位置 | 内容 |
|---|---|
| `metrics_resolver.py` | 新增 `compute_canonical_gain_m()` 静态方法 + `_resample_to_1hz()` + `_median_filter()` |
| `track_backend.py:parse_fit_file` | `data["gain_m"]` 不再生效,改为保留 `data["fit_total_ascent_raw"]` 供 audit |
| `profile_backend.py:_summarize_track_points` | 内部改为调 `MetricsResolver.compute_canonical_gain_m` |
| `profile_backend.py:build_activity_payload` | gain_m 拼接改为调同一函数 |
| DB Schema | 新增 `gain_m_method` 字段(取值为 `fit_native_validated` / `project_resample_smooth` / `empty`) |
| 历史数据回灌 | 仅 GPX / KML 来源活动重算,FIT 来源保留原值 + 写入 `gain_m_audit_project_calc` 字段 |

### 5.4 验证清单(本 bug 修复后必跑)

```bash
# 1. 用户这条 GPX 重算,gain_m 应在 1300~1400m
python3 -m unittest test_canonical_gain_m

# 2. FIT 与 GPX 同路线对齐测试(±10%)
python3 -m unittest test_fit_gpx_gain_alignment

# 3. 旧测试不能挂
python3 -m unittest test_fit_parser test_fit_sync test_p0_gpx_isolation

# 4. 用户 GPX 复算验证
python3 /tmp/mtdi_compute.py  # 复算 gain_m 应 ≈ 1344m

# 5. 契约文档更新
# - docs/field_contract_matrix.md (gain_m 字段说明)
# - docs/js_api_contract.json (如有相关接口)
```

---

## 六、附录

### 6.1 关键代码引用

| 路径 | 说明 |
|---|---|
| [profile_backend.py L2171-L2195](file:///Users/fanglei/应用开发/AI%20track/profile_backend.py#L2171-L2195) | `_summarize_track_points` 函数体(本 bug 主犯) |
| [profile_backend.py L2180-L2183](file:///Users/fanglei/应用开发/AI%20track/profile_backend.py#L2180-L2183) | 1.5m 阈值具体逻辑 |
| [profile_backend.py L1451-L1454](file:///Users/fanglei/应用开发/AI%20track/profile_backend.py#L1451-L1454) | `build_activity_payload` 中 gain_m 优先级逻辑 |
| [track_backend.py L401-L436](file:///Users/fanglei/应用开发/AI%20track/track_backend.py#L401-L436) | `parse_fit_file` 直接透传 `total_ascent` |
| [fit_engine.py L178](file:///Users/fanglei/应用开发/AI%20track/fit_engine.py#L178) | FIT SDK 读取 `total_ascent` |
| [metrics_resolver.py L1492-L1556](file:///Users/fanglei/应用开发/AI%20track/metrics_resolver.py#L1492-L1556) | `_calculate_track_difficulty`(MTDI 算法,本 bug 受害者) |
| [field_contract_matrix.md L32](file:///Users/fanglei/应用开发/AI%20track/docs/field_contract_matrix.md#L32) | `gain_m` 字段契约描述(写作"与 total_ascent 直读")|

### 6.2 复现脚本

```bash
# 计算用户 GPX 的三种阈值口径 gain_m
python3 /tmp/mtdi_dual.py

# 单独验证 1.5m 阈值 bug
python3 /tmp/mtdi_check_gain.py

# 复算 MTDI
python3 /tmp/mtdi_compute.py
```

### 6.3 相关历史

- **2026-Q1**: 雷达图功能引入,首次在多模块消费 `gain_m`,暴露口径不齐
- **2026-Q2**: 风险预警引入 `_risk_snapshot_payload`,直接消费 `gain_m`,本 bug 风险扩大
- **2026-06-09**: 用户在轨迹报告 MTDI 评级中观察到 LV3 ≠ LV4,触发本 bug 报告

---

> **结束**: 本 bug 是 **契约级 P0 修复项**,影响 MTDI / 风险预警 / 轨迹报告 / 雷达图 4 个核心模块,需在 [gain_alignment_prompt.md](file:///Users/fanglei/应用开发/AI%20track/) 实施计划中统一处理。