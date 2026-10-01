/**
 * test_viewer_evidence.js — 지면 **낱말 위치** 저장 확인 (실제 Chromium 으로 그린 가짜 지면 + 실제 tesseract)
 *
 * 2026-10-01 '근거 자동 형광펜'(요약 숫자·근거 문장을 지면에 자동으로 칠하기)을 만들었다가
 * **가독성이 떨어져 웹 화면에서는 걷어냈다**(사용자 요청, 다른 방법 고민 중).
 * 서버가 저장하는 낱말 위치(page_words.json)는 다음 방법에 다시 쓸 수 있어 남겨 두고, 그 부분만 검사한다.
 *
 *   ① scripts/news_page_text.py 가 낱말 위치를 page_words.json 에 저장
 *   ② 여러 단 지면을 단별로 다시 정렬(옆 단 글자가 섞이지 않고, 한 줄이 둘로 쪼개지지 않음)
 *   ③ 한 번 읽은 장은 다시 읽지 않음 · stock/news_files.page_words() 가 한 장씩 돌려줌(/api/news/pagewords)
 *
 * tesseract 가 없으면 건너뛴다. 실행: npm i playwright && node scripts/test_viewer_evidence.js
 */
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync, spawnSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
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

  await browser.close();
  if (!process.env.KEEP) fs.rmSync(cache, { recursive: true, force: true }); else console.log('캐시 보존:', cache);
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
