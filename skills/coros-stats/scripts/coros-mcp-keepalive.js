#!/usr/bin/env node
/**
 * COROS MCP 客户端 - 修复版
 * 
 * 根因确认：
 * 1. COROS MCP 服务器 session 绑定在 TCP 连接上，非 session header
 * 2. COROS 服务器不支持 notifications/initialized（返回 Method not found）
 * 3. 必须使用自定义 https.Agent 且 maxSockets: 1 强制复用同一个 socket
 * 4. 所有调用必须在同一个 Node.js 进程内完成（进程结束 = 连接断开 = session 丢失）
 *
 * 用法：
 *   COROS_REGION=eu node coros-mcp-keepalive.js call queryUserInfo '{}'
 *   node coros-mcp-keepalive.js --region us call queryUserInfo '{}'
 *   node coros-mcp-keepalive.js --print-config
 *   node coros-mcp-keepalive.js call queryUserInfo '{}'
 *   node coros-mcp-keepalive.js call queryFitnessAssessmentOverview '{}'
 *   node coros-mcp-keepalive.js batch queryUserInfo queryFitnessAssessmentOverview queryRecoveryStatus queryDevices
 */
const https = require('https');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { URL } = require('url');

const REGION_CONFIG = {
  cn: {
    mcpUrl: 'https://mcpcn.coros.com/mcp',
  },
  us: {
    mcpUrl: 'https://mcpus.coros.com/mcp',
  },
  eu: {
    mcpUrl: 'https://mcpeu.coros.com/mcp',
  },
};

function normalizeRegion(value) {
  const region = String(value || process.env.COROS_REGION || 'cn').trim().toLowerCase();
  if (!REGION_CONFIG[region]) {
    throw new Error(`不支持的 COROS 区域: ${region || '(empty)'}，仅支持 cn / us / eu`);
  }
  return region;
}

function parseRuntimeArgs(argv) {
  const rest = [];
  let region = null;
  let printConfig = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--print-config') {
      printConfig = true;
    } else if (arg === '--region') {
      i += 1;
      if (i >= argv.length) throw new Error('--region 需要参数: cn / us / eu');
      region = argv[i];
    } else if (arg.startsWith('--region=')) {
      region = arg.slice('--region='.length);
    } else {
      rest.push(arg);
    }
  }
  return { region: normalizeRegion(region), printConfig, args: rest };
}

let runtime;
try {
  runtime = parseRuntimeArgs(process.argv.slice(2));
} catch (err) {
  console.error('Error:', err.message);
  process.exit(1);
}
const COROS_REGION = runtime.region;
const MCP_URL = REGION_CONFIG[COROS_REGION].mcpUrl;
function resolveTokenRoot() {
  const explicit = String(process.env.COROS_MCP_TOKEN_ROOT || '').trim();
  if (explicit) return path.resolve(explicit);
  const home = os.homedir();
  if (home) return path.join(home, '.coros-mcp-skill-gateway-ts');
  throw new Error('无法解析 COROS MCP token 目录，请重新连接账号。');
}

const TOKEN_ROOT = resolveTokenRoot();
const TOKEN_PATH = path.join(TOKEN_ROOT, COROS_REGION, 'token.json');
const URL_INFO = new URL(MCP_URL);

let token;
let reqId = 1;
let sessionId = null;

// 创建自定义 agent，强制 keep-alive 且只用一个 socket
const agent = new https.Agent({
  keepAlive: true,
  keepAliveMsecs: 30000,
  maxSockets: 1,
});

function loadToken() {
  try {
    return JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).access_token;
  } catch (err) {
    throw new Error(`未找到或无法读取 COROS ${COROS_REGION} 区域 MCP token: ${TOKEN_PATH}。请先在配置页完成 COROS 授权。`);
  }
}

function mcpRequest(method, params = {}) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ jsonrpc: '2.0', id: reqId++, method, params: params || {} });

    const headers = {
      'Authorization': `Bearer ${token}`,
      'Accept': 'text/event-stream, application/json',
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
      'Connection': 'keep-alive',
    };
    if (sessionId) {
      headers['Mcp-Session-Id'] = sessionId;
    }

    const req = https.request(MCP_URL, {
      method: 'POST',
      headers,
      agent, // 使用自定义 agent 强制复用连接
    }, (res) => {
      if (res.headers['mcp-session-id']) {
        sessionId = res.headers['mcp-session-id'];
      }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString();
        const ct = res.headers['content-type'] || '';
        if (ct.includes('text/event-stream')) {
          const lines = raw.split('\n');
          let lastData = '';
          for (const l of lines) { if (l.startsWith('data:')) lastData = l.slice(5).trimStart(); }
          try {
            const parsed = JSON.parse(lastData);
            if (parsed.error) reject(new Error(JSON.stringify(parsed.error, null, 2)));
            else resolve(parsed);
          } catch { reject(new Error('Parse error: ' + lastData.slice(0, 200))); }
        } else {
          try {
            const parsed = JSON.parse(raw);
            if (parsed.error) reject(new Error(JSON.stringify(parsed.error, null, 2)));
            else resolve(parsed);
          } catch { resolve({ raw, status: res.statusCode }); }
        }
      });
    });

    req.on('error', err => {
      sessionId = null;
      reject(err);
    });

    req.write(body);
    req.end();
  });
}

async function initSession() {
  const resp = await mcpRequest('initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'coros-stats', version: `1.0-${COROS_REGION}` },
  });
  if (resp.error) {
    throw new Error('初始化失败: ' + JSON.stringify(resp.error, null, 2));
  }
  // 不调用 notifications/initialized（COROS 不支持，返回 Method not found）
  return resp;
}

async function callTool(toolName, toolArgs = {}) {
  const resp = await mcpRequest('tools/call', { name: toolName, arguments: toolArgs });
  if (resp.result && resp.result.content) {
    for (const item of resp.result.content) {
      if (item.type === 'text') {
        try { console.log(JSON.stringify(JSON.parse(item.text), null, 0)); }
        catch { console.log(item.text); }
      } else {
        console.log(JSON.stringify(item));
      }
    }
  } else if (resp.error) {
    console.error(JSON.stringify(resp.error, null, 2));
  } else {
    console.log(JSON.stringify(resp, null, 2));
  }
}

async function main() {
  if (runtime.printConfig) {
    console.log(JSON.stringify({
      region: COROS_REGION,
      mcpUrl: MCP_URL,
      tokenRoot: TOKEN_ROOT,
      tokenPath: TOKEN_PATH,
      host: URL_INFO.host,
    }, null, 2));
    return;
  }

  token = loadToken();
  const args = runtime.args;

  await initSession();

  if (args[0] === 'list') {
    const resp = await mcpRequest('tools/list', {});
    console.log(JSON.stringify(resp, null, 2));
  } else if (args[0] === 'call' && args[1]) {
    const toolName = args[1];
    let toolArgs = {};
    if (args.length > 2) {
      try { toolArgs = JSON.parse(args.slice(2).join(' ')); } catch {}
    }
    await callTool(toolName, toolArgs);
  } else if (args[0] === 'batch') {
    // 批量调用模式：在单个 session 中顺序调用多个工具
    const tools = args.slice(1);
    for (const toolName of tools) {
      console.log(`\n=== ${toolName} ===`);
      try {
        await callTool(toolName, {});
      } catch (err) {
        console.error('Error:', err.message);
      }
    }
  } else if (!args[0]) {
    // Default: user profile
    await callTool('queryUserInfo', {});
  } else {
    await callTool(args[0], {});
  }
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
