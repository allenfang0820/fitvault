# 任务：圈速统计补齐步频/GCT 全链路可追溯修复（P1）

> 立项依据：用户报告"圈速统计里步频数据和 GCT 没有消费到"
> 契约参考：fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层 / §五 AI 边界 / §八 Canonical DB
> 工作量：≤ 0.5 个工作日 | 后端业务逻辑改动文件：1 个（metrics_resolver.py）

---

## 一、根因（已确认）

> **核心违约**：`gct_ms` 字段没有走完 §2.1 全链路 `FIT SDK → Resolver → API → 前端`，在 [metrics_resolver.py:849](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py#L849) 被**硬编码为 `None`**，**切断追溯链**。

### 4 层断点

| # | 层级 | 位置 | 现状 |
|---|---|---|---|
| L1 | FIT SDK → fitparse | fitparse SDK | ✅ SDK 实际含 `stance_time` / `vertical_oscillation` / `stride_length` 字段 |
| **L2** | **fitparse → Resolver._normalize_laps** | [metrics_resolver.py:1666-1686](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py#L1666-L1686) | **❌ 完全忽略 stance_time / vertical_oscillation / stride_length** |
| **L3** | **Resolver → 详情 API** | [metrics_resolver.py:807-852 `_build_real_laps_from_row`](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py#L807-L852) line 849 | **❌ 硬编码 `"gct_ms": None`** |
| L4 | API → 前端 | [track.html:6119](file:///Users/fanglei/应用开发/AI track/track.html#L6119) | ✅ 正确消费 `lap.gct_ms` / `lap.cadence` / `lap.power_w` |

**cadence 字段也未真正消费到**：`activities.avg_cadence` 列在 271 个活动中 **100% NULL**；`laps_json` 内的 `avg_cadence` 也都是 `null`。这与 fitparse 默认不读字段 + 旧设备不记录 cadence 有关，但**契约层面是 L2 没读**。

---

## 二、目标

让 `gct_ms` / `cadence` / `power_w` 走完 §2.1 完整链路：

```
FIT lap_mesgs (stance_time / vertical_oscillation / stride_length)
  ↓
MetricsResolver._normalize_laps  (下沉 L2 修复)
  ↓
activities.laps_json  (含 stance_time_ms / vertical_oscillation_cm / stride_length_m)
  ↓
MetricsResolver._build_real_laps_from_row  (下沉 L3 修复:从硬编码 None 改为读真值)
  ↓
record.detail.laps[].gct_ms / cadence / power_w
  ↓
track.html 圈速统计表格 (已有,零改动)
```

---

## 三、契约约束（强制遵守）

### 3.1 §V4.0 防腐层契约（最重要）

> **业务逻辑严禁放 main.py，所有计算下沉到 MetricsResolver**

✅ **本任务只改 `metrics_resolver.py`，零 `main.py` 业务逻辑改动**
✅ `main.py` 中现有的 `_build_real_laps_from_row`（line 5941-5945）已是 1 行透传，**保持不变**
✅ **不引入新文件、不创建新的 main.py 函数**（除非要新增 `api_force_rebuild_*` 门禁 API，本次不做）

### 3.2 §2.1 字段全链路可追溯

✅ 新增的每个字段必须能追溯到 `FIT SDK field`
✅ 删除既有 `test_gct_ms_always_none` 反向断言（违反 §2.1），替换为正向测试

### 3.3 §五 AI 边界契约

✅ 圈速是**用户可信原始数据（source_type=fit_sdk）**，**不是 AI 输出**
✅ 本修复**不构造任何 `_ai_snapshot` 输入**、**不刷 AI 会话**、**不进 `ai_snapshots` 表**

### 3.4 §八 Canonical DB 原则

✅ `laps_json` 仅在 FIT 重导入时**自然增量写入**新字段
✅ **本任务不实施存量回填**（重读 271 个 FIT 文件的 I/O 成本高，老活动 GCT 降级显示 `--` 是可接受的空态）

### 3.5 §九 目录契约

✅ 不修改 `lib/`
✅ 不修改 `requirements.txt`
✅ 不新增 Python 文件
✅ `track.html` 零改动

---

## 四、范围与边界

### 4.1 必须做

1. **改 `metrics_resolver.py._normalize_laps`**：增读 3 个 FIT 字段 → 输出到 normalized dict
2. **改 `metrics_resolver.py._build_real_laps_from_row`**：`gct_ms` 从硬编码 None 改为读 `stance_time_ms`
3. **改 `tests/test_real_laps_resolver.py`**：删 1 个反向测 + 加 8 个正向测
4. **跑全量测试**：`pytest tests/test_real_laps_resolver.py -v` + `pytest tests/ -x`

### 4.2 不许做

- ❌ 不改 `main.py`（业务逻辑已下沉）
- ❌ 不改 `track.html`（前端消费契约未变）
- ❌ 不改 `docs/js_api_contract.json`（无新 API）
- ❌ 不写 `ai_snapshots` 表
- ❌ 不引用 `shadow_diff`
- ❌ 不批量回填 271 个老活动（重读 FIT I/O 成本过高）
- ❌ 不加 `api_force_rebuild_laps_data` 门禁 API（本次不做）
- ❌ 不在 `_build_real_laps_from_row` 输出 vertical_oscillation / stride_length 字段（避免给前端加未消费字段，违反 §九 简单原则）

### 4.3 边界与降级

| 情况 | 行为 |
|---|---|
| FIT 文件无 stance_time 字段 | `_normalize_laps` 输出 `stance_time_ms = None` → `_build_real_laps_from_row` 输出 `gct_ms = None` → 前端显示 `--`（**正确降级**） |
| `stance_time = 0` | 经 `_safe_int_zero` → 0 → `if x else None` → 输出 `None`（防 0 污染） |
| 老活动 `laps_json` 缺新字段 | `lap.get("stance_time_ms") = None` → 输出 `None` → 显示 `--`（**不破坏老数据**） |
| 新 FIT 入库 | 走新 `_normalize_laps` → 含 stance_time_ms → 详情页 GCT 列显示真实值 |

---

## 五、实施步骤

### Step 1：改 `_normalize_laps`

**文件**：[metrics_resolver.py:1666-1686](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py#L1666-L1686)

**当前代码**：
```python
def _normalize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for i, lap in enumerate(laps):
        if not isinstance(lap, dict):
            continue
        dist = MetricsResolver._num(lap.get("total_distance"))
        elapsed = MetricsResolver._num(lap.get("total_timer_time"))
        avg_hr = MetricsResolver._num(lap.get("avg_heart_rate"))
        avg_power = MetricsResolver._num(lap.get("avg_power"))
        avg_cadence = MetricsResolver._num(lap.get("avg_cadence"))
        if dist == 0 and elapsed == 0:
            continue
        result.append({
            "lap_index": lap.get("lap_index", i),
            "distance_m": dist,
            "elapsed_sec": elapsed,
            "avg_hr": avg_hr if avg_hr else None,
            "avg_power": avg_power if avg_power else None,
            "avg_cadence": avg_cadence if avg_cadence else None,
        })
    return result
```

**新代码**（**严格按此实现**）：

```python
def _normalize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """归一化 FIT lap_mesgs 为前端展示格式(§2.1 全链路可追溯)。

    §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
    §2.1 全链路可追溯:UI 字段必须能追溯至 FIT SDK
      - stance_time (FIT, ms) → stance_time_ms
      - vertical_oscillation (FIT, cm) → vertical_oscillation_cm
      - stride_length (FIT, m) → stride_length_m

    Returns:
        list[dict]: 9 字段归一化圈速字典(为未来 VO/stride 进入前端预留,当前仅 gct_ms/avg_cadence/avg_power 进入 UI)
    """
    result: list[dict[str, Any]] = []
    for i, lap in enumerate(laps):
        if not isinstance(lap, dict):
            continue
        dist = MetricsResolver._num(lap.get("total_distance"))
        elapsed = MetricsResolver._num(lap.get("total_timer_time"))
        avg_hr = MetricsResolver._num(lap.get("avg_heart_rate"))
        avg_power = MetricsResolver._num(lap.get("avg_power"))
        avg_cadence = MetricsResolver._num(lap.get("avg_cadence"))
        # V9.x 修复:增读 FIT 步态字段,§2.1 全链路可追溯,严禁硬编码 None
        stance_time_ms = MetricsResolver._safe_int_zero(lap.get("stance_time")) or None
        vertical_oscillation_cm = MetricsResolver._safe_float_zero(lap.get("vertical_oscillation")) or None
        stride_length_m = MetricsResolver._safe_float_zero(lap.get("stride_length")) or None
        if dist == 0 and elapsed == 0:
            continue
        result.append({
            "lap_index": lap.get("lap_index", i),
            "distance_m": dist,
            "elapsed_sec": elapsed,
            "avg_hr": avg_hr if avg_hr else None,
            "avg_power": avg_power if avg_power else None,
            "avg_cadence": avg_cadence if avg_cadence else None,
            "stance_time_ms": stance_time_ms,
            "vertical_oscillation_cm": vertical_oscillation_cm,
            "stride_length_m": stride_length_m,
        })
    return result
```

---

### Step 2：改 `_build_real_laps_from_row`

**文件**：[metrics_resolver.py:807-852](file:///Users/fanglei/应用开发/AI track/metrics_resolver.py#L807-L852)

**当前代码 (line 838-851)**：
```python
lap_avg_hr = MetricsResolver._safe_int_zero(lap.get("avg_hr"))
lap_avg_cadence = MetricsResolver._safe_int_zero(lap.get("avg_cadence"))
lap_avg_power = MetricsResolver._safe_int_zero(lap.get("avg_power"))
if dist_m <= 0 and elapsed <= 0:
    continue
pace_sec = int(round(elapsed / (dist_m / 1000.0))) if dist_m > 0 and elapsed > 0 else 0
rows.append({
    "lap_no": idx + 1,
    "distance_km": round(dist_m / 1000.0, 2) if dist_m > 0 else None,
    "pace_sec": pace_sec if pace_sec > 0 else None,
    "hr": lap_avg_hr if lap_avg_hr else None,
    "cadence": lap_avg_cadence if lap_avg_cadence else None,
    "gct_ms": None,
    "power_w": lap_avg_power if lap_avg_power else None,
})
```

**新代码**（**严格按此实现,严禁改输出 dict 的 7 字段契约**）：

```python
lap_avg_hr = MetricsResolver._safe_int_zero(lap.get("avg_hr"))
lap_avg_cadence = MetricsResolver._safe_int_zero(lap.get("avg_cadence"))
lap_avg_power = MetricsResolver._safe_int_zero(lap.get("avg_power"))
# V9.x 修复:从 normalized lap dict 读 stance_time_ms(§2.1 全链路可追溯)
# 原实现硬编码 None 切断追溯链,本次改为读真值
lap_gct_ms = MetricsResolver._safe_int_zero(lap.get("stance_time_ms")) or None
if dist_m <= 0 and elapsed <= 0:
    continue
pace_sec = int(round(elapsed / (dist_m / 1000.0))) if dist_m > 0 and elapsed > 0 else 0
rows.append({
    "lap_no": idx + 1,
    "distance_km": round(dist_m / 1000.0, 2) if dist_m > 0 else None,
    "pace_sec": pace_sec if pace_sec > 0 else None,
    "hr": lap_avg_hr if lap_avg_hr else None,
    "cadence": lap_avg_cadence if lap_avg_cadence else None,
    "gct_ms": lap_gct_ms,   # V9.x:从硬编码 None 改为透传 Resolver 解析值
    "power_w": lap_avg_power if lap_avg_power else None,
})
```

**关键约束**：
- 输出 dict 仍为 7 字段契约（前端表格契约不变）
- `gct_ms` 从 `None` 改为 `lap_gct_ms` 变量
- `vertical_oscillation_cm` / `stride_length_m` **不进输出**（避免给前端加未消费字段，§九 简单原则）

---

### Step 3：改测试 `tests/test_real_laps_resolver.py`

#### 3.1 删除 1 个反向测试

**删除**：[test_real_laps_resolver.py:116-119](file:///Users/fanglei/应用开发/AI track/tests/test_real_laps_resolver.py#L116-L119)

```python
def test_gct_ms_always_none(self):
    """gct_ms 当前未实现,始终为 None"""
    self.assertIsNone(self.result[0]["gct_ms"])
    self.assertIsNone(self.result[1]["gct_ms"])
```

**删除原因**：违反 §2.1 全链路可追溯。`gct_ms` 不再是"未实现"。

#### 3.2 追加 8 个新测试

**追加位置**：[test_real_laps_resolver.py](file:///Users/fanglei/应用开发/AI track/tests/test_real_laps_resolver.py) 文件末尾，**`if __name__ == "__main__":` 之前**。

```python
# ══════════════════════════════════════════════════════════════════
# V9.x: GCT/Vertical Oscillation/Stride Length 全链路追溯测试
# 契约:fit-arch-contrac §2.1 字段全链路可追溯 / §V4.0 防腐层
# ══════════════════════════════════════════════════════════════════

class TestNormalizeLapsRunningDynamics(unittest.TestCase):
    """_normalize_laps 透读 FIT 步态字段(stance_time/vertical_oscillation/stride_length)"""

    def test_stance_time_parsed(self):
        """FIT stance_time (ms) → stance_time_ms"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "stance_time": 245}
        ])
        self.assertEqual(r[0]["stance_time_ms"], 245)

    def test_vertical_oscillation_parsed(self):
        """FIT vertical_oscillation (cm) → vertical_oscillation_cm"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "vertical_oscillation": 8.7}
        ])
        self.assertEqual(r[0]["vertical_oscillation_cm"], 8.7)

    def test_stride_length_parsed(self):
        """FIT stride_length (m) → stride_length_m"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0, "stride_length": 1.23}
        ])
        self.assertEqual(r[0]["stride_length_m"], 1.23)

    def test_missing_fields_default_none(self):
        """字段缺失 → None(与 avg_hr 风格一致)"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0}
        ])
        self.assertIsNone(r[0]["stance_time_ms"])
        self.assertIsNone(r[0]["vertical_oscillation_cm"])
        self.assertIsNone(r[0]["stride_length_m"])

    def test_zero_values_become_none(self):
        """stance_time=0 → None(防 0 污染)"""
        r = MetricsResolver._normalize_laps([
            {"total_distance": 1000.0, "total_timer_time": 300.0,
             "stance_time": 0, "vertical_oscillation": 0, "stride_length": 0}
        ])
        self.assertIsNone(r[0]["stance_time_ms"])
        self.assertIsNone(r[0]["vertical_oscillation_cm"])
        self.assertIsNone(r[0]["stride_length_m"])


class TestBuildRealLapsGctForwarding(unittest.TestCase):
    """_build_real_laps_from_row 透传 stance_time_ms → gct_ms(§2.1 全链路可追溯)"""

    def test_gct_ms_forwarded_from_laps_json(self):
        """laps_json 中 stance_time_ms=245 → gct_ms=245"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0,
                "stance_time_ms": 245
            }])
        })
        self.assertEqual(r[0]["gct_ms"], 245, "stance_time_ms 必须透传到 gct_ms")

    def test_gct_ms_none_when_stance_missing(self):
        """laps_json 无 stance_time_ms → gct_ms=None(老数据降级)"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0
            }])
        })
        self.assertIsNone(r[0]["gct_ms"], "字段缺失 → gct_ms=None")

    def test_gct_ms_none_when_stance_zero(self):
        """stance_time_ms=0 → gct_ms=None(防 0 污染)"""
        r = MetricsResolver._build_real_laps_from_row({
            "laps_json": json.dumps([{
                "distance_m": 1000.0, "elapsed_sec": 300.0,
                "stance_time_ms": 0
            }])
        })
        self.assertIsNone(r[0]["gct_ms"], "stance_time_ms=0 → gct_ms=None")
```

---

### Step 4：跑测试

按顺序执行：

```bash
# 4.1 跑 V9.x 新增测试
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_real_laps_resolver.py -v

# 4.2 跑 V4-0 防腐层测试(确保 main.py 透传约束未破)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_v4_0_layer_isolation.py -v

# 4.3 跑 V8.3 cadence 测试(确保 record 级 cadence 链路未破)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/test_v8_3_cadence.py -v

# 4.4 跑全量(必须 698+ tests 全绿)
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/ -x --tb=short
```

**注意**：`tests/` 全量跑时**忽略** `tests/test_laps_real_data.py`（已知问题，与本任务无关）。

```bash
cd "/Users/fanglei/应用开发/AI track" && python3 -m pytest tests/ --ignore=tests/test_laps_real_data.py -x --tb=short
```

---

### Step 5：lint / 类型校验

```bash
# 5.1 Python 编译
cd "/Users/fanglei/应用开发/AI track" && python3 -m py_compile metrics_resolver.py

# 5.2 静态扫描
# (无强制要求,但建议基于 IDE 的 basedpyright hint 看下 metrics_resolver.py)
```

---

## 六、验收标准

### 6.1 功能验收

| # | 场景 | 期望 |
|---|---|---|
| F1 | 导入新 FIT（含 GCT 数据） | `_normalize_laps` 输出 `stance_time_ms` 字段非空 |
| F2 | 详情页打开该活动 | 圈速统计表 GCT 列显示 `XXX ms`（非 `--`） |
| F3 | 打开老活动（无 GCT） | 圈速统计表 GCT 列显示 `--`（降级） |
| F4 | 打开非跑步活动（室内） | 圈速统计表 GCT 列显示 `--`（无步态数据） |

### 6.2 契约验收

- [ ] `main.py` 业务逻辑 **零改动**（仅检查 line 5941-5945 仍是 1 行透传）
- [ ] `_build_real_laps_from_row` 输出 7 字段契约不变
- [ ] `_normalize_laps` 输出 9 字段契约（新增 3 字段，§2.1 可追溯）
- [ ] 既有 `test_each_lap_has_7_fields` / `test_no_extra_fields` 测试**仍通过**
- [ ] 删除的 `test_gct_ms_always_none` 是 1 个，**不多删**
- [ ] 新增测试 8 个，**全绿**
- [ ] 全量测试 `pytest tests/ --ignore=tests/test_laps_real_data.py` 698+ 全绿

### 6.3 性能验收

- `_normalize_laps` 单圈解析增加 < 0.05ms（仅 3 次 dict.get + 类型转换）
- 详情页打开时间无明显变化（laps 解析在服务端，不是热路径）

### 6.4 §2.1 全链路可追溯验证

```
FIT SDK 字段 stance_time
  ↓ fitparse 解析
lap_mesg.stance_time
  ↓ MetricsResolver._normalize_laps (line 新增:lap.get("stance_time"))
activities.laps_json[i].stance_time_ms
  ↓ MetricsResolver._build_real_laps_from_row (line 849 改为:lap.get("stance_time_ms"))
record.detail.laps[i].gct_ms
  ↓ GET /api/get_activity_detail
前端 track.html:6119 ${(lap.gct_ms || '--') + ' ms'}
```

链路中**无任何硬编码 None / fallback 切断追溯**。

---

## 七、回滚预案

如发现新代码有异常：

**回滚 Step 2**（仅 1 行）：

```python
# 回滚为硬编码 None
"gct_ms": None,
```

`_normalize_laps` 的新增字段保留（**不破坏**，DB 多 3 个字段无害）。

---

## 八、交付物清单

| # | 文件 | 类型 | 必改行 | 状态 |
|---|---|---|---|---|
| 1 | `metrics_resolver.py` | 修改 `_normalize_laps` | line 1666-1686（+9 行） | ⏳ |
| 2 | `metrics_resolver.py` | 修改 `_build_real_laps_from_row` | line 838-851（+1 行 / 改 1 行） | ⏳ |
| 3 | `tests/test_real_laps_resolver.py` | 删 1 测 + 加 8 测 | +110 行 | ⏳ |
| 4 | `main.py` | **不修改** | 0 | ✅ |
| 5 | `track.html` | **不修改** | 0 | ✅ |
| 6 | `docs/js_api_contract.json` | **不更新** | 0 | ✅ |
| 7 | `requirements.txt` | **不更新** | 0 | ✅ |

---

## 九、§V4.0 防腐层契约自检（提交前必跑）

```bash
# 确认 main.py 中 _build_real_laps_from_row 仍为 1 行透传
cd "/Users/fanglei/应用开发/AI track" && python3 -c "
import ast
with open('main.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == '_build_real_laps_from_row':
        non_doc = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(non_doc) == 1, f'main.py 防腐层被破坏: {len(non_doc)} 行'
        print('✅ §V4.0 防腐层契约保持')
"
```

如果输出 `AssertionError`，说明改动**破坏了防腐层**，必须回退 main.py 改动。

---

## 十、执行确认

执行完成后需向用户报告：

1. **修改了哪些行**：`metrics_resolver.py` 哪几行 + `tests/test_real_laps_resolver.py` 哪几行
2. **测试通过数**：V9.x 新增 8 测 + 既有 7 测 = 15 测全绿；全量 698+ 全绿
3. **§V4.0 防腐层自检结果**：`main.py._build_real_laps_from_row` 仍为 1 行透传
4. **链路可追溯性**：F1~F4 4 个场景的手工验证结果（或自动验证结果）
5. **意外发现**：是否有 FIT 文件 stance_time 字段值异常 / 是否需要后续回填

> **本提示词为最终交付物，提交后进入"执行 → 测试 → 报告"三步流程。**
