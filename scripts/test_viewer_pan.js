/**
 * test_viewer_pan.js — 확대한 신문 사진 '옮기기' 확인 (실제 Chromium)
 *
 * 확인하는 것
 *   ① 확대한 뒤 **방향키**로 상하좌우 이동
 *   ② 확대한 뒤 **마우스 오른쪽 버튼 드래그**로 이동 (형광펜 모드에서도)
 *   ③ 오른쪽 버튼 드래그가 **장을 넘기거나 뷰어를 닫지 않는다**
 *   ④ 원래 크기(1배)에서는 방향키가 **기존대로 장 넘기기**로 동작
 *   ⑤ 확대한 상태에서도 Shift+←/→ · PageUp/Down 으로 장을 넘길 수 있다
 *   ⑥ 사진 경계 밖으로는 안 나간다
 *   ⑦ 오른쪽 클릭 시 브라우저 메뉴가 안 뜬다(안 막으면 끌 수가 없다)
 *
 * 실행: node scripts/test_viewer_pan.js
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
const PNG = makePng(1600, 2400);

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-18', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-18' }));
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

const openViewer = (page) => page.evaluate(() => {
  newsState.images = ['01.jpg', '02.jpg', '03.jpg'].map(n =>
    ({ name: n, url: '/page.png', download_url: '/page.png' }));
  openViewer(0);
  return new Promise(r => { const im = document.getElementById('lb-img');
    (im.complete && im.naturalWidth) ? r() : im.addEventListener('load', () => r(), { once: true }); });
});

const pos = (page) => page.evaluate(() => ({ tx: Math.round(V.tx), ty: Math.round(V.ty), z: +V.zoom.toFixed(3), i: V.i }));
const zoomIn = async (page, n = 5) => {
  await page.mouse.move(600, 450);
  for (let k = 0; k < n; k++) await page.mouse.wheel(0, -100);
  await page.waitForTimeout(220);
};

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

  console.log('\n[원래 크기에서는 기존대로 장 넘기기]');
  let a = await pos(page);
  check(a.z === 1 && a.i === 0, '1배, 1쪽에서 시작');
  await page.keyboard.press('ArrowRight'); await page.waitForTimeout(150);
  check((await pos(page)).i === 1, '방향키 →  가 다음 장으로 넘어간다');
  await page.keyboard.press('ArrowLeft'); await page.waitForTimeout(150);
  check((await pos(page)).i === 0, '방향키 ←  가 이전 장으로 돌아온다');

  console.log('\n[확대한 뒤 방향키로 이동]');
  await zoomIn(page);
  const z0 = await pos(page);
  check(z0.z > 2, '충분히 확대됨', `${z0.z}배`);
  await page.keyboard.press('ArrowRight'); await page.waitForTimeout(150);
  const right = await pos(page);
  check(right.tx < z0.tx && right.i === z0.i, '→ 로 오른쪽을 본다(장은 안 넘어감)',
        `tx ${z0.tx} → ${right.tx}`);
  await page.keyboard.press('ArrowDown'); await page.waitForTimeout(150);
  const down = await pos(page);
  check(down.ty < right.ty, '↓ 로 아래를 본다', `ty ${right.ty} → ${down.ty}`);
  await page.keyboard.press('ArrowUp'); await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(200);
  const back = await pos(page);
  check(back.tx > down.tx && back.ty > down.ty, '↑ ← 로 되돌아온다');

  console.log('\n[확대한 상태에서도 장을 넘기는 길]');
  await page.keyboard.press('Shift+ArrowRight'); await page.waitForTimeout(150);
  check((await pos(page)).i === 1, 'Shift+→ 로 다음 장', `${(await pos(page)).i + 1}쪽`);
  await page.keyboard.press('PageUp'); await page.waitForTimeout(150);
  check((await pos(page)).i === 0, 'PageUp 으로 이전 장');

  console.log('\n[마우스 오른쪽 버튼으로 끌어 옮기기]');
  await zoomIn(page);
  const p0 = await pos(page);
  await page.mouse.move(600, 450);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(450, 350, { steps: 6 });
  await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(180);
  const p1 = await pos(page);
  check(p1.tx < p0.tx && p1.ty < p0.ty, '오른쪽 버튼으로 끌면 화면이 따라 움직인다',
        `(${p0.tx},${p0.ty}) → (${p1.tx},${p1.ty})`);
  check(p1.i === p0.i, '끌어도 장이 안 넘어간다', `${p1.i + 1}쪽 그대로`);
  check(await page.evaluate(() => !document.getElementById('lb').hidden), '뷰어가 안 닫힌다');

  console.log('\n[형광펜 모드에서도 오른쪽 드래그로 이동]');
  await page.click('#lb-pen'); await page.waitForTimeout(200);
  const m0 = await pos(page);
  await page.mouse.move(600, 450);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(520, 400, { steps: 5 });
  await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(180);
  const m1 = await pos(page);
  check(m1.tx !== m0.tx || m1.ty !== m0.ty, '형광펜을 켜도 오른쪽 드래그는 이동이다',
        `(${m0.tx},${m0.ty}) → (${m1.tx},${m1.ty})`);
  const drawn = await page.evaluate(() => (M.marks[markName()] || []).length);
  check(drawn === 0, '오른쪽 드래그로는 줄이 그어지지 않는다', `${drawn}줄`);
  await page.click('#lb-pen-off'); await page.waitForTimeout(150);

  console.log('\n[경계 · 오른쪽 메뉴]');
  for (let k = 0; k < 30; k++) await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(250);
  const edge = await page.evaluate(() => ({ tx: Math.round(V.tx), max: 0 }));
  check(edge.tx <= 0.5, '왼쪽 끝을 넘어가지 않는다', `tx=${edge.tx} (0 이하)`);

  const menuShown = await page.evaluate(() => new Promise(r => {
    const st = document.getElementById('lb-stage');
    const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    const prevented = !st.dispatchEvent(ev);
    r(prevented);
  }));
  check(menuShown, '사진 위에서 오른쪽 클릭 메뉴가 안 뜬다(끌 수 있게)');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
