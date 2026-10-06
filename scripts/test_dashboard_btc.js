/**
 * test_dashboard_btc.js — 주가 대시보드 '₿ 비트코인' 칸과 4칸 배치 확인 (실제 Chromium)
 *
 * 가짜 서버가 stock/templates/index.html(서버가 실제로 내주는 파일 — app.py 가 templates/ 를 먼저 찾음)을 내주고 /api/indices · /api/crypto 를 흉내 낸다.
 *   ① 캡처 폭(1320px): 2줄 — 1줄 지수 4개(같은 너비), 2줄 QLD·TQQQ·비트코인 3개(같은 너비), 양 끝 맞춤
 *      + 이름이 잘리지 않음 (2026-10-06 실제 서버: 출처 'Korea Investment API (real-time)' 가 길어 QLD·TQQQ 이름이 잘렸다)
 *   ② 비트코인 칸 내용: 원화 크게 · 등락 기준 · 달러 · 김치 프리미엄 · 52주 최고가 대비 · 30일 추이
 *   ③ 중간 폭(1000px): 2칸 — 비트코인은 맨 아래 한 줄 통째
 *   ④ 폰(390px): 1칸 — 비트코인이 옆으로 넘치지 않음(가로 스크롤 없음)
 *   ⑤ 거래소가 전부 실패해도 지수 6장은 그대로 + 비트코인 자리만 안내 문구
 *   ⑥ 달러만 살아 있으면 달러를 주인공으로 표시
 *   ⑦ 캡처가 기다리는 '#indices-grid .price-value' 가 나온다(슬랙 15:40 캡처 안 깨짐)
 *
 * 실행: node scripts/test_dashboard_btc.js   (개발 환경 전용, 서버엔 불필요)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'templates', 'index.html');   // 실제로 나가는 파일
const HTML_COPY = path.join(__dirname, '..', 'stock', 'index.html');            // 예비 사본(둘이 같아야 함)
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const idx = (cur, ch, ath) => ({ current: cur, change_rate: ch, ath, ath_change_rate: (cur / ath - 1) * 100,
  source: 'Naver Finance', sparkline: [10, 40, 30, 60, 50, 80] });
const INDICES = {
  'KOSPI': idx(3412.5, 0.42, 3500), 'KOSDAQ': idx(865.2, -0.31, 1229.42),
  'S&P 500': idx(6702.1, 0.12, 7620.9), 'NASDAQ': idx(22650.3, -0.25, 27190.21),
  'QLD': idx(88.4, 1.1, 101.19), 'TQQQ': idx(72.3, 1.6, 88.09),
};
// 실제 서버 응답처럼 QLD·TQQQ 는 한투 실시간(긴 출처 이름)
INDICES.QLD.source = INDICES.TQQQ.source = 'Korea Investment API (real-time)';
// 2026-10-06 서버 실측값(scripts/test_btc_price.py)과 같은 모양
const BTC_FULL = {
  krw: { price: 116190000, change_rate: -0.58, basis: '오전 9시 대비', source: 'Upbit',
         high_52w: 163325000, high_52w_date: '2025-10-06', dd_52w: -28.86 },
  usd: { price: 85960, change_rate: -0.38, basis: '24시간 대비', source: 'Binance' },
  kimchi: { pct: 0.05, fx: 1351.0, basis: '환율' },
  sparkline: [20, 35, 30, 55, 70, 60, 45],
};
let crypto = BTC_FULL;   // 테스트마다 바꿔 끼운다 (null = 전부 실패)

const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x').pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/api/indices') return send('application/json', JSON.stringify({ status: 'success', data: INDICES }));
  if (u === '/api/crypto') {
    if (crypto === 'http500') { res.writeHead(500); return res.end('boom'); }
    return send('application/json', JSON.stringify(crypto ? { status: 'success', data: { BTC: crypto } } : { status: 'error', data: null }));
  }
  // 나머지(알람·관심종목·요약)는 이 테스트 대상이 아니라 '데이터 없음'으로 둔다
  if (u.startsWith('/api/')) return send('application/json', '{"status":"error"}');
  res.writeHead(404); res.end();
});

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) { pass++; console.log('  ✅', m); } else { fail++; console.log('  ❌', m); } };

// 카드들의 위치를 줄(row)별로 묶어 돌려준다
async function layout(page) {
  return page.$$eval('#indices-grid > .market-card', cs => cs.map(c => {
    const r = c.getBoundingClientRect();
    return { name: c.querySelector('.index-name').textContent.trim(), x: Math.round(r.left), y: Math.round(r.top),
             w: Math.round(r.width), crypto: c.classList.contains('crypto-card') };
  }));
}
const rows = l => { const m = {}; l.forEach(c => (m[c.y] = m[c.y] || []).push(c)); return Object.values(m); };

(async () => {
  await new Promise(r => srv.listen(0, r));
  const URL0 = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await chromium.launch({ executablePath: fs.existsSync(CHROME) ? CHROME : undefined });

  async function open(width) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    // 국기 이미지(flagcdn)·폰트는 외부라 막아서 테스트가 인터넷에 기대지 않게
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
    await page.goto(URL0);
    await page.waitForSelector('#indices-grid .price-value', { timeout: 10000 });
    await page.waitForTimeout(200);
    return page;
  }

  console.log('⓪ 화면 파일 두 벌이 같은지');
  ok(fs.readFileSync(HTML, 'utf8') === fs.readFileSync(HTML_COPY, 'utf8'),
     'stock/templates/index.html = stock/index.html (한쪽만 고치면 서버엔 반영 안 될 수 있음)');

  console.log('① 캡처 폭 1320px — 1줄 4개 · 2줄 3개');
  let page = await open(1320);
  let l = await layout(page), R = rows(l);
  ok(l.length === 7, `카드 7장 (지수 6 + 비트코인 1) → ${l.length}`);
  ok(R.length === 2, `2줄 → ${R.length}줄`);
  ok(R[0].length === 4 && R[0].every(c => !c.crypto), '1줄 = 지수 4개');
  ok(R[1] && R[1].length === 3 && R[1][2].crypto, '2줄 = QLD·TQQQ + 비트코인');
  const one = R[0][0].w, btc = l.find(c => c.crypto);
  const spread = r => Math.max(...r.map(c => c.w)) - Math.min(...r.map(c => c.w));
  ok(spread(R[0]) <= 1, `1줄 4장 같은 너비 (${R[0].map(c => c.w).join('/')}px)`);
  ok(spread(R[1]) <= 1, `2줄 3장 같은 너비 (${R[1].map(c => c.w).join('/')}px)`);
  ok(Math.abs(R[0][0].x - R[1][0].x) <= 1, '두 줄 왼쪽 끝 맞음');
  const right = Math.max(...R[0].map(c => c.x + c.w)), right2 = btc.x + btc.w;
  ok(Math.abs(right - right2) <= 1, '두 줄 오른쪽 끝 맞음(빈칸 없음)');
  ok(one >= 280, `카드 1장 폭 ≥ 280px (${one}px) — 숫자·스파크라인 여유`);
  const heads = await page.$$eval('#indices-grid .card-head', hs => hs.map(h => Math.round(h.getBoundingClientRect().height)));
  ok(Math.max(...heads) - Math.min(...heads) <= 2, `카드 머리(이름·출처) 높이가 모두 한 줄로 같음 (${[...new Set(heads)].join('/')}px)`);
  const natural = await page.$$eval('#indices-grid > .row2', cs => cs.map(c => {
    const last = c.lastElementChild.getBoundingClientRect(), top = c.getBoundingClientRect().top;
    return Math.round(last.bottom - top);   // 카드 위 ~ 마지막 내용 아래 = 실제 내용 높이
  }));
  ok(Math.max(...natural) - Math.min(...natural) <= 70, `2줄 카드 내용 높이 차이 ≤ 70px — 빈 공간 적게 (${natural.join('/')}px)`);
  const cut = await page.$$eval('#indices-grid .index-name', ns => ns.filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent.trim()));
  ok(cut.length === 0, `카드 이름이 하나도 안 잘림${cut.length ? ' → 잘림: ' + cut.join(', ') : ''}`);
  const qld = await page.$$eval('#indices-grid .market-card', cs => cs.map(c => c.querySelector('.card-head').innerText).filter(t => t.includes('QLD'))[0] || '');
  ok(qld.includes('QLD (2x)') && qld.includes('KIS 실시간'), `QLD 이름 + 짧은 출처 'KIS 실시간' (${qld.replace(/\n/g, ' | ')})`);
  const srcTitle = await page.$eval('.row2:not(.crypto-card) .source-tag', e => e.title);
  ok(srcTitle === 'Korea Investment API (real-time)', '출처 전체 이름은 마우스 올리면(title) 보임');

  console.log('② 비트코인 칸 내용');
  const txt = await page.$eval('.crypto-card', e => e.innerText);
  ok(txt.includes('116,190,000원'), '원화 가격 116,190,000원');
  ok(/▼\s*-0\.58%/.test(txt), '원화 등락 ▼ -0.58%');
  ok(txt.includes('오전 9시 대비'), '등락 기준(오전 9시 대비) 표기');
  ok(txt.includes('$85,960') && txt.includes('-0.38%'), '달러 $85,960 · -0.38%');
  ok(txt.includes('김프') && txt.includes('+0.05%'), '김치 프리미엄(김프) +0.05%');
  ok(await page.$$eval('.crypto-card .crypto-sub', r => r.length) === 1, '달러·김프는 한 줄(카드 높이 절약)');
  ok(/환율 1,351\.0원/.test(await page.$eval('.crypto-card .crypto-sub [title]', e => e.title)), '김프 계산 기준·환율은 마우스 올리면(title) 보임');
  ok(txt.includes('52주 최고가') && txt.includes('163,325,000원') && txt.includes('-28.86%'), '52주 최고가 대비 -28.86%');
  ok(txt.includes('25.10.06'), '52주 최고가 날짜 25.10.06');
  ok(txt.includes('Upbit · Binance'), '출처 Upbit · Binance');
  ok(await page.$('.crypto-card .sparkline-svg path') !== null, '30일 추이 선 그래프');
  ok(await page.$eval('.crypto-card .ath-dd-pct', e => e.classList.contains('alert-level')), '-20% 넘게 빠지면 빨간 경고색(지수 칸과 같은 규칙)');
  const overflow = await page.$eval('.crypto-card', e => e.scrollWidth > e.clientWidth + 1);
  ok(!overflow, '비트코인 칸 안 글자가 넘치지 않음');
  const dark = await page.$eval('.crypto-card .crypto-sub .down, .crypto-card .crypto-sub .up', e => getComputedStyle(e).color);
  ok(dark !== 'rgb(0, 0, 0)', `달러 등락률 색 적용(${dark})`);
  await page.close();

  console.log('③ 중간 폭 1000px — 2칸');
  page = await open(1000);
  l = await layout(page); R = rows(l);
  ok(R.length === 4 && R.slice(0, 3).every(r => r.length === 2), '지수 6장이 2장씩 3줄');
  ok(R[3] && R[3].length === 1 && R[3][0].crypto, '비트코인은 맨 아래 한 줄 통째');
  ok(Math.abs(R[3][0].w - (R[0][1].x + R[0][1].w - R[0][0].x)) <= 1, '비트코인 폭 = 2칸 전체');
  await page.close();

  console.log('④ 폰 390px — 1칸');
  page = await open(390);
  l = await layout(page);
  ok(new Set(l.map(c => c.x)).size === 1, '모두 한 줄에 1장');
  const hs = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  ok(!hs, '가로 스크롤 없음(비트코인 span 2 가 화면을 밀지 않음)');
  const bw = l.find(c => c.crypto).w, iw = l[0].w;
  ok(bw === iw, `비트코인 폭 = 다른 카드 폭 (${bw} = ${iw})`);
  await page.close();

  console.log('⑤ 거래소 전부 실패');
  for (const mode of [null, 'http500']) {
    crypto = mode;
    page = await open(1320);
    l = await layout(page);
    ok(l.filter(c => !c.crypto).length === 6, `지수 6장 그대로 (${mode || 'status=error'})`);
    const t = await page.$eval('.crypto-card', e => e.innerText);
    ok(t.includes('거래소 응답이 없습니다'), '비트코인 자리엔 안내 문구(배치 유지)');
    ok(rows(l).length === 2, '배치 그대로 2줄');
    await page.close();
  }

  console.log('⑥ 달러만 살아 있음');
  crypto = { krw: null, usd: BTC_FULL.usd, kimchi: null, sparkline: [] };
  page = await open(1320);
  const t6 = await page.$eval('.crypto-card', e => e.innerText);
  ok(t6.includes('$85,960') && t6.includes('24시간 대비'), '달러가 주인공 + 24시간 대비');
  ok(!t6.includes('김프') && !t6.includes('52주'), '김프·52주 줄은 숨김');
  await page.close();

  await browser.close(); srv.close();
  console.log(`\n결과: ${pass} 통과 / ${fail} 실패`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
