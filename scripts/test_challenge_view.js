// 🔥 챌린지 화면 검사(실제 Chromium, 개발 환경 전용).
// scripts/challenge_demo_server.py 로 가짜 서버(가짜 신문·기수·사용자)를 띄워
// PC(1280px)·폰(390px)에서: 진행도 달력 · 사진 바둑판 · 글쓰기 창 · 저장 · 같은 기수 글 잠금/열림 · 완수 축하 팝업 을 확인한다.
// 실행: node scripts/test_challenge_view.js   (스크린샷: SHOT_DIR 환경변수 폴더에 저장, 없으면 안 찍음)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PORT = 8765 + Math.floor(Math.random() * 500);
const BASE = `http://localhost:${PORT}`;   // ⚠️ 숫자 IP 로 열면 "IP 접속 = 관리자 비밀번호 전용" 규칙에 걸린다
const CK = path.join(os.tmpdir(), `chcookies_${PORT}.json`);
const CHROME = process.env.PW_CHROME || undefined;
const SHOT = process.env.SHOT_DIR || '';
let pass = true;
const check = (ok, msg) => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function waitUp() {
  for (let i = 0; i < 60; i++) { try { const r = await fetch(BASE + '/privacy'); if (r.ok) return; } catch (e) {} await sleep(250); }
  throw new Error('demo server did not start');
}
const TEXT = { what: '반도체 수출이 석 달 연속 늘었다는 기사', why: 'AI 서버 수요가 메모리 가격을 끌어올렸기 때문', how: '내년 상반기까지 증가세가 이어질 전망', think: '반도체 ETF 비중을 조금 늘리고 분기 실적을 확인하겠다' };

(async () => {
  const srv = spawn('python3', [path.join(__dirname, 'challenge_demo_server.py'), '--port', String(PORT), '--cookies', CK, '--today', '2026-11-04'], { stdio: ['ignore', 'inherit', 'inherit'] });
  try {
    await waitUp();
    const cookies = JSON.parse(fs.readFileSync(CK, 'utf8'));
    const browser = await chromium.launch(CHROME ? { executablePath: CHROME } : {});
    const ctxFor = async (who, w, h) => {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 500, hasTouch: w < 500 });
      await ctx.addCookies([{ name: 'gate_sess', value: cookies[who], url: BASE }]);
      return ctx;
    };
    const errors = [];

    for (const [label, w, h] of [['PC', 1280, 900], ['폰', 390, 844]]) {
      console.log(`[${label} ${w}px]`);
      // B: 아직 오늘 글 없음 → 잠금
      let ctx = await ctxFor('b', w, h);
      let pg = await ctx.newPage();
      pg.on('pageerror', e => errors.push(e.message));
      await pg.goto(BASE + '/challenge');
      await pg.waitForSelector('.tile');
      const tabs = await pg.$$eval('.sitenav a[href]', as => as.map(a => a.getAttribute('href')));
      check(tabs.includes('/dig') && tabs.includes('/challenge') && !tabs.includes('/economy'), '찰스 탭은 디그·챌린지만');
      check(await pg.$$eval('.tile', t => t.length) === 12, '오늘 신문 사진 12장');
      check(await pg.$eval('.day.today', e => !!e), '달력에 오늘(⭕)');
      check(await pg.$eval('.day.missed', e => !!e), '빠진 날(✗) 표시');
      const lockTxt = await pg.$eval('#posts', e => e.textContent);
      check(lockTxt.includes('내 글을 저장하면'), '내 글 쓰기 전엔 같은 기수 글 잠김');
      const noHScroll = await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
      check(noHScroll, '가로 스크롤 없음');
      if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_${w}_list.png`), fullPage: true });

      // 글쓰기 창
      await pg.click('.tile >> nth=2');
      await pg.waitForSelector('#ed.open');
      check(await pg.$eval('#ed-photo', i => i.src.includes('/api/challenge/photo')), '사진을 누르면 큰 사진 + 입력칸');
      check(await pg.$$eval('#ed-form textarea', t => t.length) === 4, '입력칸 4개(WHAT·WHY·HOW·생각)');
      // 🖼 사진 뷰어: 휠 확대 · 끌어 옮기기 · 🖍 줄 긋기 · 되돌리기 (경제 화면 뷰어와 같은 사용법)
      await pg.waitForFunction(() => document.querySelector('#ed-photo').naturalWidth > 0);
      await sleep(200);
      const st = () => pg.evaluate(() => window.__PV.state());
      const box = await pg.$eval('#pv-stage', e => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
      check(box.w > 100 && box.h > 100, '사진 칸이 보임 (' + Math.round(box.w) + '×' + Math.round(box.h) + ')');
      check(await pg.evaluate(() => document.querySelector('.pv-bar').scrollWidth <= document.querySelector('.pv-bar').clientWidth + 1), '사진 도구줄이 칸 안에 들어감');
      if (w >= 500) {
        const cx = box.x + box.w / 2, cy = box.y + box.h / 3;
        await pg.mouse.move(cx, cy);
        await pg.mouse.wheel(0, -300);
        await sleep(100);
        const z1 = await st();
        check(z1.s > 1.3, '마우스 휠 → 확대 (' + z1.s.toFixed(2) + '배)');
        await pg.mouse.down(); await pg.mouse.move(cx + 120, cy + 80, { steps: 5 }); await pg.mouse.up();
        const z2 = await st();
        check(z2.tx !== z1.tx || z2.ty !== z1.ty, '✋ 손바닥(기본): 끌어서 옮기기');
        await pg.mouse.move(cx, cy); await pg.mouse.down({ button: 'right' }); await pg.mouse.move(cx - 80, cy - 60, { steps: 4 }); await pg.mouse.up({ button: 'right' });
        check((await st()).tx !== z2.tx, '오른쪽 버튼으로도 옮기기(우클릭 메뉴 없이)');
        await pg.click('#pv-pen');
        check(await pg.$eval('#pv-pentools', e => !e.hidden) && !(await st()).hand, '🖍 켜면 도구(직선·동그라미·자유·색·굵기) 나오고 손바닥 꺼짐');
        await pg.mouse.move(cx - 100, cy); await pg.mouse.down(); await pg.mouse.move(cx + 100, cy + 4, { steps: 6 }); await pg.mouse.up();
        check((await st()).marks === 1 && await pg.$$eval('#pv-svg polyline', l => l.length) === 1, '직선 긋기 → 줄 1개');
        const ys = await pg.$eval('#pv-svg polyline', l => l.getAttribute('points').split(' ').map(p => +p.split(',')[1]));
        check(Math.abs(ys[0] - ys[1]) < 0.01, '수평 근처 직선은 반듯하게');
        await pg.click('#pv-t-oval');
        await pg.mouse.move(cx - 60, cy + 40); await pg.mouse.down(); await pg.mouse.move(cx + 60, cy + 100, { steps: 5 }); await pg.mouse.up();
        check(await pg.$$eval('#pv-svg ellipse', l => l.length) === 1, '동그라미 그리기');
        await pg.click('#pv-undo');
        check((await st()).marks === 1, '↶ 되돌리기');
        await pg.click('#ed-close');
        await pg.click('.tile >> nth=2');
        await pg.waitForSelector('#ed.open');
        await sleep(200);
        check((await st()).marks === 1, '창을 닫았다 다시 열어도 그 장의 줄은 남음(새로고침 전까지)');
        await pg.click('#pv-pen');           // 원래대로(손바닥)
      }
      await pg.fill('#f-what', '짧음');
      await pg.click('#ed-save');
      check((await pg.textContent('#ed-st')).includes('자 이상'), '짧으면 저장 안 하고 안내');
      for (const k of Object.keys(TEXT)) await pg.fill('#f-' + k, TEXT[k]);
      // 📖 모르는 용어: HOW 와 생각 사이 · Enter 로 추가 · 🔍 뜻 찾기 → AI 풀이 카드
      const order = await pg.$$eval('#ed-form .fld', fs => fs.map(f => f.querySelector('label').textContent.trim().split(/\s+/)[0]));
      check(order.slice(0, 5).join('|') === 'WHAT|WHY|HOW|📖|생각', '모르는 용어 칸은 HOW 와 생각 사이 (' + order.join('|') + ')');
      await pg.fill('#t-in', '기준금리');
      await pg.press('#t-in', 'Enter');
      await pg.fill('#t-in', 'PER, 기준 금리');
      await pg.click('#t-add');
      check(await pg.$$eval('#t-list .tcard', c => c.length) === 2, '용어 추가(같은 말은 한 번만)');
      await pg.click('#t-find');
      await pg.waitForFunction(() => document.querySelectorAll('#t-list .tcard:not(.wait)').length === 2);
      const card = await pg.textContent('#t-list .tcard');
      check(card.includes('시험용 한 줄 뜻') && card.includes('AI 풀이') && !card.includes('사전'), '🔍 뜻 찾기 → AI 풀이(사전 링크 없음)');
      check(!(await pg.content()).includes('terms.naver.com'), '화면 어디에도 사전 링크 없음');
      if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_${w}_terms.png`) });
      await pg.reload();                       // 새로고침해도 쓰던 글이 남는지
      await pg.waitForSelector('.tile');
      await pg.click('.tile >> nth=2');
      await pg.waitForSelector('#ed.open');
      check((await pg.inputValue('#f-what')) === TEXT.what, '새로고침해도 쓰던 글이 남음(임시 보관)');
      check(await pg.$$eval('#t-list .tcard', c => c.length) === 2, '새로고침해도 고른 용어가 남음');
      if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_${w}_editor.png`) });
      await pg.click('#ed-save');
      await pg.waitForFunction(() => (document.querySelector('#ed-st') || {}).textContent?.includes('저장했어요'));
      check(true, '저장됨');
      await pg.click('#ed-close');
      check(await pg.$eval('.tile >> nth=2', t => t.classList.contains('has')), '내가 쓴 사진에 ✅ 표시');
      const unlocked = await pg.$eval('#posts', e => e.textContent);
      check(!unlocked.includes('내 글을 저장하면') && (unlocked.includes('찰스에이') || unlocked.includes('아직 다른 찰스')), '저장 뒤 같은 기수 글이 열림');
      const mineSaved = await pg.evaluate(async () => (await (await fetch('/api/challenge/day')).json()).mine['03.jpg'].terms);
      check(JSON.stringify(mineSaved) === JSON.stringify(['기준금리', 'PER']), '저장한 글에 용어 2개');
      // 📖 우리 기수 용어장
      await pg.click('#v-gloss');
      await pg.waitForSelector('.gcard');
      const gc = await pg.$$eval('.gcard', c => c.map(x => x.textContent));
      check(gc.length === 2 && gc.some(t => t.includes('기준금리') && t.includes('시험용 한 줄 뜻') && t.includes('내 용어')), '용어장: 내가 찾은 용어 2개 + 풀이');
      check(await pg.$eval('#daycard', e => e.hidden), '용어장을 열면 신문 칸은 숨김');
      await pg.fill('#g-q', 'per');
      check(await pg.$$eval('.gcard', c => c.length) === 1, '용어장 찾기(대소문자 무시)');
      check(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), '용어장 가로 스크롤 없음');
      if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_${w}_gloss.png`), fullPage: true });
      await pg.fill('#g-q', '');
      await pg.click('.gcard button[data-day]');
      await pg.waitForSelector('#daycard:not([hidden]) .tile');
      check(true, '용어장 → "글 보기"로 그날 신문으로');
      check(await pg.$('.day.today') === null && await pg.$eval('.day.sel', e => e.classList.contains('done')), '오늘 칸이 ⭕ → ✅ 완료로');
      if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_${w}_after.png`), fullPage: true });
      // 이번 회차의 B 글 지우기(다음 화면 크기 검사를 같은 조건으로)
      await pg.evaluate(async () => { await fetch('/api/challenge/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date: '2026-11-04', page: '03.jpg' }) }); });
      await ctx.close();
    }

    console.log('[관리자]');
    let ctx = await ctxFor('admin', 1280, 900);
    let pg = await ctx.newPage();
    await pg.goto(BASE + '/challenge');
    await pg.waitForSelector('.tile');
    check(await pg.$('#cohortsel') !== null, '관리자는 기수 고르기');
    const at = await pg.$$eval('.sitenav a[href]', as => as.map(a => a.getAttribute('href')));
    check(['/economy', '/dig', '/ai', '/challenge'].every(x => at.includes(x)), '관리자 탭 4개(챌린지 포함)');
    await pg.goto(BASE + '/gate/admin');
    check((await pg.content()).includes('찰스 기수'), '관리 화면에 기수 관리 칸');
    if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_admin.png`), fullPage: true });
    await ctx.close();

    console.log('[완수 축하]');
    // A: 월·화 썼음 → 수·목·금 쓰면 완수
    ctx = await ctxFor('a', 390, 844);
    pg = await ctx.newPage();
    for (const d of ['2026-11-04', '2026-11-05', '2026-11-06']) {
      await pg.request.post(BASE + '/__today?d=' + d);
      await pg.goto(BASE + '/challenge');
      await pg.waitForSelector('.tile');
      await pg.click('.tile >> nth=0');
      await pg.waitForSelector('#ed.open');
      for (const k of Object.keys(TEXT)) await pg.fill('#f-' + k, TEXT[k]);
      await pg.click('#ed-save');
      await pg.waitForFunction(() => (document.querySelector('#ed-st') || {}).textContent?.includes('저장했어요'));
    }
    await pg.waitForSelector('#cele.open', { timeout: 4000 });
    check((await pg.textContent('#cele-text')).includes('꾸준함은 인생을 바꿀 수 있습니다'), '마지막 날 저장 → 축하 팝업 "꾸준함은 인생을 바꿀 수 있습니다"');
    if (SHOT) await pg.screenshot({ path: path.join(SHOT, `ch_celebrate.png`) });
    await pg.click('#cele-go');
    await pg.waitForURL(BASE + '/economy');
    check(true, '완수 후 신문 요약 화면이 열림(무기한 일반 권한)');
    await pg.goto(BASE + '/challenge');
    await pg.waitForSelector('.tile');
    await sleep(600);
    check(!(await pg.$eval('#cele', e => e.classList.contains('open'))), '축하 팝업은 한 번만');
    await ctx.close();

    check(errors.length === 0, '화면 스크립트 오류 없음' + (errors.length ? ': ' + errors.join(' | ') : ''));
    await browser.close();
  } finally {
    srv.kill();
    try { fs.unlinkSync(CK); } catch (e) {}
  }
  console.log(pass ? '\n결과: 전부 통과' : '\n결과: 실패 있음');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
