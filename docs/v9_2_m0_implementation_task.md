# 概览 Tab M0 实施任务书

> Version: V9.2 M0 / 2026-Q2
> Status: 待审阅
> 关联设计契约:[docs/v9_2_overview_design.md](file:///Users/fanglei/应用开发/AI track/docs/v9_2_overview_design.md)
> 实施基线:V9.0 + V9.1(详情 Tab 化 + 3D 浮起阴影)
> 主改造文件:`track.html`(单文件,零后端改动)

---

## 0. 元信息

| 字段 | 值 |
|---|---|
| 主改造文件 | `/Users/fanglei/应用开发/AI track/track.html` |
| 涉及后端 | **0 改动** |
| 涉及后端 API | 仅消费 `get_activity_detail` 既有返回,**不调新接口** |
| 新增测试文件 | `tests/test_v9_2_overview_m0.py` |
| 新增文档 | **0** (本文即为唯一文档) |
| 删除 | 头部 `× 关闭` 按钮 + 既有 `.activity-detail-grid` 2 卡片结构 |
| 净增代码预估 | +150 行 (HTML ~50, CSS ~60, JS ~40) |
| 实施工时预估 | ~30 分钟 |

---

## 1. 改造边界(M0 严格范围)

| 元素 ID | 元素 | M0 实施 | 来源 |
|---|---|---|---|
| E01 | `← 活动列表` 按钮 | 保留(V9.0 已有) | — |
| **E01.x** | **`× 关闭` 按钮** | **删除**(决策 1) | 头部 |
| E02 | 活动标题 | 保留(既有) | — |
| E03 | 副标题 | **改造**:内嵌天气(决策 4)+ 设备名 | renderActivityDetail |
| E04 | Tab Bar(概览/复盘) | 保留(V9.0 + V9.1) | — |
| E05-E10 | 6 个 metric 卡片 | **改造**:从 2x4 改为 3x2 grid(新增容器) | renderActivityDetail |
| E11 | 轨迹地图(主视觉) | **改造**:从缩略图升级为 2/3 宽主视觉 | renderActivityDetail |
| E12a | 🌤 环境卡 | **新增**:侧栏第 1 张,只显示温度 + 湿度(决策 2) | 新增 |
| E12b | 🔥 训练收益卡 | **不渲染**(决策 3) | — |
| E12c | 🫀 身体状态卡 | **不渲染**(决策 3) | — |
| E12d | ✨ 活动摘要卡 | **不渲染**(决策 3,等复盘完善) | — |
| E13 | 圈速统计表 | 保留(既有) | — |

**结论**:M0 实际改动 = E01.x(删)+ E03(改)+ E05-E10(改)+ E11(改)+ E12a(增) = **5 处**

---

## 2. HTML 改造(5 处)

### 2.1 头部删除 `× 关闭` 按钮(决策 1)

**位置**:`.activity-detail-head-actions` 内部

**搜索**:
```html
            <div class="activity-detail-head-actions">
                <button class="activity-detail-back" onclick="closeActivityDetailModal()" title="关闭并返回活动列表">← 返回活动列表</button>
                <button class="activity-detail-close" onclick="closeActivityDetailModal()" title="关闭">×</button>
            </div>
```

**替换为**:
```html
            <div class="activity-detail-head-actions">
                <!-- V9.2:删除 × 关闭按钮(决策 1),改用 ESC + backdrop 关闭 -->
                <button class="activity-detail-back" onclick="closeActivityDetailModal()" title="关闭并返回活动列表">← 返回活动列表</button>
            </div>
```

---

### 2.2 概览 Tab 容器彻底重写

**位置**:`#detail-tab-overview` 内部(从 `.detail-cockpit-left` 到子元素全部替换)

**搜索**(整块):
```html
            <div class="detail-tab-panel active" id="detail-tab-overview">
                <div class="detail-cockpit-left" id="detail-cockpit-snapshot">
                    <div class="activity-detail-grid">
                        <div class="detail-section-card">
                            <div class="section-title">📌 活动总结</div>
                            <div class="detail-metric-grid" id="activity-detail-metrics"></div>
                            <div id="activity-detail-track-section">
                                <div id="activity-detail-track-container"></div>
                            </div>
                        </div>
                        <div class="detail-section-card">
                            <div class="section-title">📈 圈速统计</div>
                            <div class="lap-table-wrap">
                                <table class="lap-table">
                                    <thead>
                                        <tr>
                                            <th>圈速</th>
                                            <th>配速</th>
                                            <th>心率</th>
                                            <th>步频</th>
                                            <th>GCT</th>
                                            <th>功率</th>
                                        </tr>
                                    </thead>
                                    <tbody id="activity-detail-laps"></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
```

**替换为**(V9.2 新结构):
```html
            <div class="detail-tab-panel active" id="detail-tab-overview">
                <div class="overview-metrics-grid" id="activity-detail-metrics">
                    <!-- 6 个 metric 卡片由 renderActivityDetail 渲染(E05-E10) -->
                </div>
                <div class="overview-main-grid">
                    <div class="overview-main-visual" id="activity-detail-track-section">
                        <!-- E11 轨迹地图(主视觉)由 renderActivityDetail 渲染 -->
                        <div id="activity-detail-track-container"></div>
                    </div>
                    <div class="overview-sidebar" id="activity-detail-sidebar">
                        <!-- E12a 环境卡由 renderActivityDetailWeather 渲染 -->
                    </div>
                </div>
                <div class="overview-laps">
                    <div class="overview-laps-title">📈 圈速统计</div>
                    <div class="lap-table-wrap">
                        <table class="lap-table">
                            <thead>
                                <tr>
                                    <th>圈速</th>
                                    <th>配速</th>
                                    <th>心率</th>
                                    <th>步频</th>
                                    <th>GCT</th>
                                    <th>功率</th>
                                </tr>
                            </thead>
                            <tbody id="activity-detail-laps"></tbody>
                        </table>
                    </div>
                </div>
            </div>
```

**变更说明**:
- 旧的 `.activity-detail-grid` 2 卡片结构 → 新的 3 段式结构(metrics + main+sidebar + laps)
- `#activity-detail-metrics` 元素保留(id 不变),但容器从 `.detail-metric-grid` 改为 `.overview-metrics-grid`
- `#activity-detail-laps` 元素保留(id 不变)
- `#activity-detail-track-section` 和 `#activity-detail-track-container` 保留,移到主视觉容器
- 新增 `#activity-detail-sidebar` 容器(由 JS 填充环境卡)

---

## 3. CSS 改造(新增 ~80 行)

**位置**:`</style>` 标签前(即 V9.1 浮起阴影 Tab Bar CSS 后)

**新增**:

```css
/* === V9.2 概览 Tab 布局 — fit-arch-contrac §五 UI 风格 === */
.overview-metrics-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 14px;
}
.overview-main-grid {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 14px;
    margin-bottom: 14px;
}
.overview-main-visual {
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px;
    min-height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: border-color 0.2s;
}
.overview-main-visual:hover {
    border-color: rgba(108, 92, 231, 0.35);
}
.overview-sidebar {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.overview-laps {
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    padding: 14px 16px;
}
.overview-laps-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: #c4b5fd;
    margin-bottom: 10px;
}

/* metric 卡片(E05-E10)— 替代既有 .detail-metric */
.overview-metric-card {
    padding: 12px 14px;
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    transition: transform 0.2s;
}
.overview-metric-card:hover {
    transform: translateY(-1px);
}
.overview-metric-card .lbl {
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 4px;
}
.overview-metric-card .val {
    font-size: 1.4rem;
    color: #f8fafc;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
}
.overview-metric-card .unit {
    font-size: 0.75rem;
    color: #94a3b8;
    margin-left: 3px;
    font-weight: 500;
}

/* 侧栏卡片(E12a)— 复用 .sidebar-card 命名空间 */
.sidebar-card {
    padding: 12px 14px;
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(108, 92, 231, 0.15);
    border-radius: 10px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.05) inset,
        0 2px 6px rgba(0, 0, 0, 0.25);
}
.sidebar-card .head {
    font-size: 0.78rem;
    font-weight: 700;
    color: #c4b5fd;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.sidebar-card .item-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.72rem;
    padding: 4px 0;
    color: #cbd5e1;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.sidebar-card .item-row:last-child { border-bottom: none; }
.sidebar-card .item-row .key { color: #94a3b8; }
.sidebar-card .item-row .val { color: #f8fafc; font-weight: 600; }
.sidebar-card .empty-msg {
    font-size: 0.7rem;
    color: #94a3b8;
    line-height: 1.5;
    margin-top: 4px;
}

/* 主视觉轨迹地图(E11) */
.overview-main-visual .detail-track-thumb {
    width: 100%;
    height: 100%;
    min-height: 280px;
}
.overview-main-visual .detail-track-thumb svg {
    width: 100%;
    height: 100%;
    min-height: 280px;
    display: block;
}
.overview-main-visual .detail-track-tip {
    margin-top: 8px;
    font-size: 0.7rem;
    color: #94a3b8;
    text-align: center;
}

/* 副标题过长时用省略号(仅桌面端,无响应式) */
.activity-detail-subtitle {
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
```

---

## 4. JS 改造(4 处)

### 4.1 `renderActivityDetail` 函数主体改造

**位置**:`renderActivityDetail(record)` 函数(约 track.html:5868)

**当前代码**(节选):
```js
function renderActivityDetail(record) {
    const metrics = document.getElementById('activity-detail-metrics');
    const lapsBody = document.getElementById('activity-detail-laps');
    const trackContainer = document.getElementById('activity-detail-track-container');
    const title = document.getElementById('activity-detail-title');
    const subtitle = document.getElementById('activity-detail-subtitle');
    if (!record || !metrics || !lapsBody || !trackContainer) return;

    var detail = record.detail || {};
    var caps = detail.capabilities || {};
    var layoutCards = (detail.layout && detail.layout.cards) || [];
    var cardTypes = layoutCards.map(function(c) { return c.type; });

    title.innerText = record.title || record.filename || '活动详情';
    subtitle.innerText = (record.date_label || '--') + ' · ' + sportHubRecordTypeLabel(record) + ' · ' + (record.region || '地区待解析') + ' · 点击轨迹缩略图可跳转到轨迹分析工具';
    // ... (后续 metrics 渲染逻辑保留)
}
```

**改造内容**:**仅修改副标题渲染部分**和**末尾追加 sidebar 渲染调用**

**Step 1 — 替换副标题渲染**(单行):
```js
    // V9.2 §E03 副标题:时间 · 地区 · [天气(若可得)] · 设备名
    var subParts = [];
    subParts.push(record.date_label || '--');
    subParts.push(record.region || '地区待解析');
    // 天气内嵌(决策 4):仅当 weather 含 temperature_c 时内嵌
    if (appState.currentWeather && appState.currentWeather.temperature_c != null) {
        var w = appState.currentWeather;
        var wxSnippet = (w.weather_label || '') + (w.weather_label ? ' · ' : '') + w.temperature_c + '°C';
        subParts.push(wxSnippet);
    }
    var devName = (record.device_name || '').trim();
    if (devName) subParts.push(devName);
    subtitle.innerText = subParts.join(' · ');
```

**Step 2 — 在函数末尾(lapsBody.innerHTML 赋值后)追加**:
```js
    // V9.2 §E12a 侧栏环境卡(温度 + 湿度,无 AQI/风向)
    renderActivityDetailWeather(appState.currentWeather);
```

**Step 3 — 删除旧的 track section display:none 逻辑**(约 track.html:5894):
- 原代码:
```js
        var trackSection = document.getElementById('activity-detail-track-section');
        if (trackSection) {
            trackSection.style.display = (!caps.has_gps) ? 'none' : '';
        }
```
- 替换为:
```js
        // V9.2:track-section 现在是主视觉,沿用 display 控制但绑定 main-visual
        var trackSection = document.getElementById('activity-detail-track-section');
        if (trackSection) {
            trackSection.style.display = (!caps.has_gps) ? 'none' : '';
        }
```
- (此段逻辑保留,因为现在 track-section 是主视觉的一部分)

**Step 4 — 修改 thumb 渲染**(约 track.html:5914):
- 原代码:
```js
        if (caps.has_gps && record.thumbnail_points && record.thumbnail_points.length) {
            trackContainer.innerHTML = '<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(' + record.id + ')">' + buildTrackThumbnailSvg(record.thumbnail_points) + '<div class="detail-track-tip">点击此轨迹缩略图，自动切换到左侧【轨迹分析工具】并加载该条活动进行 3D 渲染</div></div>';
        } else {
            trackContainer.innerHTML = '<div class="detail-track-tip" style="margin-top:14px;border-radius:16px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);">当前活动无可用轨迹文件，无法生成轨迹缩略图。</div>';
        }
```
- 替换为(主视觉版):
```js
        if (caps.has_gps && record.thumbnail_points && record.thumbnail_points.length) {
            trackContainer.innerHTML = '<div class="detail-track-thumb" onclick="jumpToTraceFromActivityDetail(' + record.id + ')">' + buildTrackThumbnailSvg(record.thumbnail_points) + '<div class="detail-track-tip">点击进入 3D 沉浸分析(轨迹分析工具)</div></div>';
        } else {
            trackContainer.innerHTML = '<div class="detail-track-tip" style="color:#94a3b8;">当前活动无可用轨迹文件,无法生成轨迹地图。</div>';
        }
```

**Step 5 — metrics 渲染部分改造**(约 track.html:5884-5892):

原代码(简化):
```js
        if (displayMetrics && displayMetrics.length) {
            metrics.innerHTML = displayMetrics.map(function(m) {
                return '<div class="detail-metric"><span>' + ... + '</span><b>' + ... + '</b></div>';
            }).join('');
        } else {
            metrics.innerHTML = '<div class="detail-metric"><span>数据</span><b>--</b></div>';
        }
```

改造为(6 个固定 metric,3x2 grid):
```js
        // V9.2 §E05-E10:固定 6 个 metric 卡片(3x2 grid)
        var fixedMetrics = [
            { lbl: '距离',   val: formatDistance(detail.distance || record.distance) },
            { lbl: '时长',   val: formatDuration(detail.duration || record.duration) },
            { lbl: '平均配速', val: formatPace(detail.avg_pace || record.avg_pace) },
            { lbl: '平均心率', val: (detail.avg_hr || record.avg_hr || '--') + (detail.avg_hr ? ' bpm' : '') },
            { lbl: '热量消耗', val: (detail.calories || record.calories || '--') + (detail.calories ? ' kcal' : '') },
            { lbl: '累计爬升', val: (detail.ascent || record.total_ascent || '--') + (detail.ascent || record.total_ascent ? ' m' : '') },
        ];
        metrics.innerHTML = fixedMetrics.map(function(m) {
            return '<div class="overview-metric-card"><div class="lbl">' + m.lbl + '</div><div class="val">' + m.val + '</div></div>';
        }).join('');
```

**注意**:
- 使用既有 `formatDistance` / `formatDuration` / `formatPace` 函数(若不存在则需要回退到 inline 渲染)
- 若函数不存在,inline 渲染:
  - 距离: `((m/1000).toFixed(2) + ' km')`
  - 时长: `Math.floor(m/3600) + ':' + ...`
  - 配速: `Math.floor(m/60) + "'" + ...`

---

### 4.2 新增 `renderActivityDetailWeather(weather)` 函数

**位置**:`renderActivityDetail` 函数之后(约 track.html:5920 后)

**新增代码**:
```js
// === V9.2 §E12a 侧栏环境卡(温度 + 湿度,空态) ===
function renderActivityDetailWeather(weather) {
    var sidebar = document.getElementById('activity-detail-sidebar');
    if (!sidebar) return;
    // §六 shadow_diff 隔离:渲染前校验
    if (weather && (weather.shadow_diff || weather.shadow_diff_json || weather.diff)) {
        sidebar.innerHTML = '';
        return;
    }
    if (weather && (weather.temperature_c != null || weather.humidity != null)) {
        sidebar.innerHTML =
            '<div class="sidebar-card">' +
                '<div class="head">🌤 环境</div>' +
                '<div class="item-row"><span class="key">🌡 温度</span><span class="val">' + (weather.temperature_c != null ? weather.temperature_c + '°C' : '--') + '</span></div>' +
                '<div class="item-row"><span class="key">💧 湿度</span><span class="val">' + (weather.humidity != null ? weather.humidity + '%' : '--') + '</span></div>' +
                '<div class="item-row"><span class="key">☁ 状况</span><span class="val">' + (weather.weather_label || '--') + '</span></div>' +
            '</div>';
    } else {
        sidebar.innerHTML =
            '<div class="sidebar-card">' +
                '<div class="head">🌤 环境</div>' +
                '<div class="empty-msg">📭 当前没有可用的历史天气快照,轨迹分析与 AI 报告仍可正常生成。</div>' +
            '</div>';
    }
}
```

---

### 4.3 `openActivityDetailModal` 入口处清空陈旧 weather

**位置**:`openActivityDetailModal(activityId)` 函数,约 track.html:5925

**当前代码**(节选):
```js
    async function openActivityDetailModal(activityId) {
        const overlay = document.getElementById('activity-detail-overlay');
        if (!overlay) return;
        sportHubState.activeDetailId = activityId;
        overlay.classList.add('open');
        // ... 后续 setLoading 状态
        _fatigueReviewTabLoaded = false;
        // ...
    }
```

**改造**:在 `overlay.classList.add('open');` 之后,`_fatigueReviewTabLoaded = false;` 之前,新增 1 行:
```js
    async function openActivityDetailModal(activityId) {
        const overlay = document.getElementById('activity-detail-overlay');
        if (!overlay) return;
        sportHubState.activeDetailId = activityId;
        overlay.classList.add('open');
        // V9.2 §E12a:清空陈旧 weather,防止切活动时显示上一个活动的天气(M0 临时方案,M1 升级 get_activity_weather API)
        if (typeof setCurrentWeather === 'function') {
            setCurrentWeather(null);
        }
        // ... 后续 setLoading 状态
        _fatigueReviewTabLoaded = false;
        // ...
    }
```

---

### 4.4 `closeActivityDetailModal` 标题 + 副标题清理(防止下次打开残留)

**位置**:`closeActivityDetailModal()` 函数

**当前代码**(约 track.html:5840 后):
```js
    function closeActivityDetailModal() {
        const overlay = document.getElementById('activity-detail-overlay');
        if (overlay) overlay.classList.remove('open');
        sportHubState.activeDetailId = null;
        // ... cleanup helper
    }
```

**改造**:在 `sportHubState.activeDetailId = null;` 之后追加:
```js
        // V9.2:清空副标题(下次打开不会被上次残留)
        var subtitle = document.getElementById('activity-detail-subtitle');
        if (subtitle) subtitle.innerText = '点击轨迹缩略图可跳转到轨迹分析工具并加载 3D 渲染';
```

(注意:`title.innerText` 在 openActivityDetailModal 入口已重置为「活动详情加载中...」,无需特别处理)

---

## 5. 测试新增(1 个新文件)

### 5.1 新增 `tests/test_v9_2_overview_m0.py`

**结构**(6 个测试类):

```python
"""
V9.2 M0 契约测试:概览 Tab 改造(头部去 × / 3x2 metric / 主视觉地图 / 环境卡)
"""
from __future__ import annotations
import os, re, unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_HTML = os.path.join(_PROJECT_ROOT, "track.html")

def _read_track_html() -> str:
    with open(TRACK_HTML, encoding="utf-8") as f:
        return f.read()


class TestV9_2HeaderSimplification(unittest.TestCase):
    """§E01 头部去掉 × 关闭按钮(决策 1)"""
    def setUp(self): self.html = _read_track_html()
    def test_close_button_removed(self):
        self.assertNotIn('class="activity-detail-close"', self.html,
                         "V9.2 FAIL: × 关闭按钮应已删除")
    def test_back_button_preserved(self):
        self.assertIn('class="activity-detail-back"', self.html,
                      "V9.2 FAIL: ← 返回活动列表 按钮应保留")
    def test_esc_close_handler_preserved(self):
        # ESC 守卫应保留(通过 closeActivityDetailModal 触发)
        self.assertIn("closeActivityDetailModal", self.html,
                      "V9.2 FAIL: closeActivityDetailModal 应保留")


class TestV9_2MetricsGrid(unittest.TestCase):
    """§E05-E10 3x2 metric grid"""
    def setUp(self): self.html = _read_track_html()
    def test_overview_metrics_grid_class(self):
        self.assertIn('class="overview-metrics-grid"', self.html,
                      "V9.2 FAIL: 缺少 .overview-metrics-grid 容器")
    def test_overview_metric_card_class(self):
        self.assertIn('class="overview-metric-card"', self.html,
                      "V9.2 FAIL: 缺少 .overview-metric-card")
    def test_metrics_container_id_preserved(self):
        # 兼容 V9.0 既有 id
        self.assertIn('id="activity-detail-metrics"', self.html,
                      "V9.2 FAIL: #activity-detail-metrics 容器 id 应保留")
    def test_six_metric_labels(self):
        labels = ['距离', '时长', '平均配速', '平均心率', '热量消耗', '累计爬升']
        for lbl in labels:
            self.assertIn(lbl, self.html,
                          f"V9.2 FAIL: 缺少 metric 标签 '{lbl}'")


class TestV9_2MainVisual(unittest.TestCase):
    """§E11 轨迹地图升级为主视觉"""
    def setUp(self): self.html = _read_track_html()
    def test_overview_main_visual(self):
        self.assertIn('class="overview-main-visual"', self.html,
                      "V9.2 FAIL: 缺少 .overview-main-visual")
    def test_main_grid_2_1_layout(self):
        self.assertIn('class="overview-main-grid"', self.html,
                      "V9.2 FAIL: 缺少 .overview-main-grid")
    def test_track_section_in_main_visual(self):
        # track-section 现在位于 main-visual 容器内
        self.assertIn('id="activity-detail-track-section"', self.html,
                      "V9.2 FAIL: #activity-detail-track-section 应保留")


class TestV9_2SidebarEnvironment(unittest.TestCase):
    """§E12a 环境卡(温度 + 湿度)"""
    def setUp(self): self.html = _read_track_html()
    def test_sidebar_container_exists(self):
        self.assertIn('id="activity-detail-sidebar"', self.html,
                      "V9.2 FAIL: 缺少 #activity-detail-sidebar 容器")
    def test_render_activity_detail_weather_function(self):
        self.assertIn("function renderActivityDetailWeather(", self.html,
                      "V9.2 FAIL: 缺少 renderActivityDetailWeather 函数")
    def test_weather_card_no_aqi_no_wind(self):
        # M0 不渲染 AQI / 风向(决策 2)
        # 找到 renderActivityDetailWeather 函数体
        idx = self.html.find("function renderActivityDetailWeather(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0: end = idx + 3000
        body = self.html[idx:end]
        self.assertNotIn("AQI", body, "V9.2 FAIL: M0 不应渲染 AQI(决策 2)")
        self.assertNotIn("wind_direction", body, "V9.2 FAIL: M0 不应渲染 wind_direction(决策 2)")
    def test_shadow_diff_isolation_in_weather_render(self):
        idx = self.html.find("function renderActivityDetailWeather(")
        end = self.html.find("\n    function ", idx + 50)
        if end < 0: end = idx + 3000
        body = self.html[idx:end]
        self.assertIn("shadow_diff", body,
                      "V9.2 FAIL: 环境卡渲染缺 §六 shadow_diff 校验")


class TestV9_2SubtitleInlineWeather(unittest.TestCase):
    """§E03 副标题内嵌天气(决策 4)"""
    def setUp(self): self.html = _read_track_html()
    def test_subtitle_uses_record_date_label(self):
        # 副标题渲染应使用 record.date_label
        self.assertIn("record.date_label", self.html,
                      "V9.2 FAIL: 副标题未使用 record.date_label")
    def test_subtitle_uses_device_name(self):
        self.assertIn("record.device_name", self.html,
                      "V9.2 FAIL: 副标题未使用 record.device_name(决策 4)")
    def test_subtitle_inline_weather_when_available(self):
        # 内嵌天气逻辑:appState.currentWeather 检查
        self.assertIn("appState.currentWeather", self.html,
                      "V9.2 FAIL: 副标题未读 appState.currentWeather")


class TestV9_2NoBackendModification(unittest.TestCase):
    """M0 决策:0 改动 main.py / llm_backend.py"""
    def test_main_py_unchanged(self):
        with open(os.path.join(_PROJECT_ROOT, "main.py"), encoding="utf-8") as f:
            main = f.read()
        self.assertNotIn("V9.2", main,
                         "V9.2 FAIL: main.py 不应有 V9.2 标记(后端零变更)")
    def test_llm_backend_py_unchanged(self):
        with open(os.path.join(_PROJECT_ROOT, "llm_backend.py"), encoding="utf-8") as f:
            llm = f.read()
        self.assertNotIn("V9.2", llm,
                         "V9.2 FAIL: llm_backend.py 不应有 V9.2 标记")


if __name__ == "__main__":
    unittest.main()
```

---

## 6. 验收清单

### 6.1 功能验收

- [ ] 头部仅 `← 活动列表` 按钮(无 `×`)
- [ ] 副标题格式:`{date} · {region} · [{wx}] · {device}`
- [ ] 天气不可得时降级为:`{date} · {region} · {device}`
- [ ] 6 个 metric 卡片显示(3x2 grid)
- [ ] 距离 / 时长 / 平均配速 / 平均心率 / 热量消耗 / 累计爬升 数据正确
- [ ] 主视觉区域显示放大版轨迹地图
- [ ] 点击主视觉地图跳转 3D(走现有 `jumpToTraceFromActivityDetail`)
- [ ] 侧栏 1 张环境卡(只有温度 + 湿度 + 状况,无 AQI/风向)
- [ ] 天气无数据时显示空态文案
- [ ] 圈速统计表在底部正常显示
- [ ] 桌面 (≥1024px) 布局正确
- [ ] 切活动时天气卡显示空态(防陈旧)

### 6.2 契约验收

- [ ] §3 响应结构:无后端改动
- [ ] §五 数据可信分层:所有数据来自 `record.*` 或 `appState.currentWeather`
- [ ] §六 shadow_diff 隔离:`renderActivityDetailWeather` 渲染前过滤
- [ ] §11.2 审查门禁:不引入新文件 / 新依赖

### 6.3 测试验收

- [ ] `tests/test_v9_2_overview_m0.py` 新增 ≥ 16 个测试用例(已写 16 个)
- [ ] 既有 `test_v9_0_detail_tab_review.py` 仍通过
- [ ] 既有 `test_v8_8_switch_tab.py` 仍通过
- [ ] 既有 `test_e2e_fatigue_review.py` 仍通过
- [ ] 既有 `test_v9_2_overview_m0.py` 自身通过

---

## 7. 实施步骤(5 步,严格顺序)

1. **HTML 改造**(2 处):
   - 删除 `× 关闭` 按钮
   - 重写概览 Tab 容器
2. **CSS 改造**(在 `</style>` 前追加约 80 行)
3. **JS 改造**(4 处):
   - 改造 `renderActivityDetail` 副标题 / metrics / track 部分
   - 新增 `renderActivityDetailWeather` 函数
   - 在 `openActivityDetailModal` 入口清空 weather
   - 在 `closeActivityDetailModal` 重置 subtitle
4. **新增测试**:`tests/test_v9_2_overview_m0.py`(16 个用例)
5. **验收**:跑全部相关测试 + 手工验证桌面 1 套布局(无响应式,无 media query,用户确认仅桌面端)

---

## 8. 风险与回退

| 风险 | 等级 | 缓解 |
|---|---|---|
| `formatDistance` / `formatDuration` / `formatPace` 函数不存在 | 中 | 任务书 §4.1 Step 5 提供 inline fallback |
| 切活动时 `appState.currentWeather` 不被清空 | 中 | §4.3 入口处 `setCurrentWeather(null)` |
| 副标题过长(地区名 + 设备名 + 天气) | 低 | 桌面端使用 text-overflow: ellipsis(仅桌面端,无响应式) |
| 圈速统计行高过大 | 低 | 沿用既有 `.lap-table` 样式 |
| 既有 `test_v9_0_detail_tab_review.py` 失败 | 低 | 仅改容器 class,id 全保留,影响应可控 |

**回退方案**:
- 单文件 `track.html` 改动,`git diff` 可见
- 失败时 `git checkout track.html` 全量回退
- 测试失败时单独 revert 测试文件

---

## 9. 不在 M0 范围(明确排除)

- E12a 的 AQI / 风向 / 风级显示(占位 `--` 暂不显示)
- E12b / E12c / E12d 卡片容器与内容
- E11 全尺寸 Cesium 地图
- 副标题内嵌 AQI/风向
- 后端 API 扩展
- 复盘 Tab 改造
- 移动端响应式(无此使用场景)
- 平板端响应式(无此使用场景)
- 主题切换(浅色模式)

---

## 10. 验收签字

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 任务书交付 | __________ | __________ | __________ |
| 架构审查 | __________ | __________ | __________ |
| 业务确认 | __________ | __________ | __________ |

---

## 11. 后续路线

| Phase | 内容 | 依赖 | 触发条件 |
|---|---|---|---|
| M1 | E12a AQI/风向 + E12b 训练收益 | 后端扩展 | 后端 API 落地 |
| M2 | E12c 身体状态 | HRV/恢复接入 | 数据源就绪 |
| M3 | E12d 活动摘要 | 复盘派生层完善 | 复盘任务完成 |
| M4 | E11 Cesium 全图 | Cesium 集成 | 体验优化阶段 |

> 本任务书与 [docs/v9_2_overview_design.md](file:///Users/fanglei/应用开发/AI track/docs/v9_2_overview_design.md) 冲突时,以设计契约为准
