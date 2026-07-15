# RCV2-07 V2 高保真视觉、交互与响应式契约

完成时间：2026-07-14

本文冻结 Records Center V2 的视觉方向、信息架构、组件状态、响应式断点、可访问性和截图验收基线。后续 `RCV2-32` 至 `RCV2-35` 前端实现必须按本文执行，并严格遵守 `RCV2-06` API/ViewModel 契约。

## 1. 视觉参考取舍

参考文件：

- `/Users/fanglei/Downloads/sports_records.html`
- `/Users/fanglei/Desktop/截屏2026-07-14 10.52.59.png`

可继承：

- 深色沉浸背景。
- 蓝色主高亮与少量运动辅助色。
- 顶部运动页签。
- 左侧纪录卡片列表。
- 右侧大图表主舞台。
- 底部 3 张摘要卡。
- 大圆角、细边框、柔和阴影、低饱和文字层级。
- 当前选中卡片高亮边框和轻微发光。

必须舍弃：

- “运动成就看板”独立导航和头像/通知等无关外壳。
- 外部 CDN：Tailwind CDN、Iconify CDN、ECharts CDN、Google Fonts。
- “表现指数”“基准值 100”“指数越高代表成绩越好”等伪指标。
- 2018-2022 伪年度数据。
- 硬编码 5K/10K/半马/全马卡片作为所有运动通用结构。
- 前端计算提升率、活跃天数、累计训练小时。
- 前端从 DOM、图表或历史点反推纪录事实。

## 2. 页面定位

产品名：

```text
记录中心
```

位置：

```text
运动生涯 > 记录中心
```

视觉语气：

- 像“运动生涯里的数据陈列馆”，不是独立娱乐网站。
- 重点表达个人纪录的可信、演进和待确认。
- 避免竞技平台式夸张庆祝；只有后端 active 新纪录事件允许轻量庆祝。

## 3. 信息架构

桌面布局：

```text
┌──────────────────────────────────────────────────────────────┐
│ 运动生涯 header / 当前模块标题 / rebuild 状态                 │
├──────────────────────────────────────────────────────────────┤
│ Sport tabs from Catalog                                      │
├───────────────┬──────────────────────────────────────────────┤
│ 左侧导航       │ 右侧主舞台                                    │
│ - 状态页签     │ - 主图 / 当前纪录 / 历史演进 / 曲线             │
│ - 分组列表     │ - 详情摘要 / 候选操作 / 灰态说明               │
│ - record cards │ - 底部指标卡                                  │
└───────────────┴──────────────────────────────────────────────┘
```

一级运动页签：

- 跑步
- 骑行
- 徒步
- 游泳
- 越野

页签来源：

```text
get_career_record_catalog().sports
```

二级状态页签：

- 当前纪录
- 演进
- 候选

二级页签状态：

- 有候选时显示候选数量徽标。
- `validation_required` 运动默认落在当前纪录页，但主舞台显示待验证灰态。
- `analysis_only/model_only` 不作为当前纪录页签内容，只进入曲线/分析区。

左侧区域：

- 顶部显示当前 sport label 和记录数摘要。
- 分组 accordion：如跑步标准距离、骑行功率、骑行整次活动、徒步海拔、泳池、公开水域、越野路线。
- 纪录卡片由 Catalog + Records ViewModel 组合生成。
- 卡片显示：`display_name`、`metric.display`、`scope.labels`、`event_date/display_date`、状态徽标、候选/待验证标记。

右侧主舞台：

- 标题来自选中 record 的 `display_name`。
- 副标题来自 `sport_label/source_mode_label/scope.labels`。
- 大图优先显示 History 或 Curve ViewModel。
- 图下摘要只显示后端 `history_summary`、`metric`、`improvement` 和 `quality`。

底部摘要卡：

- 当前值。
- 总提升或首次记录。
- 最近一次刷新/候选数量/数据状态。

所有值必须来自 API，不得在前端补算。

## 4. 运动专属展示

### 4.1 跑步

默认分组：

- 标准距离 PB：5K、10K、半马、马拉松。

主图：

- History line chart。
- y 轴方向由 `axis_direction` 决定；时间越低越好时图表可采用“成绩提升向上”的视觉转换，但必须由后端提供 `chart.points` 和 `axis_direction`，前端不得重算原值。

卡片值：

- 使用 `metric.display`，例如 `54:38`。
- 不显示表现指数。

### 4.2 骑行

默认分组：

- 标准距离：10K、20K、40K、50K、100K、180K；V2 先以轻量标题卡展示，正式纪录状态由 Catalog 的 `validation_required` 表达。
- 功率纪录：5s、30s、1m、5m、10m、20m、30m、60m、2h。
- 整次活动：最长距离、最大爬升、最长历时、最大机械功。
- 分析曲线：Power Duration Curve。

主图：

- 标准距离纪录显示 History line；无正式历史时显示距离-时间流待验收空态。
- 功率纪录选中时在记录中心主视图仍显示统一 History line；Power Duration Curve 仅作为后端/详情分析能力，不在主视图另开大模块。
- 整次活动纪录显示 History line/bar。

卡片值：

- 功率：`248 W`。
- 距离：`128.4 km`。
- 爬升：`1,620 m`。
- 机械功：若 `validation_required`，显示待验证，不显示正式值。

禁止：

- 显示 W/kg 正式纪录。
- 显示 FTP/CP/W′/TSS/IF 为正式纪录。

### 4.3 徒步

默认分组：

- 整次活动：最长距离、最大累计爬升、最长历时、最高海拔。
- 海拔范围：最大连续爬升。

主图：

- 整次活动纪录显示 History。
- 最大连续爬升可显示 range summary，不显示完整轨迹。

卡片状态：

- 最大连续爬升默认 candidate-only，必须带“需复核”徽标。

禁止：

- 把 walking/mountaineering/trail_running 混到徒步页。
- 用总爬升冒充连续爬升。

### 4.4 游泳

运动内二级水域切换：

- 泳池
- 公开水域

泳池：

- 50m、100m、200m、400m、800m、1500m。
- 默认 `validation_required`，显示“等待泳池长度事实/真实样本验证”。
- 不默认 25m。

公开水域：

- 750m、1500m、1900m、3800m、5K、10K。
- 最长距离、最长历时。
- 默认 candidate-only，显示“公开水域 GPS 质量需复核”。

禁止：

- 在无真实泳池样本时展示正式泳池纪录。
- 前端根据距离自行判断标准距离命中。

### 4.5 越野

默认分组：

- 整次活动：距离、爬升、历时、最高海拔、连续爬升。
- 路线 PR。
- 赛段 PR。
- 分析曲线：Pace/GAP。

主图：

- 整次活动纪录显示 History。
- route/segment 显示 route/segment 安全摘要和匹配状态，不显示完整地图轨迹。
- Pace/GAP 曲线只作为分析区，不能显示成正式纪录。

默认状态：

- 因真实样本为 0，所有越野正式纪录默认 candidate-only 或灰态。

## 5. 组件状态

### 5.1 Loading

- 使用固定高度 skeleton。
- 左侧卡片、右侧主图、底部摘要分别占位。
- 不显示伪值。

### 5.2 Empty

文案：

```text
还没有可展示的记录
完成一次符合规则的活动后，这里会显示你的正式记录。
```

要求：

- 不用 fixture 或 mock 填充。
- 保留 Catalog 分组，让用户知道可支持哪些纪录。

### 5.3 Partial

展示：

- 可用纪录正常显示。
- 缺失部分以灰态说明展示。
- `warnings` 以轻提示显示，不阻断主流程。

### 5.4 Candidate

候选卡片：

- 标题前加“待确认”徽标。
- 显示 `quality.message_key` 对应文案和 reason chips。
- 可确认时显示“确认 / 忽略”按钮。
- hard-block 候选不显示确认按钮。

禁止：

- 候选进入当前纪录榜首。
- 候选触发烟花/庆祝/成就。

### 5.5 Validation Required

视觉：

- 灰态卡片。
- 虚线边框。
- 显示缺失事实或待验收原因。

文案示例：

```text
规则已准备好，仍需真实数据验证
当前缺少泳池长度事实，暂不生成正式纪录。
```

### 5.6 Rebuilding

- 顶部状态条显示“正在重建记录索引”。
- 保留上次成功结果。
- 禁止清空当前列表。

### 5.7 Error

- 局部错误卡片。
- 保留上次可用数据。
- 提供重试入口，但不自动 rebuild。

## 6. 视觉 tokens

颜色：

| token | 值 | 用途 |
| --- | --- | --- |
| `--rc-bg` | `#0F1020` | 页面背景 |
| `--rc-surface` | `#191A2E` | 主卡片 |
| `--rc-surface-2` | `#20213A` | 选中卡片/嵌套卡片 |
| `--rc-border` | `#2C2E4A` | 普通边框 |
| `--rc-border-active` | `#4FC3F7` | 主高亮 |
| `--rc-text` | `#F2F4FF` | 主文字 |
| `--rc-muted` | `#9296AD` | 次文字 |
| `--rc-blue` | `#4FC3F7` | 跑步/主高亮 |
| `--rc-orange` | `#FF9F43` | 骑行/警示 |
| `--rc-green` | `#5FD18B` | 徒步/可用 |
| `--rc-cyan` | `#4DD9D4` | 游泳 |
| `--rc-purple` | `#A78BFA` | 越野/分析 |
| `--rc-danger` | `#FB7185` | 错误/不可用 |

尺寸：

- 页面最大宽度：`1440px`。
- 桌面外边距：`32px`。
- 主布局 gap：`28px`。
- 左侧宽度：`300px`。
- 主卡片圆角：`28px`。
- 纪录卡圆角：`18px`。
- 主图最小高度：`380px`。
- 小卡片内边距：`16-20px`。

字体：

- 使用系统字体栈，不引入 Google Fonts。
- 数字可使用 `font-variant-numeric: tabular-nums`。

图标：

- 使用现有项目本地图标能力或 CSS/内置 SVG。
- 不使用 Iconify CDN。

图表：

- 优先复用项目现有本地图表能力。
- 不使用外部 ECharts CDN。
- 如果运行环境无图表库，前端任务必须实现简化 SVG/canvas 折线 fallback。

## 7. 响应式断点

### >= 1200px

- 左侧 `300px`，右侧自适应。
- 底部摘要三列。
- 主图和详情同屏。

### 1100px

- 左侧降为 `280px`。
- 主图标题和筛选按钮允许换行。
- 底部摘要保持三列但缩短文案。

### 980px

- 左侧变为顶部横向 record rail。
- 主舞台单列。
- 分组 accordion 横向滚动。

### 720px

- sport tabs 横向滚动。
- 二级状态页签固定在 sport tabs 下。
- 纪录卡一列。
- 底部摘要改为一列或两列。
- 主图高度降为 `300px`。

### < 520px

- 隐藏非必要副文案。
- metric display 保留，scope labels 折叠为最多 1 行。
- 候选操作按钮全宽堆叠。

## 8. 可访问性与交互

键盘：

- Sport tabs、状态页签、record cards、候选按钮均可 Tab 聚焦。
- 左右方向键可在同组 tabs 中移动。
- Enter/Space 激活选中项。

读屏：

- 当前选中 tab 使用 `aria-selected=true`。
- 当前纪录卡使用 `aria-current=true`。
- 候选按钮有明确 action label。
- 图表必须有文本摘要 `aria-label` 或旁路 summary。

Reduced motion：

- 系统开启 reduced motion 时关闭发光动画和曲线入场动画。
- hover 只保留颜色/边框变化。

文本溢出：

- 标题最多 2 行。
- 卡片 scope labels 最多 1 行，超出省略。
- reason chips 最多 3 个，其余折叠为“+N”。

## 9. 截图验收基线

后续 `RCV2-35` 至少产出以下截图：

| 场景 | 宽度 | 必须可见 |
| --- | ---: | --- |
| 跑步 available | 1440 | sport tabs、跑步纪录卡、history 主图、底部摘要。 |
| 骑行功率 | 1440 | 功率锚点、Power Duration Curve、W 单位、curve anchors。 |
| 徒步 candidate-only | 1440 | 最大连续爬升候选徽标、海拔 reason 文案。 |
| 游泳 validation-required | 1440 | 泳池灰态、pool length 缺失说明、公开水域 candidate-only。 |
| 越野 candidate-only | 1440 | 路线/赛段待验收、无真实样本说明。 |
| 窄窗口 | 720 | sport tabs 横滚、record rail、主图单列。 |
| 错误/重建 | 1440 | 保留旧结果、局部状态条。 |

## 10. 实现边界

前端实现任务必须清理 V1 冗余：

- 删除或替换 `track.html` 中硬编码的未交付骑行 PB 筛选项。
- 用 Catalog 驱动替代 V1 `career-pb-*` 硬编码结构。
- 删除“PB中心”或旧 PB-only 文案，统一为“记录中心”。

但清理只能在 `RCV2-32` 至 `RCV2-35` 前端实现阶段进行，本任务不改代码。

## 11. 后续测试计划

`RCV2-32` 至 `RCV2-35` 至少覆盖：

- Catalog 驱动 sport tabs。
- 无外部 CDN。
- 无“表现指数”文案。
- 无伪年度 mock 数据进入生产渲染。
- 五运动状态渲染。
- Candidate confirm/reject 按 API 状态显示。
- Validation Required 灰态。
- Rebuilding 保留旧数据。
- 响应式断点截图。
- 键盘与 aria 属性。
- 禁止前端计算 improvement、scope、confidence、history summary 或 axis direction。
