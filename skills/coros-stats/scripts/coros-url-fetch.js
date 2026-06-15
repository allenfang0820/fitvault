#!/usr/bin/env node
/**
 * coros-url-fetch.js - COROS URL 数据抓取器
 *
 * 功能：
 * 1. 连 Chrome DevTools（默认 :9222）
 * 2. 找到 t.coros.com/admin/views/dash-board tab（缺失则自动 navigate）
 * 3. 切两个 arco-select 下拉（个人跑步纪录 + 个人骑行纪录）到 "全部"
 * 4. 抓页面结构化数据
 * 5. 输出 JSON 到 stdout
 *
 * 使用：
 *   node coros-url-fetch.js
 *   node coros-url-fetch.js --port 9223
 */

const http = require('http');
const WebSocket = require('ws');

const PORT = (() => {
  const i = process.argv.indexOf('--port');
  return i >= 0 ? parseInt(process.argv[i + 1], 10) : 9222;
})();

function httpGetJSON(path) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: 'localhost', port: PORT, path }, res => {
      let data = '';
      res.on('data', c => (data += c));
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`Bad JSON: ${data.slice(0, 200)}`)); }
      });
    });
    req.on('error', e => {
      if (e.code === 'ECONNREFUSED' || e.code === 'ECONNRESET') {
        reject(new Error(
          `Chrome DevTools 未启动 (localhost:${PORT} 拒绝连接)。\n` +
          `修复: 运行  bash ~/.qclaw/skills/coros-stats/scripts/start_chrome.sh\n` +
          `或确认 Chrome 以 --remote-debugging-port=${PORT} 启动`
        ));
      } else {
        reject(new Error(`HTTP ${e.code || '错误'}: ${e.message}`));
      }
    });
    req.on('error', reject);
    req.setTimeout(5000, () => req.destroy(new Error('请求超时')));
  });
}

let _msgId = 0;
function wsSend(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++_msgId;
    const onMsg = ev => {
      const msg = JSON.parse(ev.data);
      if (msg.id === id) {
        ws.removeEventListener('message', onMsg);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function openWs(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => { ws.once('open', resolve); ws.once('error', reject); });
  return ws;
}

async function findOrOpenDashboardTab() {
  const tabs = await httpGetJSON('/json');
  // 1) 找 dash-board page tab
  let tab = tabs.find(t => t.type === 'page' && t.url && t.url.includes('t.coros.com/admin/views/dash-board'));
  if (tab) return tab;
  // 2) 找 t.coros.com 任意 page tab，navigate
  tab = tabs.find(t => t.type === 'page' && t.url && t.url.includes('t.coros.com'));
  if (tab) {
    console.error('[信息] 正在把已有的 t.coros.com 标签页切到 dash-board');
    const ws = await openWs(tab.webSocketDebuggerUrl);
    try { await wsSend(ws, 'Page.enable'); await wsSend(ws, 'Page.navigate', { url: 'https://t.coros.com/admin/views/dash-board' }); }
    finally { ws.close(); }
    await sleep(3500);
    return findOrOpenDashboardTab();
  }
  // 3) 任何 page tab，navigate
  const pageTabs = tabs.filter(t => t.type === 'page');
  if (pageTabs.length > 0) {
    console.error('[信息] 正在新标签页打开 dash-board');
    const ws = await openWs(pageTabs[0].webSocketDebuggerUrl);
    try { await wsSend(ws, 'Page.enable'); await wsSend(ws, 'Page.navigate', { url: 'https://t.coros.com/admin/views/dash-board' }); }
    finally { ws.close(); }
    await sleep(4000);
    return findOrOpenDashboardTab();
  }
  // 4) 真的没 tab (可能是 background.js / devtools tab only)
  throw new Error(
    'Chrome 中找不到任何 page tab。\n' +
    '修复: 在 Chrome 中手动打开一个 tab (about:blank 也行) 后重跑'
  );
}

// 验证是否已登录 t.coros.com
async function verifyLoggedIn(wsUrl) {
  const code = String.raw`
    (function(){
      const t = document.body.innerText;
      const url = location.href;
      // 未登录特征
      if (url.includes('/login') || url.includes('oauth')) return {loggedIn: false, reason: 'login url'};
      if (/获取验证码|扫码登录|手机号登录|邮箱登录|微信登录/.test(t)) return {loggedIn: false, reason: 'login form detected'};
      // 已登录特征
      if (t.includes('总训练时长') || t.includes('uid:')) return {loggedIn: true};
      if (url.includes('dash-board')) return {loggedIn: true, reason: 'dash-board but no expected text'};
      return {loggedIn: false, reason: 'unknown page state'};
    })()
  `;
  const r = await evalIn(wsUrl, code);
  return r;
}

async function evalIn(wsUrl, jsCode) {
  const ws = await openWs(wsUrl);
  try {
    await wsSend(ws, 'Runtime.enable');
    const r = await wsSend(ws, 'Runtime.evaluate', {
      expression: jsCode, awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'eval error');
    return r.result.value;
  } finally { ws.close(); }
}

async function main() {
  const tab = await findOrOpenDashboardTab();
  if (!tab) {
    throw new Error('findOrOpenDashboardTab() returned null (should not happen)');
  }

  // 验证是否已登录 COROS
  const loginState = await verifyLoggedIn(tab.webSocketDebuggerUrl);
  if (!loginState.loggedIn) {
    throw new Error(
      `COROS 未登录 (${loginState.reason})。\n` +
      `修复: 在 Chrome 窗口中打开 https://t.coros.com 并完成登录 (手机/微信/邮箱)，然后重跑`
    );
  }
  if (loginState.reason) console.error(`[info] Login verified (${loginState.reason})`);

  // ========== Step 1: 切两个下拉到"全部" ==========
  // String.raw 让 \n \s 等保持原样，避免模板字符串 escape 干扰
  const switchCode = String.raw`
    (async function(){
      function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
      const log = [];
      for (let pass=0; pass<3; pass++) {
        const sels = Array.from(document.querySelectorAll('.arco-select')).filter(s=>{
          const v = s.querySelector('.arco-select-view-value');
          return v && /^(4周|12周|半年|1周|2周|3个月|6个月|1年)/.test(v.textContent.trim());
        });
        if (sels.length === 0) break;
        const sel = sels[0];
        const before = sel.querySelector('.arco-select-view-value').textContent.trim();
        if (before === '全部') { log.push({before, after:'全部', skipped:true}); continue; }
        const r = sel.getBoundingClientRect();
        sel.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));
        sel.click();
        await sleep(700);
        const popups = Array.from(document.querySelectorAll('.arco-trigger-popup'));
        // 找离 select 最近的 popup（不限制方向，popup 可能向上展开）
        let target = null, bestDist = Infinity;
        for (const p of popups) {
          const pr = p.getBoundingClientRect();
          if (pr.width === 0) continue;
          if (pr.x > r.x + r.width + 50 || pr.x + pr.width < r.x - 50) continue;
          const dx = Math.max(pr.x - r.x - r.width, r.x - pr.x - pr.width, 0);
          const dy = pr.y > r.y + r.height ? pr.y - (r.y + r.height)
                       : pr.y + pr.height < r.y ? r.y - (pr.y + pr.height)
                       : 0;
          const dist = Math.hypot(dx, dy);
          if (dist < bestDist) { bestDist = dist; target = p; }
        }
        if (!target) { log.push({before, error:'no popup'}); await sleep(500); continue; }
        const opt = Array.from(target.querySelectorAll('.arco-select-option')).find(o=>o.textContent.trim()==='全部');
        if (!opt) { log.push({before, error:'no 全部 option'}); await sleep(500); continue; }
        ['mousedown','mouseup','click'].forEach(t => opt.dispatchEvent(new MouseEvent(t,{bubbles:true,button:0})));
        await sleep(1500);
        log.push({before, after:'clicked'});
        await sleep(800);
      }
      return JSON.stringify(log);
    })()
  `;
  const switchResult = await evalIn(tab.webSocketDebuggerUrl, switchCode);
  const switchLog = JSON.parse(switchResult);
  for (const s of switchLog) {
    if (s.error) console.error(`[warn] ${s.before} → ${s.error}`);
    else if (s.skipped) console.error(`[skip] ${s.before} already at target`);
    else console.error(`[ok] ${s.before} → ${s.after}`);
  }

  // ========== Step 2: 抓数据 ==========
  const extractCode = String.raw`
    (function(){
      const t = document.body.innerText;
      function g(re){
        const m = t.match(re);
        return m ? m[1].trim() : null;
      }
      // PBs: 严格匹配 label 行 + hh:mm:ss 时间
      function findPB(label){
        const re = new RegExp('\\n' + label + '\\s*\\n[\\t\\s]*(\\d{2}:\\d{2}:\\d{2})');
        return g(re);
      }
      // 4 个 race predict: 锚定到"成绩预测"段
      function findPredict(label){
        const re = new RegExp('成绩预测[\\s\\S]*?' + label + '\\s*\\n[\\t\\s]*(\\d{1,2}:\\d{2}:\\d{2})');
        return g(re);
      }
      // 距离/爬升/日期 (label 后跟 N 个 token)
      function findRow(label){
        const re = new RegExp('\\n' + label + '\\s*\\n([\\s\\S]*?)(?:\\n\\n|\\n个人)');
        return g(re);
      }
      return JSON.stringify({
        username: (t.match(/^([^\n]+)/) || [,''])[1],
        max_heart_rate: parseInt(g(/最大心率\s*\n+\s*(\d+)/)),
        resting_heart_rate: parseInt(g(/静息心率\s*\n+\s*(\d+)/)),
        lactate_threshold_hr: parseInt(g(/乳酸阈心率\s*\n+\s*(\d+)/)),
        lactate_threshold_pace: g(/乳酸阈配速\s*\n+\s*([\d'\"\s]+)/),
        hrv_status: t.includes('HRV评估') && t.includes('近7日无数据') ? 'empty' : 'has_data',
        race_predict_5k: findPredict('5km'),
        race_predict_10k: findPredict('10km'),
        race_predict_half: findPredict('半马'),
        race_predict_full: findPredict('全马'),
        longest_run_km: parseFloat(((findRow('最长跑步距离') || '').match(/(\d+\.\d+)km/) || [,''])[1] || 0) || 0,
        longest_run_date: (findRow('最长跑步距离') || '').match(/(\d{4}\/\d{2}\/\d{2})/)?.[1] || null,
        highest_climb_m: parseInt(g(/最高累计爬升\s*\n+\s*(\d+)m/)),
        highest_climb_date: g(/个人跑步纪录[\s\S]*?最高累计爬升[\s\S]*?(\d{4}\/\d{2}\/\d{2})/),
        pbs: {
          '1km': findPB('1km'),
          '3km': findPB('3km'),
          '5km': findPB('5km'),
          '10km': findPB('10km')
        },
        longest_cycle_km: parseFloat(((findRow('最长骑行距离') || '').match(/(\d+\.\d+)km/) || [,''])[1] || 0) || 0,
        longest_cycle_date: (findRow('最长骑行距离') || '').match(/(\d{4}\/\d{2}\/\d{2})/)?.[1] || null,
        cycle_highest_climb_m: parseInt(g(/个人骑行纪录[\s\S]*?最高累计爬升\s*\n+\s*(\d+)m/)),
        cycle_highest_climb_date: g(/个人骑行纪录[\s\S]*?最高累计爬升[\s\S]*?(\d{4}\/\d{2}\/\d{2})/),
        training: {
          acute_load: parseInt(g(/短期负荷\s*\n+\s*(\d+)/)),
          chronic_load: parseInt(g(/长期负荷\s*\n+\s*(\d+)/)),
          acwr: g(/负荷比\s*\n+\s*(\d+%)/),
          recovery_pct: parseInt(g(/体力恢复\s*\n+\s*(\d+)/))
        }
      });
    })()
  `;
  const data = JSON.parse(await evalIn(tab.webSocketDebuggerUrl, extractCode));

  // 诊断：如果关键字段全 null，提示 UI 可能变了
  const criticalFields = ['username', 'max_heart_rate', 'resting_heart_rate',
                          'lactate_threshold_hr', 'lactate_threshold_pace'];
  const allNull = criticalFields.every(f => !data[f]);
  if (allNull) {
    console.error('\n⚠️  关键字段全 null。可能原因:');
    console.error('   - COROS 改了 dashboard UI (类名/文案变了)');
    console.error('   - 页面加载未完成 (重跑试试)');
    console.error('   - 登录后 account_id 不匹配 (走错账号了)');
    console.error('   诊断信息: bodyText 样例 = \n');
    const sampleCode = String.raw`(function(){ return document.body.innerText.slice(0, 500); })()`;
    const sample = await evalIn(tab.webSocketDebuggerUrl, sampleCode);
    console.error(JSON.stringify(sample));
  }

  console.log(JSON.stringify(data, null, 2));
}

main().catch(e => {
  console.error('\n❌ ' + e.message + '\n');
  process.exit(1);
});
