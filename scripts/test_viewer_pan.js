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
 *   ⑧ ✋ 손바닥 버튼(2026-10-01): 켜면 **왼쪽 버튼**으로 끌어 옮긴다 — 형광펜이 켜져 있어도 줄 대신 이동,
 *      1배에서도 옮겨지고 가장자리를 화면 40% 까지 넘어 구석 기사를 가운데로 · 장 넘김·닫기 안 함 ·
 *      색·도구·🖍 를 고르면 손바닥이 꺼져 바로 긋기 · M 키 · 끄면 정상 범위로 돌아옴 · 폰 상단 바 안 넘침
 *   ⑪ 2026-10-19: 뷰어 안 어디서든 우클릭 메뉴·dragstart 차단(document capture, 닫으면 정리) · 1배에서도 오른쪽 드래그 이동 · 왼쪽 긋기·지우개·휠·Esc 그대로
 *   ⑩ 2026-10-16: ✋ 로 옮겨 둔 뒤 🖍·색·도구를 눌러도 사진이 제자리로 안 돌아감(그 자리에서 바로 긋기), ✋ 버튼으로 직접 끌 때만 가운데로
 *   ⑨ **PC 에선 뷰어를 열면 ✋ 가 기본으로 켜져 있다**(폰은 꺼짐 — 쓸어서 장 넘기기) · 손바닥이어도 두 번 눌러 확대·바깥 눌러 닫기
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

  console.log('\n[✋ 손바닥: 왼쪽 버튼으로 옮기기]');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');   // 닫았다가
  await openViewer(page); await page.waitForTimeout(250);
  const drag = async (dx, dy) => {
    await page.mouse.move(600, 450); await page.mouse.down();
    await page.mouse.move(600 + dx, 450 + dy, { steps: 8 }); await page.mouse.up(); await page.waitForTimeout(150);
  };
  check(await page.isVisible('#lb-hand'), '상단에 ✋ 버튼이 있다');
  const h0 = await pos(page);
  // 2026-10-01: PC 에선 뷰어를 열면 처음부터 ✋ 손바닥(사용자 요청)
  check(await page.evaluate(() => V.hand && document.getElementById('lb-hand').getAttribute('aria-pressed') === 'true'
        && getComputedStyle(document.getElementById('lb-img')).cursor === 'grab'), 'PC: 열자마자 ✋ 손바닥이 켜져 있다(버튼 눌림 · 손 모양 커서)');
  // 손바닥이어도 '톡' 누르기는 클릭: 두 번 누르면 확대, 사진 바깥을 누르면 닫기
  await page.mouse.dblclick(600, 450); await page.waitForTimeout(250);
  check((await pos(page)).z > 1.2, '손바닥이어도 두 번 누르면 확대된다', `배율 ${(await pos(page)).z}`);
  await page.mouse.dblclick(600, 450); await page.waitForTimeout(250);
  const gx = await page.evaluate(() => document.getElementById('lb-img').getBoundingClientRect().left / 2);
  await page.mouse.click(gx, 450); await page.waitForTimeout(150);
  check(await page.evaluate(() => document.getElementById('lb').hidden), '손바닥이어도 사진 바깥을 누르면 닫힌다');
  await openViewer(page); await page.waitForTimeout(250);
  check(await page.evaluate(() => V.hand), '다시 열어도 ✋ 로 시작');
  await drag(-200, -120);
  const h1 = await pos(page);
  check(h1.tx < h0.tx - 150 && h1.ty < h0.ty - 80 && h1.z === 1, '1배에서도 왼쪽 버튼으로 끌면 옮겨진다', `(${h0.tx},${h0.ty}) → (${h1.tx},${h1.ty})`);
  check(h1.i === h0.i && await page.evaluate(() => !document.getElementById('lb').hidden), '끌어도 장이 안 넘어가고 뷰어도 안 닫힌다');
  await zoomIn(page);
  for (let k = 0; k < 6; k++) await drag(400, 300);
  const far = await page.evaluate(() => ({ tx: V.tx, ty: V.ty, sw: V.stage.w, sh: V.stage.h }));
  check(far.tx > 50 && far.tx <= far.sw * 0.4 + 1 && far.ty <= far.sh * 0.4 + 1,
        '확대해도 가장자리를 넘어(화면의 40%까지) 구석 기사를 가운데로 끌어올 수 있다', `tx=${Math.round(far.tx)} (한계 ${Math.round(far.sw * 0.4)})`);
  await page.click('#lb-pen'); await page.waitForTimeout(150);
  check(await page.evaluate(() => M.on && !V.hand), '🖍 를 켜면 손바닥은 꺼진다(바로 긋기)');
  check(!(await page.isVisible('#lb-hand')) && await page.isVisible('#lb-t-hand'), '형광펜 중엔 ✋ 가 상단이 아니라 편집 도구모음 안에 있다(2026-10-16)');
  await page.click('#lb-t-hand');
  check(await page.evaluate(() => V.hand && !['lb-t-line','lb-t-oval','lb-t-free'].some(id => document.getElementById(id).getAttribute('aria-pressed') === 'true')),
        '도구모음 ✋ 를 켜면 직선·동그라미·자유 표시는 꺼진다(하나만 고르기)');
  const before = await pos(page);
  await drag(-150, 0);
  const lines = await page.evaluate(() => (M.marks[markName()] || []).length);
  check(lines === 0 && (await pos(page)).tx < before.tx, '형광펜이 켜져 있어도 손바닥이면 줄 대신 옮긴다');
  await page.click('#lb-c2');
  check(await page.evaluate(() => !V.hand), '색을 고르면 손바닥이 꺼진다');
  await drag(-150, 0);
  check(await page.evaluate(() => (M.marks[markName()] || []).length) === 1, '그다음 왼쪽 드래그는 다시 줄 긋기');
  await page.click('#lb-t-hand'); await page.click('#lb-erase');
  check(await page.evaluate(() => !V.hand), '지우개를 고르면 손바닥이 꺼진다');
  await page.click('#lb-pen-off');
  await page.keyboard.press('m');
  check(await page.evaluate(() => V.hand), 'M 키로 손바닥 켜기');
  await page.keyboard.press('m');
  const hb = await page.evaluate(() => ({ tx: V.tx, w: V.fitW * V.zoom, sw: V.stage.w }));
  check(!await page.evaluate(() => V.hand) && hb.tx <= 0.5 && hb.tx >= hb.sw - hb.w - 0.5, '끄면 사진이 정상 범위 안으로 돌아온다');

  // 2026-10-16 사용자 요청: 손바닥으로 옮겨 둔 뒤 🖍·색·도구를 눌러도 사진이 원래 자리로 돌아가지 않는다(그 자리에서 바로 긋기)
  console.log('\n[✋ 로 옮긴 자리 지키기 → 🖍 로 바로 긋기]');
  await page.evaluate(() => resetZoom()); await page.waitForTimeout(100);
  await page.keyboard.press('m');                       // 손바닥 켜기(1배)
  await drag(-300, -200); await page.waitForTimeout(100);
  const rect = () => page.evaluate(() => { const r = document.getElementById('lb-img').getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width) }; });
  const same = (a, b) => Math.abs(a.x - b.x) <= 2 && Math.abs(a.y - b.y) <= 2 && Math.abs(a.w - b.w) <= 2;
  const r0 = await rect();
  await page.click('#lb-pen'); await page.waitForTimeout(150);
  const r1 = await rect();
  check(await page.evaluate(() => M.on && !V.hand) && same(r0, r1), '🖍 를 눌러도 옮겨 둔 자리·크기 그대로', `(${r0.x},${r0.y},${r0.w}) → (${r1.x},${r1.y},${r1.w})`);
  await page.click('#lb-c1'); await page.click('#lb-t-oval'); await page.waitForTimeout(100);
  check(same(r0, await rect()), '색·도구를 골라도 그대로');
  const n0 = await page.evaluate(() => (M.marks[markName()] || []).length);
  await drag(-80, -40); await page.waitForTimeout(100);
  check(await page.evaluate(() => (M.marks[markName()] || []).length) === n0 + 1 && same(r0, await rect()), '그 자리에서 바로 그려지고 사진은 안 움직인다');
  await page.click('#lb-pen-off'); await page.waitForTimeout(150);
  check(same(r0, await rect()), '형광펜을 꺼도 그 자리 그대로');
  // 확대 + 형광펜 켜 둔 채 ✋ 로 옮기고 → 색을 고르면(사용자 화면 그대로) 그 자리 유지
  await page.click('#lb-pen'); await zoomIn(page, 3); await page.click('#lb-t-hand');
  await drag(250, 180); await page.waitForTimeout(100);
  const zr = await rect();
  await page.click('#lb-t-hand'); await page.waitForTimeout(100);
  check(await page.evaluate(() => !V.hand && document.getElementById('lb-t-' + M.tool).getAttribute('aria-pressed') === 'true') && same(zr, await rect()),
        '도구모음 ✋ 를 다시 누르면 긋기로 돌아오고(고르던 도구 표시) 자리는 그대로');
  await page.click('#lb-t-hand');
  await page.click('#lb-c2'); await page.waitForTimeout(100);
  check(await page.evaluate(() => !V.hand && V.zoom > 1.2) && same(zr, await rect()), "확대한 채 ✋ 로 옮긴 뒤 색을 골라도 그 자리 그대로", `(${zr.x},${zr.y},${zr.w})`);
  await page.click('#lb-pen-off'); await page.evaluate(() => resetZoom()); await page.waitForTimeout(100);
  await page.click('#lb-hand'); await page.click('#lb-hand'); await page.waitForTimeout(100);
  const rc = await page.evaluate(() => ({ tx: V.tx, c: (V.stage.w - V.fitW * V.zoom) / 2 }));
  check(Math.abs(rc.tx - rc.c) < 1, '✋ 버튼으로 직접 끄면 그때는 정상 자리(가운데)로', `tx=${Math.round(rc.tx)} 가운데=${Math.round(rc.c)}`);

  // 2026-10-19 사용자 요청: 뷰어 안 어디서든 우클릭 메뉴·이미지 끌어가기 차단(capture 단계) · 오른쪽 버튼은 1배에서도 이동 · 닫으면 정리
  console.log('\n[우클릭 메뉴·이미지 끌기 차단 / 1배 오른쪽 드래그]');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await openViewer(page); await page.waitForTimeout(250);
  await page.evaluate(() => { setHand(false); resetZoom(); }); await page.waitForTimeout(120);
  // 뒤늦게(버블 단계) 붙인 감시자로 '기본 동작이 막혔는지'만 기록 — 앱 핸들러가 capture 에서 먼저 막아야 true
  await page.evaluate(() => { window.__ctx = []; window.__drag = [];
    window.addEventListener('contextmenu', e => __ctx.push([e.target.id || e.target.className || e.target.tagName, e.defaultPrevented]));
    window.addEventListener('dragstart', e => __drag.push([e.target.id || e.target.tagName, e.defaultPrevented])); });
  const fire = (sel, type) => page.evaluate(([sel, type]) => {
    const el = document.querySelector(sel); return !el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 2 })); }, [sel, type]);
  check(await fire('#lb-img', 'contextmenu') && await fire('#lb-mark', 'contextmenu') && await fire('.lb-bar', 'contextmenu') && await fire('#lb-count', 'contextmenu'),
        '뷰어 안 어디서든(사진·그림판·위쪽 바) 우클릭 메뉴가 막힌다');
  check(await page.evaluate(() => { const r = document.getElementById('lb-img').getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return hit && hit.id === 'lb-stage'; }),
        '사진 위를 눌러도 브라우저는 사진(img)이 아니라 사진 칸을 누른 것으로 본다 → 크롬 "이미지" 메뉴가 생길 수 없다(2026-10-20)');
  check(await page.evaluate(() => { const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true }); return !window.dispatchEvent(e) && !document.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true })); }),
        '뷰어 밖(창·문서 자체)에서 끝난 우클릭도 뷰어가 열려 있으면 막는다');
  // 2026-10-21: 확장 프로그램이 페이지를 다 읽은 뒤 붙인 우클릭 감시자가 신호를 멈춰도(stopImmediatePropagation) 우리가 먼저 막는다
  //   실제 순서 재현: 페이지를 다 읽은 뒤(사진 창을 열기 **전**) 확장 프로그램이 감시자를 붙이고 → 사용자가 사진 창을 연다
  await page.evaluate(() => { closeViewer(); window.__ext = e => e.stopImmediatePropagation(); window.addEventListener('contextmenu', window.__ext, true); });
  await openViewer(page); await page.waitForTimeout(150);
  check(await page.evaluate(() => { const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true }); document.getElementById('lb-stage').dispatchEvent(ev);
      window.removeEventListener('contextmenu', window.__ext, true); return ev.defaultPrevented; }),
        '확장 프로그램이 우클릭 신호를 중간에서 멈춰도 메뉴가 막힌다(페이지 맨 앞 감시자)');
  check(await page.evaluate(() => document.getElementById('lb-img').draggable === false) && await fire('#lb-img', 'dragstart') && await fire('#lb-stage', 'dragstart'),
        '사진·사진 칸의 브라우저 기본 끌기(dragstart)가 막힌다');
  // 실제 마우스: 사진 위에서 오른쪽 버튼을 누르고 위쪽 바까지 끌고 가서 떼기(윈도 크롬은 뗄 때 메뉴를 띄운다)
  const q0 = await pos(page);
  await page.evaluate(() => { __ctx.length = 0; });
  await page.mouse.move(640, 500); await page.mouse.down({ button: 'right' });
  await page.mouse.move(560, 430, { steps: 6 });
  const q1 = await pos(page);
  await page.mouse.move(560, 20, { steps: 6 }); await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(150);
  const ctx = await page.evaluate(() => __ctx);
  check(q1.z === 1 && q1.tx < q0.tx - 40 && q1.ty < q0.ty - 40, '1배(확대 안 함)에서도 오른쪽 버튼으로 끌면 지면이 움직인다', `(${q0.tx},${q0.ty}) → (${q1.tx},${q1.ty})`);
  check(ctx.length > 0 && ctx.every(c => c[1]), '실제 오른쪽 클릭·드래그에서 생긴 메뉴 신호가 모두 막혔다', JSON.stringify(ctx));
  check(q1.i === 0 && await page.evaluate(() => !document.getElementById('lb').hidden), '장이 안 넘어가고 뷰어도 안 닫힌다');
  // 왼쪽 버튼 기능은 그대로: 형광펜 긋기 · 지우개 · 휠 확대 · Esc
  await page.click('#lb-pen'); await page.waitForTimeout(150);
  const L0 = await page.evaluate(() => (M.marks[markName()] || []).length);
  await page.mouse.move(600, 600); await page.mouse.down({ button: 'right' }); await page.mouse.move(640, 620, { steps: 4 }); await page.mouse.up({ button: 'right' });
  check(await page.evaluate(() => (M.marks[markName()] || []).length) === L0, '형광펜 중 1배 오른쪽 드래그도 줄을 긋지 않는다(이동만)');
  await page.mouse.move(560, 520); await page.mouse.down(); await page.mouse.move(700, 520, { steps: 6 }); await page.mouse.up();
  check(await page.evaluate(() => (M.marks[markName()] || []).length) === L0 + 1, '왼쪽 버튼 긋기는 그대로 된다');
  await page.click('#lb-erase'); await page.mouse.click(630, 520);
  check(await page.evaluate(() => (M.marks[markName()] || []).length) === L0, '지우개도 그대로 된다');
  await page.click('#lb-erase');
  const zb = (await pos(page)).z; await page.mouse.move(640, 450); await page.mouse.wheel(0, -400); await page.waitForTimeout(250);
  check((await pos(page)).z > zb, '마우스 휠 확대도 그대로 된다', `${zb} → ${(await pos(page)).z}`);
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  check(await page.evaluate(() => document.getElementById('lb').hidden), 'Esc 로 (형광펜 끄고) 닫힌다');
  // 닫은 뒤엔 막기를 뗀다 → 페이지의 우클릭·끌기는 원래대로
  check(await page.evaluate(() => V.guards === false) && !(await fire('body', 'contextmenu')) && !(await fire('body', 'dragstart')),
        '뷰어를 닫으면 막기 리스너를 정리한다(페이지 우클릭·끌기는 원래대로)');

  // 2026-10-21: 확장 프로그램이 페이지보다 먼저(document_start) 우클릭을 가로채면 페이지 코드로는 못 막는다 → 화면에 알림
  console.log('\n[확장 프로그램 우클릭 가로채기 알림]');
  check(await page.evaluate(() => { openViewer(0); return document.getElementById('lb-warn').hidden; }), '확장 프로그램이 없으면 알림이 안 뜬다');
  const ectx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ectx.addInitScript(() => window.addEventListener('contextmenu', e => e.stopImmediatePropagation(), true));
  const ep = await ectx.newPage(); await ep.goto(base + '/slack'); await openViewer(ep); await ep.waitForTimeout(150);
  check(await ep.evaluate(() => !document.getElementById('lb-warn').hidden && /손바닥/.test(document.getElementById('lb-warn').textContent)),
        '확장 프로그램이 먼저 가로채면 "✋ 손바닥을 쓰세요" 알림이 뜬다');
  await ep.click('#lb-warn-x');
  check(await ep.evaluate(() => document.getElementById('lb-warn').hidden), '✕ 로 알림을 닫을 수 있다');
  await ectx.close();

  // 2026-10-21: '우클릭 허용' 류 확장이 preventDefault 를 아무것도 안 하는 가짜로 바꿔치기해도 진짜 함수로 취소
  console.log('\n[preventDefault 바꿔치기 확장 · 점검 칸]');
  const pctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await pctx.addInitScript(() => { const o = Event.prototype.preventDefault;
    Event.prototype.preventDefault = function () { if (this.type === 'contextmenu') return; return o.call(this); }; });
  const pp = await pctx.newPage(); await pp.goto(base + '/slack?diag=1'); await openViewer(pp); await pp.waitForTimeout(150);
  await pp.evaluate(() => { window.__fin = []; window.addEventListener('contextmenu', e => __fin.push(e.defaultPrevented), false); });
  await pp.mouse.move(640, 450); await pp.mouse.down({ button: 'right' }); await pp.mouse.move(600, 420, { steps: 3 }); await pp.mouse.up({ button: 'right' });
  await pp.waitForTimeout(150);
  const fin = await pp.evaluate(() => __fin);
  check(fin.length > 0 && fin.every(Boolean), 'preventDefault 를 바꿔치기한 확장이 있어도 실제 우클릭이 취소된다(진짜 함수 사용)', JSON.stringify(fin));
  const diag = await pp.evaluate(() => (document.getElementById('ctx-diag') || {}).textContent || '');
  check(/바꿔치기: 있음/.test(diag) && /맨앞감시자:받음  막힘:예  사진창:열림/.test(diag), '?diag=1 점검 칸이 바꿔치기·받음·막힘을 보여 준다', diag.split('\n').pop());
  await pctx.close();
  check(await page.evaluate(() => !document.getElementById('ctx-diag')), '?diag=1 이 없으면 점검 칸은 안 나온다');

  const ph = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true });
  await ph.goto(base + '/slack');
  await openViewer(ph);
  const over = await ph.evaluate(() => document.querySelector('.lb-bar').scrollWidth - document.querySelector('.lb-bar').clientWidth);
  check(over <= 0 && await ph.isVisible('#lb-hand'), '폰(390px): ✋ 버튼이 상단 바에 들어간다', `넘침 ${over}px`);
  check(await ph.evaluate(() => !V.hand), '폰(손가락)에선 ✋ 가 꺼진 채로 열린다(쓸어서 장 넘기기 유지)');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
