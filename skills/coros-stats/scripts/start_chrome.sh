#!/usr/bin/env bash
# start_chrome.sh - 跨平台启动带远程调试端口的 Chrome
#
# 用法:
#   bash start_chrome.sh                  # 默认端口 9222, 默认用户目录
#   bash start_chrome.sh --port 9223      # 自定义端口
#   bash start_chrome.sh --user-data-dir /path
#   bash start_chrome.sh --stop           # 关闭 debug Chrome 进程
#   bash start_chrome.sh --status         # 查看 debug Chrome 状态
#   bash start_chrome.sh --open-url URL   # 启动后自动打开 URL

set -e

PORT=9222
ACTION="start"
OPEN_URL=""

# === 默认用户目录 (隔离 debug 会话, 不影响正常 Chrome) ===
case "$(uname -s)" in
  Darwin*)
    DEFAULT_USER_DATA_DIR="$HOME/Library/Application Support/ChromeDebug"
    ;;
  Linux*)
    DEFAULT_USER_DATA_DIR="$HOME/.config/chrome-debug"
    ;;
  MINGW*|CYGWIN*|MSYS*)
    DEFAULT_USER_DATA_DIR="/c/Users/${USERNAME}/AppData/Local/Google/Chrome/User Data Debug"
    ;;
  *)
    DEFAULT_USER_DATA_DIR=""
    ;;
esac

USER_DATA_DIR="$DEFAULT_USER_DATA_DIR"

# === 解析参数 ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --user-data-dir) USER_DATA_DIR="$2"; shift 2 ;;
    --stop) ACTION="stop"; shift ;;
    --status) ACTION="status"; shift ;;
    --open-url) OPEN_URL="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# === 平台检测 ===
case "$(uname -s)" in
  Darwin*)    PLATFORM="macos" ;;
  Linux*)     PLATFORM="linux" ;;
  MINGW*|CYGWIN*|MSYS*) PLATFORM="windows" ;;
  *)          echo "✗ 不支持的平台: $(uname -s)" >&2; exit 1 ;;
esac

# === 状态查询 ===
check_status() {
  if curl -s --max-time 2 "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
    local ver tabs
    ver=$(curl -s "http://localhost:$PORT/json/version" 2>/dev/null | \
      grep -oE '"Browser":\s*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
    tabs=$(curl -s "http://localhost:$PORT/json" 2>/dev/null | \
      grep -cE '"type":\s*"page"' || echo 0)
    echo "✓ Chrome DevTools 正在监听 :$PORT"
    echo "  浏览器: $ver"
    echo "  页面标签数: $tabs"
    # 检查 COROS 登录态
    local login_status
    login_status=$(curl -s "http://localhost:$PORT/json" 2>/dev/null | \
      grep -oE '"url":\s*"[^"]*coros\.com[^"]*"' | head -3)
    if [[ -n "$login_status" ]]; then
      echo "  COROS 标签页:"
      echo "$login_status" | sed 's/^/    /'
    else
      echo "  ⚠ 未发现已打开的 coros.com 标签页"
    fi
  else
    echo "✗ 端口 :$PORT 上未发现 Chrome DevTools"
    echo "  修复: 运行 'bash $0' 启动 debug Chrome"
  fi
}

# === 关闭 debug Chrome ===
stop_chrome() {
  case "$PLATFORM" in
    macos)
      osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true
      ;;
    linux)
      pkill -f "remote-debugging-port=$PORT" 2>/dev/null || true
      ;;
    windows)
      taskkill //F //IM chrome.exe //FI "PID gt 1000" 2>/dev/null || true
      ;;
  esac
  sleep 1
  echo "✓ Chrome 调试会话已关闭"
}

# === 找 Chrome 可执行文件 ===
find_chrome() {
  case "$PLATFORM" in
    macos)
      for app in "/Applications/Google Chrome.app" \
                 "/Applications/Google Chrome Beta.app" \
                 "/Applications/Google Chrome Dev.app" \
                 "/Applications/Chromium.app"; do
        if [[ -d "$app" ]]; then
          echo "$app/Contents/MacOS/Google Chrome"
          return 0
        fi
      done
      return 1
      ;;
    linux)
      for c in google-chrome google-chrome-stable chromium chromium-browser; do
        if command -v "$c" >/dev/null 2>&1; then
          echo "$c"; return 0
        fi
      done
      for p in /opt/google/chrome/chrome /usr/bin/google-chrome \
               /snap/bin/chromium /usr/bin/chromium-browser; do
        [[ -x "$p" ]] && echo "$p" && return 0
      done
      return 1
      ;;
    windows)
      # Git Bash / MSYS: 优先 chrome.exe (PATH), 后备绝对路径
      if command -v chrome.exe >/dev/null 2>&1; then
        echo "chrome.exe"; return 0
      fi
      for p in "/c/Program Files/Google/Chrome/Application/chrome.exe" \
               "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"; do
        [[ -x "$p" ]] && echo "$p" && return 0
      done
      return 1
      ;;
  esac
}

# === 启动 debug Chrome ===
start_chrome() {
  local chrome
  chrome=$(find_chrome) || {
    echo "✗ 未找到 Chrome，请先安装 Google Chrome。" >&2
    case "$PLATFORM" in
      macos) echo "  → https://www.google.com/chrome/" ;;
      linux) echo "  → sudo apt install google-chrome-stable" ;;
      windows) echo "  → https://www.google.com/chrome/" ;;
    esac
    exit 1
  }

  # 先检查端口是否被占
  if curl -s --max-time 1 "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
    echo "⚠ 端口 $PORT 已有 Chrome 在运行，当前状态如下:"
    echo
    check_status
    echo
    echo "如要重启: 'bash $0 --stop' 然后再跑 'bash $0'"
    exit 0
  fi

  echo "▶ 正在以调试端口 $PORT 启动 Chrome"
  echo "  可执行文件: $chrome"
  echo "  用户数据目录: $USER_DATA_DIR"
  mkdir -p "$USER_DATA_DIR"

  # 关闭任何残留 Chrome (防止 lock file)
  case "$PLATFORM" in
    macos) osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true ;;
    linux) pkill -f "google-chrome.*remote-debugging" 2>/dev/null || true ;;
    windows) taskkill //F //IM chrome.exe //FI "PID gt 1000" 2>/dev/null || true ;;
  esac
  sleep 1

  # 启动
  case "$PLATFORM" in
    macos)
      "$chrome" \
        --remote-debugging-port=$PORT \
        --remote-allow-origins='*' \
        --user-data-dir="$USER_DATA_DIR" \
        --no-first-run --no-default-browser-check \
        --disable-background-timer-throttling \
        ${OPEN_URL:+"$OPEN_URL"} \
        >/dev/null 2>&1 &
      ;;
    linux)
      nohup "$chrome" \
        --remote-debugging-port=$PORT \
        --remote-allow-origins='*' \
        --user-data-dir="$USER_DATA_DIR" \
        --no-first-run --no-default-browser-check \
        --disable-background-timer-throttling \
        ${OPEN_URL:+"$OPEN_URL"} \
        >/dev/null 2>&1 &
      ;;
    windows)
      # Windows Git Bash 需要双斜杠转义 flag
      "$chrome" \
        --remote-debugging-port=$PORT \
        --remote-allow-origins=* \
        --user-data-dir="$(cygpath -w "$USER_DATA_DIR" 2>/dev/null || echo "$USER_DATA_DIR")" \
        --no-first-run --no-default-browser-check \
        --disable-background-timer-throttling \
        ${OPEN_URL:+"$OPEN_URL"} \
        >/dev/null 2>&1 &
      ;;
  esac

  # 等 DevTools 上线
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.5
    if curl -s --max-time 1 "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
      echo "✓ Chrome DevTools 已启动，端口 :$PORT"
      echo
      check_status
      echo
      if [[ -z "$OPEN_URL" ]]; then
        echo "下一步: 在新打开的 Chrome 中访问 https://t.coros.com 并完成登录"
        echo "  登录完成后运行:  bash $0 --status  确认 COROS tab 出现"
      else
        echo "已自动打开: $OPEN_URL"
      fi
      return
    fi
  done

  echo "✗ Chrome 已启动，但 DevTools 端口 $PORT 在 5 秒内无响应"
  echo "  可能原因:"
  echo "  - 防火墙拦截 (试: --port 9223)"
  echo "  - 系统已有其他 Chrome 占用 (试: pkill -f Chrome)"
  exit 1
}

# === 主入口 ===
echo "▶ 平台: $PLATFORM | 端口: $PORT | 动作: $ACTION"
echo
case "$ACTION" in
  start) start_chrome ;;
  stop) stop_chrome ;;
  status) check_status ;;
  *) echo "未知动作: $ACTION" >&2; exit 1 ;;
esac
