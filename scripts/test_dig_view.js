// 경제 공부(디그) 화면 검사 (실제 Chromium): 화이트/다크/자동 테마 + ⤓ PDF 받기.
// 개발 환경 전용. 서버(app.py)를 먼저 띄워 두고 주소를 넘긴다:
//   DIG_URL=http://127.0.0.1:8000 node scripts/test_dig_view.js     (npm i playwright 필요)
// 캐시(~/.openclaw/dig_cache)에 호가 1개 이상 있어야 한다.
const { chromium } = require('playwright');
const BASE = process.env.DIG_URL || 'http://127.0.0.1:8000';
const LIGHT = 'rgb(246, 247, 249)', DARK = 'rgb(18, 21, 27)';
let fails = 0;
const ok = (n, c) => { console.log((c ? '  OK  ' : ' FAIL ') + n); if (!c) fails++; };

(async () => {
  const launch = { executablePath: process.env.CHROMIUM_PATH || undefined };
  const b = await chromium.launch(launch).catch(() => chromium.launch());
  const bg = p => p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const open = async ctx => { const p = await ctx.newPage(); await p.goto(BASE + '/dig'); await p.waitForSelector('.card'); return p; };

  for (const os of ['light', 'dark']) {
    console.log('[테마 · 기기 설정=' + os + ']');
    const ctx = await b.newContext({ colorScheme: os, viewport: { width: 800, height: 700 } });
    const p = await open(ctx);
    ok('처음엔 자동 = 기기 설정을 따름', (await bg(p)) === (os === 'dark' ? DARK : LIGHT) && (await p.textContent('#th')).includes('자동'));
    await p.click('#th'); ok('1번 누르면 화이트', (await bg(p)) === LIGHT && (await p.textContent('#th')).includes('화이트'));
    await p.click('#th'); ok('2번 누르면 다크', (await bg(p)) === DARK && (await p.textContent('#th')).includes('다크'));
    await p.reload(); await p.waitForSelector('.card'); ok('새로고침해도 유지', (await bg(p)) === DARK);
    await p.click('#th'); ok('3번 누르면 다시 자동', (await bg(p)) === (os === 'dark' ? DARK : LIGHT));
    await p.setViewportSize({ width: 390, height: 800 });
    ok('폰 폭(390px)에서 가로 넘침 없음', !(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth)));
    await ctx.close();
  }

  console.log('[PDF 받기]');
  {
    const ctx = await b.newContext({ colorScheme: 'dark', acceptDownloads: true });
    const p = await open(ctx);
    await p.click('#th'); await p.click('#th');                     // 다크로 고정(PDF 는 그래도 흰 종이여야 함)
    const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 60000 }), p.click('#pdf')]);
    const file = await dl.path(); const fs = require('fs'); const buf = fs.readFileSync(file);
    ok('파일 이름이 dig_날짜.pdf', /^dig_\d{4}-\d{2}-\d{2}\.pdf$/.test(dl.suggestedFilename()));
    ok('진짜 PDF 파일(%PDF)', buf.slice(0, 4).toString() === '%PDF' && buf.length > 5000);
    ok('받은 뒤 버튼이 원래대로', (await p.textContent('#pdf')).includes('PDF') && !(await p.isDisabled('#pdf')));
    ok('PDF 만들 때 고른 테마를 건드리지 않음', (await p.evaluate(() => localStorage.getItem('dig.theme'))) === 'dark');
    await ctx.close();
  }
  {
    const ctx = await b.newContext({ acceptDownloads: true });
    const p = await open(ctx);
    await p.route('**/api/dig/pdf**', r => r.fulfill({ status: 500, contentType: 'application/json', body: '{"ok":false,"reason":"테스트 실패"}' }));
    await p.evaluate(() => { window.__printed = 0; window.print = () => { window.__printed++; }; });
    p.on('dialog', d => d.accept());                                  // "인쇄창을 열까요?" → 예
    await p.click('#pdf'); await p.waitForFunction(() => window.__printed > 0, null, { timeout: 5000 });
    ok('서버 PDF 실패 시 브라우저 인쇄창으로 대신함', true);
    ok('실패 후 버튼 복구', !(await p.isDisabled('#pdf')));
    await ctx.close();
  }
  {
    console.log('[인쇄 모양(Ctrl+P)]');
    const ctx = await b.newContext({ colorScheme: 'dark' });
    const p = await open(ctx); await p.click('#th'); await p.click('#th');   // 다크
    await p.emulateMedia({ media: 'print' });
    ok('인쇄할 땐 도구줄 숨김', (await p.evaluate(() => getComputedStyle(document.querySelector('.top')).display)) === 'none');
    ok('인쇄할 땐 다크여도 흰 바탕', (await bg(p)) === 'rgb(255, 255, 255)');
    await ctx.close();
  }
  await b.close();
  console.log(fails ? ('\n실패 ' + fails + '개') : '\n전부 통과');
  process.exit(fails ? 1 : 0);
})();
