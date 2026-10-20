/**
 * test_viewer_flow.js — '오늘 신문 연결 5가지' 기사 고리 확인 (실제 Chromium) — 2026-10-20 사용자 요청
 *   "오늘 있었던 기사들을 연결해서 세상의 흐름을 연결해 보고 싶어"
 *
 *   ① "① 서울 입주 감소(1) → 정비사업 이주비 부담(2)" → 화살표로 나눈 기사 카드 + 번호 단추(1)(2)
 *   ② 번호 단추를 누르면 그 기사로 이동해 잠깐 빛남 · 단추에 마우스를 올리면 기사 제목·WHAT
 *   ③ 설명 줄 "흐름:" → 굵은 이름, "연결 고리:"·"다음에 볼 것:" → 라벨, 글 속 (1) 도 단추
 *   ④ 카드 아래 연결된 기사 제목 목록(폰용) · 눌러도 이동
 *   ⑤ 10-19 형식 "(10쪽)" 은 지면 쪽 번호로 찾음 · 번호 없는 평범한 목록은 예전 그대로 · 못 찾은 번호는 글자 그대로
 *   ⑥ 폰 390px 에서 넘치지 않음
 * 실행: npm i playwright && node scripts/test_viewer_flow.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const D = '2026-10-20';
const ARTS = `[2026-10-20 신문 요약 1/2] 부동산
_1. 서울 11월 입주 488가구 (PDF 1·7)_
WHAT: 서울 11월 입주 예정 3개 단지·488가구.
WHY: 전국 입주물량 감소.
HOW [예정]: 전국 1만1559가구(-30%).
_2. 강북 재개발 이주비 금리 (2)_
WHAT: 서울 정비사업 지역별 이주비 대출금리 격차.
WHY: 종전자산 담보가치 차이.
HOW [확정/검토]: 강남4구 기본 평균 3.78%.
_6. 고급 아파트 하이필로티 (3 좌)_
WHAT: 신축 아파트에서 높은 저층 필로티 채택 확대.
WHY: 개방감.
HOW [기사 사례]: 10m 이상 높은 필로티.`;
const FLOW = `[2026-10-20 신문 요약 2/2] 종합
:mag_right: 오늘 신문 연결 5가지
① 서울 입주 감소(1) → 정비사업 이주비 부담(2) → 고급 신축 설계 경쟁(6)
• 흐름: 공급 절벽이 정비사업 비용으로 번진다
• 연결 고리: 11월 서울 입주 488가구로 급감(1), 강북 이주비 금리 최고 6%(2).
• 다음에 볼 것: 12월 서울 입주 물량
② 이주비 부담(2) ↔ 지면 쪽으로 찾기(3쪽)
③ 주택 공급 → 금리 → 구매력
④ 없는 기사(77) ↔ 서울 입주(1)`;
const srv = http.createServer((req, res) => {
  const p = new URL(req.url, 'http://x').pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (p === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (p === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: D + 'T07:10:00', source: 'user', kind: 'text', text: ARTS }, { ts: D + 'T07:11:00', source: 'user', kind: 'text', text: FLOW }] }));
  if (p === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
  send('application/json', '{"ok":false}');
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(base + '/slack?date=' + D);
  await page.waitForSelector('.brf-num');
  const items = await page.evaluate(() => [...document.querySelectorAll('.brf-num')].map(i => ({
    flow: i.classList.contains('is-flow'), nodes: [...i.querySelectorAll('.flow-node')].map(n => n.textContent),
    ops: [...i.querySelectorAll('.flow-op')].map(o => o.textContent), refs: [...i.querySelectorAll('.flow > .flow-node .flow-ref')].map(r => r.textContent + (r.dataset.go ? '' : '×')),
    name: (i.querySelector('.flow-name') || {}).textContent || '', lbls: [...i.querySelectorAll('.flow-lbl')].map(l => l.textContent),
    noteRefs: [...i.querySelectorAll('.note .flow-ref')].map(r => r.textContent), arts: [...i.querySelectorAll('.flow-art')].map(a => a.textContent),
    tip: (i.querySelector('.flow-ref[data-go]') || {}).title || '', text: i.textContent })));

  console.log('\n[① 기사 고리]');
  const a = items[0];
  check(a.flow && a.nodes.join('|') === '서울 입주 감소1|정비사업 이주비 부담2|고급 신축 설계 경쟁6' && a.ops.join('') === '→→',
        '화살표로 나눈 기사 카드 3개 + 번호 단추', a.nodes.join(' → '));
  check(/^1\. 서울 11월 입주 488가구 — 서울 11월 입주 예정 3개 단지/.test(a.tip), '번호 단추에 기사 제목·WHAT 이 뜬다', a.tip);
  console.log('\n[③ 흐름 이름·라벨]');
  check(a.name === '공급 절벽이 정비사업 비용으로 번진다' && a.lbls.join('|') === '연결 고리|다음에 볼 것' && a.noteRefs.join('') === '12',
        '"흐름:" 은 굵은 이름, "연결 고리:"·"다음에 볼 것:" 은 라벨, 설명 속 (1)(2) 도 단추', a.lbls.join(','));
  console.log('\n[④ 연결된 기사 목록]');
  check(a.arts.join('|') === '1. 서울 11월 입주 488가구|2. 강북 재개발 이주비 금리|6. 고급 아파트 하이필로티', '카드 아래 연결된 기사 제목 3개', a.arts.join(' / '));

  console.log('\n[② 누르면 그 기사로]');
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.click('.brf-num.is-flow .flow-ref[data-go="n2"]');
  await page.waitForTimeout(700);
  const go = await page.evaluate(() => { const t = [...document.querySelectorAll('.brf-art')].find(x => /강북 재개발/.test(x.textContent)); const r = t.getBoundingClientRect();
    return { flash: t.classList.contains('flow-flash'), inView: r.top >= 0 && r.top < innerHeight }; });
  check(go.flash && go.inView, '번호 2 를 누르면 2번 기사로 이동하고 빛난다');
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.click('.flow-art:text("6. 고급 아파트 하이필로티")');
  await page.waitForTimeout(700);
  check(await page.evaluate(() => [...document.querySelectorAll('.brf-art')].find(x => /하이필로티/.test(x.textContent)).classList.contains('flow-flash')), '아래 제목 목록을 눌러도 이동');

  console.log('\n[⑤ 여러 형식]');
  check(items[1].flow && items[1].refs.join(',') === '2,3쪽', '"(3쪽)" 은 지면 쪽 번호로 그 쪽 기사를 찾는다', items[1].refs.join(','));
  check(!items[2].flow && /주택 공급 → 금리 → 구매력/.test(items[2].text), '번호 없는 평범한 흐름 목록은 예전 그대로');
  check(items[3].flow && /없는 기사\(77\)/.test(items[3].nodes[0]) && items[3].refs.join(',') === '1', '못 찾은 번호(77)는 글자 그대로, 찾은 번호만 단추', items[3].nodes.join(' | '));
  await page.close();

  console.log('\n[⑥ 폰]');
  const ph = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await ph.goto(base + '/slack?date=' + D); await ph.waitForSelector('.brf-num.is-flow');
  const over = await ph.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  check(over <= 0, '폰 390px 에서 옆으로 안 넘친다', `${over}px`);
  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
