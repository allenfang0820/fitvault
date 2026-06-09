# 详情 Tab 化 + 复盘 AI 洞察 Modal 化 手工测试清单

> Version: V9.0 / 2026-Q2
> 适用版本:脉图 v9.0+
> 契约依据:`/Users/fanglei/应用开发/AI track/ARCHITECTURE.md` + `.trae/rules/fit-arch-contrac.md`

---

## 0. 测试环境准备

| 项 | 要求 |
|---|---|
| 启动方式 | `python main.py`(或开发模式 `python main.py --debug`) |
| 数据 | 至少 5 个不同 sport_type 的活动记录:`running` / `trail_running` / `hiking` / `cycling` / `swimming` |
| LLM 配置 | 已配置可用 LLM(OpenAI / Claude / Gemini / OpenRouter 任一) |
| 浏览器控制台 | 打开 DevTools,准备查看 `console.log` 与 Network |

---

## 1. 基础功能验收(必过)

### 1.1 详情 Modal 打开与 Tab 切换

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-001 | 在活动列表点击任意一条活动 | 详情 Modal 打开,**默认显示「概览」Tab**(紫色下划线高亮) | ☐ |
| FR-TC-002 | 检查 Modal head 区域 | 显示「概览」「复盘」两个 Tab 按钮,**无「进入复盘」独立按钮** | ☐ |
| FR-TC-003 | 概览 Tab 顶部 | 显示活动标题、副标题(日期 · 运动类型 · 地区) | ☐ |
| FR-TC-004 | 概览 Tab 主体 | 显示活动总结指标 + 圈速统计表 + 轨迹缩略图 | ☐ |
| FR-TC-005 | 点击「复盘」Tab | Tab 切换,概览 Tab 内容消失,复盘 Tab 内容出现 | ☐ |
| FR-TC-006 | 复盘 Tab 头部 | 显示「🔍 运动复盘」+ 副标题(加载中/已加载)+「🤖 生成 AI 洞察」按钮 | ☐ |
| FR-TC-007 | 复盘 Tab 主体 | 显示 8 个 metric cards(心率漂移/解耦率/Bonk/崩溃事件/运动效率/耐久/步频稳定/训练负荷) | ☐ |
| FR-TC-008 | 复盘 Tab 主体 | 显示 ECharts 三层图(效率·坡度·海拔)或空态占位卡 | ☐ |
| FR-TC-009 | 复盘 → 概览 → 复盘 | 复盘 Tab 不再触发 API 调用(已 lazy load) | ☐ |

### 1.1.1 P4 复盘页面结构

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009A | 切到复盘 Tab | 顶部出现“后端权威快照”摘要带,含数据来源、距离轴、事件/疲劳带状态 | ☐ |
| FR-TC-009B | 查看复盘指标 | 指标分为“核心状态”和“能力与负荷”两组,共 8 张卡 | ☐ |
| FR-TC-009C | 查看主图 | 主图区标题为“疲劳带 · 事件 · 曲线”,图例包含心率/速度/GAP/疲劳带/事件 | ☐ |
| FR-TC-009D | 查看右侧信息列 | 右侧显示上下文标签、关键事件、建议和 disclaimer | ☐ |
| FR-TC-009E | 缩窄窗口 | 右侧信息列下移为单列,无文字重叠或按钮溢出 | ☐ |

### 1.1.2 P7.0 复盘分析驾驶舱设计边界

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009F | 检查活动详情顶部 | 活动标题、时间、设备、路线等信息保持现有详情 Modal 设计,未按草图另造顶部全局头部 | ☐ |
| FR-TC-009G | 检查详情 Tab | 现有 Tab 系统保持不变;项目“复盘”Tab 被视为草图“分析”页 | ☐ |
| FR-TC-009H | 对照草图右侧功能按钮 | 首页、活动、日历等全局导航按钮未出现在复盘 Tab 本阶段实现范围 | ☐ |
| FR-TC-009I | 对照草图顶部全局动作 | 分享、导出等草图全局动作区未被新增到本阶段复盘 Tab | ☐ |
| FR-TC-009J | 检查复盘 Tab AI 入口 | AI 按钮仍为 P6.1 冻结态:置灰、无 onclick、点击不触发 `call_llm` | ☐ |

### 1.1.3 P7.1 复盘 Tab 信息架构稿

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009K | 检查 P7.1 信息架构文档 | 复盘 Tab 信息顺序固定为标题状态行、摘要带、核心状态、能力负荷、主图、事件/疲劳、上下文建议、disclaimer | ☐ |
| FR-TC-009L | 检查字段来源矩阵 | 每个 UI 区块均有明确后端字段来源,且标注禁止前端推导 | ☐ |
| FR-TC-009M | 检查空态策略 | code 非 0、data 为空、metrics 缺失、距离轴为空、事件/疲劳区为空、建议为空均有处理策略 | ☐ |
| FR-TC-009N | 检查响应式骨架 | 桌面、中等宽度、窄屏均有布局策略,长文本/长数值不得重叠或溢出 | ☐ |
| FR-TC-009O | 检查 P7.1 范围 | P7.1 不改生产 UI、不改接口、不改算法、不接 AI、不修改数据库 | ☐ |

### 1.1.4 P7.2 顶部分析摘要带

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009P | 进入复盘 Tab | 复盘 Tab 内部顶部显示分析摘要带,且不替代活动详情 Modal 顶部 | ☐ |
| FR-TC-009Q | 查看摘要带状态标签 | 显示数据源、距离轴、曲线、风险、事件/疲劳区间、AI 待开放状态 | ☐ |
| FR-TC-009R | 后端 `curves.distance = []` | 摘要带显示距离轴缺失,主图保持空态,不补算距离轴 | ☐ |
| FR-TC-009S | 后端事件/疲劳区间为空 | 摘要带显示事件 0、疲劳带 0,事件/区间区块为空态 | ☐ |
| FR-TC-009T | 检查 AI 入口 | AI 按钮和摘要带 AI 状态均为待开放,不触发 `call_llm` | ☐ |
| FR-TC-009U | 缩窄窗口 | 摘要带状态标签自然换行,无文字重叠、按钮溢出或全局导航出现 | ☐ |

### 1.1.5 P7.3 核心指标驾驶舱

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009V | 查看核心状态区 | 心率漂移、解耦率、Bonk 风险、崩溃事件 4 张卡存在且层级清晰 | ☐ |
| FR-TC-009W | 查看能力与负荷区 | 运动效率、耐久指数、步频稳定性、训练负荷 4 张卡存在且层级清晰 | ☐ |
| FR-TC-009X | 检查每张指标卡 | 每张卡都有主值、状态标签、解释或空态文案 | ☐ |
| FR-TC-009Y | mock `metrics = {}` | 8 张卡均显示数据不足/设备未记录/待接入等空态,不补算 | ☐ |
| FR-TC-009Z | 静态检查渲染函数 | `_renderFatigueReviewMetrics` 只消费 `metrics`,不读取 curves/points/DOM 推导指标 | ☐ |
| FR-TC-009AA | 缩窄窗口 | 指标卡自动换行,无文字重叠、溢出或布局跳动 | ☐ |
| FR-TC-009AB | 检查 AI 入口 | AI 按钮仍置灰且无 onclick,不触发 `call_llm` | ☐ |

### 1.1.6 P7.4 主图容器与图例

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009AC | 查看主图标题 | 显示“疲劳带 · 事件 · 曲线”,并有 X 轴来自后端 `curves.distance` 的说明 | ☐ |
| FR-TC-009AD | 查看主图边界说明 | 显示曲线来自 `data.curves`、疲劳带来自 `data.fatigue_zones`、事件来自 `data.collapse_events` | ☐ |
| FR-TC-009AE | 查看图例 | 图例能区分心率、速度、GAP、疲劳带、事件 | ☐ |
| FR-TC-009AF | 后端 `curves.distance = []` | 主图显示“后端未返回权威距离轴”空态,不补算距离轴 | ☐ |
| FR-TC-009AG | 后端 `fatigue_zones = []` | 不画疲劳背景带,摘要/侧栏显示暂无疲劳区间状态 | ☐ |
| FR-TC-009AH | 后端 `collapse_events = []` | 不画事件标记,摘要/侧栏显示暂无关键事件状态 | ☐ |
| FR-TC-009AI | 缩窄窗口 | 图例自然换行,不遮挡图表、不溢出 | ☐ |
| FR-TC-009AJ | 检查 AI 入口 | AI 按钮仍置灰且无 onclick,不触发 `call_llm` | ☐ |

### 1.1.7 P7.5 事件与疲劳区间说明

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009AK | 查看关键事件面板 | 面板说明事件来自 `data.collapse_events`,位置使用 `trigger_km` | ☐ |
| FR-TC-009AL | 查看疲劳区间面板 | 面板说明疲劳区间来自 `data.fatigue_zones`,区间使用 `start_km / end_km` | ☐ |
| FR-TC-009AM | 后端 `collapse_events = []` | 关键事件面板显示暂无关键事件,主图不画事件标记 | ☐ |
| FR-TC-009AN | 后端 `fatigue_zones = []` | 疲劳区间面板显示暂无疲劳区间,主图不画疲劳背景带 | ☐ |
| FR-TC-009AO | 后端返回事件 | 事件卡显示 type、trigger_km、description,不从曲线推导位置 | ☐ |
| FR-TC-009AP | 后端返回疲劳区间 | 区间卡显示 level、start_km、end_km、reason/description,不从曲线推导区间 | ☐ |
| FR-TC-009AQ | 缩窄窗口 | 事件卡和区间卡文本自然换行,无重叠或溢出 | ☐ |
| FR-TC-009AR | 检查 AI 入口 | AI 按钮仍置灰且无 onclick,不触发 `call_llm` | ☐ |

### 1.1.8 P7.6 建议与上下文侧栏

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009AS | 查看上下文面板 | 面板说明上下文来自 `data.context_tags`,不从活动标题、设备或 DOM 推导 | ☐ |
| FR-TC-009AT | 后端 `context_tags = {}` | 上下文面板显示空态,不从其他字段补标签 | ☐ |
| FR-TC-009AU | 查看建议面板 | 面板说明建议来自 `data.advice`,免责声明来自 `data.disclaimer` | ☐ |
| FR-TC-009AV | 后端 `advice = ""` | 建议面板显示“建议待接入”,不从 metrics/curves 生成建议 | ☐ |
| FR-TC-009AW | 后端 `disclaimer` 缺失 | 前端使用固定兜底免责声明,不抛错 | ☐ |
| FR-TC-009AX | 缩窄窗口 | 上下文标签、建议和免责声明自然换行,无重叠或溢出 | ☐ |
| FR-TC-009AY | 检查 AI 入口 | AI 按钮仍置灰且无 onclick,不触发 `call_llm` | ☐ |

### 1.1.9 P7.7 响应式与可读性检查

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009AZ | 桌面宽度查看复盘 Tab | 主图 + 侧栏布局稳定,各区块无重叠 | ☐ |
| FR-TC-009BA | 中等宽度查看复盘 Tab | 侧栏下移,主图标题和图例自然换行 | ☐ |
| FR-TC-009BB | 窄屏查看复盘 Tab | 指标卡 2 列或合理换行,图例不遮挡图表 | ☐ |
| FR-TC-009BC | 小屏查看复盘 Tab | 指标卡单列,AI 冻结按钮不溢出 | ☐ |
| FR-TC-009BD | 长 disclaimer / advice | 文本自然换行,不撑破容器 | ☐ |
| FR-TC-009BE | 长事件/疲劳区间说明 | 事件卡和区间卡文本可读,无横向溢出 | ☐ |
| FR-TC-009BF | 静态检查 CSS | 无 viewport 字体缩放,无负 letter-spacing | ☐ |
| FR-TC-009BG | 检查 AI 入口 | AI 按钮仍置灰且无 onclick,不触发 `call_llm` | ☐ |

### 1.1.10 P7.8 视觉回归测试与手工清单

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-009BH | 对照 P7.1 信息架构查看复盘 Tab | 区块顺序保持为标题状态行、摘要带、核心状态、能力负荷、主图、上下文/事件/疲劳区间/建议、disclaimer | ☐ |
| FR-TC-009BI | 对照设计草图查看复盘 Tab | 仅实现草图“分析”页的信息层级,未新增右侧首页/活动/日历等全局导航 | ☐ |
| FR-TC-009BJ | 检查顶部活动信息和 Tab | 活动详情顶部与概览/复盘 Tab 保持现有设计,复盘不替换为独立页面 | ☐ |
| FR-TC-009BK | 检查草图全局动作 | 复盘 Tab 未新增分享、导出、外部跳转或非本阶段按钮 | ☐ |
| FR-TC-009BL | 桌面 / 中宽 / 窄屏 / 小屏各查看一次 | 摘要带、8 张指标卡、主图图例、侧栏面板均不重叠、不溢出 | ☐ |
| FR-TC-009BM | 使用长 advice / disclaimer / context tag / 事件描述 | 文本可读,必要时换行或截断,不撑破容器 | ☐ |
| FR-TC-009BN | mock 空 metrics / 空 distance / 空事件 / 空疲劳区间 | 各区块显示空态,不从前端补算事实字段 | ☐ |
| FR-TC-009BO | 静态检查视觉回归门禁 | P7.8 测试覆盖区块顺序、草图边界、AI 冻结和响应式可读性 | ☐ |
| FR-TC-009BP | 检查 AI 入口 | AI 按钮仍 disabled、`aria-disabled="true"`、无 onclick、不触发 `call_llm` | ☐ |

### 1.2 返回路径

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-010 | 在复盘 Tab 按 Modal 头部「← 返回活动列表」 | 详情 Modal 关闭,回到活动列表 | ☐ |
| FR-TC-011 | 重复打开同一活动 3 次 | 每次打开都默认激活「概览」Tab,无残留 Tab 状态 | ☐ |
| FR-TC-012 | 打开 A 活动 → 切到复盘 → 关闭 → 打开 B 活动 | B 活动默认仍显示「概览」Tab | ☐ |

### 1.3 3D 入口(由概览 Tab 承担)

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-020 | 概览 Tab 点击轨迹缩略图 | 跳转到 trace 面板,加载 3D 渲染 | ☐ |
| FR-TC-021 | 复盘 Tab 顶部检查 | **无「进入 3D 沉浸分析」按钮**(已删除) | ☐ |
| FR-TC-022 | 3D 跳回详情 | 显示「返回详情」FAB,点击后回到概览 Tab | ☐ |

---

## 2. AI 洞察 Modal 验收(必过)

### 2.1 打开与关闭

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-030 | 切到复盘 Tab,点击「🤖 生成 AI 洞察」 | **毛玻璃 Modal 弹出**,背景为详情 Modal 模糊态 | ☐ |
| FR-TC-031 | AI Modal 打开时检查 | Modal 内显示 4 sections:总评 / 维度评分 / 关键事件 / 改进建议 | ☐ |
| FR-TC-032 | AI Modal 打开时检查 | Modal 内显示底部 disclaimer | ☐ |
| FR-TC-033 | AI Modal 打开时点击 X 关闭按钮 | Modal 关闭,数据清空 | ☐ |
| FR-TC-034 | AI Modal 打开时点击 backdrop(非卡片区域) | Modal 关闭,数据清空 | ☐ |
| FR-TC-035 | AI Modal 打开时按 ESC 键 | Modal 关闭,数据清空 | ☐ |
| FR-TC-036 | AI Modal 关闭后,复盘 Tab 的 AI 按钮 | 文案回到「🤖 生成 AI 洞察」(非「重新生成」) | ☐ |

### 2.2 物理拦截 Tab 切换(关键 UX)

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-040 | AI Modal 打开时,点击「概览」Tab 按钮 | **Tab 按钮被拦截,无法切换**(无响应) | ☐ |
| FR-TC-041 | AI Modal 打开时,点击 Modal head 的「← 返回活动列表」 | 同样被拦截(Modal 在最上层) | ☐ |
| FR-TC-042 | AI Modal 打开时,点击 Modal head 的「×」 | 同样被拦截 | ☐ |
| FR-TC-043 | 上述拦截仅可通过 X / backdrop / ESC 解除 | Modal 关闭后,所有头部按钮恢复正常 | ☐ |

### 2.3 阅后即焚 3 触发点(契约 §5.6.2 规则 5)

| 触发点 | 触发动作 | 预期结果 | 通过 |
|---|---|---|---|
| ① 关闭 Modal | 点 X / backdrop / ESC | `_clearFatigueAiInsight` 被调用,数据清空 | ☐ |
| ② 切活动 | 关闭详情 → 打开另一活动 | AI 状态已清空,新活动默认「概览」Tab | ☐ |
| ③ 重新点击 | 复盘 Tab 再次点「🤖 生成 AI 洞察」 | 旧数据清空,新 loading → success 流程正常 | ☐ |
| 切 Tab 触发点 | N/A | **物理上不可能**(backdrop 全屏拦截),无需测试 | N/A |

### 2.4 Loading / Error / Empty 三态

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-050 | 点击 AI 按钮,观察 Modal 打开瞬间 | Modal 立即显示,内容为「⏳ AI 正在分析...」 | ☐ |
| FR-TC-051 | 等待 LLM 响应(~3-8s) | Modal 内容替换为 success 数据 | ☐ |
| FR-TC-052 | 断网状态下点击 AI 按钮 | Modal 显示错误态「❌ AI 洞察暂不可用:...」 | ☐ |
| FR-TC-053 | LLM 返回数据无 `summary` 字段 | Modal 显示空态「📭 数据不足,无法生成洞察」 | ☐ |

### 2.5 P6 AI 洞察边界

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-054 | 查看复盘 Tab AI 按钮 | 按钮置灰,文案为「AI 洞察待开放」 | ☐ |
| FR-TC-055 | 鼠标悬停 AI 按钮 | tooltip 说明「AI 洞察将在 UI 定稿后开放」 | ☐ |
| FR-TC-056 | 点击 AI 按钮 | 无响应,不弹 Modal,不触发 Network / pywebview `call_llm` | ☐ |
| FR-TC-057 | 静态检查按钮 HTML | `fr-ai-generate-btn` 含 `disabled` / `aria-disabled="true"`,且无 `onclick` | ☐ |
| FR-TC-058 | 后端能力检查 | P6 后端 sentinel 和 compact snapshot 测试仍通过,能力保留待 UI 定稿后开放 | ☐ |

---

## 3. 5 种运动类型回归(全过)

| sport_type | 活动示例 | 复盘 Tab 数据 | AI Modal 响应 | 通过 |
|---|---|---|---|---|
| `running` | 5km 慢跑 | metric 8 项 + 三层图 | AI 解读正常 | ☐ |
| `trail_running` | 20km 越野 | 含爬升/坡度数据 | AI 解读正常 | ☐ |
| `hiking` | 10km 徒步 | metric 8 项(HR 较低) | AI 解读正常 | ☐ |
| `cycling` | 30km 骑行 | 含功率数据 | AI 解读正常 | ☐ |
| `swimming` | 1500m 游泳 | metric 数据可能部分为空 | AI 解读正常 | ☐ |

---

## 4. 契约验收(必过)

### 4.1 §3 统一响应结构

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| `onFatigueReviewAiInsight` 使用 `res.code !== 0` | DevTools Network,模拟 `call_llm` 返回 `{code: 5001, msg: "..."}` 应进入 error 态 | ☐ |
| 不再使用 `res.ok !== true` | 静态 grep `track.html`,确认 `res.ok` 仅出现在雷达 Modal 等其他独立链路 | ☐ |

### 4.2 §六 shadow_diff 隔离

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| AI Modal 渲染前不出现 `shadow_diff` | DevTools,断点 `_renderFatigueReviewAiSuccess`,检查入参 | ☐ |
| Modal 渲染时 Modal body 不含 `shadow_diff` 字样 | DevTools Elements,搜索 modal body | ☐ |

### 4.2.1 P3 前端零推断

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| 复盘图表 X 轴来自后端 `data.curves.distance` | DevTools,断点 `openFatigueReview`,确认 `chartPayload.distance_curve === data.curves.distance` | ☐ |
| 前端不再包含 `_distanceFromSpeedTime` | 静态 grep `track.html`,确认无该函数和调用 | ☐ |
| 前端不按 `speed / total_distance_m` 重建距离 | 静态 grep `track.html`,确认无 `validSpeedSum`、`speed * 1s` 等距离轴推导逻辑 | ☐ |
| 后端未返回权威距离轴时展示空态 | mock `data.curves.distance = []`,复盘图表显示「复盘曲线数据不足」 | ☐ |
| fatigue zones / events 与曲线同源 | 图表背景带和事件图钉位置使用后端 `start_km/end_km/trigger_km`,不做前端换算 | ☐ |

### 4.3 §5.4 AI 边界

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| AI 洞察结果只存在前端内存 | 关闭 Modal 后 sessionStorage 不增加新键(仅 `fatigue_review_ai:*` 5min 缓存) | ☐ |
| 关闭 Modal 后复盘 Tab 无残留 AI 状态 | 关闭再打开,默认显示「点击「生成 AI 洞察」开始分析」 | ☐ |

### 4.4 §5.6.2 阅后即焚

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| 关闭 Modal → 数据清空 | DevTools,断点 `_clearFatigueAiInsight`,确认 `_fatigueAiInsightData = null` | ☐ |
| 切活动 → AI 状态已清空 | 流程同 §2.3 触发点 ② | ☐ |
| 重新点击 → 旧数据被覆盖 | 流程同 §2.3 触发点 ③ | ☐ |

### 4.5 §7.1 敏感字段脱敏

| 验收点 | 检查方式 | 通过 |
|---|---|---|
| Modal 内容不含 `api_key` | DevTools Elements,搜索 modal body | ☐ |
| AI prompt 不含明文密钥 | Network 面板,检查 `call_llm` 请求体 | ☐ |

---

## 5. 性能与体验(辅助)

| 用例 ID | 操作 | 预期结果 | 通过 |
|---|---|---|---|
| FR-TC-100 | 切到复盘 Tab 首次加载 | loading 占位 → 数据填入,总耗时 < 2s(本地 SQLite) | ☐ |
| FR-TC-101 | 复盘 → 概览 → 复盘 切换 | ECharts 容器 resize 正常,无白屏闪烁 | ☐ |
| FR-TC-102 | 关闭详情 Modal,1s 内重新打开 | 复盘 Tab 重新触发 lazy load(已重置 `_fatigueReviewTabLoaded`) | ☐ |
| FR-TC-103 | AI Modal 打开时滚动 Modal body | 滚动流畅,4 sections 完整可见 | ☐ |
| FR-TC-104 | AI Modal 打开时窗口缩小 | 卡片自适应宽度(720px max,100vw - 32px min) | ☐ |

---

## 6. 回归测试(必过)

| 测试项 | 命令 / 检查点 | 通过 |
|---|---|---|
| P5 质量门禁 | `pytest tests/test_fatigue_review_quality_gate.py -v` | ☐ |
| P6 AI 洞察 | `pytest tests/test_fatigue_review_ai_insight_p6.py -v` | ☐ |
| `tests/test_e2e_fatigue_review.py` | `pytest tests/test_e2e_fatigue_review.py -v` | ☐ |
| `tests/test_v8_8_switch_tab.py` | `pytest tests/test_v8_8_switch_tab.py -v`(V8.8 全局 switchTab 行为未变) | ☐ |
| `tests/test_v9_0_detail_tab_review.py` | `pytest tests/test_v9_0_detail_tab_review.py -v`(本次新增) | ☐ |
| `tests/test_fatigue_review_e2e_contract.py` | `pytest tests/test_fatigue_review_e2e_contract.py -v` | ☐ |
| 既有雷达 Modal 测试 | `pytest tests/test_radar_insight_integration.py -v`(不受影响) | ☐ |

### 6.1 P5 质量门禁覆盖点

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 前端零推断 | 不存在 `_distanceFromSpeedTime`、`speed/sum(speed)`、`speed * 1s`、`total_distance_m` 均分距离轴 | ☐ |
| 后端白名单 | `get_fatigue_review` snapshot 顶层与 `curves` 字段严格匹配契约 | ☐ |
| Forbidden 隔离 | 任意层级不含 `shadow_diff / diff / records / points / raw_records / track_points` | ☐ |
| 曲线同源 | 非空曲线长度与 `curves.distance` 一致 | ☐ |
| P4 UI 结构 | 摘要、核心状态、能力负荷、主图、上下文、事件、建议区均存在 | ☐ |
| AI 边界 | `__FATIGUE_REVIEW_INSIGHT__` 保留,前端只传 sentinel + sportType | ☐ |

### 6.2 P7 设计边界门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 详情顶部保持 | P7 不改活动详情顶部标题、时间、设备、路线和现有 Tab 容器 | ☐ |
| 草图范围限定 | 只吸收草图“分析”页中的复盘内容层级,不实现右侧全局导航和顶部分享/导出区 | ☐ |
| 前端零推断 | P7 任一 UI 改造不得从 speed/time/total_distance_m/points/DOM 推导事实字段 | ☐ |
| 后端白名单 | 指标、主图、事件、疲劳带、上下文和建议只读取 `get_fatigue_review` 白名单字段 | ☐ |
| 缺失字段处理 | 字段缺失或运动类型不适用时展示空态/弱化态/待接入,不得补算 | ☐ |
| AI 入口冻结 | UI 定稿前 `fr-ai-generate-btn` 仍 disabled、无 onclick、不触发 `call_llm` | ☐ |

### 6.3 P7.1 信息架构门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 区块顺序 | 信息架构固定复盘 Tab 8 个区块顺序,后续 UI 实现不得随意重排 | ☐ |
| 区块职责 | 每个区块都有用户可见内容、判断目的、后端字段来源、缺失态和交互边界 | ☐ |
| 字段矩阵 | 每个展示字段均映射到 `get_fatigue_review` 白名单字段或 API envelope 状态 | ☐ |
| 空态完整 | 错误态、空 data、空 metrics、空 `curves.distance`、空事件、空疲劳区间、空建议均有策略 | ☐ |
| 响应式骨架 | 桌面主图+侧栏、中宽下移、窄屏单列已形成文档基线 | ☐ |
| 范围冻结 | P7.1 只做文档规划,不修改 `track.html`、后端、契约 JSON 或 DB schema | ☐ |

### 6.4 P7.2 顶部分析摘要带门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 容器位置 | `fr-status-strip` 位于复盘 Tab 内部,在核心指标区之前,不改活动详情顶部 | ☐ |
| 状态完整 | 摘要带包含数据源、距离轴、曲线、风险、事件/疲劳区间、AI 待开放状态 | ☐ |
| 字段来源 | 摘要带只读取 `curves / metrics / fatigue_zones / collapse_events / sport_type / advice / disclaimer` | ☐ |
| 零推断 | 摘要带不使用 speed/time/total_distance_m/points/DOM 推导事实字段 | ☐ |
| AI 冻结 | `fr-ai-generate-btn` 仍 disabled、无 onclick,`fr-ai-status-pill` 显示 AI 待开放 | ☐ |
| 草图边界 | 未新增首页、活动、日历、分享、导出等草图全局动作 | ☐ |

### 6.5 P7.3 核心指标驾驶舱门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 8 卡保留 | 8 个既有主值 id 全部保留,不破坏渲染目标 | ☐ |
| 状态标签 | 8 张卡均有 `fr-*-status` 状态标签 | ☐ |
| 解释容器 | 8 张卡均有解释/空态文案容器 | ☐ |
| 字段来源 | 指标卡只读取 `data.metrics` 对应字段,崩溃事件只读后端事件摘要 | ☐ |
| 零推断 | 不从 speed/time/total_distance_m/points/DOM/curves 推导指标 | ☐ |
| 响应式 | 桌面多列、中宽换行、窄屏不重叠不溢出 | ☐ |
| AI 冻结 | P7.3 不开放 AI 入口,不触发 `call_llm` | ☐ |

### 6.6 P7.4 主图容器与图例门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 容器保留 | `fatigue-review-chart` 保留,新增/保留主图区标题、边界说明、图例和轴说明 | ☐ |
| X 轴边界 | 主图明确 `distance_curve = data.curves.distance`,不恢复 `_distanceFromSpeedTime` | ☐ |
| 字段来源 | 心率/速度/GAP 只读 `data.curves`,疲劳带只读 `data.fatigue_zones`,事件只读 `data.collapse_events` | ☐ |
| 空态 | 缺 `curves.distance` 时展示空态,不补算 | ☐ |
| 零推断 | 不用 speed/time/total_distance_m/points/DOM 重建距离轴或事件位置 | ☐ |
| 响应式 | 图例可换行,窄屏不遮挡图表、不溢出 | ☐ |
| AI 冻结 | P7.4 不开放 AI 入口,不触发 `call_llm` | ☐ |

### 6.7 P7.5 事件与疲劳区间说明门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 事件来源 | 关键事件面板只读取 `data.collapse_events`,位置使用 `trigger_km` | ☐ |
| 区间来源 | 疲劳区间面板只读取 `data.fatigue_zones`,位置使用 `start_km / end_km` | ☐ |
| 空态 | 空事件/空疲劳区间均展示空态,不补算、不伪造 | ☐ |
| 零推断 | 不从 speed/time/total_distance_m/points/DOM/curves 推导事件或区间 | ☐ |
| 图表同源 | 侧栏事件/区间与主图事件/疲劳带使用同一后端数组 | ☐ |
| 响应式 | 事件卡和区间卡窄屏不重叠不溢出 | ☐ |
| AI 冻结 | P7.5 不开放 AI 入口,不触发 `call_llm` | ☐ |

### 6.8 P7.6 建议与上下文侧栏门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 上下文来源 | 上下文标签只读取 `data.context_tags`,不从标题/设备/DOM 推导 | ☐ |
| 建议来源 | 建议只读取 `data.advice`,免责声明只读取 `data.disclaimer` 或固定兜底 | ☐ |
| 空态 | 空 context_tags 和空 advice 均展示空态,不补算、不生成 | ☐ |
| 零推断 | 不从 metrics/curves/collapse_events/fatigue_zones/points/DOM 生成建议 | ☐ |
| 响应式 | 标签、建议、免责声明窄屏不重叠不溢出 | ☐ |
| AI 冻结 | P7.6 不开放 AI 入口,不触发 `call_llm` | ☐ |

### 6.9 P7.7 响应式与可读性门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 中宽布局 | `max-width: 1100px` 下侧栏下移,主图标题和图例纵向排列 | ☐ |
| 窄屏布局 | `max-width: 720px` 下摘要带、图例、指标卡自然换行 | ☐ |
| 小屏布局 | `max-width: 480px` 下指标卡单列,AI 冻结按钮不溢出 | ☐ |
| 长文本 | 摘要、指标解释、事件、区间、建议、免责声明均有换行/截断策略 | ☐ |
| 图表稳定 | 主图容器有稳定高度,图例不遮挡图表 | ☐ |
| 字体约束 | 不使用 viewport 字体缩放,不使用负 letter-spacing | ☐ |
| 契约不变 | P7.7 不改变字段来源,不新增前端事实推导 | ☐ |
| AI 冻结 | P7.7 不开放 AI 入口,不触发 `call_llm` | ☐ |

### 6.10 P7.8 视觉回归测试与手工清单门禁

| 门禁 | 检查内容 | 通过 |
|---|---|---|
| 区块顺序 | 复盘 Tab 顺序锁定为摘要带、核心状态、能力负荷、主图、上下文、事件、疲劳区间、建议 | ☐ |
| 草图边界 | 不实现首页/活动/日历全局导航,不新增分享/导出动作 | ☐ |
| 顶部保持 | 活动详情顶部和现有 Tab 系统保持不变,复盘仍在详情 Modal 内 | ☐ |
| AI 冻结 | `fr-ai-generate-btn` disabled、`aria-disabled="true"`、无 onclick、不触发 `call_llm` | ☐ |
| 零推断 | 前端不从 speed/time/total_distance_m/points/DOM 推导距离、指标、事件或建议 | ☐ |
| 响应式兜底 | 桌面、中宽、窄屏、小屏和长文本场景都有手工验收项 | ☐ |
| 自动门禁 | `tests/test_fatigue_review_quality_gate.py` 和 `tests/test_v9_0_detail_tab_review.py` 覆盖 P7.8 视觉回归 | ☐ |

---

## 7. 已知限制与未来扩展

| 项 | 说明 |
|---|---|
| 概览 Tab 切到复盘 Tab | 第一次会触发 `get_fatigue_review` API;后续复用缓存(同一活动内) |
| AI Modal 嵌套层级 | 仅一层 Modal,不支持嵌套(避免 z-index 与 ESC 守卫冲突) |
| 移动端适配 | 当前 z-index 与 width 设计为桌面端,移动端需重新设计 |
| 国际化(i18n) | 文字硬编码中文,后续接入 i18n 时需提取文案 |

---

## 8. 验收签字

| 角色 | 姓名 | 日期 | 签字 |
|---|---|---|---|
| 测试执行 | __________ | __________ | __________ |
| 架构审查 | __________ | __________ | __________ |
| 业务方确认 | __________ | __________ | __________ |

---

## 9. 回归失败处理

如任何用例未通过:

1. **记录失败现场**:DevTools 截图 + `console.log` 全文 + 复现步骤
2. **定位代码位置**:对照本任务书第 5 节实施步骤,确认漏改 / 误改
3. **回退方案**:`git diff` 查看改动,若改动小可手工回退;若改动大,`git checkout track.html` 全量回退
4. **重新验收**:修复后重新跑本清单所有用例

> 严禁:不通知架构师私自修改契约字段 / 引入新依赖 / 修改后端代码
