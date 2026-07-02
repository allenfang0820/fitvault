# COROS MCP 字段能力交叉验证报告（任务十三）

日期：2026-07-02

## 结论摘要

本次只执行了 COROS MCP 工具目录刷新：

```bash
PATH="$HOME/.nvm/versions/node/v24.18.0/bin:$PATH" coros-mcp --issuer https://mcpcn.coros.com list-tools --refresh
```

该命令连接已授权的 COROS MCP 并执行 `tools/list`，只刷新工具目录，不调用个人数据工具，不读取 token 内容，不下载活动数据。

刷新后的 `~/.coros-mcp-skill-gateway-ts/cn/tool-catalog.json` 显示工具目录更新时间为 `2026-07-02 21:48:25 +0800`，共 22 个工具。用户提供的工具清单大部分已被 MCP 工具目录证实，包括：

- 用户与设备：`queryUserInfo`, `queryDevices`
- 体能评估：`queryFitnessAssessmentOverview`, `queryTrainingLoadAssessment`, `queryRecoveryStatus`
- 运动记录与活动详情：`querySportRecords`, `getActivityDetail`, `analyzeActivityDetail`, `queryActivityLapData`, `queryCustomActivityLapData`
- 每日健康：`queryDailyHealthData`, `queryAvgHeartRate`, `queryRestingHeartRate`, `queryStressLevel`, `queryHealthCheckTimeSeries`, `queryStressTimeSeries`
- 睡眠与 HRV：`querySleepData`, `querySleepHrv`
- 训练计划：`queryTrainingSchedule`
- 生理周期：`queryMenstruationCycles`
- FIT 文件下载：`downloadActivityFitFiles`, `queryActivityFitFileDownloadUrls`

因此，当前 `coros-stats` 仍要求 Training Hub 二次登录来补字段的设计已经明显落后。后续画像同步应改为 MCP-first：优先使用 COROS MCP 获取用户画像、健康、睡眠、HRV、静息心率、活动摘要和体能评估；Training Hub 只能作为可选增强或历史兼容通道，不应再作为配置页持续提示的必需授权状态。

## 本地实现现状

当前 `skills/coros-stats/SKILL.md` 和 `~/.codex/skills/coros-stats/SKILL.md` 仍描述为：

1. Training Hub URL/API 优先。
2. COROS MCP 兜底。

当前 `skills/coros-stats/scripts/coros_runner_profile.py` 也只调用 3 个 MCP 工具：

- `queryUserInfo`
- `queryFitnessAssessmentOverview`
- `querySportRecords`

脚本里大量 `UNAVAILABLE` 说明来自旧判断，例如：

- `hrv` 标注为 URL 面板无数据、MCP NPE。
- `avg_sleep_hours` / `avg_bedtime` 标注为 `querySleepData` 返回无数据。
- `resting_heart_rate` 主要依赖 Training Hub URL。
- FIT/活动下载能力在旧收口文档中被认为未确认。

这些结论现在需要整体复审。刷新后的 MCP 工具目录已经提供 `querySleepHrv`、`querySleepData`、`queryRestingHeartRate`、`downloadActivityFitFiles` 和 `queryActivityFitFileDownloadUrls`，足以支撑后续把画像与活动能力重新分层设计。

## 工具清单交叉验证

| 能力域 | 用户提供工具 | MCP 刷新目录 | 对脉图的意义 |
| --- | --- | --- | --- |
| 用户信息 | `queryUserInfo` | 已确认 | 可继续作为 `username`, `age`, `gender`, `height_cm`, `weight_kg` 主来源 |
| 设备 | `queryDevices` | 已确认 | 可用于授权状态增强、设备展示、调试诊断；不是画像必要字段 |
| 体能概览 | `queryFitnessAssessmentOverview` | 已确认 | 可提供 `vo2_max`, `lactate_threshold_pace`, 比赛预测等 |
| 训练负荷 | `queryTrainingLoadAssessment` | 已确认 | 可作为后续运动能力/疲劳上下文，不一定进入当前 42 字段画像 |
| 恢复状态 | `queryRecoveryStatus` | 已确认 | 可作为后续运动能力/疲劳上下文 |
| 运动记录 | `querySportRecords` | 已确认 | 可按日期范围查询摘要，返回 `labelId`, `sportType`, `startTimestamp`, `endTimestamp` 时可衔接详情/圈段/FIT |
| 活动详情 | `getActivityDetail` | 已确认 | 可补心率、配速、海拔、步频等活动详情，但需后续真实样本确认结构 |
| 活动分析 | `analyzeActivityDetail` | 已确认 | 偏教练总结，不建议作为脉图结构化入库主来源 |
| 默认圈段 | `queryActivityLapData` | 已确认 | 可用于详情页圈段或分析增强 |
| 自定义圈段 | `queryCustomActivityLapData` | 已确认 | 可用于最后 N 分钟、任意窗口等分析增强 |
| 每日健康 | `queryDailyHealthData` | 已确认 | 可补步数、卡路里、压力、睡眠质量和时长等 |
| 平均心率 | `queryAvgHeartRate` | 已确认 | 可作为健康趋势；当前 42 字段不是核心 |
| 静息心率 | `queryRestingHeartRate` | 已确认 | 应替代 Training Hub 作为 `resting_heart_rate` 主来源 |
| 压力 | `queryStressLevel` | 已确认 | 后续可扩展健康趋势 |
| 健康检查时间序列 | `queryHealthCheckTimeSeries` | 已确认 | 可提供心率、HRV、压力、呼吸频率、SpO2 原始序列 |
| 压力时间序列 | `queryStressTimeSeries` | 已确认 | 可用于健康趋势；当前画像可暂不入库 |
| 睡眠 | `querySleepData` | 已确认 | 应作为 `avg_sleep_hours`, `avg_bedtime` 主来源候选 |
| 睡眠 HRV | `querySleepHrv` | 已确认 | 应作为 `hrv` / HRV 基线字段主来源候选 |
| 训练计划 | `queryTrainingSchedule` | 已确认 | 与当前画像同步边界无关，后续可单独规划 |
| 生理周期 | `queryMenstruationCycles` | 已确认 | 与当前画像同步边界无关，应注意隐私和性别适配 |
| FIT 二进制下载 | `downloadActivityFitFiles` | 已确认 | 推翻“COROS 远程活动同步不可行”的旧结论，需要单独设计活动 provider |
| FIT URL 查询 | `queryActivityFitFileDownloadUrls` | 已确认 | 可作为 MCP 客户端不能接收二进制资源时的 fallback |

## 对当前画像字段的影响

建议后续任务把画像字段来源改为 MCP-first：

| 脉图字段 | 建议主来源 | 说明 |
| --- | --- | --- |
| `username`, `age`, `gender`, `height_cm`, `weight_kg` | `queryUserInfo` | 已有实现可保留，但解析要适配真实返回结构 |
| `resting_heart_rate` | `queryRestingHeartRate` | 不再依赖 Training Hub |
| `hrv` | `querySleepHrv` | 取官方 daily sleep HRV assessment，不从 raw points 自行计算 |
| `avg_sleep_hours`, `avg_bedtime` | `querySleepData` 或 `queryDailyHealthData` | 优先真实结构验证后确定 |
| `vo2_max`, `lactate_threshold_pace`, 比赛预测 | `queryFitnessAssessmentOverview` | 已有实现可扩展 |
| `lactate_threshold_hr` | 待验证 | 当前工具目录未直接说明阈值心率；需真实返回样本确认 `queryFitnessAssessmentOverview` 或其他工具是否包含 |
| `max_heart_rate` | 待验证 | 工具目录未明确；可能仍需 Training Hub 或暂保持 null |
| PB / 最长距离 / 总里程 | `querySportRecords` + `downloadActivityFitFiles` | `querySportRecords` 可做摘要，all-time PB 和完整指标建议通过 FIT 解析确认 |
| 体成分字段 | 暂无证据 | 工具目录未出现体脂/肌肉/骨量等专用能力，仍应保持 null 或第三方来源另行设计 |
| FTP / 骑行专项字段 | 待验证 | 需通过 `querySportRecords`、FIT 下载和 FIT 解析真实样本确认 |

## 对活动同步的影响

旧结论是 COROS 不支持远程活动 FIT 同步，只能本地 FIT/ZIP/目录监听导入。现在需要修正为：

COROS MCP 已确认存在 FIT 下载能力，但脉图还没有 COROS 远程活动 provider。后续必须单独设计，不应把它混进 Garmin provider，也不应直接复用 Garmin token 路径。

建议后续活动同步任务边界：

- `coros_sync.py` 增加独立 COROS 活动同步 provider 能力。
- 先通过 `querySportRecords` 获取日期范围内活动摘要和 `labelId`/`sportType`。
- 再通过 `downloadActivityFitFiles` 获取 FIT 二进制资源，或通过 `queryActivityFitFileDownloadUrls` 获取 URL fallback。
- 复用现有 FIT 解析和入库链路，但 provider、错误码、授权状态、区域配置保持 COROS 独立。
- 继续遵循统一 API 响应契约 `{ok, code, msg, data, traceId}`。

## 配置页影响

当前配置页提示“Training Hub 未检测到登录 token，画像字段可能不完整”已经不适合新版能力。

建议后续改为：

- 授权状态主判断只看 COROS MCP token / MCP 可用性。
- Training Hub 状态变成可选高级诊断，不作为绿色授权状态的阻断项。
- “准备 Training Hub”按钮可以隐藏、弱化，或移动到高级/兼容区域。
- 画像同步失败时只提示回配置页处理 COROS MCP 授权，不再引导用户二次登录 Training Hub。

## 后续任务建议

### 任务十四：COROS 画像同步 MCP-first 改造

目标：改造 `coros_runner_profile.py` 和相关状态文案，使用户画像同步优先使用 MCP 22 工具能力，移除 Training Hub 作为必要路径的体验依赖。

边界：

- 可改 `skills/coros-stats/scripts/coros_runner_profile.py`、`skills/coros-stats/SKILL.md`、`~/.codex/skills/coros-stats/SKILL.md`、`coros_sync.py` 状态文案、`track.html` 配置页文案、相关测试和文档。
- 不做 COROS 远程 FIT 活动同步实现。
- 不读取 token 内容，不保存账号密码。
- 除非用户明确允许，不调用真实个人数据工具；可以通过 mock 样本和工具 schema 做实现准备。

### 任务十五：COROS 远程 FIT 活动同步方案与实现

目标：基于 `downloadActivityFitFiles` / `queryActivityFitFileDownloadUrls` 设计并实现 COROS 独立远程活动同步链路。

边界：

- Garmin provider 不改混。
- COROS 活动同步走独立 provider 分支。
- 需要先定义日期范围、下载限制、重复导入、FIT 解析错误、URL fallback、部分成功等契约。
- 必须补充 `docs/js_api_contract.json` 和测试。

### 任务十六：真实 MCP 字段样本验证

目标：在用户明确允许后，只调用必要的只读 MCP 工具，采集脱敏字段结构样本，确认解析逻辑。

边界：

- 不输出原始隐私数据到文档。
- 不读取 token 文件内容。
- 不调用下载 FIT 二进制，除非任务十五需要且用户明确确认。
- 输出字段结构、缺失情况、解析风险和测试样本脱敏模板。

## 风险与未确认项

- 工具目录只能证明工具存在和 schema/description，不证明当前账号每个字段都有数据。
- `lactate_threshold_hr`、`max_heart_rate`、all-time PB、FTP、体成分仍需真实返回结构或 FIT 解析验证。
- `downloadActivityFitFiles` 的 MCP binary resource 返回形态需要单独验证，不能假设等同于 URL 文本。
- FIT 下载描述提到默认最多 5、最大 10，后续活动同步要设计分页/日期窗口/部分成功策略。
- 生理周期、健康时间序列等字段敏感度高，后续如果进入 UI 或文档，应有更严格的隐私边界。

