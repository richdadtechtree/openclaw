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
// 2026-10-12 실제 메시지 그대로 — "[검수신문요약 1/8]" + 기사마다 제목 / • 사진 / • 원문 / • WHAT 순서
const MSG15 = "[검수신문요약 1/8]\n\n\n1. :large_blue_circle: 수원 영통구, 집값 상승률 1위 … 분당구도 강세\n• 사진: 01\n• 원문: <https://www.hankyung.com/article/2026101145381|hankyung.com/article/2026101145381>\n• WHAT: 10월 1~7일 아파트값이 수원 영통구 0.62%, 성남 분당구 0.56%, 안양 동안구 0.41%, 광명 0.39%, 서울 서대문구 0.36%, 성북구 0.35% 올랐음.\n• WHY: 기사에서는 서울의 규제·가격 부담 속에 교통·학군을 갖춘 경기 남부와 서울 비강남권으로 수요가 이동한 흐름이라고 설명함.\n• HOW: 확정 통계임. 주간 상승률은 단기 수급 지표라 거래량·실거래가와 함께 봐야 함.\n\n2. :large_blue_circle: 낙찰가율 115% … 경매서도 뜨거운 경기 남부 아파트\n• 사진: 01\n• 원문: 원문 확인 실패\n• WHAT: 9월 아파트 경매 낙찰가율이 안양 동안구 115.7%, 수원 영통구 114.0%, 광명 113.1%, 수원 장안구 111.9%, 분당구 109.7%였음. 경기 평균은 88.8%, 서울은 94.7%였음.\n• WHY: 기사에서는 인기 지역의 경매 경쟁이 감정가를 웃돌 정도로 강해졌다고 설명함.\n• HOW: 확정 통계임. 선순위 권리·체납관리비·명도비용을 포함한 총비용 확인이 필요함.\n\n3. :large_blue_circle: “더 귀해진다” … 역세권 15억 이하 아파트 잡아볼까\n• 사진: 02\n• 원문: 원문 확인 실패\n• WHAT: 서울 아파트값이 87주 연속 올랐고, 10월 거래 중 10억원 이하 비중은 55.8%, 10억~15억원은 19.1%였음.\n• WHY: 기사에서는 대출·세금 규제 속에 역세권 중저가 단지의 희소성이 커졌다고 설명함.\n• HOW: 기사 조언임. 역 거리·정비사업 단계·전세가율·추가분담금을 따로 확인해야 함.\n\n4. :large_blue_circle: :star: [부동산 중요] [단독] 집지을 땅 없다는데 … LH 택지 절반 유찰\n• 사진: 03\n• 원문: <https://www.mk.co.kr/news/realestate/12173017|mk.co.kr/news/realestate/12173017>\n• WHAT: LH 공동주택용지 유찰률이 2021년 3%, 2022년 41%, 2023년 27%, 2024년 56%(45필지 중 25필지), 2025년 45%(22필지 중 10필지)였음. 공급 필지는 2022년 81개에서 2025년 22개로 72.8%, 공급금액은 6조5580억원에서 1조9952억원으로 69.6% 줄었음. 7월 기준 장기 미매각은 707필지·3조4491억원이었음.\n• WHY: 주택 공급의 출발점인 택지 감소가 중장기 공급 공백으로 이어질 수 있어 중요함.\n• HOW: 시행 중임. 2023년~2026년 5월 계약 40조4000억원 중 무이자 할부가 9조5000억원(23.5%)이었음.\n\n5. :large_blue_circle: 이번주 화성·양평 등 1829가구 청약\n• 사진: 04\n• 원문: <https://www.mk.co.kr/news/realestate/12173019|mk.co.kr/news/realestate/12173019>\n• WHAT: 10월 12~16일 전국 8개 단지에서 1829가구가 청약을 받음. 향남역 그로브 스위첸 933가구, 양평역 금호어울림 333가구, 더샵 동인 센트리체 314가구임.\n• WHY: 기사에서는 연휴 뒤 분양 일정이 재개돼 수도권과 지방 청약 수요가 시험받는다고 설명함.\n• HOW: 시행 예정임. 단지별 분양가·중도금대출·전매제한·거주의무 확인이 필요함.\n```{\"date\":\"2026-10-12\",\"articles\":[{\"title\":\"🔵 수원 영통구, 집값 상승률 1위 … 분당구도 강세\",\"page\":1,\"evidence\":[{\"k\":\"WHAT\",\"quote\":\"수원 영통구, 집값 상승률 1위 … 분당구도 강세\",\"nums\":[\"0.62%\",\"0.56%\",\"0.41%\",\"0.39%\",\"0.36%\",\"0.35%\"]},{\"k\":\"HOW\",\"src\":\"지면 통계\"}]},{\"title\":\"🔵 낙찰가율 115% … 경매서도 뜨거운 경기 남부 아파트\",\"page\":1,\"evidence\":[{\"k\":\"WHAT\",\"quote\":\"낙찰가율 115% … 경매서도 뜨거운 경기 남부 아파트\",\"nums\":[\"115.7%\",\"114.0%\",\"113.1%\",\"111.9%\",\"109.7%\",\"88.8%\",\"94.7%\"]},{\"k\":\"HOW\",\"src\":\"지면 통계\"}]},{\"title\":\"🔵 “더 귀해진다” … 역세권 15억 이하 아파트 잡아볼까\",\"page\":2,\"evidence\":[{\"k\":\"WHAT\",\"quote\":\"“더 귀해진다” … 역세권 15억 이하 아파트 잡아볼까\",\"nums\":[\"87주\",\"10억원\",\"55.8%\",\"10억~15억원\",\"19.1%\"]},{\"k\":\"HOW\",\"src\":\"기사 조언\"}]},{\"title\":\"🔵 ⭐ [부동산 중요] [단독] 집지을 땅 없다는데 … LH 택지 절반 유찰\",\"page\":3,\"evidence\":[{\"k\":\"WHAT\",\"quote\":\"집지을 땅 없다는데 … LH 택지 절반 유찰\",\"nums\":[\"56%\",\"45%\",\"72.8%\",\"69.6%\",\"707필지\",\"3조4491억원\"]},{\"k\":\"HOW\",\"src\":\"지면 통계\"}]},{\"title\":\"🔵 이번주 화성·양평 등 1829가구 청약\",\"page\":4,\"evidence\":[{\"k\":\"WHAT\",\"quote\":\"이번주 화성·양평 등 1829가구 청약\",\"nums\":[\"8개 단지\",\"1829가구\",\"933가구\",\"333가구\",\"314가구\"]},{\"k\":\"HOW\",\"src\":\"시행 예정\"}]}]}```";
// 2026-10-13 실제 메시지 그대로 — 머리말이 "…신문 요약"(예전 "신문 브리핑") + 기사 끝 "• 중요:" 줄
// 머리말을 '목록 머리말'로 오인해 기사 제목이 번호 목록이 되고 내용이 한 칸씩 밀렸다
const MSG16 = "[신문요약 1/8]\n2026-10-13 신문 요약\n1. :rotating_light: 서울 3분기 아파트 매매 절반 이상 ‘전고점’ 넘어\n• 원문: <https://www.hankyung.com/article/2026101268521|hankyung.com/article/2026101268521>\n• WHAT: 3분기 서울 비교 가능 거래 1만930건 중 54.7%가 종전 최고가 이상에서 거래됨. 1분기 38.2%, 2분기 43.0%에서 상승함. 동대문 81.9%, 서대문 73.5%, 성북 68.5%였고 강남 43.0%, 서초 62.6%, 용산 66.9%였음.\n• WHY: 비강남권까지 전고점 회복 거래가 퍼졌지만 강남·서초·용산은 가격 부담과 대출 규제 영향으로 비율이 전분기보다 낮아짐.\n• HOW: 경기도도 3만3619건 중 22.4%가 전고점 이상이었고 분당 94.1%, 수정 77.2%, 수지 74.1%, 하남 73.6%로 서울 인접 선호지에 집중됨.\n• 중요: 서울 상승세가 외곽과 경기 핵심지로 확산되는지 보여주는 지표임.\n\n2. :rotating_light: ‘20년 장기전세 갈등’ 은평·마포로 번지나\n• 원문: 원문 확인 실패\n• WHAT: 서울 장기전세 약 6600가구가 2030~2031년 최대 20년 거주기한을 맞음. 2030년 2452가구 중 은평 1086·마포 648·중랑 478가구가 90.2%, 2031년 4170가구 중 강동 1170·구로 909·양천 844가구가 70.1%임.\n• WHY: 현행 제도는 20년 뒤 계약을 끝내고 주택을 다시 공급하는 구조인데, 만기 물량이 특정 자치구에 몰려 이주 수요가 한꺼번에 생길 수 있음.\n• HOW: 마포 장기전세 평균 보증금은 2억4710만원으로 인근 아파트 평균 전셋값 7억1918만원보다 4억4447만원 낮아 같은 지역 재정착 부담이 큼.\n• 중요: 2030년부터 전세·비아파트 임대시장 수요를 밀어 올릴 가능성을 점검해야 함.\n\n3. 삼성E&amp;A·가스안전공사, 해외 플랜트 보수시장 공략\n• 원문: <https://www.hankyung.com/article/2026101269341|hankyung.com/article/2026101269341>\n• WHAT: 삼성E&A와 한국가스안전공사가 해외 노후 플랜트 안전·보수 시장 공동 공략을 위한 업무협약을 맺음.\n• WHY: 해외 플랜트가 노후화하면서 안전진단과 설비 수명 검증 수요가 커지고 있음.\n• HOW: 안전진단, 적합성·잔여수명 제3자 검증, 비파괴검사 기술과 EPC 사업 경험을 결합해 공동 사업을 발굴함.\n\n4. 재건축 없어도 신축처럼…래미안식 리모델링\n• 원문: <https://www.hankyung.com/article/2026101268541|hankyung.com/article/2026101268541>\n• WHAT: 삼성물산이 반포푸르지오에 벽식 아파트 평면을 바꾸는 ‘넥스트 리모델링’을 제안함. 전용 84㎡ 2베이를 슬라이딩도어와 호텔식 욕실 등을 적용한 평면으로 바꾸는 방식임.\n• WHY: 수직증축 리모델링보다 인허가와 공사기간 부담을 낮추면서 내부 구조를 개선하려는 수요를 겨냥함.\n• HOW: 준공 뒤 새 사용승인일과 래미안 브랜드를 적용하는 방안을 제시했으며 최종 적용은 조합 의사결정과 인허가가 필요함.\n\n5. :rotating_light: 주택사업 인허가만 8년도 걸리는데…5년 내 승인 못 받으면 세금폭탄\n• 원문: <https://www.mk.co.kr/news/realestate/12173902|mk.co.kr/news/realestate/12173902>\n• WHAT: 주택용지 취득 뒤 5년 안에 사업계획승인을 받지 못하면 종부세 감면액을 추징함. 기사 사례는 약 200억원 토지에 종부세·가산액 15억~20억원이 예상됨.\n• WHY: 용도변경 3~5년과 후속 인허가를 합치면 5~8년이 걸릴 수 있는데 세제 시한은 5년임. 토지담보대출은 27조9000억원에서 10조4000억원으로 62.7% 줄었고 공사비지수는 103.8에서 135.76으로 30.8% 오름.\n• HOW: 지난해 정당한 지연 사유 예외가 생겼지만 도시계획 절차·금융경색 인정 범위가 불명확함. 행안부는 승인 뒤 재산세 분리과세도 5년으로 제한하고 인구감소지역은 8년을 적용하는 개편을 추진 중임.\n• 중요: 공급 지연이 사업자 귀책이 아니어도 세금·금융 부담이 동시에 커질 수 있음.";
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

// 구조 우선(2026-10-12 "요약이든 브리핑이든 잘 판단해서") — 머리말 낱말이 바뀌고, 기사 제목이 목록·강조·체크 머리말처럼 생겨도
//   다음에 (사진·원문 줄만 지나) WHAT 이 오면 기사 제목. 끝의 진짜 종합 분석(5가지·핵심 한 줄)은 그대로.
const MSG17 = `[신문요약 1/2]
2026-10-14 오늘의 경제 뉴스 정리
1. 서울 아파트 거래 체크할 5가지
• 사진: 03
• 원문: <https://a.com/x|매일경제>
• WHAT: 구조판별A 거래량 3,200건
• WHY: 금리.
• HOW: 지켜봄.
📌 강남 재건축 핵심 한 줄
• WHAT: 구조판별B 재건축 120건
• WHY: 규제 완화.
:white_check_mark: 반드시 체크할 핵심 주제 금리
• 사진: 05
• WHAT: 구조판별C 금리 3.5%
🔍 오늘 신문에서 반드시 연결해서 봐야 할 5가지
1. 금리 하락
2. 거래 증가
📌 오늘 신문 핵심 한 줄
거래가 늘어난다`;

// 2026-10-20 실제 메시지 모양 — 제목이 _기울임_ 으로 오고, 지면 번호가 앞말 없이 제목 끝에 "(PDF 1·7)" "(2)" "(3 좌)" 로 붙는다.
//   예전엔 "(사진 07)" 처럼 앞말이 있어야만 알아봐서 옆에 지면이 안 붙었다("어느 지면에 실렸는지 아직 몰라요").
const MSG18 = `[2026-10-20 신문 수동 재브리핑 1/4] :house: 부동산·산업 (1~9/35)
원본 PDF: <https://drive.google.com/file/d/13jeHDp/view|drive.google.com/file/d/…/view>
※ 1·7쪽은 중복 기사, 30쪽은 사진만 있어 제외함.

_1. 서울 11월 입주 488가구 (PDF 1·7)_
WHAT: 지면새형식A 서울 11월 입주 예정 3개 단지·488가구.
WHY: 전국 입주물량 감소.
HOW [예정]: 전국 1만1559가구(-30%).
원문: <https://www.mk.co.kr/news/realestate/12179853|mk.co.kr/news/realestate/12179853>
_2. 강북 재개발 이주비 금리 (2)_
WHAT: 지면새형식B 서울 정비사업 지역별 이주비 대출금리 격차.
WHY: 종전자산 담보가치 차이.
HOW [확정/검토]: 강남4구 기본 평균 3.78%.
_6. 고급 아파트 하이필로티 (3 좌하)_
WHAT: 지면새형식C 신축 아파트에서 높은 저층 필로티 채택 확대.
WHY: 개방감.
HOW [기사 사례]: 10m 이상 높은 필로티.
17. 제주항공 등 영업이익 추정 변화 (PDF 2쪽 하단)
• WHAT: 지면새형식D 항공·에너지·콘텐츠 기업의 분기 이익 추정이 엇갈림.
• WHY: 환율.`;

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
    { ts: D + 'T11:12:00', source: 'user', kind: 'text', text: MSG14 },
    { ts: D + 'T11:13:00', source: 'user', kind: 'text', text: MSG15 },
    { ts: D + 'T11:14:00', source: 'user', kind: 'text', text: MSG16 },
    { ts: D + 'T11:15:00', source: 'user', kind: 'text', text: MSG17 },
    { ts: D + 'T11:16:00', source: 'user', kind: 'text', text: MSG18 }] }));
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
    const g12 = await page.evaluate(() => {
      const e = [...document.querySelectorAll('.entry')].find(x => /낙찰가율 115%/.test(x.textContent));
      return { body: e.querySelector('.body').textContent, badge: [...e.querySelectorAll('.kind')].map(k => k.textContent).join(','),
        arts: [...e.querySelectorAll('.brf-art')].map(a => {
          const t = a.querySelector('.brf-title'), cl = t && t.cloneNode(true);
          if (cl) cl.querySelectorAll('.brf-flag').forEach(n => n.remove());
          return { t: cl ? cl.textContent.trim().slice(0, 12) : '(제목 없음)', what: ((a.querySelector('.brf-kv .v') || {}).textContent || '').slice(0, 8),
                   kvs: a.querySelectorAll('.brf-kv').length };
        }) };
    });
    check(g12.arts.length === 5 && g12.arts.every((x, i) => x.t.startsWith((i + 1) + '.')) && g12.arts.every(x => x.kvs === 3),
          '제목 / 사진 / 원문 / WHAT 순서(2026-10-12)도 기사 5개가 각자 제목·WHAT·WHY·HOW', g12.arts.map(x => x.t.slice(0, 6)).join(' / '));
    check(/^10월 1~7/.test(g12.arts[0].what) && /^9월 아파트/.test(g12.arts[1].what) && /^서울 아파트/.test(g12.arts[2].what),
          '제목마다 자기 WHAT(한 칸씩 밀리지 않음)', g12.arts.map(x => x.what).join(' / '));
    check(!/검수신문요약/.test(g12.body) && /1\/8/.test(g12.badge), '"[검수신문요약 1/8]" 도 떼고 배지로만', g12.badge);
    const g13 = await page.evaluate(() => {
      const e = [...document.querySelectorAll('.entry')].find(x => /3분기 서울 비교 가능 거래/.test(x.textContent));
      const body = e.querySelector('.body');
      return { nums: body.querySelectorAll('.brf-num').length, head: (body.querySelector('.brf-head') || {}).textContent || '',
        text: body.textContent,
        arts: [...body.querySelectorAll('.brf-art')].map(a => {
          const t = a.querySelector('.brf-title'), cl = t && t.cloneNode(true);
          if (cl) cl.querySelectorAll('.brf-flag').forEach(n => n.remove());
          return { t: cl ? cl.textContent.trim().slice(0, 10) : '(제목 없음)', what: ((a.querySelector('.brf-kv .v') || {}).textContent || '').slice(0, 8) };
        }) };
    });
    check(g13.nums === 0 && /신문 요약$/.test(g13.head.trim()), '머리말 "…신문 요약" 을 목록 머리말로 오인하지 않는다(기사 제목이 번호 목록이 안 됨)', g13.head);
    check(g13.arts.length === 5 && g13.arts.every((x, i) => x.t.startsWith((i + 1) + '.')), '기사 5개가 각자 제목을 가진다', g13.arts.map(x => x.t.slice(0, 6)).join(' / '));
    check(/^3분기 서울/.test(g13.arts[0].what) && /^서울 장기전세/.test(g13.arts[1].what) && /^삼성E&A/.test(g13.arts[2].what),
          '제목마다 자기 WHAT(밀리지 않음)', g13.arts.map(x => x.what).join(' / '));
    check(!/확인 실패/.test(g13.text), '"원문: 원문 확인 실패" 줄은 숨김');
    const g14 = await page.evaluate(() => {
      const e = [...document.querySelectorAll('.entry')].find(x => /구조판별A/.test(x.textContent));
      const body = e.querySelector('.body');
      return { head: (body.querySelector('.brf-head') || {}).textContent || '', nums: body.querySelectorAll('.brf-num').length,
        keys: body.querySelectorAll('.brf-key').length, chks: body.querySelectorAll('.brf-chk').length,
        arts: [...body.querySelectorAll('.brf-art')].map(a => ((a.querySelector('.brf-title') || {}).textContent || '').trim() + ' | ' +
          ((a.querySelector('.brf-kv .v') || {}).textContent || '').slice(0, 5)) };
    });
    check(g14.head.trim() === '2026-10-14 오늘의 경제 뉴스 정리', '머리말 낱말이 바뀌어도("…뉴스 정리") 날짜 든 짧은 첫 줄은 머리말', g14.head);
    check(g14.arts.length === 3 && /5가지 \| 구조판별A/.test(g14.arts[0]) && /핵심 한 줄 \| 구조판별B/.test(g14.arts[1]) && /핵심 주제 금리 \| 구조판별C/.test(g14.arts[2]),
          '목록·강조·체크 머리말처럼 생긴 제목도 다음에 WHAT 이 오면 기사 제목', g14.arts.join(' / '));
    check(g14.nums === 2 && g14.keys === 1 && g14.chks === 0, '진짜 종합 분석(5가지 목록·핵심 한 줄)은 그대로', `번호 ${g14.nums} · 강조 ${g14.keys} · 체크 ${g14.chks}`);
    const g15 = await page.evaluate(() => {
      const e = [...document.querySelectorAll('.entry')].find(x => /지면새형식A/.test(x.textContent));
      return [...e.querySelectorAll('.brf-art')].map(a => ({ t: (a.querySelector('.brf-title') || {}).textContent || '', page: a.dataset.page || '',
        no: ((a.querySelector('.side-no') || {}).textContent || '').trim(), pg: ((a.querySelector('.brf-pg') || {}).textContent || '') }));
    });
    check(g15.length === 4 && g15.map(x => x.page).join(',') === '1,2,3,2', '제목 끝 "(PDF 1·7)" "(2)" "(3 좌하)" "(PDF 2쪽 하단)" 에서 지면 번호를 읽는다', g15.map(x => x.page).join(','));
    check(g15.map(x => x.no).join(',') === '01,02,03,02', '그래서 기사 옆에 그 지면 사진이 붙는다', g15.map(x => x.no).join(','));
    check(g15.every(x => !/[_()]|PDF/.test(x.t.replace(x.pg, ''))) && g15.map(x => x.pg).join('|') === '1·7쪽|2쪽|3쪽 좌하|2쪽 하단',
          '제목엔 밑줄·괄호가 안 남고, 쪽·자리는 작은 꼬리표로', g15.map(x => x.t).join(' / '));
    check(r.over <= 0, '화면이 옆으로 넘치지 않는다', `${r.over}px`);
    await page.close();
  }
  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
