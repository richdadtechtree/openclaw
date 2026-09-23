/**
 * test_viewer_list.js — "🔍 …반드시 연결해서 봐야 할 5가지" 머리말 뒤 **줄바꿈** + 번호 목록 확인 (실제 Chromium)
 *
 *   · 한 줄에 붙어 온 "…5가지 1. 가 → 나 2. 다 …" → 머리말 따로, 1·2·3 한 항목씩
 *   · 줄이 나뉘어 온 경우도 같은 모양, 머리말은 '기사 제목'처럼 크게 뭉치지 않는다
 *   · 본문 속 숫자("3.5%", "1. 5배", 순서가 안 맞는 번호)는 목록으로 오인하지 않는다
 *   · 이 묶음만 따로 온 메시지도 같은 서식
 *
 * 실행: npm i playwright && node scripts/test_viewer_list.js
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

const JOINED = [
  '*[신문요약 6/6] 신문 브리핑*',
  '목동 9·13단지 최고 49층 재건축',
  '• WHAT: 목동9단지는 49층으로 계획됨.',
  '• WHY: 통합심의로 속도를 높임.',
  '• HOW: 인허가는 별도 확인.',
  '🔍 오늘 신문에서 반드시 연결해서 봐야 할 5가지 1. 서울 매매 3% 이상 상승 전망 96% → 한강벨트·기존주택 선호 → 5대 은행 대출한도 소진 → 현금·대출 여력에 따른 매수 양극화 2. 금리 3.5% 유지 → 1. 5배 레버리지 제한 3. 수출 호조',
].join('\n');
const SPLIT = [
  '*🔍 오늘 신문에서 반드시 연결해서 봐야 할 3가지*',
  '1. 첫째 흐름',
  '2. 둘째 흐름',
  '3. 셋째 흐름',
].join('\n');
const PLAIN = '오늘 회의는 3. 5시에 합니다. 2. 준비물 없음';   // 목록 아님 — 그대로 둬야 한다

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: '2026-09-23', messages: [
    { ts: '2026-09-23T06:29:00', source: 'user', kind: 'text', text: JOINED },
    { ts: '2026-09-23T06:30:00', source: 'user', kind: 'text', text: SPLIT },
    { ts: '2026-09-23T06:31:00', source: 'user', kind: 'text', text: PLAIN }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: '2026-09-23' }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };

  for (const [w, label] of [[1280, 'PC'], [390, '휴대폰']]) {
    const page = await browser.newPage({ viewport: { width: w, height: 900 } });
    await page.goto(base + '/slack');
    await page.waitForSelector('.entry');
    const r = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.entry .body')];
      const pick = (c) => ({
        sec: [...c.querySelectorAll('.brf-sec')].map(e => e.textContent),
        nums: [...c.querySelectorAll('.brf-num')].map(e => e.querySelector('.n').textContent + '|' + e.querySelector('.v').textContent),
        titles: [...c.querySelectorAll('.brf-title')].map(e => e.textContent),
        text: c.innerText,
      });
      const a = pick(cards[0]), b = pick(cards[1]), c = pick(cards[2]);
      const sec = cards[0].querySelector('.brf-sec'), n1 = cards[0].querySelector('.brf-num');
      return { a, b, c, below: sec && n1 ? n1.getBoundingClientRect().top >= sec.getBoundingClientRect().bottom - 1 : false,
               over: document.documentElement.scrollWidth - innerWidth };
    });
    console.log(`\n[${label} ${w}px]`);
    check(r.a.sec.length === 1 && /봐야 할 5가지$/.test(r.a.sec[0].trim()), '머리말 "…5가지" 가 따로 한 줄', JSON.stringify(r.a.sec));
    check(r.below, '1번 항목은 머리말 **아래 줄**에서 시작한다(줄바꿈)');
    check(r.a.nums.length === 3 && r.a.nums[0].startsWith('1|서울 매매 3% 이상') && r.a.nums[0].endsWith('매수 양극화')
          && r.a.nums[1].startsWith('2|금리 3.5% 유지') && r.a.nums[2] === '3|수출 호조',
          '1·2·3 이 한 항목씩 나뉜다', r.a.nums.map(x => x.slice(0, 14)).join(' / '));
    check(/1\. 5배 레버리지/.test(r.a.nums[1] || ''), '"3.5%"·"1. 5배" 같은 본문 숫자에서는 자르지 않는다');
    check(!r.a.titles.some(t => /5가지/.test(t)), '머리말이 기사 제목(크게 뭉친 글씨)으로 그려지지 않는다');
    check(r.a.titles.some(t => /목동/.test(t)), '앞의 기사 제목은 그대로 기사 제목');
    check(r.b.sec.length === 1 && r.b.nums.length === 3, '줄이 나뉘어 온 경우도 같은 모양(머리말 + 3항목)',
          `${r.b.sec.length} + ${r.b.nums.length}`);
    check(r.c.sec.length === 0 && r.c.nums.length === 0 && /3\. 5시에 합니다\. 2\. 준비물/.test(r.c.text),
          '평범한 대화의 숫자는 목록으로 바꾸지 않는다');
    check(r.over <= 0, '가로로 넘치지 않는다');
    await page.close();
  }

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
