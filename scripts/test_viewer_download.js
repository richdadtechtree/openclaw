/**
 * test_viewer_download.js — 신문 사진 뷰어 '⤓ 저장' 확인 (실제 Chromium) — 2026-10-16 사용자 요청
 *   "줄 그은 뒤 PDF 로 전체 다운로드하거나 낱장 그림파일로도 받을 수 있도록"
 *
 * 확인하는 것
 *   ① ⤓ 를 누르면 메뉴(이 장 그림 · 전체 PDF · 줄 그은 장만 PDF · 원본)가 열리고 Esc·바깥 누르기로 닫힌다
 *   ② 이 장 그림(JPG): 그은 줄이 그림에 들어가 있다(줄 자리 색이 바뀜, 줄 없는 자리는 그대로)
 *   ③ 전체 PDF: 장 수만큼 쪽 · PDF 구조(xref 위치)가 맞다 · 안의 그림을 실제로 열 수 있고 줄 그은 장에만 줄
 *   ④ 줄 그은 장만 PDF: 1쪽 · 줄이 없으면 버튼이 꺼져 있다
 *   ⑤ 만들 때 서버로 보내는 요청 없음(사진 읽기 GET 만)
 * 실행: npm i playwright && node scripts/test_viewer_download.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');

const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

function makePng(w, h) {                       // 연회색 세로 지면 PNG
  const crc32 = (buf) => { let c, crc = 0xffffffff; for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = c ^ (crc >>> 8); } return (crc ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const tc = Buffer.concat([Buffer.from(type), data]);
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(tc));
    return Buffer.concat([len, tc, crc]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 230)]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: h }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(800, 1200);
const calls = [];
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  if (u !== '/slack') calls.push(req.method + ' ' + u);
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-10-16', messages: [] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-10-16' }));
  if (u.startsWith('/p')) return send('image/png', PNG);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  await page.goto(base + '/slack?hand=0');
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    state.date = '2026-10-16';
    newsState.images = ['01.jpg', '02.jpg', '03.jpg'].map((n, i) => ({ name: n, url: '/p' + i + '.png', download_url: '/p' + i + '.png' }));
    openViewer(0);
  });
  await page.waitForFunction(() => { const im = document.getElementById('lb-img'); return im.complete && im.naturalWidth && V.fitW > 0; });

  console.log('\n[① 메뉴]');
  await page.click('#lb-dl');
  check(await page.isVisible('#lb-dlmenu') && await page.isVisible('#lb-dl-pdf') && await page.isVisible('#lb-dl-img'), '⤓ 를 누르면 저장 메뉴가 열린다');
  check(await page.isDisabled('#lb-dl-pdfm'), '줄을 안 그었으면 "줄 그은 장만 PDF" 는 꺼져 있다');
  await page.keyboard.press('Escape');
  check(!(await page.isVisible('#lb-dlmenu')) && await page.isVisible('#lb'), 'Esc 는 메뉴만 닫는다(뷰어는 그대로)');

  // 2번째 장(02.jpg)에 빨간 가로줄 긋기: 높이 30% 자리
  await page.evaluate(() => go(1));
  await page.waitForFunction(() => { const im = document.getElementById('lb-img'); return im.complete && im.naturalWidth && V.fitW > 0 && V.i === 1; });
  await page.click('#lb-pen'); await page.click('#lb-c1'); await page.waitForTimeout(150);
  const r = await page.evaluate(() => { const b = document.getElementById('lb-img').getBoundingClientRect(); return { l: b.left, t: b.top, w: b.width, h: b.height }; });
  await page.mouse.move(r.l + r.w * 0.2, r.t + r.h * 0.3); await page.mouse.down();
  for (let k = 1; k <= 8; k++) await page.mouse.move(r.l + r.w * (0.2 + 0.6 * k / 8), r.t + r.h * 0.3);
  await page.mouse.up();
  check(await page.evaluate(() => (M.marks['02.jpg'] || []).length) === 1, '(준비) 2번째 장에 줄 1개');
  const before = calls.length;

  // 그림(JPG/PDF 속 JPG)을 브라우저에서 열어 줄 자리·빈 자리 색을 잰다
  const probe = (b64, mime) => page.evaluate(async ([b64, mime]) => {
    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bin], { type: mime }));
    const cv = new OffscreenCanvas(bmp.width, bmp.height), c = cv.getContext('2d'); c.drawImage(bmp, 0, 0);
    const px = (x, y) => [...c.getImageData(Math.round(bmp.width * x), Math.round(bmp.height * y), 1, 1).data].slice(0, 3);
    return { w: bmp.width, h: bmp.height, line: px(0.5, 0.3), blank: px(0.5, 0.7) };
  }, [b64, mime]);
  const reddish = p => p[0] > 200 && p[1] < 190 && p[2] < 190, plain = p => Math.abs(p[0] - 230) < 8 && Math.abs(p[1] - 230) < 8;

  console.log('\n[② 이 장 그림(JPG)]');
  page.on('pageerror', e => console.log('   (페이지 오류)', e.message));
  await page.click('#lb-dl');
  let [dl] = await Promise.all([page.waitForEvent('download'), page.click('#lb-dl-img')]);
  let buf = fs.readFileSync(await dl.path());
  check(dl.suggestedFilename() === '2026-10-16_p02_marked.jpg' && buf[0] === 0xff && buf[1] === 0xd8, '파일 이름·JPG 형식', dl.suggestedFilename());
  let pr = await probe(buf.toString('base64'), 'image/jpeg');
  check(pr.w === 800 && pr.h === 1200 && reddish(pr.line) && plain(pr.blank), '그은 줄이 그림에 들어가 있다(원본 크기, 줄 자리만 빨갛게)', `줄 ${pr.line} · 빈 곳 ${pr.blank}`);

  const pdfCheck = async (btn, wantPages, label) => {
    if (!(await page.isVisible('#lb-dlmenu'))) await page.click('#lb-dl');   // 저장 뒤에도 메뉴가 열려 있다(✅ 안내를 보이려고)
    const [d] = await Promise.all([page.waitForEvent('download'), page.click(btn)]);
    const b = fs.readFileSync(await d.path()), txt = b.toString('latin1');
    const n = (txt.match(/\/Type \/Page\b/g) || []).length;
    // xref 표의 위치가 실제 "N 0 obj" 자리와 맞는지
    const xs = +txt.match(/startxref\n(\d+)/)[1], rows = txt.slice(xs).split('\n').slice(3).filter(l => / n $/.test(l));
    const okX = rows.every((l, k) => txt.startsWith(`${k + 1} 0 obj`, +l.slice(0, 10)));
    check(txt.startsWith('%PDF-1.4') && txt.trimEnd().endsWith('%%EOF') && n === wantPages && okX && /^2026-10-16_(all_3|marked_1)p\.pdf$/.test(d.suggestedFilename()), `${label}: PDF ${wantPages}쪽 · 구조(xref) 맞음`, `${d.suggestedFilename()} ${(b.length / 1024).toFixed(0)}KB`);
    // 안에 든 JPG 들을 꺼내 열어 본다
    const imgs = []; let at = 0;
    while ((at = txt.indexOf('/Filter /DCTDecode /Length ', at)) >= 0) {
      const L = +txt.slice(at + 27).match(/^\d+/)[0], s0 = txt.indexOf('stream\n', at) + 7;
      imgs.push(b.subarray(s0, s0 + L)); at = s0 + L;
    }
    return Promise.all(imgs.map(x => probe(Buffer.from(x).toString('base64'), 'image/jpeg')));
  };
  console.log('\n[③ 전체 PDF]');
  const all = await pdfCheck('#lb-dl-pdf', 3, '전체');
  check(all.length === 3 && !reddish(all[0].line) && reddish(all[1].line) && !reddish(all[2].line) && all.every(p => plain(p.blank)),
        '안의 그림이 열리고, 줄 그은 2번째 장에만 줄', all.map(p => p.line.join(',')).join(' / '));
  console.log('\n[④ 줄 그은 장만 PDF]');
  const only = await pdfCheck('#lb-dl-pdfm', 1, '줄 그은 장만');
  check(only.length === 1 && reddish(only[0].line), '그 1쪽에 줄이 들어 있다');

  console.log('\n[⑤ 서버로 보내는 것 없음]');
  const sent = calls.slice(before).filter(c => !/^GET \/p\d\.png$/.test(c));
  check(sent.length === 0, '저장하는 동안 사진 읽기(GET) 말고 요청 없음', sent.join(', ') || '0건');

  console.log('\n[⑥ 폰 390px]');
  const ph = await browser.newPage({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true });
  await ph.goto(base + '/slack');
  await ph.evaluate(() => { newsState.images = [{ name: '01.jpg', url: '/p0.png', download_url: '/p0.png' }]; openViewer(0); });
  await ph.waitForTimeout(300);
  await ph.tap('#lb-dl');
  const mb = await ph.evaluate(() => { const r = document.getElementById('lb-dlmenu').getBoundingClientRect(); return { l: r.left, r: r.right, vw: innerWidth }; });
  check(await ph.isVisible('#lb-dl-pdf') && mb.l >= 0 && mb.r <= mb.vw, '폰에서도 저장 메뉴가 화면 안에 다 보인다', `${Math.round(mb.l)}~${Math.round(mb.r)} / ${mb.vw}`);
  await ph.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
