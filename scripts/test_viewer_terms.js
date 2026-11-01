/**
 * test_viewer_terms.js — 신문 사진 뷰어(지면+요약) 오른쪽 아래 **📖 관리자 용어 노트** 확인 (실제 Chromium) — 2026-11-01 사용자 요청
 *
 *   ① 관리자(서버 /api/news/terms 가 200)만 '📖 용어' 버튼이 보인다 · 관리자가 아니면(403) 버튼 자체가 없다
 *   ② 버튼은 뷰어 **오른쪽 아래** · 누르면 패널, 지금 보는 날짜·면·기사가 표시됨
 *   ③ 용어 입력 → 🔍 → 풀이 카드 + 서버에 저장(날짜·면·기사 제목 같이 보냄) → 목록에 생김
 *   ④ 입력 중 키(h·n·화살표·Space)가 뷰어 단축키로 새지 않음 · Esc 는 패널만 닫음
 *   ⑤ 새로고침해도 목록이 그대로(서버 저장) · 목록 찾기 · 지우기 · '27면' 누르면 그 면으로 이동
 * 서버 쪽(저장·관리자 확인·풀이 캐시)은 python3 scripts/test_challenge.py 에서 따로 검사.
 * 실행: node scripts/test_viewer_terms.js
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
const BRIEF = [
  '*[신문요약 1/2] 신문 요약*',
  '38. FBI "北, 바이낸스서 9조원 해킹"… 연 수출액 13배 털어',
  '• WHAT: FBI가 바이낸스 해킹을 북한 소행이라고 언급함.',
  '• WHY: 외화 조달이 어려운 북한이 해커를 육성함.',
  '• HOW: 탈중앙화금융(DeFi) 서비스로 자금세탁 시도 예상.',
  '• 사진: 03',
].join('\n');

let ADMIN = true;
const SAVED = [];                     // 가짜 서버의 '관리자 노트'(새로고침해도 남는지 보려고 서버 쪽에 둔다)
let lastPost = null, nextId = 1;
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-11-01';
  const send = (t, b, code = 200) => { res.writeHead(code, { 'Content-Type': t }); res.end(b); };
  const json = (o, code = 200) => send('application/json', JSON.stringify(o), code);
  if (u === '/' || u === '/slack' || u === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data' || u === '/economy/data') return json({ date: D, messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] });
  if (u === '/api/news/today') {
    const images = Array.from({ length: 6 }, (_, i) => {
      const n = String(i + 1).padStart(2, '0') + '.jpg';
      return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' };
    });
    return json({ ok: true, ready: true, date: D, count: 6, images });
  }
  if (u === '/api/news/terms' && req.method === 'GET') return ADMIN ? json({ ok: true, items: SAVED }) : json({ ok: false, reason: 'forbidden' }, 403);
  if (u === '/api/news/terms' && req.method === 'POST') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      const b = JSON.parse(body); lastPost = b;
      const old = SAVED.find(x => x.term === b.term);
      const meaning = { short: b.term + ': 시험용 한 줄 뜻', easy: '시험용 쉬운 풀이예요.', invest: '이런 걸 보세요.' };
      if (old) { old.count++; Object.assign(old, { date: b.date, page: b.page, article: b.article }); }
      else SAVED.unshift(Object.assign({ id: nextId++, term: b.term, date: b.date, page: b.page, article: b.article, count: 1 }, meaning));
      json({ ok: true, result: Object.assign({ ok: true, term: b.term }, meaning), items: SAVED });
    });
    return;
  }
  if (u === '/api/news/terms/delete') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      const id = JSON.parse(body).id; const k = SAVED.findIndex(x => x.id === id); if (k >= 0) SAVED.splice(k, 1);
      json({ ok: k >= 0, items: SAVED });
    });
    return;
  }
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
  const openViewer = async (page) => {
    await page.waitForFunction(() => document.querySelectorAll('.brf-side img').length >= 1);
    await page.evaluate(() => document.querySelector('.brf-side [data-act="pen"]').click());
    await page.waitForFunction(() => !document.getElementById('lb').hidden && document.getElementById('lb-img').naturalWidth > 0);
  };

  console.log('\n[① 관리자가 아니면 버튼 없음]');
  ADMIN = false;
  let ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  let page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/economy');
  await openViewer(page);
  await page.waitForTimeout(300);
  check(await page.$eval('#tn-fab', b => b.hidden), '관리자가 아니면(403) 📖 용어 버튼이 안 보임');
  await ctx.close();

  console.log('\n[② 관리자: 오른쪽 아래 버튼·패널]');
  ADMIN = true;
  ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/economy');
  await openViewer(page);
  await page.waitForSelector('#tn-fab:not([hidden])');
  const pos = await page.$eval('#tn-fab', b => { const r = b.getBoundingClientRect(); return { r: innerWidth - r.right, b: innerHeight - r.bottom }; });
  check(pos.r < 40 && pos.b < 40, '버튼이 뷰어 오른쪽 아래', JSON.stringify(pos));
  await page.click('#tn-fab');
  check(await page.isVisible('#tn-panel'), '누르면 용어 노트 패널');
  await page.click('#tn-close');
  check(!(await page.isVisible('#tn-panel')), '✕ 로 닫힘(처음엔 안 보임)');
  await page.click('#tn-fab');
  const TODAY = await page.evaluate(() => state.date);       // 화면이 고른 날짜(오늘)
  const ctxText = await page.textContent('#tn-ctx');
  check(ctxText.includes(TODAY) && ctxText.includes('3면') && ctxText.includes('FBI'), '지금 보는 날짜·면·기사가 표시됨', ctxText);
  check(await page.evaluate(() => document.activeElement && document.activeElement.id === 'tn-q'), '열자마자 입력 칸에 커서');

  console.log('\n[③ 찾아서 저장]');
  const before = await page.evaluate(() => ({ i: V.i, pen: M.on }));
  await page.keyboard.type('디파이 h n');                    // h·n·Space 가 뷰어 단축키로 새면 형광펜·요약 칸이 바뀐다
  await page.keyboard.press('ArrowRight');
  const after = await page.evaluate(() => ({ i: V.i, pen: M.on, v: document.getElementById('tn-q').value }));
  check(after.i === before.i && after.pen === before.pen && after.v === '디파이 h n', '입력 중 키가 뷰어 단축키로 새지 않음(장 넘김·형광펜 그대로)', JSON.stringify(after));
  await page.fill('#tn-q', '디파이');
  await page.click('#tn-go');
  await page.waitForSelector('#tn-res .tn-card');
  check((await page.textContent('#tn-res')).includes('디파이: 시험용 한 줄 뜻'), '풀이 카드가 보임');
  check(lastPost && lastPost.term === '디파이' && lastPost.date === TODAY && lastPost.page === '03.jpg' && /FBI/.test(lastPost.article),
        '서버에 용어·날짜·면·기사 제목을 함께 보냄', JSON.stringify(lastPost));
  check((await page.$$eval('#tn-list .tn-item', e => e.length)) === 1 && (await page.textContent('#tn-n')) === '1', '목록에 생기고 버튼에 개수 1');
  if (process.env.SHOT_DIR) await page.screenshot({ path: path.join(process.env.SHOT_DIR, 'terms_pc.png') });
  await page.keyboard.press('Escape');
  check(!(await page.isVisible('#tn-panel')) && !(await page.$eval('#lb', e => e.hidden)), 'Esc 는 패널만 닫고 뷰어는 그대로');
  await page.click('#tn-fab'); await page.click('#lb-stage', { position: { x: 30, y: 30 } }).catch(() => {});
  await page.keyboard.press('Escape');
  check(!(await page.isVisible('#tn-panel')) && !(await page.$eval('#lb', e => e.hidden)), '커서가 패널 밖에 있어도 Esc 는 먼저 패널만 닫음');

  console.log('\n[④ 새로고침해도 그대로 · 찾기 · 이동 · 지우기]');
  SAVED.push({ id: 99, term: '스테이블코인', date: TODAY, page: '05.jpg', article: '다른 기사', count: 1, short: '가치가 고정된 코인' });
  await page.reload();
  await openViewer(page);
  await page.waitForSelector('#tn-fab:not([hidden])');
  await page.click('#tn-fab');
  check((await page.$$eval('#tn-list .tn-item b', e => e.map(x => x.textContent))).join() === '디파이,스테이블코인', '새로고침해도 서버에 저장된 목록이 보임');
  await page.fill('#tn-f', '스테이블');
  check((await page.$$eval('#tn-list .tn-item', e => e.length)) === 1, '저장한 용어에서 찾기');
  await page.click('#tn-list a[data-go]');
  check(await page.evaluate(() => (V.list[V.i] || {}).name) === '05.jpg', "'5면'을 누르면 그 면으로 이동");
  await page.fill('#tn-f', '');
  page.once('dialog', d => d.accept());
  await page.click('#tn-list [data-del="99"]');
  await page.waitForFunction(() => document.querySelectorAll('#tn-list .tn-item').length === 1);
  check(SAVED.length === 1 && SAVED[0].term === '디파이', '지우기(확인 후)');
  await ctx.close();

  console.log('\n[⑥ 메인 화면에서도 오른쪽 아래에 늘 떠 있음 (2026-11-01 사용자 요청)]');
  ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/economy');
  await page.waitForSelector('#tn-fab:not([hidden])');
  check(await page.$eval('#lb', e => e.hidden), '사진 뷰어를 열지 않은 메인 화면에서도 버튼이 보임');
  if (process.env.SHOT_DIR) await page.screenshot({ path: path.join(process.env.SHOT_DIR, 'terms_main.png') });
  const mpos = await page.$eval('#tn-fab', b => { const r = b.getBoundingClientRect(); return { r: innerWidth - r.right, b: innerHeight - r.bottom }; });
  await page.mouse.wheel(0, 3000); await page.waitForTimeout(200);
  const mpos2 = await page.$eval('#tn-fab', b => { const r = b.getBoundingClientRect(); return { r: innerWidth - r.right, b: innerHeight - r.bottom }; });
  check(mpos.r < 40 && mpos.b < 40 && JSON.stringify(mpos) === JSON.stringify(mpos2), '메인 화면 오른쪽 아래 · 스크롤해도 그 자리', JSON.stringify(mpos2));
  await page.click('#tn-fab');
  check((await page.$$eval('#tn-list .tn-item b', e => e.map(x => x.textContent))).join() === '디파이', '메인 화면에서도 저장한 용어가 계속 보임');
  check(!(await page.textContent('#tn-ctx')).includes('면'), '메인 화면에선 지금 보는 곳 = 날짜만(면·기사 없음)', await page.textContent('#tn-ctx'));
  await page.fill('#tn-q', '환율');
  await page.click('#tn-go');
  await page.waitForSelector('#tn-res .tn-card');
  check(lastPost.term === '환율' && lastPost.page === '' && lastPost.article === '', '메인 화면에서 찾아도 저장(면·기사는 비움)', JSON.stringify(lastPost));
  SAVED.push({ id: 77, term: '금리', date: TODAY, page: '04.jpg', article: '', count: 1, short: '돈의 값' });
  await page.reload();
  await page.waitForSelector('#tn-fab:not([hidden])');
  await page.waitForFunction(() => (newsState.images || []).length > 0);
  await page.click('#tn-fab');
  await page.fill('#tn-f', '금리');
  await page.click('#tn-list a[data-go]');
  const opened = await page.waitForFunction(() => !document.getElementById('lb').hidden && (V.list[V.i] || {}).name === '04.jpg', null, { timeout: 5000 }).then(() => true, () => false);
  check(opened && !(await page.isVisible('#tn-panel')), "메인 화면에서 '4면'을 누르면 그 면으로 사진 뷰어가 열림",
        opened ? '' : JSON.stringify(await page.evaluate(() => ({ lb: !document.getElementById('lb').hidden, n: (V.list && V.list[V.i] || {}).name, nd: newsState.date, sd: state.date }))));
  check(await page.isVisible('#tn-fab'), '사진 뷰어 위에서도 버튼이 그대로 보임');
  await ctx.close();

  console.log('\n[⑤ 폰 390px]');
  ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  page = await ctx.newPage();
  await page.goto(base + '/economy');
  await openViewer(page);
  await page.waitForSelector('#tn-fab:not([hidden])');
  await page.tap('#tn-fab');
  const box = await page.$eval('#tn-panel', p => { const r = p.getBoundingClientRect(); return { l: r.left, r: r.right, w: innerWidth }; });
  check(box.l >= 0 && box.r <= box.w, '폰에서도 패널이 화면 안에', JSON.stringify(box));
  await ctx.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
