---
name: coros-stats
description: 高驰/COROS 用户画像与运动健康数据查询 Skill。用于在 Codex/OpenClaw/QClaw/WorkBuddy 中安装或调用 COROS MCP，连接高驰账号，查询高驰用户画像，给脉图同步用户画像，返回用户画像 JSON 数组，或通过 https://t.coros.com/admin/views/dash-board 获取 Training Hub 仪表盘数据。触发词包括「高驰数据」「COROS MCP」「同步用户画像」「更新脉图用户画像」「查询我的跑步档案」「返回所有运动指标 JSON」。
---

# coros-stats

这个 Skill 用来获取高驰/COROS 用户画像 JSON 数组，主要服务于脉图用户画像更新。数据只来自两条通道：

1. COROS Training Hub URL/API：通过 `https://t.coros.com/admin/views/dash-board` 获取全部历史 PB、阈值面板、心率区间、训练负荷等字段，优先级最高。
2. COROS MCP：通过官方账号授权的 MCP 服务获取身份信息、身体基础数据、体能评估和近期运动记录，只在 Training Hub 没有覆盖该字段时兜底。

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

安装脚本会检查 Node/npm，执行 `npm install -g coros-mcp`，启动 COROS OAuth 登录，注册 MCP 到 OpenClaw，并重启 OpenClaw 网关。

## 仪表盘通道准备

仪表盘通道需要一个开启 DevTools 端口的 Chrome，并且已经登录 COROS Training Hub。

```bash
bash ~/.qclaw/skills/coros-stats/scripts/start_chrome.sh
```

在打开的 Chrome 中登录并保持这个页面可访问：

```text
https://t.coros.com/admin/views/dash-board
```

不要询问、保存或记录用户的 COROS 密码。让用户在浏览器里用 COROS 支持的方式自行完成登录。

## 主要命令

### 脉图用户画像同步

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

这个 JSON 数组用于给脉图的用户画像更新程序直接消费。

普通查询模式：

```bash
python3 ~/.qclaw/skills/coros-stats/scripts/coros_runner_profile.py
```

仅返回原始 JSON 数组：

```bash
python3 ~/.qclaw/skills/coros-stats/scripts/coros_runner_profile.py sync
```

## 数据合并规则

字段优先级从高到低：

1. Training Hub URL/API：`t.coros.com/admin/views/dash-board` 和同一登录态下的 Training Hub 接口。
2. COROS MCP 工具。
3. 获取不到时返回 `null`，并用 `note` 说明原因。

不要读取本地手动覆盖文件，不要用公式估算字段值。PB 字段优先使用 Training Hub URL 的“全部/all-time”个人纪录；MCP 的 `querySportRecords` 只代表近期窗口，只能在 URL 没有覆盖到该字段时作为兜底，并必须在 `note` 中说明不是 all-time。

## 输出格式

输出为 JSON 数组，每一项格式如下：

```json
[
  {"metric": "username", "value": "用户昵称"},
  {"metric": "age", "value": 46},
  {"metric": "vo2_max", "value": 45, "note": "COROS MCP"}
]
```

`value` 可以是字符串、数字、布尔值或 `null`。当数据来源、可信度或不可获取原因需要说明时，添加 `note`。

核心字段：

| 字段 | 主要来源 |
|---|---|
| `username`, `age`, `gender`, `height_cm`, `weight_kg` | MCP `queryUserInfo` |
| `vo2_max`, `lactate_threshold_pace`, 比赛预测 | MCP `queryFitnessAssessmentOverview` |
| 近期运动合计 | MCP `querySportRecords` |
| `resting_heart_rate`, `max_heart_rate`, `lactate_threshold_hr` | 仪表盘 |
| `1km_pb`, `5km_pb`, `10km_pb`, `longest_run_km`, `longest_cycle_km` | 仪表盘全部历史纪录 |
| 半马/全马 PB、体成分 | 当前 Training Hub URL/API 和 MCP 未覆盖时返回 `null` |

`max_heart_rate` 是高驰比原佳明兼容字段多出的增强字段。只要可获取，就应保留在脉图用户画像 JSON 中。

## MCP 工具说明

安装完成后可直接调用这些高驰 MCP 工具：

```bash
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call queryUserInfo '{}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call queryFitnessAssessmentOverview '{}'
node ~/.qclaw/skills/coros-stats/scripts/coros-mcp-keepalive.js call querySportRecords '{}'
```

直接调用 MCP 时优先使用 `coros-mcp-keepalive.js`。COROS MCP 会话可能绑定在当前连接上，朴素调用容易出现 `Session not found`。

## 仪表盘通道说明

抓取仪表盘数据：

```bash
node ~/.qclaw/skills/coros-stats/scripts/coros-url-fetch.js
```

脚本会连接 Chrome DevTools，找到或打开高驰仪表盘标签页，尽量切换全部历史纪录下拉框，读取页面文本并解析字段。

如果失败，按顺序检查：

- Chrome 是否已用 DevTools 端口 `9222` 启动。
- 用户是否已登录 `https://t.coros.com/admin/views/dash-board`。
- 是否需要重新运行 `start_chrome.sh`。
- 如果高驰页面结构变化导致字段大面积为 `null`，除「同步用户画像」场景外，应在 `note` 里说明仪表盘解析异常，并退回 MCP 可用字段。

## Training Hub Token

少量 Training Hub 接口需要 `accessToken`。获取方式：

```bash
node ~/.qclaw/skills/coros-stats/scripts/coros_traininghub_login.js
```

脚本会等待浏览器中已登录的 dashboard cookie，并保存到：

```bash
~/.qclaw/coros-traininghub-token.json
```

Token 来自浏览器登录态，不要询问用户密码。

## 不可获取字段

部分字段可能返回 `null`，这是高驰当前 MCP 或仪表盘不暴露造成的：

- 体成分：`body_fat_percent`, `body_water_percent`, `bone_mass_kg`, `muscle_mass_kg`, `metabolic_age`, `visceral_fat`
- 睡眠和 HRV：账号近期没有手表睡眠数据，或 MCP/仪表盘没有返回
- FTP 和部分骑行/游泳 PB
- 全部历史总里程：当高驰只暴露近期运动记录时无法直接获取

这些字段返回 `null` 并带简短 `note`。本 Skill 不通过手动覆盖或估算补齐字段。
