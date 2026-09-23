/**
 * test_viewer_font.js — 신문 요약 **글자 크기 조절** 확인 (실제 Chromium)
 *
 *   · 툴바 오른쪽 [가− 100% 가+] — 90·100·112·125·140·160% 6단계, 가운데 숫자 = 100% 로
 *   · 제목·카테고리·본문·WHAT 라벨이 **같은 비율**로 커진다 (버튼·시간·사진 뷰어는 그대로)
 *   · 글이 커지면 '글만' 화면 폭을 조금 넓혀 한 줄 길이를 지킨다
 *   · 이 브라우저에 기억(digest.fontScale 하나만 저장)
 *   · 한국어 가독성: 낱말 중간에서 줄을 끊지 않는다(keep-all) — 폰에서 실제 줄바꿈 위치로 확인
 *   · 글+지면·휴대폰 390px 에서 가로 넘침 없음
 *
 * 실행: npm i playwright && node scripts/test_viewer_font.js
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

// 스크린샷과 같은 모양의 브리핑 — 기사 3개: 번호 줄 있음 / 없음 / 제목 끝에 번호
const BRIEF = [
  '*[신문요약 2/6] 신문 브리핑*',
  '부동산·주거 🔴 반드시 체크 | 목동 9·13단지 최고 49층 재건축',
  '• WHAT: 목동9단지는 49층·41개동·3958가구, 13단지는 49층·26개동·3852가구로 계획됨.',
  '• WHY: 통합심의로 사업 속도를 높이려는 것임.',
  '• HOW: 녹지·상업가로와 공공보행 동선을 함께 정비함.',
  '• 사진: 03',
  '수색·상암 비행안전구역 19.8㎢ 해제',
  '• WHAT: 수색비행장 안전구역의 93%가 해제돼 21.3㎢에서 1.5㎢로 축소됨.',
  '• WHY: 장기간의 높이·개발 제한을 완화함.',
  '• HOW: 상암동 156만㎡, 수색동 64만㎡ 등이 포함됨.',
  'K의료관광, 상가 층별 공식 변경 (사진 04)',
  '• WHAT: 2025년 외국인 환자 131만2700명 중 피부과 비중 62.9%.',
  '• WHY: 피부과·성형외과가 저층 상권과 관광 소비를 흡수함.',
  '• HOW: 의료기관 입점 확대가 공실 감소에 기여했다는 분석임.',
].join('\n');

let newsReady = true;
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-23',
    messages: [{ ts: '2026-09-23T06:29:00', source: 'user', kind: 'text', text: BRIEF }] }));
  if (u === '/api/news/today') {
    if (!newsReady) return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-23' }));
    const images = Array.from({ length: 6 }, (_, i) => {
      const n = String(i + 1).padStart(2, '0') + '.jpg';
      return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' };
    });
    return send('application/json', JSON.stringify({ ok: true, ready: true, date: '2026-09-23', count: 6, images }));
  }
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});


const px = (page, sel, prop = 'fontSize') => page.evaluate(([s, p]) => {
  const el = document.querySelector(s); return el ? parseFloat(getComputedStyle(el)[p]) : NaN; }, [sel, prop]);
const label = (page) => page.textContent('.fontctl .lv');
const near = (a, b) => Math.abs(a - b) < 0.3;

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  let page = await ctx.newPage();
  await page.goto(base + '/slack');
  await page.waitForSelector('.brf-art');

  console.log('\n[기본 — 예전과 같은 크기]');
  check(await label(page) === '100%', '처음엔 100%');
  check(near(await px(page, '.brf-title'), 17.5) && near(await px(page, '.brf-kv'), 15),
        '제목 17.5px · 본문 15px (예전 그대로)');
  check(await px(page, '.wrap', 'maxWidth') === 720, '화면 폭 720px 그대로');
  check(await page.evaluate(() => getComputedStyle(document.querySelector('.body')).wordBreak) === 'keep-all',
        '한국어 낱말 중간에서 줄을 끊지 않는다(keep-all)');

  console.log('\n[가+ 로 키우기]');
  await page.click('.fontctl .up'); await page.click('.fontctl .up');
  check(await label(page) === '125%', '두 번 누르면 125%');
  const t = await px(page, '.brf-title'), k = await px(page, '.brf-kv'), c = await px(page, '.brf-cat');
  check(near(t, 17.5 * 1.25) && near(k, 15 * 1.25) && near(c, 22 * 1.25),
        '제목·본문·카테고리가 같은 비율로 커진다', `${t}/${k}/${c}px`);
  check(near(await px(page, '.brf-kv .k', 'width'), 50 * 1.25), 'WHAT/WHY/HOW 라벨 칸도 같이 넓어져 본문과 안 겹친다');
  check(await px(page, '.wrap', 'maxWidth') > 720, '글이 커지면 화면 폭도 조금 넓혀 한 줄 길이를 지킨다',
        `${await px(page, '.wrap', 'maxWidth')}px`);
  check(near(await px(page, '.chip', 'fontSize'), 13) && near(await px(page, '.entry .time'), 13),
        '버튼·시간 표시는 그대로(요약 글만 커진다)');
  for (let i = 0; i < 5; i++) await page.evaluate(s => document.querySelector(s).click(), '.fontctl .up');
  check(await label(page) === '160%' && await page.isDisabled('.fontctl .up'), '최대 160% — 더 누를 수 없게 흐려진다');

  console.log('\n[기억 · 되돌리기]');
  await page.reload(); await page.waitForSelector('.brf-art');
  check(await label(page) === '160%' && near(await px(page, '.brf-kv'), 24), '새로고침해도 고른 크기를 기억한다');
  const keys = await page.evaluate(() => { const k = []; for (let i = 0; i < localStorage.length; i++) k.push(localStorage.key(i)); return k.join(','); });
  check(keys === 'digest.fontScale', '저장은 글자 크기 하나뿐', keys);
  await page.click('.fontctl .lv');
  check(await label(page) === '100%' && near(await px(page, '.brf-kv'), 15), '가운데 숫자를 누르면 100%로');
  for (let i = 0; i < 4; i++) await page.evaluate(s => document.querySelector(s).click(), '.fontctl .dn');
  check(await label(page) === '90%' && await page.isDisabled('.fontctl .dn'), '최소 90%');

  console.log('\n[글+지면 · 뷰어와 함께]');
  await page.click('.fontctl .lv');
  for (let i = 0; i < 4; i++) await page.click('.fontctl .up');
  await page.waitForFunction(() => newsState.images.length === 6);
  await page.click('.viewseg [data-view="paper"]');
  const lay = await page.evaluate(() => {
    const a = document.querySelector('.brf-art.has-side');
    const m = a.querySelector('.brf-main').getBoundingClientRect(), d = a.querySelector('.brf-side').getBoundingClientRect();
    return { side: d.left >= m.right - 1, over: document.documentElement.scrollWidth - innerWidth };
  });
  check(lay.side && lay.over <= 0, '140% 에서도 글+지면은 사진이 옆에, 가로 넘침 없음');
  await page.click('.brf-side .side-fig');
  await page.waitForSelector('#lb:not([hidden])');
  check(near(await px(page, '#lb-close', 'height'), 36), '사진 뷰어 버튼 크기는 그대로(글자 크기와 무관)');
  await page.close();

  console.log('\n[휴대폰 390px]');
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  page = await phone.newPage();
  await page.goto(base + '/slack'); await page.waitForSelector('.brf-art');
  for (let i = 0; i < 5; i++) await page.evaluate(s => document.querySelector(s).click(), '.fontctl .up');
  const ph = await page.evaluate(() => ({ over: document.documentElement.scrollWidth - innerWidth,
    tb: (() => { const t = document.getElementById('toolbar'); return t.scrollWidth - t.clientWidth; })() }));
  check(await label(page) === '160%' && ph.over <= 0 && ph.tb <= 0, '160% 로 키워도 가로로 넘치지 않는다',
        `페이지 ${ph.over}px · 툴바 ${ph.tb}px`);
  const words = await page.evaluate(() => {
    // 한 줄의 끝이 낱말 중간(한글-한글)에서 끊겼는지 — keep-all 이면 공백에서만 끊긴다
    const el = document.querySelector('.brf-kv .v'); const r = document.createRange(); const txt = el.firstChild;
    let lastTop = null, broken = 0;
    for (let i = 1; i < txt.length; i++) { r.setStart(txt, i); r.setEnd(txt, i + 1);
      const top = r.getBoundingClientRect().top;
      if (lastTop !== null && top > lastTop + 2 && /[가-힣]/.test(txt.data[i - 1]) && /[가-힣]/.test(txt.data[i])) broken++;
      lastTop = top; }
    return broken;
  });
  check(words === 0, '폰에서도 낱말이 중간에서 잘리지 않는다', `잘린 곳 ${words}`);

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
