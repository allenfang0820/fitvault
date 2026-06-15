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
 *   node coros-mcp-keepalive.js call queryUserInfo '{}'
 *   node coros-mcp-keepalive.js call queryFitnessAssessmentOverview '{}'
 *   node coros-mcp-keepalive.js batch queryUserInfo queryFitnessAssessmentOverview queryRecoveryStatus queryDevices
 */
const https = require('https');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const TOKEN_PATH = path.join(process.env.HOME, '.coros-mcp-skill-gateway-ts', 'cn', 'token.json');
const MCP_URL = 'https://mcpcn.coros.com/mcp';
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
  return JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).access_token;
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
    clientInfo: { name: 'coros-stats', version: '1.0' },
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
  token = loadToken();
  const args = process.argv.slice(2);

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
