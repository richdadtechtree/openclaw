/**
 * test_dashboard_btc.js — 주가 대시보드 '₿ 비트코인'·'💱 원/달러 환율' 칸과 4장×2줄 배치 확인 (실제 Chromium)
 *
 * 가짜 서버가 stock/templates/index.html(서버가 실제로 내주는 파일 — app.py 가 templates/ 를 먼저 찾음)을 내주고
 * /api/indices · /api/crypto · /api/fx · /api/charts?period= 를 흉내 낸다.
 *   ⑧ 그래프 기간 선택(2026-10-08): 6개월·1년·3년·5년·10년 버튼 → 8장 그래프가 한꺼번에, 짧은 기간은 '월' 눈금,
 *      고른 기간 기억(localStorage)·?period= 우선·받아 둔 기간은 다시 안 받음·환율 상자도 기간을 따라감
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
// 그래프(서버 charts.get_charts 모양): 기간마다 {values(실제 값), from, to, years, high, low, ...}
const PFROM = { '6m': '2026-04-08', '1y': '2025-10-08', '3y': '2023-10-09', '5y': '2021-10-08', '10y': '2016-10-07' };
const PYRS = { '6m': 0.5, '1y': 1, '3y': 3, '5y': 5, '10y': 10 };
// lo~hi 사이를 오가는 160점(첫 점 = lo, 가운데 = hi 를 정확히 포함), 끝 = cur
function mk(per, lo, hi, cur, extra = {}) {
  const n = 160, v = Array.from({ length: n }, (_, i) => lo + (hi - lo) * (0.5 - 0.5 * Math.cos(i / (n - 1) * Math.PI * 2)));
  v[0] = lo; v[Math.floor(n / 2)] = hi; v[n - 1] = cur;
  const mn = Math.min(...v), mx = Math.max(...v);
  return { values: v.map(x => +x.toFixed(4)), from: extra.from || PFROM[per], to: '2026-10-08', years: extra.years || PYRS[per],
    high: mx, high_date: extra.high_date || '2024-12-27', low: mn, low_date: extra.low_date || '2024-07-16',
    from_high_pct: +((cur / mx - 1) * 100).toFixed(2), change_pct: 0, log: mx / mn > 5, source: extra.source || 'Naver',
    splits: extra.splits || [] };
}
function chartsFor(per) {
  const k = { '6m': 0.97, '1y': 0.93, '3y': 0.8, '5y': 1, '10y': 0.55 }[per];   // 기간마다 최저가 다르게
  return {
    'KOSPI': per === '5y' ? mk(per, 2284.7, 3512.3, 3412.5) : mk(per, 3500 * k * 0.9, 3512.3, 3412.5),
    'KOSDAQ': mk(per, 651.2, 1060.0, 865.2), 'S&P 500': mk(per, 3577.0 / k, 6750.0, 6702.1),
    'NASDAQ': mk(per, 10213.3, 22800.0, 22650.3),
    // 레버리지 ETF: 5년·10년은 5배↑(→ 로그 자동), 짧은 기간은 덜 움직임(보통 눈금)
    'QLD': mk(per, ['5y', '10y'].includes(per) ? 18.1 : 95 * k * 0.8, 95.0, 88.4, { splits: ['2022-01-13 2:1'] }),
    'TQQQ': mk(per, ['5y', '10y'].includes(per) ? 8.6 : 91 * k * 0.75, 91.0, 72.3),
    'BTC': per === '10y' ? mk(per, 706383, 177033281, 116190000, { source: 'Bithumb' })
                         : mk(per, 116190000 * k * 0.8, 163325000, 116190000, { source: 'Bithumb' }),
    'USDKRW': mk(per, 1305.2, 1487.6, 1385.5, { source: 'ECB' }),
  };
}
let chartOverride = {};      // 테스트마다 특정 칸을 null 등으로 바꿔 끼운다
const chartReqs = [];        // /api/charts 요청 기록(받아 둔 기간은 다시 안 받는지)
// 2026-10-06 서버 실측값(scripts/test_btc_price.py)과 같은 모양
const BTC_FULL = {
  krw: { price: 116190000, change_rate: -0.58, basis: '오전 9시 대비', source: 'Upbit',
         high_52w: 163325000, high_52w_date: '2025-10-06', dd_52w: -28.86,
         // 서버가 업비트 일봉 전체를 훑어 찾은 역대 최고가(52주 밖, 2021년) — 52주 최고가와 다른 경우
         ath: 179869000, ath_date: '2021-11-09', dd_ath: -35.4 },
  usd: { price: 85960, change_rate: -0.38, basis: '24시간 대비', source: 'Binance' },
  kimchi: { pct: 0.05, fx: 1351.0, basis: '환율' },
  sparkline: [20, 35, 30, 55, 70, 60, 45],
};
// 원/달러 환율(현재값·전일 대비). 추이·기간 최고/최저는 /api/charts 의 USDKRW
const FX_FULL = { price: 1385.5, change_rate: -0.42, basis: '전일 대비', source: 'Naver', history_source: 'ECB' };
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
  if (u === '/api/charts') {
    const per = new URL(req.url, 'http://x').searchParams.get('period') || '5y';
    chartReqs.push(per);
    return send('application/json', JSON.stringify({ status: 'success', period: per, data: { ...chartsFor(per), ...chartOverride } }));
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

  async function open(width, query = '') {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    // 국기 이미지(flagcdn)·폰트는 외부라 막아서 테스트가 인터넷에 기대지 않게
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, r => r.abort());
    await page.goto(URL0 + query);
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
  ok(await page.$('.crypto-card .year-chart .sparkline-svg path') !== null, '기간 추이 선 그래프(기본 5년)');
  const by = await page.$$eval('.crypto-card .fx-years span', ss => ss.map(e => e.textContent));
  ok(by[0] === '2021.10' && by[by.length - 1] === '2026.10' && by.length >= 4, `5년 그래프 아래 연도: ${by.join(' · ')}`);
  const tag = await page.$eval('.crypto-card .chart-tag', e => e.textContent);
  ok(tag === '5년', `왼쪽 위 꼬리표 '${tag}' (5년엔 5배 미만이라 보통 눈금)`);
  const tip = await page.$eval('.crypto-card .year-chart', e => e.title);
  ok(tip.includes('Bithumb') && tip.includes('기간 최저') && !tip.includes('로그'), '마우스 올리면 출처·기간 최저/최고 설명');
  ok(await page.$eval('.crypto-card .ath-dd-pct', e => e.classList.contains('alert-level')), '-20% 넘게 빠지면 빨간 경고색(지수 칸과 같은 규칙)');
  const subTop = await page.$$eval('.crypto-card .crypto-sub > span', ss => ss.map(e => Math.round(e.getBoundingClientRect().top)));
  ok(new Set(subTop).size === 1, '좁아진 칸에서도 달러·김프가 한 줄에(줄바꿈 없음)');
  const dark = await page.$eval('.crypto-card .crypto-sub .down, .crypto-card .crypto-sub .up', e => getComputedStyle(e).color);
  ok(dark !== 'rgb(0, 0, 0)', `달러 등락률 색 적용(${dark})`);

  console.log('②-1 지수·ETF 그래프(기본 5년)');
  const idxCharts = await page.$$eval('#indices-grid > .market-card', cs => cs.slice(0, 4).concat(cs.slice(4, 6)).map(c => ({
    name: c.querySelector('.index-name').innerText.trim(), chart: !!c.querySelector('.year-chart'),
    tag: (c.querySelector('.chart-tag') || {}).textContent, years: [...c.querySelectorAll('.fx-years span')].map(e => e.textContent),
    title: (c.querySelector('.year-chart') || {}).title || '' })));
  ok(idxCharts.length === 6 && idxCharts.every(c => c.chart && c.tag.startsWith('5년')), `지수·ETF 6장 모두 5년 그래프 (${idxCharts.map(c => c.tag).join(' / ')})`);
  ok(idxCharts.find(c => c.name.includes('TQQQ')).tag === '5년 · 로그' && idxCharts.find(c => c.name.includes('코스피')).tag === '5년',
     '5배 넘게 움직인 TQQQ 만 로그(자동), 코스피는 보통 눈금');
  ok(idxCharts.every(c => c.years[0] === '2021.10' && c.years[c.years.length - 1] === '2026.10' && c.years.length >= 4),
     `아래 연도: ${idxCharts[0].years.join(' · ')}`);
  const ilap = await page.$$eval('#indices-grid .fx-years', ys => ys.some(y => { const r = [...y.children].map(e => e.getBoundingClientRect());
    const box = y.getBoundingClientRect();
    return r.some((a, i) => (i && a.left < r[i - 1].right + 6) || a.left < box.left - 1 || a.right > box.right + 1); }));
  ok(!ilap, '8장 모든 그래프에서 연도 글자 안 겹치고 칸 밖으로 안 나감');
  const q = idxCharts.find(c => c.name.includes('QLD'));
  ok(q.title.includes('액면분할 보정: 2022-01-13 2:1') && q.title.includes('네이버'), 'QLD 그래프에 분할 보정 사실을 마우스 설명으로 밝힘');
  ok(idxCharts.find(c => c.name.includes('코스피')).title.includes('기간 최저 2,284.70 ~ 최고 3,512.30'), '코스피 기간 최저~최고 설명');

  console.log('②-2 5년 그래프 기준 가로선(코스피·코스닥 -30% 실선 / QLD·TQQQ -10% 점선)');
  const refs = await page.$$eval('#indices-grid > .market-card', cs => cs.map(c => {
    const l = c.querySelector('.ref-line'), t = c.querySelector('.ref-label');
    return { name: c.querySelector('.index-name').innerText.trim(), has: !!l,
             dash: l ? l.getAttribute('stroke-dasharray') : null, y: l ? +l.getAttribute('y1') : null,
             label: t ? t.textContent : '', title: (c.querySelector('.year-chart') || {}).title || '' };
  }));
  const R2 = n => refs.find(r => r.name.includes(n));
  ok(R2('코스피').has && !R2('코스피').dash && R2('코스닥').has && !R2('코스닥').dash, '코스피·코스닥: 가로선(실선)');
  ok(R2('QLD').dash && R2('TQQQ').dash, 'QLD·TQQQ: 가로선(점선)');
  ok(!R2('S&P').has && !R2('나스닥').has && !R2('비트코인').has && !R2('환율').has, 'S&P·나스닥·비트코인·환율엔 선 없음');
  ok(R2('코스피').label === '-30% 2,450' && R2('QLD').label === '-10% 91.07', `선 라벨: 코스피 '${R2('코스피').label}', QLD '${R2('QLD').label}'`);
  const expY = 52 - ((3500 * 0.7 - 2284.7) / (3512.3 - 2284.7)) * 48;
  ok(Math.abs(R2('코스피').y - expY) < 0.2, `코스피 선 높이 = ATH 3,500 × 0.7 = 2,450 위치 (y ${R2('코스피').y} ≈ ${expY.toFixed(1)})`);
  ok(R2('TQQQ').title.includes('역대 최고가 88.09 대비 -10% = 79.28'), 'TQQQ 마우스 설명에 기준선 계산식');
  await page.close();
  // 기준선이 5년 최저보다 아래면 그래프 범위를 넓혀 선이 보이게
  chartOverride = { KOSPI: mk('5y', 3000, 3512.3, 3412.5) };
  page = await open(1320);
  const low = await page.$$eval('#indices-grid > .market-card', cs => { const l = cs[0].querySelector('.ref-line');
    const pts = cs[0].querySelector('.year-chart path[fill="none"]').getAttribute('d').match(/[\d.]+,[\d.]+/g).map(s => +s.split(',')[1]);
    return { y: +l.getAttribute('y1'), maxY: Math.max(...pts) }; });
  ok(Math.abs(low.y - 52) < 0.2 && low.maxY < 52 - 5, `선이 5년 최저보다 낮으면 범위를 넓혀 맨 아래에 보임 (선 y ${low.y}, 그래프 최저점 y ${low.maxY.toFixed(1)})`);
  await page.close();
  chartOverride = {};
  page = await open(1320);

  console.log('③ 환율 칸 내용');
  const fxt = await page.$eval('.fx-card', e => e.innerText);
  ok(fxt.includes('원/달러 환율'), '이름 원/달러 환율');
  ok(fxt.includes('1,385.50원'), '현재 환율 1,385.50원');
  ok(/▼\s*-0\.42%/.test(fxt) && fxt.includes('전일 대비'), '전일 대비 ▼ -0.42%');
  ok(fxt.includes('5년 최고') && fxt.includes('1,487.60원') && fxt.includes('24.12.27'), '5년 최고 1,487.60원 (24.12.27) — 상자도 고른 기간');
  ok(fxt.includes('5년 최저') && fxt.includes('1,305.20원') && fxt.includes('24.07.16'), '5년 최저 1,305.20원 (24.07.16)');
  ok(fxt.includes('고점 대비') && fxt.includes('-6.86%') && !fxt.includes('3년 전 대비'), '고점 대비 -6.86%');
  ok(fxt.includes('Naver · ECB'), '출처 Naver · ECB');
  ok(await page.$('.fx-card .fx-chart .sparkline-svg path') !== null, '환율 추이 선 그래프');
  const bar = await page.$eval('.fx-card .progress-bar-fill', e => parseFloat(e.style.width));
  ok(Math.abs(bar - (1385.5 - 1305.2) / (1487.6 - 1305.2) * 100) < 0.5, `막대 = 기간 최저~최고 사이 지금 위치 (${bar.toFixed(1)}%)`);
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

  console.log('⑦-00 지수 추이 준비 전');
  chartOverride = { NASDAQ: null };
  page = await open(1320);
  const nq = await page.$$eval('#indices-grid > .market-card', cs => { const c = cs.find(x => x.innerText.includes('나스닥'));
    return { year: !!c.querySelector('.year-chart'), spark: !!c.querySelector('.sparkline-svg') }; });
  ok(!nq.year && nq.spark, '추이가 아직 없는 칸은 예전 작은 그래프로(빈칸 없음)');
  await page.close();
  chartOverride = {};

  console.log('⑦-0 비트코인 추이 준비 전 / 업비트 예비(9년)');
  chartOverride = { BTC: null }; crypto = BTC_FULL;
  page = await open(1320);
  ok(await page.$('.crypto-card .year-chart') === null && await page.$('.crypto-card .sparkline-svg path') !== null,
     '기간 추이 준비 전엔 30일 그래프(연도 없음)로 대신');
  await page.close();
  chartOverride = { BTC: mk('10y', 2.1e6, 177033281, 116190000, { from: '2017-09-25', years: 9, source: 'Upbit' }) };
  page = await open(1320, '?period=10y');
  const t9y = await page.$eval('.crypto-card .chart-tag', e => e.textContent);
  const y9 = await page.$$eval('.crypto-card .fx-years span', ss => ss.map(e => e.textContent));
  ok(t9y === '9년 · 로그' && y9[0] === '2017.09', `업비트 예비면 있는 만큼만: '${t9y}', ${y9.join(' · ')} — 10년인 척 안 함`);
  await page.close();
  chartOverride = {};
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
  fx = { ...FX_FULL, history_source: null };
  chartOverride = { USDKRW: null };
  page = await open(1320);
  const t7 = await page.$eval('.fx-card', e => e.innerText);
  ok(t7.includes('1,385.50원') && !t7.includes('최고') && !(await page.$('.fx-card .year-chart')) && t7.includes('Naver'),
     '환율 추이 없음 → 현재 환율만(기간 상자·그래프 숨김)');
  await page.close();
  chartOverride = {}; fx = FX_FULL;

  console.log('⑧ 그래프 기간 선택(6개월·1년·3년·5년·10년)');
  page = await open(1320);
  const tabs = await page.$$eval('#period-tabs button', bs => bs.map(b => ({ t: b.textContent, on: b.classList.contains('active') })));
  ok(tabs.map(b => b.t).join(',') === '6개월,1년,3년,5년,10년' && tabs.find(b => b.on).t === '5년', '버튼 5개, 처음엔 5년(슬랙 캡처도 5년)');
  const tagsOf = () => page.$$eval('#indices-grid .chart-tag', ts => ts.map(t => t.textContent));
  const labelsOf = sel => page.$$eval(sel + ' .fx-years span', ss => ss.map(e => e.textContent));
  const clickP = async t => { await page.click(`#period-tabs button:text-is("${t}")`); await page.waitForTimeout(300); };
  await clickP('1년');
  let tg = await tagsOf();
  ok(tg.length === 8 && tg.every(t => t === '1년'), `1년: 8장 모두 '1년' (${[...new Set(tg)].join('/')})`);
  let lb = await labelsOf('#indices-grid > .market-card:first-child');
  ok(lb[0] === '2025.10' && lb[lb.length - 1] === '2026.10' && lb.some(x => x.endsWith('월')), `1년은 '월' 눈금: ${lb.join(' · ')}`);
  // 2026년 1월은 시작 글자(2025.10)에 너무 붙어(23%) 글자는 숨지만, 해 바뀜 세로 점선은 남는다
  const janLine = await page.$$eval('#indices-grid > .market-card:first-child .year-chart line', ls => ls.map(l => +l.getAttribute('x1')));
  const janX = 4 + ((Date.UTC(2026, 0, 1) - Date.UTC(2025, 9, 8)) / (Date.UTC(2026, 9, 8) - Date.UTC(2025, 9, 8))) * 272;
  ok(janLine.some(x => Math.abs(x - janX) < 1.5), `1년: 해 바뀜(2026-01) 세로 점선은 그려짐 (x≈${janX.toFixed(1)})`);
  ok((await page.$eval('.fx-card', e => e.innerText)).includes('1년 최고'), '환율 상자도 1년 최고/최저로');
  await clickP('6개월');
  tg = await tagsOf(); lb = await labelsOf('.fx-card');
  ok(tg.every(t => t === '6개월') && lb[0] === '2026.04' && lb.some(x => x.endsWith('월')), `6개월: 꼬리표 '6개월', ${lb.join(' · ')}`);
  await clickP('10년');
  tg = await tagsOf();
  const btcTag = await page.$eval('.crypto-card .chart-tag', e => e.textContent);
  ok(btcTag === '10년 · 로그' && tg.every(t => t.startsWith('10년')) && tg[0] === '10년', `10년: 비트코인 '${btcTag}'(250배 → 로그 자동), 코스피 '${tg[0]}'`);
  ok(await page.$$eval('.crypto-card .year-chart line', ls => ls.length) === 10, '10년 연도 눈금 점선 10개(2017~2026)');
  ok(await page.$$eval('#indices-grid .ref-line', ls => ls.length) === 4, '기간을 바꿔도 기준 가로선 4개 그대로');
  const allLap = await page.$$eval('#indices-grid .fx-years', ys => ys.some(y => { const r = [...y.children].map(e => e.getBoundingClientRect());
    const box = y.getBoundingClientRect();
    return r.some((a, i) => (i && a.left < r[i - 1].right + 6) || a.left < box.left - 1 || a.right > box.right + 1); }));
  ok(!allLap, '10년에서도 날짜 글자 안 겹치고 칸 밖으로 안 나감');
  const nBefore = chartReqs.length;
  await clickP('1년'); await clickP('10년');
  ok(chartReqs.length === nBefore, '이미 받은 기간으로 돌아가면 다시 안 받음(즉시 바뀜)');
  await page.reload(); await page.waitForSelector('#indices-grid .year-chart'); await page.waitForTimeout(300);
  ok(await page.$eval('#period-tabs button.active', b => b.textContent) === '10년' && (await tagsOf())[0] === '10년', '새로고침해도 고른 기간(10년) 기억');
  await page.close();
  page = await open(1320, '?period=3y');
  lb = await labelsOf('.fx-card');
  ok(await page.$eval('#period-tabs button.active', b => b.textContent) === '3년'
     && lb[0] === '2023.10' && lb.includes('2025') && lb.includes('2026') && !lb.includes('2024'), `주소 ?period=3y 우선 · 3년 연도 ${lb.join(' · ')} (시작에 붙은 2024 는 숨김)`);
  ok(await page.$$eval('.fx-card .year-chart line', ls => ls.length) === 3, '3년: 해 바뀜 점선 3개(2024·2025·2026)');
  await page.close();
  page = await open(390);
  const tabFit = await page.$eval('#period-tabs', e => { const r = e.getBoundingClientRect(); return r.right <= innerWidth && e.scrollWidth <= e.clientWidth + 1; });
  const hs2 = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  ok(tabFit && !hs2, '폰 390px: 기간 버튼이 화면 안에 다 들어가고 가로 스크롤 없음');
  await page.close();

  await browser.close(); srv.close();
  console.log(`\n결과: ${pass} 통과 / ${fail} 실패`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
