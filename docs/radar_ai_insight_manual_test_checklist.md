# 雷达图 AI 洞察 手工测试清单 (P2-5 ~ P2-10)

> **版本**:2026-06-02(Modal 化升级)
> **适用版本**:雷达图 AI 洞察 P1 完整 + P2-1~P2-4 测试套件 + Modal 弹窗升级 (commit `d0e50a0` 后续)
> **对齐契约**:fit-arch-contrac §5.4(前端只传控制参数 / 阅后即焚 / 独立 sentinel)+ §5.6.2 七条铁律
> **核心目的**:在自动化测试覆盖之外,补充真实 pywebview + 真实 LLM + 真实 DB 下的端到端验收

---

## 0. 前置条件

### 0.1 环境
- [ ] App 正在运行(`python main.py` 已启动 pywebview)
- [ ] LLM 网关可连通(本地 OpenClaw / 远程 API 均可)
- [ ] 数据库 `~/.fitvault/user_profile.db` 存在且有数据

### 0.2 数据准备
- [ ] 当前用户至少有 **30 天** 活动数据(90 天最佳,可触发完整 5 sport_type 流程)
- [ ] 至少 5 个 sport_type 中各有 ≥ 1 条活动(running / trail_running / hiking / cycling / swimming)
- [ ] 至少 1 个 sport_type 数据**不足 90 天**(用于 P2-8 降级测试)

### 0.3 准备工具
- [ ] 打开 pywebview DevTools(`F12` 或右键 → Inspect)
- [ ] Console 标签页保留,准备看 `_radarInsightData` / `_clearRadarInsight` 调用日志
- [ ] Network 标签页保留,准备看 LLM 请求 / 响应
- [ ] 准备截图工具,记录每个测试的最终结果

---

## 1. P2-5:5 个 sport_type 切换 + AI 洞察

### 1.1 测试目标
验证 **5 个 sport_type(running / trail_running / hiking / cycling / swimming)** 都能正常触发 AI 洞察,各自返回不同的 radar_insight 内容(对齐契约 §5.4 规则 1:前端只传 sport_type,后端独立生成 snapshot)。

### 1.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 启动 app,进入 **profile Tab** | "🕸️ 运动能力"区域可见,5 个 sport tab + "✨ AI 洞察"按钮 |  |
| 2 | 当前 sport = running,点击 **✨ AI 洞察** | 按钮变 disabled + 显示 spinner + "解读中..." |  |
| 3 | 等待 3-10 秒(LLM 响应) | 面板展开,显示 running 的雷达洞察(summary / 6 维度 / 训练建议) |  |
| 4 | 检查面板内容 | `summary` 含"跑步"或"耐力"关键词;`weakest_dim` 是 6 维度 key 之一;`training_advice` 有内容 |  |
| 5 | 点击 **越野跑** tab,再点 **✨ AI 洞察** | 按钮再次变 loading(loading 守门验证:再次点击只触发一次) |  |
| 6 | 等待响应 | 面板更新,显示 trail_running 的洞察,内容应**不同于** running(中文标签/维度侧重点) |  |
| 7 | 重复步骤 5-6,依次测试 **徒步 / 骑行 / 游泳** | 5 个 sport_type 都返回各自的洞察 |  |
| 8 | 检查 DevTools Console | 看到 5 次 `__RADAR_INSIGHT__` 请求,sport_type 参数依次为 running / trail_running / hiking / cycling / swimming |  |
| 9 | 检查 DevTools Network | 5 次 LLM 请求,每次的 system prompt 含对应 sport_cn("跑步" / "越野跑" / "徒步" / "骑行" / "游泳") |  |

### 1.3 验收准则

- [ ] **AC-1**:5 个 sport_type 都返回 `ok: true` 响应
- [ ] **AC-2**:5 个响应的 `sport_type` 字段与点击时一致
- [ ] **AC-3**:5 个响应的 `radar_insight.summary` 至少有 1 处中文体育术语差异(说明是不同维度解读,而非复用同一 cache)
- [ ] **AC-4**:每次点击只触发 1 次 LLM 请求(loading 守门生效)
- [ ] **AC-5**:面板 6 类 CSS 样式全部生效(summary 紫色 / dim-list grid / advice 上分隔线 / disclaimer 60% 透明)

---

## 2. P2-6:切 Tab → 切回,弹窗应关闭并清空(_clearRadarInsight 触发点 2)

### 2.1 测试目标
验证 §5.4 规则 6(阅后即焚):**切 Tab 时** AI 洞察弹窗必须关闭并清空,避免跨页面残留。
> **Modal 化变更**(2026-06-02):弹窗已从内联 `<div id="radar-ai-insight-panel">` 升级为 `<div id="radar-ai-insight-modal">` Modal 容器。切 Tab 行为从"隐藏内联面板"升级为"关闭弹窗 + 清空 DOM + `_radarInsightModalOpen = false`"。

### 2.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 在 profile Tab 触发 AI 洞察,等待弹窗完整显示 | 弹窗可见,内容完整(summary / 6 维度 / 建议 / 免责) |  |
| 2 | 点击 **trace Tab** (轨迹 Tab) | 整个 profile 区域隐藏;**不**进入 trace(应在 tab 切换) |  |
| 3 | 切回 **profile Tab** | profile 区域重新显示 |  |
| 4 | 检查 AI 洞察弹窗 | **弹窗已关闭**(`#radar-ai-insight-modal.hidden === true`、body `innerHTML === ""`、`_radarInsightModalOpen === false`) |  |
| 5 | 重新点击 **✨ AI 洞察** | 正常触发,弹窗重新弹出(新数据,不是旧缓存) |  |
| 6 | DevTools Console | 看到 `_clearRadarInsight()` 被调用(`switchTab` 末尾) |  |
| 7 | 重复:settings Tab → profile Tab | 同样关闭 + 清空 |  |
| 8 | 重复:sport_hub Tab → profile Tab | 同样关闭 + 清空 |  |

### 2.3 验收准则

- [ ] **AC-1**:切 Tab 后,`#radar-ai-insight-modal` 的 `hidden` 属性为 `true`
- [ ] **AC-2**:切 Tab 后,`#radar-ai-insight-modal-body` 的 `innerHTML` 为 `""`(空字符串)
- [ ] **AC-3**:切 Tab 后,`_radarInsightData === null`
- [ ] **AC-4**:切 Tab 后,`_radarInsightModalOpen === false`
- [ ] **AC-5**:从任意 Tab 切回 profile,弹窗都保持关闭(一致性)
- [ ] **AC-6**:DevTools Console 出现 `_clearRadarInsight` 调用日志(如果未启用可跳过此条)

---

## 3. P2-7:模拟 LLM 异常,验证错误显示

### 3.1 测试目标
验证 LLM 失败时弹窗显示错误信息,**不卡死按钮**,用户可以重试。
> **Modal 化变更**(2026-06-02):错误容器从内联 `.radar-ai-panel.error` 升级为弹窗内 `.radar-ai-modal.error`。其余错误语义不变。

### 3.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 在 profile Tab 触发 AI 洞察,确认正常流程 | 弹窗正常显示 |  |
| 2 | **方法 A - 关闭 LLM**:关闭本地 LLM 服务(或将 `api_url` 改成不可达地址) | 配置生效 |  |
| 3 | **方法 B - 网络断开**:临时断网(wifi 关闭 / 网线拔掉) | 网络中断 |  |
| 4 | 选择任一 sport_type,点击 **✨ AI 洞察** | 按钮变 loading,等待 30 秒(LLM 超时) |  |
| 5 | LLM 失败后 | 按钮**恢复 enabled**(不再 disabled) |  |
| 6 | 弹窗显示 | 弹窗自动弹出 + 红色 error 容器(`.radar-ai-modal.error`),含 "⚠️ ..." 提示 |  |
| 7 | 检查错误内容 | 错误信息含"AI 洞察请求失败"或"JSON 解析失败"或"LLM 未返回内容" |  |
| 8 | 点击弹窗 ✕ 关闭(或遮罩 / ESC) | 弹窗关闭,`_radarInsightData === null` |  |
| 9 | 重新打开 LLM / 网络,再次点击 | 正常恢复,弹窗显示完整洞察 |  |
| 10 | DevTools Console | 看到 `console.error('onRadarAiInsight failed', e)` 调用 |  |

### 3.3 验收准则

- [ ] **AC-1**:LLM 失败后,按钮 `disabled === false`(可再次点击)
- [ ] **AC-2**:LLM 失败后,弹窗自动弹出 + body 内显示 `.radar-ai-modal.error` 红框
- [ ] **AC-3**:错误信息可读(`⚠️` 符号 + 简短描述)
- [ ] **AC-4**:**不**出现白屏 / 未捕获 promise rejection
- [ ] **AC-5**:再次点击可正常重试(状态机可恢复)
- [ ] **AC-6**:DevTools Console 记录了具体错误堆栈
- [ ] **AC-7**:错误弹窗可通过 ✕ / 遮罩 / ESC 三种方式关闭,且关闭后状态机干净

### 3.4 降级路径(§5.4 规则 5 部分实现)
> ⚠️ **已知设计**:在降级路径(空 sport_type / 无 metrics)下,`_chat_messages` **不会**被清空,session 也不会刷新。仅在 LLM 调用后才清空 + 刷新。详见 P2-4 测试文件 docstring。此为 P3 修复项。

---

## 4. P2-8:无 90 天数据,验证降级提示

### 4.1 测试目标
验证当某 sport_type **没有 90 天活动数据**时,后端走降级路径,直接返回 `empty_radar_insight("当前运动类型暂无 90 天数据")`,**不**调 LLM,响应快(< 100ms)。

### 4.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 准备:在 DB 中给某 sport_type(推荐 hiking)只插入 1-2 条活动(< 30 天) | DB 修改完成 |  |
| 2 | 重启 app,进入 profile Tab | 正常加载 |  |
| 3 | 切换到 hiking tab | 雷达图正常显示(基于 1-2 条数据) |  |
| 4 | 点击 **✨ AI 洞察** | 按钮 loading 极短(几乎瞬间) |  |
| 5 | 面板显示 | 红色 error 容器,错误信息含"暂无 90 天数据" |  |
| 6 | 检查 DevTools Network | **没有** LLM 请求(降级路径短路) |  |
| 7 | 切到其他 sport_type(running,有数据),点击 AI 洞察 | 正常返回完整洞察(对比) |  |
| 8 | 切回 hiking | 面板清空(§5.4 规则 6 触发点 1) |  |
| 9 | 再次点击 hiking 的 AI 洞察 | 同样降级,响应稳定 |  |

### 4.3 验收准则

- [ ] **AC-1**:无 90 天数据的 sport_type 走降级,响应 < 500ms
- [ ] **AC-2**:降级响应 `radar_insight.error` 字段含"暂无 90 天数据"
- [ ] **AC-3**:DevTools Network **没有** `/v1/chat/completions` 请求
- [ ] **AC-4**:按钮恢复 enabled(不卡死)
- [ ] **AC-5**:有数据 / 无数据 两种 sport_type 切换时,响应行为一致(都立即返回,只是内容不同)

---

## 5. P2-9:切 sport_type,弹窗应关闭并清空(_clearRadarInsight 触发点 1)

### 5.1 测试目标
验证 §5.4 规则 6(阅后即焚):**切 sport_type** 时,AI 洞察弹窗必须关闭并清空,避免跨 sport 残留。
> **Modal 化变更**(2026-06-02):切 sport_type 行为从"隐藏内联面板"升级为"关闭弹窗 + 清空 DOM + `_radarInsightModalOpen = false`"。

### 5.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 在 profile Tab,切到 running,触发 AI 洞察,等待弹窗显示 | running 的洞察完整显示 |  |
| 2 | 切到 **trail_running** tab | 雷达图重新渲染(基于 trail_running 数据) |  |
| 3 | 检查 AI 洞察弹窗 | **弹窗已关闭**(`hidden === true`、body `innerHTML === ""`、`_radarInsightModalOpen === false`) |  |
| 4 | 点击 **✨ AI 洞察** | 弹窗弹出,显示 trail_running 的洞察(与 running **内容不同**) |  |
| 5 | 切到 **cycling**,再切回 **trail_running** | 弹窗关闭 + 清空(再次切回时弹窗仍为关闭) |  |
| 6 | 5 个 sport_type 依次循环切 1 圈 | 每次切都关闭 + 清空,无残留 |  |
| 7 | DevTools Console | 看到 `_clearRadarInsight()` 被调用(`switchRadarSportType` 末尾) |  |

### 5.3 验收准则

- [ ] **AC-1**:切 sport_type 后,`#radar-ai-insight-modal.hidden === true`
- [ ] **AC-2**:切 sport_type 后,`#radar-ai-insight-modal-body.innerHTML === ""`
- [ ] **AC-3**:切 sport_type 后,`_radarInsightData === null`
- [ ] **AC-4**:切 sport_type 后,`_radarInsightModalOpen === false`
- [ ] **AC-5**:切回原 sport_type 时,弹窗不会"恢复"旧数据(必须重新点击)
- [ ] **AC-6**:5 个 sport_type 任意切换都触发关闭 + 清空(覆盖率 100%)
- [ ] **AC-7**:每次切换 + 点击的组合,弹窗可正常显示新数据

---

## 5bis. P2-10:Modal 弹窗 UX 验收(2026-06-02 Modal 化新增)

### 5bis.1 测试目标
验证 Modal 弹窗的 **3 种关闭方式**、**不挤压活动列表**、**重开能正常显示新数据**,且与全局快捷键 / 事件冒泡不冲突。  
> **背景**:P2-6 / P2-7 / P2-9 仅验证 `_clearRadarInsight` 状态机,P2-10 验证 Modal 容器本身的 UX 完整性(遮罩 / ESC / 居中 / 滚动 / 不挤压布局)。

### 5bis.2 测试步骤

| # | 操作 | 期望 | ✓/✗ |
|---|---|---|---|
| 1 | 在 profile Tab 触发 AI 洞察,等待弹窗显示 | 弹窗居中,半透明遮罩(`.radar-ai-modal-backdrop`) |  |
| 2 | 检查 `.profile-radar-card` 高度 | 高度**未增加**(与未触发时一致) |  |
| 3 | 检查 `.profile-bottom-workspace`(活动列表 / 成绩记录 / 荣誉墙 / 预留分析) | 布局未受挤压,无元素被遮挡 |  |
| 4 | 点击弹窗 ✕ 关闭按钮 | 弹窗关闭,`_radarInsightData === null`,body `innerHTML === ""` |  |
| 5 | 重新点击 AI 洞察,弹窗再次显示 | 弹窗正常弹出,显示新数据(无残留) |  |
| 6 | 点击遮罩(弹窗外黑色区域) | 弹窗关闭(同 ✕ 行为) |  |
| 7 | 重新打开弹窗,按 **ESC** 键 | 弹窗关闭,`_radarInsightModalOpen === false` |  |
| 8 | 重新打开弹窗,点击弹窗主体(非 ✕) | 弹窗**不关闭**(事件不冒泡) |  |
| 9 | 调整窗口分辨率到 1280×800,弹窗打开 | 弹窗仍居中,`max-width: 720px` 生效,无溢出 |  |
| 10 | 调整窗口分辨率到 1920×1080,弹窗打开 | 弹窗仍居中,内容宽度自适应 |  |
| 11 | 制造 > 80vh 高度内容(例如手工注入长 summary) | body 内出现垂直滚动条,弹窗头部 / 关闭按钮**不滚动** |  |
| 12 | 关闭弹窗后,重新触发 AI 洞察 | 弹窗内容为**新一次响应**(不是上一次缓存) |  |
| 13 | 弹窗打开时,按 Cesium 快捷键(在 Cesium 加载完成后) | Cesium 行为正常,不被 ESC 守卫拦截(因 `_radarInsightModalOpen` 守卫) |  |
| 14 | 弹窗打开时,按其他全局快捷键 | 行为正常,不冲突 |  |
| 15 | DevTools Elements 面板检查 DOM 结构 | `#radar-ai-insight-modal` 为 `position: fixed; z-index: 9999` |  |

### 5bis.3 验收准则

- [ ] **AC-1**:弹窗有 3 种关闭方式:`✕` 按钮 / 遮罩点击 / **ESC** 键,行为一致
- [ ] **AC-2**:点击弹窗主体(非关闭按钮)不会关闭弹窗
- [ ] **AC-3**:`.profile-radar-card` 高度恒定,**不**因洞察内容变化
- [ ] **AC-4**:`.profile-bottom-workspace` 完全不受影响(布局 / 滚动 / 高度)
- [ ] **AC-5**:1280×800 与 1920×1080 两种分辨率下弹窗均居中显示
- [ ] **AC-6**:弹窗内容超过 `max-height: 80vh` 时,body 内出现垂直滚动条
- [ ] **AC-7**:关闭弹窗后重新打开,内容为新一次 LLM 响应,无缓存残留
- [ ] **AC-8**:弹窗 `z-index: 9999` 足以覆盖 Cesium 地图层
- [ ] **AC-9**:ESC 守卫 `_radarInsightModalOpen` 不会拦截非弹窗场景下的 ESC 行为
- [ ] **AC-10**:a11y 属性齐备:`role="dialog"` / `aria-modal="true"` / `aria-labelledby="radar-ai-modal-title"`

### 5bis.4 视觉验收(仅记录,不强制自动化)
- [ ] 弹窗阴影 `box-shadow: 0 20px 60px rgba(0,0,0,0.5)` 在暗背景下层次清晰
- [ ] 弹窗圆角 `border-radius: 12px` 与雷达图卡片视觉协调
- [ ] 关闭按钮 hover 状态(`background: rgba(255,255,255,0.05); color: #f8fafc`)有视觉反馈
- [ ] 5 类内容(summary / dim-list / dim-item / advice / disclaimer)在弹窗 body 内排版与原内联面板一致

### 5bis.5 不挤压活动列表的硬性验收(§核心目的)
- [ ] 触发 AI 洞察前,记录 `.profile-bottom-workspace` 的 `getBoundingClientRect().height` 值为 **H1**
- [ ] 触发 AI 洞察后(弹窗打开),再次记录为 **H2**
- [ ] 断言 `Math.abs(H2 - H1) < 1`(浮点容差),即活动列表区域**未被弹窗挤压缩短**
- [ ] 关闭弹窗后,记录为 **H3**
- [ ] 断言 `Math.abs(H3 - H1) < 1`,即关闭后布局完全恢复

---

## 6. 横向验收(覆盖所有 5 个测试)

### 6.1 loading 守门(双击防护)
- [ ] 快速双击 **✨ AI 洞察** 按钮(间隔 < 100ms)
- [ ] DevTools Network 显示**只有 1 次** LLM 请求
- [ ] 第一次完成后,第二次点击的 loading 状态**没有**出现(因第一次已完成,状态已清)

### 6.2 spinner 关键帧
- [ ] 加载期间,spinner 元素有连续旋转动画
- [ ] 动画结束后,spinner 元素被清空(随面板 innerHTML 一起重置)

### 6.3 响应时间
- [ ] 正常 LLM 响应:3-10 秒
- [ ] 降级路径响应:< 500ms
- [ ] 错误路径响应:< 30 秒(LLM 超时)

### 6.4 多次连按同一按钮
- [ ] 5 次连按同一 sport_type 的 AI 洞察
- [ ] 每次都返回完整洞察(无残留 / 无堆积)
- [ ] 面板内容始终是最新一次的结果

### 6.5 边界场景
- [ ] 切 Tab → 切回 → 立即点 AI 洞察:正常
- [ ] 切 sport_type → 立即点 AI 洞察:正常
- [ ] 在 LLM 响应过程中切 Tab:不报错,响应被丢弃
- [ ] 在 LLM 响应过程中切 sport_type:不报错,响应被丢弃
- [ ] 关闭 app 过程中点 AI 洞察:不报错(pywebview 已关)

---

## 7. 自动化测试覆盖度(参考)

| 测试场景 | 自动化测试 | 手工测试(本清单) |
|---|---|---|
| 5 sport_type happy path | P2-1 / P2-2 / P2-4(部分) | **P2-5**(本清单) |
| 切 Tab 清空(弹窗关闭) | ❌ 无(需真实 UI) | **P2-6**(本清单) |
| LLM 异常显示(弹窗内) | P2-4 单元(降级 + 错误返回) | **P2-7**(本清单) |
| 无 90 天数据降级 | P2-4(降级路径覆盖) | **P2-8**(本清单) |
| 切 sport_type 清空(弹窗关闭) | ❌ 无(需真实 UI) | **P2-9**(本清单) |
| **Modal 弹窗 UX**(3 种关闭 / 不挤压 / 重开) | ❌ 无(纯前端 UI) | **P2-10**(本清单,2026-06-02 增) |
| loading 守门 | P2-4(同 sentinel 串行) | 6.1 |
| spinner 关键帧 | ❌ 无(需视觉验证) | 6.2 |
| 多次连按 | ❌ 无 | 6.4 |
| 边界场景 | ❌ 无 | 6.5 |

**结论**:本清单补足了 9 个自动化测试**无法**覆盖的真实 UI 场景(含 2026-06-02 增补的 P2-10 Modal 弹窗 UX)。每次大改雷达图前端,必须**完整**走一遍。

---

## 8. 测试报告模板

```
测试日期: 2026-XX-XX
测试环境: macOS 14.x / Python 3.11 / pywebview 5.x
LLM: OpenClaw 本地 / OpenAI GPT-4o
DB: ~/.fitvault/user_profile.db (X 条活动)
P1 commit: <hash>
P2 commit: <hash>

| 场景 | 步骤 | 状态 | 备注 |
|---|---|---|---|
| P2-5 5 sport_type | 9 步 | ✅/❌ | |
| P2-6 切 Tab 弹窗关闭 | 8 步 | ✅/❌ | |
| P2-7 LLM 异常(弹窗内) | 10 步 | ✅/❌ | |
| P2-8 无 90 天数据 | 9 步 | ✅/❌ | |
| P2-9 切 sport 弹窗关闭 | 7 步 | ✅/❌ | |
| P2-10 Modal UX(2026-06-02 增) | 15 步 | ✅/❌ | |
| 6.1 loading 守门 | 3 步 | ✅/❌ | |
| 6.2 spinner 关键帧 | 2 步 | ✅/❌ | |
| 6.3 响应时间 | 3 项 | ✅/❌ | |
| 6.4 多次连按 | 3 步 | ✅/❌ | |
| 6.5 边界场景 | 5 项 | ✅/❌ | |

总状态: X / 11 通过
发现问题: <列出 bug 与复现步骤>
```

---

## 9. 相关引用

- 设计文档:`/Users/fanglei/.qclaw/workspace-agent-823b6b76/radar_ai_insight_design_20260601.md` §七 P2-5~P2-9 + P2-10(Modal 化 2026-06-02 增补)
- 全局契约:`/Users/fanglei/应用开发/AI track/.trae/rules/fit-arch-contrac.md` §5.4
- 前端实现:`/Users/fanglei/应用开发/AI track/track.html` 1682-1744 (Modal CSS 体系,5 类内部样式 + .radar-ai-modal) / 8330-8340 (Modal 容器 HTML) / 2880-2961 (状态层 + `_clearRadarInsight` / `openRadarAiInsightModal` / `closeRadarAiInsightModal` / ESC 监听 / `_renderRadarInsightModal`)
- 后端 sentinel:`/Users/fanglei/应用开发/AI track/main.py` 2704 (`RADAR_INSIGHT` 常量) / 3165-3193 (call_llm 分支)
- 自动化测试:`/Users/fanglei/应用开发/AI track/test_radar_insight_integration.py`

---

> **维护说明**:本清单是雷达图 AI 洞察 UI 行为的"人类可执行规范"。每次修改前端或后端 sentinel 流程,需同步更新本清单。
