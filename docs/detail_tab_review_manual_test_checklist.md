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
| `tests/test_e2e_fatigue_review.py` | `pytest tests/test_e2e_fatigue_review.py -v` | ☐ |
| `tests/test_v8_8_switch_tab.py` | `pytest tests/test_v8_8_switch_tab.py -v`(V8.8 全局 switchTab 行为未变) | ☐ |
| `tests/test_v9_0_detail_tab_review.py` | `pytest tests/test_v9_0_detail_tab_review.py -v`(本次新增) | ☐ |
| `tests/test_fatigue_review_e2e_contract.py` | `pytest tests/test_fatigue_review_e2e_contract.py -v` | ☐ |
| 既有雷达 Modal 测试 | `pytest tests/test_radar_insight_integration.py -v`(不受影响) | ☐ |

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
