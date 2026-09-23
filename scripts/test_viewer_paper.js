/**
 * test_viewer_paper.js — '📰 글+지면' 보기 확인 (실제 Chromium)
 *
 * 브리핑 기사마다 옆에 그 기사가 실린 신문 사진을 붙이고, 누르면 형광펜이 켜진 뷰어로 여는 기능.
 * 기존 '📝 글만' 보기는 그대로 유지돼야 한다.
 *
 * 확인하는 것
 *   ① 처음엔 '글만'(기존 화면 그대로) — 사진 칸 없음 · 폭 720px
 *   ② "• 사진: 03" 줄은 화면에 안 보이고, 기사 번호로만 쓰인다 / 제목 끝 "(사진 04)" 도 인식
 *      (07.jpg · *사진* · "07, 08" 같은 변형도 인식, "사진 3장 공개" 같은 본문은 오인 안 함)
 *   ③ '글+지면' 을 누르면 기사마다 사진 칸이 붙는다 (번호 있는 기사 = 그 사진, 없는 기사 = 연결 버튼)
 *   ④ 사진을 누르면 뷰어가 **그 장에서, 형광펜 켜진 채로** 열린다
 *   ⑤ 뷰어에서 그은 줄이 닫은 뒤 기사 옆 작은 사진에도 보인다
 *   ⑥ 번호 없는 기사: 📌 지면 찾아 연결 → 넘겨서 고르고 📌 → 그 사진이 붙는다
 *   ⑦ 새로고침: 보기 방식·직접 연결은 기억, **형광펜은 사라짐**(일회성 규칙 유지)
 *      저장소엔 digest.view / digest.pageLinks 만 — 형광펜 흔적 0
 *   ⑧ 20초 자동 갱신 때 사진 칸을 다시 만들지 않는다(깜빡임 없음)
 *   ⑨ 다시 '글만' → 사진 칸이 사라지고 기존 화면과 같아진다
 *   ⑩ 사진이 아직 없는 날 → 안내문 · 휴대폰(390px)에서 가로 넘침 없음
 *
 * 실행: npm i playwright && node scripts/test_viewer_paper.js
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
  '',
  '다음을 사용하여 보냄 <@U0BUG6LJXL0>',   // 슬랙이 붙이는 앱 발신 꼬리표 — 화면에서 지워져야 한다
].join('\n');

let newsReady = true;
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-23',
    messages: [{ ts: '2026-09-23T06:29:00', source: 'user', kind: 'text', text: BRIEF },
               { ts: '2026-09-23T06:30:00', source: 'user', kind: 'text', text: '_다음을 사용하여 보냄_ <@U0BUG6LJXL0|ChatGPT>' }] }));
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

const sides = (page) => page.evaluate(() => [...document.querySelectorAll('.brf-side')].map(s => ({
  no: (s.querySelector('.side-no') || {}).textContent || '',
  src: (s.querySelector('.side-src') || {}).textContent || '',
  empty: !!s.querySelector('.side-empty'),
})));

/** 사진 안의 비율 좌표(0~1)로 형광펜 긋기 */
async function stroke(page, x1, y1, x2, y2) {
  const r = await page.evaluate(() => {
    const b = document.getElementById('lb-img').getBoundingClientRect();
    return { l: b.left, t: b.top, w: b.width, h: b.height };
  });
  await page.mouse.move(r.l + r.w * x1, r.t + r.h * y1);
  await page.mouse.down();
  for (let k = 1; k <= 8; k++)
    await page.mouse.move(r.l + r.w * (x1 + (x2 - x1) * k / 8), r.t + r.h * (y1 + (y2 - y1) * k / 8));
  await page.mouse.up();
}
const waitImg = (page) => page.waitForFunction(() => {
  const im = document.getElementById('lb-img'); return im.complete && im.naturalWidth > 0 && V.fitW > 0;
});
// 기사 옆 작은 사진 위 그림판에 '색칠된 점'이 몇 개인가 (0 이면 아무 줄도 없음)
const sideInk = (page, k) => page.evaluate((k) => {
  const cv = document.querySelectorAll('.brf-side')[k].querySelector('canvas');
  if (!cv || !cv.width) return 0;
  const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
  let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
  return n;
}, k);

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
  await page.waitForFunction(() => newsState.images.length === 6);

  console.log('\n[① 기본은 글만 — 기존 화면 그대로]');
  check((await sides(page)).length === 0, '처음엔 기사 옆에 사진 칸이 없다');
  check(await page.evaluate(() => document.querySelector('.viewseg [data-view="text"]').getAttribute('aria-pressed') === 'true'),
        '보기 버튼은 "📝 글만" 이 눌린 상태');
  const w0 = await page.evaluate(() => getComputedStyle(document.querySelector('.wrap')).maxWidth);
  check(w0 === '720px', '화면 폭도 예전 그대로(720px)', w0);
  check(await page.evaluate(() => document.querySelectorAll('.brf-art').length) === 3, '기사 3개가 그려진다');

  console.log('\n[② 사진 번호 표기]');
  const text = await page.evaluate(() => document.getElementById('feed').innerText);
  check(!/사진\s*:\s*03/.test(text), '"• 사진: 03" 줄은 화면에 안 보인다');
  check(!/사진 04/.test(text) && /K의료관광/.test(text), '제목 끝 "(사진 04)" 도 떼어내고 제목은 남는다');
  check(!/사용하여 보냄|U0BUG6LJXL0/.test(text), '슬랙 꼬리표 "다음을 사용하여 보냄 @앱" 이 안 보인다');
  check(await page.evaluate(() => document.querySelectorAll('.entry').length) === 1, '꼬리표만 있던 메시지는 카드로 안 만든다');
  check(await page.evaluate(() => cleanSent('• HOW: 새 공법을 사용하여 공사함.')) === '• HOW: 새 공법을 사용하여 공사함.',
        '본문 속 "사용하여" 는 지우지 않는다');
  const pages = await page.evaluate(() => [...document.querySelectorAll('.brf-art')].map(a => a.dataset.page || ''));
  check(pages.join(',') === '3,,4', '기사별 사진 번호를 기억한다', pages.join(','));

  const variants = await page.evaluate(() => {
    const L = ['• 사진: 07.jpg', '• *사진*: 12.gif', '• 사진 07번', '• 사진: 07, 08', '📰 사진 7/30',
               '• 사진 3장 공개', '• 사진: 삼성 공장', '• 사진 속 인물 07명 공개'].map(t => (t.match(PAGE_LINE_RE) || [])[1] || '-');
    const T = ['목동 (사진: 07.jpg)', '목동 [사진 07, 08]', '목동 (사진 설명)'].map(t => (t.match(PAGE_TAIL_RE) || [])[1] || '-');
    return L.join(',') + ' | ' + T.join(',');
  });
  check(variants === '07,12,07,07,7,-,-,- | 07,07,-',
        'GPT 표기가 조금 달라도 번호를 읽고, 본문 문장("사진 3장 공개")은 번호로 착각 안 함', variants);

  console.log('\n[③ 글+지면]');
  await page.click('.viewseg [data-view="paper"]');
  let s = await sides(page);
  check(s.length === 3, '기사마다 사진 칸이 붙는다', `${s.length}개`);
  check(s[0].no === '03' && /요약문 표기/.test(s[0].src), '번호 있는 기사 → 03번 사진', s[0].src);
  check(s[1].empty, '번호 없는 기사 → 짐작하지 않고 "지면 찾아 연결" 버튼');
  check(s[2].no === '04', '제목 끝 번호 기사 → 04번 사진');
  const lay = await page.evaluate(() => {
    const a = document.querySelector('.brf-art.has-side');
    const m = a.querySelector('.brf-main').getBoundingClientRect(), d = a.querySelector('.brf-side').getBoundingClientRect();
    return { side: d.left >= m.right - 1, top: Math.abs(d.top - m.top) < 4 };
  });
  check(lay.side && lay.top, '넓은 화면: 사진이 기사 "옆"(오른쪽)에 나란히');
  check(await page.evaluate(() => getComputedStyle(document.querySelector('.wrap')).maxWidth) === '1120px',
        '글+지면일 땐 화면을 넓게 쓴다(1120px)');

  console.log('\n[④ 사진 누르면 → 그 장에서 형광펜 켜진 뷰어]');
  await page.click('.brf-side .side-fig');
  await waitImg(page);
  const st = await page.evaluate(() => ({ open: !document.getElementById('lb').hidden, i: V.i, pen: M.on,
    pick: !document.getElementById('lb-pick').hidden }));
  check(st.open && st.i === 2, '뷰어가 03번째 장에서 열린다', `V.i=${st.i}`);
  check(st.pen, '형광펜이 켜진 채로 열린다(바로 줄 긋기 가능)');
  check(!st.pick, '"📌 이 장 연결" 버튼은 안 보인다(고르기 모드 아님)');

  console.log('\n[⑤ 그은 줄이 기사 옆에도 보인다]');
  await stroke(page, 0.2, 0.3, 0.8, 0.3);
  await page.keyboard.press('Escape');           // 형광펜 끄기
  await page.keyboard.press('Escape');           // 뷰어 닫기
  check(await page.evaluate(() => document.getElementById('lb').hidden), 'Esc 두 번으로 닫힌다');
  const ink = await sideInk(page, 0);
  check(ink > 20, '기사 옆 작은 사진에 형광펜 줄이 겹쳐 보인다', `칠해진 점 ${ink}개`);
  check(await sideInk(page, 2) === 0, '다른 장(04) 사진엔 줄이 없다');

  console.log('\n[⑥ 번호 없는 기사: 직접 찾아 연결]');
  await page.evaluate(() => document.querySelectorAll('.brf-side')[1].querySelector('[data-act="pick"]').click());
  await waitImg(page);
  check(await page.isVisible('#lb-pick'), '고르기 모드: 상단에 "📌 이 장 연결" 버튼');
  check(await page.evaluate(() => !M.on), '고르기 모드는 형광펜 꺼진 채(좌우 넘기기 가능)');
  check(await page.evaluate(() => V.pick && /수색/.test(V.pick.title)), '어느 기사를 고르는 중인지 기억한다');
  for (let k = 0; k < 4; k++) await page.click('#lb-next');
  await waitImg(page);
  await page.click('#lb-pick');
  s = await sides(page);
  check(await page.evaluate(() => document.getElementById('lb').hidden), '📌 누르면 뷰어가 닫힌다');
  check(s[1].no === '05' && /직접 연결/.test(s[1].src), '그 기사 옆에 05번 사진이 붙는다', s[1].src);

  console.log('\n[⑧ 20초 자동 갱신 — 깜빡임 없음]');
  await page.evaluate(() => { document.querySelector('.brf-side img').__probe = 1; });
  await page.evaluate(async () => { await load(); await loadNews(); });
  check(await page.evaluate(() => document.querySelector('.brf-side img').__probe === 1),
        '내용이 그대로면 사진 칸을 다시 만들지 않는다');

  console.log('\n[⑦ 새로고침]');
  await page.reload();
  await page.waitForSelector('.brf-side');
  await page.waitForFunction(() => document.querySelectorAll('.brf-side').length === 3);
  s = await sides(page);
  check(await page.evaluate(() => document.body.classList.contains('paper')), '보기 방식(글+지면)을 기억한다');
  check(s[1].no === '05', '직접 연결한 사진도 기억한다');
  await page.waitForFunction(() => { const im = document.querySelector('.brf-side img'); return im.complete && im.naturalWidth; });
  check(await sideInk(page, 0) === 0, '형광펜 줄은 사라진다(일회성 규칙 그대로)');
  const keys = await page.evaluate(() => { const k = []; for (let i = 0; i < localStorage.length; i++) k.push(localStorage.key(i));
    for (let i = 0; i < sessionStorage.length; i++) k.push('session:' + sessionStorage.key(i)); return k.sort(); });
  check(keys.join(',') === 'digest.pageLinks,digest.view', '저장소엔 보기 방식·연결 정보뿐 — 형광펜 흔적 0', keys.join(', '));

  console.log('\n[⑨ 다시 글만]');
  await page.click('.viewseg [data-view="text"]');
  check((await sides(page)).length === 0, '사진 칸이 모두 사라진다');
  check(await page.evaluate(() => !document.body.classList.contains('paper') &&
        getComputedStyle(document.querySelector('.wrap')).maxWidth === '720px' &&
        !document.querySelector('.has-side')), '화면이 기존과 똑같이 돌아온다');
  await page.close();

  console.log('\n[⑩ 사진 없는 날 · 휴대폰]');
  newsReady = false;
  page = await ctx.newPage();
  await page.goto(base + '/slack');
  await page.waitForSelector('.brf-art');
  await page.click('.viewseg [data-view="paper"]');
  await page.waitForTimeout(300);
  check(await page.isVisible('.paper-note') && (await sides(page)).length === 0,
        '사진이 아직 없으면 안내문만(빈 칸을 억지로 만들지 않음)');
  await page.close();
  newsReady = true;

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  page = await phone.newPage();
  await page.goto(base + '/slack');
  await page.waitForSelector('.brf-art');
  await page.waitForFunction(() => newsState.images.length === 6);
  await page.click('.viewseg [data-view="paper"]');
  const ph = await page.evaluate(() => {
    const f = document.querySelector('.brf-side .side-fig').getBoundingClientRect();
    const m = document.querySelector('.brf-art.has-side .brf-main').getBoundingClientRect();
    return { over: document.documentElement.scrollWidth - innerWidth, figW: Math.round(f.width), below: f.top >= m.bottom - 1 };
  });
  check(ph.over <= 0, '휴대폰: 가로로 넘치지 않는다', `넘침 ${ph.over}px`);
  check(ph.below && ph.figW < 120, '휴대폰: 사진은 기사 아래에 작게', `폭 ${ph.figW}px`);
  await page.evaluate(() => document.querySelectorAll('.brf-side')[1].querySelector('[data-act="pick"]').click());
  await waitImg(page);
  const bar = await page.evaluate(() => {
    const b = document.querySelector('.lb-bar'); return b.scrollWidth - b.clientWidth;
  });
  check(bar <= 0 && await page.isVisible('#lb-pick'), '휴대폰: 📌 버튼이 상단 바에 들어간다', `넘침 ${bar}px`);

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
