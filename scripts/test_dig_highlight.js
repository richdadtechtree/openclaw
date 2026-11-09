/**
 * test_dig_highlight.js — 경제 공부(디그) 글 형광펜(관리자 전용, 서버 저장) 화면 확인 (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청
 *   ① 관리자가 아니면(403) 단추·도구 줄이 안 나오고 글자 위를 그어도 아무 일 없음
 *   ② 🖍 가 꺼진 기본 상태에선 그어도 칠해지지 않고 평소처럼 글자가 선택됨(복사 가능)
 *   ③ 🖍 를 켜고 글자 위를 마우스로 쭉 그으면 손을 떼는 순간 바로 칠해지고 서버에 저장됨(글자는 하나도 안 바뀜)
 *   ④ 색 바꾸기·겹침(기존 표시가 잘려 나감)·같은 색 합치기·두 문단에 걸친 긋기
 *   ⑤ 🧽 지우개: 칠한 글자 위를 그으면 그 부분만 지워지고, 칠한 조각을 한 번 눌러도 지워짐
 *   ⑥ Ctrl+Z 되돌리기 · Ctrl+Shift+Z / Ctrl+Y 다시 · 도구 줄 ↶ ↷ (기록이 없으면 꺼짐) · 지우기도 되돌릴 수 있음
 *   ⑦ 🗑 모두 지우기(확인창, 되돌릴 수 있음)
 *   ⑧ ✋ 손: 그어도 칠해지지 않고 글자 선택이 되며, 선택해 둔 채 색 단추를 누르면 그 글자에 칠해짐 · 펜일 땐 링크를 안 따라감
 *   ⑨ 새로고침 유지·켠 상태 기억 · 안 맞는 표시 건너뜀 · 다른 창이 먼저 저장(409) · 끄면 Ctrl+Z 도 안 먹음
 *   ⑩ 폰 390px: 도구 줄이 화면 안, 손가락으로 쭉 그어 칠해짐, 펜일 땐 스크롤 막힘(touch-action:none)·✋ 이면 풀림 · 인쇄용 요청 0건
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
  const UNITS = '#main p, #main h2.title, #main h2.sec, #main h3, #main li, #main .cap';
  // 덩어리 u 의 k 번째 글자 위치(화면 좌표). 왼쪽 1/4 지점이면 그 글자 앞, 오른쪽 3/4 지점이면 뒤로 읽힌다.
  const charPt = (page, u, k, frac) => page.evaluate(([UNITS, u, k, frac]) => {
    const el = [...document.querySelectorAll(UNITS)][u];
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let pos = 0, n;
    while ((n = tw.nextNode())) {
      if (k < pos + n.nodeValue.length) {
        const r = document.createRange(); r.setStart(n, k - pos); r.setEnd(n, k - pos + 1);
        const b = r.getBoundingClientRect(); return { x: b.left + b.width * frac, y: b.top + b.height / 2 };
      }
      pos += n.nodeValue.length;
    }
  }, [UNITS, u, k, frac]);
  // 글자 [s,e) 위를 마우스로 쭉 긋는다(u2/e2 가 있으면 u 의 s 부터 u2 의 e2 까지)
  const draw = async (page, u, s, e, u2 = null, e2 = null) => {
    const a = await charPt(page, u, s, 0.25), b = await charPt(page, u2 === null ? u : u2, (u2 === null ? e : e2) - 1, 0.75);
    await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 4 }); await page.mouse.move(b.x, b.y, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(150);
  };
  const select = (page, i, s, e) => page.evaluate(([UNITS, i, s, e]) => {
    const U = [...document.querySelectorAll(UNITS)];
    const at = (u, k) => { const tw = document.createTreeWalker(u, NodeFilter.SHOW_TEXT); let pos = 0, n; while ((n = tw.nextNode())) { if (k <= pos + n.nodeValue.length) return [n, k - pos]; pos += n.nodeValue.length; } };
    const r = document.createRange(); const a = at(U[i], s), b = at(U[i], e);
    r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  }, [UNITS, i, s, e]);
  const marksText = page => page.$$eval('#main mark.hl', ms => ms.map(m => m.className.replace('hl hl-', '') + ':' + m.textContent));
  const bodyText = page => page.$eval('#main', m => m.textContent);
  const lastMarks = u => (posts[posts.length - 1] || { marks: [] }).marks.filter(m => m.u === u).sort((a, b) => a.s - b.s).map(m => [m.c, m.s, m.e]);
  const settle = page => page.waitForTimeout(800);
  const pressed = (page, t) => page.$eval(`#hlbar [data-t="${t}"]`, b => b.getAttribute('aria-pressed'));

  console.log('\n[① 관리자가 아니면]');
  ADMIN = false; STORE = []; REV = 0; posts = [];
  let { ctx, page } = await open();
  check(await page.$eval('#hlt', b => b.hidden) && await page.$eval('#hlbar', b => b.hidden), '🖍 단추도 도구 줄도 안 보임(서버 403)');
  await draw(page, 1, 0, 6); await settle(page);
  check((await marksText(page)).length === 0 && posts.length === 0, '글자 위를 그어도 아무 일 없음(칠하기·저장 요청 0건)');
  await ctx.close();

  ADMIN = true; STORE = []; REV = 0; posts = [];
  console.log('\n[② 꺼진 기본 상태: 평소처럼 글자 선택]');
  ({ ctx, page } = await open());
  const units = await page.$$eval(UNITS, us => us.map(u => u.textContent));
  const before = await bodyText(page);
  check(units.length === 6, '글 덩어리 6개(구역 제목·큰 제목·문단 2·요약 줄 2)', String(units.length));
  check(!(await page.$eval('#hlt', b => b.hidden)) && await page.$eval('#hlbar', b => b.hidden), '관리자: 🖍 단추는 보이고 도구 줄은 꺼져 있음(실수로 칠하지 않게 기본은 꺼짐)');
  await draw(page, 1, 0, 6);
  check((await marksText(page)).length === 0 && posts.length === 0, '꺼진 상태에서 그으면 칠해지지 않음');
  check(await page.evaluate(() => getSelection().toString()) === units[1].slice(0, 6), '대신 평소처럼 글자가 선택됨(복사 가능)', await page.evaluate(() => getSelection().toString()));
  await page.evaluate(() => getSelection().removeAllRanges());

  console.log('\n[③ 🖍 켜고 쭉 그으면 바로 칠해짐]');
  await page.click('#hlt'); await page.waitForTimeout(200);
  check(!(await page.$eval('#hlbar', b => b.hidden)) && await pressed(page, 'y') === 'true', '🖍 를 켜면 도구 줄이 나오고 노랑 펜이 골라져 있음');
  check(await page.$eval('#main', m => getComputedStyle(m).touchAction) === 'none', '펜일 땐 글 위에서 끌어도 스크롤되지 않음(touch-action:none)');
  await draw(page, 1, 0, 6); await settle(page);
  check((await marksText(page)).join('|') === 'y:' + units[1].slice(0, 6), '제목 앞 "파랗게 물든" 위를 쭉 그으니 손을 떼자 바로 노랑으로 칠해짐', (await marksText(page)).join('|'));
  check(posts.length === 1 && posts[0].id === '2026-11-09' && posts[0].revision === 0, '서버에 저장 요청 1번(호 번호·버전 0)');
  const m0 = posts[0].marks[0];
  check(posts[0].marks.length === 1 && m0.u === 1 && m0.s === 0 && m0.e === 6 && m0.c === 'y' && m0.q === units[1].slice(0, 6), '저장 내용 = 덩어리 1 · 0~6 · 노랑 · 앞부분 글', JSON.stringify(m0));
  check(await bodyText(page) === before, '글자는 하나도 안 바뀜(감싸기만)');
  check(await page.evaluate(() => getSelection().isCollapsed), '칠한 뒤 선택이 풀림');
  // 굵은 글·링크가 섞인 문단
  const p2 = units[2], s0 = p2.indexOf('블루'), e0 = p2.indexOf('자세히') + 3;
  await page.click('#hlbar [data-t="r"]'); await page.waitForTimeout(100);
  check(await pressed(page, 'r') === 'true' && await pressed(page, 'y') === 'false', '빨강 펜으로 바꿈');
  await draw(page, 2, s0, e0); await settle(page);
  const red = (await marksText(page)).filter(x => x.startsWith('r:')).map(x => x.slice(2)).join('');
  check(red === p2.slice(s0, e0), '굵은 글·링크 경계를 넘어 그어도 칠한 글자를 이으면 정확히 그은 글자', red);
  check(await bodyText(page) === before, '여전히 글자는 하나도 안 바뀜');

  console.log('\n[④ 두 문단에 걸침·겹침·합치기]');
  await page.click('#hlbar [data-t="b"]');
  await draw(page, 2, p2.length - 6, 0, 3, 5); await settle(page);                       // 문단2 끝 6글자 ~ 문단3 앞 5글자
  const blue = posts[posts.length - 1].marks.filter(m => m.c === 'b').sort((a, b) => a.u - b.u);
  check(blue.length === 2 && blue[0].u === 2 && blue[1].u === 3 && blue[0].e === p2.length && blue[1].s === 0 && blue[1].e === 5, '두 문단에 걸쳐 그으면 문단마다 한 조각씩(파랑 2조각)', JSON.stringify(blue.map(m => [m.u, m.s, m.e])));
  await page.click('#hlbar [data-t="y"]');
  await draw(page, 3, 0, 2); await settle(page);
  check(JSON.stringify(lastMarks(3)) === JSON.stringify([['y', 0, 2], ['b', 2, 5]]), '겹쳐 칠하면 기존 표시가 잘려 나감(노랑 0~2 + 파랑 2~5)', JSON.stringify(lastMarks(3)));
  await draw(page, 3, 2, 3); await settle(page);
  check(JSON.stringify(lastMarks(3)) === JSON.stringify([['y', 0, 3], ['b', 3, 5]]), '같은 색이 맞닿으면 하나로 합쳐짐(노랑 0~3 한 조각)', JSON.stringify(lastMarks(3)));
  check(await bodyText(page) === before, '글자는 끝까지 그대로');
  await ctx.close();

  console.log('\n[⑤ 🧽 지우개]');
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open());
  await page.click('#hlt'); await draw(page, 1, 0, 6); await settle(page);
  await page.click('#hlbar [data-t="e"]'); await page.waitForTimeout(100);
  check(await pressed(page, 'e') === 'true', '🧽 지우개를 고름');
  await draw(page, 1, 2, 5); await settle(page);                                      // "게 물" 위를 긋기(공백이 끼어도 지워짐)
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 2], ['y', 5, 6]]), '칠한 글자 위를 그으면 그 부분만 지워져 양끝이 남음(2~5 삭제)', JSON.stringify(lastMarks(1)));
  const n0 = posts.length;
  await draw(page, 2, 0, 5); await settle(page);
  check(posts.length === n0, '칠하지 않은 글자 위를 그어도 아무 변화·저장 없음');
  const pt = await page.evaluate(() => { const m = document.querySelectorAll('#main mark.hl')[1].getBoundingClientRect(); return { x: m.left + m.width / 2, y: m.top + m.height / 2 }; });
  await page.mouse.click(pt.x, pt.y); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 2]]) && (await marksText(page)).length === 1, '지우개로 칠한 조각을 한 번 누르면 그 조각이 지워짐', JSON.stringify(lastMarks(1)));
  check(await bodyText(page) === before, '글자는 그대로');

  console.log('\n[⑥ 되돌리기·다시 하기]');
  const undoBtn = '#hlbar [data-a="undo"]', redoBtn = '#hlbar [data-a="redo"]';
  check(!(await page.$eval(undoBtn, b => b.disabled)) && await page.$eval(redoBtn, b => b.disabled), '기록이 있으면 ↶ 켜짐, 다시할 게 없으면 ↷ 꺼짐');
  await page.keyboard.press('Control+z'); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 2], ['y', 5, 6]]), 'Ctrl+Z: 방금 지운 조각이 되살아남(서버에도 저장)', JSON.stringify(lastMarks(1)));
  await page.keyboard.press('Control+z'); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 6]]), 'Ctrl+Z 한 번 더: 지우개 긋기도 되돌려 처음 칠한 상태', JSON.stringify(lastMarks(1)));
  await page.keyboard.press('Control+z'); await settle(page);
  check((await marksText(page)).length === 0 && await page.$eval(undoBtn, b => b.disabled), '처음 칠한 것까지 되돌리면 표시 없음 · ↶ 꺼짐');
  await page.keyboard.press('Control+Shift+z'); await settle(page);
  check((await marksText(page)).join('|') === 'y:' + units[1].slice(0, 6), 'Ctrl+Shift+Z: 다시 하기');
  await page.keyboard.press('Control+y'); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 2], ['y', 5, 6]]), 'Ctrl+Y 도 다시 하기', JSON.stringify(lastMarks(1)));
  await page.click(undoBtn); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 6]]), '도구 줄 ↶ 단추도 되돌리기');
  await page.click(redoBtn); await settle(page);
  check(JSON.stringify(lastMarks(1)) === JSON.stringify([['y', 0, 2], ['y', 5, 6]]), '도구 줄 ↷ 단추도 다시 하기');
  await page.click('#hlbar [data-t="y"]');
  await draw(page, 1, 8, 10); await settle(page);
  check(await page.$eval(redoBtn, b => b.disabled), '새로 칠하면 다시 하기 기록은 비워짐(↷ 꺼짐)');
  check(await bodyText(page) === before, '되돌리고 다시 해도 글자는 그대로');

  console.log('\n[⑦ 🗑 모두 지우기]');
  const cnt = (await marksText(page)).length;
  page.once('dialog', d => d.dismiss());
  await page.click('#hlbar [data-a="clear"]'); await settle(page);
  check((await marksText(page)).length === cnt, '확인창에서 취소하면 그대로');
  page.once('dialog', d => { check(/모두 지울까요/.test(d.message()), '확인창이 뜸', d.message().split('\n')[0]); d.accept(); });
  await page.click('#hlbar [data-a="clear"]'); await settle(page);
  check((await marksText(page)).length === 0 && (posts[posts.length - 1].marks.length === 0), '확인하면 이 호의 형광펜이 모두 지워지고 서버에도 반영');
  await page.keyboard.press('Control+z'); await settle(page);
  check((await marksText(page)).length === cnt, '모두 지운 것도 Ctrl+Z 로 되살릴 수 있음');
  await ctx.close();

  console.log('\n[⑧ ✋ 손 · 펜일 땐 링크를 안 따라감]');
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open());
  await page.click('#hlt'); await page.click('#hlbar [data-t="h"]'); await page.waitForTimeout(100);
  check(await page.$eval('#main', m => getComputedStyle(m).touchAction) !== 'none', '✋ 이면 스크롤이 풀림(touch-action 이 none 이 아님)');
  await draw(page, 1, 0, 6); await settle(page);
  check((await marksText(page)).length === 0 && await page.evaluate(() => getSelection().toString()) === units[1].slice(0, 6), '✋ 에선 그어도 칠해지지 않고 글자가 선택됨');
  await page.click('#hlbar [data-t="b"]'); await settle(page);
  check((await marksText(page)).join('|') === 'b:' + units[1].slice(0, 6) && await pressed(page, 'b') === 'true', '선택해 둔 채 파랑을 누르면 그 글자에 칠해지고 펜이 파랑으로 바뀜', (await marksText(page)).join('|'));
  // 링크: 펜(파랑)일 땐 안 따라가고, ✋ 일 땐 따라감
  const pg = () => ctx.waitForEvent('page', { timeout: 1200 }).then(() => true, () => false);
  let w = pg(); await page.click('#main p a'); check(!(await w), '펜일 땐 링크를 눌러도 따라가지 않음');
  await page.click('#hlbar [data-t="h"]');
  w = pg(); await page.click('#main p a'); check(await w, '✋ 일 땐 링크가 평소처럼 열림');
  await ctx.close();

  console.log('\n[⑨ 새로고침 유지 · 켠 상태 기억 · 안 맞는 표시 · 409 · 끄면 Ctrl+Z 무효]');
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open());
  await page.click('#hlt'); await draw(page, 1, 0, 6); await settle(page);
  await page.reload(); await page.waitForSelector('#main mark.hl'); await page.waitForTimeout(300);
  check((await marksText(page)).join('|') === 'y:' + units[1].slice(0, 6), '새로고침해도 서버에 저장된 표시가 다시 칠해짐');
  check(!(await page.$eval('#hlbar', b => b.hidden)) && await pressed(page, 'y') === 'true', '켜 둔 상태·고른 도구를 이 브라우저가 기억');
  check(await page.$eval(undoBtn, b => b.disabled), '새로고침하면 되돌리기 기록은 비움(↶ 꺼짐)');
  await page.click('#hlt'); await page.waitForTimeout(100);
  check(await page.$eval('#hlbar', b => b.hidden) && (await marksText(page)).length === 1, '끄면 도구 줄은 사라지고 칠한 표시는 그대로 보임');
  await draw(page, 1, 8, 10); await settle(page);
  const np = posts.length;
  await page.keyboard.press('Control+z'); await settle(page);
  check(posts.length === np && (await marksText(page)).length === 1, '꺼진 동안엔 Ctrl+Z 도 안 먹음(브라우저 기본 동작만)');
  await ctx.close();
  STORE = [{ u: 1, s: 0, e: 3, c: 'y', q: '틀린글' }, { u: 1, s: 0, e: 3, c: 'r', q: units[1].slice(0, 3) }, { u: 99, s: 0, e: 3, c: 'b', q: 'x' }];
  ({ ctx, page } = await open());
  check((await marksText(page)).join('|') === 'r:' + units[1].slice(0, 3), '글이 안 맞거나 없는 덩어리의 표시는 건너뛰고 맞는 것만 칠함');
  await ctx.close();
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open());
  await page.click('#hlt'); FORCE409 = true;
  await draw(page, 2, 0, 4); await page.waitForTimeout(1300);
  check((await marksText(page)).join('|') === 'r:' + units[3].slice(0, 5), '다른 창이 먼저 저장했으면(409) 서버의 최신 표시로 바뀜', (await marksText(page)).join('|'));
  check(await page.$eval(undoBtn, b => b.disabled), '그때는 되돌리기 기록도 비움(남의 변경을 되돌리지 않게)');
  await ctx.close();

  console.log('\n[⑩ 폰 390px · 인쇄용]');
  STORE = []; REV = 0; posts.length = 0;
  ({ ctx, page } = await open({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true }));
  await page.tap('#hlt'); await page.waitForTimeout(200);
  const geo = await page.$eval('#hlbar', b => { const r = b.getBoundingClientRect(); return { hidden: b.hidden, l: r.left, r: r.right, b: r.bottom, vw: innerWidth, vh: innerHeight }; });
  check(!geo.hidden && geo.l >= 0 && geo.r <= geo.vw && geo.b <= geo.vh, '폰에서 도구 줄이 화면 안', JSON.stringify(geo));
  check((await page.$eval('#hlbar', b => b.getBoundingClientRect().height)) < 64, '폰에서도 도구 줄이 한 줄(두 줄로 접혀 글을 가리지 않음)');
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '가로 스크롤 없음');
  check(await page.$eval('#main', m => getComputedStyle(m).touchAction) === 'none', '펜일 땐 손가락으로 끌어도 화면이 스크롤되지 않음');
  const cdp = await ctx.newCDPSession(page);                                       // 진짜 손가락 터치로 긋기
  const a = await charPt(page, 2, 0, 0.25), b = await charPt(page, 2, 11, 0.75);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: a.x, y: a.y }] });
  for (let i = 1; i <= 6; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: a.x + (b.x - a.x) * i / 6, y: a.y + (b.y - a.y) * i / 6 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await settle(page);
  check((await marksText(page)).join('') === 'y:' + units[2].slice(0, 12), '손가락으로 쭉 그으면 칠해짐', (await marksText(page)).join('|'));
  await page.tap('#hlbar [data-t="h"]');
  check(await page.$eval('#main', m => getComputedStyle(m).touchAction) !== 'none', '✋ 를 고르면 다시 스크롤할 수 있음');
  await ctx.close();
  marksGets = 0;
  ({ ctx, page } = await open({}, '/dig?print=1'));
  check(marksGets === 0 && await page.$eval('#hlt', b => b.hidden) && await page.$eval('#hlbar', b => b.hidden), '인쇄용(?print=1)은 형광펜 요청 0건·단추·도구 줄 없음');
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
