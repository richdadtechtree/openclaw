# CLAUDE.md — 이 리포 작업 컨텍스트

이 리포(`richdadtechtree/openclaw`)는 서버의 **`/home/ubuntu/.openclaw`** (openclaw AI 에이전트 홈)이며,
Git으로 서버와 자동 동기화됩니다. 별도 프로젝트인 **stock**(`/home/ubuntu/stock/stock`)도 함께 다룹니다.

## 응답 규칙 (항상 지킬 것)
- **클로드 코드로 작업할 때는 무조건 — 무엇을 했는지 / 왜 했는지 / 어떻게 했는지를 쉽게 설명한다.**
  모든 답변, 특히 코드/작업을 한 경우엔 맨 마지막에 "쉽게 정리" 섹션을 반드시 붙인다.
  초등학생도 이해할 만큼 **정말 쉬운 말로**, 아래 순서대로 짧게:
  - 🎯 **왜 이 작업을 했나** (목적 — 무엇을 위해 손댔는지)
  - 🔎 **무엇이 문제였나** (원인)
  - 🛠 **무엇을 어떻게 고쳤나** (조치 내용 + 구체적 방법·절차 — "어떻게"까지 반드시 포함)
  - ✅ **그래서 어떻게 되나 / 확인할 것** (결과·다음 행동)
  - 전문용어는 풀어 쓰고, 필요하면 실행할 명령어를 그대로 복붙할 수 있게 제시.
  - 이 규칙은 예외 없이 항상 적용(간단한 질문 답변이라도 최소 한두 줄로 요약). 코드/설정을 건드린 답변에서 이 섹션이 빠지면 그 답변은 미완성으로 간주한다.

## 시스템 구성 (누가 무엇을 하나)
- 🤖 **뚜떵또 = openclaw AI 에이전트** (`~/.openclaw`): 텔레그램/슬랙 대화 + **온디맨드 신문 브리핑**. AI 모델 사용.
- 📈 **stock 프로젝트** (`~/stock/stock`, FastAPI+Playwright, `briefing-bot` 텔레그램): 주가 대시보드 캡처 + 관심종목 급등락 알림. **AI 미사용(규칙 기반)** → 모델 문제와 무관하게 동작.

## 핵심 규칙 / 함정 (필독)
- **서버 경로**: openclaw = `/home/ubuntu/.openclaw`, stock = `/home/ubuntu/stock/stock`.
- **파이썬**: 서버에 맨 `python` 없음 → `python3` 또는 venv 사용.
  ⚠️ **시스템 `python3` 에는 `requests` 가 없다** → 외부 API를 쓰는 스크립트(`book_slack.py`,
  `get_notion_book.py` 등)는 venv 파이썬 절대경로로 실행할 것: `/home/ubuntu/newspaper/.venv/bin/python`
  (stock 쪽은 `~/stock/stock/venv/bin/python`). **cron 등록 시 특히 주의.**
  ✅ **예외**: `workspace/news_fetcher.py` + `scripts/verify_article_url.py` 는 `requests`·`bs4`·`feedparser` 가 **없어도** 표준 라이브러리로 돌아간다(있으면 그걸 쓴다). `.venv` 가 켜져 있든 아니든 `python3` 로 그냥 실행하면 된다. 확인: `python3 scripts/test_news_fetcher_nodeps.py`
- **openclaw 재시작**: `openclaw daemon restart` (systemd user 서비스 `openclaw-gateway`).
- **git 권한**: `richdadtechtree/openclaw`만 push 가능. **`richdadtechtree/stock`은 push 불가(403)** → stock 변경은 openclaw `scripts/`에 파일 두고 서버가 복사/적용하거나, 서버에서 직접 편집.
- **자동 동기화**: openclaw main에 push → 서버 cron이 1분마다 `git-auto-pull.sh`로 pull + 재시작. 런타임 파일(세션/로그/미디어/*.sqlite/*.bak)은 `.gitignore`로 추적 제외 → pull 안전.
  - 서버에서 즉시 반영: `OPENCLAW_GIT_BRANCH=main OPENCLAW_RESTART_CMD="openclaw daemon restart" ~/.openclaw/scripts/git-auto-pull.sh`
- **openclaw.json**: `.gitignore` 대상(비밀 포함) → 서버에서 **jq로 직접 편집**. 백업(`cp openclaw.json openclaw.json.bak-*.$(date +%s)`) 후 `jq ... > /tmp/oc.json && jq empty /tmp/oc.json && mv /tmp/oc.json openclaw.json`.
- **openclaw 모델 등록**: 모델을 쓰려면 **①`agents.defaults.model`(+ list agents) ②`models.providers.<provider>.models[]`(id/name 등록)** 둘 다 필요. 안 하면 "Unknown model".
- **Gemini via openclaw**: ⚠️ **openclaw 2026.7.1-2 에선 `models.providers.google.api="openai-chat"` 값이 무효**(config invalid → 게이트웨이 기동 실패). 이 버전 허용값: `openai-completions`, `openai-responses`, `openai-chatgpt-responses`, `anthropic-messages`, `google-generative-ai`, `google-vertex`, `github-copilot`, `bedrock-converse-stream`, `ollama`, `azure-openai-responses`.
  → Gemini는 **네이티브 `google-generative-ai`** api 권장(별도 baseUrl 우회 불필요). OpenAI-호환 엔드포인트를 굳이 쓰려면 `openai-completions` + `baseUrl=".../v1beta/openai/"` 로 시도(검증 필요).
  Gemini 키는 게이트웨이 env `GEMINI_API_KEY`로 읽힘(systemd 유닛 `Environment=`에 있음).

## 비밀/키
- 키는 `~/.openclaw/.env`(gitignored). openclaw.json은 `${VAR}` 참조 or 자체 인증 저장소 사용.
- ⚠️ 이 세션 중 다수 키가 채팅/히스토리에 노출됨(텔레그램봇x2, Slack, Brave, Gateway, Gemini). **재발급 권장.**

## 주요 스크립트 (`scripts/`)
| 파일 | 용도 |
|---|---|
| `git-auto-push.sh`/`git-auto-pull.sh`/`setup-server-cron.sh` | 설정 자동 git 동기화 |
| `sheets_push.py` + `sheets-apps-script.gs` | 브리핑 → 구글 시트(Apps Script 웹앱) |
| `slack_briefing.py` | stock 대시보드 캡처 → 슬랙 (openclaw cron `stock-slack-briefing`, 평일 15:40) |
| `slack_text.py` | 텍스트 → 슬랙 |
| `test_slack_alert.py` | 관심종목 오늘 변동 슬랙 테스트(국장/미장 구분, KRX 장시간 표시) |
| `debate.py` | `#ai-토론` 슬랙 채널: GPT/Gemini/Qwen/Mistral 다중 모델 토론(개별답변·토론·상태·도움말). `debate` 에이전트가 exec 로 호출, stdout 그대로 답장. GPT는 API키 대신 게이트웨이 경유 ChatGPT Plus OAuth(무툴 에이전트 `debate-gpt`). 상세: HANDOFF.md "AI 토론 채널" |
| `get_notion_book.py` | 책읽남(bookman) 독서 브리핑. 노션 '독서 리스트' DB에서 **실제로 적혀 있는 문장만** 1건 추출. 못 찾으면 지어내지 않고 exit 2. **색칠·형광펜·인용 문장을 최우선**으로 고르고, 애매한 줄은 버리는 대신 후순위로 미룬다(빈손 방지). 본문은 캐시. 노션 **`책읽남` 열이 `제외`** 인 책은 후보에서 뺀다. `--check`/`--list`/`--book`/`--build-cache`/`--reset` 지원 |
| `book_slack.py` | **책 글귀 → 슬랙 직접 발송(AI 미경유)**. `get_notion_book.py` 를 실행해 결과가 있을 때만 보낸다. **글귀가 없으면 아무것도 안 보내고 조용히 종료(exit 1)** → AI 창작 원천 차단. cron 은 이 스크립트를 호출할 것. 역할 분담 — **책읽남=자료 수집, 뚜떵또=최종 발송(기본)**, `--as bookman` 으로 전환. `--dry-run` 지원 |
| `verify_article_url.py` | ⏸ **브리핑 출력엔 미사용(2026-09-17 링크 기능 중단)**. 단 수집기가 **엉뚱한 기사 본문을 요약하는 것**을 막으려고 내부 검증엔 계속 쓴다. **링크↔제목 대조** — 주소를 실제로 열어 ①도메인(구글뉴스 등 중계주소 탈락) ②기사번호 ↔ canonical 대조 ③제목 유사도 로 '같은 기사'인지 판정. 표준 라이브러리만. `--url/--title` 단건, `--json ... --write` 일괄. exit 0=동일/2=다름. 403 등 봇차단이면 브라우저 헤더로 1회 재시도 |
| `naver_article_search.py` | ⏸ **현재 브리핑에서 미사용(2026-09-17 중단, 나중에 재검토)**. 도구 자체는 보관 — 사용자가 특정 기사 링크를 직접 물으면 그때 쓴다. **제목 → 네이버에서 매경·한경 원문 링크 찾기**. 지면 브리핑(제목만 있음)과 **한국경제 403 우회**용. 원문이 안 열리면 네이버 뉴스 링크를 준다. 유사도 미달이면 **링크를 주지 않는다**(지어내기 차단). 키: `.env` 의 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`(무료, developers.naver.com). exit 0=찾음/2=없음/3=키없음. `--self-test` 로 키 없이 로직 점검 |
| `test_viewer_nav.js` | 신문 사진 뷰어 **넘김 화살표** 동작 확인(실제 Chromium). 1초 자동숨김·되살아남·눌림 차단·사진 바깥 배치·장 넘기기 5가지를 PC/폰 두 화면에서 검사. `npm i playwright && node scripts/test_viewer_nav.js` (개발 환경 전용, 서버엔 불필요) |
| `test_viewer_zoom.js` | 신문 사진 뷰어 **마우스 휠 확대·축소** 확인(실제 Chromium). 휠 위/아래·**커서 지점 고정**·최소(1배)/최대 배율 한계·트랙패드처럼 잘게 굴릴 때 부드러움·형광펜 모드 병행 9항목. `node scripts/test_viewer_zoom.js` (개발 환경 전용) |
| `test_viewer_pan.js` | 확대한 신문 사진 **옮기기** 확인(실제 Chromium). 방향키 상하좌우·**오른쪽 버튼 드래그**(형광펜 모드 포함)·우드래그가 장넘김/닫기를 안 함·1배에선 방향키가 **기존대로 장 넘기기**·확대 중에도 Shift+←→/PageUp·Down 으로 장 넘김·경계 제한·우클릭 메뉴 차단 17항목. `node scripts/test_viewer_pan.js` (개발 환경 전용) |
| `test_viewer_mark.js` | 신문 사진 **형광펜** 동작 확인(실제 Chromium). 형광펜은 **일회성** — 새로고침하면 사라지고 **서버·브라우저 저장소에 아무것도 안 남긴다**. 도구 3가지(**직선**=자 댄 듯 수평/수직 보정, **동그라미**=타원, 자유)와 색 3가지(빨강·파랑·노랑), **선 굵기 3단계**(`[`·`]`), **동그라미를 그린 직후 안쪽을 끌어 위치 옮기기**(방향키 미세조정·사진 밖 안 나감·크기 유지), 켜기·긋기·**새로고침 시 소멸**·**요청 0건/저장소 0개**·확대 시 따라붙기·창 열린 동안 유지·장별 분리·되돌리기·지우개(동그라미는 테두리 판정)·모드 중 스와이프 차단·다른 창과 분리·**도구모음이 켰을 때만 나오고 사진을 안 가림**(폰 390px 포함) 56항목. `node scripts/test_viewer_mark.js` |
| `test_viewer_paper.js` | 다이제스트 **보기 방식 2가지**(`📝 글만`=기존 / `📰 글+지면`=기사 옆에 실린 신문 사진, 누르면 형광펜 켜진 뷰어) 확인(실제 Chromium). 사진 번호는 **GPT 가 요약할 때 붙이는** `• 사진: 07` 줄(요약은 사용자의 **ChatGPT 슬랙 앱**이 만듦 → 규칙은 ChatGPT 지시문에 넣어야 함. SOUL.md 에도 있음, `07.jpg`·`07, 08` 변형도 인식) 또는 **📌 직접 연결**(이 브라우저 `localStorage` 에만 기억), 번호 없으면 **짐작 안 함**. 슬랙 앱 꼬리표(`다음을 사용하여 보냄 <@U…>`) 제거도 확인 · 형광펜은 여전히 저장 0 · 폰 390px 40항목. `node scripts/test_viewer_paper.js` |
| `test_viewer_font.js` | 다이제스트 **요약 글자 크기 조절** 확인(실제 Chromium). 툴바 오른쪽 `[가− 100% 가+]` 6단계(90~160%), 가운데 숫자=100%로. 요약 글은 전부 `px × --fs` 로 계산돼 제목·카테고리·본문·WHAT 라벨이 **같은 비율**로 커지고 버튼·시간·사진 뷰어는 그대로. 글이 커지면 '글만' 폭도 넓힘(한 줄 길이 유지). 한국어 **낱말 중간 줄바꿈 금지(keep-all)**. `localStorage` `digest.fontScale` 하나만 저장 · 폰 390px 19항목. `node scripts/test_viewer_font.js` |
| `test_viewer_list.js` | 요약 속 **"🔍 …반드시 연결해서 봐야 할 5가지" 머리말 뒤 줄바꿈 + 번호 목록** 확인(실제 Chromium). 한 줄에 붙어 온 `…5가지 1. … 2. …` 을 머리말(`.brf-sec`) + 한 항목씩(`.brf-num`, 번호 배지·내어쓰기)으로 나눈다. 머리말은 `N가지/포인트/체크포인트/키워드/정리` 로 끝나야 하고 번호는 **1→2→3 순서대로 이어질 때만** 자른다 → `3.5%`·`1. 5배`·평범한 대화 숫자는 오인 안 함. 번호 아래 **설명 줄은 그 항목에 흐리게 붙이고**(1번만 특별해지던 문제), 목록은 카테고리나 `• WHAT` 앞 새 기사 제목에서만 끝난다. **`📌 …핵심 한 줄`→강조 상자, `✅ …체크할 핵심 주제` 아래 줄→✓ 체크 칸(PC 2열·폰 1열)**, `🔴 반드시 체크 | 제목` 기사·평범한 대화는 오인 안 함. PC/폰 42항목. `node scripts/test_viewer_list.js` |
| `news_page_text.py` | **지면 글자 읽기 → 요약 기사와 신문 사진 자동 연결**(2026-09-24). 요약(ChatGPT)에 `• 사진: NN` 이 빠져도 되게, 서버가 사진마다 **tesseract**(무료 글자 인식, AI·인터넷·요금 없음)로 글자를 읽어 대조용 조각(숫자 3자리↑·소수 / 한글 낱말 앞 2·3글자 / 영문 약어)을 `news_cache/<날짜>/page_text.json` 에 저장. 웹이 `/api/news/pagetext` 로 받아 요약 기사와 점수 대조(숫자 2.5배, 드문 말일수록 높게) → 1등이 충분히 높고 2등보다 1.35배 앞설 때만 붙인다(애매하면 짐작 안 함). 우선순위: 📌직접 연결 > `• 사진: NN` > 자동 대조. ⚠️ 조각 규칙은 Python `tokens()` 와 JS `pageTokens()` 를 **함께** 고칠 것. `news_sync.py` 가 사진 준비 직후 자동 호출(`NEWS_PAGE_OCR=0` 으로 끔), 읽은 장은 건너뜀. **서버 설치 필요: `sudo apt-get install -y tesseract-ocr tesseract-ocr-kor`**. `--all`/`--show`/`--force` |
| `test_viewer_match.js` | 위 자동 연결 확인(실제 Chromium + 실제 tesseract). 가짜 지면 4장(JPG+GIF)을 그려 읽히고, Python·JS 조각 규칙 일치 · 요약 기사 3개가 맞는 장에 붙음 · 지면에 없는 기사는 안 붙임 · 직접 연결 우선. tesseract 없으면 건너뜀. `node scripts/test_viewer_match.js` |
| `test_viewer_json.js` | **요약 GPT 의 '기사↔지면' JSON 묶음**으로 연결 확인(실제 Chromium). 요약 끝 `{"articles":[{"title","page","bbox"}]}` (```json 감싼 것·안 감싼 것·깨진 것) 를 **화면에서 숨기고** 읽어, page=사진 번호로 연결 · 제목이 조금 달라도 짝 찾기(글자 2개 조각 60%↑) · **bbox(기사 영역, 0~1 비율)가 있으면 그 부분만 잘라 보이고 🖍 는 그 기사로 확대된 채 열림**(🔍 크게=지면 전체) · 같은 장 다시 열어도 확대 적용. 우선순위 📌직접 > JSON > `• 사진: NN` > 지면 글자 대조. ChatGPT 에 붙일 지침: **`docs/chatgpt-newspaper-prompt.md`**. 16항목. `node scripts/test_viewer_json.js` |
| `news_sync.py` | **그날 신문 원본(사진·PDF)을 웹이 읽을 캐시로 준비**. ①**서버 로컬 우선** — 수집기(`~/newspaper/data/newspapers/YYYY-MM/YYYY-MM-DD/`)가 만들어 둔 파일을 **심볼릭 링크**로 연결(인증·네트워크·디스크 추가 0). ②없으면 구글 드라이브(`gog` CLI, 형태 자동탐색+기억 `.gog_shape.json`, `--probe` 진단). `--source auto|local|drive`. 종료코드 0=성공/2=아직 없음/1=오류 |
| `patch-newspaper-keep-local.sh` + `newspaper_keep_local.py` | 수집기가 업로드 후 로컬을 지우던 `shutil.rmtree(local_dir)` 한 줄을 **'오늘치는 남기고 지난 날짜만 정리'**로 교체(멱등·백업·문법검사·`--revert`·`--dry-run`). 지난 날짜는 `metadata.json` 보존. 보관일수 `NEWSPAPER_KEEP_DAYS`(기본 1) |
| `patch-newspaper-title-filter.sh` + `newspaper_title_filter.py` | ⚠️ **2026-09-16 사고 대응**: 수집기가 제목의 **날짜만** 보고 글을 골라 `26.9.16 미모`(6장)를 신문(30장)으로 착각해 드라이브까지 덮어썼다. → 제목에 `NEWSPAPER_TITLE_KEYWORD`(기본 `신문스크랩`)가 있어야 통과하도록 조건 추가. 못 찾으면 실패 처리 → `run_daily.sh` 재시도 루프가 돈다. `NEWSPAPER_TITLE_EXCLUDE` 도 지원 |
| `set-newspaper-schedule.sh` | 신문 수집 cron 시작 시각 변경(기본 05:00). `run_daily.sh` 가 원래 5분 간격·07:00 마감 재시도라 **05:00~07:00 사이 5분마다 확인**이 된다 |
| `retention_cleanup.py` | **날짜별 자료 보관 기간을 한 곳에서 관리**(2026-09-19 신설). 대상: `news_cache`(사진·PDF, 기본 **14일**) · `slack_logs`(요약 텍스트, 기본 **무제한**) · `news_marks`(형광펜 잔재, 14일). **달력 날짜 기준** — 예전 '최근 N개 폴더' 방식은 평일만 올라오는 신문 탓에 9~10일 전까지 남았다. 안전장치: 이름이 정확히 `YYYY-MM-DD` 인 것만 삭제 · **가장 최근 1개는 무조건 보존** · 홈 밖 경로 거부 · 심볼릭 링크는 링크만 지우고 원본 보존. `--status`(현황 + **깨진 링크 경고** — 원본이 지워져 사진이 안 열리는 상태를 잡아낸다, 2026-09-20 실제로 96개 중 62개 발생) / `--dry-run`(미리보기) / `--days` / `--only`. cron 불필요 — `news_sync.py` 가 30분마다 불러 쓴다. 검증: `python3 scripts/test_retention_cleanup.py` (15항목) |
| `setup-news-cron.sh` | 위 동기화를 30분마다 돌리는 cron 등록(멱등). cron 에 `XDG_RUNTIME_DIR` 을 넣어 gog keyring 잠금 해제 문제를 피한다 |
| `notion_push.py` / `notion-briefing-*.txt` | (구) 노션 저장 — **시트로 대체됨, 미사용** |

> 상세 현황·다음 할 일은 **`HANDOFF.md`** 참고.
