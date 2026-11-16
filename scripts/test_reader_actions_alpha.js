/**
 * test_reader_actions_alpha.js — 화면 아래 떠 있는 책갈피·불러오기·용어 단추가 뒤의 글을 덜 가리는지 (실제 Chromium) — 2026-11-16 사용자 요청
 *   ① 평소엔 배경이 반투명(알파 0.45~0.8) — 뒤 글이 비친다 · 그림자도 옅다
 *   ② 그래도 단추 글자는 읽힌다: 가장 불리한 경우(뒤가 완전 검정/완전 흰색)에서도 글자 대비 4.5:1 이상 (화이트·다크 둘 다)
 *   ③ 손을 올리면(PC)·누르면 거의 불투명(알파 0.9↑) — 누를 때 또렷
 * 실행: PW_CHROME=<크로미움 경로> node scripts/test_reader_actions_alpha.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-11-16';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/economy/data') return send('application/json', JSON.stringify({ date: D, messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 0, images: [] }));
  res.writeHead(404); res.end();
});
const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); const p = m[1].split(',').map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
const lum = (r, g, b) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const ratio = (c1, c2) => { const a = lum(...c1), b = lum(...c2); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  let pass = true;
  const check = (ok, name, extra) => { console.log((ok ? '  ✔ ' : '  ✘ ') + name + (ok ? '' : '  → ' + (extra || ''))); if (!ok) pass = false; };
  try {
    for (const scheme of ['light', 'dark']) {
      const ctx = await browser.newContext({ viewport: { width: 1000, height: 700 }, colorScheme: scheme });
      const page = await ctx.newPage();
      await page.goto(base + '/economy?date=2026-11-16', { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('#reader-actions', { state: 'attached' });
      await page.evaluate(() => { document.querySelectorAll('.bm-controls,#tn-fab').forEach(e => e.hidden = false); });
      for (const id of ['bm-save', 'bm-go', 'tn-fab']) {
        const s = await page.evaluate((i) => { const e = document.getElementById(i), c = getComputedStyle(e);
          return { bg: c.backgroundColor, fg: c.color, shadow: c.boxShadow, shown: e.getBoundingClientRect().width > 0 }; }, id);
        const bg = parse(s.bg), fg = parse(s.fg);
        check(s.shown, `[${scheme}] ${id} 보임`);
        check(bg.a >= 0.45 && bg.a <= 0.8, `[${scheme}] ${id} ① 평소 배경이 반투명(알파 ${bg.a})`, s.bg);
        const worst = [[0, 0, 0], [255, 255, 255]].map(back => [0, 1, 2].map(i => Math.round([bg.r, bg.g, bg.b][i] * bg.a + back[i] * (1 - bg.a))));
        const minRatio = Math.min(...worst.map(w => ratio([fg.r, fg.g, fg.b], w)));
        check(minRatio >= 4.5, `[${scheme}] ${id} ② 뒤가 검정·흰색이어도 글자 대비 ${minRatio.toFixed(1)}:1`, minRatio);
      }
      await page.hover('#bm-save');
      await page.waitForTimeout(300);
      const hv = parse(await page.evaluate(() => getComputedStyle(document.getElementById('bm-save')).backgroundColor));
      check(hv.a >= 0.9, `[${scheme}] ③ 손을 올리면 거의 불투명(알파 ${hv.a})`, hv.a);
      await ctx.close();
    }
  } finally { await browser.close(); srv.close(); }
  console.log(pass ? 'ALL PASS' : 'SOME FAILED'); process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
