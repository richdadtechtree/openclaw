/**
 * test_viewer_hide.js — 웹 화면 '🧹 지금까지 것 숨기기' 확인 (실제 Chromium)
 *
 * GPT 에게 요약을 새로 받기 전에, 그날 먼저 올라온 요약을 **웹 화면에서만** 한 번에 치운다.
 * (슬랙 원본은 그대로 · 서버 stock/app.py 의 /slack/hide · /slack/unhide 와 같은 규칙을 가짜 서버로 흉내)
 *   ① 누르면 확인 창 → 지금까지의 카드가 모두 사라지고 "↩ 숨긴 N개 다시 보기" 가 나온다
 *   ② 그 뒤에 새로 올라온 요약만 보인다
 *   ③ '다시 보기' 로 되돌리면 전부 다시 보인다 · 확인 창에서 취소하면 아무 일도 없다
 *
 * 실행: npm i playwright && node scripts/test_viewer_hide.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const msgs = [
  { ts: 'T06:29:00', text: '*[신문요약 1/6] 신문 브리핑*\n옛 요약 기사 하나\n• WHAT: 예전 내용.' },
  { ts: 'T06:40:00', text: '*[신문요약 2/6] 신문 브리핑*\n옛 요약 기사 둘\n• WHAT: 예전 내용.' },
];
let cut = '';                                   // 서버의 '이 시각까지 숨김' 기준 (slack_hidden.json 흉내)
let clock = '10:30:00';                         // 서버 현재 시각(흉내)

const srv = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x'), u = url.pathname;
  const D = url.searchParams.get('date') || '2026-09-24';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') {
    const all = msgs.map(m => ({ ...m, ts: D + m.ts, source: 'user', kind: 'text' }));
    const keep = cut ? all.filter(m => m.ts.slice(0, 19) > cut) : all;
    return send('application/json', JSON.stringify({ date: D, messages: keep, hidden: all.length - keep.length, hidden_before: cut }));
  }
  if (u === '/slack/hide' && req.method === 'POST') { cut = D + 'T' + clock; return send('application/json', '{"ok":true}'); }
  if (u === '/slack/unhide' && req.method === 'POST') { cut = ''; return send('application/json', '{"ok":true}'); }
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const page = await browser.newPage({ viewport: { width: 1100, height: 850 } });
  let answer = true, dialogText = '';
  page.on('dialog', d => { dialogText = d.message(); answer ? d.accept() : d.dismiss(); });
  await page.goto(base + '/slack');
  await page.evaluate(() => { state.date = '2026-09-24'; lastSnapshot = null; return load(); });
  await page.waitForSelector('.entry');
  const cards = () => page.evaluate(() => [...document.querySelectorAll('.brf-title')].map(e => e.textContent.trim()));

  console.log('\n[취소하면 그대로]');
  answer = false;
  await page.click('#hide-old');
  await page.waitForTimeout(300);
  check((await cards()).length === 2, '확인 창에서 취소 → 아무것도 안 숨김');

  console.log('\n[① 숨기기]');
  answer = true;
  await page.click('#hide-old');
  await page.waitForFunction(() => !document.querySelector('.entry'));
  check(/2개/.test(dialogText) && /슬랙 원본은 지우지 않습니다/.test(dialogText), '확인 창에 개수와 "슬랙 원본은 그대로" 안내');
  check((await cards()).length === 0, '지금까지의 요약 카드가 모두 사라진다');
  check(await page.isVisible('#unhide') && /숨긴 2개 다시 보기 \(10:30 이전\)/.test(await page.textContent('#unhide')),
        '"↩ 숨긴 2개 다시 보기 (10:30 이전)" 버튼이 나온다', await page.textContent('#unhide'));

  console.log('\n[② 새로 올라온 요약만]');
  msgs.push({ ts: 'T10:45:00', text: '*[신문요약 1/6] 신문 브리핑*\n새 요약 기사\n• WHAT: 새 내용.' });
  await page.evaluate(() => { lastSnapshot = null; return load(); });
  await page.waitForSelector('.entry');
  check(JSON.stringify(await cards()) === JSON.stringify(['새 요약 기사']), '숨긴 뒤에 올라온 새 요약만 보인다', (await cards()).join(','));

  console.log('\n[③ 되돌리기]');
  await page.click('#unhide');
  await page.waitForFunction(() => document.querySelectorAll('.brf-title').length === 3);
  check((await cards()).length === 3 && !(await page.isVisible('#unhide')), '"다시 보기" → 전부 다시 보이고 버튼은 사라진다');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
