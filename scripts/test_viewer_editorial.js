/**
 * test_viewer_editorial.js — 신문 요약 페이지 맨 아래 '📰 매일경제 사설' 칸 확인 (실제 Chromium) — 2026-10-20 사용자 요청
 *
 *   ① 사설이 있으면: 요약 글들 **아래**에 제목·올라온 시각·원문 링크·본문, 긴 글은 2문단만 보이고 '전문 펼치기'/'접기'
 *   ② 2문단 이하 글은 펼치기 단추 없이 다 보인다(흐리게 가리지 않음)
 *   ③ 못 가져오면: 화면이 안 깨지고 '사설 목록 열기' 링크만 · 서버로 20초마다 다시 묻지 않는다
 *   ④ 폰 390px 에서 옆으로 안 넘친다
 * 서버 쪽(사설 모으기)은 python3 scripts/test_mk_editorial.py 에서 따로 검사.
 * 실행: npm i playwright && node scripts/test_viewer_editorial.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const D = '2026-10-20';
const MSG = `[2026-10-20 신문 요약 1/1]\n1. 서울 11월 입주 488가구 (2)\n• WHAT: 서울 11월 입주 예정 488가구.\n• WHY: 공급 감소.\n• HOW: 지켜봄.`;
const ED = { ok: true, date: D, stale: false, items: [
  { title: '공급 없는 대책은 집값을 못 잡는다', url: 'https://www.mk.co.kr/news/editorial/12180001', published: '2026-10-19T17:31:00+09:00',
    paras: ['첫째 문단 사설본문가.', '둘째 문단 사설본문나.', '셋째 문단 사설본문다.', '넷째 문단 사설본문라.'] },
  { title: '노동개혁 더 미룰 시간 없다', url: 'https://www.mk.co.kr/news/editorial/12180002', published: '2026-10-20T05:00:00+09:00',
    paras: ['짧은 사설 첫 문단.', '짧은 사설 둘째 문단.'] }] };
let edMode = 'ok', edCalls = 0;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), p = u.pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (p === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (p === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [{ ts: D + 'T07:10:00', source: 'user', kind: 'text', text: MSG }] }));
  if (p === '/api/news/editorial') { edCalls++; return send('application/json', JSON.stringify(edMode === 'ok' ? ED : { ok: false, items: [], error: '사설 링크를 못 찾음' })); }
  if (p === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  console.log('\n[① ② 사설이 있을 때]');
  let page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(base + '/slack?date=' + D);
  await page.waitForSelector('.mk-ed-item');
  const info = await page.evaluate(() => {
    const sec = document.getElementById('mk-ed'), feed = document.getElementById('feed');
    const vis = el => el && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().height > 0;
    const items = [...sec.querySelectorAll('.mk-ed-item')];
    return { below: feed.getBoundingClientRect().bottom <= sec.getBoundingClientRect().top + 1,
      titles: items.map(i => i.querySelector('h3').textContent), meta: items[0].querySelector('.mk-ed-meta').textContent,
      link: items[0].querySelector('.mk-ed-meta a').href, shown0: [...items[0].querySelectorAll('p')].filter(vis).length,
      btn0: !!items[0].querySelector('.mk-ed-more'), shown1: [...items[1].querySelectorAll('p')].filter(vis).length, btn1: !!items[1].querySelector('.mk-ed-more'),
      faded1: getComputedStyle(items[1].querySelectorAll('p')[1]).maskImage || getComputedStyle(items[1].querySelectorAll('p')[1]).webkitMaskImage };
  });
  check(info.below && info.titles.join('|') === '공급 없는 대책은 집값을 못 잡는다|노동개혁 더 미룰 시간 없다', '요약 글들 아래에 사설 두 편', info.titles.join(' / '));
  check(/10월 19일 17:31 올라옴/.test(info.meta) && info.link === 'https://www.mk.co.kr/news/editorial/12180001', '올라온 시각과 원문 링크', info.meta);
  check(info.shown0 === 2 && info.btn0, '긴 글은 2문단만 보이고 "전문 펼치기" 단추', `${info.shown0}문단`);
  await page.click('.mk-ed-more');
  check(await page.evaluate(() => document.querySelectorAll('#mk-ed-b0 p').length === 4 && [...document.querySelectorAll('#mk-ed-b0 p')].every(p => getComputedStyle(p).display !== 'none')) &&
        (await page.textContent('.mk-ed-more')) === '접기', '누르면 전문이 다 보이고 단추는 "접기"');
  check(info.shown1 === 2 && !info.btn1 && (!info.faded1 || info.faded1 === 'none'), '2문단짜리는 단추 없이 다 보이고 흐리게 가리지 않는다', info.faded1);
  await page.close();

  console.log('\n[③ 못 가져올 때]');
  edMode = 'fail'; edCalls = 0;
  page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(base + '/slack?date=' + D);
  await page.waitForSelector('.mk-ed-empty');
  check(await page.isVisible('.mk-ed-empty a[href="https://www.mk.co.kr/opinion/editorial/"]') && await page.isVisible('.brf-art'),
        '요약은 그대로, 사설 칸엔 "사설 목록 열기" 링크만');
  await page.evaluate(() => { loadNews(); loadNews(); });
  await page.waitForTimeout(300);
  check(edCalls === 1, '20초 자동 갱신마다 사설을 다시 묻지 않는다(몇 분 간격)', `사설 요청 ${edCalls}번`);
  await page.close();

  console.log('\n[④ 폰]');
  edMode = 'ok';
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.goto(base + '/slack?date=' + D);
  await page.waitForSelector('.mk-ed-item');
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const ed = await page.evaluate(() => { const r = document.getElementById('mk-ed').getBoundingClientRect(); return { l: r.left, r: r.right }; });
  check(over <= 0 && ed.l >= 0 && ed.r <= 390, '폰에서 옆으로 안 넘치고 사설 칸이 화면 안에', `넘침 ${over}px · ${Math.round(ed.l)}~${Math.round(ed.r)}`);
  await page.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
