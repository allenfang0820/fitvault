# COROS / 高驰账号改造任务一调研报告

日期：2026-07-02

## 结论摘要

COROS / 高驰账号改造建议新增独立 `coros_sync.py` provider，参考 Garmin 已完成的 provider/direct-script 架构，但必须保持 Garmin 与 COROS 实现边界独立，不共用 provider。

当前 COROS 用户画像同步仍走 `profile_backend.fetch_mcp_persona("coros") -> LLM/OpenClaw -> MCP 工具调用`。后续应改为直接调用本地 `coros-stats` skill 脚本，优先使用：

```bash
python3 skills/coros-stats/scripts/coros_runner_profile.py sync
```

区域配置建议新增 `coros_region`，候选值为 `cn/us/eu`，默认 `cn`。本地 `coros-stats` skill 明确维护了 `cn/us/eu` 三个 MCP endpoint；调研时也确认 `mcpcn`、`mcpus`、`mcpeu` 三个 `/mcp` endpoint 均表现为 OAuth Bearer 保护的 MCP 资源。

活动同步不能直接把 COROS `querySportRecords` 等同于 Garmin FIT 下载。当前只确认它可以提供运动记录摘要或近期窗口数据，未确认可下载 FIT 文件或完整活动数据。除非后续确认 COROS 提供可下载 FIT/API，否则远程活动同步仍应提示用户使用本地 FIT、ZIP 或目录监听导入。

授权入口建议放在配置页，和 Garmin 的区域选择、状态灯、「检查状态」「授权」按钮体验保持一致，但 API、provider、错误码、状态判断都应使用 COROS 独立实现。

## 当前代码现状

### 用户画像同步

`profile_backend.py` 中 Garmin 已经 provider 化：`fetch_mcp_persona("garmin")` 直接调用 `garmin_sync.sync_profile_json()`，不再依赖 LLM/OpenClaw。

COROS 当前仍走 LLM/OpenClaw：`fetch_mcp_persona("coros")` 会读取 LLM URL/model，然后通过 `llm_backend.chat_completions()` 让模型调用 COROS MCP 工具并返回 JSON。这与 Garmin 已完成的 direct-script 架构不一致，也是后续任务四的主要改造点。

### 运动记录 / FIT 同步

`main.py` 中 `sync_remote_fit_activities()` 当前只支持 Garmin。它会读取 `watch_brand`，非 Garmin 时直接返回“不支持按时间同步活动”，并提示使用本地 FIT 文件导入。

前端 `track.html` 中远程同步按钮也只在 Garmin 品牌下可用。COROS 当前显示为“活动通过本地 FIT 导入”。

### 配置页

`track.html` 已有 Garmin 区域和授权卡片：

- `garmin-region`
- `garmin-auth-dot`
- `garmin-auth-status-text`
- `garmin-auth-check-btn`
- `garmin-auth-login-btn`

COROS 目前没有对应的 `coros_region`、授权状态灯或授权按钮。

### 配置存储

`llm_backend.py` 目前只持久化 `garmin_region`，没有 `coros_region`。如果 COROS 区域要成为一等配置，需要同步更新：

- `load_llm_config()`
- `save_llm_config()`
- `main.Api.test_llm_config()`
- 配置页 `currentLLMConfig`
- 配置签名 `buildLLMConfigSignature()`
- `docs/js_api_contract.json`

### API 契约

`docs/js_api_contract.json` 已包含 Garmin 的：

- `set_garmin_region`
- `check_garmin_auth_status`
- `start_garmin_login`
- `sync_remote_fit_activities`

但没有 COROS 对应的区域、授权状态或授权入口 API。

## coros-stats Skill 能力

本地存在两份相关 skill 定义：

- `skills/coros-stats/SKILL.md`
- `~/.codex/skills/coros-stats/SKILL.md`

两者内容一致。该 skill 目标是输出脉图可消费的用户画像 JSON 数组。

### 画像同步命令

Codex 路径：

```bash
python3 ~/.codex/skills/coros-stats/scripts/coros_runner_profile.py sync
```

项目内路径：

```bash
python3 skills/coros-stats/scripts/coros_runner_profile.py sync
```

OpenClaw/QClaw 路径：

```bash
python3 ~/.qclaw/skills/coros-stats/scripts/coros_runner_profile.py sync
```

输出格式为 JSON 数组：

```json
[
  {"metric": "username", "value": "用户昵称"},
  {"metric": "age", "value": 46},
  {"metric": "vo2_max", "value": 45, "note": "COROS MCP"}
]
```

### 数据源优先级

`coros-stats` 的数据来源按优先级为：

1. COROS Training Hub URL/API：`https://t.coros.com/admin/views/dash-board`
2. COROS MCP：官方账号授权的 MCP 服务
3. 获取不到时返回 `null`，并用 `note` 说明原因

Training Hub 用于 all-time PB、心率区间、训练负荷等字段。MCP 用于身份信息、身体基础数据、体能评估和近期运动记录兜底。

### MCP 工具

skill 中明确使用这些 MCP 工具：

- `queryUserInfo`
- `queryFitnessAssessmentOverview`
- `querySportRecords`

`querySportRecords` 当前更适合作为近期运动记录摘要或画像字段兜底，不应直接等同于 Garmin 的活动 FIT 文件下载。

### Token 与登录

Training Hub token 路径：

```text
~/.qclaw/coros-traininghub-token.json
```

调研时观察到 MCP token 相关路径：

```text
~/.coros-mcp-skill-gateway-ts/cn/token.json
~/.coros-mcp-skill-gateway-ts/us/pending-login.json
```

本次调研只确认路径存在，没有读取 token 内容。

### 当前脚本问题

`skills/coros-stats/scripts/coros-mcp-keepalive.js` 当前写死：

```js
const TOKEN_PATH = path.join(process.env.HOME, '.coros-mcp-skill-gateway-ts', 'cn', 'token.json');
const MCP_URL = 'https://mcpcn.coros.com/mcp';
```

这意味着即使 skill 文档声明支持 `cn/us/eu`，实际 keepalive 调用仍需要后续改造才能按 `coros_region` 切换 token 路径和 MCP URL。

## MCP / mcpcn.coros.com 调研结果

调研目标站点：

- `https://mcpcn.coros.com`
- `https://mcpcn.coros.com/mcp`

确认事实：

- `https://mcpcn.coros.com` 返回 401 Bearer，说明它是需要 OAuth token 的受保护资源，不是公开文档页。
- `https://mcpcn.coros.com/mcp` 返回 401 Bearer，并带有 `resource_metadata`。
- `https://mcpcn.coros.com/.well-known/oauth-protected-resource/mcp` 返回 OAuth protected resource metadata。
- `https://mcpus.coros.com/mcp` 和 `https://mcpeu.coros.com/mcp` 也返回 401 Bearer MCP 资源响应。
- `mcpus` 与 `mcpeu` 的 `.well-known/oauth-protected-resource/mcp` 也能返回对应的 resource、authorization server、scope 信息。

三区域 endpoint：

| 区域 | MCP endpoint |
| --- | --- |
| `cn` | `https://mcpcn.coros.com/mcp` |
| `us` | `https://mcpus.coros.com/mcp` |
| `eu` | `https://mcpeu.coros.com/mcp` |

scope 信息包括：

- `openid`
- `mcp.tools`
- `offline_access`

官方资料同时提到新版 COROS MCP 使用统一入口：

```text
https://mcp.coros.com/mcp
```

参考来源：

- https://coros.com/stories/coros-metrics/c/mcp-testing

因此，后续 provider 设计应把 `coros_region -> issuer/endpoint/token_path` 做在 provider 层，业务层只认 `coros_region`，并保留切换统一 endpoint 的空间。

## 推荐 COROS Provider 架构

建议新增文件：

```text
coros_sync.py
```

### Provider 职责

`coros_sync.py` 建议提供：

- `resolve_coros_region(region)`
  - 支持 `cn/us/eu`
  - 默认 `cn`
  - 非法值抛出 `CorosSyncError(code="invalid_coros_region")`

- `get_coros_skill_paths(base_dir=None)`
  - 定位 `skills/coros-stats`
  - 定位 `coros_runner_profile.py`
  - 定位 `install_coros_mcp.sh`
  - 定位 `coros_traininghub_login.js`
  - 定位 `start_chrome.sh`

- `check_auth_status(region=None)`
  - 检查 skill 脚本是否存在
  - 检查 Node 是否可用
  - 检查 MCP token 路径是否存在
  - 检查 Training Hub token 路径是否存在
  - 返回可用于配置页状态灯的数据结构

- `start_login(region=None, channel="mcp")`
  - `channel="mcp"` 时启动 COROS MCP OAuth 登录
  - 后续可支持 `channel="traininghub"` 启动浏览器登录辅助
  - macOS 可参考 Garmin 在 Terminal 中启动授权流程

- `sync_profile_json(region=None, timeout=300)`
  - 直接运行 `coros_runner_profile.py sync`
  - 校验 stdout 是 JSON 数组
  - 校验数组元素是对象
  - token 缺失或授权失败时转换为稳定错误码

### 不属于 Provider 的职责

`coros_sync.py` 不负责：

- 用户画像入库
- 用户画像字段合并策略
- 前端 UI 渲染
- 活动库 FIT 导入
- Garmin 区域和授权逻辑
- LLM/OpenClaw 会话调用

## 账号区域配置方案

建议新增配置字段：

```json
{
  "coros_region": "cn"
}
```

候选值：

- `cn`
- `us`
- `eu`

默认值：

- `cn`

保存位置建议沿用当前 `llm_config.json` 配置结构，但只保存区域，不保存账号、密码或 token。

前端配置页建议：

- 选择 COROS 时显示 COROS 区域选择和授权状态卡片。
- 选择 Garmin 时显示 Garmin 区域和授权卡片。
- Garmin 与 COROS 区域控件和状态函数分开实现，避免共享 provider 逻辑。

## 授权状态和授权入口设计

建议新增后端 API：

### set_coros_region

请求参数：

```json
{
  "value": "cn"
}
```

响应：

```json
{
  "ok": true,
  "code": 0,
  "msg": "ok",
  "data": {
    "coros_region": "cn"
  },
  "traceId": "..."
}
```

### check_coros_auth_status

请求参数：

```json
{
  "region": "cn"
}
```

响应数据建议：

```json
{
  "region": "cn",
  "status": "authorized",
  "authorized": true,
  "mcp_authorized": true,
  "traininghub_authorized": true,
  "token_path": "~/.coros-mcp-skill-gateway-ts/cn/token.json",
  "traininghub_token_path": "~/.qclaw/coros-traininghub-token.json",
  "message": "已检测到 COROS 中国区授权。",
  "login_command": ["bash", ".../install_coros_mcp.sh", "--region", "cn"]
}
```

### start_coros_login

请求参数：

```json
{
  "region": "cn",
  "channel": "mcp"
}
```

响应数据建议：

```json
{
  "region": "cn",
  "status": "launched",
  "message": "已打开终端窗口，请完成 COROS 授权。",
  "command": ["bash", ".../install_coros_mcp.sh", "--region", "cn"],
  "stdout": "",
  "stderr": ""
}
```

同步流程遇到 token 缺失或失效时，只提示用户回配置页授权，不在同步流程中弹账号密码输入，也不要求用户在应用内输入 COROS 密码。

## 用户画像同步链路设计

后续应将 `fetch_mcp_persona("coros")` 内部从 LLM/OpenClaw 改为：

1. 读取 `coros_region`。
2. 调用 `coros_sync.sync_profile_json(region=coros_region)`。
3. 解析 JSON 数组。
4. 复用 Garmin 分支已有的 array-to-map 映射方式，或抽出通用映射 helper。
5. 保留 COROS raw snapshot，用于追踪字段来源和 `note`。
6. 使用现有 `merge_profile_with_existing()` 保留已有有效字段。
7. 写入 `profile_sync_summary`。
8. 失败时返回统一错误结构和稳定 provider 错误码。

COROS 用户画像同步不应再依赖 LLM URL、model、agent_id 或 OpenClaw 会话。

## 运动记录同步链路设计

当前不建议直接开启 COROS 远程活动同步。

已确认：

- `querySportRecords` 可作为近期运动记录或画像字段兜底来源。
- `coros-stats` 当前没有明确提供“按日期下载 FIT 文件到本地目录”的脚本。
- `sync_remote_fit_activities()` 当前语义是 Garmin FIT 下载并导入活动库，不能直接复用给 COROS。

后续任务五应先确认：

- COROS 是否有官方或 Training Hub API 可下载 FIT。
- 是否可按日期范围获取完整活动列表和文件。
- 是否有稳定 activity id、文件名、去重字段。
- 下载结果是否能复用现有本地 FIT 导入流程。

未确认前，COROS 活动同步继续提示：

```text
COROS 暂不支持远程活动同步；请使用本地 FIT、ZIP 或目录监听导入活动。
```

## API 契约与错误码建议

所有新增 API 必须遵循统一响应契约：

```json
{
  "ok": true,
  "code": 0,
  "msg": "ok",
  "data": {},
  "traceId": "..."
}
```

建议新增 API：

- `set_coros_region`
- `check_coros_auth_status`
- `start_coros_login`

后续如确认 COROS 支持远程活动文件下载，再新增或扩展：

- `sync_remote_fit_activities` 的 provider 分支
- 或新增更明确的 `sync_coros_remote_activities`

建议 provider 错误码：

- `invalid_coros_region`
- `coros_auth_required`
- `coros_skill_not_found`
- `coros_node_missing`
- `coros_script_failed`
- `coros_json_parse_error`
- `coros_traininghub_login_required`
- `coros_mcp_token_missing`
- `unknown`

## 测试清单

### Provider 测试

建议新增：

```text
tests/test_coros_sync_provider.py
```

覆盖：

- `resolve_coros_region()` 默认值和非法值。
- `get_coros_skill_paths()` 缺脚本错误。
- `sync_profile_json()` 能解析 JSON 数组。
- 非 JSON / 非数组 / 非对象元素报 `coros_json_parse_error`。
- token 缺失返回 `coros_auth_required` 或状态 `missing_token`。
- `check_auth_status()` 不读取 token 内容。
- `start_login()` 生成正确命令。

### API 测试

建议新增：

```text
tests/test_coros_auth_api.py
```

覆盖：

- `set_coros_region()` 成功与非法值。
- `check_coros_auth_status()` 包装 provider 成功/失败。
- `start_coros_login()` 包装 provider 成功/失败。
- API 返回 `{ok, code, msg, data, traceId}`。
- 不调用 LLM backend。

### 画像同步测试

扩展：

```text
tests/test_fit_sync.py
```

覆盖：

- COROS 画像同步直接调用 `coros_sync.sync_profile_json()`。
- COROS 画像同步不调用 `llm_backend.chat_completions()`。
- COROS provider 失败时写入 sync failed 状态。
- COROS 数组输出能映射到现有 profile 字段。
- Garmin 画像同步保持原有行为。

### 前端静态测试

扩展：

```text
tests/test_track_html_sync_logic.py
tests/test_llm_cli_frontend_config.py
```

覆盖：

- 配置页包含 COROS 区域 select。
- 配置页包含 COROS 状态灯、检查状态、授权按钮。
- 选择 COROS 时显示 COROS 授权卡片，不显示 Garmin 授权卡片。
- `coros_region` 参与配置读取、签名、保存。
- 同步遇到 COROS 授权失败时跳转配置页，而不是启动同步流程内登录。

### Garmin 回归

后续代码改造后应继续验证：

```bash
python3 -m py_compile main.py garmin_sync.py profile_backend.py llm_backend.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
python3 -m pytest tests/test_track_html_sync_logic.py -k garmin -q
python3 -m pytest tests/test_llm_cli_frontend_config.py -q
python3 -m pytest tests/test_garmin_auth_api.py -q
python3 -m pytest tests/test_garmin_sync_provider.py -q
python3 -m pytest tests/test_fit_sync.py -k "remote_fit_sync or garmin" -q
```

完整 `tests/test_track_html_sync_logic.py` 中已有 3 个非 Garmin 静态断言失败，不应在 COROS 任务中顺手修。

## 风险与不确定项

### Node/npm 环境依赖

`coros-stats` 依赖 Node、npm、`ws` 和 `coros-mcp`。调研时 shell 中未解析到 `node/npm` 命令，后续 provider 的 `check_auth_status()` 应将 Node 缺失作为明确状态返回，而不是让画像同步才失败。

### 区域 endpoint 与官方统一入口差异

本地 skill 使用：

- `https://mcpcn.coros.com/mcp`
- `https://mcpus.coros.com/mcp`
- `https://mcpeu.coros.com/mcp`

官方资料提到：

- `https://mcp.coros.com/mcp`

后续应避免在业务层硬编码 endpoint，保留 provider 层映射和未来切换空间。

### Training Hub 浏览器登录态

Training Hub 通道依赖 Chrome DevTools 端口和用户已登录 `https://t.coros.com/admin/views/dash-board`。这比 Garmin tokenstore 更复杂，需要在状态检查中区分：

- MCP 已授权
- Training Hub 已登录
- 两者都可用
- 仅 MCP 可用，画像字段可能部分缺失

### 当前 skill region 硬编码

`coros-mcp-keepalive.js` 写死 `cn` token 和 `mcpcn` endpoint。后续若引入 `coros_region`，必须修复这个脚本或由 provider 设置环境变量/参数。

### 远程 FIT 下载能力未确认

当前没有证据表明 COROS skill 能按日期范围下载 FIT 文件。运动记录 provider 化必须先确认数据能力，不能把 `querySportRecords` 的近期摘要直接当作活动同步。

### Token 和发布清理

COROS token 应只存在用户主目录，不应随 `.app` 或源码目录分发。发布前清理方案需要覆盖：

- `llm_config.json`
- `*.db`
- `.dbg/`
- 本地轨迹/备份数据
- 可能误放入源码目录的 token 或 cookie 文件

## 后续任务拆分建议

### 任务二：COROS provider 骨架与授权状态 API

新增 `coros_sync.py`，实现区域解析、路径定位、授权状态检查、授权启动入口，并补充 API 与测试。

### 任务三：配置页 COROS 账号 UI

在配置页增加 COROS 区域选择、状态灯、「检查状态」「授权」按钮。与 Garmin UI 相似，但函数、元素 id、API 独立。

### 任务四：COROS 用户画像同步 provider 化

将 `fetch_mcp_persona("coros")` 从 LLM/OpenClaw 调用改为直接调用 `coros_sync.sync_profile_json()`，并复用现有画像字段映射和入库链路。

### 任务五：COROS 运动记录同步能力确认与 provider 化

先确认 COROS 是否支持远程 FIT/API 下载。若支持，再设计独立活动同步 provider；若不支持，保持本地 FIT 导入提示，并只使用 MCP 运动摘要作为画像字段兜底。

### 任务六：契约文档与测试补齐

更新 `docs/js_api_contract.json`，补齐 provider/API/frontend/profile 测试，并做 Garmin 回归。

### 任务七：发布前敏感数据清理方案

制定发布前清理 checklist，确保本地配置、数据库、debug 目录、轨迹数据和 token 不随 app 或源码分发。
