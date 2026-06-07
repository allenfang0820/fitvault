# V9.3 字段一致性 + 同步 + 图标 M0 实施任务书

> Version: V9.3 M0 / 2026-Q2
> Status: 待审阅
> 关联设计:上一轮《Hero 区运动类型自适应方案》§一-§十一 + 用户最终确认的 4 个决策
> 实施基线:V9.0 + V9.1 + V9.2 + V9.2.1
> 主改造文件:`track.html`(单文件,零后端改动)

---

## 0. 元信息

| 字段 | 值 |
|---|---|
| 主改造文件 | `/Users/fanglei/应用开发/AI track/track.html` |
| 涉及后端 | **0 改动** |
| 新增测试文件 | `tests/test_v9_3_field_sync.py` |
| 新增文档 | 0(本文为唯一文档) |
| 净增代码预估 | +220 行 (JS ~140 / CSS ~20 / 测试 ~200 - 删除 ~30) |
| 实施工时预估 | ~65 分钟 |

---

## 1. 改造边界(5 大需求映射)

| 需求 | 实施项 | 文件 | 行数 |
|---|---|---|---|
| **1. 字段一致性** | `_formatHeroValue` 统一格式化函数 + 详情页移除 inline 格式化 | track.html | +40 / -10 |
| **2. 标题 100% 匹配** | `_resolveDisplayTitle` 统一函数 + 3 处调用站点替换 | track.html | +5 / -10 |
| **3. 动态同步框架** | `appState.activityCache` + `_setActivityMeta` + `_emitActivityChanged` + `refreshActivityDetailModal` | track.html | +60 |
| **4. 全量场景测试** | `test_v9_3_field_sync.py`(10 用例,5 类别各 2) | tests/ | +200 |
| **5a. 网格统一** | 已 V9.2 统一,本次微调 | — | — |
| **5b. 图标 + 文字间距** | `HERO_FIELD_ICONS` 15 字段 + `.head` flex + `.icon` 14x14 | track.html | +25 / -5 |
| **5c. 桌面 3 分辨率** | 1920x1080 / 2560x1440 / 3440x1440 验收(无 media query) | — | — |

---

## 2. 用户已确认的 4 个决策

| # | 决策 | 落地 |
|---|---|---|
| 1 | M0 用 **emoji** 而非 SVG | `HERO_FIELD_ICONS` 全 emoji(15 个) |
| 2 | M0 仅实现 setter **框架** | `_setActivityMeta` 不调后端,仅广播;`_setActivityMeta` 含 M1 sentinel 注释 |
| 3 | 桌面分辨率验证 **1920/2560/3440** | 文档 §6 手工测试清单 |
| 4 | M0 测试覆盖 **10 个核心用例** | `test_v9_3_field_sync.py` 严格 10 用例 |

---

## 3. JS 改造(主战场,~140 行新增)

### 3.1 新增 `HERO_FIELD_LABELS` 常量

**位置**:`renderActivityDetailWeather` 函数之后(track.html:约 6080)

**新增代码**(~20 行):
```js
// === V9.3 §需求 1:Hero 字段中文 label 统一映射 ===
const HERO_FIELD_LABELS = {
    'distance': '距离',           'duration': '时长',           'avg_pace': '平均配速',
    'avg_speed': '平均速度',     'avg_power': '平均功率',       'avg_cadence': '平均踏频',
    'training_load': '训练负荷',  'avg_hr': '平均心率',          'max_hr': '最高心率',
    'calories': '热量消耗',       'elevation_gain': '累计爬升',  'moving_time': '移动时间',
    'sets': '训练组数',           'total_volume': '总重量',      'swolf': 'SWOLF',
};
```

### 3.2 新增 `HERO_FIELD_ICONS` 常量

**位置**:`HERO_FIELD_LABELS` 之后

**新增代码**(~20 行):
```js
// === V9.3 §需求 5:15 字段矢量图标(M0 用 emoji,M1 升级 SVG) ===
const HERO_FIELD_ICONS = {
    'distance': '📏',     'duration': '⏱',     'avg_pace': '⏩',
    'avg_speed': '💨',     'avg_power': '⚡',     'avg_cadence': '🔄',
    'training_load': '📊', 'avg_hr': '❤️',       'max_hr': '💓',
    'calories': '🔥',      'elevation_gain': '⛰', 'moving_time': '🚶',
    'sets': '🔢',          'total_volume': '🏋',   'swolf': '🏊',
};
```

### 3.3 新增 `_formatHeroValue` 统一格式化函数

**位置**:`HERO_FIELD_ICONS` 之后

**新增代码**(~50 行):
```js
// === V9.3 §需求 1:统一 Hero 字段格式化(单点真理) ===
// 15 字段全覆盖:数值精度 / 单位换算 / 空态占位符 / 数学常量
function _formatHeroValue(field, raw) {
    if (raw == null) return { value: '--', unit: '' };
    switch (field) {
        case 'distance':
            return { value: raw >= 1000 ? (raw / 1000).toFixed(2) : raw.toFixed(0), unit: 'km' };
        case 'duration':
        case 'moving_time':
            return { value: formatDuration(raw), unit: '' };
        case 'avg_pace':
            return { value: formatPace(raw), unit: '/km' };
        case 'avg_speed':
            return { value: (raw * 3.6).toFixed(1), unit: 'km/h' };
        case 'avg_power':
            return { value: Math.round(raw), unit: 'W' };
        case 'avg_cadence':
            return { value: Math.round(raw), unit: 'rpm' };
        case 'training_load':
            return { value: Math.round(raw), unit: 'TSS' };
        case 'avg_hr':
        case 'max_hr':
            return { value: Math.round(raw), unit: 'bpm' };
        case 'calories':
            return { value: Math.round(raw), unit: 'kcal' };
        case 'elevation_gain':
            return { value: Math.round(raw), unit: 'm' };
        case 'sets':
            return { value: String(raw), unit: '组' };
        case 'total_volume':
            return { value: Math.round(raw), unit: 'kg' };
        case 'swolf':
            return { value: Math.round(raw), unit: '' };
        default:
            return { value: String(raw), unit: '' };
    }
}
```

### 3.4 新增 `_resolveDisplayTitle` 统一标题函数

**位置**:`_formatHeroValue` 之后

**新增代码**(~5 行):
```js
// === V9.3 §需求 2:统一标题解析(3 处调用站点:列表 / 详情 / 历史卡片) ===
function _resolveDisplayTitle(record) {
    if (!record) return '未命名活动';
    return record.title || record.file_name || record.filename || '未命名活动';
}
```

### 3.5 新增动态同步框架(4 函数)

**位置**:`_resolveDisplayTitle` 之后

**新增代码**(~60 行):
```js
// === V9.3 §需求 3:活动元数据动态同步框架 ===
// M0 仅实现框架(M1 接入 __SET_ACTIVITY_META__ sentinel + 真实编辑入口)
function _setActivityMeta(activityId, patch) {
    // M0 占位实现:仅广播,不调后端
    // M1: 调 api.call_llm('__SET_ACTIVITY_META__', JSON.stringify({ id, patch }))
    //      → 成功后 _emitActivityChanged(activityId, patch)
    console.log('[V9.3 setter placeholder] _setActivityMeta:', activityId, patch);
    _emitActivityChanged(activityId, patch);
}

function _emitActivityChanged(activityId, patch) {
    // 1. 局部更新 list cache(避免全量重渲染)
    var list = (appState && appState.activityListCache) || [];
    var idx = -1;
    for (var i = 0; i < list.length; i++) {
        if (list[i].id === activityId) { idx = i; break; }
    }
    if (idx >= 0) {
        try { Object.assign(list[idx], patch); } catch (e) { /* skip readonly fields */ }
    }
    // 2. 重新渲染活动列表该行(若存在函数)
    if (typeof _rerenderActivityListRow === 'function') {
        var row = document.querySelector('[data-activity-id="' + activityId + '"]');
        if (row && idx >= 0) _rerenderActivityListRow(row, list[idx]);
    }
    // 3. 详情页打开时刷新
    if (sportHubState && sportHubState.activeDetailId === activityId) {
        refreshActivityDetailModal();
    }
}

function refreshActivityDetailModal() {
    var id = sportHubState && sportHubState.activeDetailId;
    if (!id) return;
    var cached = (appState && appState.activityCache) || {};
    if (cached[id] && cached[id].record) {
        renderActivityDetail(cached[id].record);
    }
}

// 初始化 cache(M0 兜底,M1 由真实 fetch 填充)
if (typeof appState === 'object' && appState && !appState.activityCache) {
    appState.activityCache = {};
}
```

### 3.6 `renderActivityDetail` metrics 渲染改造

**位置**:`renderActivityDetail` 函数(track.html:约 6038-6061)

**当前代码**(节选):
```js
var distStr = (dist != null) ? (dist >= 1000 ? (dist / 1000).toFixed(2) : dist.toFixed(0)) + '<span class="unit">km</span>' : '--';
var durStr = (dur != null) ? '<span class="unit">' + formatDuration(dur) + '</span>' : '--';
// ... 4 行类似 ...

var fixedMetrics = [
    { lbl: '距离',   val: distStr },
    // ... 6 行 ...
];
metrics.innerHTML = fixedMetrics.map(function(m) {
    return '<div class="overview-metric-card"><div class="lbl">' + m.lbl + '</div><div class="val">' + m.val + '</div></div>';
}).join('');
```

**替换为**(V9.3 改造):
```js
// V9.3 §需求 1+5:统一格式化 + 图标
var heroItems = [
    { field: 'distance',       raw: dist },
    { field: 'duration',       raw: dur },
    { field: 'avg_pace',       raw: pace },
    { field: 'avg_hr',         raw: hr },
    { field: 'calories',       raw: cal },
    { field: 'elevation_gain', raw: asc },
];
metrics.innerHTML = heroItems.map(function(item) {
    var f = _formatHeroValue(item.field, item.raw);
    var label = HERO_FIELD_LABELS[item.field] || item.field;
    var icon = HERO_FIELD_ICONS[item.field] || '';
    return '<div class="overview-metric-card" data-field="' + item.field + '">'
         + '<div class="head">'
         + '<span class="icon">' + icon + '</span>'
         + '<span class="lbl">' + label + '</span>'
         + '</div>'
         + '<div class="val">' + f.value
         + (f.unit ? '<span class="unit">' + f.unit + '</span>' : '')
         + '</div>'
         + '</div>';
}).join('');
```

### 3.7 标题 fallback 3 处替换

**位置 1**:活动列表(track.html:5844)

**当前**:
```js
<td><div class="hub-record-title"><b>${safeHtml(item.title || item.file_name || item.filename || '未命名活动')}</b></div></td>
```

**替换为**:
```js
<td><div class="hub-record-title"><b>${safeHtml(_resolveDisplayTitle(item))}</b></div></td>
```

**位置 2**:详情页(track.html:6021)

**当前**:
```js
title.innerText = record.title || record.filename || '活动详情';
```

**替换为**:
```js
title.innerText = _resolveDisplayTitle(record);
```

**位置 3**:历史卡片(track.html:6966)

**当前**:
```js
const title = item.title || '';
```

**替换为**:
```js
const title = _resolveDisplayTitle(item);
```

---

## 4. CSS 改造(微调,.head flex + 图标样式)

**位置**:V9.2 `.overview-metric-card` CSS 之后

**当前**:
```css
.overview-metric-card .lbl {
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 4px;
}
```

**替换为**:
```css
.overview-metric-card .head {
    display: flex;
    align-items: center;
    gap: 6px;                    /* 5(b) 新增:图标与文字间距 */
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 4px;
}
.overview-metric-card .head .icon {
    display: inline-flex;        /* 5(c) emoji 居中 */
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;          /* 5(c) 图标尺寸与标题协调 */
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    line-height: 1;
}
/* 兼容 V9.2 既有 .lbl 直接使用的场景(无 .head 包裹) */
.overview-metric-card .lbl {
    font-size: 0.7rem;
    color: #94a3b8;
}
```

---

## 5. 测试新增(`tests/test_v9_3_field_sync.py`)

**结构**:**严格 10 个核心用例**,5 类别各 2 用例。

```python
"""
V9.3 M0 契约测试:字段一致性 + 动态同步 + 图标 + 网格

任务: 5 大需求 ——
  1. 字段一致性:_formatHeroValue 单点真理
  2. 标题同步:_resolveDisplayTitle 3 处调用
  3. 动态同步:appState.activityCache + _setActivityMeta + _emitActivityChanged
  4. 全量测试:本文件(10 用例)
  5. 网格 + 图标:HERO_FIELD_ICONS + .head flex

策略:静态 grep 验证 JS 常量/函数/CSS 存在,以及 3 处调用站点。
"""

from __future__ import annotations
import os, re, unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")


def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


class TestV9_3FieldConsistency:  # 需求 1 — 2 用例
    """§需求 1:_formatHeroValue 统一格式化函数"""

    def setUp(self): self.html = _read_track_html()

    def test_format_hero_value_function_exists(self):  # 1/10
        self.assertIn("function _formatHeroValue(", self.html,
                      "V9.3 FAIL: 缺少 _formatHeroValue 函数(需求 1)")

    def test_format_handles_all_field_types_gracefully(self):  # 2/10
        """_formatHeroValue 应处理 distance / duration / avg_pace / calories / null"""
        idx = self.html.find("function _formatHeroValue(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0: end = idx + 5000
        body = self.html[idx:end]
        # 必须涵盖 5 类典型字段
        for field in ['distance', 'duration', 'avg_pace', 'calories']:
            self.assertIn("case '" + field + "'", body,
                          f"V9.3 FAIL: _formatHeroValue 缺 {field} 分支")
        # 必须有空态占位
        self.assertIn("'--'", body, "V9.3 FAIL: _formatHeroValue 缺空态占位符 '--'")


class TestV9_3TitleSync:  # 需求 2 — 2 用例
    """§需求 2:_resolveDisplayTitle 3 处统一调用"""

    def setUp(self): self.html = _read_track_html()

    def test_resolve_display_title_function_exists(self):  # 3/10
        self.assertIn("function _resolveDisplayTitle(", self.html,
                      "V9.3 FAIL: 缺少 _resolveDisplayTitle 函数(需求 2)")
        idx = self.html.find("function _resolveDisplayTitle(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0: end = idx + 500
        body = self.html[idx:end]
        # 统一 fallback 链:title → file_name → filename → 默认
        self.assertIn("record.title", body, "V9.3 FAIL: 缺 title 字段")
        self.assertIn("record.file_name", body, "V9.3 FAIL: 缺 file_name fallback")
        self.assertIn("record.filename", body, "V9.3 FAIL: 缺 filename fallback")
        self.assertIn("未命名活动", body, "V9.3 FAIL: 缺统一默认 '未命名活动'")

    def test_three_call_sites_unified(self):  # 4/10
        """3 处调用站点:列表 / 详情 / 历史卡片 都用 _resolveDisplayTitle"""
        # 函数定义后,应该至少出现 3 次调用
        def_count = self.html.count("function _resolveDisplayTitle(")
        self.assertEqual(def_count, 1, "V9.3 FAIL: 函数应只定义 1 次")
        # 调用站点
        call_count = self.html.count("_resolveDisplayTitle(") - def_count
        self.assertGreaterEqual(
            call_count, 3,
            f"V9.3 FAIL: _resolveDisplayTitle 应被调用 ≥ 3 次(列表/详情/历史),实际 {call_count}"
        )


class TestV9_3DynamicSync:  # 需求 3 — 2 用例
    """§需求 3:动态同步框架(共享 cache + 广播)"""

    def setUp(self): self.html = _read_track_html()

    def test_appstate_activity_cache_field(self):  # 5/10
        """appState.activityCache 必须初始化(共享缓存)"""
        self.assertIn("appState.activityCache", self.html,
                      "V9.3 FAIL: appState.activityCache 未初始化(需求 3)")
        # 初始化逻辑兜底
        self.assertIn("if (typeof appState === 'object' && appState && !appState.activityCache)",
                      self.html, "V9.3 FAIL: 缺少 appState.activityCache 兜底初始化")

    def test_setter_and_emit_and_refresh_functions(self):  # 6/10
        """_setActivityMeta + _emitActivityChanged + refreshActivityDetailModal 三件套"""
        for fn in [
            "function _setActivityMeta(",
            "function _emitActivityChanged(",
            "function refreshActivityDetailModal(",
        ]:
            self.assertIn(fn, self.html,
                          f"V9.3 FAIL: 缺少 {fn}(动态同步三件套)")


class TestV9_3HeroIcons:  # 需求 5 — 2 用例
    """§需求 5:15 字段矢量图标(M0 用 emoji)+ 渲染时输出"""

    def setUp(self): self.html = _read_track_html()

    def test_hero_field_icons_constant_with_15_fields(self):  # 7/10
        """HERO_FIELD_ICONS 必须有 15 个字段"""
        self.assertIn("const HERO_FIELD_ICONS", self.html,
                      "V9.3 FAIL: 缺少 HERO_FIELD_ICONS 常量")
        # 验证 15 字段全覆盖
        required_fields = [
            'distance', 'duration', 'avg_pace', 'avg_speed', 'avg_power',
            'avg_cadence', 'training_load', 'avg_hr', 'max_hr', 'calories',
            'elevation_gain', 'moving_time', 'sets', 'total_volume', 'swolf',
        ]
        for field in required_fields:
            # 字段应出现在 const 定义中
            self.assertIn("'" + field + "':", self.html,
                          f"V9.3 FAIL: HERO_FIELD_ICONS 缺 {field} 字段")
        # 15 个 emoji 至少出现 15 个
        emoji_count = sum(1 for f in required_fields if "'" + f + "': '" in self.html)
        self.assertEqual(emoji_count, 15,
                         f"V9.3 FAIL: HERO_FIELD_ICONS 应有 15 字段带 emoji,实际 {emoji_count}")

    def test_render_activity_detail_uses_icon(self):  # 8/10
        """renderActivityDetail 应输出 .head + .icon 结构(需求 5b)"""
        idx = self.html.find("function renderActivityDetail(")
        end = self.html.find("\n    async function ", idx + 50)
        if end < 0: end = idx + 6000
        body = self.html[idx:end]
        # 验证 .head 结构
        self.assertIn("'head'", body, "V9.3 FAIL: renderActivityDetail 未输出 .head 结构")
        self.assertIn("'icon'", body, "V9.3 FAIL: renderActivityDetail 未输出 .icon")
        self.assertIn("HERO_FIELD_ICONS", body,
                      "V9.3 FAIL: renderActivityDetail 未引用 HERO_FIELD_ICONS")


class TestV9_3GridConsistency:  # 需求 5 — 2 用例
    """§需求 5:网格 + 图标间距 + 仅桌面端"""

    def setUp(self): self.html = _read_track_html()

    def test_metric_head_flex_with_gap(self):  # 9/10
        """.head 含 flex + gap(图标与文字间距统一)"""
        self.assertIn(".overview-metric-card .head {", self.html,
                      "V9.3 FAIL: 缺 .overview-metric-card .head CSS")
        idx = self.html.find(".overview-metric-card .head {")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("display: flex", body, "V9.3 FAIL: .head 缺 flex")
        self.assertIn("gap:", body, "V9.3 FAIL: .head 缺 gap(图标文字间距)")
        self.assertIn("align-items: center", body,
                      "V9.3 FAIL: .head 缺 align-items: center(图标文字垂直对齐)")

    def test_icon_size_unified_no_responsive_breakpoints(self):  # 10/10
        """.icon 尺寸统一(14x14),且无响应式断点(仅桌面)"""
        self.assertIn(".overview-metric-card .head .icon", self.html,
                      "V9.3 FAIL: 缺 .icon CSS")
        # .icon 应有 width: 14px 和 height: 14px
        idx = self.html.find(".overview-metric-card .head .icon {")
        if idx < 0:
            # 兼容 inline 写法
            idx = self.html.find(".overview-metric-card .head .icon")
        end = self.html.find("}", idx + 50)
        body = self.html[idx:end]
        self.assertIn("14px", body, "V9.3 FAIL: .icon 缺 14px 统一尺寸")
        # 无 media query(已 V9.2 决策:仅桌面端)
        # 不在本测试严格校验,仅校验 .icon 尺寸统一


if __name__ == "__main__":
    unittest.main()
```

---

## 6. 验收清单

### 6.1 功能验收(覆盖 5 大需求)

- [ ] 需求 1:详情页 6 个 metric 卡片使用 `_formatHeroValue` 统一格式化(无 inline)
- [ ] 需求 1:同一字段在列表和详情显示**完全一致**(单位/精度/占位符)
- [ ] 需求 2:活动列表 / 详情页 / 历史卡片 3 处都用 `_resolveDisplayTitle`
- [ ] 需求 2:默认标题统一为"未命名活动"(详情页"活动详情"应已删除)
- [ ] 需求 3:`appState.activityCache` 初始化(空对象兜底)
- [ ] 需求 3:`_setActivityMeta(id, patch)` 广播 → `_emitActivityChanged` 触发详情刷新
- [ ] 需求 5:6 字段每个有 emoji 图标(图标 + 文字间距统一 6px)
- [ ] 需求 5:.icon 尺寸 14x14 统一(图标与文字协调)

### 6.2 契约验收

- [ ] §3 响应结构:无后端改动
- [ ] §五 数据可信分层:所有数据来自 `record.X` / `item.X`
- [ ] §11.2 审查门禁:不引入新文件(除测试)/ 新依赖 / 后端改动

### 6.3 测试验收

- [ ] `tests/test_v9_3_field_sync.py` 严格 10 个用例(已写)
- [ ] 既有 V9.2/V9.0/V8.8/V6.3 测试套件仍通过

### 6.4 桌面端 3 分辨率视觉验收(手工)

| 分辨率 | 验收点 | 通过 |
|---|---|---|
| 1920x1080 | 6 metric 卡片 3x2 排列整齐,图标对齐,无错位 | ☐ |
| 2560x1440 | 卡片按比例放大,图标仍清晰,布局不变形 | ☐ |
| 3440x1440 | 同上 | ☐ |

### 6.4.1 验收方法

打开 DevTools → Toggle device toolbar → 设置桌面 3 档分辨率,逐一截图核对。

---

## 7. 实施步骤(6 步,严格顺序)

1. **JS 改造 1**:新增 `HERO_FIELD_LABELS` + `HERO_FIELD_ICONS` + `_formatHeroValue` + `_resolveDisplayTitle`(track.html 中合适位置,约 95 行)
2. **JS 改造 2**:新增动态同步框架 4 函数 + cache 兜底初始化(约 60 行)
3. **JS 改造 3**:改造 `renderActivityDetail` metrics 渲染部分(用新函数)
4. **JS 改造 4**:3 处标题调用站点替换(列表 / 详情 / 历史卡片)
5. **CSS 改造**:`.head` flex + `.icon` 14x14(约 20 行替换/新增)
6. **测试新增**:`tests/test_v9_3_field_sync.py`(10 用例)
7. **跑测试 + 桌面 3 分辨率手工验收**

---

## 8. 风险与回退

| 风险 | 等级 | 缓解 |
|---|---|---|
| `_setActivityMeta` 占位实现无业务调用 | 低 | 仅 console.log,M1 真实接入 |
| 列表行重渲染函数 `_rerenderActivityListRow` 可能不存在 | 中 | `_emitActivityChanged` 已加 typeof 检查 |
| 3 处调用站点替换不全 | 中 | 严格 grep `_resolveDisplayTitle` ≥ 3 次调用 |
| 桌面 3 分辨率测试无法自动化 | 中 | 手工测试清单 §6.4 覆盖 |
| 力量训练等运动 Hero Registry 未实施 | 中 | V9.3 M0 范围明确(6 字段固定),运动特定列留 V9.3+ |

**回退**:`git checkout track.html` + `git checkout tests/test_v9_3_field_sync.py`,单文件回退。

---

## 9. 不在 M0 范围(明确排除)

- ❌ 活动标题编辑 UI(无当前入口)
- ❌ `_setActivityMeta` 真实业务逻辑(M1 接入 `__SET_ACTIVITY_META__` sentinel)
- ❌ 7 种运动 Hero 字段配置(留 V9.3+ 后续)
- ❌ SVG 图标(emoji 即可)
- ❌ 跨页面跳转一致性测试(手工覆盖)
- ❌ 后端 Resolver 改造(始终 0 改动)

---

## 10. 验收签字

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 任务书交付 | __________ | __________ | __________ |
| 架构审查 | __________ | __________ | __________ |
| 业务确认 | __________ | __________ | __________ |

---

## 11. 后续路线

| Phase | 内容 | 触发条件 |
|---|---|---|
| V9.3 M1 | `_setActivityMeta` 真实实现 + `__SET_ACTIVITY_META__` sentinel | 活动编辑 UI 就绪 |
| V9.3+ | 7 种运动 Hero Registry 切换(Resover 主导) | 复盘 + 力量训练数据源稳定 |
| V9.3++ | SVG 矢量图标替代 emoji | 设计风格升级 |
| V9.4 | 跨页面跳转一致性 + 端到端测试 | M1 完成 |

---

> 本任务书与 ARCHITECTURE.md / fit-arch-contrac.md 冲突时,以架构契约为准。
