@echo off
setlocal EnableExtensions

set "ISSUER=https://mcpcn.coros.com"
set "REGION=cn"
set "LOGIN_DONE=0"
set "NODE_BIN="
set "NPM_BIN="

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--region" (
  set "REGION=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--issuer" (
  set "ISSUER=%~2"
  set "REGION=custom"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
echo [错误] 未知参数: %~1
echo 运行 --help 查看用法。
exit /b 1

:help
echo 用法: install_coros_mcp.cmd [--region cn^|us^|eu] [--issuer URL]
echo.
echo 区域映射:
echo   cn: https://mcpcn.coros.com/mcp
echo   us: https://mcpus.coros.com/mcp
echo   eu: https://mcpeu.coros.com/mcp
exit /b 0

:args_done
if /I not "%REGION%"=="custom" (
  if /I "%REGION%"=="cn" set "ISSUER=https://mcpcn.coros.com"
  if /I "%REGION%"=="us" set "ISSUER=https://mcpus.coros.com"
  if /I "%REGION%"=="eu" set "ISSUER=https://mcpeu.coros.com"
  if /I not "%REGION%"=="cn" if /I not "%REGION%"=="us" if /I not "%REGION%"=="eu" (
    echo [错误] 不支持的 region: %REGION%
    echo 支持: cn / us / eu
    exit /b 1
  )
)

call :configure_node_runtime || exit /b 1

echo ==========================================
echo   COROS MCP 安装向导
echo ==========================================
echo Region: %REGION%
echo Issuer: %ISSUER%
echo MCP URL: %ISSUER%/mcp
echo.
for /f "usebackq delims=" %%v in (`"%NODE_BIN%" -v`) do set "NODE_VERSION_TEXT=%%v"
for /f "usebackq delims=" %%v in (`"%NPM_BIN%" -v`) do set "NPM_VERSION_TEXT=%%v"
echo [1/5] Node.js %NODE_VERSION_TEXT% / npm %NPM_VERSION_TEXT% OK

where coros-mcp.cmd >nul 2>nul
if errorlevel 1 (
  echo [2/5] 正在安装 coros-mcp...
  call "%NPM_BIN%" install -g coros-mcp || exit /b 1
  echo [2/5] coros-mcp 安装完成 OK
) else (
  echo [2/5] coros-mcp 已安装 OK
)

echo.
echo [3/5] COROS 账号授权
echo --------------------------------------------------
echo 接下来会自动打开浏览器，请在浏览器中登录 COROS 账号并授权。
echo 授权完成后，回到此处继续。
echo --------------------------------------------------
pause

coros-mcp.cmd --issuer "%ISSUER%" login
if errorlevel 1 (
  echo.
  echo [警告] 授权可能未完成，请检查浏览器。
  exit /b 1
)
echo.
echo [3/5] COROS 账号授权成功 OK
set "LOGIN_DONE=1"

echo.
echo [4/5] 正在注册 COROS MCP 到 OpenClaw...
where openclaw.cmd >nul 2>nul
if errorlevel 1 (
  echo [提示] 未检测到 openclaw 命令，跳过 OpenClaw 注册。
  exit /b 0
)
coros-mcp.cmd --issuer "%ISSUER%" apply-openclaw
if errorlevel 1 (
  echo [警告] COROS 账号授权已成功，但 OpenClaw 注册失败或被跳过。
  echo        这不会影响脉图读取已授权的 COROS token。
  exit /b 0
)
echo [4/5] OpenClaw 注册成功 OK

echo.
echo [5/5] 重启 OpenClaw 网关...
openclaw.cmd gateway restart
if errorlevel 1 (
  echo [警告] OpenClaw 网关重启失败；COROS 账号授权已成功，可稍后手动重启 OpenClaw。
) else (
  echo [5/5] OpenClaw 网关已重启 OK
)

echo.
echo ==========================================
echo   安装完成！
echo ==========================================
exit /b 0

:configure_node_runtime
if defined QCLAW_CLI_NODE_BINARY if exist "%QCLAW_CLI_NODE_BINARY%" (
  set "NODE_BIN=%QCLAW_CLI_NODE_BINARY%"
  goto node_found
)
if defined MAITU_BUNDLED_NODE_DIR if exist "%MAITU_BUNDLED_NODE_DIR%\node.exe" (
  set "NODE_BIN=%MAITU_BUNDLED_NODE_DIR%\node.exe"
  goto node_found
)
if defined MAITU_BUNDLED_NODE_DIR if exist "%MAITU_BUNDLED_NODE_DIR%\bin\node.exe" (
  set "NODE_BIN=%MAITU_BUNDLED_NODE_DIR%\bin\node.exe"
  goto node_found
)
set "SCRIPT_DIR=%~dp0"
for %%P in (
  "%SCRIPT_DIR%..\..\..\node\node.exe"
  "%SCRIPT_DIR%..\..\..\node\bin\node.exe"
  "%SCRIPT_DIR%..\..\..\Resources\node\node.exe"
) do (
  if exist "%%~fP" (
    set "NODE_BIN=%%~fP"
    goto node_found
  )
)
for %%P in (node.exe) do (
  set "NODE_BIN=%%~$PATH:P"
)
if defined NODE_BIN goto node_found
echo [错误] 未检测到 Node.js。请确认脉图应用包完整，或手动安装 Node.js (https://nodejs.org)
exit /b 1

:node_found
for %%P in ("%NODE_BIN%") do set "NODE_DIR=%%~dpP"
set "PATH=%NODE_DIR%;%PATH%"
set "QCLAW_CLI_NODE_BINARY=%NODE_BIN%"
if not defined MAITU_BUNDLED_NODE_DIR set "MAITU_BUNDLED_NODE_DIR=%NODE_DIR:~0,-1%"
if not defined NPM_CONFIG_PREFIX set "NPM_CONFIG_PREFIX=%USERPROFILE%\.maitu\node-global"
if not exist "%NPM_CONFIG_PREFIX%" mkdir "%NPM_CONFIG_PREFIX%" >nul 2>nul
set "PATH=%NPM_CONFIG_PREFIX%;%PATH%"
if exist "%NODE_DIR%npm.cmd" (
  set "NPM_BIN=%NODE_DIR%npm.cmd"
) else (
  for %%P in (npm.cmd) do set "NPM_BIN=%%~$PATH:P"
)
if not defined NPM_BIN (
  echo [错误] 未检测到 npm。请使用包含完整 Node.js runtime 的脉图安装包，或手动安装 Node.js。
  exit /b 1
)
exit /b 0
