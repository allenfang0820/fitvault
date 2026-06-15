#!/usr/bin/env node
/**
 * coros_traininghub_login.js - Training Hub (t.coros.com) 登录辅助
 *
 * 工作流程：
 * 1. 启动 OpenClaw 管理的 Chrome（profile=openclaw）
 * 2. 打开 https://t.coros.com/admin/views/dash-board
 * 3. 用户在浏览器里手动登录（OAuth/SSO/手机号/邮箱）
 * 4. 等待 cookie "CPL-coros-token" 出现
 * 5. 保存到 ~/.qclaw/coros-traininghub-token.json
 *
 * 用法：node coros_traininghub_login.js
 *
 * 备注：t.coros.com 用的 token 是 JWT，存到 .coros.com 域下的 cookie "CPL-coros-token"。
 * COROS MCP 的 token 走 OAuth 不同的 scope，不能直接用。
 */

const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

const TOKEN_PATH = path.join(process.env.HOME, '.qclaw', 'coros-traininghub-token.json');
const URL = 'https://t.coros.com/admin/views/dash-board';

// 检测 chrome CDP 端口（OpenClaw 启动的）
function detectChromePort() {
  try {
    // 读 OpenClaw 浏览器状态
    const result = execSync('curl -s http://127.0.0.1:50435/ 2>/dev/null || echo ""', { encoding: 'utf-8' });
    if (result.includes('Chrome')) return 50435;
  } catch {}
  // 兜底：扫描常见端口
  for (const port of [50435, 50436, 9222, 9223]) {
    try {
      const r = execSync(`curl -s http://127.0.0.1:${port}/json/version`, { encoding: 'utf-8' });
      if (r.includes('Browser')) return port;
    } catch {}
  }
  throw new Error('找不到 Chrome DevTools 端口（OpenClaw 浏览器未启动？）');
}

async function getCookie(port) {
  // 用 CDP 拿所有 cookie，过滤 t.coros.com / .coros.com
  const targets = execSync(`curl -s http://127.0.0.1:${port}/json/list`, { encoding: 'utf-8' });
  const list = JSON.parse(targets);
  if (!list.length) throw new Error('Chrome 已启动，但没有可用页面标签页');
  const wsUrl = list[0].webSocketDebuggerUrl;
  const WebSocket = require('ws');
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.once('open', resolve);
    ws.once('error', reject);
  });
  const msgId = 1;
  ws.send(JSON.stringify({
    id: msgId, method: 'Network.getAllCookies'
  }));
  const resp = await new Promise((resolve) => {
    ws.once('message', (m) => resolve(JSON.parse(m.toString())));
  });
  ws.close();
  const cookies = resp.result && resp.result.cookies || [];
  const tokenCookie = cookies.find(c => c.name === 'CPL-coros-token' && c.value);
  return tokenCookie ? tokenCookie.value : null;
}

async function main() {
  console.log('=== COROS Training Hub 登录辅助 ===\n');
  console.log('1. 启动 Chrome 浏览器...');

  // 启动 OpenClaw Chrome（如果还没启动）
  try {
    detectChromePort();
    console.log('   ✓ Chrome 已在运行');
  } catch {
    console.log('   启动 OpenClaw Chrome...');
    // 这里不直接调 openclaw CLI（避免依赖），让用户先启动 openclaw browser
    console.log('   ✗ Chrome 未运行，请先执行：openclaw browser start');
    process.exit(1);
  }

  const port = detectChromePort();
  console.log(`2. CDP 端口: ${port}`);
  console.log(`3. 请在浏览器中打开: ${URL}`);
  console.log('   （如未自动打开，请手动复制粘贴）');
  console.log('4. 登录账号...');
  console.log('');

  // 轮询等待 cookie
  const startTime = Date.now();
  const TIMEOUT_MS = 5 * 60 * 1000; // 5 分钟超时
  let token = null;

  process.stdout.write('5. 等待 cookie "CPL-coros-token"');
  while (Date.now() - startTime < TIMEOUT_MS) {
    try {
      token = await getCookie(port);
      if (token) break;
    } catch (e) {
      // CDP 暂时不可用，继续等
    }
    process.stdout.write('.');
    await new Promise(r => setTimeout(r, 2000));
  }
  process.stdout.write('\n');

  if (!token) {
    console.error('\n✗ 超时：5 分钟内未检测到登录成功的 cookie。');
    console.error('  请确认：');
    console.error('  - 浏览器已成功登录 t.coros.com');
    console.error('  - 登录后页面已重定向到 dash-board');
    process.exit(1);
  }

  console.log('   ✓ 检测到 token');
  console.log(`   token 长度: ${token.length} 字符`);

  // 保存
  const data = {
    token,
    savedAt: new Date().toISOString(),
    domain: '.coros.com',
  };
  fs.mkdirSync(path.dirname(TOKEN_PATH), { recursive: true });
  fs.writeFileSync(TOKEN_PATH, JSON.stringify(data, null, 2));
  console.log(`\n✓ Token 已保存: ${TOKEN_PATH}`);
  console.log('\n下一步：执行 `同步用户画像` 即可拿到 lthr 实测值 + 骑行 PR。');
}

main().catch(err => {
  console.error('错误:', err.message);
  process.exit(1);
});
