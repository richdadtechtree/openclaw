/**
 * test_viewer_table.js — 요약 속 **표** 와 요약 앞머리 처리 확인 (실제 Chromium)
 *
 * 2026-09-24 실제 슬랙 메시지([신문요약 수정본 1/7])를 그대로 넣어 본다.
 * 슬랙의 표는 메시지 text 에 없고 blocks 에만 있어서, 서버(stock/app.py _merge_tables)가
 * "| 칸 | 칸 |" 줄로 바꿔 글 속 제자리에 넣어 준다 — 아래 MSG1 은 그렇게 넣어진 뒤의 모양.
 *
 *   ① "| … |" 줄 묶음이 진짜 표로 그려진다(머리칸·숫자 오른쪽 정렬), WHAT 과 보충 줄 사이 제자리에
 *   ② 앞머리 안내문("[신문요약 수정본 1/7]"·"📰 … 재요약"·"원본: …pdf"·"30쪽 전체를…")엔 사진 칸이 없다
 *      "📰 … 재요약" 이 체크 목록 머리말로 잡혀 아래 기사까지 삼키지 않는다
 *   ③ "01. 제목" 다음 줄 "🔴 오늘 신문에서 …" 는 제목에 딸린 설명(제목과 섞이지도, 새 기사가 되지도 않음)
 *   ④ 일반 메시지 속 표도 표로 · 폰(390px)에서 표 때문에 화면이 옆으로 넘치지 않는다(표만 밀어 보기)
 *
 * 실행: npm i playwright && node scripts/test_viewer_table.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const MSG1 = `[신문요약 수정본 1/7]

:newspaper: 2026년 9월 24일 신문 재요약

원본: <https://drive.google.com/file/d/x/view|2026-09-24.pdf>
30쪽 전체를 이미지로 확인함. 기사 본문이 있는 43건을 정리함. 기사별 WHAT·WHY·HOW와 표를 한 묶음으로 유지하고 이미지 연결도 기사당 하나로 지정함.
page는 PDF 순서(1부터), bbox는 [왼쪽, 위, 너비, 높이] 비율임. [0,0,1,1]은 전체 쪽임.


01. “3억대 서울 분양도 나와” 추석후 청약 큰장
:red_circle: 오늘 신문에서 부동산 관점으로 가장 중요한 기사 중 하나임. 토지임대부 분양의 소유 구조를 구분해야 함.

• WHAT: 10월 수도권 26개 단지, 1만7841가구 공급 예정임. 서울 고덕강일3단지는 약 3억원대 토지임대부 주택임.

| 지역 | 단지 | 총가구(분양) |
| 서울 서초 | 신반포22차 재건축 | 160(28) |
| 서울 강동 | 고덕강일3단지 | 1305(1305) |
| 경기 평택 | 한화포레나지제역 | 1098(1098) |

지역별 전체 물량: 서울 3곳·1641가구 / 경기 16곳·1만1405가구 / 인천 7곳·4795가구.
경기 아파트값 연초 대비 상승률(9월 2주): 전체 4.92%, 용인 11.09%, 화성 9.87%.

• WHY: 분양가가 오르면서 저렴한 공공분양에 대한 관심이 커짐.
• HOW: 고덕강일3단지는 땅을 공공이 소유하고 건물만 분양함.
<https://v.daum.net/v/20260923155413619|원문> · PDF 1쪽


02. 재건축·재개발로 공공임대 8.3만가구 공급
:red_circle: 공급계획과 실제 착공을 구분해서 봐야 할 핵심 기사임.

• WHAT: 서울 정비사업 496곳에서 51만5817가구 공급 계획임.

※ 위 표는 공공임대만이 아닌 전체 계획 물량임. 멸실 37만7678가구를 빼면 순증 약 13만8139가구임.

• WHY: 사업장의 50.2%가 초기 단계에 머물러 있음.
• HOW: 서울시는 사업 속도를 높일 방침임.
<https://www.hankyung.com/article/2026092339071|원문> · PDF 2쪽

\`\`\`{"date":"2026-09-24","articles":[{"article_id":"20260924-001","title":"“3억대 서울 분양도 나와” 추석후 청약 큰장","page":1,"bbox":[0,0,1,1]}]}\`\`\`
*다음을 사용하여 보냄* <@U0BUG6LJXL0|ChatGPT>`;
const MSG2 = `참고로 비교표야\n| 항목 | 값 |\n|---|---|\n| 금리 | 3.5% |\n| 환율 | 1,380 |`;
const MSG3 = `:white_check_mark: 반드시 체크할 핵심 주제\n• 고덕강일3단지 토지임대부 구조와 실제 청약 조건.\n• 정비사업의 착공 전환.`;

const srv = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x'), u = url.pathname, D = url.searchParams.get('date') || '2026-09-24';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: D + 'T11:05:39', source: 'user', kind: 'text', text: MSG1 },
    { ts: D + 'T11:06:00', source: 'user', kind: 'text', text: MSG2 },
    { ts: D + 'T11:06:30', source: 'user', kind: 'text', text: MSG3 }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 3,
    images: ['01.jpg', '02.jpg', '03.jpg'].map(n => ({ name: n, url: '/x.png', thumb: '/x.png', download_url: '/x.png' })) }));
  if (u === '/api/news/pagetext') return send('application/json', '{"ok":false}');
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
    page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
    await page.goto(base + '/slack');
    await page.evaluate(() => { state.date = '2026-09-24'; lastSnapshot = null; return load(); });
    await page.waitForSelector('.brf-art');
    await page.waitForFunction(() => newsState.images.length === 3);
    await page.click('.viewseg [data-view="paper"]');
    console.log(`\n[${label} ${w}px]`);
    const r = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[0];
      const arts = [...c.querySelectorAll('.brf-art')];
      const t = c.querySelector('.brf-tbl');
      const a0 = arts[0];
      const order = a0 ? [...a0.querySelector('.brf-main').children].map(e => e.classList.contains('brf-detail') ? 'detail' : (e.className.split(' ')[0] || e.tagName)) : [];
      return {
        titles: arts.map(a => (a.querySelector('.brf-title') || {}).textContent.trim()),
        flag: a0 && (a0.querySelector('.brf-flagnote') || {}).textContent,
        head: t ? [...t.querySelectorAll('th')].map(e => e.textContent) : [],
        rows: t ? t.querySelectorAll('tbody tr').length : 0,
        numRight: t ? getComputedStyle(t.querySelector('tbody tr td:nth-child(3)')).textAlign : '',
        inArt: !!(t && t.closest('.brf-art') === a0), order: order.join('>'),
        intros: [...c.querySelectorAll('.brf-intro')].map(e => e.textContent.trim().slice(0, 12)),
        introSide: [...c.querySelectorAll('.brf-intro')].some(e => e.querySelector('.brf-side')),
        secs: [...c.querySelectorAll('.brf-sec')].map(e => e.textContent), chks: c.querySelectorAll('.brf-chk').length,
        sides: arts.map(a => !!a.querySelector('.brf-side')),
        plainTbl: (() => { const t2 = document.querySelectorAll('.entry .body')[1].querySelector('.brf-tbl');
          return t2 ? [...t2.querySelectorAll('td')].map(e => e.textContent).join(',') : ''; })(),
        chk3: document.querySelectorAll('.entry .body')[2].querySelectorAll('.brf-chk').length,
        over: document.documentElement.scrollWidth - innerWidth,
      };
    });
    check(r.titles.length === 2 && /^01\. “3억대/.test(r.titles[0]) && /^02\. 재건축/.test(r.titles[1]),
          '기사는 01·02 두 개(앞머리 안내문은 기사 아님)', r.titles.map(x => x.slice(0, 10)).join(' / '));
    check(r.flag && /^🔴 오늘 신문에서/.test(r.flag) && !/오늘 신문에서/.test(r.titles[0]),
          '"🔴 오늘 신문에서…" 는 제목 아래 설명(제목과 안 섞임)');
    check(r.head.join(',') === '지역,단지,총가구(분양)' && r.rows === 3, '표: 머리칸 3개 + 3줄', r.head.join(','));
    check(r.numRight === 'right', '숫자 칸(1305(1305))은 오른쪽 정렬');
    check(r.inArt && /brf-kv>brf-tblwrap>detail/.test(r.order), '표는 01 기사 안, WHAT 과 "지역별 전체 물량" 사이 제자리', r.order);
    check(r.intros.length >= 3 && !r.introSide && r.chks === 0 && r.secs.every(x => /재요약/.test(x)),
          '앞머리 안내문엔 사진 칸 없음 · "📰 … 재요약" 은 섹션 제목일 뿐 체크 목록으로 기사를 삼키지 않음', r.intros.join(' / '));
    check(r.sides.every(Boolean), '기사 01·02 에만 사진 칸');
    check(r.plainTbl === '금리,3.5%,환율,1,380', '일반 메시지 속 표도 표로(구분줄 빼고)', r.plainTbl);
    check(r.chk3 === 2, '":white_check_mark: 반드시 체크할 핵심 주제"(슬랙 원문 표기)도 체크 칸으로');
    check(r.over <= 0, '화면이 옆으로 넘치지 않는다', `${r.over}px`);
    await page.close();
  }
  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
