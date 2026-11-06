/**
 * test_viewer_artnav.js — 신문 사진 뷰어 **폰용 '◀ 이전 / 다음 ▶ 기사' 이동 줄** 확인 (실제 Chromium) — 2026-11-06 사용자 요청
 *   ① 기사에서 사진을 열면 맨 아래에 기사 이동 줄(1/3 + 제목)이 생기고, 첫 기사에선 ◀ 가 꺼짐
 *   ② 다음 ▶ : 창을 닫지 않고 다음 기사로 — 같은 장이면 장 그대로(요약 칸·표시만 바뀜), 다른 장이면 그 장으로
 *   ③ 마지막 기사에선 ▶ 가 꺼짐 · ◀ 로 되돌아옴 · 사진 칸을 가리지 않음(줄이 사진 위에 얹히지 않음·책갈피/용어 버튼과 안 겹침)
 *   ④ 닫으면 피드가 지금 보던 기사 자리로 이동 · PC(넓은 화면)에선 줄이 안 보임
 * 실행: node scripts/test_viewer_artnav.js   (개발 환경 전용)
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
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(800, 1200);
const art = (n, t, p) => [`${n}. ${t}`, `• WHAT: ${t} 내용임.`, '• WHY: 이유임.', '• HOW: 방법임.', `• 사진: ${p}`].join('\n');
const BRIEF = ['*[신문요약 1/1] 신문 요약*', art(1, '첫째 기사 반도체 수출 급증', '03'), art(2, '둘째 기사 부동산 대출 규제', '03'), art(3, '셋째 기사 환율 변동성 확대', '05')].join('\n');
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-11-06';
  const send = (t, b, code = 200) => { res.writeHead(code, { 'Content-Type': t }); res.end(b); };
  const json = (o, code = 200) => send('application/json', JSON.stringify(o), code);
  if (u === '/' || u === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/economy/data') return json({ date: D, messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] });
  if (u === '/api/news/today') {
    const images = Array.from({ length: 6 }, (_, i) => {
      const n = String(i + 1).padStart(2, '0') + '.jpg';
      return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' };
    });
    return json({ ok: true, ready: true, date: D, count: 6, images });
  }
  if (u === '/api/news/terms') return json({ ok: false }, 403);
  if (u === '/api/news/pagetext') return json({ ok: false });
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const st = (page) => page.evaluate(() => ({
    hidden: document.getElementById('lb-artnav').hidden,
    shown: getComputedStyle(document.getElementById('lb-artnav')).display !== 'none',
    mid: document.getElementById('lb-amid').textContent,
    prevOff: document.getElementById('lb-aprev').disabled, nextOff: document.getElementById('lb-anext').disabled,
    count: document.getElementById('lb-count').textContent.replace(/\s+/g, ''),
    open: !document.getElementById('lb').hidden,
  }));
  const openNth = async (page, n) => {
    await page.waitForFunction(() => document.querySelectorAll('.brf-side [data-act="pen"]').length >= 3);
    await page.evaluate((k) => document.querySelectorAll('.brf-side [data-act="pen"]')[k].click(), n);
    await page.waitForFunction(() => !document.getElementById('lb').hidden && document.getElementById('lb-img').naturalWidth > 0);
    await page.waitForTimeout(200);
  };

  console.log('\n[폰 390px]');
  let ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });
  let page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/economy');
  await openNth(page, 0);
  let s = await st(page);
  check(s.shown && s.mid.startsWith('1/3') && s.mid.includes('첫째 기사'), '① 기사 이동 줄 표시 · 1/3 + 제목', s.mid);
  check(s.prevOff && !s.nextOff, '   첫 기사: ◀ 꺼짐 · ▶ 켜짐');
  check(s.count.startsWith('03/'), '   03번째 장', s.count);
  const geo = await page.evaluate(() => { const a = document.getElementById('lb-artnav').getBoundingClientRect(), b = document.getElementById('lb-stage').getBoundingClientRect(); const ra = document.getElementById('reader-actions').getBoundingClientRect(); return { aTop: a.top, aBottom: a.bottom, sBottom: b.bottom, w: a.width, vw: innerWidth, vh: innerHeight, raBottom: ra.bottom, raVisible: ra.width > 0 }; });
  check(geo.aTop >= geo.sBottom - 0.5 && geo.w <= geo.vw, '   줄이 사진 칸 아래(맨 아래)에 있고 화면 폭을 안 넘음', JSON.stringify(geo));
  check(geo.vh - geo.aBottom < 12, '   화면 맨 아래에 붙어 있음(엄지 닿는 곳)');
  check(!geo.raVisible || geo.raBottom <= geo.aTop + 0.5, '   책갈피·용어 버튼이 이동 줄을 가리지 않음(한 줄 위로 올라감)');

  await page.tap('#lb-anext'); await page.waitForTimeout(250);
  s = await st(page);
  check(s.open && s.mid.startsWith('2/3') && s.mid.includes('둘째 기사'), '② ▶ : 닫지 않고 2/3 기사로', s.mid);
  check(s.count.startsWith('03/') && !s.prevOff && !s.nextOff, '   같은 장이라 장 그대로(03)');
  check(await page.$eval('#lb-img', i => i.style.visibility !== 'hidden'), '   사진이 계속 보임(깜빡임으로 숨은 채 아님)');

  await page.tap('#lb-anext'); await page.waitForTimeout(400);
  s = await st(page);
  check(s.mid.startsWith('3/3') && s.count.startsWith('05/'), '   ▶ : 다른 장(05)의 3/3 기사', s.mid + ' ' + s.count);
  check(s.nextOff && !s.prevOff, '③ 마지막 기사: ▶ 꺼짐 · ◀ 켜짐');
  check(await page.$eval('#lb-img', i => i.style.visibility !== 'hidden'), '   사진 보임');

  await page.tap('#lb-aprev'); await page.waitForTimeout(400);
  s = await st(page);
  check(s.mid.startsWith('2/3') && s.count.startsWith('03/'), '   ◀ : 되돌아 2/3 · 03장', s.mid + ' ' + s.count);

  await page.tap('#lb-close'); await page.waitForTimeout(300);
  s = await st(page);
  check(!s.open && s.hidden, '④ 닫으면 이동 줄도 숨음');
  const vis = await page.evaluate(() => { const a = [...document.querySelectorAll('#feed .brf-art')][1]; const r = a.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; });
  check(vis, '   피드가 지금 보던(둘째) 기사 자리로 이동');
  await ctx.close();

  console.log('\n[장 목록(썸네일)에서 연 경우·PC]');
  ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/economy');
  await openNth(page, 0);
  s = await st(page);
  check(!s.shown, 'PC(900px↑)에선 이동 줄이 안 보임(옆 요약 칸 사용)');
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
