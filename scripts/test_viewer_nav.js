/**
 * test_viewer_nav.js — 신문 사진 뷰어의 '넘김 화살표' 동작 확인 (실제 Chromium)
 *
 * 확인하는 것
 *   ① 1초 동안 가만히 두면 화살표가 사라진다 (신문 글씨를 가리지 않게)
 *   ② 마우스를 움직이거나 화면을 건드리면 다시 나온다
 *   ③ 사라진 동안엔 눌리지 않는다(pointer-events:none)
 *   ④ 사진 옆에 여백이 있으면 화살표가 '사진 바깥'에 놓인다 → 아예 안 겹친다
 *   ⑤ 장 넘기기는 그대로 동작한다
 *
 * 실행 (playwright 가 있는 개발 환경에서만 — 서버엔 없어도 된다):
 *   npm i playwright && node scripts/test_viewer_nav.js
 * 브라우저 경로는 PW_CHROME 환경변수로 바꿀 수 있다.
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');

const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

/** 신문 지면 비율(세로로 긴)의 가짜 PNG 를 즉석에서 만든다 — 별도 파일이 필요 없게. */
function makePng(w, h) {
  const chunk = (type, data) => {
    const tc = Buffer.concat([Buffer.from(type), data]);
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(zlib.crc32 ? zlib.crc32(tc) >>> 0 : crc32(tc));
    return Buffer.concat([len, tc, crc]);
  };
  function crc32(buf) {                       // node 18 등 zlib.crc32 가 없는 경우 대비
    let c, crc = 0xffffffff;
    for (let n = 0; n < buf.length; n++) {
      c = (crc ^ buf[n]) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crc = c ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 2;                   // 8bit truecolor
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 220)]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
                        chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)),
                        chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(800, 1200);

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (type, body) => { res.writeHead(200, { 'Content-Type': type }); res.end(body); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-17', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-17' }));
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

/** 썸네일 UI 를 거치지 않고 뷰어만 직접 연다(테스트 대상은 화살표 동작이므로). */
const openViewer = (page) => page.evaluate(() => {
  newsState.images = [0, 1, 2].map(() => ({ url: '/page.png', download_url: '/page.png' }));
  openViewer(0);
  return new Promise(r => {
    const im = document.getElementById('lb-img');
    (im.complete && im.naturalWidth) ? r() : im.addEventListener('load', () => r(), { once: true });
  });
});

const navState = (page) => page.evaluate(() => {
  const p = document.getElementById('lb-prev'), n = document.getElementById('lb-next');
  const img = document.getElementById('lb-img').getBoundingClientRect();
  const pr = p.getBoundingClientRect();
  return {
    idle: p.classList.contains('idle') && n.classList.contains('idle'),
    // ⚠️ 첫 장에서는 '이전'이 비활성(opacity .25)이라 보임 판정 기준이 못 된다 → '다음'으로 잰다
    opacity: +getComputedStyle(n).opacity,
    left: p.style.left,
    overlapsImage: pr.right > img.left + 0.5,
    imgLeft: Math.round(img.left), navRight: Math.round(pr.right),
  };
});

const FADE = 400;   // CSS 페이드 0.3초 + 여유

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  console.log('\n[PC 1280x800 — 사진 옆에 여백이 있는 경우]');
  let page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(base + '/slack');
  await openViewer(page);
  await page.waitForTimeout(FADE);

  let s = await navState(page);
  check(!s.idle && s.opacity > 0.9, '열자마자 화살표가 보인다', `opacity=${s.opacity}`);
  check(!s.overlapsImage, '화살표가 사진(신문)을 안 가린다',
        `화살표 우측 ${s.navRight}px < 사진 좌측 ${s.imgLeft}px, left=${s.left}`);

  await page.waitForTimeout(1300);
  s = await navState(page);
  check(s.idle && s.opacity < 0.05, '1초 뒤 화살표가 사라진다', `opacity=${s.opacity}`);

  await page.mouse.move(640, 400);
  await page.waitForTimeout(FADE);
  s = await navState(page);
  check(!s.idle && s.opacity > 0.9, '마우스를 움직이면 다시 나온다', `opacity=${s.opacity}`);

  await page.waitForTimeout(1300);
  const pe = await page.evaluate(() => getComputedStyle(document.getElementById('lb-prev')).pointerEvents);
  check(pe === 'none', '사라진 동안엔 눌리지 않는다', `pointer-events=${pe}`);
  await page.close();

  console.log('\n[휴대폰 390x780 — 사진이 화면을 거의 채우는 경우]');
  page = await browser.newPage({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true });
  await page.goto(base + '/slack');
  await openViewer(page);
  await page.waitForTimeout(FADE);
  s = await navState(page);
  check(!s.idle, '열자마자 보인다');
  check(s.overlapsImage, '(참고) 폰에선 사진이 꽉 차 화살표가 겹친다 → 자동숨김이 필요한 이유');

  await page.waitForTimeout(1300);
  s = await navState(page);
  check(s.idle && s.opacity < 0.05, '1초 뒤 사라진다 → 지면을 안 가린다', `opacity=${s.opacity}`);

  await page.touchscreen.tap(195, 400);
  await page.waitForTimeout(FADE);
  s = await navState(page);
  check(!s.idle, '화면을 건드리면 다시 나온다');

  const before = await page.evaluate(() => V.i);
  await page.evaluate(() => go(1));
  const after = await page.evaluate(() => V.i);
  check(after === before + 1, '장 넘기기는 그대로 동작한다', `${before} → ${after}`);
  check(!(await navState(page)).idle, '넘기면 화살표가 다시 보인다');

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
