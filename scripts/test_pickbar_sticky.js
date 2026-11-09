/**
 * test_pickbar_sticky.js — 신문 요약 화면의 '종이신문/온라인신문 전환 + 날짜 고르기' 줄이 스크롤해도 늘 보이는지 확인
 * (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청 "아래로 내려갔다가 바로 누를 수 있게"
 *   ① 전환 단추·날짜 칸·오늘 단추가 머리말 밖의 고정 줄(#pickbar)에 있음
 *   ② 아래로 한참 내려가도 이 줄이 맨 위 메뉴 바로 아래에 붙어 보이고, 그 아래 도구 줄과 서로 안 겹침
 *   ③ 내려간 채로 종이↔온라인 전환·날짜 바꾸기·오늘 단추가 바로 동작
 *   ④ 폰 390px: 한 줄에 들어가고(너무 크게 가리지 않음) 가로로 안 넘침
 * 실행: node scripts/test_pickbar_sticky.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const BRIEF = '*[신문요약 1/1] 신문 요약*\n1. 기사 제목\n• WHAT: 내용임.\n• WHY: 이유임.\n• HOW: 방법임.\n';
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  const D = u.searchParams.get('date') || '2026-11-09';
  const send = (t, b, c = 200) => { res.writeHead(c, { 'Content-Type': t }); res.end(b); };
  const json = (o, c = 200) => send('application/json', JSON.stringify(o), c);
  if (u.pathname === '/' || u.pathname === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u.pathname === '/economy/data') return json({ date: D, messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] });
  if (u.pathname === '/api/news/today') return json({ ok: true, ready: false, date: D, count: 0, images: [] });
  if (u.pathname === '/api/news/editorial') return json({ ok: false });
  if (u.pathname === '/api/news/terms') return json({ ok: false }, 403);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const open = async (opts = {}) => {
    const ctx = await browser.newContext(Object.assign({ viewport: { width: 1100, height: 800 } }, opts));
    const page = await ctx.newPage();
    page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
    await page.route('https://**/*', r => r.abort());
    await page.goto(base + '/economy');
    await page.waitForFunction(() => document.getElementById('feed').textContent.includes('기사 제목'));
    await page.waitForTimeout(500);
    // 가짜 화면이 짧아 스크롤이 안 되므로 아래에 긴 빈 칸을 붙인다
    await page.evaluate(() => { const d = document.createElement('div'); d.id = 'tall'; d.style.height = '4000px'; document.querySelector('.wrap').appendChild(d); });
    return { ctx, page };
  };
  const rect = (page, sel) => page.evaluate(s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { t: b.top, b: b.bottom, l: b.left, r: b.right, h: b.height, w: b.width }; }, sel);
  const hit = (a, b) => !(a.b <= b.t + 0.5 || b.b <= a.t + 0.5);

  console.log('\n[① 고정 줄에 들어 있음]');
  let { ctx, page } = await open();
  check(await page.evaluate(() => ['edtog', 'datepick', 'today'].every(id => document.getElementById('pickbar').contains(document.getElementById(id)))), '종이/온라인 전환·날짜 칸·오늘 단추가 #pickbar 안에 있음');
  check(await page.evaluate(() => !document.querySelector('header.mast').querySelector('#edtog, #datepick, #today')), '머리말(스크롤되면 사라지는 곳)에는 더 이상 없음');

  console.log('\n[② 아래로 내려가도 붙어 있음]');
  const top0 = await rect(page, '#pickbar');
  await page.evaluate(() => window.scrollTo(0, 2500)); await page.waitForTimeout(500);
  const nav = await rect(page, '.sitenav'), pick = await rect(page, '#pickbar'), tool = await rect(page, '#toolbar');
  check(await page.evaluate(() => scrollY) > 2000, '아래로 한참 내려감', String(await page.evaluate(() => scrollY)));
  check(Math.abs(nav.t) < 1.5 && Math.abs(pick.t - nav.b) < 1.5, '고정 줄이 화면에 계속 보이고 맨 위 메뉴 바로 아래에 붙음', `메뉴 ${Math.round(nav.t)}~${Math.round(nav.b)} · 고정 줄 ${Math.round(pick.t)}~${Math.round(pick.b)}`);
  check(Math.abs(tool.t - pick.b) < 1.5, '도구 줄(칩·글자 크기)은 고정 줄 바로 아래에 붙음', `도구 줄 ${Math.round(tool.t)}~${Math.round(tool.b)}`);
  check(!hit(nav, pick) && !hit(pick, tool) && !hit(nav, tool), '세 줄이 서로 겹치지 않음');
  const cs = await page.$eval('#pickbar', e => getComputedStyle(e).position);
  check(cs === 'sticky', '고정 방식은 sticky(스크롤을 막지 않음)');
  const vis = await page.evaluate(() => { const r = document.getElementById('edtog').getBoundingClientRect(); const x = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!x && document.getElementById('edtog').contains(x); });
  check(vis, '전환 단추가 실제로 맨 위에 보이고 눌림 가능(다른 줄이 가리지 않음)');

  console.log('\n[③ 내려간 채로 바로 동작]');
  const edState = () => page.evaluate(() => document.querySelector('#edtog [aria-pressed="true"]').dataset.ed);
  await page.click('#edtog [data-ed="online"]'); await page.waitForTimeout(500);
  check(await edState() === 'online', '내려간 채로 온라인신문을 누르면 바로 전환됨');
  await page.click('#edtog [data-ed="paper"]'); await page.waitForTimeout(500);
  check(await edState() === 'paper', '종이신문으로도 바로 돌아옴');
  await page.evaluate(() => window.scrollTo(0, 2500)); await page.waitForTimeout(300);
  await page.fill('#datepick', '2026-11-06'); await page.dispatchEvent('#datepick', 'change'); await page.waitForTimeout(500);
  check(await page.evaluate(() => state.date) === '2026-11-06', '내려간 채로 날짜를 바꾸면 바로 적용됨');
  await page.click('#today'); await page.waitForTimeout(500);
  check(await page.evaluate(() => state.date) === await page.evaluate(() => todayKST()), '"오늘" 단추도 바로 동작');
  await ctx.close();

  console.log('\n[④ 폰 390px]');
  ({ ctx, page } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }));
  const pk = await rect(page, '#pickbar');
  check(pk.h < 64, '폰에서도 고정 줄이 한 줄(너무 크게 가리지 않음)', `높이 ${Math.round(pk.h)}px`);
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '가로 스크롤 없음');
  await page.evaluate(() => window.scrollTo(0, 2500)); await page.waitForTimeout(500);
  const n2 = await rect(page, '.sitenav'), p2 = await rect(page, '#pickbar'), t2 = await rect(page, '#toolbar');
  check(Math.abs(p2.t - n2.b) < 1.5 && Math.abs(t2.t - p2.b) < 1.5 && !hit(n2, p2) && !hit(p2, t2), '폰에서도 메뉴 → 고정 줄 → 도구 줄이 차례로 붙고 겹치지 않음', `메뉴 ${Math.round(n2.b)} · 고정 줄 ${Math.round(p2.t)}~${Math.round(p2.b)} · 도구 ${Math.round(t2.t)}`);
  check(p2.l >= 0 && p2.r <= 390 + 1, '고정 줄이 화면 폭 안');
  const stack = t2.b;
  check(stack < 844 * 0.45, '붙어 있는 줄들이 화면의 절반 미만만 차지(본문을 읽을 공간 남음)', `${Math.round(stack)}px / 844px`);
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
