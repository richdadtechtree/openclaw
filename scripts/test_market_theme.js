/**
 * test_market_theme.js — 시장 지수(/market) 화면이 계정별 화이트/다크를 따르고 저장하는지 (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청
 *   ① 계정 값(window.__GATE_THEME)이 light/dark 면 그대로 적용되고 버튼 글자도 맞음
 *   ② 'auto' 면 기기 설정(밝게/어둡게)을 따름
 *   ③ 버튼을 누르면 바뀌고 서버 /gate/theme 에 저장(보낸 값 확인)
 *   ④ 계정에 값이 없고 이 브라우저에 예전 선택(dashboard_theme)이 있으면 그 값 적용 + 한 번 올려 줌
 *   ⑤ 슬랙 캡처용 '/' (in-market 아님)는 계정에 아무것도 안 보냄
 * 실행: node scripts/test_market_theme.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'templates', 'index.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

let ACCT = null;                 // 서버가 자리표에 넣어 줄 계정 값(null = 아직 저장한 적 없음 → 자리표 빈 칸)
const saved = [];                // /gate/theme 로 받은 값들
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b, c = 200) => { res.writeHead(c, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/market') {
    // 서버(gate.fill_page)가 하는 일을 흉내: /market 이고 계정 값이 있으면 자리표를 머리글 스크립트로 바꾼다
    let h = fs.readFileSync(HTML, 'utf8');
    const head = (u === '/market' && ACCT)
      ? `<script>window.__GATE_THEME="${ACCT}";(function(t){var d=document.documentElement;if(t==="auto")d.removeAttribute("data-theme");else d.setAttribute("data-theme",t);})("${ACCT}");</script>` : '';
    return send('text/html; charset=utf-8', h.replace('<!--GATE_THEME-->', head));
  }
  if (u === '/gate/theme' && req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => { saved.push(JSON.parse(b).theme); send('application/json', '{"ok":true}'); });
    return;
  }
  send('application/json', '{}');                // 데이터 주소들은 빈 응답(이 검사는 화면 모드만 본다)
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const open = async (url, { scheme = 'light', ls = null } = {}) => {
    const ctx = await browser.newContext({ colorScheme: scheme });
    if (ls) await ctx.addInitScript(v => { try { localStorage.setItem('dashboard_theme', v); } catch (e) {} }, ls);
    const page = await ctx.newPage();
    await page.goto(base + url);
    await page.waitForTimeout(500);
    return { ctx, page };
  };
  const theme = p => p.evaluate(() => document.documentElement.getAttribute('data-theme'));
  const label = p => p.$eval('#theme-toggle-btn', b => b.textContent.trim());

  console.log('\n[① 계정 값 그대로]');
  for (const t of ['light', 'dark']) {
    ACCT = t; saved.length = 0;
    const { ctx, page } = await open('/market', { scheme: t === 'light' ? 'dark' : 'light' });   // 기기 설정과 반대로 해서 계정 값이 이기는지 본다
    check(await theme(page) === t, `계정 값 ${t} 가 기기 설정보다 먼저 적용`, await theme(page));
    check((await label(page)).includes(t === 'light' ? '☀️' : '🌙'), '버튼 글자가 현재 모드와 맞음', await label(page));
    check(saved.length === 0, '이미 계정에 값이 있으면 다시 올리지 않음');
    await ctx.close();
  }

  console.log('\n[② auto = 기기 설정]');
  ACCT = 'auto';
  for (const s of ['dark', 'light']) {
    const { ctx, page } = await open('/market', { scheme: s });
    check(await theme(page) === s, `auto + 기기 ${s} → ${s}`, await theme(page));
    await ctx.close();
  }

  console.log('\n[③ 버튼 누르면 계정에 저장]');
  ACCT = 'light'; saved.length = 0;
  let { ctx, page } = await open('/market');
  await page.click('#theme-toggle-btn'); await page.waitForTimeout(300);
  check(await theme(page) === 'dark' && saved.join() === 'dark', '화이트 → 다크로 바뀌고 서버에 dark 저장', `${await theme(page)} / ${saved.join()}`);
  await page.click('#theme-toggle-btn'); await page.waitForTimeout(300);
  check(await theme(page) === 'light' && saved.join() === 'dark,light', '다시 누르면 light 저장', saved.join());
  await ctx.close();

  console.log('\n[④ 계정 값 없음 + 브라우저에 예전 선택]');
  ACCT = null; saved.length = 0;
  ({ ctx, page } = await open('/market', { ls: 'light' }));
  check(await theme(page) === 'light', '브라우저에 기억된 light 적용', await theme(page));
  check(saved.join() === 'light', '계정에 한 번 올려 줌(옮겨 담기)', saved.join());
  await ctx.close();
  saved.length = 0;
  ({ ctx, page } = await open('/market'));
  check(await theme(page) === 'dark' && saved.length === 0, '아무 선택도 없으면 기본(다크)·아무것도 안 보냄', `${await theme(page)} / ${saved.length}`);
  await ctx.close();

  console.log('\n[⑤ 슬랙 캡처용 / 는 계정에 안 보냄]');
  ACCT = 'light'; saved.length = 0;
  ({ ctx, page } = await open('/', { ls: 'light' }));
  await page.click('#theme-toggle-btn'); await page.waitForTimeout(300);
  check(saved.length === 0, "'/' 에서는 /gate/theme 요청 없음(로그인 화면이 아님)");
  check(await theme(page) === 'dark', "'/' 의 버튼은 예전처럼 동작");
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
