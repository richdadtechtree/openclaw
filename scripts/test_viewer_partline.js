/**
 * test_viewer_partline.js — 신문 요약 글 맨 위의 분할 표시("1/7") 숨김 확인 (실제 Chromium) — 2026-11-16 사용자 요청
 *
 *   슬랙에서 요약을 7개로 나눠 보낼 때 첫 줄이 "1/7" 만 덩그러니 와서 카드 맨 위에 그대로 보였다.
 *   ① 첫 줄 전체가 "1/7"(괄호·볼드 포함)이면 카드에 안 보인다 — 머리말·기사는 그대로
 *   ② 예전 모양 "[신문요약 2/7]" 도 계속 숨김
 *   ③ 본문 속 "3/4분기"·"1/7 규모" 같은 숫자는 건드리지 않는다
 * 실행: PW_CHROME=<크로미움 경로> node scripts/test_viewer_partline.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const art = (n, t, w) => [`${n}. ${t}`, `• WHAT: ${w}`, '• WHY: 이유를 설명함.', '• HOW: 방법을 설명함.', `• 사진: 0${n}`].join('\n');
const M1 = ['1/7', '2026년 11월 16일 신문 브리핑', '원본 PDF', art(1, '반도체 호황…용인 기흥·수원 영통구 집값 상승', '용인 기흥구의 주간 아파트값 상승률이 전국에서 가장 높았음.')].join('\n');
const M2 = ['**(2/7)**', '2026년 11월 16일 신문 브리핑', art(2, '서울 전세 불안 지속', '서울 전세가격이 계속 올랐음.')].join('\n');
const M3 = ['[신문요약 3/7]', '2026년 11월 16일 신문 브리핑', art(3, '금리 동결 전망', '3/4분기 성장률은 1/7 수준으로 둔화됐다고 설명함.')].join('\n');

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-11-16';
  const send = (t, b, code = 200) => { res.writeHead(code, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack' || u === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data' || u === '/economy/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: D + 'T06:29:00', source: 'user', kind: 'text', text: M1 },
    { ts: D + 'T06:30:00', source: 'user', kind: 'text', text: M2 },
    { ts: D + 'T06:31:00', source: 'user', kind: 'text', text: M3 }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 0, images: [] }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  let pass = true;
  const check = (ok, name, extra) => { console.log((ok ? '  ✔ ' : '  ✘ ') + name + (ok ? '' : '  → ' + (extra || ''))); if (!ok) pass = false; };
  try {
    const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
    await page.goto(base + '/economy?date=2026-11-16', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.brf-art', { timeout: 15000 });
    const cards = await page.evaluate(() => [...document.querySelectorAll('.entry')].map(e => {
      const b = e.querySelector('.body');
      return { text: b.textContent.replace(/\s+/g, ' ').trim(), titles: [...e.querySelectorAll('.brf-title')].map(x => x.textContent.trim()),
               what: ((e.querySelector('.brf-kv .v') || {}).textContent || '').trim() };
    }));
    check(cards.length === 3, '카드 3개', cards.length);
    const c = (i) => cards[i] || { text: '', titles: [], what: '' };
    check(!/^\s*1\/7/.test(c(0).text) && !/(^|\s)1\/7(\s|$)/.test(c(0).text), '① 첫 줄 "1/7" 이 카드에 안 보임', c(0).text.slice(0, 60));
    check(/신문 브리핑/.test(c(0).text) && c(0).titles.some(t => /^1\. 반도체 호황/.test(t)) && /^용인 기흥구/.test(c(0).what), '① 머리말·제목·WHAT 은 그대로', JSON.stringify(c(0)).slice(0, 160));
    check(!/\(?2\/7\)?/.test(c(1).text) && c(1).titles.some(t => /^2\. 서울 전세/.test(t)), '① "**(2/7)**" 형태도 숨김', c(1).text.slice(0, 60));
    check(!/신문요약\s*3\/7/.test(c(2).text) && c(2).titles.some(t => /^3\. 금리 동결/.test(t)), '② 예전 "[신문요약 3/7]" 도 계속 숨김', c(2).text.slice(0, 60));
    check(/3\/4분기 성장률은 1\/7 수준/.test(c(2).what), '③ 본문 속 "3/4분기"·"1/7 수준" 은 그대로', c(2).what);
  } finally { await browser.close(); srv.close(); }
  console.log(pass ? 'ALL PASS' : 'SOME FAILED'); process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
