# 账号连接中心中期方案任务简报

## 背景

请在 FitVault/脉图 项目中设计并实现“账号连接中心”中期方案。

当前 Garmin/COROS 授权入口在配置页分别调用 `start_garmin_login` / `start_coros_login`，macOS/Windows 会打开 Terminal/cmd；Windows Garmin 还依赖 `FitVaultCLI.exe` 作为 console helper。

产品目标是让用户感知为统一的账号连接中心，不再暴露终端/配套程序。

## 必读代码与契约

请先阅读当前代码与契约：

- `main.py`
- `garmin_sync.py`
- `coros_sync.py`
- `track.html`
- `docs/js_api_contract.json`
- `HikingTrackAnalyzer.spec`
- `skills/garmin-stats/scripts/garmin_auth.py`
- `skills/coros-stats/scripts/install_coros_mcp.*`
- `skills/coros-stats/scripts/coros-mcp-keepalive.js`
- 相关测试

## 目标设计

1. 前端配置页将零散授权入口升级为“账号连接中心”：Garmin/COROS 统一连接卡，展示品牌、区域、状态、连接/重新连接/断开/检查状态。

2. 后端新增统一账号连接 API 契约，建议命名：
   - `list_account_connections`
   - `check_account_connection(provider, region)`
   - `start_account_connection(provider, region, payload)`
   - `continue_account_connection(session_id, payload)`
   - `disconnect_account(provider, region)`

   如果发现更贴合现有风格的命名，可以调整，但必须更新 `docs/js_api_contract.json` 和测试。

3. 统一状态机至少覆盖：
   - `idle`
   - `checking`
   - `needs_credentials`
   - `needs_mfa`
   - `opening_browser`
   - `waiting_callback`
   - `authorized`
   - `failed`
   - `expired`

4. Garmin 中期优先实现完整 App 内授权：账号、密码、MFA 输入在脉图内完成，token 保存到现有 `default_tokenstore` 路径，授权成功后复用现有 `check_garmin_auth_status`。

   调研结果：当前 `garmin_auth.login_and_save` 可被后端直接调用；底层 `garth.sso.login` 支持 `prompt_mfa` 回调。但也请评估是否升级 `garminconnect>=0.3.0` 更合适，若升级风险较大，先用现有 garth `prompt_mfa` 做最小可交付。

5. COROS 中期实现无终端连接向导：保留官方 MCP/OAuth 方向，不改为非官方账号密码登录。把当前 `install_coros_mcp` 脚本拆解或封装为后台流程：检查/使用内置 Node+npm，安装/检查 `coros-mcp`，打开系统浏览器让用户完成 OAuth，App 内轮询 token 文件状态；OpenClaw 注册作为可选增强项，不阻塞脉图自身同步。

6. 不要重写活动同步、FIT 导入、画像同步主链路。只替换授权入口和状态/连接管理，现有 sync/download/profile provider 尽量复用。

7. Windows 用户体验目标：Garmin 授权不再需要用户感知 `FitVaultCLI.exe`；若实现后不再需要 console helper，请移除或降级它在 spec 中的必要性。COROS 不应弹空白终端，进度和错误应在 App 内展示。

8. macOS 用户体验目标：同步画像或授权不应再额外打开新的脉图窗口或 Terminal，除非 COROS OAuth 必须打开系统浏览器。

9. 安全要求：不要在日志、错误、契约返回值中泄露账号密码、MFA、token；前端密码框清空策略要合理；错误提示保留可操作诊断但脱敏。

10. 验证要求：补充/更新单元测试和前端契约测试；至少覆盖 Garmin App 内授权成功、MFA 分支、失败脱敏、COROS 连接向导状态、Windows 不依赖 `FitVaultCLI` 的路径。运行相关 pytest。完成后总结是否还需要重新打包验证。

## 执行方式

先做一次源码审阅并给出简短实现计划，然后按计划实现。

不要做无关 UI 重构，不要改动数据同步核心算法。
