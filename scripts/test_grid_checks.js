/**
 * test_grid_checks.js — 사진 목록(사진 펼치기) 썸네일에 CHECK 스티커 표시 (실제 Chromium) — 2026-11-16 사용자 요청
 *   ① 서버에 저장된 CHECK 스티커가 있는 지면만 ✓ 배지·빨간 테두리 (스티커 2개면 ✓2) · WHAT 등 다른 스티커·표시 없는 지면은 없음
 *   ② 뷰어를 한 번도 안 열어도 목록을 펼치면 바로 보임(표시를 따로 불러옴)
 *   ③ 뷰어에서 CHECK 스티커(4 키)를 붙이면 닫은 뒤 목록에 ✓ 가 생기고, 지우면(지우개) 사라짐
 *   ④ 관리자가 아니면(403) 저장된 표시는 없고, 이 세션에서 붙인 것만 보임
 * 실행: PW_CHROME=<크로미움 경로> node scripts/test_grid_checks.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = fs.readFileSync(path.join(__dirname, '..', 'stock', 'slack_digest_live.html'), 'utf8');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const stk = (label, x) => ({ t: 'sticker', label, c: '#dc2626', w: .01, pts: [[x, .3], [x + .1, .4]] });
const STORED = { '02.jpg': { revision: 1, strokes: [stk('CHECK', .2)] }, '03.jpg': { revision: 1, strokes: [stk('WHAT', .2)] },
                 '04.jpg': { revision: 1, strokes: [stk('CHECK', .2), stk('CHECK', .5)] } };
let ADMIN = true;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), D = u.searchParams.get('date') || '2026-11-16';
  const send = (t, b, code = 200) => { res.writeHead(code, { 'Content-Type': t }); res.end(b); };
  const json = (o, code = 200) => send('application/json', JSON.stringify(o), code);
  if (u.pathname === '/economy') return send('text/html; charset=utf-8', HTML);
  if (u.pathname === '/economy/data') return json({ date: D, messages: [] });
  if (u.pathname === '/api/news/today') return json({ ok: true, ready: true, date: D, count: 4,
    images: [1, 2, 3, 4].map(n => ({ name: '0' + n + '.jpg', url: '/page.svg', thumb: '/page.svg', download_url: '/page.svg' })) });
  if (u.pathname === '/page.svg') return send('image/svg+xml', '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800"><rect width="1200" height="1800" fill="white"/></svg>');
  if (u.pathname === '/api/news/marks') {
    if (!ADMIN) return json({ ok: false }, 403);
    if (req.method === 'GET') return json({ ok: true, pages: STORED });
    let raw = ''; req.on('data', c => raw += c); req.on('end', () => { const b = JSON.parse(raw);
      STORED[b.page] = { revision: b.revision + 1, strokes: b.strokes }; json({ ok: true, revision: b.revision + 1 }); }); return;
  }
  json({ ok: false }, 403);
});
(async () => {
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  let pass = true;
  const check = (ok, name, extra) => { console.log((ok ? '  ✔ ' : '  ✘ ') + name + (ok ? '' : '  → ' + (extra || ''))); if (!ok) pass = false; };
  const cells = (page) => page.evaluate(() => [...document.querySelectorAll('.news-cell')].map(c => {
    const b = c.querySelector('.chk'); const vis = b && getComputedStyle(b).display !== 'none';
    return { has: c.classList.contains('has-check'), badge: vis ? b.textContent : '', border: getComputedStyle(c).borderTopColor }; }));
  const openGrid = async (page) => { await page.goto(base + '/economy?date=2026-11-16'); await page.waitForSelector('.news-toggle:not([hidden])');
    await page.click('.news-toggle'); await page.waitForSelector('.news-cell'); };
  try {
    let ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } }); await ctx.route('https://**/*', r => r.abort());
    let page = await ctx.newPage();
    await openGrid(page);
    await page.waitForFunction(() => document.querySelectorAll('.news-cell.has-check').length > 0, null, { timeout: 8000 }).catch(() => {});
    let c = await cells(page);
    check(c.length === 4, '사진 4장 목록', c.length);
    check(!c[0].has && c[1].has && !c[2].has && c[3].has, '① CHECK 스티커 있는 2·4번 지면만 표시(WHAT 만 있는 3번·표시 없는 1번은 아님)', JSON.stringify(c.map(x => x.has)));
    check(c[1].badge === '✓' && c[3].badge === '✓2', '① 배지: 한 개 ✓ · 두 개 ✓2', c.map(x => x.badge).join('|'));
    check(c[1].border.replace(/\s/g, '') === 'rgb(220,38,38)', '① 빨간 테두리', c[1].border);
    check(await page.evaluate(() => document.getElementById('lb').hidden), '② 뷰어는 한 번도 안 열었는데 위 표시가 이미 보임(표시를 따로 불러옴)');

    await page.evaluate(() => openViewer(0));
    await page.waitForFunction(() => document.getElementById('lb-img').naturalWidth > 0 && V.fitW > 0);
    const r = await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x + r.width * .3, r.y + r.height * .3); await page.keyboard.press('4');
    await page.keyboard.press('Escape');
    await page.evaluate(() => closeViewer());
    await page.waitForFunction(() => document.querySelector('.news-cell').classList.contains('has-check'), null, { timeout: 5000 }).catch(() => {});
    c = await cells(page);
    check(c[0].has && c[0].badge === '✓', '③ 뷰어에서 CHECK(4 키) 붙이면 1번 지면에 ✓ 생김', JSON.stringify(c[0]));
    await page.evaluate(() => { markList().length = 0; marksChanged(); });          // 지움(지우개와 같은 결과)
    c = await cells(page);
    check(!c[0].has && c[0].badge === '', '③ 지우면 ✓ 사라짐', JSON.stringify(c[0]));
    await ctx.close();

    ADMIN = false;
    ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } }); await ctx.route('https://**/*', r => r.abort());
    page = await ctx.newPage();
    await openGrid(page);
    await page.waitForFunction(() => markDay && markDay.mode === 'guest', null, { timeout: 8000 }).catch(() => {});
    c = await cells(page);
    check(c.every(x => !x.has), '④ 관리자가 아니면 저장된 표시는 안 보임', JSON.stringify(c.map(x => x.has)));
    await page.evaluate(() => openViewer(1));
    await page.waitForFunction(() => document.getElementById('lb-img').naturalWidth > 0 && V.fitW > 0);
    const r2 = await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r2.x + r2.width * .3, r2.y + r2.height * .3); await page.keyboard.press('4');
    await page.evaluate(() => closeViewer());
    c = await cells(page);
    check(c[1].has && !c[0].has && !c[2].has, '④ 이 세션에서 붙인 것은 보임(2번만)', JSON.stringify(c.map(x => x.has)));
    await ctx.close();
  } finally { await browser.close(); srv.close(); }
  console.log(pass ? 'ALL PASS' : 'SOME FAILED'); process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
