/**
 * test_viewer_evidence.js — 지면 **근거 자동 형광펜** 확인 (실제 Chromium + 실제 tesseract)
 *
 * 요약(WHAT·WHY·HOW·표)에 쓴 숫자와 요약 GPT 가 JSON 에 적은 근거 문장(evidence.quote)을
 * 신문 사진 속 글자 위치에서 찾아 자동으로 형광펜을 칠하는 기능(2026-10-01).
 *
 *   ① 서버: scripts/news_page_text.py 가 낱말 위치를 page_words.json 에 저장 · 여러 단을 단별로 다시 정렬
 *           stock/news_files.page_words() 가 한 장씩 돌려준다(/api/news/pagewords)
 *   ② 숫자(8,807 → 지면 8807 · 76,952 → 7만6952)를 찾아 **그 글자 위**에 칠한다(기사 영역 bbox 안에서만)
 *   ③ 근거 문장(글자 인식이 몇 글자 틀려도) 찾기 · WHAT/WHY/HOW 색 구분
 *   ④ 옆 요약 칸: 찾은 숫자 = 밑줄(마우스 올리면 지면 위치 반짝, 누르면 확대), 못 찾은 숫자 = ⚠, 🧠 해석 배지
 *   ⑤ ✨ 버튼 / E 키로 끄고 켜기 · 사용자 형광펜(되돌리기·지우개)과 분리 · 저장소엔 끈 상태만
 *   ⑥ 폰(390px)에서도 지면 위 칠은 보인다(옆 칸은 PC 전용)
 *
 * tesseract 가 없으면 건너뛴다. 실행: npm i playwright && node scripts/test_viewer_evidence.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync, spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const HTML = path.join(ROOT, 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const D = '2026-10-01';

if (spawnSync('tesseract', ['--version']).status !== 0) {
  console.log('tesseract 가 없어 건너뜀 (sudo apt-get install -y tesseract-ocr tesseract-ocr-kor)');
  process.exit(0);
}

const BODY1 = '최근 1년 반 동안 전국에서 미분양 주택이 가장 많이 줄어든 곳은 대구·울산·경북인 것으로 나타났다. ' +
  '신규 분양이 크게 줄자 실수요가 쌓여 있던 재고를 흡수한 결과로 풀이된다. 30일 부동산R114에 따르면 ' +
  '대구 미분양은 2024년 말 8807가구에서 올해 상반기 말 4383가구로 4424가구 감소했다. 같은 기간 울산은 ' +
  '미분양이 4131가구에서 1359가구로 2772가구 감소했다. 경북은 6987가구에서 5284가구로 1703가구 줄었다. ' +
  '이들 지역의 미분양 감소세는 신규 공급이 줄어든 영향이 크다. 지난해 1월부터 올해 6월까지 대구에서 ' +
  '일반분양된 물량은 2642가구에 그쳤다. 같은 기간 경기에서는 7만6952가구가 분양됐다.';
const BODY2 = '수색비행장 안전구역의 93%가 해제돼 21.3㎢에서 1.5㎢로 축소된다. 상암동 156만㎡, 수색동 64만㎡ 등이 ' +
  '포함됐다. 국방부는 장기간 이어진 건축물 높이 제한을 완화한다고 밝혔다. 주민들은 재개발 기대감을 나타냈다.';
const PAGE = `<html><body style="margin:0;background:#f7f4ec;width:1600px;font-family:'WenQuanYi Zen Hei','Noto Sans CJK KR',sans-serif;color:#111">
<div id="a1" style="padding:40px 50px 30px"><div style="font-size:60px;font-weight:bold">새 아파트 공급 뜸해지자 대구 미분양 절반으로</div>
<div style="columns:3;column-gap:44px;font-size:25px;line-height:1.7;margin-top:24px;text-align:justify">${BODY1}</div></div>
<div id="a2" style="padding:30px 50px 50px;border-top:3px solid #333"><div style="font-size:54px;font-weight:bold">수색 상암 비행안전구역 해제</div>
<div style="columns:3;column-gap:44px;font-size:25px;line-height:1.7;margin-top:22px;text-align:justify">${BODY2}</div></div>
</body></html>`;

// 요약 — 기사1 은 JSON(쪽·영역·근거), 기사2 는 사진 번호만(영역 없음) + 지면에 없는 숫자 9,999
const BRIEF = (bbox) => `[신문요약 1/1]
1. 🔵 새 아파트 공급 뜸해지자…대구 미분양 절반으로 ‘뚝’
• WHAT: 대구 미분양이 2024년 말 8,807가구에서 2026년 6월 4,383가구로 4,424가구 줄었음.
| 지역 | 2024년 말 | 2026년 6월 |
| 울산 | 4,131 | 1,359 |
• WHY: 신규 분양이 줄자 실수요가 재고를 흡수했음.
• HOW: (해석) 경기는 76,952가구가 분양돼 대구와 공급 차이가 컸음.
• 사진: 01

2. 수색·상암 비행안전구역 해제
• WHAT: 안전구역의 93%가 해제돼 21.3㎢에서 1.5㎢로 축소됨. 주민 9,999가구가 혜택.
• WHY: 높이 제한 완화.
• HOW: 상암동 156만㎡ 포함.
• 사진: 01

\`\`\`json
{"date":"${D}","articles":[{"article_id":"x-1","title":"새 아파트 공급 뜸해지자…대구 미분양 절반으로 ‘뚝’","page":1,"bbox":${JSON.stringify(bbox)},
 "evidence":[{"k":"WHAT","quote":"대구 미분양은 2024년 말 8807가구에서","nums":["8807가구","4383가구"]},
             {"k":"WHY","quote":"신규 분양이 크게 줄자 실수요가 쌓여 있던 재고를 흡수한 결과로","nums":[]},
             {"k":"HOW","src":"해석"}]}]}
\`\`\``;

(async () => {
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const browser = await chromium.launch({ executablePath: CHROME });

  // ── 가짜 지면을 그려 사진으로 · 서버 스크립트로 읽히기 ───────────────────
  const cache = fs.mkdtempSync(path.join(os.tmpdir(), 'evid-'));
  const dir = path.join(cache, D); fs.mkdirSync(dir);
  const shot = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  await shot.setContent(PAGE);
  const geo = await shot.evaluate(() => {
    const H = document.documentElement.scrollHeight, W = 1600;
    const b = id => { const r = document.getElementById(id).getBoundingClientRect(); return [r.left / W, r.top / H, r.width / W, r.height / H].map(v => +v.toFixed(4)); };
    return { a1: b('a1'), a2: b('a2') };
  });
  await shot.screenshot({ path: path.join(dir, '01.jpg'), type: 'jpeg', quality: 85, fullPage: true });
  await shot.close();
  fs.writeFileSync(path.join(dir, 'index.json'), JSON.stringify({ date: D, images: [{ name: '01.jpg' }] }));
  console.log('\n[① 서버: 낱말 위치 저장]');
  const t0 = Date.now();
  const run = spawnSync('python3', [path.join(ROOT, 'scripts', 'news_page_text.py'), D, '--quiet'],
    { env: { ...process.env, NEWS_CACHE_DIR: cache }, encoding: 'utf8' });
  check(run.status === 0, 'news_page_text.py 가 성공', `${((Date.now() - t0) / 1000).toFixed(0)}초 ${run.stderr.slice(-200)}`);
  const words = JSON.parse(fs.readFileSync(path.join(dir, 'page_words.json'), 'utf8'));
  const pg = words.pages['01.jpg'];
  check(pg && pg.segs.length > 10 && pg.W === 1600, 'page_words.json 에 낱말 위치가 저장된다', `조각 ${pg && pg.segs.length}개`);
  // 단 다시 정렬: 본문 첫 단에 "최근…" 과 "8807" 이 같은 단(같은 번호) 안에서 위→아래로
  const colText = {};
  pg.segs.forEach(s => { colText[s[0]] = (colText[s[0]] || '') + s[5].map(w => w[0]).join(''); });
  // 가짜 지면: 첫 단 "최근 1년 반 … 따르면 대" / 둘째 단 "구 미분양은 2024년 말 8807가구에서 …"
  const c1 = Object.values(colText).find(t => t.includes('최근')) || '', c2 = Object.values(colText).find(t => t.includes('8807')) || '';
  check(c1 && c2 && c1 !== c2 && /^구?미분양은2024년말8807/.test(c2) && /흡수한결과로/.test(c1) && !/1359|8807/.test(c1),
        '여러 단을 단별로 다시 정렬(첫 단·둘째 단 글자가 섞이지 않고, 한 줄이 둘로 쪼개지지 않음)', c2.slice(0, 18));
  const again = spawnSync('python3', [path.join(ROOT, 'scripts', 'news_page_text.py'), D],
    { env: { ...process.env, NEWS_CACHE_DIR: cache }, encoding: 'utf8' });
  check(/그대로 1/.test(again.stdout), '한 번 읽은 장은 다시 읽지 않는다', again.stdout.trim().split('\n').pop());
  const pwOut = execFileSync('python3', ['-c',
    `import sys,json;sys.path.insert(0,${JSON.stringify(path.join(ROOT, 'stock'))});import news_files as n;` +
    `print(json.dumps([n.page_words("${D}","01.jpg")["ok"], n.page_words("${D}","../01.jpg")["ok"], n.page_words("${D}","99.jpg")["ok"], n.page_words("bad","01.jpg")["ok"]]))`],
    { env: { ...process.env, NEWS_CACHE_DIR: cache }, encoding: 'utf8' });
  check(pwOut.trim() === '[true, true, false, false]', 'news_files.page_words(): 있는 장만 · 경로 조작(../)은 이름만 쓰고 · 잘못된 날짜 거부', pwOut.trim());

  // ── 웹 ───────────────────────────────────────────────────────────────
  const srv = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x'), u = url.pathname;
    const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
    if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
    if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D,
      messages: [{ ts: D + 'T06:44:00', source: 'user', kind: 'text', text: BRIEF(geo.a1) }] }));
    if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 1,
      images: [{ name: '01.jpg', url: '/img/01.jpg', thumb: '/img/01.jpg', download_url: '/img/01.jpg' }] }));
    if (u === '/api/news/pagetext') return send('application/json', '{"ok":false}');
    if (u === '/api/news/pagewords') {
      const out = execFileSync('python3', ['-c', `import sys,json;sys.path.insert(0,${JSON.stringify(path.join(ROOT, 'stock'))});import news_files as n;` +
        `print(json.dumps(n.page_words(${JSON.stringify(url.searchParams.get('date'))},${JSON.stringify(url.searchParams.get('name'))})))`],
        { env: { ...process.env, NEWS_CACHE_DIR: cache }, encoding: 'utf8' });
      return send('application/json', out);
    }
    if (u === '/img/01.jpg') return send('image/jpeg', fs.readFileSync(path.join(dir, '01.jpg')));
    res.writeHead(404); res.end();
  });
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const waitImg = (page) => page.waitForFunction(() => {
    const im = document.getElementById('lb-img');
    return im.complete && im.naturalWidth > 0 && V.fitW > 0 && Math.abs(im.getBoundingClientRect().width - V.fitW * V.zoom) < 2;
  });
  // 그림판에서 자동 형광펜 색(노랑·초록·파랑 계열)으로 칠해진 점 수
  const ink = (page) => page.evaluate(() => {
    const cv = document.getElementById('lb-mark'); const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 16) if (d[i] > 40) n++; return n;
  });

  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
  await page.goto(base + '/slack');
  await page.waitForFunction(() => document.querySelectorAll('.brf-side img').length === 2);
  await page.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="view"]').click());
  await waitImg(page);
  await page.waitForFunction(() => AUTO.res && AUTO.res.rects.length > 0, null, { timeout: 15000 });

  console.log('\n[② 숫자를 그 글자 위에]');
  const r = await page.evaluate(() => {
    const R = AUTO.res, arts = noteArts();
    const a1 = R.arts.get(arts.find(a => /대구/.test(artTitle(a)))), a2 = R.arts.get(arts.find(a => /수색/.test(artTitle(a))));
    return { n: R.rects.length, kinds: [...new Set(R.rects.map(x => x.kind + x.k))].sort().join(','),
      a1: a1.nums.map(x => x.raw + (x.found ? '✓' : '✗')).join(' '), a2: a2.nums.map(x => x.raw + (x.found ? '✓' : '✗')).join(' '),
      r8807: R.rects.filter(x => x.key === '8807').map(x => x.r), interp: [...a1.interp].join(',') };
  });
  const w8807 = pg.segs.flatMap(s => s[5]).filter(w => w[0].includes('8807'));
  const overlap = (a, b) => !(a[0] + a[2] < b[1] || b[1] + b[3] < a[0] || a[1] + a[3] < b[2] || b[2] + b[4] < a[1]);
  check(r.r8807.length === 1 && w8807.length && overlap(r.r8807[0], w8807[0]), '"8,807" → 지면의 "8807" 글자 위에 정확히 한 군데', JSON.stringify(r.r8807[0]));
  check(/8807✓/.test(r.a1) && /4383✓/.test(r.a1) && /4424✓/.test(r.a1) && /4131✓/.test(r.a1) && /1359✓/.test(r.a1),
        'WHAT·표의 숫자를 지면에서 찾는다', r.a1);
  check(/76952✓/.test(r.a1), '요약 "76,952" ↔ 지면 "7만6952" 같은 숫자로 인식');
  const inBox = r.r8807.every(x => x[0] / 1e4 >= geo.a1[0] - 0.02 && x[1] / 1e4 <= geo.a1[1] + geo.a1[3] + 0.02);
  check(inBox, '기사 영역(bbox) 안에서만 찾는다');
  // (가짜 지면의 "1.5㎢"·"156만㎡" 는 tesseract 가 "1.51ㅠ"·"「" 로 잘못 읽는다 — 인식 한계라 요구하지 않음)
  check(/93%✓/.test(r.a2) && /21\.3✓/.test(r.a2) && /9999✗/.test(r.a2),
        '영역 없는 기사도 찾고, 지면에 없는 숫자(9,999)는 "못 찾음"', r.a2);
  check(/qWHY/.test(r.kinds) && /nWHAT/.test(r.kinds), '근거 문장(WHY)도 찾아 칠한다 · WHAT/WHY/HOW 구분', r.kinds);
  check(r.interp === 'HOW', '"해석" 표시를 읽는다(HOW)', r.interp);
  const ink1 = await ink(page);
  check(ink1 > 200, '그림판에 실제로 칠해졌다', `칠해진 점 ${ink1}`);

  console.log('\n[④ 옆 요약 칸]');
  const nt = await page.evaluate(() => {
    const b = document.getElementById('lb-note');
    return { ok: [...b.querySelectorAll('.num-ok')].map(e => e.textContent), miss: [...b.querySelectorAll('.num-miss')].map(e => e.textContent),
      interp: b.querySelectorAll('.nt-interp').length, head: (b.querySelector('.nt-auto') || {}).textContent || '' };
  });
  check(nt.ok.includes('8,807') && nt.ok.includes('76,952'), '찾은 숫자는 밑줄 표시', nt.ok.slice(0, 6).join(' '));
  check(nt.miss.includes('9,999') && !nt.miss.includes('8,807'), '못 찾은 숫자는 ⚠', nt.miss.join(' '));
  check(!nt.ok.includes('6') && !nt.miss.includes('6'), '"6월"의 6 같은 짧은 숫자는 판단하지 않는다');
  check(nt.interp === 1, '🧠 해석 배지(HOW)');
  check(/근거 \d+곳/.test(nt.head) && /못 찾음 \d+개/.test(nt.head), '머리에 요약 한 줄', nt.head);
  check(!nt.miss.includes('2026') && !nt.miss.includes('2024'), '연도(2026 등)는 ⚠ 하지 않는다 — 요약이 "올해"를 연도로 바꿔 쓰는 일이 잦아서');
  const ink0 = await ink(page);
  if (process.env.KEEP) console.log('cache', cache);
  await page.hover('#lb-note .num-ok >> text=8,807');
  await page.waitForTimeout(80);
  check(await page.evaluate(() => AUTO.flash) === '8807' && (await ink(page)) > ink0, '숫자에 마우스를 올리면 지면 위치에 빨간 테두리');
  await page.click('#lb-note .num-ok >> text=8,807');
  await page.waitForTimeout(150);
  check(await page.evaluate(() => V.zoom) > 1.5, '누르면 그 자리로 확대', `배율 ${(await page.evaluate(() => V.zoom)).toFixed(2)}`);

  console.log('\n[⑤ 끄고 켜기 · 사용자 형광펜과 분리]');
  await page.evaluate(() => { V.zoom = 1; measure(); });
  await waitImg(page);
  const before = await ink(page);
  await page.click('#lb-auto');
  check(await ink(page) < before / 5 && await page.evaluate(() => localStorage.getItem('digest.lbAuto')) === '0',
        '✨ 누르면 자동 형광펜이 사라지고, 끈 상태만 저장');
  check(await page.evaluate(() => !document.querySelector('#lb-note .num-ok')), '끄면 옆 칸 표시도 사라진다');
  await page.keyboard.press('e');
  check(await ink(page) > before / 2 && await page.evaluate(() => localStorage.getItem('digest.lbAuto')) === '1', 'E 키로 다시 켜기');
  // 사용자 형광펜: 긋고 되돌려도 자동 표시는 그대로
  await page.click('#lb-pen');
  const ib = await page.evaluate(() => { const b = document.getElementById('lb-img').getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; });
  await page.mouse.move(ib[0] + ib[2] * 0.1, ib[1] + ib[3] * 0.95); await page.mouse.down();
  await page.mouse.move(ib[0] + ib[2] * 0.5, ib[1] + ib[3] * 0.95, { steps: 6 }); await page.mouse.up();
  check(await page.evaluate(() => (M.marks['01.jpg'] || []).length) === 1, '형광펜 긋기는 그대로 된다');
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(50);
  check(await page.evaluate(() => (M.marks['01.jpg'] || []).length === 0 && AUTO.res.rects.length > 0) && await ink(page) > before / 2,
        '되돌리기는 내가 그은 줄만 지운다(자동 표시는 남음)');
  const keys = await page.evaluate(() => { const k = []; for (let i = 0; i < localStorage.length; i++) k.push(localStorage.key(i)); return k.sort().join(','); });
  check(keys === 'digest.lbAuto', '저장소엔 켜고 끈 상태 하나뿐(형광펜·위치 저장 0)', keys);
  await page.close();

  console.log('\n[⑥ 폰 390px]');
  const ph = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  const pp = await ph.newPage();
  await pp.goto(base + '/slack');
  await pp.waitForFunction(() => document.querySelectorAll('.brf-side img').length === 2);
  await pp.evaluate(() => document.querySelectorAll('.brf-side')[0].querySelector('[data-act="view"]').click());
  await waitImg(pp);
  await pp.waitForFunction(() => AUTO.res && AUTO.res.rects.length > 0, null, { timeout: 15000 });
  const bar = await pp.evaluate(() => document.querySelector('.lb-bar').scrollWidth - document.querySelector('.lb-bar').clientWidth);
  check(await ink(pp) > 50 && await pp.isVisible('#lb-auto'), '폰에서도 지면 위 자동 형광펜과 ✨ 버튼');
  check(bar <= 0, '폰 상단 바가 넘치지 않는다', `${bar}px`);

  await browser.close(); srv.close();
  if (!process.env.KEEP) fs.rmSync(cache, { recursive: true, force: true }); else console.log('캐시 보존:', cache);
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
