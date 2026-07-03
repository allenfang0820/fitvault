#!/bin/bash
# coros-stats skill: COROS MCP 安装脚本
# 用法: bash install_coros_mcp.sh [--region cn|us|eu] [--issuer URL] [--help]
# 默认 issuer: https://mcpcn.coros.com (中国区)
# 北美或其他地区: bash install_coros_mcp.sh --region us
# 欧洲区: bash install_coros_mcp.sh --region eu

set -e

ISSUER="https://mcpcn.coros.com"
REGION="cn"
LOGIN_DONE=0
NODE_BIN=""
NPM_BIN=""

find_node_binary() {
  if [ -n "${QCLAW_CLI_NODE_BINARY:-}" ] && [ -x "$QCLAW_CLI_NODE_BINARY" ]; then
    echo "$QCLAW_CLI_NODE_BINARY"
    return 0
  fi
  if [ -n "${MAITU_BUNDLED_NODE_DIR:-}" ] && [ -x "$MAITU_BUNDLED_NODE_DIR/bin/node" ]; then
    echo "$MAITU_BUNDLED_NODE_DIR/bin/node"
    return 0
  fi

  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local bundled_node
  for bundled_node in \
    "$script_dir/../../../node/bin/node" \
    "$script_dir/../../../../node/bin/node" \
    "$script_dir/../../../Resources/node/bin/node"
  do
    if [ -x "$bundled_node" ]; then
      echo "$bundled_node"
      return 0
    fi
  done

  if command -v node &>/dev/null; then
    command -v node
    return 0
  fi

  local candidate
  for candidate in \
    "$HOME"/.nvm/versions/node/*/bin/node \
    "/opt/homebrew/bin/node" \
    "/usr/local/bin/node" \
    "$HOME/Library/Application Support/QClaw/openclaw/config/bin/node"
  do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

find_openclaw_mjs() {
  if [ -n "${QCLAW_CLI_OPENCLAW_MJS:-}" ] && [ -f "$QCLAW_CLI_OPENCLAW_MJS" ]; then
    echo "$QCLAW_CLI_OPENCLAW_MJS"
    return 0
  fi

  local candidate
  for candidate in \
    "$HOME/Library/Application Support/QClaw/openclaw/node_modules/openclaw/openclaw.mjs" \
    "$HOME/Library/Application Support/QClaw/openclaw/openclaw.mjs"
  do
    if [ -f "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

configure_node_runtime() {
  NODE_BIN="$(find_node_binary || true)"
  if [ -z "$NODE_BIN" ]; then
    echo "[错误] 未检测到 Node.js。请确认脉图应用包完整，或手动安装 Node.js (https://nodejs.org)"
    exit 1
  fi
  export PATH="$(dirname "$NODE_BIN"):$PATH"
  export QCLAW_CLI_NODE_BINARY="$NODE_BIN"
  export MAITU_BUNDLED_NODE_DIR="$(cd "$(dirname "$NODE_BIN")/.." && pwd)"
  export NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-$HOME/.maitu/node-global}"
  mkdir -p "$NPM_CONFIG_PREFIX/bin"
  export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"

  if ! NPM_BIN="$(command -v npm 2>/dev/null)"; then
    echo "[错误] 未检测到 npm。请使用包含完整 Node.js runtime 的脉图安装包，或手动安装 Node.js。"
    exit 1
  fi
}

prepare_openclaw_runtime() {
  if ! command -v openclaw &>/dev/null; then
    echo "[提示] 未检测到 openclaw 命令，跳过 OpenClaw 注册。"
    return 1
  fi

  if [ -z "${QCLAW_CLI_NODE_BINARY:-}" ]; then
    export QCLAW_CLI_NODE_BINARY="$NODE_BIN"
  fi
  if [ -z "${QCLAW_CLI_OPENCLAW_MJS:-}" ]; then
    local openclaw_mjs
    openclaw_mjs="$(find_openclaw_mjs || true)"
    if [ -n "$openclaw_mjs" ]; then
      export QCLAW_CLI_OPENCLAW_MJS="$openclaw_mjs"
    fi
  fi

  if [ -z "${QCLAW_CLI_OPENCLAW_MJS:-}" ]; then
    echo "[提示] 未找到 OpenClaw 入口 openclaw.mjs，跳过 OpenClaw 注册。"
    return 1
  fi
  return 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --region=*) REGION="${1#*=}" ;;
    --region)   shift; REGION="$1" ;;
    --issuer=*) ISSUER="${1#*=}"; REGION="custom" ;;
    --issuer)   shift; ISSUER="$1"; REGION="custom" ;;
    --help|-h)
      echo "用法: bash install_coros_mcp.sh [--region cn|us|eu] [--issuer URL]"
      echo ""
      echo "区域映射："
      echo "  cn: https://mcpcn.coros.com/mcp"
      echo "  us: https://mcpus.coros.com/mcp"
      echo "  eu: https://mcpeu.coros.com/mcp"
      echo ""
      echo "示例："
      echo "  bash install_coros_mcp.sh --region cn"
      echo "  bash install_coros_mcp.sh --issuer https://mcpcn.coros.com"
      exit 0
      ;;
    *)
      echo "[错误] 未知参数: $1"
      echo "运行 --help 查看用法。"
      exit 1
      ;;
  esac
  shift
done

if [ "$REGION" != "custom" ]; then
  case "$REGION" in
    cn) ISSUER="https://mcpcn.coros.com" ;;
    us) ISSUER="https://mcpus.coros.com" ;;
    eu) ISSUER="https://mcpeu.coros.com" ;;
    *)
      echo "[错误] 不支持的 region: $REGION"
      echo "支持: cn / us / eu"
      exit 1
      ;;
  esac
fi

echo "=========================================="
echo "  COROS MCP 安装向导"
echo "=========================================="
echo "Region: $REGION"
echo "Issuer: $ISSUER"
echo "MCP URL: $ISSUER/mcp"
echo ""

# 1. 检查 node/npm
configure_node_runtime
echo "[1/5] Node.js $("$NODE_BIN" -v) / npm $("$NPM_BIN" -v) ✓"

# 2. 安装 coros-mcp
if command -v coros-mcp &>/dev/null; then
  echo "[2/5] coros-mcp 已安装 ($(coros-mcp --version 2>/dev/null || echo 'unknown')) ✓"
else
  echo "[2/5] 正在安装 coros-mcp..."
  npm install -g coros-mcp
  echo "[2/5] coros-mcp 安装完成 ✓"
fi

# 3. OAuth 登录
echo ""
echo "[3/5] COROS 账号授权"
echo "--------------------------------------------------"
echo "接下来会自动打开浏览器，请在浏览器中登录 COROS 账号并授权。"
echo "授权完成后，回到此处继续。"
echo "--------------------------------------------------"
read -p "按 Enter 开始授权..." DUMMY

if coros-mcp --issuer "$ISSUER" login; then
  echo ""
  echo "[3/5] COROS 账号授权成功 ✓"
  LOGIN_DONE=1
else
  echo ""
  echo "[警告] 授权可能未完成，请检查浏览器。"
  exit 1
fi

# 4. 注册到 OpenClaw
echo ""
echo "[4/5] 正在注册 COROS MCP 到 OpenClaw..."
if prepare_openclaw_runtime && coros-mcp --issuer "$ISSUER" apply-openclaw; then
  echo "[4/5] OpenClaw 注册成功 ✓"
else
  echo "[警告] COROS 账号授权已成功，但 OpenClaw 注册失败或被跳过。"
  echo "       这不会影响脉图读取已授权的 COROS token；如需在 OpenClaw 中使用 COROS MCP，请检查 QCLAW_CLI_NODE_BINARY / QCLAW_CLI_OPENCLAW_MJS。"
  if [ "$LOGIN_DONE" -eq 0 ]; then
    exit 1
  fi
  exit 0
fi

# 5. 重启网关
echo ""
echo "[5/5] 重启 OpenClaw 网关..."
if openclaw gateway restart; then
  echo "[5/5] OpenClaw 网关已重启 ✓"
else
  echo "[警告] OpenClaw 网关重启失败；COROS 账号授权已成功，可稍后手动重启 OpenClaw。"
fi

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "可用工具已就绪，试试说："
echo "  「查询我的跑步档案」"
echo "  「返回所有运动指标 JSON」"
