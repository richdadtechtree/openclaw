/**
 * test_viewer_zoom.js — 신문 사진 뷰어 '마우스 휠 확대·축소' 확인 (실제 Chromium)
 *
 * 확인하는 것
 *   ① 휠을 위로 굴리면 커지고, 아래로 굴리면 작아진다
 *   ② **커서가 가리킨 지점이 제자리에 남는다** (보던 기사에 대고 굴리면 그 기사가 커짐)
 *   ③ 원래 크기(1배)보다 작아지지 않는다
 *   ④ 너무 크게는 안 커진다(선명한 한계의 3배까지)
 *   ⑤ 트랙패드처럼 잘게 굴려도 부드럽게 커진다
 *   ⑥ 형광펜 모드에서도 휠 확대가 되고, 형광펜이 사진을 따라간다
 *
 * 실행: npm i playwright && node scripts/test_viewer_zoom.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');

const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

function makePng(w, h) {
  const crc32 = (b) => { let c, crc = 0xffffffff;
    for (let n = 0; n < b.length; n++) { c = (crc ^ b[n]) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = c ^ (crc >>> 8); }
    return (crc ^ 0xffffffff) >>> 0; };
  const ch = (t, d) => { const tc = Buffer.concat([Buffer.from(t), d]);
    const l = Buffer.alloc(4); l.writeUInt32BE(d.length);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc32(tc));
    return Buffer.concat([l, tc, c]); };
  const ih = Buffer.alloc(13);
  ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 235)]);
  return Buffer.concat([Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]),
    ch('IHDR', ih), ch('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: h }, () => row)))),
    ch('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(1600, 2400);                 // 신문 지면 정도의 큰 사진

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-17', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-17' }));
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

const openViewer = (page) => page.evaluate(() => {
  newsState.images = ['01.jpg', '02.jpg'].map(n => ({ name: n, url: '/page.png', download_url: '/page.png' }));
  openViewer(0);
  return new Promise(r => { const im = document.getElementById('lb-img');
    (im.complete && im.naturalWidth) ? r() : im.addEventListener('load', () => r(), { once: true }); });
});

const zoom = (page) => page.evaluate(() => V.zoom);
/** 커서 위치가 사진의 '어느 지점'을 가리키는지(0~1). 확대 전후로 같아야 한다. */
const pointUnderCursor = (page, cx, cy) => page.evaluate(([cx, cy]) => {
  const r = document.getElementById('lb-img').getBoundingClientRect();
  return [(cx - r.left) / r.width, (cy - r.top) / r.height];
}, [cx, cy]);

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  await page.goto(base + '/slack');
  await openViewer(page);
  await page.waitForTimeout(300);

  console.log('\n[휠로 확대·축소]');
  check(await zoom(page) === 1, '처음엔 화면에 맞춘 크기(1배)');

  await page.mouse.move(600, 450);
  await page.mouse.wheel(0, -100);               // 위로 한 칸
  await page.waitForTimeout(120);
  const z1 = await zoom(page);
  check(z1 > 1.1, '휠을 위로 굴리면 커진다', `1 → ${z1.toFixed(3)}배`);

  await page.mouse.wheel(0, 100);                // 아래로 한 칸
  await page.waitForTimeout(120);
  const z2 = await zoom(page);
  check(z2 < z1, '휠을 아래로 굴리면 작아진다', `${z1.toFixed(3)} → ${z2.toFixed(3)}배`);

  console.log('\n[커서가 가리킨 지점이 제자리에 남나]');
  // ⚠️ 사진이 창보다 좁으면(세로로 긴 신문 + 넓은 창) 가로는 '가운데 정렬'이 유지된다.
  //    빈 공간이 있는데 사진이 한쪽으로 쏠리면 이상하기 때문 — 의도된 동작(clampPan).
  //    그래서 커서 고정은 **사진이 화면을 꽉 채운 뒤**에 의미가 있다. 먼저 충분히 확대한다.
  await page.evaluate(() => resetZoom());
  await page.mouse.move(600, 450);
  for (let i = 0; i < 5; i++) await page.mouse.wheel(0, -100);
  await page.waitForTimeout(200);
  const fills = await page.evaluate(() =>
    V.fitW * V.zoom > V.stage.w + 20 && V.fitH * V.zoom > V.stage.h + 20);
  check(fills, '사진이 화면을 꽉 채울 만큼 확대됨(이제 상하좌우로 움직일 수 있다)');

  const cx = 780, cy = 320;                      // 화면 오른쪽 위 어딘가를 겨냥
  await page.mouse.move(cx, cy);
  const pBefore = await pointUnderCursor(page, cx, cy);
  await page.mouse.wheel(0, -100);
  await page.waitForTimeout(150);
  const pAfter = await pointUnderCursor(page, cx, cy);
  const dx = Math.abs(pAfter[0] - pBefore[0]), dy = Math.abs(pAfter[1] - pBefore[1]);
  check(dx < 0.01 && dy < 0.01, '확대해도 커서 밑의 기사가 그대로 있다',
        `가로 ${(dx * 100).toFixed(2)}% · 세로 ${(dy * 100).toFixed(2)}% 어긋남`);

  // 반대로 '꽉 차지 않은' 상태에서는 가운데 정렬이 유지되는지도 확인(의도된 동작)
  await page.evaluate(() => resetZoom());
  await page.waitForTimeout(120);
  const centered = await page.evaluate(() => {
    const r = document.getElementById('lb-img').getBoundingClientRect();
    const s = document.getElementById('lb-stage').getBoundingClientRect();
    return Math.abs((r.left - s.left) - (s.right - r.right)) < 2;
  });
  check(centered, '(참고) 사진이 창보다 좁을 땐 가운데 정렬을 지킨다 — 의도된 동작');

  console.log('\n[한계]');
  await page.evaluate(() => resetZoom());
  for (let i = 0; i < 5; i++) await page.mouse.wheel(0, 200);   // 계속 축소
  await page.waitForTimeout(150);
  check(await zoom(page) === 1, '원래 크기보다 작아지지 않는다', `${(await zoom(page)).toFixed(3)}배`);

  for (let i = 0; i < 40; i++) await page.mouse.wheel(0, -200); // 계속 확대
  await page.waitForTimeout(250);
  const zmax = await zoom(page);
  const limit = await page.evaluate(() => maxZoom());
  check(Math.abs(zmax - limit) < 0.01, '정해진 최대 배율에서 멈춘다',
        `${zmax.toFixed(2)}배 = 한계 ${limit.toFixed(2)}배`);

  console.log('\n[트랙패드처럼 잘게 굴릴 때]');
  await page.evaluate(() => resetZoom());
  await page.mouse.move(600, 450);
  const steps = [];
  for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, -8); steps.push(await zoom(page)); }
  await page.waitForTimeout(100);
  const smooth = steps.every((v, i) => i === 0 || v >= steps[i - 1]) && steps[steps.length - 1] < 1.3;
  check(smooth, '조금씩 부드럽게 커진다(확 튀지 않음)',
        steps.map(v => v.toFixed(3)).join(' → '));

  console.log('\n[형광펜 모드에서도]');
  await page.evaluate(() => resetZoom());
  await page.click('#lb-pen');
  await page.mouse.move(600, 450);
  await page.mouse.wheel(0, -100);
  await page.waitForTimeout(150);
  check(await zoom(page) > 1.1, '형광펜을 켜도 휠 확대가 된다', `${(await zoom(page)).toFixed(3)}배`);
  const same = await page.evaluate(() => {
    const c = document.getElementById('lb-mark'), i = document.getElementById('lb-img');
    return c.style.width === i.style.width && c.style.transform === i.style.transform;
  });
  check(same, '형광펜판이 확대된 사진과 계속 겹쳐 있다');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
