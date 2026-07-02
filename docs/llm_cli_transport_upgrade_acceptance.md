# 大模型 CLI 接管升级实施说明与验收清单

## 1. 范围

本轮改造目标是把脉图的大模型通道从单一 HTTP 网关扩展为双模式配置：

- `transport=http`：沿用原 HTTP Gateway / OpenClaw Gateway / OpenAI-compatible API。
- `transport=cli`：通过本机 CLI 调用模型，例如 OpenClaw CLI、Codex CLI、Claude Code 或自定义 CLI。

一旦用户在配置页选择 CLI，`Api.call_llm()` 下的 AI 能力统一走 CLI，不再拆成“普通对话走 CLI、AI 洞察仍走 HTTP”的两套配置。

本轮覆盖：

- AI 私教普通对话
- 活动建议
- 雷达图 AI 洞察
- 疲劳复盘 AI 洞察
- 系统指令通知类 LLM 调用

本轮不覆盖：

- Garmin 按日期同步活动 FIT 文件
- Garmin 画像同步
- COROS / 高驰画像同步
- OpenClaw/QClaw skill 安装与账号授权流程改造

上述同步能力仍属于后续“数据同步脚本化 / skill 直连”专项任务。

## 2. 用户配置方式

进入脉图「配置」页，在「大模型 API 配置」中选择连接方式。

HTTP 网关模式：

- 连接方式：`HTTP 网关`
- 填写服务商、API 地址、模型、Agent ID、Gateway Token
- 点击「测试连接」

CLI 模式：

- 连接方式：`CLI`
- CLI 类型：
  - `OpenClaw CLI`
  - `Codex CLI`
  - `Claude Code`
  - `自定义 CLI`
- CLI 路径：可选。留空时使用系统 `PATH` 中的命令。
- CLI 模型：可选。留空时使用 CLI 自身默认配置。
- CLI 超时：默认 300 秒。
- CLI 参数模板：仅自定义 CLI 显示。

自定义 CLI 参数模板支持：

- `{prompt}`：脉图传入的完整对话 prompt。
- `{model}`：配置页填写的 CLI 模型。

如果自定义 CLI 参数模板未包含 `{prompt}`，后端会把 prompt 自动追加为最后一个参数。

## 3. 跨平台说明

macOS 示例：

```text
/Users/fanglei/Library/Application Support/QClaw/openclaw/config/bin/openclaw
```

Windows 示例：

```text
C:\Program Files\OpenClaw\openclaw.exe
```

注意：

- CLI 路径只填写可执行文件路径。
- 不要把 `codex exec`、`openclaw agent`、`claude -p` 这类参数写进 CLI 路径。
- 参数请写入「CLI 参数模板」。
- 后端使用 `subprocess.run(..., shell=False)`，不会通过 shell 拼接命令。

## 4. 回滚方式

本次改造在独立分支：

```bash
git branch --show-current
# codex/openclaw-cli-sync-runner
```

若要回到主分支：

```bash
git switch main
```

若确认废弃本分支改造：

```bash
git branch -D codex/openclaw-cli-sync-runner
```

如果只是想在产品内回退使用方式，不需要切分支：

1. 打开「配置」页。
2. 将连接方式切回 `HTTP 网关`。
3. 重新填写或确认 API 地址和模型。
4. 点击「测试连接」。

## 5. 本轮代码改造清单

本轮改造涉及以下文件和职责：

- `llm_backend.py`
  - 扩展 LLM 配置 schema：`transport`、`cli_type`、`cli_path`、`cli_args`、`cli_model`、`cli_timeout_sec`。
  - 新增统一入口 `generate_text(config, messages, session_id, timeout)`。
  - 保留 `chat_completions()` 作为 HTTP 兼容 wrapper。
  - 新增 CLI runner：消息序列化、命令构造、超时、非零退出、空输出和错误摘要处理。
  - 保持 `subprocess.run(..., shell=False)`。

- `main.py`
  - 扩展 `Api.test_llm_config()`，支持 HTTP / CLI 两种连接测试。
  - CLI 测试成功后保存 CLI 字段；失败不保存配置。
  - `Api.call_llm()` 改为统一通过 `_generate_llm_text()` 调用 `llm_backend.generate_text()`。
  - 保留 `sync_remote_fit_activities()` 既有 HTTP Gateway 路径，作为后续 Garmin 同步脚本化任务。
  - `set_watch_brand()`、`set_ai_notified()`、`set_ai_notified_hash()` 保留已保存的 CLI 字段，避免切换手表品牌或通知状态时覆盖配置。

- `track.html`
  - 配置页新增 `HTTP 网关 / CLI` 连接方式选择。
  - CLI 模式显示 CLI 类型、路径、模型、超时、参数模板。
  - CLI 模式隐藏 HTTP URL / model / token 字段。
  - 前端 `testLLMConfig()` 将 CLI 字段传给后端。
  - 静默验证和 TCP 心跳在 CLI 模式下避免继续探测 HTTP 端口。
  - 帮助面板同步说明 HTTP / CLI 二选一和 Garmin/COROS 边界。

- `README.md`
  - 更新用户说明，解释 HTTP 网关和 CLI 两种大模型连接方式。
  - 明确 CLI 接管 AI 私教、活动建议、雷达洞察、疲劳复盘洞察。
  - 明确 Garmin/COROS 授权、画像同步、活动同步不属于本轮 CLI 接管范围。

- `docs/llm_cli_transport_upgrade_acceptance.md`
  - 记录实施说明、验收步骤、回滚方式、已知边界和后续任务建议。

- `tests/test_llm_generate_text.py`
  - 覆盖 `generate_text()` 的 HTTP / CLI 分流。
  - 覆盖 CLI runner 超时、非零退出、空输出、自定义参数模板、Windows 带空格路径和 `shell=False`。

- `tests/test_llm_config_redaction.py`
  - 覆盖配置 redaction、旧配置兼容、CLI 字段保存、CLI 失败不保存、状态保存不覆盖 CLI 字段。

- `tests/test_call_llm_cli_transport.py`
  - 覆盖普通 AI 对话在 CLI 模式下不要求 HTTP URL/model。

- `tests/test_llm_cli_frontend_config.py`
  - 覆盖前端配置页 CLI 字段、前端测试连接传参、静默验证/心跳避开 CLI。

- `tests/test_llm_transport_contract.py`
  - 质量门：`Api.call_llm()` 禁止直接调用 HTTP wrapper，只能通过统一生成入口。

- `tests/test_activity_advice_integration.py`
  - 活动建议调用从 `chat_completions` mock 迁移到 `generate_text` mock。
  - 补充 CLI 模式不要求 HTTP URL/model 的覆盖。

- `tests/test_radar_insight_integration.py`
  - 雷达 AI 洞察调用从 `chat_completions` mock 迁移到 `generate_text` mock。
  - 补充 CLI 模式覆盖。

- `tests/test_fatigue_review_ai_insight_p6.py`
  - 疲劳复盘 AI 洞察调用从 `chat_completions` mock 迁移到 `generate_text` mock。
  - 补充 CLI 模式覆盖。

## 6. 统一自动化验收命令

本系列任务完成后，统一执行以下命令：

```bash
python3 -m pytest \
  tests/test_llm_config_redaction.py \
  tests/test_llm_cli_frontend_config.py \
  tests/test_llm_transport_contract.py \
  tests/test_llm_generate_text.py \
  tests/test_call_llm_cli_transport.py \
  tests/test_activity_advice_integration.py \
  tests/test_radar_insight_integration.py \
  tests/test_fatigue_review_ai_insight_p6.py \
  -q
```

如需要额外确认语法层面没有破坏，可追加：

```bash
python3 -m py_compile llm_backend.py main.py
```

已覆盖的质量门：

- 配置 schema 兼容旧 HTTP 配置。
- CLI 字段不会泄露 API key。
- CLI 模式测试成功后保存 CLI 字段。
- CLI 模式失败不会保存配置。
- CLI 模式下普通对话、活动建议、雷达洞察、疲劳复盘都不要求 HTTP URL/model。
- `Api.call_llm()` 禁止直接调用 HTTP wrapper。
- `Api.call_llm()` 统一通过 `_generate_llm_text()` 进入 `llm_backend.generate_text()`。
- CLI runner 支持 macOS/Windows 带空格路径。
- CLI runner 保持 `shell=False`。
- 前端 CLI 模式隐藏 HTTP URL/model/token 字段。
- HTTP 网关模式保持旧字段与旧体验。

## 7. 桌面端手工验收步骤

HTTP 模式：

- [ ] 打开配置页，选择 `HTTP 网关`。
- [ ] 填写 API 地址、模型、Token。
- [ ] 点击「测试连接」成功。
- [ ] AI 私教普通对话可返回内容。
- [ ] 活动建议可返回内容。
- [ ] 雷达 AI 洞察可返回内容。
- [ ] 疲劳复盘 AI 洞察可返回内容。

OpenClaw CLI 模式：

- [ ] 打开配置页，选择 `CLI`。
- [ ] 确认 HTTP URL/model/token 字段隐藏。
- [ ] CLI 类型选择 `OpenClaw CLI`。
- [ ] 如果 CLI 不在 `PATH` 中，填写 CLI 路径。
- [ ] 点击「测试连接」成功。
- [ ] AI 私教普通对话可返回内容。
- [ ] 活动建议可返回内容。
- [ ] 雷达 AI 洞察可返回内容。
- [ ] 疲劳复盘 AI 洞察可返回内容。
- [ ] 重启脉图后配置仍保留。
- [ ] 重启电脑后 CLI 路径仍可用。

Codex CLI 模式：

- [ ] 打开配置页，选择 `CLI`。
- [ ] CLI 类型选择 `Codex CLI`。
- [ ] 如果 `codex` 命令不在 `PATH` 中，填写完整 CLI 路径。
- [ ] 点击「测试连接」成功。
- [ ] AI 私教普通对话可返回内容。
- [ ] 活动建议可返回内容。
- [ ] 雷达 AI 洞察可返回内容。
- [ ] 疲劳复盘 AI 洞察可返回内容。
- [ ] 重启脉图后配置仍保留。

Claude Code 模式：

- [ ] 打开配置页，选择 `CLI`。
- [ ] CLI 类型选择 `Claude Code`。
- [ ] 如果 `claude` 命令不在 `PATH` 中，填写完整 CLI 路径。
- [ ] 点击「测试连接」成功。
- [ ] AI 私教普通对话可返回内容。
- [ ] 活动建议可返回内容。
- [ ] 雷达 AI 洞察可返回内容。
- [ ] 疲劳复盘 AI 洞察可返回内容。
- [ ] 重启脉图后配置仍保留。

自定义 CLI 模式：

- [ ] 打开配置页，选择 `CLI`。
- [ ] CLI 类型选择 `自定义 CLI`。
- [ ] 填写 CLI 路径。
- [ ] 如 CLI 需要固定参数，填写 CLI 参数模板。
- [ ] 确认参数模板包含 `{prompt}`，或确认后端会把 prompt 追加为最后一个参数。
- [ ] 可选填写 CLI 模型，并在参数模板中使用 `{model}`。
- [ ] 点击「测试连接」成功。
- [ ] AI 私教普通对话可返回内容。
- [ ] 活动建议可返回内容。
- [ ] 雷达 AI 洞察可返回内容。
- [ ] 疲劳复盘 AI 洞察可返回内容。

异常路径：

- [ ] CLI 类型为空时，应提示选择 CLI 类型。
- [ ] 自定义 CLI 路径为空时，应提示填写路径。
- [ ] CLI 路径误填 `codex exec`、`openclaw agent`、`claude -p` 等参数时，应提示路径栏只填写可执行文件路径。
- [ ] CLI 超时时，应显示 CLI 调用超时。
- [ ] CLI 返回非零 exit code 时，应显示错误摘要。
- [ ] CLI 返回空 stdout 时，应提示模型未返回内容。

## 8. 失败排查表

| 现象 | 可能原因 | 排查方式 |
| --- | --- | --- |
| CLI 测试失败，提示启动失败 | CLI 未安装或路径错误 | 在系统终端执行对应命令，如 `openclaw`、`codex`、`claude`；必要时填写完整路径 |
| CLI 测试失败，提示找不到命令 | CLI 不在 `PATH` 中 | 在配置页填写完整 CLI 路径 |
| CLI 测试失败，CLI 要求登录 | CLI 未登录或凭据过期 | 先在终端运行 CLI 并完成登录 |
| CLI 测试失败，提示 CLI 路径只能填写可执行文件路径 | 把命令参数误填进 CLI 路径 | CLI 路径只填可执行文件；参数写到 CLI 参数模板 |
| CLI 调用超时 | CLI 启动慢、模型响应慢、网络慢 | 增大 CLI 超时，或先在终端确认 CLI 响应速度 |
| CLI 返回空内容 | CLI 命令执行成功但 stdout 为空 | 检查 CLI 参数模板是否要求输出到 stdout |
| CLI 返回非零 exit code | CLI 自身报错 | 查看错误摘要，必要时在终端复现同一命令 |
| HTTP 网关测试失败 | 端口变化、网关未启动、API 地址为空 | 重新确认 OpenClaw / QClaw Gateway 地址、端口、模型和 Token |
| HTTP 心跳提示网关端口不可达 | 网关端口变化或进程退出 | 重启网关并重新测试连接 |
| Garmin 同步失败但 AI CLI 正常 | Garmin 同步仍走既有 OpenClaw Gateway / skill 路径 | 检查 Garmin skill、账号授权、存储规范和 HTTP Gateway；这不代表 AI CLI 配置失败 |
| COROS 画像字段为空 | COROS 授权、Training Hub 登录态或页面结构问题 | 检查 COROS MCP 授权和本机 Chrome Training Hub 登录态 |

## 9. 后续任务建议

建议后续拆成独立任务继续推进：

- Garmin 活动同步脚本化：绕开 OpenClaw HTTP Gateway，直接调用受控脚本或 skill runner。
- Garmin 画像同步脚本化：把用户画像同步从大模型对话通道中剥离。
- COROS / 高驰画像同步脚本化：明确 MCP 授权、Training Hub 登录态和返回字段契约。
- OpenClaw CLI 默认命令真实校验：确认 `openclaw agent --message {prompt}` 是否为实际可用命令，如不匹配则调整默认模板。
- CLI 错误提示进一步细化：区分未安装、未登录、权限不足、模型不可用、stdout 为空等情况。
- 静默验证轻量化：评估 CLI 模式启动时是否需要真实发起一次模型调用，或改为可选健康检查。

## 10. 已知边界

- 当前 CLI 调用采用一次性 prompt 方式，不实现长连接会话协议。
- 不同 CLI 对 prompt 参数的官方语法可能不同，自定义 CLI 通过参数模板兜底。
- CLI 的账号登录、模型选择、权限授权仍由对应 CLI 自身负责。
- Garmin/COROS 授权仍由现有 skill 或后续专项任务处理。
- Garmin 按日期活动同步当前仍走既有 OpenClaw Gateway 路径，后续需要单独改造成脚本/skill 直连。

## 11. 建议手工验收执行顺序

验收前准备：

1. 确认当前分支为 `codex/openclaw-cli-sync-runner`。
2. 确认任务 17 的自动化回归已通过。
3. 准备至少一个可打开详情页和复盘页的活动。
4. 在系统终端分别确认要测试的 CLI 已安装并已登录，例如 `openclaw`、`codex`、`claude`。
5. 如果 CLI 不在 `PATH` 中，提前准备完整可执行文件路径；路径栏只填可执行文件，不填参数。

必测路径：

| 模式 | 测试项 | 结果 | 备注 |
| --- | --- | --- | --- |
| HTTP 网关 | 测试连接 | 待测 | 确认旧网关模式仍可用 |
| HTTP 网关 | AI 私教普通对话 | 待测 | 返回内容即可 |
| HTTP 网关 | 活动建议 | 待测 | 有活动快照时验证 |
| HTTP 网关 | 雷达 AI 洞察 | 待测 | 有 90 天画像数据时验证 |
| HTTP 网关 | 疲劳复盘 AI 洞察 | 待测 | 有复盘数据时验证 |
| CLI / OpenClaw | 测试连接 | 通过 | 2026-07-01 实机验证，支持空 CLI 路径自动回落 QClaw wrapper |
| CLI / OpenClaw | OpenClaw Agent ID | 通过 | `agent_id` 透传到 `openclaw agent --agent ...`，留空使用 `main` |
| CLI / OpenClaw | HTTP 字段隐藏 | 通过 | URL、模型、Token 不要求填写 |
| CLI / OpenClaw | AI 私教普通对话 | 通过 | 用户实测由 CLI 返回 |
| CLI / OpenClaw | 活动建议 | 通过 | 用户实测不再提示未配置 API |
| CLI / OpenClaw | 雷达 AI 洞察 | 通过 | CLI 模式下不要求 HTTP 配置 |
| CLI / OpenClaw | 疲劳复盘 AI 洞察 | 通过 | CLI 模式下不要求 HTTP 配置 |

可选路径：

| 模式 | 测试项 | 结果 | 备注 |
| --- | --- | --- | --- |
| CLI / Codex | 测试连接 | 通过 | 用户实测 Codex CLI 可用 |
| CLI / Codex | AI 私教普通对话 | 通过 | 用户实测由 CLI 返回 |
| CLI / Codex | 活动建议 / AI 洞察 / AI 复盘 | 通过 | 用户实测均已走 CLI |
| CLI / Claude Code | 测试连接 | 待测 | 先在终端确认 `claude` 可用 |
| CLI / Claude Code | AI 私教普通对话 | 待测 | 可作为 CLI 稳定性对照 |
| CLI / 自定义 | 参数模板包含 `{prompt}` | 待测 | 验证模板替换 |
| CLI / 自定义 | 参数模板不含 `{prompt}` | 待测 | 验证后端自动追加 prompt |
| CLI / Windows | 带空格路径 | 待测 | 在 Windows 设备上验证 `C:\Program Files\...` |
| CLI / macOS | 带空格路径 | 待测 | 例如 `/Users/.../Application Support/.../openclaw` |
| CLI / 配置修改 | 状态回到需重新测试 | 已覆盖自动化测试 | 修改 CLI 类型、路径、Agent ID、模型或超时后不再沿用旧测试状态 |
| CLI / 静默验证 | 不覆盖未保存表单 | 已覆盖自动化测试 | 静默验证只给当前已保存配置背书 |

异常路径：

| 场景 | 期望结果 | 结果 | 备注 |
| --- | --- | --- | --- |
| CLI 类型为空 | 提示选择 CLI 类型 | 待测 | 不应继续测试连接 |
| 自定义 CLI 路径为空 | 提示填写路径 | 待测 | 不应继续测试连接 |
| CLI 路径误填 `codex exec` | 提示路径只填可执行文件 | 待测 | 参数写入 CLI 参数模板 |
| CLI 未登录 | 连接测试失败并给出错误 | 待测 | 先在终端完成登录 |
| CLI 未安装或路径错误 | 显示未找到对应 CLI | 已覆盖自动化测试 | Codex/Claude/OpenClaw 分别给出安装或路径提示 |
| OpenClaw Agent 不存在 | 提示 Agent 不存在或不可用 | 已覆盖自动化测试 | 检查 Agent ID |
| CLI 超时 | 显示 CLI 已启动但模型未在超时时间内返回 | 已覆盖自动化测试 | 可临时调低超时或使用慢命令 |
| CLI 返回空 stdout | 提示模型未返回内容 | 待测 | 自定义 CLI 常见 |
| CLI 返回非零 exit code | 显示错误摘要 | 待测 | 自定义 CLI 常见 |

失败归因规则：

- AI 私教、活动建议、雷达 AI 洞察、疲劳复盘 AI 洞察失败，优先归因到当前大模型连接方式。
- 选择 CLI 后仍要求填写 HTTP URL、模型或 Token，归因到 CLI 接管改造问题。
- Garmin 活动同步失败但 AI CLI 正常，归因到 Garmin Gateway / skill / 授权 / 存储规范，不归因到 CLI 大模型通道。
- Garmin/COROS 画像为空，归因到对应 skill、账号授权、Training Hub 登录态或平台接口变化，不归因到 CLI 大模型通道。
- OpenClaw CLI 测试失败时，先在系统终端验证真实命令语法；默认命令尚未完成真实确认，不能直接判定为脉图 UI 问题。
