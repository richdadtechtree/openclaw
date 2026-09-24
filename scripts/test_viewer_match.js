/**
 * test_viewer_match.js — 요약 기사 ↔ 신문 사진 **지면 글자 대조 자동 연결** 확인 (실제 Chromium + 실제 tesseract)
 *
 * 요약(ChatGPT)에 "• 사진: 07" 이 없어도, 서버가 사진 속 글자를 읽어 둔 것(news_page_text.py)과
 * 요약 기사를 맞춰 보고 그 장을 기사 옆에 붙이는지 본다.
 *
 *   ① 가짜 신문 지면 4장을 실제 브라우저로 그려 사진(JPG 3장 + GIF 1장)으로 만든다
 *   ② news_page_text.py 로 글자를 읽고, news_files.page_tokens() 로 웹이 받을 모양을 만든다
 *   ③ 서버(Python)와 웹(JS)의 조각 뽑기 규칙이 **똑같은지** 확인
 *   ④ 요약 기사 3개가 각자 맞는 장(01 · 02 · 04=GIF)에 자동으로 붙는다, "자동" 이라고 표시된다
 *   ⑤ 지면에 없는 기사는 **짐작하지 않는다**(지면 찾아 연결 버튼)
 *   ⑥ 직접 연결(📌)과 요약문의 "• 사진: NN" 이 자동 대조보다 우선한다
 *
 * 필요: tesseract + 한국어 (sudo apt-get install -y tesseract-ocr tesseract-ocr-kor). 없으면 건너뛴다.
 * 실행: npm i playwright && node scripts/test_viewer_match.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const HTML = path.join(ROOT, 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

try { execFileSync('tesseract', ['--list-langs'], { stdio: 'pipe' }); }
catch (e) { console.log('tesseract 가 없어 건너뜀 (sudo apt-get install -y tesseract-ocr tesseract-ocr-kor)'); process.exit(0); }

// 가짜 지면: 장마다 기사 2개(큰 제목 + 3단 본문). 요약과 겹치는 숫자·낱말이 들어 있다.
const PAGES = [
  [['“3억대 서울 분양도 나와”…추석 후 청약 큰장', '10월 수도권에서 1만8000여 가구가 공급될 예정이다. 서울은 고덕강일3단지 1305가구, 고척 푸르지오 힐스테이트 1008가구, 강남권 반값 아파트 등이 포함된다. 서울 3.3㎡당 평균 아파트값이 높은 가운데 3억~5억원대 분양 단지가 등장했다. 분양가상한제 공공분양은 시세차익이 클 수 있으나 청약자격과 소득 자산 기준, 거주의무와 전매제한을 확인해야 한다.'],
   ['코스피 외국인 순매수 사흘째', '외국인이 반도체 대형주를 중심으로 순매수에 나서며 지수가 강보합으로 마감했다. 증권가는 실적 시즌을 앞두고 수급이 개선될 것으로 봤다.']],
  [['재건축·재개발로 공공임대 8.3만가구', '서울 정비사업 496곳의 계획물량은 51만5817가구이며 공공임대는 8만2793가구로 약 16%를 차지한다. 사업단계별로 구역지정 52곳 5840가구, 추진위 73곳 5965가구, 조합설립 124곳 1만2647가구, 건축심의 44곳 5826가구, 착공 62곳 4847가구다. 절반가량이 사업 초기 단계라 입주까지 시간이 오래 걸린다.'],
   ['전세대출 금리 다시 상승', '시중은행 전세대출 금리가 두 달 만에 상승세로 돌아섰다. 서울 아파트 전세 수요가 늘면서 대출 잔액도 증가했다.']],
  [['원전 출력제한 보상금 논란', '태양광 확대로 원전 출력제한이 늘면서 보상금 규모가 커지고 있다. 송전망과 ESS 투자가 함께 필요하다는 지적이 나온다.'],
   ['현대차 휴머노이드 공장 투입', '현대차가 RMAC 확대와 함께 휴머노이드 로봇을 울산 공장에 투입한다. 2027년까지 단계적으로 적용 범위를 넓힌다.']],
  [['목동 9·13단지 최고 49층 재건축', '목동9단지는 49층 41개동 3958가구, 13단지는 49층 26개동 3852가구로 계획됐다. 통합심의로 사업 속도를 높인다. 서울시는 녹지와 상업가로를 함께 정비한다.'],
   ['수색·상암 비행안전구역 해제', '수색비행장 안전구역의 93%가 해제돼 21.3㎢에서 1.5㎢로 축소됐다. 상암동 156만㎡, 수색동 64만㎡ 등이 포함된다.']],
];
const pageHtml = arts => `<html><body style="margin:0;background:#f7f4ec;width:1600px;font-family:'WenQuanYi Zen Hei','Noto Sans CJK KR',sans-serif;color:#111">
<div style="padding:40px 50px;border-bottom:4px double #333;font-size:28px">매일경제 · 2026년 9월 24일 목요일</div>
${arts.map(([h, b]) => `<div style="padding:34px 50px;border-bottom:1px solid #999"><div style="font-size:64px;font-weight:bold;line-height:1.25">${h}</div>
<div style="columns:3;column-gap:40px;font-size:25px;line-height:1.7;margin-top:22px;text-align:justify">${(b + ' ').repeat(2)}</div></div>`).join('')}</body></html>`;

// 요약: 기사 4개 — 3개는 지면에 있음(순서 섞음, 사진 번호 없음), 1개는 지면에 없음
const BRIEF = [
  '*[신문요약 1/6] 📰 2026년 9월 24일 신문 브리핑*',
  '🔴 재건축·재개발로 공공임대 8.3만가구 중요한 이유: 서울 정비사업의 속도가 공공임대 공급 시기를 좌우함.',
  '• WHAT: 서울 정비사업 496곳의 계획물량은 51만5817가구이며 공공임대는 8만2793가구, 약 16%임.',
  '• WHY: 절반가량이 사업 초기 단계라 입주까지 시간이 오래 걸림.',
  '🔴 “3억대 서울 분양도 나와”…추석 후 청약 큰장',
  '• WHAT: 10월 수도권에서 1만8000여 가구가 공급될 예정임. 서울은 고덕강일3단지 1305가구, 고척 푸르지오 힐스테이트 1008가구 등이 포함됨.',
  '• WHY: 서울 3.3㎡당 평균 아파트값이 높은 가운데 3억~5억원대 분양 단지가 등장함.',
  '• HOW: 청약자격, 소득·자산, 거주의무와 전매제한을 확인해야 함.',
  '목동 9·13단지 최고 49층 재건축',
  '• WHAT: 목동9단지는 49층·41개동·3958가구, 13단지는 49층·26개동·3852가구로 계획됨.',
  '• WHY: 통합심의로 사업 속도를 높이려는 것임.',
  '일본은행 추가 금리 인상 시사',
  '• WHAT: 일본은행 총재가 연내 추가 인상 가능성을 언급함.',
  '• WHY: 엔화 약세와 물가 상승이 이어지고 있음.',
].join('\n');

(async () => {
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const browser = await chromium.launch({ executablePath: CHROME });

  console.log('\n[① 가짜 지면 사진 만들기 · ② 글자 읽기]');
  const cache = fs.mkdtempSync(path.join(os.tmpdir(), 'newscache-'));
  const D = '2026-09-24', day = path.join(cache, D);
  fs.mkdirSync(day);
  const shot = await browser.newPage({ viewport: { width: 1600, height: 2000 } });
  const names = [];
  for (let i = 0; i < PAGES.length; i++) {
    await shot.setContent(pageHtml(PAGES[i]));
    const jpg = path.join(day, `0${i + 1}.jpg`);
    await shot.screenshot({ path: jpg, type: 'jpeg', quality: 80, fullPage: true });
    names.push(`0${i + 1}.jpg`);
  }
  await shot.close();
  // 4번째 장은 GIF 로 (실제 지면도 GIF 가 섞여 온다) — Pillow 가 있을 때만 변환
  try {
    execFileSync('python3', ['-c', `from PIL import Image;import os;p='${day}/04.jpg';Image.open(p).convert('P',palette=Image.ADAPTIVE).save('${day}/04.gif');os.remove(p)`]);
    names[3] = '04.gif';
  } catch (e) { console.log('  (Pillow 없음 → 04 는 JPG 로 시험)'); }
  fs.writeFileSync(path.join(day, 'index.json'), JSON.stringify({ images: names.map(name => ({ name })) }));
  const env = { ...process.env, NEWS_CACHE_DIR: cache };
  const t0 = Date.now();
  execFileSync('python3', [path.join(ROOT, 'scripts', 'news_page_text.py'), D, '--quiet'], { env });
  check(true, `사진 ${names.length}장 글자 읽기 완료`, `${((Date.now() - t0) / 1000).toFixed(1)}초`);
  const again = Date.now();
  execFileSync('python3', [path.join(ROOT, 'scripts', 'news_page_text.py'), D, '--quiet'], { env });
  check(Date.now() - again < 1500, '두 번째 실행은 이미 읽은 장을 건너뛴다(빠름)', `${Date.now() - again}ms`);
  const PAGETEXT = execFileSync('python3', ['-c',
    `import sys,json;sys.path.insert(0,'${path.join(ROOT, 'stock')}');import news_files as n;print(json.dumps(n.page_tokens('${D}'),ensure_ascii=False))`],
    { env }).toString();
  const pt = JSON.parse(PAGETEXT);
  check(pt.ok && pt.n === 4, 'news_files.page_tokens() 가 4장 조각을 돌려준다', `조각 ${Object.values(pt.pages).map(v => v.length).join('/')}`);

  const srv = http.createServer((req, res) => {
    const u = req.url.split('?')[0];
    const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
    if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
    if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D,
      messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] }));
    if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 4,
      images: names.map(n => ({ name: n, url: '/img/' + n, thumb: '/img/' + n, download_url: '/img/' + n })) }));
    if (u === '/api/news/pagetext') return send('application/json', PAGETEXT);
    if (u.startsWith('/img/')) return send(u.endsWith('gif') ? 'image/gif' : 'image/jpeg', fs.readFileSync(path.join(day, u.slice(5))));
    res.writeHead(404); res.end();
  });
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(base + '/slack?x');
  await page.evaluate(d => { state.date = d; load(); loadNews(); }, D);   // 테스트 날짜로 고정
  await page.waitForSelector('.brf-art');

  console.log('\n[③ 서버·웹 조각 규칙이 같은가]');
  const sample = '서울 정비사업 496곳의 51만5817가구, 3.3㎡당 ESS·RMAC 확대를 확인해야 한다';
  const py = JSON.parse(execFileSync('python3', ['-c',
    `import sys,json;sys.path.insert(0,'${path.join(ROOT, 'scripts')}');import news_page_text as t;print(json.dumps(sorted(t.tokens(sys.argv[1])),ensure_ascii=False))`, sample]).toString());
  const js = await page.evaluate(s => [...pageTokens(s)].sort(), sample);
  check(JSON.stringify(py) === JSON.stringify(js), 'Python tokens() 와 JS pageTokens() 결과가 똑같다', `${py.length}개`);

  console.log('\n[④ 자동 연결]');
  await page.click('.viewseg [data-view="paper"]');
  await page.waitForFunction(() => PT.data && document.querySelectorAll('.brf-side').length === 4);
  const sides = () => page.evaluate(() => [...document.querySelectorAll('.brf-art')].map(a => {
    const s = a.querySelector('.brf-side');
    return { t: (a.querySelector('.brf-title') || {}).textContent.slice(0, 14),
             no: (s.querySelector('.side-no') || {}).textContent || '', src: (s.querySelector('.side-src') || {}).textContent || '',
             empty: !!s.querySelector('.side-empty') };
  }));
  let s = await sides();
  const scores = await page.evaluate(() => [...document.querySelectorAll('.brf-art')].map(a => {
    const m = matchPage(a.querySelector('.brf-main').textContent, newsState.images.map(i => i.name));
    return m ? `${m.name}:${m.score.toFixed(1)}/${m.second.toFixed(1)}` : '-'; }));
  console.log('     점수(1등/2등): ' + scores.join('  '));
  check(s[0].no === '02' && /자동/.test(s[0].src), '"공공임대 8.3만가구" → 02번 장, "자동" 표시', s[0].src);
  check(s[1].no === '01', '"3억대 서울 분양" → 01번 장');
  check(s[2].no === '04', '"목동 49층 재건축" → 04번 장(GIF 사진)');
  check(s[3].empty, '지면에 없는 "일본은행" 기사는 짐작하지 않는다(📌 지면 찾아 연결)');

  console.log('\n[⑥ 우선순위]');
  await page.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="pick"]').click());
  await page.waitForSelector('#lb:not([hidden])');
  await page.click('#lb-next');                // 02 → 03
  await page.click('#lb-pick');
  s = await sides();
  check(s[0].no === '03' && /직접 연결/.test(s[0].src), '직접 연결(📌)이 자동 대조보다 우선', s[0].src);

  await browser.close(); srv.close();
  fs.rmSync(cache, { recursive: true, force: true });
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
