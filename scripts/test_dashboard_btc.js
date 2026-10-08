/**
 * test_dashboard_btc.js — 주가 대시보드 '₿ 비트코인'·'💱 원/달러 환율' 칸과 4장×2줄 배치 확인 (실제 Chromium)
 *
 * 가짜 서버가 stock/templates/index.html(서버가 실제로 내주는 파일 — app.py 가 templates/ 를 먼저 찾음)을 내주고
 * /api/indices · /api/crypto · /api/fx 를 흉내 낸다.
 *   ① 캡처 폭(1320px): 4장×2줄 — 1줄 지수 4개, 2줄 QLD·TQQQ·비트코인·환율, 모든 카드 같은 너비·양 끝 맞춤
 *      + 이름이 잘리지 않음 (2026-10-06 실제 서버: 출처 'Korea Investment API (real-time)' 가 길어 QLD·TQQQ 이름이 잘렸다)
 *   ② 비트코인 칸 내용: 원화 크게 · 등락 기준 · 달러/김프 한 줄 · 역대 최고가(ATH)·낙폭(+다르면 52주 최고가) · 10년 추이(로그 눈금, 연도 표시 — 2026-10-08 요청; 준비 전엔 30일)
 *      (2026-10-07 '52주만 나온다' 요청: ATH 를 모를 땐 52주만, 알면 ATH, ATH=52주면 한 줄만)
 *   ③ 환율 칸 내용(2026-10-07): 현재 환율 · 전일 대비 · 3년 최고/최저/고점 대비(2026-10-08 '3년 전 대비'에서 변경) · 3년 추이 그래프 + 연도 표시
 *   ④ 중간 폭(1000px): 2장씩 4줄 / 폰(390px): 1장씩, 가로 스크롤 없음
 *   ⑤ 거래소·환율 소스가 전부 실패해도 지수 6장은 그대로 + 그 자리만 안내 문구(배치 유지)
 *   ⑥ 달러만 살아 있으면 달러를 주인공으로 / 환율 추이가 없으면 현재 환율만
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
// 5년 추이(서버 index_history.get_long 모양) — 2026-10-08 요청. QLD 는 분할 보정 기록 포함
const LONG5 = (min, max, splits = []) => ({ points: Array.from({ length: 160 }, (_, i) => Math.round(50 + 40 * Math.sin(i / 25) * (i / 160))),
  from: '2021-10-08', to: '2026-10-08', years: 5, source: 'Naver', min, max, splits });
INDICES.KOSPI.long = LONG5(2284.7, 3512.3); INDICES.KOSDAQ.long = LONG5(651.2, 1060.0);
INDICES['S&P 500'].long = LONG5(3577.0, 6750.0); INDICES.NASDAQ.long = LONG5(10213.3, 22800.0);
INDICES.QLD.long = LONG5(18.1, 95.0, ['2022-01-13 2:1']); INDICES.TQQQ.long = LONG5(8.6, 91.0);
// 2026-10-06 서버 실측값(scripts/test_btc_price.py)과 같은 모양
const BTC_FULL = {
  krw: { price: 116190000, change_rate: -0.58, basis: '오전 9시 대비', source: 'Upbit',
         high_52w: 163325000, high_52w_date: '2025-10-06', dd_52w: -28.86,
         // 서버가 업비트 일봉 전체를 훑어 찾은 역대 최고가(52주 밖, 2021년) — 52주 최고가와 다른 경우
         ath: 179869000, ath_date: '2021-11-09', dd_ath: -35.4 },
  usd: { price: 85960, change_rate: -0.38, basis: '24시간 대비', source: 'Binance' },
  kimchi: { pct: 0.05, fx: 1351.0, basis: '환율' },
  sparkline: [20, 35, 30, 55, 70, 60, 45],
  // 서버가 빗썸 일봉으로 만든 10년 추이(로그 눈금 0~100)
  long: { points: Array.from({ length: 205 }, (_, i) => Math.round(i / 2.04 + 8 * Math.sin(i / 9))).map(v => Math.max(0, Math.min(100, v))),
          from: '2016-10-07', to: '2026-10-07', source: 'Bithumb', years: 10, log: true, min: 706383, max: 177033281 },
};
// 원/달러 환율: 3년(2023-10-09 ~ 2026-10-06) 일별을 줄인 그래프 점 + 요약
const FX_FULL = {
  price: 1385.5, change_rate: -0.42, basis: '전일 대비', source: 'Naver', history_source: 'ECB',
  history: { points: Array.from({ length: 160 }, (_, i) => Math.round(50 + 45 * Math.sin(i / 20))),
             from: '2023-10-09', to: '2026-10-06', high: 1487.6, high_date: '2024-12-27',
             low: 1305.2, low_date: '2024-07-16', start: 1352.1, from_high_pct: -6.86 },
};
let crypto = BTC_FULL;   // 테스트마다 바꿔 끼운다 (null = 전부 실패)
let fx = FX_FULL;

const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x').pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/api/indices') return send('application/json', JSON.stringify({ status: 'success', data: INDICES }));
  if (u === '/api/crypto') {
    if (crypto === 'http500') { res.writeHead(500); return res.end('boom'); }
    return send('application/json', JSON.stringify(crypto ? { status: 'success', data: { BTC: crypto } } : { status: 'error', data: null }));
  }
  if (u === '/api/fx') {
    if (fx === 'http500') { res.writeHead(500); return res.end('boom'); }
    return send('application/json', JSON.stringify(fx ? { status: 'success', data: { USDKRW: fx } } : { status: 'error', data: null }));
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
             w: Math.round(r.width), crypto: c.classList.contains('crypto-card'), fx: c.classList.contains('fx-card') };
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

  console.log('① 캡처 폭 1320px — 4장 × 2줄, 모두 같은 너비');
  let page = await open(1320);
  let l = await layout(page), R = rows(l);
  ok(l.length === 8, `카드 8장 (지수 6 + 비트코인 + 환율) → ${l.length}`);
  ok(R.length === 2 && R.every(r => r.length === 4), `2줄 × 4장 → ${R.map(r => r.length).join('+')}`);
  ok(R[0].every(c => !c.crypto && !c.fx), '1줄 = 지수 4개');
  ok(R[1][2] && R[1][2].crypto && R[1][3] && R[1][3].fx, '2줄 = QLD·TQQQ·비트코인·환율 순');
  const ws = l.map(c => c.w);
  ok(Math.max(...ws) - Math.min(...ws) <= 1, `8장 모두 같은 너비 (${[...new Set(ws)].join('/')}px)`);
  ok(R[0].every((c, i) => Math.abs(c.x - R[1][i].x) <= 1), '두 줄 칸 위치가 위아래로 딱 맞음(양 끝 포함)');
  ok(ws[0] >= 280, `카드 1장 폭 ≥ 280px (${ws[0]}px) — 숫자·그래프 여유`);
  const heads = await page.$$eval('#indices-grid .card-head', hs => hs.map(h => Math.round(h.getBoundingClientRect().height)));
  ok(Math.max(...heads) - Math.min(...heads) <= 2, `카드 머리(이름·출처) 높이가 모두 한 줄로 같음 (${[...new Set(heads)].join('/')}px)`);
  const natural = await page.$$eval('#indices-grid > .market-card', cs => cs.slice(4).map(c => {
    const last = c.lastElementChild.getBoundingClientRect(), top = c.getBoundingClientRect().top;
    return Math.round(last.bottom - top);   // 카드 위 ~ 마지막 내용 아래 = 실제 내용 높이
  }));
  ok(Math.max(...natural) - Math.min(...natural) <= 90, `2줄 카드 내용 높이 차이 ≤ 90px — 빈 공간 적게 (${natural.join('/')}px)`);
  const cut = await page.$$eval('#indices-grid .index-name', ns => ns.filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent.trim()));
  ok(cut.length === 0, `카드 이름이 하나도 안 잘림${cut.length ? ' → 잘림: ' + cut.join(', ') : ''}`);
  const qld = await page.$$eval('#indices-grid .market-card', cs => cs.map(c => c.querySelector('.card-head').innerText).filter(t => t.includes('QLD'))[0] || '');
  ok(qld.includes('QLD (2x)') && qld.includes('KIS 실시간'), `QLD 이름 + 짧은 출처 'KIS 실시간' (${qld.replace(/\n/g, ' | ')})`);
  const srcTitle = await page.$$eval('#indices-grid .source-tag', ts => ts.map(t => t.title).find(t => t.startsWith('Korea')));
  ok(srcTitle === 'Korea Investment API (real-time)', '출처 전체 이름은 마우스 올리면(title) 보임');
  const over = await page.$$eval('#indices-grid > .market-card', cs => cs.filter(c => c.scrollWidth > c.clientWidth + 1).length);
  ok(over === 0, '어느 카드도 글자가 옆으로 넘치지 않음');

  console.log('② 비트코인 칸 내용');
  const txt = await page.$eval('.crypto-card', e => e.innerText);
  ok(txt.includes('116,190,000원'), '원화 가격 116,190,000원');
  ok(/▼\s*-0\.58%/.test(txt), '원화 등락 ▼ -0.58%');
  ok(txt.includes('오전 9시 대비'), '등락 기준(오전 9시 대비) 표기');
  ok(txt.includes('$85,960') && txt.includes('-0.38%'), '달러 $85,960 · -0.38%');
  ok(txt.includes('김프') && txt.includes('+0.05%'), '김치 프리미엄(김프) +0.05%');
  ok(await page.$$eval('.crypto-card .crypto-sub', r => r.length) === 1, '달러·김프는 한 줄(카드 높이 절약)');
  ok(/환율 1,351\.0원/.test(await page.$eval('.crypto-card .crypto-sub [title]', e => e.title)), '김프 계산 기준·환율은 마우스 올리면(title) 보임');
  ok(txt.includes('역대 최고가') && txt.includes('179,869,000원') && txt.includes('21.11.09'), '역대 최고가 21.11.09 · 179,869,000원');
  ok(txt.includes('ATH 대비 낙폭') && txt.includes('-35.40%'), 'ATH 대비 낙폭 -35.40% (지수 칸과 같은 말)');
  ok(txt.includes('52주 최고') && txt.includes('25.10.06') && txt.includes('163,325,000원'), 'ATH 와 다르면 52주 최고가도 한 줄 (25.10.06 · 163,325,000원)');
  // 2026-10-07 미리보기에서 좁은 칸에 '179,869,000 / 원' 처럼 숫자·라벨이 두 줄로 꺾였다 → 상자 줄은 전부 한 줄이어야
  const tall = await page.$$eval('.crypto-card .ath-header, .fx-card .ath-header', hs =>
    hs.filter(h => h.getBoundingClientRect().height > 22).map(h => h.innerText.replace(/\s+/g, ' ')));
  ok(tall.length === 0, `비트코인·환율 상자 줄이 모두 한 줄${tall.length ? ' → 꺾임: ' + tall.join(' / ') : ''}`);
  const boxOver = await page.$$eval('.crypto-card .ath-box, .fx-card .ath-box', bs => bs.filter(b => b.scrollWidth > b.clientWidth + 1).length);
  ok(boxOver === 0, '상자 안 글자가 상자 밖으로 안 넘침');
  const barW = await page.$eval('.crypto-card .progress-bar-fill', e => parseFloat(e.style.width));
  ok(Math.abs(barW - (100 - 35.4 * 1.5)) < 0.1, `막대는 ATH 낙폭 기준 (${barW}%)`);
  ok(txt.includes('Upbit · Binance'), '출처 Upbit · Binance');
  ok(await page.$('.crypto-card .year-chart .sparkline-svg path') !== null, '10년 추이 선 그래프');
  const by = await page.$$eval('.crypto-card .fx-years span', ss => ss.map(e => e.textContent));
  ok(by[0] === '2016.10' && by[by.length - 1] === '2026.10' && by.length >= 4, `10년 그래프 아래 연도: ${by.join(' · ')}`);
  const blap = await page.$$eval('.crypto-card .fx-years span', ss => { const r = ss.map(e => e.getBoundingClientRect());
    const box = ss[0].parentElement.getBoundingClientRect();
    return r.some((a, i) => (i && a.left < r[i - 1].right + 6) || a.left < box.left - 1 || a.right > box.right + 1); });
  ok(!blap, '연도 글자끼리 안 겹치고 칸 밖으로 안 나감(솎아서 표시)');
  ok(await page.$$eval('.crypto-card .year-chart line', ls => ls.length) === 10, '해마다 세로 점선(2017~2026 10개)');
  const tag = await page.$eval('.crypto-card .chart-tag', e => e.textContent);
  ok(tag === '10년 · 로그', `왼쪽 위 꼬리표 '${tag}'`);
  const tip = await page.$eval('.crypto-card .year-chart', e => e.title);
  ok(tip.includes('로그 눈금') && tip.includes('Bithumb') && tip.includes('706,383원') && tip.includes('177,033,281원'), '마우스 올리면 출처·로그 눈금·최저/최고 설명');
  ok(await page.$eval('.crypto-card .ath-dd-pct', e => e.classList.contains('alert-level')), '-20% 넘게 빠지면 빨간 경고색(지수 칸과 같은 규칙)');
  const subTop = await page.$$eval('.crypto-card .crypto-sub > span', ss => ss.map(e => Math.round(e.getBoundingClientRect().top)));
  ok(new Set(subTop).size === 1, '좁아진 칸에서도 달러·김프가 한 줄에(줄바꿈 없음)');
  const dark = await page.$eval('.crypto-card .crypto-sub .down, .crypto-card .crypto-sub .up', e => getComputedStyle(e).color);
  ok(dark !== 'rgb(0, 0, 0)', `달러 등락률 색 적용(${dark})`);

  console.log('②-1 지수·ETF 5년 그래프');
  const idxCharts = await page.$$eval('#indices-grid > .market-card', cs => cs.slice(0, 4).concat(cs.slice(4, 6)).map(c => ({
    name: c.querySelector('.index-name').innerText.trim(), chart: !!c.querySelector('.year-chart'),
    tag: (c.querySelector('.chart-tag') || {}).textContent, years: [...c.querySelectorAll('.fx-years span')].map(e => e.textContent),
    title: (c.querySelector('.year-chart') || {}).title || '' })));
  ok(idxCharts.length === 6 && idxCharts.every(c => c.chart && c.tag === '5년'), `지수·ETF 6장 모두 5년 그래프 + '5년' 꼬리표`);
  ok(idxCharts.every(c => c.years[0] === '2021.10' && c.years[c.years.length - 1] === '2026.10' && c.years.length >= 4),
     `아래 연도: ${idxCharts[0].years.join(' · ')}`);
  const ilap = await page.$$eval('#indices-grid .fx-years', ys => ys.some(y => { const r = [...y.children].map(e => e.getBoundingClientRect());
    const box = y.getBoundingClientRect();
    return r.some((a, i) => (i && a.left < r[i - 1].right + 6) || a.left < box.left - 1 || a.right > box.right + 1); }));
  ok(!ilap, '8장 모든 그래프에서 연도 글자 안 겹치고 칸 밖으로 안 나감');
  const q = idxCharts.find(c => c.name.includes('QLD'));
  ok(q.title.includes('액면분할 보정: 2022-01-13 2:1') && q.title.includes('네이버'), 'QLD 그래프에 분할 보정 사실을 마우스 설명으로 밝힘');
  ok(idxCharts.find(c => c.name.includes('코스피')).title.includes('최저 2,284.70 ~ 최고 3,512.30'), '코스피 5년 최저~최고 설명');

  console.log('③ 환율 칸 내용');
  const fxt = await page.$eval('.fx-card', e => e.innerText);
  ok(fxt.includes('원/달러 환율'), '이름 원/달러 환율');
  ok(fxt.includes('1,385.50원'), '현재 환율 1,385.50원');
  ok(/▼\s*-0\.42%/.test(fxt) && fxt.includes('전일 대비'), '전일 대비 ▼ -0.42%');
  ok(fxt.includes('3년 최고') && fxt.includes('1,487.60원') && fxt.includes('24.12.27'), '3년 최고 1,487.60원 (24.12.27)');
  ok(fxt.includes('3년 최저') && fxt.includes('1,305.20원') && fxt.includes('24.07.16'), '3년 최저 1,305.20원 (24.07.16)');
  ok(fxt.includes('고점 대비') && fxt.includes('-6.86%') && !fxt.includes('3년 전 대비'), '3년 전 대비 → 고점 대비 -6.86%');
  ok(fxt.includes('Naver · ECB'), '출처 Naver · ECB');
  ok(await page.$('.fx-card .fx-chart .sparkline-svg path') !== null, '3년 추이 선 그래프');
  const yrs = await page.$$eval('.fx-card .fx-years span', ss => ss.map(e => e.textContent));
  // 2024 는 시작(2023.10)에서 너무 가까워(7.7%) 글자가 겹치므로 일부러 숨긴다(점선은 남음)
  ok(yrs[0] === '2023.10' && yrs[yrs.length - 1] === '2026.10' && yrs.includes('2025') && yrs.includes('2026') && !yrs.includes('2024'),
     `그래프 아래 연도: ${yrs.join(' · ')} (시작에 붙은 2024 는 숨김)`);
  const lap = await page.$$eval('.fx-card .fx-years span', ss => { const r = ss.map(e => e.getBoundingClientRect());
    return r.some((a, i) => i && a.left < r[i - 1].right - 1); });
  ok(!lap, '연도 글자끼리 겹치지 않음');
  ok(await page.$$eval('.fx-card .fx-chart line', ls => ls.length) === 3, '해 바뀌는 곳(2024·2025·2026년 1월)에 세로 점선 3개');
  const ylab = await page.$$eval('.fx-card .fx-years span', ss => { const c = ss[0].parentElement.getBoundingClientRect();
    return ss.every(e => { const r = e.getBoundingClientRect(); return r.left >= c.left - 1 && r.right <= c.right + 1; }); });
  ok(ylab, '연도 글자가 카드 밖으로 안 나감');
  const bar = await page.$eval('.fx-card .progress-bar-fill', e => parseFloat(e.style.width));
  ok(Math.abs(bar - (1385.5 - 1305.2) / (1487.6 - 1305.2) * 100) < 0.5, `막대 = 3년 최저~최고 사이 지금 위치 (${bar.toFixed(1)}%)`);
  await page.close();

  console.log('④-1 중간 폭 1000px — 2장씩');
  page = await open(1000);
  l = await layout(page); R = rows(l);
  ok(R.length === 4 && R.every(r => r.length === 2), `2장씩 4줄 → ${R.map(r => r.length).join('+')}`);
  ok(Math.max(...l.map(c => c.w)) - Math.min(...l.map(c => c.w)) <= 1, '모두 같은 너비');
  await page.close();

  console.log('④-2 폰 390px — 1장씩');
  page = await open(390);
  l = await layout(page);
  ok(new Set(l.map(c => c.x)).size === 1, '모두 한 줄에 1장');
  const hs = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  ok(!hs, '가로 스크롤 없음');
  ok(l.every(c => c.w === l[0].w), `비트코인·환율 폭 = 다른 카드 폭 (${l[0].w}px)`);
  await page.close();

  console.log('⑤ 거래소·환율 소스 전부 실패');
  for (const mode of [null, 'http500']) {
    crypto = mode; fx = mode;
    page = await open(1320);
    l = await layout(page);
    ok(l.filter(c => !c.crypto && !c.fx).length === 6, `지수 6장 그대로 (${mode || 'status=error'})`);
    const t = await page.$eval('.crypto-card', e => e.innerText);
    ok(t.includes('거래소 응답이 없습니다'), '비트코인 자리엔 안내 문구');
    const tf = await page.$eval('.fx-card', e => e.innerText);
    ok(tf.includes('환율 정보 응답이 없습니다'), '환율 자리엔 안내 문구');
    ok(rows(l).length === 2 && l.length === 8, '배치 그대로 4장 × 2줄');
    await page.close();
  }

  console.log('⑥ 달러만 살아 있음');
  crypto = { krw: null, usd: BTC_FULL.usd, kimchi: null, sparkline: [] };
  page = await open(1320);
  const t6 = await page.$eval('.crypto-card', e => e.innerText);
  ok(t6.includes('$85,960') && t6.includes('24시간 대비'), '달러가 주인공 + 24시간 대비');
  ok(!t6.includes('김프') && !t6.includes('52주') && !t6.includes('ATH'), '김프·52주·ATH 줄은 숨김');
  await page.close();

  console.log('⑦-00 지수 5년 추이 준비 전');
  const saved = INDICES.NASDAQ.long; delete INDICES.NASDAQ.long;
  page = await open(1320);
  const nq = await page.$$eval('#indices-grid > .market-card', cs => { const c = cs.find(x => x.innerText.includes('나스닥'));
    return { year: !!c.querySelector('.year-chart'), spark: !!c.querySelector('.sparkline-svg') }; });
  ok(!nq.year && nq.spark, '5년 추이가 아직 없는 칸은 예전 작은 그래프로(빈칸 없음)');
  await page.close();
  INDICES.NASDAQ.long = saved;

  console.log('⑦-0 10년 그래프 준비 전 / 업비트 예비(9년)');
  crypto = { ...BTC_FULL, long: null };
  page = await open(1320);
  ok(await page.$('.crypto-card .year-chart') === null && await page.$('.crypto-card .sparkline-svg path') !== null,
     '10년 추이 준비 전엔 30일 그래프(연도 없음)로 대신');
  await page.close();
  crypto = { ...BTC_FULL, long: { ...BTC_FULL.long, from: '2017-09-25', source: 'Upbit', years: 9 } };
  page = await open(1320);
  const t9y = await page.$eval('.crypto-card .chart-tag', e => e.textContent);
  const y9 = await page.$$eval('.crypto-card .fx-years span', ss => ss.map(e => e.textContent));
  ok(t9y === '9년 · 로그' && y9[0] === '2017.09', `업비트 예비면 있는 만큼만: '${t9y}', ${y9.join(' · ')} — 10년인 척 안 함`);
  await page.close();
  crypto = BTC_FULL;

  console.log('⑦ 역대 최고가 표시 경우별');
  crypto = { ...BTC_FULL, krw: { ...BTC_FULL.krw, ath: 163325000, ath_date: '2025-10-06', dd_ath: -28.86 } };
  page = await open(1320);
  const t8 = await page.$eval('.crypto-card', e => e.innerText);
  ok(t8.includes('역대 최고가') && !t8.includes('52주'), 'ATH = 52주 최고가면 같은 숫자 두 번 안 보임(ATH 한 줄만)');
  await page.close();
  const { ath, ath_date, dd_ath, ...noAth } = BTC_FULL.krw;
  crypto = { ...BTC_FULL, krw: noAth };
  page = await open(1320);
  const t9 = await page.$eval('.crypto-card', e => e.innerText);
  ok(!t9.includes('ATH') && t9.includes('52주 최고가') && t9.includes('최고가 대비') && t9.includes('-28.86%'),
     '서버가 아직 ATH 를 못 찾았으면 예전처럼 52주 최고가만(지어내지 않음)');
  await page.close();
  crypto = BTC_FULL;
  crypto = BTC_FULL;
  fx = { ...FX_FULL, history: null, history_source: null };
  page = await open(1320);
  const t7 = await page.$eval('.fx-card', e => e.innerText);
  ok(t7.includes('1,385.50원') && !t7.includes('3년') && t7.includes('Naver'), '환율 추이 없음 → 현재 환율만(3년 칸·그래프 숨김)');
  await page.close();

  await browser.close(); srv.close();
  console.log(`\n결과: ${pass} 통과 / ${fail} 실패`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
