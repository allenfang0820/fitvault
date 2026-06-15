#!/usr/bin/env node
// 找侧栏所有 LI（不在 modal 内）
const http = require('http');
const WebSocket = require('ws');

const PORT = 9222;

async function main() {
  const tabs = await new Promise((resolve) => {
    http.get(`http://127.0.0.1:${PORT}/json/list`, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(JSON.parse(data)));
    });
  });
  const target = tabs.find(t => t.url && t.url.includes('t.coros.com')) || tabs[0];
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve) => { ws.once('open', resolve); });
  
  let id = 0;
  function call(method, params = {}) {
    const myId = ++id;
    return new Promise((resolve) => {
      const handler = (msg) => {
        const data = JSON.parse(msg.toString());
        if (data.id === myId) { ws.off('message', handler); resolve(data.result); }
      };
      ws.on('message', handler);
      ws.send(JSON.stringify({ id: myId, method, params }));
    });
  }
  
  await new Promise(r => setTimeout(r, 1000));
  
  const r = await call('Runtime.evaluate', { expression: `
    (() => {
      // 找 layout-right 内不在 modal 的所有 li
      const right = document.querySelector('.layout-right');
      const lis = right.querySelectorAll('li');
      return Array.from(lis).filter(li => !li.closest('.coros-modal')).slice(0, 15).map(li => ({
        text: (li.textContent || '').trim().slice(0, 30),
        class: (li.className || '').slice(0, 60),
        draggable: li.draggable,
        html: li.outerHTML.slice(0, 500),
      }));
    })()
  `, returnByValue: true });
  
  console.log('=== layout-right 内的 li（排除 modal）===\n');
  for (const item of (r.result.value || [])) {
    console.log(`"${item.text}" draggable=${item.draggable}`);
    console.log(`  class: ${item.class}`);
    console.log('---');
  }
  
  ws.close();
}

main().catch(e => console.error(e.message));
