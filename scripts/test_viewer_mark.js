/**
 * test_viewer_mark.js — 신문 사진 '형광펜' 기능 확인 (실제 Chromium)
 *
 * 형광펜은 **일회성**이다 — 이 창의 메모리에만 있고 새로고침하면 사라진다.
 * 서버에도 브라우저 저장소에도 아무것도 남기지 않는다.
 *
 * 확인하는 것
 *   ① 🖍 버튼으로 형광펜 모드가 켜지고 도구모음이 나온다
 *   ② 끌면 줄이 그어진다
 *   ③ **새로고침하면 사라진다** (일회성의 핵심)
 *   ④ **서버로 아무것도 안 보낸다 / 브라우저 저장소에 아무것도 안 남긴다**
 *   ⑤ 확대해도 형광펜이 사진에 딱 붙어 따라간다
 *   ⑥ 창이 열려 있는 동안엔 장을 넘기거나 뷰어를 닫았다 열어도 유지된다
 *   ⑦ 장마다 따로 · 되돌리기 · 지우개 · 모드 중 스와이프 차단
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

// 형광펜은 서버를 쓰지 않아야 한다 → 관련 요청이 오면 '있으면 안 되는 호출'로 기록해 둔다.
const strayCalls = [];

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-17', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-17' }));
  if (u === '/page.png') return send('image/png', PNG);
  if (u.includes('marks')) {                      // 형광펜 관련 요청은 오면 안 된다
    strayCalls.push(req.method + ' ' + req.url);
    res.writeHead(404); return res.end();
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
  await page.waitForTimeout(300);
  check(strayCalls.length === 0, '서버로 아무것도 보내지 않는다',
        strayCalls.length ? strayCalls.join(', ') : '요청 0건');
  const stored = await page.evaluate(() => {
    const keys = [];
    try { for (let i = 0; i < localStorage.length; i++) keys.push('local:' + localStorage.key(i)); } catch (e) {}
    try { for (let i = 0; i < sessionStorage.length; i++) keys.push('session:' + sessionStorage.key(i)); } catch (e) {}
    return keys;
  });
  check(stored.length === 0, '브라우저 저장소에도 아무것도 안 남긴다',
        stored.length ? stored.join(', ') : '저장된 값 0개');
  // 저장하지 않으므로 '저장됨' 대신 일회성이라는 안내가 떠야 한다
  const notice = await page.textContent('#lb-saved');
  check(/새로고침하면 사라짐/.test(notice || ''), '"이 창에서만 유지" 안내가 보인다',
        `"${notice}"`);

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

  console.log('\n[창이 열려 있는 동안엔 유지]');
  await page.evaluate(() => closeViewer());      // 뷰어만 닫았다가
  await openViewer(page, 0);                     // 다시 열기
  await page.waitForTimeout(300);
  check(await marksOf(page, '01.jpg') === 1, '뷰어를 닫았다 열어도 1쪽 형광펜이 남아 있다');
  const painted = await page.evaluate(() => {
    const c = document.getElementById('lb-mark');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 10) n++;
    return n;
  });
  check(painted > 500, '화면에도 실제로 그려진다', `칠해진 점 ${painted}개`);

  console.log('\n[새로고침하면 사라진다 — 일회성의 핵심]');
  await page.reload();
  await openViewer(page);
  await page.waitForTimeout(400);
  check(await marksOf(page, '01.jpg') === 0, '새로고침 후 형광펜이 사라진다');
  const afterReload = await page.evaluate(() => {
    const c = document.getElementById('lb-mark');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 10) n++;
    return n;
  });
  check(afterReload === 0, '화면에도 아무것도 안 남는다', `칠해진 점 ${afterReload}개`);

  console.log('\n[다른 사람(다른 창)에게는 안 보인다 — IP 와 무관하게 분리]');
  await page.click('#lb-pen');                   // 새로고침으로 모드가 꺼졌으니 다시 켠다
  await stroke(page, 0.2, 0.4, 0.8, 0.4);        // 이 창에 하나 긋고
  const other = await browser.newContext({ viewport: { width: 1100, height: 850 } });
  const page2 = await other.newPage();           // 같은 컴퓨터(= 같은 IP)의 다른 창
  await page2.goto(base + '/slack');
  await openViewer(page2);
  await page2.waitForTimeout(400);
  check(await marksOf(page, '01.jpg') === 1, '내 창에는 내가 그은 게 있고');
  check(await marksOf(page2, '01.jpg') === 0, '다른 창에는 안 보인다(같은 IP 여도 분리된다)');
  check(strayCalls.length === 0, '끝까지 서버로 아무 요청도 안 갔다',
        strayCalls.length ? strayCalls.join(', ') : '요청 0건');
  await other.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
