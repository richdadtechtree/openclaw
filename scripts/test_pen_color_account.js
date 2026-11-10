/**
 * test_pen_color_account.js — 🖍 형광펜 '마지막으로 고른 색'을 계정에 저장했다가 그 색으로 여는지 화면 확인
 *   (실제 Chromium, 가짜 서버) — 2026-11-10 사용자 요청
 *   대상 화면 4곳: 신문 요약 사진 뷰어(/economy) · 신문 요약 사설 형광펜 · 경제 공부(/dig) · 챌린지 사진 뷰어(/challenge)
 *   ① 저장된 색이 없으면 예전 기본색(사진=빨강, 글자=노랑)으로 열린다
 *   ② 색 단추를 누르면 서버 /gate/pen 으로 {kind,color} 가 간다 (손·지우개는 색이 아니므로 안 보냄)
 *   ③ 다시 열면(= 서버가 <head> 에 window.__GATE_PEN 을 넣어 주면) 그 색 단추가 눌린 채로 시작한다
 *   ④ 사진 펜 색은 신문 요약·챌린지가 함께 쓰고, 글자 펜 색은 경제 공부·사설이 함께 쓴다
 *   ⑤ 이 브라우저에서 ✋ 손으로 두었으면 손 그대로(색만 계정 값을 따른다) · 엉뚱한 값이 내려오면 기본색
 * 서버 쪽(권한·허용 목록·계정 분리)은 python3 scripts/test_gate.py 의 [🖍 형광펜 색을 계정에 저장] 에서 검사.
 * 실행: node scripts/test_pen_color_account.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const STOCK = path.join(__dirname, '..', 'stock');
const CHROME = process.env.PW_CHROME || undefined;
const PAGES = { '/economy': 'slack_digest_live.html', '/dig': 'dig_view.html', '/challenge': 'challenge_view.html' };

let PEN = {};            // 가짜 서버가 '계정'에 들고 있는 값 — 진짜 gate.py 처럼 <head> 자리표에 넣어 준다
let posts = [];          // 화면이 /gate/pen 으로 보낸 것
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  const send = (t, b, c = 200) => { res.writeHead(c, { 'Content-Type': t }); res.end(b); };
  if (PAGES[u.pathname]) {
    const head = Object.keys(PEN).length ? '<script>window.__GATE_PEN=' + JSON.stringify(PEN) + ';</script>' : '';
    return send('text/html; charset=utf-8', fs.readFileSync(path.join(STOCK, PAGES[u.pathname]), 'utf8').replace('<!--GATE_THEME-->', head));
  }
  if (u.pathname === '/gate/pen' && req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => {
      const d = JSON.parse(b); posts.push(d); PEN[d.kind] = d.color; send('application/json', JSON.stringify({ ok: true }));
    });
    return;
  }
  send('application/json', JSON.stringify({ ok: false }), 404);   // 나머지 데이터 주소는 이 검사와 무관
});

let fail = 0;
const check = (name, ok, extra = '') => { console.log((ok ? '  ✅ ' : '  ❌ ') + name + (ok ? '' : '  ' + extra)); if (!ok) fail++; };
const pressed = (page, sel) => page.evaluate(s => [...document.querySelectorAll(s)].filter(b => b.getAttribute('aria-pressed') === 'true')
  .map(b => b.id || b.dataset.color || b.dataset.t), sel);
const domClick = (page, sel) => page.evaluate(s => document.querySelector(s).click(), sel);   // 뷰어를 열지 않고 단추만 누른다
const settle = page => page.waitForTimeout(250);

(async () => {
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = 'http://localhost:' + srv.address().port;
  const browser = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
  const open = async (ctx, p) => { const page = await ctx.newPage(); page.on('dialog', d => d.dismiss().catch(() => {})); await page.goto(base + p); await settle(page); return page; };
  const PHOTO = '#lb-c1,#lb-c2,#lb-c3', ED = '#edhl-bar [data-t]', DIG = '#hlbar [data-t]', CH = '#pv-pentools [data-color]';

  console.log('[① 저장된 색이 없으면 예전 기본색]');
  let ctx = await browser.newContext();
  let eco = await open(ctx, '/economy'), dig = await open(ctx, '/dig'), ch = await open(ctx, '/challenge');
  check('신문 요약 사진 펜 = 빨강', (await pressed(eco, PHOTO)).join() === 'lb-c1');
  check('신문 요약 사진 펜 실제 색 값도 빨강', await eco.evaluate(() => M.color) === '#ff5b5b');
  check('챌린지 사진 펜 = 빨강', (await pressed(ch, CH)).join() === '#ff5b5b');
  check('경제 공부 글자 펜 = 노랑', await dig.evaluate(() => HL.tool) === 'y');
  check('아직 서버로 보낸 것 없음', posts.length === 0, JSON.stringify(posts));

  console.log('[② 색을 고르면 계정에 저장]');
  await domClick(eco, '#lb-c2'); await settle(eco);
  check('신문 요약에서 파랑 → /gate/pen {photo, #4da3ff}', posts.length === 1 && posts[0].kind === 'photo' && posts[0].color === '#4da3ff', JSON.stringify(posts));
  check('파랑 단추가 눌린 모양', (await pressed(eco, PHOTO)).join() === 'lb-c2');
  await domClick(eco, '#lb-c3'); await settle(eco);
  check('또 바꾸면(노랑) 마지막 값이 저장', posts.length === 2 && posts[1].color === '#ffd93b' && PEN.photo === '#ffd93b', JSON.stringify(posts));
  await domClick(dig, '#hlbar [data-t="r"]'); await settle(dig);
  check('경제 공부에서 빨강 → /gate/pen {text, r}', posts.length === 3 && posts[2].kind === 'text' && posts[2].color === 'r', JSON.stringify(posts));
  await domClick(dig, '#hlbar [data-t="e"]'); await domClick(dig, '#hlbar [data-t="h"]'); await settle(dig);
  check('🧽 지우개·✋ 손은 색이 아니므로 안 보냄', posts.length === 3, JSON.stringify(posts));
  await ctx.close();

  console.log('[③④ 다른 기기(새 브라우저)에서 열어도 그 색 — 화면끼리도 함께 쓴다]');
  ctx = await browser.newContext();                                   // 새 브라우저 = localStorage 가 비어 있다
  eco = await open(ctx, '/economy'); dig = await open(ctx, '/dig'); ch = await open(ctx, '/challenge');
  check('신문 요약 사진 펜이 노랑으로 시작', (await pressed(eco, PHOTO)).join() === 'lb-c3' && await eco.evaluate(() => M.color) === '#ffd93b');
  check('챌린지 사진 펜도 노랑으로 시작(같은 값)', (await pressed(ch, CH)).join() === '#ffd93b');
  check('경제 공부 글자 펜이 빨강으로 시작', await dig.evaluate(() => HL.tool) === 'r');
  await domClick(eco, '#edhl-t'); await settle(eco);                  // 🖍 를 켜면 도구 줄이 지금 고른 도구에 맞춰 그려진다
  check('신문 요약 사설 펜도 빨강으로 시작(같은 값)', (await pressed(eco, ED)).join() === 'r', (await pressed(eco, ED)).join());
  const n = posts.length;
  await domClick(ch, '#pv-pentools [data-color="#4da3ff"]'); await settle(ch);
  check('챌린지에서 파랑 → 저장', posts.length === n + 1 && posts[n].kind === 'photo' && posts[n].color === '#4da3ff', JSON.stringify(posts.slice(n)));
  await domClick(eco, '#edhl-bar [data-t="b"]'); await settle(eco);
  check('사설에서 파랑 → 저장 {text, b}', posts.length === n + 2 && posts[n + 1].kind === 'text' && posts[n + 1].color === 'b', JSON.stringify(posts.slice(n)));
  check('사설 파랑 단추가 눌린 모양', (await pressed(eco, ED)).join() === 'b');
  const eco2 = await open(ctx, '/economy'), dig2 = await open(ctx, '/dig');
  check('챌린지에서 바꾼 색이 신문 요약에도', (await pressed(eco2, PHOTO)).join() === 'lb-c2');
  check('사설에서 바꾼 색이 경제 공부에도', await dig2.evaluate(() => HL.tool) === 'b');

  console.log('[⑤ ✋ 손으로 둔 브라우저 · 엉뚱한 값]');
  await domClick(dig2, '#hlbar [data-t="h"]'); await settle(dig2);
  const dig3 = await open(ctx, '/dig');
  check('이 브라우저에서 ✋ 손으로 두었으면 다시 열어도 손', await dig3.evaluate(() => HL.tool) === 'h');
  await domClick(dig3, '#hlbar [data-t="y"]'); await settle(dig3);
  check('…거기서 노랑을 고르면 다시 저장', PEN.text === 'y');
  await ctx.close();
  PEN = { photo: 'javascript:alert(1)', text: 'zzz' };
  ctx = await browser.newContext();
  eco = await open(ctx, '/economy'); dig = await open(ctx, '/dig'); ch = await open(ctx, '/challenge');
  check('허용 목록에 없는 값이 내려오면 기본색(사진 빨강·글자 노랑)',
    (await pressed(eco, PHOTO)).join() === 'lb-c1' && (await pressed(ch, CH)).join() === '#ff5b5b' && await dig.evaluate(() => HL.tool) === 'y');
  await ctx.close();

  await browser.close(); srv.close();
  console.log('\n결과: ' + (fail ? '❌ 실패 ' + fail + '건' : '전부 통과'));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
