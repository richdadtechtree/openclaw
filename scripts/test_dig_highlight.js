/**
 * test_dig_highlight.js — 경제 공부(디그) 글 형광펜(관리자 전용, 서버 저장) 화면 확인 (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청
 *   ① 관리자가 아니면(403) 단추·색 줄이 안 나오고 글자를 선택해도 아무 일 없음
 *   ② 글자를 선택하면 색 줄이 나오고, 노랑을 누르면 그 글자만 칠해지고 서버에 (덩어리 번호·글자 위치·색·앞부분 글) 이 저장됨
 *   ③ 굵은 글·링크가 섞인 문단도 글자(textContent)는 하나도 안 바뀌고 <mark> 로만 감싸짐
 *   ④ 두 문단에 걸친 선택은 문단마다 한 조각씩, 겹쳐 칠하면 기존 표시가 잘려 나가고, 같은 색이 맞닿으면 하나로 합쳐짐, 🧽 로 지움
 *   ⑤ 새로고침해도 서버에 저장된 표시가 같은 글자에 다시 칠해짐 · 글이 바뀌어 안 맞는 표시는 건너뜀
 *   ⑥ 형광펜 끄기/켜기(기억) · 칠한 글자를 누르면 선택돼 바로 지울 수 있음 · 다른 창이 먼저 저장했으면(409) 최신으로 교체
 *   ⑦ 폰 390px 에서 색 줄이 화면 안·가로 스크롤 없음 · 인쇄용(?print=1)은 형광펜 요청 0건
 * 서버 쪽(권한·검증·저장·버전)은 python3 scripts/test_dig_marks.py 에서 따로 검사.
 * 실행: node scripts/test_dig_highlight.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'dig_view.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const ISSUE = {
  id: '2026-11-09', date_text: '2026.11.9(월)', tags: '#블루쓰나미 #AIDC', sent: '2026-11-09T06:07:00',
  blocks: [
    { k: 'sec', text: '오늘의 디깅' },
    { k: 'title', text: '파랗게 물든 미국, 아니 내 계좌' },
    { k: 'p', parts: [{ t: '오늘도 미국 중간선거와 ' }, { t: '블루 쓰나미', b: true }, { t: '로 불릴 정도의 압도적인 승리를 거둔 지 이틀째였던 지난 5일, ' }, { t: '자세히 보기', a: 'https://example.com/x' }, { t: ' 주식시장에서 기록적인 폭락이 벌어졌어요.' }] },
    { k: 'p', parts: [{ t: '여파는 다음날 한국으로 이어졌어요. 서킷브레이커가 발동됐고 하루 만에 6%나 하락했어요.' }] },
    { k: 'sec', text: '3줄 요약' },
    { k: 'sum', text: '나스닥 5.52% 하락' }, { k: 'sum', text: '코스피 6% 하락' },
  ],
};
let ADMIN = true, STORE = [], REV = 0, posts = [], marksGets = 0, FORCE409 = false;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  const send = (t, b, c = 200) => { res.writeHead(c, { 'Content-Type': t }); res.end(b); };
  const json = (o, c = 200) => send('application/json', JSON.stringify(o), c);
  if (u.pathname === '/dig') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u.pathname === '/api/dig/list') return json({ ok: true, items: [{ id: '2026-11-09', title: '파랗게 물든 미국' }] });
  if (u.pathname === '/api/dig/item') return json({ ok: true, issue: ISSUE });
  if (u.pathname === '/api/dig/marks' && req.method === 'GET') { marksGets++; return ADMIN ? json({ ok: true, marks: STORE, revision: REV }) : json({ ok: false }, 403); }
  if (u.pathname === '/api/dig/marks' && req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => {
      const d = JSON.parse(b); posts.push(d);
      if (!ADMIN) return json({ ok: false }, 403);
      if (FORCE409 || d.revision !== REV) {            // 다른 창이 먼저 저장한 상황을 흉내
        FORCE409 = false;
        return json({ ok: false, conflict: true, marks: [{ u: 3, s: 0, e: 5, c: 'r', q: '여파는 다' }], revision: REV + 5 }, 409);
      }
      STORE = d.marks; REV += 1; json({ ok: true, revision: REV, count: STORE.length });
    });
    return;
  }
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const open = async (opts = {}, url = '/dig') => {
    const ctx = await browser.newContext(Object.assign({ viewport: { width: 1100, height: 800 } }, opts));
    const page = await ctx.newPage();
    page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
    await page.goto(base + url);
    await page.waitForSelector('#main .card');
    await page.waitForTimeout(400);
    return { ctx, page };
  };
  // 덩어리 i 의 글자 [s,e) (또는 i 의 s 부터 i2 의 e2 까지)를 선택 상태로 만든다 — 끌어서 선택한 것과 같은 효과
  const select = (page, i, s, e, i2 = null, e2 = null) => page.evaluate(([i, s, e, i2, e2]) => {
    const U = [...document.querySelectorAll('#main p, #main h2.title, #main h2.sec, #main h3, #main li, #main .cap')];
    const at = (u, k) => { const tw = document.createTreeWalker(u, NodeFilter.SHOW_TEXT); let pos = 0, n; while ((n = tw.nextNode())) { if (k <= pos + n.nodeValue.length) return [n, k - pos]; pos += n.nodeValue.length; } };
    const r = document.createRange(); const a = at(U[i], s), b = at(U[i2 === null ? i : i2], i2 === null ? e : e2);
    r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  }, [i, s, e, i2, e2]);
  const marksText = page => page.$$eval('#main mark.hl', ms => ms.map(m => m.className.replace('hl hl-', '') + ':' + m.textContent));
  const bodyText = page => page.$eval('#main', m => m.textContent);

  console.log('\n[① 관리자가 아니면]');
  ADMIN = false; STORE = []; REV = 0; posts = [];
  let { ctx, page } = await open();
  check(await page.$eval('#hlt', b => b.hidden), '형광펜 단추가 안 보임(서버 403)');
  await select(page, 0, 0, 5); await page.waitForTimeout(300);
  check(await page.$eval('#hlbar', b => b.hidden), '글자를 선택해도 색 줄이 안 나옴');
  await ctx.close();

  console.log('\n[② 선택 → 색 줄 → 칠하기 → 서버 저장]');
  ADMIN = true; STORE = []; REV = 0; posts = [];
  ({ ctx, page } = await open());
  check(!(await page.$eval('#hlt', b => b.hidden)), '관리자: 🖍 형광펜 단추가 보임');
  const before = await bodyText(page);
  const units = await page.$$eval('#main p, #main h2.title, #main h2.sec, #main h3, #main li, #main .cap', us => us.map(u => u.textContent));
  check(units.length === 6, '글 덩어리 6개(구역 제목·큰 제목·문단 2·요약 줄 2)', String(units.length));
  await select(page, 1, 0, 7); await page.waitForTimeout(300);          // '파랗게 물든 ' — 끝의 공백은 칠하지 않고 뺌
  check(!(await page.$eval('#hlbar', b => b.hidden)), '글자를 선택하면 색 줄이 나옴');
  await page.click('#hlbar [data-c="y"]'); await page.waitForTimeout(900);
  check((await marksText(page)).join('|') === 'y:' + units[1].slice(0, 6), '제목 앞 "파랗게 물든" 만 노랑으로 칠해짐(끝 공백은 뺌)', (await marksText(page)).join('|'));
  check(posts.length === 1 && posts[0].id === '2026-11-09' && posts[0].revision === 0, '서버에 저장 요청 1번(호 번호·버전 0)');
  const m0 = posts[0].marks[0];
  check(posts[0].marks.length === 1 && m0.u === 1 && m0.s === 0 && m0.e === 6 && m0.c === 'y' && m0.q === units[1].slice(0, 6), '저장 내용 = 덩어리 1 · 0~6 · 노랑 · 앞부분 글', JSON.stringify(m0));
  check(await bodyText(page) === before, '글자는 하나도 안 바뀜(감싸기만)');
  check(await page.$eval('#hlbar', b => b.hidden) && await page.evaluate(() => getSelection().isCollapsed), '칠한 뒤 색 줄이 닫히고 선택이 풀림');

  console.log('\n[③ 굵은 글·링크가 섞인 문단]');
  const p2 = units[2];
  const s0 = p2.indexOf('블루'), e0 = p2.indexOf('자세히') + 3;
  await select(page, 2, s0, e0); await page.waitForTimeout(300);
  await page.click('#hlbar [data-c="r"]'); await page.waitForTimeout(900);
  const red = (await marksText(page)).filter(x => x.startsWith('r:')).map(x => x.slice(2)).join('');
  check(red === p2.slice(s0, e0), '굵은 글·링크 경계를 넘어도 칠한 글자를 이으면 정확히 선택한 글자', red);
  check(await bodyText(page) === before, '여전히 글자는 하나도 안 바뀜');
  check(await page.$eval('#main p a', a => a.href.startsWith('https://example.com') && a.textContent.length > 0), '링크는 그대로 링크');

  console.log('\n[④ 두 문단에 걸침·겹침·합치기·지우기]');
  posts.length = 0;
  await select(page, 2, p2.length - 6, 0, 3, 5); await page.waitForTimeout(300);     // 문단2 끝 6글자 ~ 문단3 앞 5글자
  await page.click('#hlbar [data-c="b"]'); await page.waitForTimeout(900);
  const blue = posts[posts.length - 1].marks.filter(m => m.c === 'b').sort((a, b) => a.u - b.u);
  check(blue.length === 2 && blue[0].u === 2 && blue[1].u === 3 && blue[0].e === p2.length && blue[1].s === 0 && blue[1].e === 5,
        '두 문단에 걸친 선택은 문단마다 한 조각씩(파랑 2조각)', JSON.stringify(blue.map(m => [m.u, m.s, m.e])));
  await select(page, 3, 0, 2); await page.waitForTimeout(300);                        // 겹침: 앞 2글자를 노랑으로
  await page.click('#hlbar [data-c="y"]'); await page.waitForTimeout(900);
  const l2 = posts[posts.length - 1].marks.filter(m => m.u === 3).sort((a, b) => a.s - b.s);
  check(l2.length === 2 && l2[0].c === 'y' && l2[0].e === 2 && l2[1].c === 'b' && l2[1].s === 2 && l2[1].e === 5, '겹쳐 칠하면 기존 표시가 잘려 나감(노랑 0~2 + 파랑 2~5)', JSON.stringify(l2.map(m => [m.c, m.s, m.e])));
  await select(page, 3, 2, 3); await page.waitForTimeout(300);                        // 합치기: 바로 옆 1글자도 노랑으로
  await page.click('#hlbar [data-c="y"]'); await page.waitForTimeout(900);
  const l3 = posts[posts.length - 1].marks.filter(m => m.u === 3).sort((a, b) => a.s - b.s);
  check(l3.length === 2 && l3[0].c === 'y' && l3[0].s === 0 && l3[0].e === 3 && l3[1].c === 'b' && l3[1].s === 3 && l3[1].e === 5,
        '같은 색이 맞닿으면 하나로 합쳐짐(노랑 0~2 + 0~2 옆 2~3 → 노랑 0~3 한 조각, 파랑은 3~5)', JSON.stringify(l3.map(m => [m.c, m.s, m.e])));
  await select(page, 3, 1, 3); await page.waitForTimeout(300);                        // 지우기
  await page.click('#hlbar [data-c=""]'); await page.waitForTimeout(900);
  const l4 = posts[posts.length - 1].marks.filter(m => m.u === 3).sort((a, b) => a.s - b.s);
  check(l4.length === 2 && l4[0].c === 'y' && l4[0].s === 0 && l4[0].e === 1 && l4[1].c === 'b' && l4[1].s === 3 && l4[1].e === 5, '🧽 지우기: 노랑 1~3 만 지워지고 노랑 0~1 과 파랑 3~5 는 남음', JSON.stringify(l4.map(m => [m.c, m.s, m.e])));
  check(await bodyText(page) === before, '지우고 겹쳐도 글자는 끝까지 그대로');
  await ctx.close();

  console.log('\n[⑤ 새로고침해도 유지 · 안 맞는 표시는 건너뜀]');
  ({ ctx, page } = await open());
  const reloaded = await marksText(page);
  check(reloaded.length >= 4, '서버에 저장된 표시가 새로고침 뒤에도 다시 칠해짐', reloaded.join('|').slice(0, 80));
  check(await bodyText(page) === before, '글자 그대로');
  await ctx.close();
  STORE = [{ u: 1, s: 0, e: 3, c: 'y', q: '틀린글' }, { u: 1, s: 0, e: 3, c: 'r', q: units[1].slice(0, 3) }, { u: 99, s: 0, e: 3, c: 'b', q: 'x' }];
  ({ ctx, page } = await open());
  check((await marksText(page)).join('|') === 'r:' + units[1].slice(0, 3), '글이 안 맞거나 없는 덩어리의 표시는 건너뛰고 맞는 것만 칠함', (await marksText(page)).join('|'));
  await ctx.close();

  console.log('\n[⑥ 끄기·켜기 · 눌러서 지우기 · 다른 창이 먼저 저장(409)]');
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open());
  await select(page, 1, 0, 3); await page.waitForTimeout(300);
  await page.click('#hlbar [data-c="y"]'); await page.waitForTimeout(900);
  await page.click('#hlt'); await page.waitForTimeout(100);
  check(await page.$eval('#hlt', b => b.getAttribute('aria-pressed')) === 'false', '🖍 끄면 눌림 표시가 풀림');
  await select(page, 2, 0, 4); await page.waitForTimeout(300);
  check(await page.$eval('#hlbar', b => b.hidden), '끄면 글자를 선택해도 색 줄이 안 나옴');
  check((await marksText(page)).length === 1, '끄더라도 이미 칠한 표시는 그대로 보임');
  check(await page.evaluate(() => localStorage.getItem('dig.hl')) === '0', '끈 상태를 이 브라우저에 기억');
  await page.click('#hlt'); await page.waitForTimeout(100);
  await page.evaluate(() => getSelection().removeAllRanges());
  await page.click('#main mark.hl'); await page.waitForTimeout(300);
  check(!(await page.$eval('#hlbar', b => b.hidden)) && await page.evaluate(() => getSelection().toString()) === units[1].slice(0, 3), '칠한 글자를 누르면 그 조각이 선택되고 색 줄이 나옴');
  posts.length = 0;
  await page.click('#hlbar [data-c=""]'); await page.waitForTimeout(900);
  check((await marksText(page)).length === 0 && posts[posts.length - 1].marks.length === 0, '🧽 로 지우면 서버에도 빈 목록이 저장됨');
  FORCE409 = true;
  await select(page, 2, 0, 4); await page.waitForTimeout(300);
  await page.click('#hlbar [data-c="y"]'); await page.waitForTimeout(1200);
  check((await marksText(page)).join('|') === 'r:' + units[3].slice(0, 5), '다른 창이 먼저 저장했으면(409) 서버의 최신 표시로 바뀜', (await marksText(page)).join('|'));
  await ctx.close();

  console.log('\n[⑦ 폰 390px · 인쇄용]');
  STORE = []; REV = 0;
  ({ ctx, page } = await open({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true }));
  await select(page, 2, 0, 8); await page.waitForTimeout(300);
  const geo = await page.$eval('#hlbar', b => { const r = b.getBoundingClientRect(); return { hidden: b.hidden, l: r.left, r: r.right, b: r.bottom, vw: innerWidth, vh: innerHeight }; });
  check(!geo.hidden && geo.l >= 0 && geo.r <= geo.vw && geo.b <= geo.vh, '폰에서 색 줄이 화면 안', JSON.stringify(geo));
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '가로 스크롤 없음');
  await page.tap('#hlbar [data-c="y"]'); await page.waitForTimeout(900);
  check((await marksText(page)).length === 1, '폰에서 탭으로도 칠해짐');
  await ctx.close();
  marksGets = 0;
  ({ ctx, page } = await open({}, '/dig?print=1'));
  check(marksGets === 0 && await page.$eval('#hlt', b => b.hidden), '인쇄용(?print=1)은 형광펜 요청 0건·단추 없음');
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
