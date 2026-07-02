# COROS / 高驰账号改造收口报告

日期：2026-07-02

## 收口结论

COROS 账号改造当前已从任务一调研状态推进到独立 provider/direct-script 架构。`coros_sync.py` 负责 COROS 区域解析、skill 脚本定位、授权状态只读诊断、授权入口启动、画像脚本调用与稳定错误转换；`profile_backend.py` 负责画像字段规范化、旧有效值保留、数据质量摘要和入库；`track.html` 负责配置页区域/授权 UI、失败路由和前端展示。

Garmin 与 COROS 保持独立 provider：Garmin 仍走 `garmin_sync.py`，COROS 走 `coros_sync.py`，两者没有合并到同一个 provider。COROS 用户画像同步不再走 LLM/OpenClaw，不读取或保存账号密码。

## 已落地架构

### Provider 边界

- `coros_sync.py`
  - 支持 `cn/us/eu` 三个区域，默认 `cn`。
  - 定位项目内 `skills/coros-stats` 脚本。
  - `check_auth_status()` 只读检查 skill、Node、MCP token 路径、Training Hub token 路径，并通过 `coros-mcp-keepalive.js --print-config` 校验区域 endpoint/token 路径。
  - `start_login()` 仅在配置页用户显式点击授权时启动授权脚本。
  - `start_traininghub_login()` 与 MCP OAuth 分离，仅在用户点击“准备 Training Hub”时启动 Chrome/Training Hub 登录态准备脚本。
  - `sync_profile_json()` 运行 `coros_runner_profile.py sync`，要求 stdout 为 JSON 数组。
  - 不负责画像入库、前端 UI、Garmin 逻辑、活动 FIT 导入或 LLM 调用。

- `profile_backend.py`
  - `fetch_mcp_persona("coros")` 直接调用 `coros_sync.sync_profile_json(region=coros_region)`。
  - 将 metric 数组映射到脉图 canonical profile。
  - 缺失字段保留旧有效值。
  - 输出 `profile_sync_summary`，包含 `data_quality`、`updated_fields`、`preserved_fields`、`missing_fields`、`supports_remote_activity_sync`、`activity_sync_hint`。

- `main.py`
  - 暴露 `set_coros_region`、`check_coros_auth_status`、`start_coros_login`。
  - `fetch_mcp_persona` 成功和失败都会透传画像同步摘要；失败时保留 `provider_error_code` 与 `action_hint`。

### 区域与 endpoint

| 区域 | MCP endpoint | MCP token 路径 |
| --- | --- | --- |
| `cn` | `https://mcpcn.coros.com/mcp` | `~/.coros-mcp-skill-gateway-ts/cn/token.json` |
| `us` | `https://mcpus.coros.com/mcp` | `~/.coros-mcp-skill-gateway-ts/us/token.json` |
| `eu` | `https://mcpeu.coros.com/mcp` | `~/.coros-mcp-skill-gateway-ts/eu/token.json` |

Training Hub token 默认路径为 `~/.qclaw/coros-traininghub-token.json`。状态检查只判断文件是否存在，不读取 token 内容。

### 前端配置页

`track.html` 已在配置页加入 COROS 区域选择、状态灯、「检查状态」和「授权」按钮。同步过程中遇到 COROS 授权或 Training Hub 准备类错误时，只提示用户回配置页处理，不在同步流程里静默启动授权。

任务十二补充了独立的「准备 Training Hub」按钮。MCP 授权与 Training Hub 登录态分开展示：MCP token 存在但 Training Hub token 缺失时，配置页显示“画像字段可能不完整”，并引导用户准备 Training Hub，而不是要求重复做 COROS MCP 授权。

当 COROS 画像同步提供有效 `max_heart_rate -> max_hr` 且不是保留旧值时，前端禁用手动最大心率输入；如果 `max_hr` 是旧有效值保留，则仍允许用户手动维护。

### Skill 脚本

`skills/coros-stats/scripts/coros-mcp-keepalive.js` 已区域化：

- 支持 `COROS_REGION`。
- 支持 `--region cn/us/eu`。
- 支持 `--print-config`。
- token 路径随区域切换。

`skills/coros-stats/scripts/coros_runner_profile.py` 输出 JSON 数组，字段包含 `max_heart_rate`、静息心率、阈值心率/配速、PB 和比赛预测字段。

### Node / OpenClaw Runtime

任务十一补充了 COROS 授权脚本的 runtime 探测：

- 优先使用 `PATH` 中的 `node` / `npm`。
- 若 GUI App 或终端 PATH 找不到 Node，则继续探测 nvm、Homebrew、QClaw bundled Node 常见路径。
- 调用 `openclaw` wrapper 前自动注入 `QCLAW_CLI_NODE_BINARY`。
- 若可找到 QClaw 的 `openclaw.mjs`，自动注入 `QCLAW_CLI_OPENCLAW_MJS`。
- 若 COROS OAuth 已成功但 OpenClaw 注册失败，脚本明确提示“授权已成功，OpenClaw 注册失败或跳过”，并避免误导用户重复登录。

这一步只影响 COROS MCP 安装/授权辅助流程。脉图画像同步仍由 `coros_sync.py -> coros_runner_profile.py sync` 控制，不让 LLM/OpenClaw 生成画像 JSON。

### Training Hub 登录态

Training Hub 登录态用于补充更完整的画像字段，例如部分 all-time PB、阈值心率/配速、骑行 PR 等。它与 COROS MCP OAuth 是两套 token：

- MCP token 默认路径：`~/.coros-mcp-skill-gateway-ts/<region>/token.json`
- Training Hub token 默认路径：`~/.qclaw/coros-traininghub-token.json`

Training Hub 准备流程会打开带 DevTools 的 Chrome，并让用户自行登录 `https://t.coros.com/admin/views/dash-board`。脚本从浏览器登录态检测 `CPL-coros-token` 并保存到本地 token 文件；应用状态检查只判断文件是否存在，不读取 token 内容。

## API 契约

`docs/js_api_contract.json` 已覆盖：

- `coros_region` 配置保存。
- `set_coros_region(value)`。
- `check_coros_auth_status(region)`。
- `start_coros_login(region)`。
- `start_coros_traininghub_login(region)`。
- `fetch_mcp_persona(platform)` 的 COROS direct provider、失败字段和 `profile_sync_summary` 语义。

统一响应契约仍以 `{ok, code, msg, data, traceId}` 为目标；画像相关旧调用保留顶层 `ok/error/profile/profile_sync_summary` 兼容字段。

稳定错误码包括：

- `invalid_coros_region`
- `coros_auth_required`
- `coros_traininghub_required`
- `coros_skill_not_found`
- `coros_script_failed`
- `coros_json_parse_error`

## 活动同步边界

COROS 当前不支持远程活动 FIT 同步。远程按日期同步仍只对 Garmin 开放；COROS 用户应使用本地 FIT、ZIP 或目录监听导入活动。`querySportRecords` 不能等同于 Garmin FIT 下载，只可作为画像字段或近期摘要的兜底来源。

## 验收覆盖

当前本地测试覆盖：

- COROS provider 区域、路径、授权状态、登录启动、脚本执行和 JSON 校验。
- Node/nvm/Homebrew/QClaw runtime 探测、OpenClaw wrapper 环境变量注入、授权成功后 OpenClaw 注册失败的非误导提示。
- Training Hub token 存在/缺失诊断、独立启动入口、前端“准备 Training Hub”按钮和 `coros_traininghub_required` 路由。
- COROS API 响应封装与不调用 LLM。
- COROS skill 区域脚本与画像字段清单。
- COROS 画像字段 alias 映射、`max_heart_rate -> max_hr`、旧有效值保留、数据质量分级。
- 前端 COROS 配置页、授权失败路由、最大心率输入禁用、远程活动同步品牌边界。

建议回归命令：

```bash
python3 -m py_compile main.py profile_backend.py coros_sync.py garmin_sync.py llm_backend.py skills/coros-stats/scripts/coros_runner_profile.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
python3 -m pytest tests/test_coros_sync_provider.py -q
python3 -m pytest tests/test_coros_auth_api.py -q
python3 -m pytest tests/test_coros_skill_region_scripts.py -q
python3 -m pytest tests/test_fit_sync.py -k "coros or garmin_persona or persona" -q
python3 -m pytest tests/test_track_html_sync_logic.py -k "coros or garmin" -q
```

## 剩余风险

- 未做自动化真实 COROS 登录、真实 MCP 调用或真实 Training Hub 同步验收；Training Hub 登录需用户在浏览器中手动完成。
- Node 缺失环境下，Node 语法/运行类测试会 skip；provider 与安装脚本会尽量探测 nvm/Homebrew/QClaw bundled Node，但发布包内置 Node 仍需单独规划。
- COROS Training Hub 页面结构变化可能导致字段解析为空，需要通过后续真实账号验收确认。
- COROS 远程活动 FIT 下载能力仍未确认，不应在当前架构中打开远程活动同步。
- 发布前仍需单独执行本地敏感文件清理任务，避免源码目录中的配置、数据库、调试文件或本地轨迹数据被打包。
