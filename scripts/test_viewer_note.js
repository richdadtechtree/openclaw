/**
 * test_viewer_note.js — 신문 사진 뷰어 **옆 기사 요약 칸** 확인 (실제 Chromium)
 *
 * 신문 사진을 크게 연 채로 요약의 수치를 지면과 맞춰 보도록(팩트 체크) 뷰어 오른쪽에
 * 그 장에 실린 기사의 제목·WHAT·WHY·HOW·표를 붙인다(2026-09-30 사용자 요청, PC 전용).
 *
 *   ① 기사 옆 사진을 누르면 → 오른쪽에 **그 기사** 요약(맨 위·파란 줄), 같은 장의 다른 기사는 아래
 *   ② 숫자는 노랗게 강조(지면 숫자와 대조) · 표도 그대로
 *   ③ 칸이 **사진을 가리지 않는다**(사진은 남은 폭에 맞춤) · › 화살표도 칸 위에 안 올라감
 *   ④ 장을 넘기면 그 장의 기사로 바뀜 · 기사가 없는 장은 칸을 숨기고 사진을 넓게
 *   ⑤ 📝 버튼 / N 키로 끄고 켜기 — 끈 상태는 다음에 열어도 유지(localStorage digest.lbNote)
 *   ⑥ 지면 고르기(📌) 중엔 칸 없음 · 칸이 있어도 형광펜 긋기는 그대로
 *   ⑦ 폰(390px)에선 칸을 안 보인다(사진이 너무 작아지므로)
 *
 * 실행: npm i playwright && node scripts/test_viewer_note.js
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

// 스크린샷(2026-09-30)과 같은 모양 — 03번 장에 기사 2개(하나는 표 포함), 04번 장에 1개
const BRIEF = [
  '*[신문요약 1/6] 신문 브리핑*',
  '1. ⭐ 새 아파트 공급 뜸해지자…대구 미분양 절반으로 ‘뚝’',
  '• WHAT: 대구 미분양이 2024년 말 8,807가구에서 2026년 6월 4,383가구로 줄었음.',
  '| 지역 | 2024년 말 | 2026년 6월 | 감소 가구 |',
  '| 대구 | 8,807 | 4,383 | 4,424 |',
  '| 울산 | 4,131 | 1,359 | 2,772 |',
  '• WHY: 미분양이 줄어든 지역은 새 분양도 적었음.',
  '• HOW: 충남은 같은 기간 미분양이 약 5,000가구 늘어 지역 차이가 컸음.',
  '• 사진: 03',
  '2. 수색·상암 비행안전구역 19.8㎢ 해제',
  '• WHAT: 안전구역의 93%가 해제돼 21.3㎢에서 1.5㎢로 축소됨.',
  '• WHY: 장기간의 높이 제한을 완화함.',
  '• HOW: 상암동 156만㎡ 등이 포함됨.',
  '• 사진: 03',
  '3. K의료관광, 상가 층별 공식 변경 (사진 04)',
  '• WHAT: 외국인 환자 131만2700명 중 피부과 비중 62.9%.',
  '• WHY: 피부과가 저층 상권을 흡수함.',
  '• HOW: 공실 감소에 기여했다는 분석임.',
].join('\n');

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-09-30';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D,
    messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] }));
  if (u === '/api/news/today') {
    const images = Array.from({ length: 6 }, (_, i) => {
      const n = String(i + 1).padStart(2, '0') + '.jpg';
      return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' };
    });
    return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 6, images }));
  }
  if (u === '/api/news/pagetext') return send('application/json', '{"ok":false}');
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

const waitImg = (page) => page.waitForFunction(() => {
  const im = document.getElementById('lb-img');
  return im.complete && im.naturalWidth > 0 && V.fitW > 0 && Math.abs(im.getBoundingClientRect().width - V.fitW * V.zoom) < 2;
});
const note = (page) => page.evaluate(() => {
  const n = document.getElementById('lb-note'), r = n.getBoundingClientRect();
  const im = document.getElementById('lb-img').getBoundingClientRect();
  const nx = document.getElementById('lb-next').getBoundingClientRect();
  const st = document.getElementById('lb-stage').getBoundingClientRect();
  return {
    shown: !n.hidden && r.width > 0, w: Math.round(r.width), left: Math.round(r.left),
    titles: [...n.querySelectorAll('.nt-art .brf-title')].map(t => t.textContent.trim()),
    cur: [...n.querySelectorAll('.nt-art')].map(a => a.classList.contains('cur')),
    kv: [...n.querySelectorAll('.nt-art:first-of-type .brf-kv .k')].map(k => k.textContent).join(','),
    nums: [...n.querySelectorAll('.num')].map(e => e.textContent),
    tblRows: n.querySelectorAll('.brf-tbl tbody tr').length,
    imgRight: Math.round(im.right), nextRight: Math.round(nx.right), stageW: Math.round(st.width),
    btn: !document.getElementById('lb-note-btn').hidden && getComputedStyle(document.getElementById('lb-note-btn')).display !== 'none',
    pressed: document.getElementById('lb-note-btn').getAttribute('aria-pressed'),
  };
});
const openSide = async (page, k, act = 'pen') => {
  await page.evaluate(([k, act]) => document.querySelectorAll('.brf-side')[k].querySelector(`[data-act="${act}"]`).click(), [k, act]);
  await waitImg(page);
};

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/slack');
  await page.waitForFunction(() => document.querySelectorAll('.brf-side img').length === 3);

  console.log('\n[① 기사 사진 누르면 → 옆에 그 기사 요약 (PC 1280px)]');
  await openSide(page, 1);                        // 2번 기사(03번 장)에서 연다
  let n = await note(page);
  check(n.shown && n.btn && n.pressed === 'true', '오른쪽에 요약 칸 + 상단 📝 버튼', `폭 ${n.w}px`);
  check(n.titles.length === 2 && /^2\. 수색/.test(n.titles[0]) && /1\. .*대구 미분양/.test(n.titles[1]),
        '연 기사가 맨 위, 같은 장(03)의 다른 기사는 아래', n.titles.map(t => t.slice(0, 8)).join(' / '));
  check(n.cur[0] === true && n.cur[1] === false, '연 기사만 파란 줄로 강조');
  check(n.kv === 'WHAT,WHY,HOW', 'WHAT·WHY·HOW 가 그대로 보인다', n.kv);

  console.log('\n[② 숫자 강조 · 표]');
  check(n.nums.includes('8,807') && n.nums.includes('4,383') && n.nums.includes('93%') && n.nums.includes('1.5'),
        '숫자(8,807 · 93% · 1.5 등)가 노랗게 강조된다', n.nums.slice(0, 6).join(' '));
  check(!n.nums.includes('1.') && !n.nums.includes('2.') && !n.nums.includes('2'), '제목 앞 기사 번호(1. 2.)는 강조 안 함');
  check(n.tblRows === 2, '표도 칸 안에 그대로(2줄)');
  const col = await page.evaluate(() => getComputedStyle(document.querySelector('#lb-note .num')).color);
  check(col === 'rgb(255, 214, 107)', '강조 숫자 색', col);

  console.log('\n[③ 사진을 가리지 않는다]');
  check(n.imgRight <= n.left + 1, '사진 오른쪽 끝이 요약 칸보다 왼쪽', `사진 ${n.imgRight} ≤ 칸 ${n.left}`);
  check(n.stageW + n.w <= 1281, '사진 칸 + 요약 칸 = 화면 폭(겹침 없음)', `${n.stageW}+${n.w}`);
  await page.mouse.move(400, 400);
  check(n.nextRight <= n.left + 1, '› 화살표가 요약 칸 위에 올라가지 않는다', `화살표 ${n.nextRight}`);

  console.log('\n[④ 장 넘기기]');
  await page.click('#lb-next'); await waitImg(page);
  n = await note(page);
  check(n.shown && n.titles.length === 1 && /K의료관광/.test(n.titles[0]) && n.cur[0] === false,
        '04번 장 → 그 장의 기사(K의료관광)로 바뀐다', n.titles.join(''));
  await page.click('#lb-next'); await waitImg(page);
  n = await note(page);
  const w05 = await page.evaluate(() => document.getElementById('lb-stage').getBoundingClientRect().width);
  check(!n.shown && !n.btn && w05 >= 1279, '기사가 없는 장(05) → 칸·버튼 숨기고 사진을 넓게', `사진 칸 ${Math.round(w05)}px`);
  await page.click('#lb-prev'); await waitImg(page);
  check((await note(page)).shown, '다시 04로 오면 칸이 돌아온다');

  console.log('\n[⑤ 📝 / N 으로 끄고 켜기]');
  await page.click('#lb-note-btn'); await waitImg(page);
  n = await note(page);
  const wOff = await page.evaluate(() => document.getElementById('lb-stage').getBoundingClientRect().width);
  check(!n.shown && n.btn && n.pressed === 'false' && wOff >= 1279, '📝 누르면 칸이 사라지고 사진이 넓어진다(버튼은 남음)');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await openSide(page, 0);
  check(!(await note(page)).shown, '끈 상태는 다음에 열어도 유지');
  check(await page.evaluate(() => localStorage.getItem('digest.lbNote')) === '0', '기억은 이 브라우저의 digest.lbNote 하나');
  await page.keyboard.press('n'); await waitImg(page);
  n = await note(page);
  check(n.shown && /대구 미분양/.test(n.titles[0]), 'N 키로 다시 켜기 → 1번 기사가 맨 위', n.titles[0].slice(0, 14));

  console.log('\n[⑥ 형광펜 · 지면 고르기]');
  const r = await page.evaluate(() => { const b = document.getElementById('lb-img').getBoundingClientRect(); return { l: b.left, t: b.top, w: b.width, h: b.height }; });
  await page.mouse.move(r.l + r.w * 0.2, r.t + r.h * 0.4); await page.mouse.down();
  for (let k = 1; k <= 8; k++) await page.mouse.move(r.l + r.w * (0.2 + 0.06 * k), r.t + r.h * 0.4);
  await page.mouse.up();
  check(await page.evaluate(() => (M.marks['03.jpg'] || []).length) === 1, '요약 칸이 있어도 형광펜 긋기는 그대로');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await page.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="pick"]').click());
  await waitImg(page);
  check(!(await note(page)).shown, '지면 고르기(📌) 중엔 칸 없음');
  await page.keyboard.press('Escape');
  await page.close();

  console.log('\n[⑦ 폰 390px]');
  const ph = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const pp = await ph.newPage();
  await pp.goto(base + '/slack');
  await pp.waitForFunction(() => document.querySelectorAll('.brf-side img').length === 3);
  await openSide(pp, 0);
  n = await note(pp);
  const over = await pp.evaluate(() => document.querySelector('.lb-bar').scrollWidth - document.querySelector('.lb-bar').clientWidth);
  check(!n.shown && !n.btn && n.stageW >= 389, '폰에선 요약 칸·📝 버튼 없이 사진만', `사진 칸 ${n.stageW}px`);
  check(over <= 0, '폰 상단 바가 넘치지 않는다', `${over}px`);

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
