/**
 * test_viewer_json.js — 요약 GPT 가 붙이는 **'기사↔지면' JSON 묶음**으로 연결 (실제 Chromium)
 *
 *   요약 끝의 {"articles":[{"title","page","bbox"}]} 를 읽어 기사 옆에 그 쪽 사진을 붙인다.
 *   ① JSON 묶음은 화면에 안 보인다(```json 으로 감싼 것 · 감싸지 않은 것 · 깨진 것 모두)
 *   ② page → 그 번호 사진, 제목이 조금 달라도(따옴표·말줄임) 같은 기사로 알아본다
 *   ③ JSON 만 담긴 메시지는 카드로 안 만들고, 다른 메시지의 기사에도 적용된다
 *   ④ bbox(기사 영역)가 있으면 **그 부분만 잘라** 보이고, 🖍 누르면 그 기사로 **확대된 채** 열린다
 *      '🔍 크게' 는 지면 전체로 연다 · 같은 장을 다시 열어도 확대가 적용된다
 *   ⑤ JSON 에 없는 기사는 예전 방식(짐작 안 함)으로 · 직접 연결(📌)이 JSON 보다 우선
 *
 * 실행: npm i playwright && node scripts/test_viewer_json.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');

const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

function makePng(w, h) {
  const crc32 = (buf) => { let c, crc = 0xffffffff;
    for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = c ^ (crc >>> 8); }
    return (crc ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const tc = Buffer.concat([Buffer.from(type), data]);
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(tc));
    return Buffer.concat([len, tc, crc]); };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 235)]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(800, 1200);


const JSON_BLOCK = JSON.stringify({ date: '2026-09-24', articles: [
  { article_id: '20260924-001', title: '3억대 서울 분양도 나와', page: 3, bbox: [0.1, 0.2, 0.5, 0.25] },
  { article_id: '20260924-002', title: '재건축·재개발로 공공임대 8.3만가구', page: 5 },
] }, null, 1);
const MSG1 = [
  '*[신문요약 1/6] 📰 2026년 9월 24일 신문 브리핑*',
  '🔴 “3억대 서울 분양도 나와”…추석 후 청약 큰장',
  '• WHAT: 10월 수도권에서 1만8000여 가구가 공급될 예정임.',
  '• WHY: 3억~5억원대 분양 단지가 등장함.',
  '🔴 재건축·재개발로 공공임대 8.3만가구',
  '• WHAT: 서울 정비사업 496곳의 계획물량은 51만5817가구임.',
  '일본은행 추가 금리 인상 시사',
  '• WHAT: 연내 추가 인상 가능성을 언급함.',
  '',
  '```json', JSON_BLOCK, '```',
].join('\n');
const MSG2 = [
  '*[신문요약 2/6] 신문 브리핑*',
  '목동 9·13단지 최고 49층 재건축',
  '• WHAT: 목동9단지는 49층·41개동·3958가구로 계획됨.',
].join('\n');
// 슬랙이 ``` 를 떼어 버린 경우 — JSON 만 담긴 메시지
const MSG3 = '{"date":"2026-09-24","articles":[{"article_id":"20260924-010","title":"목동 9·13단지 최고 49층 재건축","page":2,"bbox":[0,0.5,1,0.5]}]}';
const MSG4 = '참고\n```json\n{"articles":[{"title":"깨진 JSON", "page": 4\n```';   // 깨진 것 — 숨기되 무시

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-09-24';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: D + 'T06:29:00', source: 'user', kind: 'text', text: MSG1 },
    { ts: D + 'T06:30:00', source: 'user', kind: 'text', text: MSG2 },
    { ts: D + 'T06:31:00', source: 'user', kind: 'text', text: MSG3 },
    { ts: D + 'T06:32:00', source: 'user', kind: 'text', text: MSG4 }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 6,
    images: Array.from({ length: 6 }, (_, i) => { const n = `0${i + 1}.jpg`;
      return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' }; }) }));
  if (u === '/api/news/pagetext') return send('application/json', '{"ok":false}');
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/slack');
  await page.waitForSelector('.brf-art');
  await page.waitForFunction(() => newsState.images.length === 6);

  console.log('\n[① JSON 은 화면에 안 보인다]');
  const txt = await page.evaluate(() => document.getElementById('feed').innerText);
  check(!/article_id|"articles"|bbox|\{"date"/.test(txt), 'JSON 묶음(감싼 것·안 감싼 것)이 글에 안 보인다');
  check(!/깨진 JSON/.test(txt) && /참고/.test(txt), '깨진 JSON 도 숨기고 앞의 글은 남긴다');
  check(await page.evaluate(() => document.querySelectorAll('.entry').length) === 3, 'JSON 만 담긴 메시지는 카드로 안 만든다');
  check(await page.evaluate(() => SUMMARY_META.length) === 3, 'JSON 기사 정보 3건을 모았다(두 메시지에서)');

  console.log('\n[② ③ 글+지면 연결]');
  await page.click('.viewseg [data-view="paper"]');
  const sides = () => page.evaluate(() => [...document.querySelectorAll('.brf-art')].map(a => {
    const s = a.querySelector('.brf-side');
    return { t: (a.querySelector('.brf-title') || {}).textContent.slice(0, 10), no: (s.querySelector('.side-no') || {}).textContent || '',
             src: (s.querySelector('.side-src') || {}).textContent || '', crop: !!s.querySelector('.side-fig.crop'), empty: !!s.querySelector('.side-empty') };
  }));
  await page.waitForFunction(() => document.querySelectorAll('.brf-side').length === 4);
  let s = await sides();
  check(s[0].no === '03' && /요약 JSON · 3쪽 · 기사 영역/.test(s[0].src), '"“3억대…”…청약 큰장" → 3쪽(제목이 조금 달라도 같은 기사)', s[0].src);
  check(s[1].no === '05' && !s[1].crop, '"공공임대 8.3만가구" → 5쪽(영역 없음 → 지면 전체)', s[1].src);
  check(s[2].empty, 'JSON 에 없는 "일본은행" 기사는 짐작하지 않는다');
  check(s[3].no === '02' && s[3].crop, '다른 메시지의 JSON(감싸지 않은 것)도 "목동" 기사에 적용 → 2쪽', s[3].src);

  console.log('\n[④ 기사 영역만 잘라 보이기 · 확대해서 열기]');
  await page.waitForFunction(() => { const f = document.querySelector('.side-fig.crop'); return f && f.style.aspectRatio; });
  const crop = await page.evaluate(() => {
    const f = document.querySelector('.side-fig.crop'), r = f.getBoundingClientRect();
    return { ratio: r.width / r.height, want: (0.5 * 800) / (0.25 * 1200) };
  });
  check(Math.abs(crop.ratio - crop.want) < 0.05, '잘라 보인 칸의 모양 = 기사 영역 모양', `${crop.ratio.toFixed(2)} ≈ ${crop.want.toFixed(2)}`);
  const inBox = () => page.evaluate(() => {
    const r = document.getElementById('lb-img').getBoundingClientRect(), st = document.getElementById('lb-stage').getBoundingClientRect();
    // 화면 가운데가 사진의 어느 지점인가(0~1)
    return { z: V.zoom, cx: (st.left + st.width / 2 - r.left) / r.width, cy: (st.top + st.height / 2 - r.top) / r.height, pen: M.on };
  });
  await page.click('.brf-side .side-fig.crop');
  await page.waitForFunction(() => !document.getElementById('lb').hidden && V.zoom > 1.01);
  let z = await inBox();
  check(z.z > 1.5 && Math.abs(z.cx - 0.35) < 0.03 && Math.abs(z.cy - 0.325) < 0.03 && z.pen,
        '🖍: 그 기사 영역으로 확대돼 가운데 놓이고 형광펜이 켜진다', `배율 ${z.z.toFixed(2)} · 가운데 (${z.cx.toFixed(2)}, ${z.cy.toFixed(2)})`);
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await page.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="view"]').click());
  await page.waitForFunction(() => !document.getElementById('lb').hidden && document.getElementById('lb-img').style.visibility === 'visible');
  await page.waitForTimeout(200);
  z = await inBox();
  check(z.z < 1.01, '🔍 크게: 같은 장을 지면 전체로 연다', `배율 ${z.z.toFixed(2)}`);
  await page.keyboard.press('Escape');
  await page.click('.brf-side .side-fig.crop');                 // 같은 장을 다시 — 확대가 또 적용돼야
  await page.waitForFunction(() => !document.getElementById('lb').hidden && V.zoom > 1.01, null, { timeout: 5000 }).catch(() => {});
  z = await inBox();
  check(z.z > 1.5, '같은 장을 다시 열어도 기사 영역 확대가 적용된다', `배율 ${z.z.toFixed(2)}`);
  check(await page.evaluate(() => document.getElementById('lb-img').style.visibility) === 'visible', '사진이 가려진 채 남지 않는다');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');

  console.log('\n[⑤ 우선순위]');
  await page.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="pick"]').click());
  await page.waitForSelector('#lb-pick:not([hidden])');
  await page.click('#lb-next');
  await page.click('#lb-pick');
  s = await sides();
  check(s[0].no === '04' && /직접 연결/.test(s[0].src), '직접 연결(📌)이 JSON 보다 우선', s[0].src);

  console.log('\n[글만 보기]');
  await page.click('.viewseg [data-view="text"]');
  check(!/article_id|"articles"/.test(await page.evaluate(() => document.getElementById('feed').innerText)) &&
        await page.evaluate(() => !document.querySelector('.brf-side')), '글만 보기에서도 JSON 은 안 보이고 사진 칸도 없다');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
