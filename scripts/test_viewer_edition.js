/**
 * test_viewer_edition.js — 신문 요약 화면 '📰 종이신문 / 🌐 온라인신문' 고르기 확인 (실제 Chromium) — 2026-10-27 사용자 요청
 *
 *   ① 처음엔 종이신문: 종이 요약 + 오디오 칸 + 사설 칸, 서버엔 edition 없이 묻는다
 *   ② 온라인신문을 누르면: edition=online 으로 다시 받아 온라인 요약만, 사설·원본 칸은 숨김
 *      오디오 칸은 온라인 브리핑으로 바뀌고(18시 먼저), 09시·18시 단추로 고른다 (2026-10-28)
 *   ③ 고른 것을 기억(새로고침해도 온라인) · 주소 ?edition=paper 가 우선
 *   ④ 온라인 요약이 없으면 '9시·18시' 안내
 *   ⑤ 폰 390px 에서 옆으로 안 넘친다
 * 실행: npm i playwright && node scripts/test_viewer_edition.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const D = '2026-10-27';
const PAPER = `[신문요약 1/1] ${D}\n\n1. 🔵 종이기사 제목가\n• 사진: 01\n• WHAT: 종이 기사 내용.\n• WHY: 기사에 원인 언급 없음.\n• HOW:\n• [확정] 종이 사실.\n• 원문: <https://n.news.naver.com/mnews/article/009/0000000001|매일경제>`;
const ONLINE = `[신문요약 1/1] ${D} 09시 온라인신문\n\n1. 🔵 온라인기사 제목나\n• WHAT: 온라인 기사 내용.\n• WHY: 기사에 원인 언급 없음.\n• HOW:\n• [확정] 온라인 사실.\n• 원문: <https://n.news.naver.com/mnews/article/015/0000000002|한국경제>`;
const ED = { ok: true, date: D, items: [{ title: '사설 제목', url: 'https://www.mk.co.kr/news/editorial/1', paras: ['문단.'] }] };
let onlineMsgs = [ONLINE];
let onlinePods = [{ ok: true, slot: '18', title: '저녁 온라인', bytes: 2048, url: '/api/news/podcast/audio?date=' + D + '&slot=18' },
                  { ok: true, slot: '09', title: '아침 온라인', bytes: 2048, url: '/api/news/podcast/audio?date=' + D + '&slot=09' }];
const asked = [];
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), p = u.pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (p === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (p === '/economy/data') {
    const ed = u.searchParams.get('edition') || ''; asked.push(ed);
    const texts = ed === 'online' ? onlineMsgs : [PAPER];
    return send('application/json', JSON.stringify({ date: D, messages: texts.map(t => ({ ts: D + 'T09:05:00+09:00', source: 'web', kind: 'text', text: t })) }));
  }
  if (p === '/api/news/editorial') return send('application/json', JSON.stringify(ED));
  if (p === '/api/news/podcast') return send('application/json', JSON.stringify(u.searchParams.get('edition') === 'online'
    ? { ok: onlinePods.length > 0, date: D, items: onlinePods }
    : { ok: true, date: D, title: '오늘 브리핑', bytes: 2048, url: '/api/news/podcast/audio?date=' + D }));
  if (p === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const look = page => page.evaluate(() => {
    const vis = id => { const el = document.getElementById(id); return !!el && !el.hidden && el.getBoundingClientRect().height > 0; };
    return { feed: document.getElementById('feed').textContent, pod: vis('pod'), ed: vis('mk-ed'),
      podSrc: document.getElementById('pod-audio').getAttribute('src') || '', podSub: document.getElementById('pod-sub').textContent,
      slots: [...document.querySelectorAll('#pod-slots button')].map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : '')),
      pressed: document.querySelector('#edtog [aria-pressed="true"]').dataset.ed, label: document.getElementById('ed-label').textContent };
  });

  console.log('\n[① 처음엔 종이신문]');
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  let page = await ctx.newPage();
  await page.goto(base + '/economy');
  await page.waitForSelector('#mk-ed:not([hidden])');
  await page.waitForSelector('#pod:not([hidden])');
  let s = await look(page);
  check(s.pressed === 'paper' && /종이기사 제목가/.test(s.feed) && !/온라인기사/.test(s.feed), '종이 요약이 보이고 종이신문 단추가 눌림', s.label);
  check(s.pod && s.ed, '오디오 칸·사설 칸이 보인다');
  check(asked[0] === '', '서버엔 edition 없이 묻는다(기존 그대로)', JSON.stringify(asked));

  console.log('\n[② 온라인신문 누르기]');
  await page.click('#edtog button[data-ed="online"]');
  await page.waitForFunction(() => /온라인기사 제목나/.test(document.getElementById('feed').textContent));
  s = await look(page);
  check(!/종이기사/.test(s.feed), '온라인 요약만 보인다');
  check(!s.ed && await page.evaluate(() => document.getElementById('news').hidden), '사설·원본 칸은 숨김');
  await page.waitForFunction(() => /slot=18/.test(document.getElementById('pod-audio').getAttribute('src') || ''));
  s = await look(page);
  check(s.pod && /18시 · 저녁 온라인/.test(s.podSub) && s.slots.join() === '09시,18시*', '오디오 칸은 온라인 18시 브리핑, 09시·18시 단추', `${s.podSub} [${s.slots}]`);
  await page.click('#pod-slots button[data-slot="09"]');
  s = await look(page);
  check(/slot=09/.test(s.podSrc) && /09시 · 아침 온라인/.test(s.podSub) && s.slots.join() === '09시*,18시', '09시 단추를 누르면 아침 브리핑으로', s.podSrc);
  check(s.pressed === 'online' && /온라인/.test(s.label) && asked.includes('online'), '단추·제목 줄이 온라인으로, 서버엔 edition=online', s.label);
  await page.click('#edtog button[data-ed="paper"]');
  await page.waitForFunction(() => /종이기사 제목가/.test(document.getElementById('feed').textContent));
  await page.waitForSelector('#mk-ed:not([hidden])');
  await page.waitForSelector('#pod:not([hidden])');
  await page.waitForFunction(() => /audio\?date=[\d-]+$/.test(document.getElementById('pod-audio').getAttribute('src') || ''));
  s = await look(page);
  check(s.slots.length === 0 && /오늘 브리핑/.test(s.podSub), '종이신문으로 돌아오면 종이 오디오·사설 칸이 다시 보인다', s.podSub);
  await page.click('#edtog button[data-ed="online"]');
  await page.waitForFunction(() => /온라인기사/.test(document.getElementById('feed').textContent));

  console.log('\n[③ 기억하기]');
  await page.reload();
  await page.waitForFunction(() => /온라인기사 제목나/.test(document.getElementById('feed').textContent));
  check((await look(page)).pressed === 'online', '새로고침해도 온라인신문');
  await page.goto(base + '/economy?edition=paper');
  await page.waitForFunction(() => /종이기사 제목가/.test(document.getElementById('feed').textContent));
  check((await look(page)).pressed === 'paper', '주소 ?edition=paper 가 기억보다 우선');
  await page.close();

  console.log('\n[④ 온라인 요약이 없을 때]');
  onlineMsgs = [];
  onlinePods = [onlinePods[1]];
  page = await ctx.newPage();
  await page.goto(base + '/economy?edition=online');
  await page.waitForSelector('#feed .empty');
  check(/9시·18시/.test(await page.textContent('#feed .empty')), "'9시·18시에 올립니다' 안내");
  await page.waitForSelector('#pod:not([hidden])');
  s = await look(page);
  check(/slot=09/.test(s.podSrc) && s.slots.length === 0, '온라인 오디오가 하나면 시간대 단추 없이 그것만', s.podSub);
  await page.close(); await ctx.close();

  console.log('\n[⑤ 폰]');
  onlineMsgs = [ONLINE];
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto(base + '/economy?edition=online');
  await page.waitForFunction(() => /온라인기사/.test(document.getElementById('feed').textContent));
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const tg = await page.evaluate(() => { const r = document.getElementById('edtog').getBoundingClientRect(); return { l: r.left, r: r.right }; });
  check(over <= 0 && tg.l >= 0 && tg.r <= 390, '폰에서 옆으로 안 넘치고 단추가 화면 안에', `넘침 ${over}px · ${Math.round(tg.l)}~${Math.round(tg.r)}`);
  await page.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
