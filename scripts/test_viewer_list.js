/**
 * test_viewer_list.js — "🔍 …반드시 연결해서 봐야 할 5가지" 머리말 뒤 **줄바꿈** + 번호 목록 확인 (실제 Chromium)
 *
 *   · 한 줄에 붙어 온 "…5가지 1. 가 → 나 2. 다 …" → 머리말 따로, 1·2·3 한 항목씩
 *   · 줄이 나뉘어 온 경우도 같은 모양, 머리말은 '기사 제목'처럼 크게 뭉치지 않는다
 *   · 본문 속 숫자("3.5%", "1. 5배", 순서가 안 맞는 번호)는 목록으로 오인하지 않는다
 *   · 이 묶음만 따로 온 메시지도 같은 서식
 *   · "📌 오늘 신문 핵심 한 줄" → 강조 상자, "✅ …체크할 핵심 주제" 아래 줄 → ✓ 체크 칸(PC 2열·폰 1열)
 *     "🔴 반드시 체크 | 제목" 기사·평범한 대화는 오인 안 함
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
  '*🔍 오늘 신문에서 반드시 연결해서 봐야 할 3가지* 1. 서울 매매 3% 이상 상승 전망 96% → 매수 양극화',
  '공급 기대보다 즉시 입주 가능성과 금융 접근성이 실제 거래를 좌우하는 흐름임.',
  '',
  '2. 세제개편 부정 평가 78% → 임대료 전가 우려 → 순증 입주가 핵심',
  '',
  '세부담과 공급 시차가 동시에 임차시장에 영향을 줌.',
  '',
  '3. 태양광 확대 → 송전망·ESS 필요',
  '',
  '발전설비만 늘리면 해결되지 않고 전력망·저장·수요관리가 함께 가야 함.',
  '',
  '금융 🔴 반드시 체크 | 목록 뒤에 오는 새 기사',
  '• WHAT: 이 줄은 기사로 보여야 한다.',
].join('\n');
const KEY = [
  '📌 오늘 신문 핵심 한 줄 서울 주택은 공급 시차와 대출한도 소진으로 ‘기존주택·현금여력’ 중심 양극화가 커지고, 산업은 AI가 반도체를 넘어 로봇·전력망·냉각·양자칩까지 투자 지형을 넓히는 흐름임.',
  '✅ 오늘 반드시 체크할 핵심 주제',
  '5대 은행 신규 주담대·집단대출 심사 변화',
  '공적주택 119만가구 중 실제 신축 입주 물량과 시점',
  '목동 9·13단지 분담금·인허가 일정',
  '원전 출력제한 보상과 송전망·ESS 투자',
  '현대차 RMAC 확대와 휴머노이드 공장 투입 일정',
  '한미 원전 8기 구상의 계약·로열티 구조',
  '원유 레버리지·인버스 ETP 변동성',
  '',
  '금융 🔴 반드시 체크 | 체크 묶음 뒤 새 기사',
  '• WHAT: 기사로 보여야 한다.',
].join('\n');
// 2026-09-24 GPT 가 바꿔 보낸 새 형식 — 불릿·콜론 없이, 제목 줄에 WHAT 이 붙어 옴 (한 기사가 셋으로 쪼개지던 문제)
const NEWFMT = [
  '43. 연휴에 고양이 밥줄 시터 모집 WHAT 추석을 앞두고 반려동물 방문 돌봄과 단기 아르바이트 구인이 늘었음.',
  'WHY 연휴에 집을 비우는 가구와 근처에서 일하려는 사람의 수요가 맞물림.',
  'HOW 당근의 9월16~22일 반려동물 돌봄 공고는 전월 동기보다 30%, 지원자는 40% 증가함.',
  '',
  '44. How to 투자 설명회 성황 WHAT 개인투자자 대상 설명회에 2000명이 몰렸음.',
  'WHY 금리 인하 기대가 커짐.',
].join('\n');
const CHAT = '✅ 확인했어요';   // 평범한 대화 — 서식 없이 그대로
const PLAIN = '오늘 회의는 3. 5시에 합니다. 2. 준비물 없음';   // 목록 아님 — 그대로 둬야 한다

const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  // 화면이 달라는 날짜를 그대로 돌려준다 — 테스트를 도는 날이 바뀌어도(자정 넘김) 결과가 같게
  const D = new URL(req.url, 'http://x').searchParams.get('date') || '2026-09-23';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/' || u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: '2026-09-23T06:29:00', source: 'user', kind: 'text', text: JOINED },
    { ts: '2026-09-23T06:30:00', source: 'user', kind: 'text', text: SPLIT },
    { ts: '2026-09-23T06:31:00', source: 'user', kind: 'text', text: PLAIN },
    { ts: '2026-09-23T06:32:00', source: 'user', kind: 'text', text: KEY },
    { ts: '2026-09-23T06:33:00', source: 'user', kind: 'text', text: CHAT },
    { ts: '2026-09-23T06:34:00', source: 'user', kind: 'text', text: NEWFMT }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
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
    const bs = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[1];
      return { notes: [...c.querySelectorAll('.brf-num .note')].map(e => e.textContent.slice(0, 8)),
               titles: [...c.querySelectorAll('.brf-title')].map(e => e.textContent),
               cats: [...c.querySelectorAll('.brf-cat')].map(e => e.textContent),
               fs: [...c.querySelectorAll('.brf-num .v')].map(e => getComputedStyle(e).fontWeight + '/' + getComputedStyle(e).fontSize) };
    });
    check(bs.notes.length === 3 && /^공급/.test(bs.notes[0]) && /^세부담/.test(bs.notes[1]) && /^발전설비/.test(bs.notes[2]),
          '항목마다 딸린 설명 줄이 그 항목 안에 붙는다(1번만 특별해지지 않음)', bs.notes.join(' / '));
    check(new Set(bs.fs).size === 1, '1·2·3 항목이 모두 같은 모양(굵기·크기)', bs.fs.join(' '));
    check(!bs.titles.some(t => /^\s*[23]\.|공급 기대|세부담/.test(t)), '2·3번이나 설명 줄이 굵은 기사 제목으로 그려지지 않는다');
    check(bs.titles.some(t => /목록 뒤에 오는 새 기사/.test(t)) && bs.cats.includes('금융'),
          '목록 뒤에 오는 새 기사(카테고리 + WHAT)는 다시 기사로 그려진다');
    check(r.c.sec.length === 0 && r.c.nums.length === 0 && /3\. 5시에 합니다\. 2\. 준비물/.test(r.c.text),
          '평범한 대화의 숫자는 목록으로 바꾸지 않는다');
    const k = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('.entry .body')];
      const c = cards[3], chat = cards[4];
      const items = [...c.querySelectorAll('.brf-chk')];
      const tops = items.slice(0, 2).map(e => Math.round(e.getBoundingClientRect().top));
      const key = c.querySelector('.brf-key');
      return { lbl: key && key.querySelector('.lbl').textContent, txt: key && key.querySelector('.txt').textContent,
               keyFs: key && parseFloat(getComputedStyle(key.querySelector('.txt')).fontSize),
               bodyFs: parseFloat(getComputedStyle(c).fontSize),
               sec: [...c.querySelectorAll('.brf-sec')].map(e => e.textContent),
               items: items.map(e => e.querySelector('.v').textContent), sameRow: tops[0] === tops[1],
               titles: [...c.querySelectorAll('.brf-title')].map(e => e.textContent),
               flags: [...c.querySelectorAll('.brf-flag')].length,
               chatPlain: !chat.querySelector('.brf-sec,.brf-key,.brf-chk') && /✅ 확인했어요/.test(chat.innerText) };
    });
    check(/핵심 한 줄$/.test(k.lbl || '') && /^서울 주택은/.test(k.txt || '') && /흐름임\.$/.test(k.txt || ''),
          '"📌 핵심 한 줄" → 머리표와 문장이 나뉜 강조 상자', `${k.lbl} | ${(k.txt || '').slice(0, 12)}…`);
    check(k.keyFs > k.bodyFs, '핵심 문장은 본문보다 크게', `${k.keyFs}px > ${k.bodyFs}px`);
    check(k.sec.length === 1 && /체크할 핵심 주제/.test(k.sec[0]), '"✅ …체크할 핵심 주제" 는 섹션 머리말');
    check(k.items.length === 7 && k.items[0].startsWith('5대 은행') && k.items[6].startsWith('원유'),
          '아래 7줄이 ✓ 체크 항목 7칸', `${k.items.length}칸`);
    check(w >= 900 ? k.sameRow : !k.sameRow, w >= 900 ? 'PC: 2열로 나란히(한눈에 훑기)' : '폰: 1열');
    check(k.titles.some(t => /체크 묶음 뒤 새 기사/.test(t)) && k.flags === 1 && !k.items.some(t => /새 기사/.test(t)),
          '"🔴 반드시 체크 | 제목" 기사는 섹션으로 오인하지 않고 기사로 그린다');
    check(k.chatPlain, '"✅ 확인했어요" 같은 평범한 대화는 그대로');
    const nf = await page.evaluate(() => {
      const c = [...document.querySelectorAll('.entry .body')][5];
      return [...c.querySelectorAll('.brf-art')].map(a => ({
        t: (a.querySelector('.brf-title') || {}).textContent || '',
        kv: [...a.querySelectorAll('.brf-kv .k')].map(e => e.textContent).join(','),
        first: ((a.querySelector('.brf-kv .v') || {}).textContent || '').slice(0, 6) }));
    });
    check(nf.length === 2, '새 형식(불릿·콜론 없음): 기사 2개로 묶인다(WHY·HOW 가 새 기사로 쪼개지지 않음)', `${nf.length}개`);
    check(nf[0] && /연휴에 고양이 밥줄 시터 모집$/.test(nf[0].t.trim()) && nf[0].kv === 'WHAT,WHY,HOW' && nf[0].first.startsWith('추석을'),
          '제목 줄에 붙은 WHAT 을 떼어 제목 + WHAT·WHY·HOW 한 기사로', nf[0] && `${nf[0].t.slice(0, 16)} | ${nf[0].kv}`);
    check(nf[1] && /How to 투자 설명회/.test(nf[1].t) && nf[1].kv === 'WHAT,WHY', '제목 속 영어 "How to" 는 HOW 로 오인하지 않는다', nf[1] && nf[1].t);
    check(r.over <= 0, '가로로 넘치지 않는다');
    await page.close();
  }

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
