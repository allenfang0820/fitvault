---
name: coros-stats
description: 高驰/COROS 用户画像与运动健康数据查询 Skill。用于在 OpenClaw/QClaw/Codex 中安装或调用 COROS MCP，连接高驰账号，查询高驰用户画像，给脉图同步用户画像，返回用户画像 JSON 数组，并支持通过 COROS MCP 下载活动 FIT 文件。触发词包括「高驰数据」「COROS MCP」「同步用户画像」「更新脉图用户画像」「查询我的跑步档案」「返回所有运动指标 JSON」。
---

# coros-stats

这个 Skill 用来获取高驰/COROS 用户画像 JSON 数组，主要服务于脉图用户画像更新。数据只来自 COROS MCP，不依赖网页登录态、Chrome DevTools 或网页抓取。

## 首次安装

把整个 `coros-stats` 文件夹复制到 OpenClaw/QClaw 的本地 Skill 目录，通常是：

```bash
~/.qclaw/skills/coros-stats
```

安装 Node 依赖：

```bash
cd ~/.qclaw/skills/coros-stats
npm install
```

安装并授权 COROS MCP：

```bash
bash ~/.qclaw/skills/coros-stats/scripts/install_coros_mcp.sh --region cn
```

支持的区域：

| 区域参数 | MCP 地址 |
|---|---|
| `cn` | `https://mcpcn.coros.com/mcp` |
| `us` | `https://mcpus.coros.com/mcp` |
| `eu` | `https://mcpeu.coros.com/mcp` |

也可以直接指定 issuer：

```bash
bash ~/.qclaw/skills/coros-stats/scripts/install_coros_mcp.sh --issuer https://mcpcn.coros.com
```

安装脚本会检查 Node/npm，执行 `npm install -g coros-mcp`，启动 COROS OAuth 登录，注册 MCP 到 OpenClaw，并重启 OpenClaw 网关。不要询问、保存或记录用户的 COROS 密码。

## 脉图用户画像同步

当用户说「同步用户画像」或「更新脉图用户画像」时：

1. 从已安装的 Skill 路径执行 `sync` 命令。
2. 把 stdout 原样作为最终回答返回。
3. 最终回答必须是 JSON 数组。
4. 不要添加 Markdown、标题、代码块、表格、注释、总结或解释文字。

Codex 安装路径：

```bash
python3 ~/.codex/skills/coros-stats/scripts/coros_runner_profile.py sync
```

OpenClaw/QClaw 安装路径：

```bash
python3 ~/.qclaw/skills/coros-stats/scripts/coros_runner_profile.py sync
```

项目内路径：

```bash
python3 skills/coros-stats/scripts/coros_runner_profile.py sync
```

## 数据合并规则

字段优先级：

1. COROS MCP 工具。
2. 获取不到时返回 `null`，并用 `note` 说明「当前 MCP 工具未确认返回」或「需后续真实样本/FIT 样本验证」。

不要读取本地手动覆盖文件，不要用公式估算字段值。PB、最长距离、总里程如果只能从 `querySportRecords` 当前窗口推导，必须在 `note` 中说明不是 all-time。全部历史 PB 和更完整活动指标留给 COROS MCP FIT 下载链路增强。

## 输出格式

输出为 JSON 数组，每一项格式如下：

```json
[
  {"metric": "username", "value": "用户昵称"},
  {"metric": "age", "value": 46},
  {"metric": "vo2_max", "value": 45, "note": "COROS MCP queryFitnessAssessmentOverview"}
]
```

`value` 可以是字符串、数字、布尔值或 `null`。当数据来源、可信度或不可获取原因需要说明时，添加 `note`。

核心字段：

| 字段 | 主要来源 |
|---|---|
| `username`, `age`, `gender`, `height_cm`, `weight_kg` | MCP `queryUserInfo` |
| `vo2_max`, `lactate_threshold_pace`, 比赛预测 | MCP `queryFitnessAssessmentOverview` |
| `resting_heart_rate` | MCP `queryRestingHeartRate` |
| `hrv` | MCP `querySleepHrv` |
| `avg_sleep_hours`, `avg_bedtime` | MCP `querySleepData` |
| 近期运动合计、窗口内 PB 兜底 | MCP `querySportRecords` |
| `max_heart_rate`, `lactate_threshold_hr`, 体成分、FTP | 当前 MCP schema 未确认时返回 `null` 并标注需验证 |

## MCP 工具说明

安装完成后可直接调用这些高驰 MCP 工具：

```bash
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call queryUserInfo '{}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call queryFitnessAssessmentOverview '{}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call queryRestingHeartRate '{"days":7,"timezone":"Asia/Shanghai"}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call querySleepHrv '{"days":7,"timezone":"Asia/Shanghai"}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call querySleepData '{"days":7,"timezone":"Asia/Shanghai"}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call querySportRecords '{"sportTypeCodes":[65535],"limit":20,"timezone":"Asia/Shanghai"}'
```

直接调用 MCP 时优先使用 `coros-mcp-keepalive.js`。COROS MCP 会话可能绑定在当前连接上，朴素调用容易出现 `Session not found`。

新版 COROS MCP 已确认支持 FIT 文件能力：

- `downloadActivityFitFiles`
- `queryActivityFitFileDownloadUrls`

脉图的活动同步 provider 会按日期范围调用这些工具，单次限制最大 10 个文件，并复用本地 FIT 导入链路。

## 不可获取字段

部分字段可能返回 `null`：

- 体成分：当前 COROS MCP 工具目录未确认体脂、体水分、骨量、肌肉量、代谢年龄、内脏脂肪字段。
- `max_heart_rate`、`lactate_threshold_hr`：当前 MCP schema 未直接确认，需后续真实样本验证。
- FTP、骑行 40km/80km、游泳 100m PB：需后续通过 COROS FIT 下载和 FIT 解析验证。
- 全部历史 PB/总里程：`querySportRecords` 是查询窗口数据，不应伪装为 all-time。

这些字段返回 `null` 并带简短 `note`。本 Skill 不通过手动覆盖或估算补齐字段。
