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
if ! command -v node &>/dev/null; then
  echo "[错误] 未检测到 Node.js，请先安装 Node.js (https://nodejs.org)"
  exit 1
fi
if ! command -v npm &>/dev/null; then
  echo "[错误] 未检测到 npm"
  exit 1
fi
echo "[1/5] Node.js $(node -v) / npm $(npm -v) ✓"

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

coros-mcp --issuer "$ISSUER" login

echo ""
if [ $? -eq 0 ]; then
  echo "[3/5] COROS 账号授权成功 ✓"
  LOGIN_DONE=1
else
  echo "[警告] 授权可能未完成，请检查浏览器。"
fi

# 4. 注册到 OpenClaw
echo ""
echo "[4/5] 正在注册 COROS MCP 到 OpenClaw..."
coros-mcp --issuer "$ISSUER" apply-openclaw

if [ $? -eq 0 ]; then
  echo "[4/5] OpenClaw 注册成功 ✓"
else
  echo "[错误] OpenClaw 注册失败"
  exit 1
fi

# 5. 重启网关
echo ""
echo "[5/5] 重启 OpenClaw 网关..."
openclaw gateway restart

echo ""
echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "可用工具已就绪，试试说："
echo "  「查询我的跑步档案」"
echo "  「返回所有运动指标 JSON」"
