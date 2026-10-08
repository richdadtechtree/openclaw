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
// 실제 [신문요약 수정본 7/7] — 동그라미 숫자 ①~⑤ + 설명 줄, 체크 주제, 핵심 한 줄(> 인용)
const MSG7 = `[신문요약 수정본 7/7]


:mag_right: 오늘 신문에서 반드시 연결해서 봐야 할 5가지
① *주택 공급의 핵심은 발표 물량에서 실제 착공으로 옮겨감.*
정비사업 51.6만가구 계획 → 초기 단계 물량 55.3% → 인허가 단축·PF 보증료 인하 추진. 공급계획의 크기와 당장 입주할 물량을 구분해서 볼 필요가 있음.

② *분양 기회와 전세 공급은 지역·상품별로 다르게 나타남.*
고덕강일 토지임대부 본청약 → 낮은 건물 분양가에 관심. 한편 서울 10월 입주의 74%는 은평 한 단지에 집중됨. 서울 전체의 동일한 공급 개선으로 해석하기는 어려움.

③ *반도체 호황이 산업 전체의 같은 이익으로 이어지지는 않음.*
반도체 수출 확대 → 한국 성장 전망 상향. 동시에 메모리 가격 상승 → 완제품 원가 부담 → 비반도체 부품 단가 인하 요구가 나타남. 수출 호황과 협력사 이익 압박이 공존함.

④ *AI 확산은 소프트웨어 활용·채용과 전력 인프라를 함께 바꿈.*
AI 모델 비용 인하·기업 AX 확대 → AI 활용 신입 채용 증가. 미국 데이터센터 전력 수요 → 발전·원전 투자와 전선 수주로 연결됨.

⑤ *성장 전망 개선 속에서도 에너지와 금리 부담은 남아 있음.*
OECD 성장률 상향과 물가 전망 상향이 동시 발생함. 성장 개선만으로 투자심리가 일제히 좋아진 상황은 아님.


:white_check_mark: 반드시 체크할 핵심 주제
• 고덕강일3단지 토지임대부 구조와 실제 청약 조건.
• 정비사업의 착공 전환과 2026년 8월13일~2027년 말 PF 보증 지원.
• 반도체 수출 호황과 비반도체 협력사의 원가 부담.

:pushpin: 오늘 신문 핵심 한 줄
> 반도체·AI가 성장과 투자를 끌어도 에너지·금리·원가 부담이 함께 커지고 있어, 실제 이익과 계약으로 이어지는지를 가려보는 흐름이 중요해질 것으로 보임.




\`\`\`{"date":"2026-09-24","articles":[]}\`\`\`
*다음을 사용하여 보냄* <@U0BUG6LJXL0|ChatGPT>
`;
// 제목과 🔴 표시가 **한 줄**에 이어져 온 경우(2026-09-24 실제 화면)
const MSG8 = `02. 재건축·재개발로 공공임대 8.3만가구 공급 :red_circle: 공급계획과 실제 착공을 구분해서 봐야 할 핵심 기사임.
• WHAT: 서울 정비사업 496곳에서 51만5817가구 공급 계획임.
• WHY: 초기 단계가 많음.
🔴 반드시 체크 | 머리표 형식 제목은 그대로
• WHAT: 예전 형식.`;
// 머리말과 ① 이 **한 줄**에 붙어 온 실제 형식(2026-09-24 화면) + 번호 없이 뭔가 붙어 온 경우
const MSG9 = `[신문요약 수정본 7/7]
:mag_right: 오늘 신문에서 반드시 연결해서 봐야 할 5가지 ① *주택 공급의 핵심은 발표 물량에서 실제 착공으로 옮겨감.*
정비사업 51.6만가구 계획 → 초기 단계 물량 55.3%.
② *분양 기회와 전세 공급은 지역·상품별로 다르게 나타남.*
고덕강일 토지임대부 본청약 → 낮은 건물 분양가에 관심.
:mag_right: 내일 봐야 할 3가지 아래 순서로 정리함.`;
// 2026-10-06 실제 형식 — 원문 줄이 **제목 바로 아래**(WHAT 앞)에 온다. 예전엔 제목이 앞 기사로 당겨지고 WHAT 이 제목 없는 기사가 됐다
const MSG13 = `[신문요약 1/4]
2026-10-06 신문 브리핑
2. :rotating_light: 이매촌1·시범단지1·파크타운 ‘특별정비구역’ 지정
• 원문 확인 실패
• WHAT: 성남시가 분당 이매촌1·시범1 등 5개 구역, 1만3429가구를 특별정비구역으로 지정하는 절차에 들어감.
    ◦ 이매촌1 1734가구, 시범1 4200가구임.
• WHY: 주민제안 방식으로 정비 속도를 높이려는 것임.
• HOW: 12월 지정·고시가 목표임. *중요한 이유: 1기 신도시 사업 속도에 영향 줌.*





3. 풀옵션 착한 임대…6년간 월세 5만원 올라
• 원문: <https://www.mk.co.kr/news/realestate/12168487|매일경제>
• WHAT: 서울 왕십리 ‘지웰홈스 왕십리’ 21.5㎡ 월세가 104만5000원으로 6년간 4만5000원 오름.
    ◦ 총 299실, 전용 16~44㎡로 구성됐음.
• WHY: 코레일 땅을 30년 장기 임차해 토지 매입비를 줄였음.
• HOW: 장기 임대 모델로 임대료 상승을 억제했음.





4. 신반포22차 ‘디에이치 신반포 에스테라’로
• 원문: <https://www.mk.co.kr/news/realestate/12168484|매일경제>
• WHAT: 신반포22차를 최고 35층 2개 동, 160가구로 재건축함.
• WHY: 일반분양이 30가구 미만이라 분양가상한제 적용 대상에서 빠짐.
• HOW: 일부 주택형 분양가가 40억원 안팎까지 거론됨.





5. 경기광주역 롯데캐슬 시그니처 2단지 분양
• 원문 확인 실패
• WHAT: 경기 광주시 양벌동에 1249가구 규모로 공급됨.
• WHY: 경기광주역 접근성을 내세운 분양임.
• HOW: 수요층을 넓혔음.`;

// 2026-10-08 실제 — 나눠 보낸 순서 표시가 첫 기사 제목과 한 줄에 붙어 온다
const MSG14 = `*[신문요약 4/5]* 25. 애플, 스마트홈 파트너로 LG 택했다
• 원문: <https://www.mk.co.kr/news/business/12170771|mk.co.kr/news/business/12170771>
• WHAT: 애플과 LG전자가 스마트 도어록·보안카메라 등을 공동 개발 중인 것으로 보도됐음.
• WHY: 스마트홈 생태계를 넓히려는 목적임.
• HOW: 공식 출시 일정은 확정 보도가 아님.`;
// 슬랙이 보내는 그대로의 모양 — 글 속 & < > 는 &amp; &lt; &gt; 로 온다(2026-10-01 "&amp; 로 보인다" 제보)
const MSG12 = `[신문요약 2/2]
1. S&amp;P500 급등…R&amp;D 투자 확대
• WHAT: 금리 &lt; 3% 이고 환율 &gt; 1,300 이면 M&amp;A 조건 충족. 글자 그대로 &amp;lt; 라고 쓴 것도 있음.
• WHY: 시장 기대.
• HOW: <https://example.com/a?x=1&amp;y=2|원문> 참고.
• 사진: 02
\`\`\`json
{"articles":[{"title":"S&amp;P500 급등…R&amp;D 투자 확대","page":3}]}
\`\`\``;
const MSG2 = `참고로 비교표야\n| 항목 | 값 |\n|---|---|\n| 금리 | 3.5% |\n| 환율 | 1,380 |`;
const MSG3 = `:white_check_mark: 반드시 체크할 핵심 주제\n• 고덕강일3단지 토지임대부 구조와 실제 청약 조건.\n• 정비사업의 착공 전환.`;

const srv = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x'), u = url.pathname, D = url.searchParams.get('date') || '2026-09-24';
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (u === '/slack') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/slack/data') return send('application/json', JSON.stringify({ date: D, messages: [
    { ts: D + 'T11:05:39', source: 'user', kind: 'text', text: MSG1 },
    { ts: D + 'T11:06:00', source: 'user', kind: 'text', text: MSG2 },
    { ts: D + 'T11:06:30', source: 'user', kind: 'text', text: MSG3 },
    { ts: D + 'T11:07:00', source: 'user', kind: 'text', text: MSG7 },
    { ts: D + 'T11:07:30', source: 'user', kind: 'text', text: MSG8 },
    { ts: D + 'T11:08:00', source: 'user', kind: 'text', text: MSG9 },
    { ts: D + 'T11:09:00', source: 'user', kind: 'text', text: MSG10 },
    { ts: D + 'T11:10:00', source: 'user', kind: 'text', text: MSG12 },
    { ts: D + 'T11:11:00', source: 'user', kind: 'text', text: MSG13 },
    { ts: D + 'T11:12:00', source: 'user', kind: 'text', text: MSG14 }] }));
  if (u === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: true, date: D, count: 3,
    images: ['01.jpg', '02.jpg', '03.jpg'].map(n => ({ name: n, url: '/x.png', thumb: '/x.png', download_url: '/x.png' })) }));
  if (u === '/api/news/pagetext') return send('application/json', '{"ok":false}');
  res.writeHead(404); res.end();
});

// 2026-09-28 실제 모양 — 번호 바로 뒤에 🔴 가 오면 제목이 통째로 설명 줄로 내려가던 버그
const MSG10 = `[신문요약 1/6] :newspaper: 2026년 9월 28일 신문 브리핑

1. :red_circle: ‘반도체 벨트’ 강세 지속…수원 영통 상승률 1위 중요한 이유: 기업 저금리 대출과 반도체 호황 자금이 경기 남부 집값을 빠르게 밀어 올리는 흐름임.
• WHAT: 주간 아파트값 상승률은 수원 영통 1.09%, 권선 0.66%였음.
• WHY: 삼성전자 사내 주택구입 대출과 반도체 업황 개선이 구매력을 높였음.
• HOW: 기업 대출 조건과 금리 변화를 함께 봐야 함.

2. 연 4.5% 청년드림청약통장, 가입 문턱 낮아진다
• WHAT: 가입 소득 기준이 연 7000만원 이하로 완화됨.
• WHY: 청년층의 청약통장 가입을 늘리려는 조치임.
• HOW: 만 19~34세 무주택 청년이 대상임.

3. 🔴 “수도권 전세, 연말까지 3% 이상 강세…집값도 밀어올릴 것” 🔴 전세 상승이 매매 수요로 옮겨갈 수 있음.
• WHAT: 전문가 100명 설문 결과임.
• WHY: 입주물량 감소가 원인으로 지목됨.
• HOW: 전월세 대책을 봐야 함.`;

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
    // 날짜를 바꿀 땐 실제 화면의 날짜 선택(datepick)과 똑같이 요약(load)과 신문 사진(loadNews)을 **둘 다** 다시 받는다.
    // ⚠️ 예전엔 load() 만 불러, 사진 목록은 '오늘' 날짜로 남았다 → 테스트를 2026-09-24 에 돌릴 때만
    //    통과하고 그 뒤로는 "사진 칸 없음"으로 실패했다(화면 버그가 아니라 테스트의 날짜 의존).
    await page.evaluate(() => { state.date = '2026-09-24'; lastSnapshot = null; return Promise.all([load(), loadNews()]); });
    await page.waitForSelector('.brf-art');
    await page.waitForFunction(() => newsState.images.length === 3 && newsState.date === '2026-09-24');
    await page.waitForFunction(() => document.querySelectorAll('.entry .body')[0].querySelectorAll('.brf-side').length === 2);
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
    // 2026-10-08: 맨 앞 "[신문요약 수정본 1/7]" 는 이제 안내문으로도 안 보이고 배지로만 간다 → 안내문은 1개 이상("원본: …")
    check(r.intros.length >= 1 && !r.intros.some(x => /신문요약/.test(x)) && !r.introSide && r.chks === 0 && r.secs.every(x => /재요약/.test(x)),
          '앞머리 안내문엔 사진 칸 없음 · "📰 … 재요약" 은 섹션 제목일 뿐 체크 목록으로 기사를 삼키지 않음', r.intros.join(' / '));
    check(r.sides.every(Boolean), '기사 01·02 에만 사진 칸');
    check(r.plainTbl === '금리,3.5%,환율,1,380', '일반 메시지 속 표도 표로(구분줄 빼고)', r.plainTbl);
    check(r.chk3 === 2, '":white_check_mark: 반드시 체크할 핵심 주제"(슬랙 원문 표기)도 체크 칸으로');
    const t7 = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[3];
      const all = document.getElementById('feed').innerText;
      const n = [...c.querySelectorAll('.brf-num')];
      const noteCol = n[0] && getComputedStyle(n[0].querySelector('.note')).color;
      const bg = getComputedStyle(document.querySelector('.card')).backgroundColor;
      return { meta: /30쪽 전체를 이미지로|page는 PDF 순서|원문 기준으로 수정함/.test(all),
               src: /원본: /.test(all),
               sec: (c.querySelector('.brf-sec') || {}).textContent || '',
               nums: n.map(e => e.querySelector('.n').textContent).join(','),
               first: n[0] && n[0].querySelector('.v').firstChild.textContent.trim(),
               note: n[0] && n[0].querySelector('.note').textContent.slice(0, 10),
               intro: [...c.querySelectorAll('.brf-intro')].map(e => e.textContent.trim()),
               key: ((c.querySelector('.brf-key .txt') || {}).textContent || '').slice(0, 6), noteCol, bg };
    });
    const lum = c => { const m = (c || '').match(/[\d.]+/g) || [0, 0, 0]; const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
      return .2126 * f(+m[0]) + .7152 * f(+m[1]) + .0722 * f(+m[2]); };
    const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
    check(!t7.meta && t7.src, '작업 설명 줄("30쪽 전체를…"·"page는…"·"원문 기준으로 수정함")은 숨기고 "원본:" 은 남긴다');
    check(/봐야 할 5가지$/.test(t7.sec.trim()) && t7.nums === '1,2,3,4,5', '"…5가지" 뒤 줄바꿈 + ①~⑤ 가 번호 목록 1~5', t7.nums);
    check(/^주택 공급의 핵심은/.test(t7.first || '') && /^정비사업 51\.6만/.test(t7.note || '') && !t7.intro.some(x => /정비사업|신문요약/.test(x)),
          '요점 문장 + 그 아래 설명 줄이 한 항목(흐린 안내문으로 안 빠짐)', `${(t7.first || '').slice(0, 10)} | ${t7.note}`);
    const cr = contrast(t7.noteCol, t7.bg);
    check(cr >= 7, '설명 줄 글씨가 배경과 충분히 대비된다(7:1 이상 — 잘 보임)', `${cr.toFixed(1)}:1`);
    check(t7.key && !t7.key.startsWith('>'), '핵심 한 줄의 인용 표시 ">" 는 떼고 보인다', t7.key);
    const f8 = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[4];
      return [...c.querySelectorAll('.brf-art')].map(a => ({
        t: ((a.querySelector('.brf-title') || {}).textContent || '').trim(),
        flag: ((a.querySelector('.brf-flagnote') || {}).textContent || '').trim(),
        badge: !!a.querySelector('.brf-flag') }));
    });
    check(f8[0] && f8[0].t === '02. 재건축·재개발로 공공임대 8.3만가구 공급' && /^🔴 공급계획과/.test(f8[0].flag),
          '제목 옆에 붙어 온 🔴 부터는 줄을 바꿔 제목 아래 설명으로', f8[0] && `${f8[0].t.slice(0, 12)} / ${f8[0].flag.slice(0, 10)}`);
    check(f8[1] && f8[1].badge && /머리표 형식 제목은 그대로/.test(f8[1].t) && !f8[1].flag,
          '"🔴 반드시 체크 | 제목" 머리표 형식은 예전처럼(배지 + 제목)');
    const g9 = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[5];
      const n = [...c.querySelectorAll('.brf-num')];
      const col = e => getComputedStyle(e).color;
      return { secs: [...c.querySelectorAll('.brf-sec')].map(e => e.textContent.trim()),
               nums: n.map(e => e.querySelector('.n').textContent).join(','),
               first: n[0] && n[0].querySelector('.v').firstChild.textContent.trim(),
               lead: ((c.querySelector('.brf-listlead') || {}).textContent || '').trim(),
               introCol: c.querySelector('.brf-intro') && col(c.querySelector('.brf-intro')),
               bg: getComputedStyle(document.querySelector('.card')).backgroundColor };
    });
    check(g9.secs[0] && /봐야 할 5가지$/.test(g9.secs[0]) && g9.nums === '1,2' && /^주택 공급의 핵심은/.test(g9.first || ''),
          '머리말에 ① 이 붙어 와도 "…5가지" 뒤에서 줄바꿈 → ①부터 번호 목록', `${g9.nums} · ${(g9.first || '').slice(0, 8)}`);
    check(g9.secs[1] && /봐야 할 3가지$/.test(g9.secs[1]) && /^아래 순서로/.test(g9.lead),
          '번호 없이 뭔가 붙어 와도 "…N가지" 뒤는 무조건 줄바꿈', g9.lead);
    const cr9 = contrast(g9.introCol, g9.bg);
    check(cr9 >= 7, '안내문 글씨도 잘 보인다(대비 7:1 이상)', `${cr9.toFixed(1)}:1`);
    const h10 = await page.evaluate(() => {
      const c = document.querySelectorAll('.entry .body')[6];
      return [...c.querySelectorAll('.brf-art')].map(a => {
        const t = a.querySelector('.brf-title'), cl = t.cloneNode(true);
        cl.querySelectorAll('.brf-flag').forEach(n => n.remove());
        return { t: cl.textContent.trim(), badge: ((t.querySelector('.brf-flag') || {}).textContent || '').trim(),
                 sub: [...a.querySelectorAll('.brf-sub')].map(e => e.textContent.trim()) };
      });
    });
    check(h10.length === 3 && h10[0].t === '1. ‘반도체 벨트’ 강세 지속…수원 영통 상승률 1위' && h10[0].badge === '🔴'
          && /^기업 저금리 대출/.test(h10[0].sub[0] || ''),
          '"1. 🔴 제목 중요한 이유: …" → 제목은 제목 줄에(🔴 는 작은 배지), 이유만 아래로', h10[0] && h10[0].t.slice(0, 14));
    check(h10[1] && h10[1].t === '2. 연 4.5% 청년드림청약통장, 가입 문턱 낮아진다' && !h10[1].badge, '🔴 없는 제목은 그대로');
    check(h10[2] && /^3\. “수도권 전세, 연말까지 3% 이상 강세…집값도 밀어올릴 것”$/.test(h10[2].t) && h10[2].badge === '🔴'
          && /^🔴 전세 상승이/.test(h10[2].sub[0] || ''),
          '앞 🔴 는 배지, 제목 뒤 🔴 설명은 여전히 아래 줄로', h10[2] && h10[2].sub[0]);
    const am = await page.evaluate(() => {
      const c = [...document.querySelectorAll('.entry .body')].find(b => /S&P500/.test(b.textContent));
      if (!c) return null;
      const a = c.querySelector('.brf-art'), link = c.querySelector('a[href*="example.com"]');
      return { title: (a.querySelector('.brf-title') || {}).textContent.trim(), text: c.querySelector('.brf-main').textContent,
               href: link && link.getAttribute('href'), src: ((a.querySelector('.side-src') || {}).textContent || '') };
    });
    check(am && am.title === '1. S&P500 급등…R&D 투자 확대', '슬랙의 &amp; 가 제목에서 & 로 보인다', am && am.title);
    check(am && /금리 < 3% 이고 환율 > 1,300 이면 M&A 조건/.test(am.text) && !/&amp;|&lt;|&gt;/.test(am.text.replace('&lt; 라고', '')),
          '본문의 &lt; &gt; &amp; 도 < > & 로', am && am.text.slice(6, 46));
    check(am && /그대로 &lt; 라고/.test(am.text), '사람이 글자 그대로 쓴 "&lt;" 는 그대로 보인다(두 번 풀지 않음)');
    check(am && am.href === 'https://example.com/a?x=1&y=2', '링크 주소 속 & 도 바르게', am && am.href);
    check(am && /요약 JSON · 3쪽/.test(am.src), 'JSON 제목의 &amp; 도 풀려서 기사와 짝이 맞는다', am && am.src);
    const nf = await page.evaluate(() => {
      const c = [...document.querySelectorAll('.entry .body')].find(b => /지웰홈스/.test(b.textContent));
      return [...c.querySelectorAll('.brf-art')].map(a => {
        const t = a.querySelector('.brf-title'), cl = t && t.cloneNode(true);
        if (cl) cl.querySelectorAll('.brf-flag').forEach(n => n.remove());
        return { t: cl ? cl.textContent.trim() : '(제목 없음)', what: ((a.querySelector('.brf-kv .v') || {}).textContent || '').slice(0, 12),
                 src: ((a.querySelector('.brf-src') || {}).textContent || '').trim(), main: a.querySelector('.brf-main').textContent };
      });
    });
    check(nf.length === 4 && nf.map(x => x.t.slice(0, 2)).join(',') === '2.,3.,4.,5.',
          '원문 줄이 제목 바로 아래 와도 기사 4개 — 제목마다 자기 기사', nf.map(x => x.t.slice(0, 8)).join(' / '));
    check(/^성남시/.test(nf[0].what) && /^서울 왕십리/.test(nf[1].what) && /^신반포22차/.test(nf[2].what) && /^경기 광주시/.test(nf[3].what),
          '각 제목 아래에 자기 WHAT 이 붙는다(한 칸씩 당겨지지 않음)', nf.map(x => x.what.slice(0, 5)).join(' / '));
    check(!/신반포22차 ‘디에이치/.test(nf[1].main) && !/경기광주역 롯데캐슬/.test(nf[2].main), '다음 기사 제목이 앞 기사 안으로 끌려가지 않는다');
    check(/매일경제/.test(nf[1].src) && /매일경제/.test(nf[2].src) && !/원문 확인 실패/.test(nf.map(x => x.main).join('')),
          '원문 링크는 그 기사 안에, "원문 확인 실패" 줄은 숨김');
    const pt = await page.evaluate(() => {
      const e = [...document.querySelectorAll('.entry')].find(x => /스마트홈 파트너/.test(x.textContent));
      return { title: e.querySelector('.brf-title').textContent.trim(), body: e.querySelector('.body').textContent,
               badge: [...e.querySelectorAll('.kind')].map(k => k.textContent).join(',') };
    });
    check(pt.title === '25. 애플, 스마트홈 파트너로 LG 택했다' && !/신문요약/.test(pt.body),
          '제목에 붙어 온 "[신문요약 4/5]" 는 떼어낸다(제목·본문에 안 보임)', pt.title);
    check(/4\/5/.test(pt.badge), '순서는 카드 위 작은 배지로만', pt.badge);
    check(r.over <= 0, '화면이 옆으로 넘치지 않는다', `${r.over}px`);
    await page.close();
  }
  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
