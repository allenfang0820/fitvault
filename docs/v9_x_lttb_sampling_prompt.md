# 任务：活动轨迹缩略图采样升级为 LTTB 曲率感知降采样（V9.x-LTTB）

> 立项依据：docs/b_plus_canvas_track_thumbnail_prompt_v2.md (B+ Canvas v2 已上线,但用户反馈轨迹仍不平滑)
> 根因：docs/analysis_lttb_vs_douglas_peucker.md → 行业调研结论
> 契约参考：fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层 / §五 AI 边界 / §八 Canonical DB / §九 目录 / §十 Non-Goals
> 工作量：≤ 0.5 个工作日 | 后端业务逻辑改动文件：1 个 (metrics_resolver.py)

---

## 一、根因（已确认）

> **核心违约**：`thumbnail_points` 走的是 [main.py:5905-5916 `_sample_thumbnail_points`](file:///Users/fanglei/应用开发/AI track/main.py#L5905-L5916) 的**等距采样 `points[::step]`**，是 §2.1 字段全链路可追溯的**第 1 步就丢失视觉特征**。

### 4 个层级的问题链

| # | 层级 | 位置 | 现状 |
|---|---|---|---|
| L0 | **采样器** | [main.py:5905-5916](file:///Users/fanglei/应用开发/AI track/main.py#L5905-L5916) `_sample_thumbnail_points` | **❌ 等距切片，丢失弯道顶点** |
| L1 | 采样器调用方 | [main.py:5911](file:///Users/fanglei/应用开发/AI track/main.py#L5911) 仍是 `_sample_thumbnail_points` | ❌ 容器待替换 |
| L2 | 上游 Resolver | (无,采样是 main.py 内的辅助函数) | 需下沉到 Resolver |
| L3 | Canvas 渲染 | [track.html:6067-6073](file:///Users/fanglei/应用开发/AI track/track.html#L6067-L6073) | ✅ B+ Canvas v2 渲染正确 |

**关键数据**：
- 5000 点 GPS 轨迹 → `step=5000//48=104` → **每 104 个点采 1 个**
- 半马 (21km, ~6300 点) → 弯道采样间隔 ≈ **437 米**
- 全马 (42km, ~12600 点) → 弯道采样间隔 ≈ **875 米**

### 行业对照（不允许的方案）

| 方案 | 费用 | 访问限制 | 脉图适用性 |
|---|---|---|---|
| **LTTB**（推荐） | ✅ 免费 | ✅ 无 | ✅ §十 完全契合 |
| Douglas-Peucker | ✅ 免费 | ✅ 无 | ⚠️ ε 参数不直观 |
| Simplify.js (npm) | ✅ BSD-2 | ⚠️ 需 npm | ❌ 违反 §九 目录契约 |
| Garmin/COROS/Strava 商业 | ⚠️ Mapbox 收费 + Key | ❌ 需注册 + 服务器 | ❌ 违反 §十 Non-Goals |
| OSM 瓦片 | ⚠️ 重负载禁公共 | ❌ 需自托管 | ❌ 需服务器 |

**结论：LTTB 是唯一既满足"零门槛"又满足"§十 Non-Goals"的方案**。

---

## 二、目标

让 `thumbnail_points` 走完 §2.1 完整链路，**采样阶段就保留视觉特征**：

```
原始 GPS 轨迹 (5000+ points)
  ↓
MetricsResolver._lttb_sample(points, threshold=60)  (下沉 L0+L1 修复)
  ↓
activities.thumbnail_points  (含 60 个曲率感知采样点,弯道顶点保留)
  ↓
MetricsResolver._build_real_laps_from_row (未变)
  ↓
record.detail.thumbnail_points
  ↓
track.html buildTrackThumbnailCanvas (B+ v2 已实现真实比例)
  ↓
活动详情页轨迹缩略图 (视觉平滑,弯道特征保留)
```

---

## 三、契约约束（强制遵守）

### 3.1 §V4.0 防腐层契约（最重要）

> **业务逻辑严禁放 main.py，所有计算下沉到 MetricsResolver**

✅ **本任务只改 2 个文件**：
- `metrics_resolver.py`：新增 `_lttb_sample` 静态方法（核心算法）
- `main.py`：`_sample_thumbnail_points` 改为 1 行透传到 `MetricsResolver._lttb_sample`（删除内部实现）

✅ 改造后 `main.py._sample_thumbnail_points` 必须**仅 1 行**：
```python
def _sample_thumbnail_points(self, points, limit=60):
    return MetricsResolver._lttb_sample(points, limit)
```

### 3.2 §2.1 字段全链路可追溯

✅ 每个被 LTTB 选中的点必须能追溯到 `activities.track_json[i]`
✅ 起点 / 终点**强制保留**（Strava/COROS 行业惯例）
✅ LTTB 仅是**点的重排序选择**，**不修改点的经纬度值**

### 3.3 §五 AI 边界契约

✅ LTTB 是**几何降采样**，**不构造任何 AI 输入**、**不刷 AI 会话**、**不进 `ai_snapshots` 表**
✅ 输出 `thumbnail_points` 字段名/类型不变，前端消费契约零变化

### 3.4 §八 Canonical DB 原则

✅ `thumbnail_points` 在前端展示时才实时计算（**不写 DB**）— 沿用既有架构
✅ 本任务**不修改 `activities` 表**任何字段
✅ **不实施存量回填**（老活动 271 个存的是旧 `thumbnail_points` 字段，**该字段在 main.py:5890 行已注明"前端展示用，不入库"**，老数据保持现状即可）

### 3.5 §九 目录契约

✅ **不引入新 lib/npm 包**（LTTB 是公开算法，自实现 ~30 行）
✅ **不修改 `requirements.txt`**（无新 Python 依赖）
✅ `track.html` 零改动（B+ Canvas v2 已正确消费 `thumbnail_points`）

### 3.6 §十 Non-Goals

✅ 纯算法、零网络、零 Mapbox/OSM/任何外部服务依赖
✅ 符合"本地 AI 运动外挂"定位

---

## 四、范围与边界

### 4.1 必须做

1. **改 `metrics_resolver.py`**：
   - 新增 `@staticmethod _lttb_sample(points, threshold=60) -> list[dict]`
   - 实现 LTTB 完整算法（含起/终点强制保留、O(n) 桶排序、最大三角形面积选择）
2. **改 `main.py._sample_thumbnail_points`**：
   - 删除内部实现（约 12 行）
   - 改为 1 行透传 `MetricsResolver._lttb_sample(points, limit)`
3. **新增测试 `tests/test_lttb_sampling.py`**：
   - 覆盖 5 个核心场景（少于/等于/多于阈值、弯道保留、起/终点保留、空输入、单调轨迹）
4. **跑全量测试 + §V4.0 防腐层自检**

### 4.2 不许做

- ❌ 不修改 `main.py` 任何其他业务逻辑（仅改 `_sample_thumbnail_points`）
- ❌ 不改 `track.html`（前端消费契约未变）
- ❌ 不改 `docs/js_api_contract.json`（无新 API）
- ❌ 不写 `ai_snapshots` 表
- ❌ 不引用 `shadow_diff`
- ❌ 不批量回填老活动（`thumbnail_points` 本就不入库）
- ❌ 不引入 LTTB 第三方 Python 库（自实现 ~30 行）
- ❌ 不修改 `requirements.txt`
- ❌ 不加 `api_force_rebuild_thumbnail` 门禁 API

### 4.3 边界与降级

| 情况 | 行为 |
|---|---|
| `points = []` 或 `None` | 返回 `[]`（上游已处理） |
| `len(points) <= threshold` | 返回原 `points` 副本（不采样，保留所有点） |
| `len(points) > threshold` | 执行 LTTB 桶排序采样到 `threshold` 点 |
| 所有点共线 | 退化为均匀采样（不抛异常） |
| 经度跨度 = 0（南北跑） | 仅纬度参与三角形面积计算，OK |
| 起点=终点（圆形轨迹） | 起点终点同点也保留 2 次（行业惯例） |

---

## 五、实施步骤

### Step 1：在 `metrics_resolver.py` 新增 `_lttb_sample` 静态方法

**位置建议**：[metrics_resolver.py](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py) 文件中 `_normalize_laps` 函数**之前**（约 line 1660 之前），作为同类纯计算工具。

**完整实现**（**严格按此实现，不要自行"优化"**）：

```python
@staticmethod
def _lttb_sample(points: list[dict[str, Any]], threshold: int = 60) -> list[dict[str, Any]]:
    """LTTB (Largest-Triangle-Three-Buckets) 曲率感知降采样。

    契约依据:
      §2.1 字段全链路可追溯: 仅选择点的子集, 不修改经纬度
      §V4.0 防腐层: 纯计算无 IO, 从 main.py 整体迁移
      §十 Non-Goals: 纯本地算法, 零网络依赖

    算法来源:
      Sveinn Steinarsson 2013, "Downsampling Time Series for Visual Representation"
      (MS thesis, University of Iceland) — 公开学术算法, 无专利
      同实现广泛用于 ECharts/Highcharts 工业级图表库

    关键不变式:
      1. 起点 (index 0) 与终点 (index n-1) 强制保留
      2. 中间点按"最大三角形面积"准则选择 (曲率感知)
      3. O(n) 时间复杂度
      4. 输出点数 = min(threshold, len(points))

    Args:
        points: GPS 轨迹点列表, 每点必须含 'lat' / 'lon' 字段
        threshold: 目标采样点数, 默认 60 (适配 760x220 canvas 真实比例渲染)

    Returns:
        list[dict]: 降采样后的点列表 (按原顺序)
    """
    n = len(points)
    # 边界: 0 / 1 个点直接返回
    if n < 2:
        return list(points) if n else []
    # 边界: 不需要采样
    if n <= threshold:
        return list(points)

    # 桶大小 (排除首尾 2 个必保留点)
    bucket_size = (n - 2) / (threshold - 2)

    sampled: list[dict[str, Any]] = []
    # 强制保留起点
    sampled.append(points[0])

    # 前一个被保留点的索引 (用于三角形面积计算)
    prev_index = 0

    # 遍历每个"选择桶"
    for i in range(1, threshold - 1):
        # 当前桶的索引范围 [start, end)
        bucket_start = int((i - 1) * bucket_size) + 1
        bucket_end = int(i * bucket_size) + 1
        # 边界修正: 最后一桶包含到 n-1 (排除终点)
        if i == threshold - 2:
            bucket_end = n - 1
        # 下一桶的第一个点 (用于三角形计算的"下一个保留点")
        next_start = int(i * bucket_size) + 1
        if next_start >= n - 1:
            next_start = n - 2  # 防止越界

        # 当前桶内计算最大三角形面积的点
        prev_p = points[prev_index]
        next_p = points[next_start]
        ax = float(prev_p.get("lon", 0) or 0)
        ay = float(prev_p.get("lat", 0) or 0)
        bx = float(next_p.get("lon", 0) or 0)
        by = float(next_p.get("lat", 0) or 0)

        max_area = -1.0
        max_index = bucket_start
        for j in range(bucket_start, bucket_end):
            p = points[j]
            cx = float(p.get("lon", 0) or 0)
            cy = float(p.get("lat", 0) or 0)
            # 三角形面积 = |(B-A) x (C-A)| / 2 (仅需绝对值,省去 /2)
            area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
            if area > max_area:
                max_area = area
                max_index = j

        sampled.append(points[max_index])
        prev_index = max_index

    # 强制保留终点
    sampled.append(points[n - 1])
    return sampled
```

**关键设计点**：
- 起点 `points[0]` 强制保留（line `sampled.append(points[0])`）
- 终点 `points[n-1]` 强制保留（line `sampled.append(points[n - 1])`）
- 中间桶按"最大三角形面积"选择（line `area = abs(...)`）
- 异常边界：少于 2 个点 / 不需要采样 / 最后一桶越界 → 全部正常返回
- 复杂度：O(n) 主循环（每个点只访问一次）+ O(1) 桶内查找

---

### Step 2：改 `main.py._sample_thumbnail_points`

**当前实现**（[main.py:5905-5916](file:///Users/fanglei/应用开发/AI track/main.py#L5905-L5916)）：
```python
def _sample_thumbnail_points(self, points: list[dict], limit: int = 48) -> list[dict]:
    if not points:
        return []
    step = max(1, len(points) // limit)
    sampled = []
    for p in points[::step]:
        lat = p.get("lat")
        lon = p.get("lon")
        ...
        sampled.append({"lat": float(lat), "lon": float(lon)})
    # 末尾补全 (既有逻辑)
    if points and sampled and points[-1] is not sampled[-1]:
        last = points[-1]
        ...
        sampled.append({"lat": float(last["lat"]), "lon": float(last["lon"])})
    return sampled
```

**新实现**（**严格按此实现，必须仅 1 行透传**）：
```python
def _sample_thumbnail_points(self, points: list[dict], limit: int = 60) -> list[dict]:
    """活动轨迹缩略图采样(V9.x-LTTB 升级)。
    
    契约:fit-arch-contrac §V4.0 防腐层 / §2.1 字段全链路可追溯
    业务逻辑已下沉至 MetricsResolver._lttb_sample, 本函数仅做 1 行透传
    采样阈值从 48 提升至 60 以适配 B+ Canvas v2 真实比例渲染
    """
    return MetricsResolver._lttb_sample(points, limit)
```

**关键约束**：
- 整个函数体只有 1 行 `return` 语句
- 默认 `limit` 从 48 → 60（适配 B+ Canvas v2，60 点在 760×220 DPR=2 画布下视觉密度最优）
- 删除原 12 行内部实现
- 末尾**不再需要**补全逻辑（LTTB 强制保留终点）

---

### Step 3：新增测试 `tests/test_lttb_sampling.py`

**完整实现**（**严格按此实现**）：

```python
"""LTTB 降采样算法测试

契约:fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层
覆盖: docs/v9_x_lttb_sampling_prompt.md §4.1.3 测试场景
"""

import math
import unittest
from metrics_resolver import MetricsResolver


class TestLttbSample(unittest.TestCase):
    """MetricsResolver._lttb_sample 单元测试"""

    # ---- T1: 空输入 ----
    def test_t1_empty_input(self):
        r = MetricsResolver._lttb_sample([], 60)
        self.assertEqual(r, [])

    def test_t1_none_input(self):
        """None 入参 (上游会处理, 但 _lttb_sample 应健壮)"""
        # 由于 _lttb_sample 内部未做 None 检查, 此处不测 None
        # 上游 _sample_thumbnail_points 已有 `if not points: return []` 保护
        pass

    # ---- T2: 单点 / 双点 ----
    def test_t2_single_point(self):
        pts = [{"lat": 39.96, "lon": 116.40}]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["lat"], 39.96)

    def test_t2_two_points(self):
        pts = [{"lat": 39.96, "lon": 116.40}, {"lat": 39.97, "lon": 116.41}]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 2)

    # ---- T3: 不需要采样 ----
    def test_t3_under_threshold(self):
        """50 < 60, 不采样, 返回原 50 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(50)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 50, "少于阈值应原样返回")

    def test_t3_equal_threshold(self):
        """60 == 60, 不采样, 返回原 60 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(60)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)

    # ---- T4: 标准 LTTB 降采样 ----
    def test_t4_oversample_returns_threshold(self):
        """5000 点 → 60 点 (LTTB 采样)"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(5000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60, f"应返回 60 个点, 实际 {len(r)}")

    # ---- T5: 起点 / 终点强制保留 ----
    def test_t5_endpoints_preserved(self):
        """起点 points[0] 和终点 points[n-1] 必须保留"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40 + i * 0.0001} for i in range(5000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(r[0]["lat"], pts[0]["lat"], "起点必须保留")
        self.assertEqual(r[0]["lon"], pts[0]["lon"])
        self.assertEqual(r[-1]["lat"], pts[-1]["lat"], "终点必须保留")
        self.assertEqual(r[-1]["lon"], pts[-1]["lon"])

    # ---- T6: 弯道顶点保留 (曲率感知) ----
    def test_t6_curve_vertex_preserved(self):
        """发夹弯顶点必须被保留(曲率感知)"""
        # 构造: 直线 1000 点 + 急弯顶点 + 直线 1000 点
        pts = []
        # 前段直线
        for i in range(1000):
            pts.append({"lat": 39.96, "lon": 116.40 + i * 0.0001})
        # 急弯顶点 (lat 突变)
        pts.append({"lat": 40.50, "lon": 116.50})  # 顶点
        pts.append({"lat": 40.50, "lon": 116.50})  # 顶点
        # 后段直线
        for i in range(1000):
            pts.append({"lat": 40.50, "lon": 116.50 + i * 0.0001})

        r = MetricsResolver._lttb_sample(pts, 60)
        # 急弯顶点应在采样结果中
        vertex_found = any(abs(p["lat"] - 40.50) < 0.01 and abs(p["lon"] - 116.50) < 0.01 for p in r)
        self.assertTrue(vertex_found, f"发夹弯顶点必须被保留,实际采样点 lat/lon: {[(p['lat'], p['lon']) for p in r[:5]]} ... {[(p['lat'], p['lon']) for p in r[-5:]]}")

    # ---- T7: 单调轨迹不退化 ----
    def test_t7_monotonic_no_exception(self):
        """南北向单调直线, 不抛异常, 返回 threshold 点"""
        pts = [{"lat": 39.96 + i * 0.0001, "lon": 116.40} for i in range(2000)]
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)
        # 起点 / 终点保留
        self.assertEqual(r[0]["lat"], pts[0]["lat"])
        self.assertEqual(r[-1]["lat"], pts[-1]["lat"])

    # ---- T8: 圆形轨迹 (起点=终点附近) ----
    def test_t8_circular_track(self):
        """圆形操场轨迹, 起点终点同一区域"""
        pts = []
        import math as m
        for i in range(800):
            angle = i / 800 * 2 * m.pi
            pts.append({"lat": 39.96 + 0.001 * m.sin(angle), "lon": 116.40 + 0.001 * m.cos(angle)})
        r = MetricsResolver._lttb_sample(pts, 60)
        self.assertEqual(len(r), 60)
        # 起点是 (39.96, 116.41), 终点是 (39.96, 116.41)
        self.assertAlmostEqual(r[0]["lat"], 39.96, places=4)
        self.assertAlmostEqual(r[-1]["lat"], 39.96, places=4)

    # ---- T9: 阈值边界 ----
    def test_t9_threshold_2(self):
        """threshold=2, 仅保留首尾"""
        pts = [{"lat": i, "lon": i} for i in range(100)]
        r = MetricsResolver._lttb_sample(pts, 2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["lat"], 0)
        self.assertEqual(r[1]["lat"], 99)

    def test_t9_threshold_3(self):
        """threshold=3, 保留首尾 + 1 个中间点"""
        pts = [{"lat": i, "lon": i} for i in range(100)]
        r = MetricsResolver._lttb_sample(pts, 3)
        self.assertEqual(len(r), 3)

    # ---- T10: 抽样后点数 ≤ 原始点数 ----
    def test_t10_shrink_guarantee(self):
        """任意 N, 采样后点数 <= N"""
        for n in [10, 100, 1000, 5000, 10000]:
            pts = [{"lat": i * 0.0001, "lon": i * 0.0001} for i in range(n)]
            r = MetricsResolver._lttb_sample(pts, 60)
            self.assertLessEqual(len(r), n, f"n={n} 时采样后不能超过原数")
            self.assertLessEqual(len(r), 60, f"n={n} 时采样后不能超过 threshold")


class TestSampleThumbnailPointsTransparent(unittest.TestCase):
    """main.py._sample_thumbnail_points 防腐层自检 (1 行透传)"""

    def test_sample_thumbnail_points_is_one_line(self):
        """§V4.0 防腐层契约: _sample_thumbnail_points 必须是 1 行透传"""
        import ast
        from pathlib import Path
        main_path = Path(__file__).resolve().parent.parent / "main.py"
        src = main_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_sample_thumbnail_points":
                # 计算非 docstring 语句数
                non_doc = [s for s in node.body if not (
                    isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                )]
                # 容忍 docstring + 1 行 return = 2 条语句
                self.assertEqual(
                    len(non_doc), 1,
                    f"main.py._sample_thumbnail_points 防腐层被破坏: "
                    f"实际 {len(non_doc)} 条非 docstring 语句 (期望 1 行 return)"
                )


if __name__ == "__main__":
    unittest.main()
```

---

### Step 4：跑测试

按顺序执行：

```bash
# 4.1 跑 V9.x-LTTB 新增测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_lttb_sampling.py -v

# 4.2 跑 V4-0 防腐层测试 (确保 main.py 透传约束未破)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_v4_0_layer_isolation.py -v

# 4.3 跑 B+ Canvas v2 测试 (确保前端消费契约未破)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_track_thumbnail_canvas.py -v

# 4.4 跑 V9.x 圈速测试 (确保 _normalize_laps 改动未影响)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_real_laps_resolver.py -v

# 4.5 跑全量 (必须 831+ tests 全绿)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/ --ignore=tests/test_laps_real_data.py -x --tb=short
```

---

### Step 5：lint / 类型校验

```bash
# 5.1 Python 编译
cd "/Users/fanglei/应用开发/AI track" && python3 -m py_compile metrics_resolver.py main.py

# 5.2 静态扫描
# (无强制要求, 建议基于 IDE 的 basedpyright hint 看下 metrics_resolver.py)
```

---

## 六、验收标准

### 6.1 功能验收

| # | 场景 | 期望 |
|---|---|---|
| F1 | 导入新长距离活动（半马/全马） | `thumbnail_points` 输出 60 点，弯道特征保留 |
| F2 | 详情页打开 | Canvas 缩略图视觉平滑，急弯不再是硬折角 |
| F3 | 圆形操场活动 | 缩略图显示完整闭合圆/椭圆 |
| F4 | 直线型活动 | 起点/终点正确连接，中间点均匀 |
| F5 | 短活动（< 60 点） | 100% 原样返回，无采样损失 |

### 6.2 契约验收

- [ ] `main.py._sample_thumbnail_points` 业务逻辑 = **1 行 return** (`test_sample_thumbnail_points_is_one_line`)
- [ ] `metrics_resolver.py` 新增 `_lttb_sample` 静态方法
- [ ] `_lttb_sample` 起点 / 终点强制保留
- [ ] `_lttb_sample` 时间复杂度 O(n)
- [ ] `track.html` 零改动
- [ ] `docs/js_api_contract.json` 不更新
- [ ] `requirements.txt` 不更新
- [ ] 全量测试 `pytest tests/ --ignore=tests/test_laps_real_data.py` 831+ 全绿

### 6.3 性能验收

- 10000 点 LTTB 采样 < 5ms (O(n) 复杂度)
- 详情页打开时间无明显变化（采样在服务端，非热路径）
- 内存：仅 1 份副本返回（无累积）

### 6.4 §2.1 全链路可追溯验证

```
FIT SDK gps_lat / gps_long
  ↓
activities.track_json[i].lat / lon
  ↓
MetricsResolver._lttb_sample  (新增, 纯计算)
  ↓
返回 [points[j] for j in selected_indices]  ← 引用原始点, 不修改
  ↓
activities.thumbnail_points  (前端展示字段, 不入库)
  ↓
record.detail.thumbnail_points  (API 透传)
  ↓
track.html buildTrackThumbnailCanvas  (B+ v2 已实现)
  ↓
Canvas 真实比例 + 弯道特征保留
```

**链路中无任何"硬编码 None / 假数据 / AI 输出"切断追溯**。

---

## 七、回滚预案

如发现 LTTB 行为异常（视觉/性能/边界）：

**回滚 Step 2**（1 行透传 → 12 行等距采样）：

```python
def _sample_thumbnail_points(self, points: list[dict], limit: int = 60) -> list[dict]:
    """活动轨迹缩略图采样 (回滚: 朴素等距切片版)"""
    if not points:
        return []
    step = max(1, len(points) // limit)
    sampled = []
    for p in points[::step]:
        lat = p.get("lat")
        lon = p.get("lon")
        if lat is None or lon is None:
            continue
        sampled.append({"lat": float(lat), "lon": float(lon)})
    if points and sampled and points[-1] is not sampled[-1]:
        last = points[-1]
        if last.get("lat") is not None and last.get("lon") is not None:
            sampled.append({"lat": float(last["lat"]), "lon": float(last["lon"])})
    return sampled
```

`_lttb_sample` 函数保留（不破坏）— 未来重新启用。

---

## 八、交付物清单

| # | 文件 | 类型 | 必改行 | 状态 |
|---|---|---|---|---|
| 1 | `metrics_resolver.py` | 新增 `_lttb_sample` | +75 行 | ⏳ |
| 2 | `main.py._sample_thumbnail_points` | 删 12 行 + 加 1 行 | -11 行 | ⏳ |
| 3 | `tests/test_lttb_sampling.py` | 新增 | +200 行 | ⏳ |
| 4 | `track.html` | **不修改** | 0 | ✅ |
| 5 | `docs/js_api_contract.json` | **不更新** | 0 | ✅ |
| 6 | `requirements.txt` | **不更新** | 0 | ✅ |
| 7 | `lib/` | **不修改** | 0 | ✅ |

---

## 九、§V4.0 防腐层契约自检（提交前必跑）

```bash
# 确认 main.py._sample_thumbnail_points 仍为 1 行透传
cd "/Users/fanglei/应用开发/AI track" && python3 -c "
import ast
with open('main.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_sample_thumbnail_points':
        non_doc = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(non_doc) == 1, f'main.py 防腐层被破坏: {len(non_doc)} 行'
        print('✅ §V4.0 防腐层契约保持: _sample_thumbnail_points 仍为 1 行透传')
"
```

如果输出 `AssertionError`，说明改动**破坏了防腐层**，必须回退 main.py 改动。

---

## 十、执行确认

执行完成后需向用户报告：

1. **修改了哪些行**：`metrics_resolver.py` 哪几行 + `main.py` 哪几行 + `tests/test_lttb_sampling.py` 哪几行
2. **测试通过数**：V9.x-LTTB 新增 11 测 + 既有 831+ 测 = 842+ 全绿
3. **§V4.0 防腐层自检结果**：`main.py._sample_thumbnail_points` 仍为 1 行透传
4. **链路可追溯性**：F1~F5 5 个场景的手工验证结果（长距离/圆形/直线/短活动/急弯）
5. **意外发现**：LTTB 在某些异常轨迹上是否需要调整（如全共线、极短轨迹）

> **本提示词为最终交付物，提交后进入"执行 → 测试 → 报告"三步流程。**
