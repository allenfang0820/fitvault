# 概览 Tab 设计契约 V9.2

> Version: V9.2 Draft / 2026-Q2
> Status: 待审阅
> Author: 脉图架构组
> 关联契约:
> - `ARCHITECTURE.md`(§2.1 原则 1 全链路可追溯 / §4.5 ai_snapshot / §5.4 AI 边界 / §5.5 轨迹报告 v3 边界)
> - `.trae/rules/fit-arch-contrac.md`(§3 响应结构 / §5.4 / §5.6.2 阅后即焚 / §六 shadow_diff 隔离)
>
> 前置版本:V9.0(详情 Tab 化) + V9.1(3D 浮起阴影)
>
> 适用范围:`#detail-tab-overview` 内的全部 UI 元素、数据契约、视觉规范

---

## 1. 设计目标

### 1.1 核心目标

将活动详情 Modal 的「概览」Tab 改造为**信息密度高、专业运动风格、AI 增强**的一屏式仪表盘,使用户在 1 屏内完成「活动画像 → 环境背景 → 训练影响」的快速认知。

### 1.2 用户价值

| 旧痛点 | 新价值 |
|---|---|
| 概览 Tab 信息散落(2 张大卡片) | 信息分层(指标 / 主视觉 / 侧栏) |
| 天气信息埋藏在 trace 报告(需跳页) | 概览首屏即可见天气 |
| 副标题信息密度低(只有时间 + 设备) | 副标题内嵌地区 + 天气关键值 |
| 头部有 `× 关闭` 按钮(冗余) | 仅 `← 返回` + ESC 关闭(更专业) |
| 缩略图小,跳 3D 才发现详情 | 缩略图放大,作为主视觉 |

### 1.3 范围边界

- ✅ **本契约范围**:`#detail-tab-overview` 内部布局、视觉、数据流
- ❌ **不在本契约**:`#detail-tab-review` 内容、trace 页面、AI 链路(已在独立任务)
- ❌ **不在本契约**:后端 API 变更(待 M1/M2 阶段评估)

---

## 2. 信息架构(用户线框图原文)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← 活动列表                                                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  西城区晨跑                                                                    │
│  2026-06-04 08:15 · 北京市 · 晴 · 27°C · Garmin Instinct 3 Tactical          │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   概览   │   复盘                                                              │
│ ───────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│  ┌────────────┬────────────┬────────────┐                                   │
│  │ 距离       │ 时长       │ 平均配速    │                                   │
│  │            │            │            │                                   │
│  │ 5.54 km    │ 37:49      │ 6'49"/km   │                                   │
│  └────────────┴────────────┴────────────┘                                   │
│                                                                              │
│  ┌────────────┬────────────┬────────────┐                                   │
│  │ 平均心率    │ 热量消耗    │ 累计爬升    │                                   │
│  │            │            │            │                                   │
│  │ 131 bpm    │ 462 kcal   │ 48 m       │                                   │
│  └────────────┴────────────┴────────────┘                                   │
│                                                                              │
│                                                                              │
│  ┌──────────────────────────────────────┬───────────────────────────────┐   │
│  │                                      │  ┌─────────────────────────┐  │   │
│  │                                      │  │ 🌤 环境                  │  │   │
│  │                                      │  │                         │  │   │
│  │                                      │  │ 27°C                    │  │   │
│  │                                      │  │ 湿度 81%               │  │   │
│  │                                      │  │ AQI 72                 │  │   │
│  │                                      │  │ 东南风 3级             │  │   │
│  │                                      │  └─────────────────────────┘  │   │
│  │                                      │                               │   │
│  │                                      │  ┌─────────────────────────┐  │   │
│  │                                      │  │ 🔥 训练收益              │  │   │
│  │                                      │  │                         │  │   │
│  │                                      │  │ 有氧收益                │  │   │
│  │                                      │  │ 提升有氧体能             │  │   │
│  │                                      │  │                         │  │   │
│  │                                      │  │ 无氧刺激                │  │   │
│  │                                      │  │ 轻度提升                │  │   │
│  │                                      │  └─────────────────────────┘  │   │
│  │                                      │                               │   │
│  │                                      │  ┌─────────────────────────┐  │   │
│  │                                      │  │ 🫀 身体状态              │  │   │
│  │                                      │  │                         │  │   │
│  │                                      │  │ 训练压力：中等          │  │   │
│  │                                      │  │ 恢复需求：12h           │  │   │
│  │                                      │  │ 当前状态：稳定          │  │   │
│  │                                      │  └─────────────────────────┘  │   │
│  │                                      │                               │   │
│  │                                      │  ┌─────────────────────────┐  │   │
│  │                                      │  │ ✨ 活动摘要              │  │   │
│  │                                      │  │                         │  │   │
│  │                                      │  │ 稳定低强度有氧跑。       │  │   │
│  │                                      │  │ 热环境略影响后程效率。   │  │   │
│  │                                      │  └─────────────────────────┘  │   │
│  │                                      │                               │   │
│  │                                      │                               │   │
│  │                                      │                               │   │
│  │                                      │                               │   │
│  │           轨迹地图（主视觉）           │                               │   │
│  │                                      │                               │   │
│  │       配速热力渐变 / 起终点标记        │                               │   │
│  │                                      │                               │   │
│  │                                      │                               │   │
│  │                                      │                               │   │
│  └──────────────────────────────────────┴───────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ 📈 圈速统计                                                          │    │
│  │ 圈速 | 配速 | 心率 | 步频 | GCT | 功率                                │    │
│  │ ...                                                                  │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 12 元素清单

### 3.1 元素矩阵

| ID | 元素 | 位置 | 数据源(字段) | 状态 | M0 实施? |
|---|---|---|---|---|---|
| E01 | `← 活动列表` 按钮 | head 左侧 | — | ✅ 已有(V9.0) | ✅ |
| E02 | 活动标题 | head 中央 | `record.title` | ✅ 已有 | ✅ |
| E03 | 副标题(时间/地区/天气/设备) | head 标题下 | `record.start_time + region_display + weather(temperature_c + weather_label) + record.device` | ⚠️ 需内嵌天气 | ✅(基础部分) |
| E04 | Tab Bar(概览/复盘) | head 下方 | — | ✅ V9.0 + V9.1 | ✅ |
| E05 | 距离 metric | 指标区 (1,1) | `record.distance` | ✅ 已有 | ✅ |
| E06 | 时长 metric | 指标区 (1,2) | `record.duration` | ✅ 已有 | ✅ |
| E07 | 平均配速 metric | 指标区 (1,3) | `record.avg_pace` | ✅ 已有 | ✅ |
| E08 | 平均心率 metric | 指标区 (2,1) | `record.avg_hr` | ✅ 已有 | ✅ |
| E09 | 热量消耗 metric | 指标区 (2,2) | `record.calories` | ✅ 已有 | ✅ |
| E10 | 累计爬升 metric | 指标区 (2,3) | `record.ascent` | ✅ 已有 | ✅ |
| E11 | 轨迹地图(主视觉) | 主体左侧 (2/3 宽) | `record.thumbnail_points` + SVG builder | ✅ 已有但需放大 | ✅ |
| E12a | 🌤 环境 卡 | 侧栏第 1 张 | `weather.temperature_c + humidity + AQI + wind` | ⚠️ AQI/风向需扩展 | ✅(部分占位) |
| E12b | 🔥 训练收益 卡 | 侧栏第 2 张 | `record.aerobic_training_effect / anaerobic_training_effect` | ⚠️ 待查 | ❌ M0 不实施 |
| E12c | 🫀 身体状态 卡 | 侧栏第 3 张 | 训练负荷 + HRV + 恢复(多源) | ⚠️ 数据未接入 | ❌ M0 不实施 |
| E12d | ✨ 活动摘要 卡 | 侧栏第 4 张 | **复盘派生指标 consume**(非 AI 重新生成) | ❌ 等待复盘完善 | ❌ M0 不实施 |
| E13 | 圈速统计表 | 主体下方 | `record.laps` | ✅ 已有 | ✅ |

### 3.2 M0 范围(7 个 ✅ 元素)

E01 + E02 + E03(基础)+ E04 + E05-E10 + E11 + E12a(基础)+ E13

**M0 不含 E12b/c/d**(等待后端扩展 + 复盘完善)

### 3.3 元素实现细节

#### E03 副标题(基础部分 M0 可做)

格式:`{YYYY-MM-DD HH:mm} · {地区} · 设备名`

天气内嵌(待定):`{YYYY-MM-DD HH:mm} · {地区} · {晴}·{27°C} · 设备名`

**M0 决策**:**内嵌天气**(节省 Tab 内高度,信息密度更高)
- 天气数据不可得时降级为:`{YYYY-MM-DD HH:mm} · {地区} · 设备名`
- AQI / 风向不内嵌(避免副标题过长)

#### E11 轨迹地图(主视觉 M0)

- 复用现有 `buildTrackThumbnailSvg(record.thumbnail_points)` 函数
- **尺寸升级**:从缩略图 ~200x100 升级到主视觉 ~600x300
- **保留跳转**:点击放大版仍触发 `jumpToTraceFromActivityDetail(id)`(走现有 3D 链路)
- **新增功能**:配速热力渐变 / 起终点标记(在线框图中,但 M0 可暂用基础 SVG,后续 M3 升级)

#### E12a 环境卡(M0 部分)

| 子项 | M0 | 备注 |
|---|---|---|
| 🌡 温度 | ✅ 显示 | 来自 `weather.temperature_c` |
| 💧 湿度 | ✅ 显示 | 来自 `weather.humidity` |
| AQI 72 | ❌ 占位 `--` | M1 后端扩展 |
| 💨 风向风级 | ❌ 占位 `--` | M1 后端扩展 |
| 空态 | ✅ 显示 | 沿用 trace 报告原空态 |

#### E12b/c/d(M0 不实施)

M0 仅在 HTML 中保留卡片容器(灰色骨架,标 "数据接入中"),**不渲染**。具体内容待后端/复盘就绪后实施。

---

## 4. 布局栅格

### 4.1 桌面端(≥1024px)

```
┌─────────────────────────────────────────────────┐
│ E01 [← 活动列表]                                  │
│ E02 标题                                          │
│ E03 副标题(时间 · 地区 · 天气 · 设备)              │
│ E04 ┌──[概览]──[复盘]──┐                         │
├─────────────────────────────────────────────────┤
│ E05-E10  3x2 指标 grid                           │
├──────────────────────────┬──────────────────────┤
│                          │  E12a 环境            │
│                          │  E12b 训练收益(占位)  │
│   E11 轨迹地图(主视觉)    │  E12c 身体状态(占位)  │
│   2/3 宽                 │  E12d 活动摘要(占位)  │
│                          │  1/3 宽               │
├──────────────────────────┴──────────────────────┤
│ E13 圈速统计表                                    │
└─────────────────────────────────────────────────┘
```

栅格规则:
- 指标 grid:`grid-template-columns: repeat(3, 1fr)`
- 主体 + 侧栏:`grid-template-columns: 2fr 1fr`(主体占 2/3,侧栏占 1/3)
- 卡片间距:`gap: 16px`

### 4.2 仅桌面端(≥1024px)

- 指标 grid:`repeat(3, 1fr)`(固定)
- 主体 + 侧栏:`2fr 1fr`(固定,主体占 2/3,侧栏占 1/3)
- 卡片间距:`gap: 16px`

> **V9.2 决策**:仅桌面端使用场景(用户确认),无移动端无平板端。**最小支持分辨率 = 1024px**。**不设任何 media query 断点**,布局固定。

---

## 5. 视觉规范

### 5.1 复用 V9.1 设计令牌

| 令牌 | 值 | 来源 |
|---|---|---|
| 主背景 | `rgba(15, 23, 42, 0.6)` | 既有 |
| 卡片背景 | `rgba(30, 41, 59, 0.6)` | 既有 |
| 边框 | `rgba(255, 255, 255, 0.08)` | 既有 |
| 主色 | `#6c5ce7` | 既有 |
| 文字主 | `#f8fafc` | 既有 |
| 文字次 | `#94a3b8` | 既有 |
| 圆角 | `8-12px` | 既有 |
| 阴影 | 多层(详见 V9.1) | 既有 |

### 5.2 新增视觉规范

#### metric 卡片(E05-E10)

```css
.metric-card-v2 {
    padding: 14px 16px;
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}
.metric-card-v2 .lbl {
    font-size: 0.7rem;
    color: #94a3b8;
    margin-bottom: 6px;
}
.metric-card-v2 .val {
    font-size: 1.5rem;
    color: #f8fafc;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
}
.metric-card-v2 .unit {
    font-size: 0.8rem;
    color: #94a3b8;
    margin-left: 4px;
}
```

#### 侧栏卡片(E12a/b/c/d)

```css
.sidebar-card {
    padding: 14px 16px;
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(108, 92, 231, 0.12);
    border-radius: 10px;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.05) inset,
        0 2px 6px rgba(0, 0, 0, 0.25);
    margin-bottom: 10px;
}
.sidebar-card .head {
    font-size: 0.78rem;
    font-weight: 700;
    color: #c4b5fd;
    margin-bottom: 8px;
}
.sidebar-card .item-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.72rem;
    padding: 2px 0;
    color: #cbd5e1;
}
.sidebar-card .item-row .key { color: #94a3b8; }
.sidebar-card .item-row .val { color: #f8fafc; font-weight: 600; }
```

#### 占位骨架(E12b/c/d M0 用)

```css
.sidebar-card.skeleton {
    opacity: 0.45;
    background: rgba(15, 23, 42, 0.4);
    border-style: dashed;
}
.sidebar-card.skeleton .skeleton-text {
    height: 10px;
    background: rgba(148, 163, 184, 0.15);
    border-radius: 3px;
    margin: 6px 0;
    animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.8; }
}
```

---

## 6. 交互规范

### 6.1 全局

- 关闭 Modal:点击 backdrop / 按 ESC / 点 `← 活动列表`(三选一)
- 详情 Modal 已有 `onclick="if(event.target===this) closeActivityDetailModal()"`,复用即可
- ESC 关闭:沿用现有 ESC 守卫(若已实现)

### 6.2 元素级

| 元素 | hover | active | loading | error | empty |
|---|---|---|---|---|---|
| E01 返回 | 文字变浅 | — | — | — | — |
| E05-E10 metric | 微浮起 1px | — | "--" | 红色"加载失败" | "暂无数据" |
| E11 轨迹地图 | cursor pointer | — | "加载中"骨架 | 红色 toast | "无轨迹数据" |
| E12a 环境 | — | — | "查询中" | "天气不可用" | "无天气数据" |
| E12b/c/d 占位 | — | — | 骨架 pulse | — | "数据接入中" |
| E13 圈速表 | — | — | "加载中"行 | "加载失败"行 | "暂无圈速" |

### 6.3 阅后即焚(本契约不引入新 AI 洞察,E12d 待复盘完善后另行约定)

---

## 7. 数据契约

### 7.1 字段来源矩阵

| 字段 | 数据源 | 后端 API | Resolver 路径 | 备注 |
|---|---|---|---|---|
| `record.title` | `activities.title` | `get_activity_detail` | `_build_record_from_row` | 既有 |
| `record.start_time` | `activities.start_time` | 同上 | 同上 | 既有 |
| `record.region_display` | `activities.region` | 同上 | `resolve_activity_region` | 既有 |
| `record.distance` | `activities.distance` | 同上 | 既有 | m → km(前端) |
| `record.duration` | `activities.duration` | 同上 | 既有 | s → "37:49"(前端) |
| `record.avg_pace` | `activities.avg_pace` | 同上 | 既有 | sec/km → "6'49\""(前端) |
| `record.avg_hr` | `activities.avg_hr` | 同上 | 既有 | — |
| `record.calories` | `activities.calories` | 同上 | 既有 | — |
| `record.ascent` | `activities.total_ascent` | 同上 | 既有 | m |
| `record.thumbnail_points` | 后端预计算 | 同上 | 既有 | 数组 `{lat, lon}` |
| `weather.temperature_c` | 后端 weather resolver | `appState.currentWeather` | 既有(M0 暂时) | — |
| `weather.humidity` | 同上 | 同上 | 同上 | — |
| `weather.weather_label` | 同上 | 同上 | 同上 | 中文("晴"等) |
| `weather.AQI` | ❌ 无 | — | — | M1 后端扩展 |
| `weather.wind_direction` | ❌ 无 | — | — | M1 后端扩展 |
| `weather.wind_level` | ❌ 无 | — | — | M1 后端扩展 |
| `record.aerobic_training_effect` | FIT 字段 | `get_activity_detail` | 待 Resolver 透传 | M1 待查 |
| `record.anaerobic_training_effect` | FIT 字段 | 同上 | 同上 | M1 待查 |
| `body.training_load` | 后端计算 | `get_fatigue_review` | Resolver | M1 接入 |
| `body.recovery_hours` | ❌ 无 | — | — | M1+ 接入 |
| `body.current_status` | ❌ 无 | — | — | M1+ 接入 |
| `summary.text` | 复盘派生 | `get_fatigue_review.data` | Resolver | M2 复用 |

### 7.2 M0 临时方案:appState.currentWeather

**问题**:`appState.currentWeather` 在 `openActivityDetailModal` 打开时未刷新,可能为空或陈旧。

**M0 缓解**:
- 在 `openActivityDetailModal` 入口处 `setCurrentWeather(null)` 清空陈旧
- 显示"暂无数据"空态
- 用户期望看到天气时,主动 trace → 回退(暂不优化)

**M1 长期方案**:`get_activity_weather` 新 API(详见 ARCHITECTURE 审阅时已确认)

### 7.3 §六 shadow_diff 隔离

- E12a/b/c/d 任一卡片**严禁**展示 `shadow_diff` / `shadow_diff_json` / `diff` 字段
- 数据消费前在 `renderXxx` 函数中校验
- 同 V9.0 阅后即焚 Modal 校验逻辑(行 9882 模式)

---

## 8. 实施路线图

### 8.1 阶段总览

| Phase | 范围 | 依赖 | Done 定义 | 风险 |
|---|---|---|---|---|
| **M0** | E01-E11, E12a 基础, E13 | 无 | 桌面 1 套布局(无响应式),7 个 ✅ 元素就位,天气基础字段渲染 | 低 |
| **M1** | E12a AQI/风向 + E12b 训练收益 | 后端扩展 weather API + Resolver 透传 training_effect | M0 元素外加 2 类扩展字段 | 中 |
| **M2** | E12c 身体状态 | HRV/恢复数据接入 + 训练负荷组合 | 多源数据组合展示 | 中 |
| **M3** | E12d 活动摘要 | 复盘派生层完善 + 复用机制 | consume-only,无 AI 重新生成 | 中 |
| **M4** | E11 全尺寸 Cesium 地图 | 概览 Tab 嵌入 Cesium 实例 | 缩略图 → 全图 → 3D 链路完整 | 高 |

### 8.2 M0 详细任务边界

**M0 含**:
- 7 个 ✅ 元素(E01-E11, E12a 基础, E13)
- 3D 浮起 Tab Bar 复用(V9.1)
- 头部简化(去掉 `× 关闭`,保留 `← 返回` + ESC + backdrop)
- 桌面 1 套布局(无响应式,无 media query)
- E12a 的温度/湿度/空态(无 AQI/风向)
- 圈速统计表保留

**M0 不含**:
- E12a 的 AQI / 风向 / 风级(占位 `--`)
- E12b / E12c / E12d 实体内容(占位骨架)
- E11 全尺寸 Cesium 地图(继续用放大版 SVG 缩略图)
- 副标题内嵌天气(AQI/风向,温度部分可)
- 复盘侧改造(独立任务)

### 8.3 复用契约

| 复用对象 | 位置 | 复用方式 |
|---|---|---|
| `buildTrackThumbnailSvg` | track.html:5839 | 直接调用,改尺寸参数 |
| `jumpToTraceFromActivityDetail` | track.html:6071 | 现有 3D 跳转,不变 |
| `appState.currentWeather` | track.html:8508 | 临时使用,M1 替换 |
| `.weather-glass-card` CSS | track.html:1902 | 改名 `.sidebar-weather-card` 或直接复用 |
| `setCurrentWeather` | track.html:8574 | 修改为 `(weather, activityId)` 双参数 |
| Tab Bar HTML + CSS | V9.0 + V9.1 | 完全复用 |

---

## 9. 验收清单(M0)

### 9.1 功能验收

- [ ] 活动列表点击 → 详情 Modal 打开,默认概览 Tab
- [ ] 头部显示 `← 活动列表` 按钮(无 `× 关闭`)
- [ ] 标题 + 副标题正确显示(时间/地区/天气若可得/设备)
- [ ] Tab Bar 浮起阴影效果正常(V9.1)
- [ ] 6 个 metric 卡片(3x2)显示数据正确
- [ ] 轨迹地图(放大版 SVG)显示,点击跳转 3D
- [ ] 侧栏 4 张卡片(环境/训练/身体/摘要)就位,后 3 张为占位骨架
- [ ] 环境卡显示温度/湿度,无数据时显示空态
- [ ] 圈速统计表显示
- [ ] 桌面 1 套布局正确(无响应式,无 media query)
- [ ] ESC 关闭 Modal(沿用)
- [ ] 点 backdrop 关闭 Modal(沿用)

### 9.2 契约验收

- [ ] §3 响应结构:`get_activity_detail` 调用未变,res.code === 0
- [ ] §五 数据可信分层:所有数据来自 `record.*` 或 `appState.currentWeather`,无前端自造
- [ ] §六 shadow_diff 隔离:卡片渲染前过滤,无 `shadow_diff` 字样
- [ ] §7.1 敏感字段脱敏:无 `api_key` 出现在 DOM
- [ ] §11.2 审查门禁:不引入新文件 / 新依赖 / 不改后端

### 9.3 测试验收

- [ ] `test_v9_2_overview_redesign.py` 新增(待 M0 任务书细化)
- [ ] `test_v9_0_detail_tab_review.py` 仍通过
- [ ] `test_v8_8_switch_tab.py` 仍通过
- [ ] `test_e2e_fatigue_review.py` 仍通过

---

## 10. 风险与备选

| 风险 | 等级 | 缓解 |
|---|---|---|
| E12b/c/d 永远不来数据 | 中 | 占位骨架带 "数据接入中" 提示,避免误以为已实现 |
| 副标题过长(地区名 + 设备名 + 天气) | 低 | 桌面端 max-width 容器 + text-overflow: ellipsis(已加) |
| 圈速统计表行高过大 | 低 | 沿用现有 .lap-table 样式 |
| `appState.currentWeather` 永久陈旧 | 中 | M0 入口 setCurrentWeather(null);M1 升级 API |
| 天气 resolver 失败无降级 | 低 | 已有空态文案 |
| M0 范围蔓延(用户要求加更多元素) | 中 | 严格按 7 个 ✅ 元素实施,其他纳入 M1+ 排队 |

---

## 11. 不在范围(明确排除)

| 排除项 | 原因 | 后续阶段 |
|---|---|---|
| 复盘 Tab 内容改造 | 独立任务 | — |
| 后端 API 新增/扩展 | 任务书 9 节"不引入新 API" | M1/M2/M3 |
| AI 链路(活动摘要 LLM) | 复用复盘派生,不重生成 | M3 |
| Cesium 全尺寸地图 | 重大改造 | M4 |
| 移动端响应式 | 不在脉图范围(无此使用场景) | — |
| 平板端响应式 | 不在脉图范围(无此使用场景) | — |
| 主题切换(浅色模式) | 不在脉图范围 | — |

---

## 12. 变更控制

- 本契约更新需经过:架构组评审 + 用户签字
- 本契约的代码落地前必须先出"M0 实施任务书"(细化到行)
- 本契约与 ARCHITECTURE.md / fit-arch-contrac.md 冲突时,以架构契约为准

---

## 13. 验收签字

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 设计交付 | __________ | __________ | __________ |
| 架构审查 | __________ | __________ | __________ |
| 业务确认 | __________ | __________ | __________ |

---

> 文档版本控制:
> - V9.2 Draft(2026-Q2):初版,待审阅
