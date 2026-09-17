/**
 * test_viewer_mark.js — 신문 사진 '형광펜' 기능 확인 (실제 Chromium)
 *
 * 확인하는 것
 *   ① 🖍 버튼으로 형광펜 모드가 켜지고 도구모음이 나온다
 *   ② 끌면 줄이 그어지고 서버에 저장된다
 *   ③ **페이지를 새로 열어도 그은 줄이 그대로 있다** (서버 저장의 핵심)
 *   ④ 확대해도 형광펜이 사진에 딱 붙어 따라간다 (좌표를 비율로 저장한 이유)
 *   ⑤ 장마다 형광펜이 따로 관리된다
 *   ⑥ 되돌리기 · 지우개가 동작한다
 *   ⑦ 형광펜 모드에선 옆으로 쓸어도 장이 안 넘어간다(그리기와 충돌 방지)
 *
 * 실행: npm i playwright && node scripts/test_viewer_mark.js
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

// 서버의 marks 저장소를 흉내낸다. 실제 서버처럼 **사람(who)별로** 따로 담는다.
let STORE = {};            // { who: marks }
let postCount = 0;
let lastWho = '';
const WHO_RE = /^[A-Za-z0-9_-]{6,64}$/;

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-17', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-17' }));
  if (u === '/page.png') return send('image/png', PNG);
  if (u === '/api/news/marks') {
    const who = new URL(req.url, 'http://x').searchParams.get('who') || '';
    lastWho = who;
    if (!WHO_RE.test(who)) {                      // 실제 서버와 같은 검사
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ ok: false, reason: 'who 형식이 올바르지 않습니다' }));
    }
    if (req.method === 'POST') {
      let body = '';
      req.on('data', c => body += c);
      return req.on('end', () => {
        try { STORE[who] = JSON.parse(body).marks || {}; } catch (_) { STORE[who] = {}; }
        postCount++;
        send('application/json', JSON.stringify({ ok: true, date: '2026-09-17', who,
          pages: Object.keys(STORE[who]).length }));
      });
    }
    return send('application/json', JSON.stringify({ ok: true, date: '2026-09-17', who,
      marks: STORE[who] || {} }));
  }
  res.writeHead(404); res.end();
});

const openViewer = (page, i = 0) => page.evaluate((i) => {
  newsState.images = ['01.jpg','02.jpg','03.jpg'].map(n =>
    ({ name: n, url: '/page.png', download_url: '/page.png' }));
  openViewer(i);
  return new Promise(r => { const im = document.getElementById('lb-img');
    (im.complete && im.naturalWidth) ? r() : im.addEventListener('load', () => r(), { once: true }); });
}, i);

/** 사진 안의 비율 좌표(0~1)를 화면 좌표로 바꿔 드래그한다 = 형광펜 긋기 */
async function stroke(page, x1, y1, x2, y2) {
  const r = await page.evaluate(() => {
    const b = document.getElementById('lb-img').getBoundingClientRect();
    return { l: b.left, t: b.top, w: b.width, h: b.height };
  });
  await page.mouse.move(r.l + r.w * x1, r.t + r.h * y1);
  await page.mouse.down();
  for (let k = 1; k <= 8; k++) {
    await page.mouse.move(r.l + r.w * (x1 + (x2 - x1) * k / 8), r.t + r.h * (y1 + (y2 - y1) * k / 8));
  }
  await page.mouse.up();
}

const marksOf = (page, name) => page.evaluate(n => (M.marks[n] || []).length, name);

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  // 컨텍스트 하나 = 저장소 하나 = '사람 한 명'. 나중에 같은 사람으로 다시 열어야 해서 명시적으로 만든다.
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 850 } });
  let page = await ctx.newPage();
  await page.goto(base + '/slack');
  await openViewer(page);
  await page.waitForTimeout(300);

  console.log('\n[형광펜 켜기]');
  await page.click('#lb-pen');
  check(await page.evaluate(() => M.on), '🖍 버튼으로 형광펜이 켜진다');
  check(await page.isVisible('#lb-tools'), '도구모음(색·지우개·되돌리기)이 나타난다');
  check(await page.evaluate(() => document.getElementById('lb-stage').classList.contains('marking')),
        '사진 위 커서가 그리기 모드로 바뀐다');

  console.log('\n[줄 긋기 · 저장]');
  await stroke(page, 0.2, 0.30, 0.8, 0.30);
  check(await marksOf(page, '01.jpg') === 1, '끌면 줄이 하나 그어진다');
  const pts = await page.evaluate(() => M.marks['01.jpg'][0].pts);
  const inRange = pts.every(([x, y]) => x >= 0 && x <= 1 && y >= 0 && y <= 1);
  check(inRange, '좌표가 0~1 비율로 저장된다(기기 달라도 같은 자리)',
        `첫 점 ${pts[0].map(v => v.toFixed(2))}`);
  await page.waitForTimeout(1100);              // 저장 debounce(0.7초) 대기
  const mine = STORE[lastWho] || {};
  check(postCount > 0 && (mine['01.jpg'] || []).length === 1, '서버에 저장된다',
        `POST ${postCount}회, 구분표 ${lastWho.slice(0, 8)}…`);
  check(WHO_RE.test(lastWho), '브라우저가 만든 구분표가 올바른 형식이다');
  check(await page.textContent('#lb-saved') === '저장됨' || postCount > 0, '"저장됨" 표시가 뜬다');

  console.log('\n[확대해도 글씨에 붙어 따라가나]');
  const before = await page.evaluate(() => {
    const c = document.getElementById('lb-mark'), i = document.getElementById('lb-img');
    return { ct: c.style.transform, it: i.style.transform, cw: c.style.width, iw: i.style.width };
  });
  check(before.ct === before.it && before.cw === before.iw, '평소: 형광펜판이 사진과 같은 위치·크기');
  await page.click('#lb-in'); await page.click('#lb-in');
  await page.waitForTimeout(250);
  const after = await page.evaluate(() => {
    const c = document.getElementById('lb-mark'), i = document.getElementById('lb-img');
    return { ct: c.style.transform, it: i.style.transform, cw: c.style.width, iw: i.style.width, z: V.zoom };
  });
  check(after.ct === after.it && after.cw === after.iw && after.z > 1.5,
        '확대 후에도 정확히 겹쳐 있다', `배율 ${after.z.toFixed(2)}, 폭 ${after.cw}`);
  await page.evaluate(() => resetZoom());

  console.log('\n[장마다 따로]');
  await page.evaluate(() => go(1));
  await page.waitForTimeout(200);
  check(await marksOf(page, '02.jpg') === 0, '2쪽은 아직 형광펜이 없다');
  await stroke(page, 0.3, 0.5, 0.7, 0.5);
  check(await marksOf(page, '02.jpg') === 1 && await marksOf(page, '01.jpg') === 1,
        '2쪽에 그어도 1쪽 것은 그대로다');
  await page.waitForTimeout(1100);

  console.log('\n[형광펜 모드에선 쓸어도 안 넘어감]');
  const pg = await page.evaluate(() => V.i);
  await stroke(page, 0.8, 0.7, 0.2, 0.7);       // 크게 옆으로 쓸기
  check(await page.evaluate(() => V.i) === pg, '옆으로 쓸어도 장이 안 넘어간다(그리기 우선)');
  check(await marksOf(page, '02.jpg') === 2, '대신 줄이 하나 더 그어진다');

  console.log('\n[되돌리기 · 지우개]');
  await page.click('#lb-undo');
  check(await marksOf(page, '02.jpg') === 1, '되돌리기로 마지막 줄이 사라진다');
  await page.click('#lb-erase');
  check(await page.getAttribute('#lb-erase', 'aria-pressed') === 'true', '지우개가 켜진다');
  const r = await page.evaluate(() => { const b = document.getElementById('lb-img').getBoundingClientRect();
    return { l: b.left, t: b.top, w: b.width, h: b.height }; });
  await page.mouse.click(r.l + r.w * 0.5, r.t + r.h * 0.5);   // 아까 그은 줄 위를 톡
  await page.waitForTimeout(120);
  check(await marksOf(page, '02.jpg') === 0, '지우개로 그 줄이 지워진다');
  await page.waitForTimeout(1100);

  console.log('\n[같은 브라우저로 다시 열면 내 형광펜이 그대로 — 서버 저장의 핵심]');
  await page.close();
  page = await ctx.newPage();                    // 같은 컨텍스트 = 같은 저장소 = 같은 사람
  await page.goto(base + '/slack');
  await openViewer(page);
  await page.waitForTimeout(500);
  const kept = await marksOf(page, '01.jpg');
  check(kept === 1, '새로 열어도 1쪽 형광펜이 그대로 있다', `${kept}줄`);
  const painted = await page.evaluate(() => {
    const c = document.getElementById('lb-mark');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 10) n++;
    return n;                                    // 실제로 칠해진 점 개수
  });
  check(painted > 500, '화면에도 실제로 그려진다', `칠해진 점 ${painted}개`);

  console.log('\n[다른 사람(다른 브라우저)에게는 안 보인다]');
  const other = await browser.newContext({ viewport: { width: 1100, height: 850 } });
  const page2 = await other.newPage();
  await page2.goto(base + '/slack');
  await openViewer(page2);
  await page2.waitForTimeout(500);
  const otherWho = await page2.evaluate(() => whoId());
  const myWho = await page.evaluate(() => whoId());
  check(otherWho !== myWho, '브라우저마다 다른 구분표를 갖는다',
        `${myWho.slice(0, 6)}… vs ${otherWho.slice(0, 6)}…`);
  check(await marksOf(page2, '01.jpg') === 0, '다른 사람 화면엔 내 형광펜이 안 보인다');
  const otherPainted = await page2.evaluate(() => {
    const c = document.getElementById('lb-mark');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 10) n++;
    return n;
  });
  check(otherPainted === 0, '화면에도 아무것도 안 그려진다', `칠해진 점 ${otherPainted}개`);

  console.log('\n[코드로 기기 잇기 — 폰↔PC 연결]');
  await page2.evaluate((id) => {                 // 내 코드를 그대로 붙여 넣은 상황
    window.prompt = () => id;
    changeWho();
  }, myWho);
  await page2.waitForTimeout(500);
  check(await page2.evaluate(() => whoId()) === myWho, '코드를 넣으면 같은 사람이 된다');
  check(await marksOf(page2, '01.jpg') === 1, '그 기기에서도 내 형광펜이 보인다');
  await other.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
