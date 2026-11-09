/**
 * test_ed_highlight.js — 신문 요약 화면 맨 아래 '사설' 형광펜(관리자 전용, 서버 저장, 경제 공부(디그)와 같은 방식) 확인
 * (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청
 *   ① 관리자가 아니면(403) 🖍 단추·도구 줄이 안 나오고 그어도 아무 일 없음
 *   ② 🖍 기본은 꺼짐 — 그어도 칠해지지 않고 평소처럼 글자가 선택됨
 *   ③ 켜고 사설 글자 위를 쭉 그으면 손을 떼는 순간 칠해지고 서버에 날짜별로 저장됨(글자는 하나도 안 바뀜)
 *   ④ 접혀서 안 보이는 문단은 칠하지 않음 · '전문 펼치기'·원문 링크는 펜일 때도 평소처럼 눌림
 *   ⑤ 🧽 지우개(긋기·누르기) · Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y · ↶ ↷ · 🗑 모두 지우기 · ✋ 손
 *   ⑥ 마우스 커서가 펜·지우개 모양 · 도구 줄은 사설 칸이 화면에 보일 때만 · 아래 책갈피/구역 이동 줄과 안 겹침
 *   ⑦ 날짜를 바꿨다 돌아오면 그 날짜 표시가 다시 칠해짐(다시 그릴 때 지워지지 않음) · 새로고침 유지 · 409(다른 창이 먼저 저장)
 *   ⑧ 폰 390px: 도구 줄이 한 줄·화면 안, 손가락으로 쭉 그어 칠해짐
 * 서버 쪽(권한·검증·저장·버전)은 python3 scripts/test_dig_marks.py 에서 검사.
 * 실행: node scripts/test_ed_highlight.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

function makePng(w, h) {
  const crc32 = (buf) => { let c, crc = 0xffffffff; for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = c ^ (crc >>> 8); } return (crc ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const tc = Buffer.concat([Buffer.from(type), data]); const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(tc)); return Buffer.concat([len, tc, crc]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 235)]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: h }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(400, 600);
const BRIEF = '*[신문요약 1/1] 신문 요약*\n1. 기사 제목\n• WHAT: 내용임.\n• WHY: 이유임.\n• HOW: 방법임.\n• 사진: 03';
const EDITORIAL = {
  ok: true,
  items: [
    { press: '매일경제', title: '금리 인하 기대와 가계부채 관리', published: '2026-11-09T00:10:00', url: 'https://example.com/a',
      paras: ['한국은행이 기준금리를 동결하면서 시장의 인하 기대가 한풀 꺾였다. 가계부채 증가세가 여전히 가파르기 때문이다.',
              '정부는 대출 규제를 단계적으로 강화하겠다고 밝혔지만 실수요자 보호 방안은 구체적이지 않다는 지적이 나온다.',
              '세 번째 문단은 접혀 있어 처음에는 보이지 않는다. 전문을 펼쳐야 읽을 수 있다.',
              '네 번째 문단도 마찬가지로 접혀 있다.'] },
    { press: '한국경제', title: '반도체 수출 호조를 이어가려면', published: '2026-11-09T00:20:00', url: 'https://example.com/b',
      paras: ['반도체 수출이 석 달 연속 증가세를 이어갔다. 인공지능 서버 수요가 늘어난 덕분이다.',
              '다만 중국 업체의 추격과 미국의 규제 변수는 여전히 부담이다.'] },
  ],
};
let ADMIN = true, STORE = {}, REVS = {}, posts = [], FORCE409 = false;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  const D = u.searchParams.get('date') || '2026-11-09';
  const send = (t, b, c = 200) => { res.writeHead(c, { 'Content-Type': t }); res.end(b); };
  const json = (o, c = 200) => send('application/json', JSON.stringify(o), c);
  if (u.pathname === '/' || u.pathname === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u.pathname === '/economy/data') return json({ date: D, messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] });
  if (u.pathname === '/api/news/today') {
    const images = Array.from({ length: 6 }, (_, i) => { const n = String(i + 1).padStart(2, '0') + '.jpg'; return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' }; });
    return json({ ok: true, ready: true, date: D, count: 6, images });
  }
  if (u.pathname === '/api/news/editorial') return json(EDITORIAL);
  if (u.pathname === '/api/news/edmarks' && req.method === 'GET') return ADMIN ? json({ ok: true, marks: STORE[D] || [], revision: REVS[D] || 0 }) : json({ ok: false }, 403);
  if (u.pathname === '/api/news/edmarks' && req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => {
      const d = JSON.parse(b); posts.push(d);
      if (!ADMIN) return json({ ok: false }, 403);
      if (FORCE409 || d.revision !== (REVS[d.id] || 0)) { FORCE409 = false; return json({ ok: false, conflict: true, marks: [{ u: 5, s: 0, e: 4, c: 'r', q: '반도체 ' }], revision: (REVS[d.id] || 0) + 5 }, 409); }
      STORE[d.id] = d.marks; REVS[d.id] = (REVS[d.id] || 0) + 1; json({ ok: true, revision: REVS[d.id], count: d.marks.length });
    });
    return;
  }
  if (u.pathname === '/api/news/terms') return json({ ok: false }, 403);
  if (u.pathname === '/api/news/pagetext') return json({ ok: false });
  if (u.pathname === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const UNITS = '#mk-ed-list .mk-ed-item h3, #mk-ed-list .mk-ed-body p';
  const open = async (opts = {}, url = '/economy') => {
    const ctx = await browser.newContext(Object.assign({ viewport: { width: 1100, height: 800 } }, opts));
    const page = await ctx.newPage();
    page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
    await page.goto(base + url);
    await page.waitForSelector('#mk-ed-list .mk-ed-item');
    await page.waitForTimeout(500);
    return { ctx, page };
  };
  const toEd = async page => { await page.waitForTimeout(600); await page.evaluate(() => document.getElementById('mk-ed').scrollIntoView({ block: 'start' })); await page.waitForTimeout(500); };   // (사진 목록 등이 늦게 떠 내용이 밀릴 수 있어 잠깐 기다린다)
  const today = page => page.evaluate(() => state.date);
  const charPt = (page, u, k, frac) => page.evaluate(([UNITS, u, k, frac]) => {
    const el = [...document.querySelectorAll(UNITS)][u];
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let pos = 0, n;
    while ((n = tw.nextNode())) {
      if (k < pos + n.nodeValue.length) { const r = document.createRange(); r.setStart(n, k - pos); r.setEnd(n, k - pos + 1); const b = r.getBoundingClientRect(); return { x: b.left + b.width * frac, y: b.top + b.height / 2 }; }
      pos += n.nodeValue.length;
    }
  }, [UNITS, u, k, frac]);
  const draw = async (page, u, s, e, u2 = null, e2 = null) => {
    await page.evaluate(([UNITS, u]) => [...document.querySelectorAll(UNITS)][u].scrollIntoView({ block: 'center' }), [UNITS, u]); await page.waitForTimeout(250);   // 글자를 화면 안으로
    const a = await charPt(page, u, s, 0.25), b = await charPt(page, u2 === null ? u : u2, (u2 === null ? e : e2) - 1, 0.75);
    await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 4 }); await page.mouse.move(b.x, b.y, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(150);
  };
  const marksText = page => page.$$eval('#mk-ed-list mark.hl', ms => ms.map(m => m.className.replace('hl hl-', '') + ':' + m.textContent));
  const listText = page => page.$eval('#mk-ed-list', m => m.textContent);
  const settle = page => page.waitForTimeout(800);
  const lastMarks = u => ((posts[posts.length - 1] || { marks: [] }).marks).filter(m => m.u === u).sort((a, b) => a.s - b.s).map(m => [m.c, m.s, m.e]);
  const cur = (page, sel) => page.$eval(sel, e => getComputedStyle(e).cursor);

  console.log('\n[① 관리자가 아니면]');
  ADMIN = false; STORE = {}; REVS = {}; posts = [];
  let { ctx, page } = await open();
  await toEd(page);
  check(await page.$eval('#edhl-t', b => b.hidden) && await page.$eval('#edhl-bar', b => b.hidden), '🖍 단추도 도구 줄도 안 보임(서버 403)');
  await draw(page, 1, 0, 8); await settle(page);
  check((await marksText(page)).length === 0 && posts.length === 0, '글자 위를 그어도 아무 일 없음(칠하기·저장 요청 0건)');
  await ctx.close();

  ADMIN = true; STORE = {}; REVS = {}; posts = [];
  console.log('\n[② 꺼진 기본 상태]');
  ({ ctx, page } = await open());
  await toEd(page);
  const DAY = await today(page);
  const units = await page.$$eval(UNITS, us => us.map(u => u.textContent));
  const before = await listText(page);
  check(units.length === 8, '글 덩어리 8개(제목 2 + 문단 6, 접힌 문단 포함)', String(units.length));
  check(!(await page.$eval('#edhl-t', b => b.hidden)) && await page.$eval('#edhl-bar', b => b.hidden), '관리자: 🖍 줄 긋기 단추는 보이고 도구 줄은 꺼져 있음(실수로 칠하지 않게 기본은 꺼짐)');
  await draw(page, 1, 0, 10);
  check((await marksText(page)).length === 0 && posts.length === 0 && (await page.evaluate(() => getSelection().toString())) === units[1].slice(0, 10), '그으면 칠해지지 않고 평소처럼 글자가 선택됨(복사 가능)');
  await page.evaluate(() => getSelection().removeAllRanges());

  console.log('\n[③ 켜고 쭉 그으면 칠해짐]');
  await page.click('#edhl-t'); await page.waitForTimeout(200);
  check(!(await page.$eval('#edhl-bar', b => b.hidden)) && await page.$eval('#edhl-bar [data-t="y"]', b => b.getAttribute('aria-pressed')) === 'true', '켜면 도구 줄이 나오고 노랑 펜이 골라져 있음');
  check(await page.$eval('#mk-ed-list', m => getComputedStyle(m).touchAction) === 'none', '펜일 땐 사설 위에서 끌어도 스크롤되지 않음');
  await draw(page, 0, 0, 5); await settle(page);                                      // 제목 "금리 인하 기대" 앞부분
  check((await marksText(page)).join('|') === 'y:' + units[0].slice(0, 5), '제목 앞부분을 쭉 그으니 손을 떼자 바로 노랑으로 칠해짐', (await marksText(page)).join('|'));
  check(posts.length === 1 && posts[0].id === DAY && posts[0].revision === 0, '서버에 날짜별로 저장 요청 1번', JSON.stringify({ id: posts[0] && posts[0].id }));
  const m0 = posts[0].marks[0];
  check(posts[0].marks.length === 1 && m0.u === 0 && m0.s === 0 && m0.e === 5 && m0.c === 'y' && m0.q === units[0].slice(0, 5), '저장 내용 = 덩어리 0 · 0~5 · 노랑 · 앞부분 글', JSON.stringify(m0));
  check(await listText(page) === before, '글자는 하나도 안 바뀜(감싸기만)');
  await page.click('#edhl-bar [data-t="r"]');
  await draw(page, 1, 0, 14); await settle(page);                                      // 문단 1 (여러 줄)
  const red = (await marksText(page)).filter(x => x.startsWith('r:')).map(x => x.slice(2)).join('');
  check(red === units[1].slice(0, 14), '문단 위를 그어 빨강으로 칠함(여러 줄에 걸쳐도 정확히 그은 글자)', red);

  console.log('\n[④ 접힌 문단·전문 펼치기·링크]');
  await page.click('#edhl-bar [data-t="b"]');
  posts.length = 0;
  await draw(page, 2, units[2].length - 8, 0, 5, 6); await settle(page);              // 문단2 끝 ~ (접힌 문단 3·4 건너뛰고) 둘째 사설 제목 앞 6글자
  const blue = posts[posts.length - 1].marks.filter(m => m.c === 'b').sort((a, b) => a.u - b.u);
  check(blue.length === 2 && blue[0].u === 2 && blue[1].u === 5 && !blue.some(m => m.u === 3 || m.u === 4), '문단에서 다음 사설 제목까지 그어도 접혀서 안 보이는 문단(3·4)은 칠하지 않음', JSON.stringify(blue.map(m => [m.u, m.s, m.e])));
  await page.click('.mk-ed-more'); await page.waitForTimeout(200);
  check(await page.$eval('#mk-ed-b0', b => b.classList.contains('open')), '펜이 켜져 있어도 "전문 펼치기" 단추는 평소처럼 눌림');
  check((await marksText(page)).filter(x => /세 번째|네 번째/.test(x)).length === 0, '펼친 문단에는 칠해진 게 없음');
  await draw(page, 3, 0, 8); await settle(page);
  check(lastMarks(3).length === 1, '펼친 뒤에는 그 문단도 칠해짐');
  const popup = () => ctx.waitForEvent('page', { timeout: 1200 }).then(() => true, () => false);
  let w = popup(); await page.click('.mk-ed-meta a'); check(await w, '"원문 보기" 링크도 펜일 때 평소처럼 열림');

  console.log('\n[⑤ 지우개·되돌리기·다시·모두 지우기·손]');
  await page.click('#edhl-bar [data-t="y"]');
  await draw(page, 5, 0, 6); await settle(page);                                       // 둘째 사설 제목 앞 "반도체 수출" 노랑 (파랑을 덮음)
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 6]]), '겹쳐 칠하면 기존 표시가 잘려 나감(파랑 0~6 → 노랑)', JSON.stringify(lastMarks(5)));
  await page.click('#edhl-bar [data-t="e"]');
  await draw(page, 5, 1, 3); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 1], ['y', 3, 6]]), '🧽 지우개로 그으면 그 부분만 지워짐', JSON.stringify(lastMarks(5)));
  const pt = await page.evaluate(() => { const ms = [...document.querySelectorAll('#mk-ed-list h3 mark.hl')]; const m = ms[ms.length - 1].getBoundingClientRect(); return { x: m.left + m.width / 2, y: m.top + m.height / 2 }; });
  await page.mouse.click(pt.x, pt.y); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 1]]), '지우개로 칠한 조각을 한 번 누르면 그 조각이 지워짐', JSON.stringify(lastMarks(5)));
  await page.keyboard.press('Control+z'); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 1], ['y', 3, 6]]), 'Ctrl+Z: 방금 지운 조각이 되살아남(서버에도 저장)', JSON.stringify(lastMarks(5)));
  await page.keyboard.press('Control+z'); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 6]]), 'Ctrl+Z 한 번 더: 지우개 긋기도 되돌림');
  await page.keyboard.press('Control+Shift+z'); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 1], ['y', 3, 6]]), 'Ctrl+Shift+Z: 다시 하기');
  await page.click('#edhl-bar [data-a="undo"]'); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 6]]), '도구 줄 ↶ 단추도 되돌리기');
  await page.click('#edhl-bar [data-a="redo"]'); await settle(page);
  check(JSON.stringify(lastMarks(5)) === JSON.stringify([['y', 0, 1], ['y', 3, 6]]), '도구 줄 ↷ 단추도 다시 하기');
  await page.click('#edhl-bar [data-t="y"]');
  const cnt = (await marksText(page)).length;
  page.once('dialog', d => d.dismiss());
  await page.click('#edhl-bar [data-a="clear"]'); await settle(page);
  check((await marksText(page)).length === cnt, '🗑 확인창에서 취소하면 그대로');
  page.once('dialog', d => d.accept());
  await page.click('#edhl-bar [data-a="clear"]'); await settle(page);
  check((await marksText(page)).length === 0 && posts[posts.length - 1].marks.length === 0, '🗑 확인하면 이 날짜 사설의 형광펜이 모두 지워지고 서버에도 반영');
  await page.keyboard.press('Control+z'); await settle(page);
  check((await marksText(page)).length === cnt, '모두 지운 것도 Ctrl+Z 로 되살릴 수 있음');
  await page.click('#edhl-bar [data-t="h"]'); await page.waitForTimeout(100);
  const np = posts.length;
  await draw(page, 6, 0, 8); await settle(page);
  check(posts.length === np && await page.evaluate(() => getSelection().toString()) === units[6].slice(0, 8), '✋ 에선 그어도 칠해지지 않고 글자가 선택됨');
  await page.click('#edhl-bar [data-t="b"]'); await settle(page);
  check(lastMarks(6).length === 1 && lastMarks(6)[0][0] === 'b', '선택해 둔 채 파랑을 누르면 그 글자에 칠해짐');

  console.log('\n[⑥ 커서·도구 줄 보이는 때·겹침]');
  await page.click('#edhl-bar [data-t="y"]');
  const penY = await cur(page, '#mk-ed-list');
  check(/^url\("data:image\/svg\+xml,/.test(penY) && /, text$/.test(penY), '글 위 커서가 펜 그림(SVG)으로 바뀜', penY.slice(0, 50));
  check(await cur(page, '#mk-ed-list h3') === penY && await cur(page, '#mk-ed-list mark.hl') === penY, '제목·칠한 글자 위에서도 같은 펜 커서');
  check(await cur(page, '.mk-ed-more') === 'pointer' && await cur(page, '#edhl-bar button') !== penY, '"전문" 단추·도구 줄 위에서는 평소 커서');
  await page.click('#edhl-bar [data-t="r"]'); const penR = await cur(page, '#mk-ed-list');
  await page.click('#edhl-bar [data-t="e"]'); const eras = await cur(page, '#mk-ed-list');
  check(new Set([penY, penR, eras]).size === 3, '색마다 다른 펜, 🧽 는 지우개 그림');
  await page.click('#edhl-bar [data-t="h"]');
  check(!/^url\(/.test(await cur(page, '#mk-ed-list')), '✋ 손일 땐 평소 커서');
  await page.click('#edhl-bar [data-t="y"]');
  const geo = await page.evaluate(() => { const r = n => { const e = document.querySelector(n); if (!e) return null; const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width }; }; return { bar: r('#edhl-bar'), ra: r('.reader-actions'), vw: innerWidth, vh: innerHeight }; });
  const hit = (a, b) => a && b && b.w > 0 && !(a.r <= b.l || b.r <= a.l || a.b <= b.t || b.b <= a.t);
  check(geo.bar && geo.bar.b <= geo.vh && !hit(geo.bar, geo.ra), '도구 줄이 책갈피·용어 버튼(오른쪽 아래)과 안 겹침', JSON.stringify({ bar: geo.bar && [geo.bar.l | 0, geo.bar.t | 0, geo.bar.r | 0, geo.bar.b | 0], ra: geo.ra && [geo.ra.l | 0, geo.ra.t | 0, geo.ra.r | 0, geo.ra.b | 0] }));
  await page.evaluate(() => { const sp = document.createElement('div'); sp.id = 'spacer'; sp.style.height = '3000px'; document.getElementById('mk-ed').before(sp); window.scrollTo(0, 0); });   // (가짜 화면이 짧아서 사설 칸 앞에 빈 칸을 끼워 넣어 사설이 화면 밖으로 나가게 한다)
  await page.waitForFunction(() => document.getElementById('edhl-bar').hidden, null, { timeout: 8000 }).catch(() => {});   // (화면이 갱신될 때 알림이 오므로 바뀔 때까지 기다린다)
  check(await page.$eval('#edhl-bar', b => b.hidden) && !(await page.evaluate(() => document.body.classList.contains('edhl-on'))), '위로 올라가 사설 칸이 안 보이면 도구 줄이 사라짐(요약을 읽을 때 방해 안 함)');
  await page.evaluate(() => document.getElementById('spacer').remove()); await toEd(page);
  await page.waitForFunction(() => !document.getElementById('edhl-bar').hidden, null, { timeout: 8000 }).catch(() => {});
  check(!(await page.$eval('#edhl-bar', b => b.hidden)), '사설 칸이 보이면 다시 나타남');
  await page.click('#edhl-t'); await page.waitForTimeout(100);
  check(await page.$eval('#edhl-bar', b => b.hidden) && !/^url\(/.test(await cur(page, '#mk-ed-list')), '🖍 를 끄면 도구 줄이 사라지고 평소 커서로 돌아감');
  const nq = posts.length;
  await page.keyboard.press('Control+z'); await settle(page);
  check(posts.length === nq, '꺼진 동안엔 Ctrl+Z 도 안 먹음');
  check((await marksText(page)).length > 0, '끄더라도 칠한 표시는 그대로 보임');
  await page.click('#edhl-t'); await page.waitForTimeout(100);

  console.log('\n[⑦ 날짜 바꿨다 돌아오기·새로고침·409]');
  const savedCount = (STORE[DAY] || []).length;
  const other = '2026-11-06';
  await page.evaluate(d => { const e = document.getElementById('datepick'); e.value = d; e.dispatchEvent(new Event('change')); }, other);
  await page.waitForFunction(o => document.getElementById('mk-ed-date').textContent.replace(/\./g, '-').includes(o.slice(5)), other, { timeout: 8000 });
  await page.waitForTimeout(600);
  check((await marksText(page)).length === 0, '다른 날짜로 가면 그 날짜의 표시(없음)만 보임');
  await page.evaluate(d => { const e = document.getElementById('datepick'); e.value = d; e.dispatchEvent(new Event('change')); }, DAY);
  await page.waitForFunction(() => document.querySelector('#mk-ed-list mark.hl'), null, { timeout: 8000 });
  check((await marksText(page)).length > 0 && savedCount > 0, '원래 날짜로 돌아오면 서버에 저장된 표시가 다시 칠해짐(다시 그려도 안 지워짐)');
  await ctx.close();
  ({ ctx, page } = await open());
  await toEd(page);
  check((await marksText(page)).length > 0 && await page.$eval('#edhl-t', b => b.getAttribute('aria-pressed')) === 'false', '새로고침해도 표시가 유지됨(새 브라우저 창이라 켠 상태는 꺼짐)');
  await ctx.close();
  ({ ctx, page } = await open());
  await toEd(page);
  await page.click('#edhl-t'); STORE[DAY] = []; REVS[DAY] = 0; FORCE409 = false; posts.length = 0;
  await page.reload(); await page.waitForSelector('#mk-ed-list .mk-ed-item'); await toEd(page);
  check(!(await page.$eval('#edhl-bar', b => b.hidden)), '켠 상태는 이 브라우저가 기억해 새로고침 뒤에도 켜져 있음');
  FORCE409 = true;
  await draw(page, 1, 0, 8); await page.waitForTimeout(1300);
  check((await marksText(page)).join('|') === 'r:' + (await page.$$eval(UNITS, us => us[5].textContent)).slice(0, 4), '다른 창이 먼저 저장했으면(409) 서버의 최신 표시로 바뀜', (await marksText(page)).join('|'));
  check(await page.$eval('#edhl-bar [data-a="undo"]', b => b.disabled), '그때는 되돌리기 기록도 비움(남의 변경을 되돌리지 않게)');
  await ctx.close();

  console.log('\n[⑧ 폰 390px]');
  STORE = {}; REVS = {}; posts.length = 0;
  ({ ctx, page } = await open({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true }));
  await toEd(page);
  await page.tap('#edhl-t'); await page.waitForTimeout(250);
  const g = await page.evaluate(() => { const r = n => { const e = document.querySelector(n); if (!e) return null; const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; }; return { bar: r('#edhl-bar'), ra: r('.reader-actions'), sj: r('.section-jump'), vw: innerWidth, vh: innerHeight }; });
  check(g.bar && g.bar.l >= 0 && g.bar.r <= g.vw && g.bar.b <= g.vh && g.bar.h < 64, '폰에서 도구 줄이 화면 안·한 줄', JSON.stringify(g.bar));
  check(!hit(g.bar, g.ra) && !hit(g.bar, g.sj), '폰에서 도구 줄이 책갈피·용어 버튼·구역 이동 줄과 안 겹침', JSON.stringify({ ra: g.ra && [g.ra.t | 0, g.ra.b | 0], sj: g.sj && [g.sj.t | 0, g.sj.b | 0] }));
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '가로 스크롤 없음');
  const cdp = await ctx.newCDPSession(page);
  await page.evaluate(UN => [...document.querySelectorAll(UN)][1].scrollIntoView({ block: 'center' }), UNITS); await page.waitForTimeout(300);
  const a = await charPt(page, 1, 0, 0.25), b = await charPt(page, 1, 9, 0.75);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: a.x, y: a.y }] });
  for (let i = 1; i <= 6; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: a.x + (b.x - a.x) * i / 6, y: a.y + (b.y - a.y) * i / 6 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await settle(page);
  const u1 = (await page.$$eval(UNITS, us => us.map(u => u.textContent)))[1];
  check((await marksText(page)).join('') === 'y:' + u1.slice(0, 10), '손가락으로 쭉 그으면 칠해짐', (await marksText(page)).join('|'));
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
