# 脉图 (MaiTu) 全局架构契约 — fit-arch-contrac

> Canonical Architecture Contract
> Version: 2026-Q2
> 项目定位：本地 AI 运动外挂 (Local AI Sports Copilot)
> 适用范围：全局所有模块、所有接口、所有数据操作

---

## 一、项目定义

脉图不是平台，不是 SaaS，不是企业 BI。

脉图 = **一个运行在用户本地的 AI 运动外挂**。

核心闭环：
- 导入运动数据 → 建立可信运动档案 → 提供结构化 AI 解读 → 形成长期运动画像 → 为 AI 提供稳定语义上下文

---

## 二、数据流契约 (Data Flow Contract)

```
FIT / GPX
    ↓
fit_engine (FIT解析引擎, 保留 Garmin 原始语义)
    ↓
resolver   (语义解析层, 唯一语义翻译层)
    ↓
SQLite canonical DB (系统唯一可信数据层)
    ↓
ai_snapshot (AI 上下文压缩层)
    ↓
OpenClaw / AI Layer (解读层, 不写回 canonical)
    ↓
Narrative / Radar / Trend / Achievement
```

### 2.1 字段全链路可追溯

任何 UI 字段必须能追溯：`UI → DB → Resolver → FIT SDK`

严禁：
- 前端偷偷计算指标
- AI 偷偷生成数据
- resolver 无来源推断
- fallback 值长期污染 canonical 层

### 2.2 数据可信分层

| 层级 | 定义 | 来源 |
|---|---|---|
| fit_sdk | Garmin SDK 解析真实数据 | FIT 文件 |
| frontend_fallback | UI 临时推导数据 | 前端计算 |
| mock | 测试数据 | 测试生成 |
| synthetic | AI 生成数据 | AI 输出 |

canonical 层只接受 `fit_sdk` 可信数据。
Resolver 可存在降级逻辑，UI 可做展示 fallback，但 AI 不允许写回 canonical 数据。

---

## 三、统一响应结构契约 (Response Envelope Contract)

所有接口必须统一返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {},
  "traceId": "<hex12>"
}
```

过渡期兼容顶层 `ok`/`error` 字段。

### 3.1 全局错误码

| 错误码 | 含义 |
|---|---|
| 0 | 成功 |
| 1001 | 参数校验错误 |
| 1004 | 资源不存在 |
| 1401 | 高风险操作确认/鉴权失败 |
| 2001 | 不支持的文件类型 |
| 3001 | 外部服务错误 |
| 4001 | 文件或配置 IO 错误 |
| 5001 | 数据库错误 |
| 9001 | 内部系统错误 |

错误码原则：
- 全局唯一
- 可追踪
- 可分类
- 稳定长期存在

---

## 四、API 契约

### 4.1 传输层

`pywebview window.pywebview.api.*`

### 4.2 API 分类

| 分类 | 方法 |
|---|---|
| **config** | `get_config` `save_config` `get_llm_config` `save_llm_config`(已废弃) `test_llm_config` |
| **ai** | `call_llm` `sync_track_context` `reset_llm_session` `debug_snapshot` |
| **activity** | `get_activity_list_snapshot` `get_activity_list` `get_sport_hub_activity_page` `get_activity_detail` `get_activity_history` |
| **sync** | `sync_local_fit_files` `batch_import_tracks` `delete_activities` `api_force_rebuild_radar_data` |
| **profile** | `get_user_profile` `save_user_profile` `get_rolling_radar_metrics` `fetch_mcp_persona` `silent_fetch_mcp_persona` `startup_sync_check` `check_daily_sync_status` `get/set_test_bypass_daily_sync_limit` |
| **file** | `pick_and_parse_track` `parse_track_at_path` `select_directory` `save_text_file` |
| **diagnostics** | `notify_frontend_ready` `diagnose_watch_service` `check_first_run_status` |

### 4.3 高风险接口

以下接口必须具备鉴权/确认门禁：

| 接口 | 风险等级 |
|---|---|
| `delete_activities` | **critical** — 需要二次确认 token (格式: `DELETE:{count}`)，仅删除 TRACKS_DIR 内文件，越权路径拒绝 |
| `save_llm_config` | **high** — 已废弃，直接返回 1401 |
| `test_llm_config` | **medium** — LLM 网关连通性测试 |
| `sync_local_fit_files` | **high** — 全量扫描 TRACKS_DIR |
| `batch_import_tracks` | **high** — 有路径穿越/资源上限防护 |
| `api_force_rebuild_radar_data` | **high** — 全量雷达指标重建 |

---

## 五、AI 边界契约 (AI Boundary Contract)

### 5.1 AI 消费边界

AI 输入 **仅来自** `_ai_snapshot` (DB truth)。

前端计算值、UI fallback 值、`shadow_diff` 等 **不进入 AI 链路**。

### 5.2 AI 输出边界

AI 职责：解读、总结、分析、生成 narrative、生成 insight。

AI **不负责**：
- 修改原始数据
- 回写 metrics
- 生成结构化 canonical 字段
- 作为事实来源

### 5.3 AI Snapshot 白名单

Snapshot 必须：小、稳定、可解释、token 可控。

**禁止进入 Snapshot 的字段**：
- `shadow_diff`
- `shadow_diff_json`
- `diff`
- 任何 debug-only / audit-only 字段
- 全量 records 原始数据

### 5.4 功能区 AI 洞察模式

未来所有数据页面 / 功能区中的「AI洞察」按钮，必须遵循统一模式：

```text
frontend button
    ↓
call_llm(SENTINEL, sportType)
    ↓
backend canonical snapshot builder
    ↓
prompt builder
    ↓
OpenClaw / 外挂 LLM
    ↓
normalizer
    ↓
frontend renderer
```

强制规则：
- 前端只允许传递触发意图、必要 ID、运动类型等控制参数
- 前端禁止拼接 `points[]`、DOM 推导值、UI fallback 值作为 AI 事实输入
- 后端必须从 `_ai_snapshot`、DB truth、profile_backend、radar/trend 后端引擎输出中构建快照
- 每类功能区洞察必须使用独立 sentinel，禁止走普通聊天 prompt 路径
- 功能区 AI 洞察调用后必须清空 `_chat_messages` 并刷新 session，避免污染 AI 教练会话
- AI 洞察结果默认只存在前端内存，页面切换或数据切换后清空
- AI 洞察结果禁止写 DB、禁止进入 canonical、禁止进入 `ai_snapshots`

### 5.5 轨迹报告 v3 边界

轨迹报告升级必须遵循以下边界：

| 模块 | 数据来源 | 允许行为 | 禁止行为 |
|---|---|---|---|
| 运动数据快照 | `appState.activityMetrics` | 格式化展示后端权威字段 | 从 `points[]` 反推距离、时间、爬升、坡度、消耗 |
| 风险预警 | `__REPORT_RISK_ASSESSMENT__` → `_ai_snapshot` | 外挂 LLM 解读，前端临时渲染 | 前端拼 prompt、发送 `points[]`、写 DB |
| 坡度增强 | 后端 `compute_report_metrics()` / Resolver truth | 后端计算后入 DB 或 canonical API 透传 | 前端用 `gain_m / dist_km` 等公式生成权威指标 |
| 配速/补给 narrative | 已有 canonical 字段 + 展示规则 | 作为 narrative 展示 | 作为 canonical 指标写回 |

轨迹报告当前可依赖的 `activityMetrics` 字段包括：
- `dist_km`
- `gain_m`
- `max_alt_m`
- `avg_pace`
- `start_time`
- `min_alt_m`
- `total_descent_m`
- `up_count`
- `down_count`
- `max_single_climb_m`
- `difficulty_score`
- `calories`（存在时可展示）

轨迹报告当前不可作为前端 canonical 推导的字段包括：
- 平均坡度
- `maxSlope`
- `minSlope`
- `uphillPct`
- `downhillPct`

这些字段如需展示，必须由后端新增计算、迁移、入库或通过 canonical API 透传。

### 5.6 AI 洞察功能开发标准流程

> **本节是 §5.4 + §5.5 的**「开发执行规范」**。新增任何功能区 AI 洞察(雷达图 / 活动详情 / 训练计划 / ...)时,必须严格遵循本节定义的 7 条铁律与 P0/P1/P2 任务清单。**

#### 5.6.1 适用范围

每新增一个**功能区**的 AI 洞察按钮,不论后端 sentinel 是什么、前端放在哪个 Tab,均适用本节。

| 类别 | 现有 / 未来 | sentinel 命名 |
|---|---|---|
| 雷达图(已实现) | `__RADAR_INSIGHT__` | 完成于 P0-2 |
| 单次活动详情(已实现) | `__REPORT_INSIGHT__` | 既有 sentinel,延用 |
| 训练计划 | `__TRAINING_PLAN_INSIGHT__` | 未来 |
| ... | ... | ... |

#### 5.6.2 7 条铁律(每条对应实现位置 + 验收方式)

| # | 规则 | 铁律描述 | 必改文件 | 验收方式 |
|---|---|---|---|---|
| 1 | **独立 sentinel** | 每类功能区必须**新建** sentinel,**严禁**复用现有 | `main.py` | 全文 grep 确认无字符串复用 |
| 2 | **前端只传控制参数** | 前端 onclick 只传 `('__XXX_INSIGHT__', control_id)`,**不传**任何 metrics / points / DOM 推导值 | `track.html` | 静态 grep,onclick 形参只有 sentinel + control_id |
| 3 | **后端从 _ai_snapshot 构建** | 后端必须从 `_ai_snapshot` / profile_backend / DB 权威字段构建,**不读**任何前端 payload | `main.py` | `_build_xxx_insight_snapshot` 必须白名单过滤 |
| 4 | **sentinel 入口清空 + 刷新** | `call_llm` 内 `if prompt == self.XXX_INSIGHT` 入口处**必须** `self._chat_messages = []; self._new_session_id()`,**所有**分支(happy / 降级)前执行 | `main.py` | 集成测试覆盖 happy + 降级 1 + 降级 2 |
| 5 | **阅后即焚 3 触发点** | 前端必须在 ①切 Tab ②切 sport/state ③重新点击 三处共用 `_clearRadarInsight()` 类清空辅助 | `track.html` | 静态 grep,3 处都引用 |
| 6 | **严禁写 DB** | 整个洞察流程**不**调 `db` / `sqlite` / `INSERT` / `save_xxx`,**不**进 `ai_snapshots` 表 | 全栈 | 集成测试断言 `_ai_snapshot` / `_track_points` 未被改写 |
| 7 | **错误用 empty_xxx_insight** | 任何失败(LLM 异常 / 数据缺失 / JSON 解析)必须返回 `empty_xxx_insight(error_msg)`,**不抛** promise reject / 不返 raw error | `llm_backend.py` | normalizer 单元测试 + 集成测试覆盖所有失败路径 |

#### 5.6.3 P0-N / P1-N / P2-N 标准任务清单

新增一个功能区 AI 洞察,必须按顺序完成下列三阶段(每阶段 5-7 个子任务):

| 阶段 | 子任务 | 必改文件 | 行数(参考) |
|---|---|---|---|
| **P0-N** 后端 | 1. 在 `main.py` 新增 sentinel 常量 + `call_llm` 分支(带 §5.6.2 规则 4 入口清空) | `main.py` | ~50 |
| | 2. 在 `llm_backend.py` 新增 prompt builder + normalizer + `empty_xxx_insight` | `llm_backend.py` | ~150 |
| | 3. 在 `main.py` 新增 `_build_xxx_insight_snapshot`(白名单过滤,严禁 shadow_diff) | `main.py` | ~30 |
| | 4. 在 `main.py` 新增 `_build_xxx_insight_messages` | `main.py` | ~15 |
| | 5. 在 `docs/js_api_contract.json` 登记新 API | `docs/js_api_contract.json` | ~5 |
| **P1-N** 前端 | 1. 在 `track.html` 目标 Tab 加按钮 + 面板 HTML | `track.html` | ~10 |
| | 2. 在 `track.html` 加 CSS(5 类:.summary / .dim-list / .dim-item / .advice / .disclaimer + error 变体) | `track.html` | ~70 |
| | 3. 在 `track.html` 加状态层(`_xxxInsightData` / `_xxxInsightLoading` / `_clearXxxInsight`) | `track.html` | ~15 |
| | 4. 在 `track.html` 加 `onXxxAiInsight` async 入口(try/catch/finally) | `track.html` | ~40 |
| | 5. 在 `track.html` 加 `_renderXxxInsightPanel` 渲染函数 | `track.html` | ~35 |
| | 6. 在 `track.html` `switchTab` 末尾追加 `_clearXxxInsight()` | `track.html` | ~2 |
| | 7. 在 `track.html` 切状态函数末尾追加 `_clearXxxInsight()`(若适用) | `track.html` | ~2 |
| **P2-N** 测试 | 1. prompt 单元测试(6 维度 / N sport / DATA BOUNDARY / MUST NOT) | `test_xxx_prompts.py` | ~25 |
| | 2. normalizer 单元测试(降级 / 截断 / clamp) | 同上 | ~15 |
| | 3. snapshot 构建器 mock 测试(白名单 / shadow_diff 隔离) | 同上 | ~10 |
| | 4. `Api.call_llm` 集成测试(happy / 降级 / §5.6.2 规则 4 全分支) | `test_xxx_integration.py` | ~15 |
| | 5. 手工测试清单(覆盖 5 sport_type / 切 Tab / 切 sport / LLM 异常 / 无数据) | `docs/xxx_manual_test_checklist.md` | ~250 |

#### 5.6.4 §5.4 / §5.5 / §5.6 三者关系

| 章节 | 角色 | 时机 |
|---|---|---|
| **§5.4** | 「是什么」(7 条 AI 边界规则) | **审计时**查阅 |
| **§5.5** | 「具体怎么算」(轨迹报告 v3 字段) | 实现轨迹报告时查阅 |
| **§5.6**(本节) | 「怎么开发」(P0/P1/P2 任务清单 + 7 条铁律) | **开始新 AI 洞察功能**时查阅 |

#### 5.6.5 违反本节的后果

| 违规 | 后果 |
|---|---|
| sentinel 复用 | 与其他功能区 session 污染(用户切 Tab 后 AI 教练回答错乱) |
| 前端读 DOM | 违反 §五 数据可信分层(UI 推导值进入 AI) |
| 入口清空缺失 | 降级路径残留旧 session,AI 教练回答带旧上下文 |
| 写 DB | 违反 §八 canonical 隔离(AI 输出污染运动画像) |
| 错误抛异常 | pywebview 通道破裂,前端白屏 |

---

## 六、shadow_diff 契约

| 属性 | 契约 |
|---|---|
| DB 字段 | `activities.shadow_diff_json` |
| API 字段 | `shadow_diff` |
| 字段性质 | **debug-only / audit-only** |
| 数据来源 | MetricsResolver Shadow Layer |
| 数据用途 | 仅用于 Resolver 与 Legacy 指标差异审计、调试、回归验证 |
| 常规 UI 展示 | **禁止**进入常规活动列表、详情主展示、指标卡片、图表 |
| AI Snapshot | **禁止**进入 AI Snapshot、AI prompt、AI 分析上下文 |
| Canonical 指标 | **禁止**参与 canonical 指标计算、排序、筛选、运动画像、雷达图、训练负荷计算 |
| 持久化格式 | JSON 字符串，反序列化后仅作为审计对象读取 |

验收规则：
- 查询活动列表或详情时，`shadow_diff` 不得影响任何业务字段展示
- 构建 AI Snapshot 时，出现 `shadow_diff` 应视为契约违规
- 修改 Resolver、入库或 API 返回逻辑时，必须验证 `shadow_diff_json` 仍不参与 canonical 数据路径

---

## 七、安全契约 (Security Contract)

### 7.1 敏感字段脱敏

- LLM `api_key`：存储加密，读取时脱敏返回（仅返回 `has_api_key` 与 `api_key_masked` 尾4位）
- 日志/错误信息中禁止输出完整 api_key

### 7.2 文件操作安全

- `batch_import_tracks`：必须有路径穿越防护、ZIP 解压上限防护
- `delete_activities`：必须有二次确认 token、路径越权检测、仅限 TRACKS_DIR 内文件
- `save_config`：`workspace_track_path` 强制锁定为 TRACKS_DIR

### 7.3 暂不引入

- OAuth
- RBAC
- 多租户 ACL
- 企业 IAM

---

## 八、数据库契约

### 8.1 技术选型

SQLite — 长期唯一数据库，不升级 PostgreSQL/ClickHouse/ElasticSearch/BigQuery。

### 8.2 核心表

| 表名 | 说明 |
|---|---|
| `activities` | 主活动表 |
| `activity_records` | 逐秒轨迹记录 |
| `activity_laps` | 圈信息 |
| `ai_snapshots` | AI 输入 snapshot |

### 8.3 Canonical DB 原则

- 只存可信数据 (source_type=fit_sdk)
- 不允许 synthetic metrics
- 不允许 AI 结果回写
- 数据必须标记 `source_type` 和 `is_mock`

---

## 九、文件/目录契约

### 9.1 根目录结构

```
├── src/          ← 核心源码
├── web/          ← 前端文件
├── lib/          ← 第三方库（版本锁定，不修改）
├── tests/        ← 测试代码
├── docs/         ← 文档
├── build/        ← 构建产物
├── .venv/        ← 虚拟环境
├── requirements.txt
└── .gitignore
```

### 9.2 文件操作规范

- Python 依赖全部写入 `requirements.txt`（格式：`包名==版本号`）
- 禁止 `sys.path.insert` 引用本地模块
- 禁止硬编码绝对路径（如 `/Desktop/AI track/`）
- 路径使用 `pathlib.Path` 和基于用户目录的相对计算
- 大型前端库放 `lib/` 本地加载，不依赖 CDN

### 9.3 技术栈

| 层 | 选型 |
|---|---|
| 后端语言 | Python >= 3.11 |
| 桌面框架 | pywebview >= 5.0 |
| 数据库 | SQLite 3 |
| 前端 | TypeScript + React (单文件 track.html 渐进迁移) |
| 地图引擎 | CesiumJS (lib/ 本地副本) |
| FIT 解析 | fitparse >= 1.2.0 |
| GPX 解析 | gpxpy >= 1.6.0 |

---

## 十、架构禁止事项 (Non-Goals — 永不允许)

### 不做
- SaaS 平台（多租户、云账号、订阅）
- 社交平台（关注、点赞、评论、动态流）
- 企业 BI（Data Lake、Cube、ETL、OLAP）
- AI Agent Runtime（agent orchestration、workflow engine）
- 微服务体系、Kafka、Event Bus、Feature Store
- GraphQL Federation、企业级权限系统

### 每个新增能力必须回答
> OpenClaw 会真实使用它吗？

答案否定 → 不进入核心架构。

---

## 十一、审查与实施

### 11.1 新增接口

任何新增接口：
1. 必须遵循本契约的响应结构规范
2. 必须登记到 `docs/js_api_contract.json`
3. 必须通过统一错误码体系返回错误

### 11.2 代码审查门禁

| 检查项 | 违规处理 |
|---|---|
| 前端 UI 推断值写回 canonical | **拒绝** |
| AI 输出进入 canonical 层 | **拒绝** |
| `shadow_diff` 进入 AI Snapshot | **拒绝** |
| 新增文件放入错误目录 | **拒绝** |
| 硬编码绝对路径 | **拒绝** |
| 未更新 requirements.txt 引入新依赖 | **拒绝** |
| 敏感字段未脱敏 | **拒绝** |

### 11.3 字段版本化

未来建议引入 `field_contract_version` 用于 schema evolution。

---

> 脉图是一个基于 FIT 可信数据层的本地 AI 运动外挂，通过轻量语义解析与 AI Snapshot 机制，为 OpenClaw 提供稳定、可解释、长期可演进的运动上下文系统。
