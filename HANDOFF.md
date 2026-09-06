# HANDOFF — 현재 상태 & 다음 할 일

> 먼저 `CLAUDE.md`(규칙/함정)를 읽으세요. 이 문서는 진행 현황과 남은 작업입니다.
> 서버: openclaw = `/home/ubuntu/.openclaw`, stock = `/home/ubuntu/stock/stock`.

## 🗂️ 무엇이 어디서 도나 (편집 위치)
- **openclaw 폴더에서 돎(=claude.ai 편집·동기화 가능)**: 뉴스 브리핑(`cron/jobs.json` + `workspace/news_fetcher.py` + `workspace/SOUL.md`), PT 트레이너(`agents/pt-trainer/`), 날씨 브리핑(`cron/jobs.json`). 단 `openclaw.json`/`.env`(비밀)는 서버 전용.
- **주식 프로젝트**: 실행은 `~/stock/stock`(nohup `scheduler.py`). ✅ **소스 vendoring 완료**(2026-08-04): openclaw repo `stock/` 에 40개 `.py` 반입됨 → 이제 **claude.ai 에서 stock 코드 편집 가능**. `git-auto-pull.sh` 후 `scripts/sync-stock.sh` 가 코드만 rsync + 변경 시 scheduler 재시작.
  - **env 통합**: 서버에서 `~/stock/stock/.env` 를 `~/.openclaw/.env` 로 심볼릭 링크(비밀 한 곳). 둘 다 gitignore.
  - **텔레그램 폐기**: stock 알림은 이제 **슬랙 전용**. `TELEGRAM_BOT_TOKEN`/`BRIEFING_BOT_TOKEN` 미설정이어도 `send_telegram_message`는 조용히 False 반환(무해). 로그 노이즈 제거하려면 `stock/notifier.py`/`scheduler.py` 정리 가능.
  - **KIS 키**: `market_data` 가 KIS 우선·yfinance 폴백. KIS 키 없으면 yfinance 로 자동 폴백(동작하나 가끔 `^GSPC` 등 불안정). 신뢰도 위해 `~/.openclaw/.env` 에 `KIS_APP_KEY/KIS_APP_SECRET/KIS_ACCOUNT_NO` 있으면 좋음.
  - seed-stock 임시 브랜치(origin) 잔존 — VS Code 에서 `git push origin --delete seed-stock` 로 정리.
  - **프로세스 구조**: `scheduler.py` 는 정상적으로 **2 프로세스**(스케줄러 본체 + uvicorn 웹워커, 포트 8000). 3개 이상이면 중복 의심. `sync-stock.sh` 가 재시작 시 0개 확인 후 1개만 기동.
  - **사이드카 슬랙**: ✅ 완료. `alert_job` 1.2 블록에서 `sas.send_slack(sidecar_message)` 로 KOSPI/KOSDAQ 사이드카 발동 시 슬랙 전송(장중만 발동 → 게이팅 불필요).
  - **yfinance 차단(서버 IP)**: `^GSPC/^IXIC/QLD/TQQQ` 등 실패. 국내는 KIS(토큰 정상)로 OK. 부작용: ①시작 시 ATH 로딩이 느림(1~2분, default_ath 폴백 후 진행) ②US 지수/ETF live 데이터 부실. **개선안**(선택): ATH 로딩을 KIS/비차단·비동기로 바꾸거나 yfinance 의존 축소. stock/ vendoring 됐으니 claude.ai 에서 편집 가능.

## ✅ 완료된 것
1. **자동 git 동기화**: 클로드에서 openclaw main에 push → 서버 cron(1분)이 pull + `openclaw daemon restart`. 런타임 파일 추적 제외.
2. **비밀 → .env 정리** + `SECRETS.md`/`.env.example`. (일부는 아직 openclaw.json 평문 — 감사 남음. 노출 키 재발급 권장.)
3. **뚜떵또(openclaw AI) 모델**: **주 = GPT(OpenAI)** 로 살림(어제 크레딧 충전 + `onboard --classic`). 정상 동작 중.
4. **온디맨드 신문 브리핑**: 정해진 시각 자동 브리핑 **OFF**. 사용자가 봇에 "신문 브리핑 해줘" 요청 시에만 → 분석 답변 + **구글 시트 저장**(`sheets_push.py`, `workspace/SOUL.md`에 규칙 있음).
   - 구글 시트: Apps Script 웹앱. `.env`에 `SHEETS_WEBAPP_URL`, `SHEETS_WEBAPP_SECRET`.
   - (노션은 시트와 병행 사용 중. `notion_push.py`로 저장.)
     - ⚠️ **저장 대상 바로잡기(오연동 → 원하는 페이지)**: 브리핑이 엉뚱한 DB(`신문 브리핑` `3b1d470c…`)에 저장되던 것을 사용자가 지정한 페이지 **"⭐ AI꿀팁 모음"** `3b5d470c68bd80c1a88dfa79b4581de8` 로 변경. 서버에서 `.env` 만 바꾸면 됨:
       ```bash
       cd ~/.openclaw
       # 신규 변수(권장). 하위호환으로 NOTION_BRIEFING_DB 도 계속 읽힘.
       grep -q '^NOTION_BRIEFING_TARGET=' .env \
         && sed -i 's#^NOTION_BRIEFING_TARGET=.*#NOTION_BRIEFING_TARGET=3b5d470c68bd80c1a88dfa79b4581de8#' .env \
         || echo 'NOTION_BRIEFING_TARGET=3b5d470c68bd80c1a88dfa79b4581de8' >> .env
       # (구 변수 NOTION_BRIEFING_DB 가 있으면 같이 맞춰두면 혼동 없음)
       sed -i 's#^NOTION_BRIEFING_DB=.*#NOTION_BRIEFING_DB=3b5d470c68bd80c1a88dfa79b4581de8#' .env
       ```
       그리고 노션 통합(Integration)이 "⭐ AI꿀팁 모음" 페이지에 **연결(공유)** 돼 있어야 함(⋯ → 연결 → 통합 선택). 안 돼 있으면 `detect_target_kind` 가 접근 불가로 실패.
5. **stock 대시보드 → 슬랙**: 평일 **15:40** openclaw cron `stock-slack-briefing`(command job) → `slack_briefing.py`. 채널 `C0BMJENDF62`. AI 미사용, 정상.
6. **stock 관심종목 급등락 알림**: `scheduler.py alert_job`(약 10분) → 텔레그램 `briefing-bot`. 2% 단위. AI 미사용, 정상.
7. **관심종목 알림 슬랙 확장(+시간대 게이팅)**: 텔레그램 그대로 두고 **슬랙에도** 전송. 국장(숫자코드)=KRX 장중만, 미장=24h. `scripts/stock_alert_slack.py`(`notify_events`) + `patch_scheduler_slack.py` 로 서버 반영·검증 완료. (상세: 아래 C)

## 💪 종국이(GYM종국) 데일리·주간 브리핑 — ✅ 신규 (2026-08-16)
"종국이는 답을 잘하는데 데일리/주간 브리핑을 안 한다" → **자동 브리핑 복원 + 웹 표시**.
- **원인**: keepgoing(종국) 에이전트엔 브리핑 cron 이 아예 없었음(구 `cron/jobs.json` 은 삭제됐고, 있던 잡도 전부 **텔레그램(비활성)** 로 발송). PT 웹 대시보드엔 `briefings` 테이블·`/api/briefings`·"📢 김종국 브리핑" UI 가 **이미 완성**돼 있었으나, 브리핑을 **생성·저장하는 주체가 없어** 늘 비어 있었음.
- **해결 = 자급식 스크립트** `scripts/pt_briefing.py` (AI 모델 불필요, 규칙 기반):
  1. PT DB(`~/pt_data/pt.db`)에서 운동/식단/컨디션 읽기 → 2. 김종국 말투(반말+ㅎ, 팩폭+사랑, USER.md 벌칙/단백질/수면 기준)로 데일리/주간 브리핑 작성 → 3. `briefings` 테이블 저장(**웹 대시보드에 즉시 표시**) → 4. 슬랙 종국 채널 전송(**종국이가 말하듯**).
  - 실행: `python3 scripts/pt_briefing.py daily|weekly` (옵션 `--print` 미리보기, `--no-slack`, `--no-db`, `--date YYYY-MM-DD`). DB에는 별표 없는 평문, 슬랙엔 `*볼드*` mrkdwn.
  - `.env`: `SLACK_BOT_TOKEN_KEEPGOING`(없으면 `SLACK_BOT_TOKEN` 폴백), `SLACK_KEEPGOING_CHANNEL`(없으면 기본 `C0BMN9FN073`), `PT_PROTEIN_GOAL`(기본 100), `PT_SLEEP_MIN`(기본 6).
- **스케줄(서버에서 1회)**: `scripts/setup-briefing-cron.sh` — OS crontab 에 데일리 21:00 / 주간 일요일 20:00 등록(멱등). 텔레그램·openclaw 내부 cron 스키마에 의존하지 않음.
  ```bash
  cd ~/.openclaw && scripts/setup-briefing-cron.sh   # crontab -l 로 확인
  # 지금 바로 만들어 보기:
  python3 ~/.openclaw/scripts/pt_briefing.py daily --print
  ```
  ⚠️ cron 은 서버 로컬 타임존 기준. 서버가 KST 아니면 `DAILY_SCHEDULE`/`WEEKLY_SCHEDULE` 로 시각 환산.
- **웹 표시**: 대시보드(`pt_dashboard.py`, `http://mystatus-btr.duckdns.org`)의 "📢 김종국 브리핑" 섹션에 자동 노출. claude.ai 미리보기 아티팩트도 게시됨(위 대화 참고).

## 🎭 종국이 페르소나(Soul/Identity) 강화 — ✅ 신규 (2026-08-19)

실제 유튜브 'GYM JONG KOOK(짐종국)' 분석을 반영해 종국이 캐릭터를 **3층 구조**로 재정리했다.
(기존엔 `SOUL.md`가 "이모지·ㅎ 금지, 냉정한 톤", `IDENTITY.md`가 "ㅎ 자주, 감탄사"로 **서로 충돌**했었음.)

| 파일 | 역할 | 우선순위 |
|---|---|---|
| `workspace/keepgoing/SOUL.md` | **왜** — 5대 신념·코칭 범위·벌칙 프로토콜·기록 저장 규칙 | 1 |
| `workspace/keepgoing/IDENTITY.md` | **어떻게** — 말투 정본. 평소/세트 2모드, '맛' 어휘, 자세 3대 체크 | 2 |
| `workspace/keepgoing/engines/CueEngine.md` | **무슨 말** — 시그니처 대사 뱅크·부위별 큐·상황별 스크립트 (신규) | 3 |

- 핵심 추가: **평소↔세트 모드 스위치**(푸시할 땐 "ㅎ" 빼고 명령형 → 끝나면 즉시 복귀),
  **이완 중심 코칭**(견갑/가슴 오픈/엘보), **'맛' 어휘**, **먹는 것까지가 운동**, **음주 단호 대응**,
  안전장치 **"힘든 것 ≠ 아픈 것"**(통증은 푸시 금지).
- `AGENTS.md`: 페르소나 로드 순서·절대 규칙 3가지·응답 마감 체크리스트 추가.
- `engines/WorkoutEngine.md`: 세트 질(質) 3기준(이완/타겟감각/마지막 1~2개), 강도 도구(강제반복·드롭세트·템포), 40분 루틴 프레임.
- `engines/NutritionEngine.md`: 운동 후 골든타임, 식단 프레임 표, 음주 판단 규칙, 직장인 상황별 대응표.
- **슬랙 실제 문구도 강화**: `scripts/pt_briefing.py` 에 뱅크 추가 —
  `DAILY_CUES`(🔧 오늘의 한 줄 코칭 섹션 신설), `CLOSERS_GOOD/MID/NONE`, `FAMILY_CLOSERS`.
  날짜 기준 결정론적 로테이션(`pick()`)이라 같은 문장이 연속으로 안 나온다. 주간 브리핑에도 적용.
- 미리보기: `python3 scripts/pt_briefing.py daily --print --no-slack --no-db --date YYYY-MM-DD`

## 🗞️ 슬랙 #gpt 채널 다이제스트 (뷰어)
슬랙 접속 불가 환경에서 **#gpt 채널 대화**를 웹(`http://<서버>:8000/slack`)으로 읽는 기능.
- ✅ **2026-08-31: #gpt 채널 전용으로 축소.** 원래는 신문/주식브리핑/주식알림 채널까지 방 탭으로 나눠 보여줬으나, 사용자 요청으로 **#gpt 채널만** 표시하도록 단순화(다른 채널 코드는 제거).
- **조회 방식**: `stock/app.py`의 `_fetch_slack_history_api`가 Slack API(`conversations.history`)로 `SLACK_GPT_CHANNEL`(기본값 `C0BTHMT2M7X`) 채널을 직접 읽고, 로컬 로그(`~/.openclaw/slack_logs/YYYY-MM-DD.jsonl`, 같은 채널 ID인 것만)와 병합. bot_id 있으면 "뚜떵또 답변", 없으면 "사용자 질문"으로 분류.
- **뷰어**: `stock/slack_digest_live.html` — 시간축 타임라인, 카테고리 필터(뚜떵또 답변/사용자 질문), 라이트/다크, 20초 자동 갱신. 슬랙 `:emoji_code:` 표기는 실제 이모지로 변환(매핑 없는 코드는 표시 안 함).
- (참고) 신문/주식브리핑/주식알림 채널로 보내는 기능 자체(`slack_briefing.py`, `stock_alert_slack.py` 등)는 그대로 동작 — 이 뷰어에서만 안 보일 뿐.

## 🔐 PT 대시보드 구글 로그인(OAuth) — 코드 완료, 서버 설정만 남음
`scripts/pt_dashboard.py`(포트 5001) 접근을 **구글 로그인**으로 잠갔다. 허용된 이메일만 입장.
- **동작**: `.env` 에 구글 키가 있으면 인증 ON, 없으면 **열린 채 유지(경고만)** → auto-pull 직후 잠겨서 못 들어가는 사고 방지. 미로그인 시 `/`=로그인 페이지, `/api/*`=401, `/auth/start`→구글, 로그인 성공+허용 이메일이면 세션 발급. `/logout` 로그아웃, `/healthz` 는 무인증.
- **보안**: CSRF `state` 검증, 이메일 화이트리스트(`PT_ALLOWED_EMAILS`), 세션 쿠키 HttpOnly/SameSite=Lax/Secure, nginx 뒤 https 대응(ProxyFix). 새 의존성 없음(`requests`만 사용).

**서버에서 켜는 법**(한 번만):
1. **구글 클라우드 콘솔**에서 OAuth 클라이언트 ID 생성 (https://console.cloud.google.com/apis/credentials)
   - 애플리케이션 유형: **웹 애플리케이션**
   - **승인된 리디렉션 URI**: `https://<대시보드 공개주소>/auth/callback` (정확히 일치해야 함)
2. `~/.openclaw/.env` 에 값 추가:
   ```bash
   cd ~/.openclaw
   cat >> .env <<'EOF'
   GOOGLE_OAUTH_CLIENT_ID=<콘솔에서 발급한 클라이언트 ID>
   GOOGLE_OAUTH_CLIENT_SECRET=<클라이언트 보안 비밀>
   PT_ALLOWED_EMAILS=bbonoyo@gmail.com
   FLASK_SECRET_KEY=<openssl rand -hex 32 결과>
   EOF
   ```
3. **대시보드 재시작**(pt_dashboard 프로세스 종료 후 재기동). 시작 로그에 `[Info] 구글 로그인 활성화` 뜨면 성공.
   - ⚠️ 리디렉션 URI 가 콘솔과 1글자라도 다르면 `redirect_uri_mismatch`. 콜백은 `.../auth/callback`.
   - ⚠️ https 프록시가 아니라 순수 http 로 접속하면 쿠키가 안 붙어 로그인 루프 → 임시로 `.env` 에 `PT_COOKIE_SECURE=0`.

## 🗣️ AI 토론 채널(#ai-토론) — 🟢 채널 연결·Gemini 응답 확인됨, GPT/Qwen/Mistral 키 설정 남음 (2026-09-04)

`openclaw_multi_model_debate_plan.md` 계획서 기반으로 GPT/Gemini/Qwen(OpenRouter 무료)/Mistral(무료) 4개 모델이
독립 의견 → (선택) 1회 반론 → GPT 사회자 종합까지 하는 슬랙 토론 채널을 구축했다.
**기존 main/pt-trainer/keepgoing 에이전트·바인딩은 전혀 건드리지 않았다** (새 에이전트 `debate`/`debate-gpt` + 새 바인딩만 추가).

**진행 상황**: 슬랙 채널(`C0BUT6PPBC1`) 바인딩 완료, `#ai-토론`에서 `@그레이트리 상태`/실제 질문 테스트 성공(Gemini 정상 응답, 나머지는 키 미설정으로 정상 실패 표시). GPT는 API 키 대신 **ChatGPT Plus 구독 OAuth 세션**을 쓰도록 구조를 바꿨다(아래).

### 구조
```
Slack #ai-토론 (채널ID C0BUT6PPBC1, 멘션 시에만 응답)
   ↓
openclaw agent "debate" (workspace/debate/SOUL.md)
   → exec 로 scripts/debate.py "<원문>" 실행 → stdout 을 그대로 답장
        ↓
   scripts/debate.py
        ├─ GPT      openclaw 게이트웨이 Chat Completions HTTP API
        │            (http://127.0.0.1:18789/v1/chat/completions, GATEWAY_TOKEN)
        │            → 전용 무툴 에이전트 "debate-gpt"(tools.profile=minimal, exec deny) 호출
        │            → main 이 이미 로그인해둔 ChatGPT Plus OAuth 세션으로 처리, 별도 API 키/과금 없음
        ├─ Gemini   (Google Generative AI 네이티브 API, 기존 GEMINI_API_KEY 재사용) ✅ 확인됨
        ├─ Qwen     (OpenRouter, OPENROUTER_API_KEY, :free 모델)
        └─ Mistral  (Mistral API, MISTRAL_API_KEY, 무료 모드)
```
- 모드: 무키워드/`개별답변:` = 개별 답변(모델별 의견+사회자 종합, 5회 호출), `토론:` = 1차의견→반론1회→사회자 종합(9회 호출), `상태`/`도움말` = API 호출 없음.
- 사회자의 "핵심 주장 정리"는 별도 LLM 호출 없이 스크립트가 기계적으로 조합 → 계획서 §12 비용 예산(5회/9회) 그대로 지킴.
- 장애 처리(계획서 §8 그대로 구현): 429=1회 재시도 후 "한도초과" 표시, 401/403=재시도 안함, 타임아웃="응답 지연" 표시, 모델 하나 실패해도 나머지+사회자 요약 계속, 무료 모델 ID 오류(400/404)시 예비 모델로 1회 전환, 사회자(GPT) 실패시 모델 원문만이라도 게시, 전체 실패시 오류 요약+재시도 안내.
- 분당 호출 제한(기본 3회/분)과 사용량 로그는 `workspace/debate/state/`(git 추적 제외, 런타임 전용)에 자동 저장.
- Gemini/Qwen/Mistral은 함수 호출/툴을 전혀 주지 않는 순수 텍스트 API 호출이라 "명령 실행·파일쓰기·메시지 발송 금지" 원칙이 코드 구조상 자동으로 지켜짐. GPT는 openclaw이 "정상 에이전트 한 턴"으로 처리하므로 완전 격리는 아니지만, 전용 에이전트 `debate-gpt`에 `tools.profile: "minimal"` + `deny: ["exec"]`로 최대한 막아뒀다.

### 📌 서버에서 수동으로 해야 하는 것 (남은 것)
1. ~~Slack 채널 생성/바인딩~~ ✅ 완료 (`C0BUT6PPBC1`).
2. ~~GPT API 키 발급~~ → **불필요해짐.** 대신 아래만 확인:
   - `~/.openclaw/.env` 에 `GATEWAY_TOKEN` 이 이미 있는지 확인(기존 게이트웨이가 쓰던 값 그대로 재사용, 새로 발급 불필요): `grep '^GATEWAY_TOKEN=' .env`
   - main 에이전트가 이미 OpenAI OAuth(Plus)로 로그인돼 있는지 확인: `openclaw models status` (안 돼 있으면 `openclaw models auth login --provider openai`)
   - `openclaw config validate` 로 새 게이트웨이 설정(`gateway.http.endpoints.chatCompletions.enabled`)과 `debate-gpt` 에이전트가 유효한지 확인 후 `openclaw daemon restart`.
3. **나머지 2개 API 키 발급 후 `~/.openclaw/.env` 에 추가**(`.env.example` §11 참고):
   - `OPENROUTER_API_KEY` (https://openrouter.ai/keys)
   - `MISTRAL_API_KEY` (https://console.mistral.ai/ → Studio 무료 모드 활성화 후 발급)
4. **무료 모델 ID 확정**(자주 바뀜 — 반드시 구축 당일 확인): OpenRouter에서 `:free` 로 끝나는 Qwen 계열 모델 ID, Mistral 무료 계정에서 쓸 수 있는 모델 ID를 조회해 `.env` 의 `DEBATE_QWEN_MODEL` / `DEBATE_QWEN_MODEL_FALLBACK` / `DEBATE_MISTRAL_MODEL` / `DEBATE_MISTRAL_MODEL_FALLBACK` 에 채운다.
5. 위 완료 후 서버에서 검증:
   ```bash
   cd ~/.openclaw
   python3 scripts/debate.py "상태"          # 키 등록 여부/모델ID 확인 (API 호출 없음)
   python3 scripts/debate.py "테스트 질문입니다"  # 실제 4개 모델 호출 확인
   ```
6. (선택) 결제수단 등록된 공급자(OpenRouter/Mistral)는 지출 한도를 0원 또는 매우 낮게 설정.

### 아직 안 된 것 / 주의
- Qwen·Mistral 정확한 모델 ID는 코드에 **placeholder**만 있다(위 4번 전에는 "모델 미설정" 오류로 실패 표시됨 — 의도된 동작).
- **GPT 게이트웨이 경로는 아직 실서버에서 실제 호출 검증 전** — `gateway.http.endpoints.chatCompletions` 설정 키와 `debate-gpt` 에이전트의 `tools.profile: "minimal"` 동작은 openclaw 공식 문서(웹검색 기반, 직접 fetch는 네트워크 정책상 불가했음)를 근거로 구현했다. **처음 GPT 호출 시 다음을 꼭 확인**: ①정상 텍스트가 오는지 ②`openclaw daemon` 로그에 `debate-gpt`가 exec/파일 접근을 시도한 흔적이 없는지(`journalctl --user -u openclaw-gateway.service | grep debate-gpt`).
- 계획서의 "시작 시 진행 메시지 한 번"은 `debate` 에이전트가 exec 호출 전에 먼저 텍스트로 답하도록 SOUL.md 에 지시했지만, 실제로 슬랙에 두 번째 메시지로 분리돼 나가는지는 openclaw 런타임의 중간 텍스트 스트리밍 동작에 달려있다 — **서버에서 실제로 확인 필요**.
- 빈 멘션(질문 없이 봇 이름만 멘션)일 때 `debate` 에이전트가 질문을 지어내 스크립트에 넘기는 사례 관찰됨(사소한 버그, 아직 미수정) — SOUL.md에 "질문 없으면 지어내지 말고 도움말 안내" 규칙 추가 필요.
- 이 기능은 기존 `main`/`keepgoing`/`bookman`/`pt-trainer` 와 완전히 분리돼 있어, 문제가 생기면 `openclaw.json` 에서 `debate`/`debate-gpt` 항목만 지우면 즉시 롤백된다(계획서 §15 롤백 계획). GPT 게이트웨이 경로가 말썽이면 `gateway.http.endpoints.chatCompletions.enabled`를 `false`로 되돌리는 것만으로도 그 경로만 차단 가능.

## ⏳ 진행 중 / 다음 할 일 (우선순위 순)

### A. Gemini 백업(fallback) 적용
GPT 주력 유지 + Gemini 무료 백업(`gemini-flash-lite-latest` → `gemini-flash-latest`).
> 💡 **openclaw 2026.7.1-2 는 `google.api="openai-chat"` 를 거부**하므로 native `google-generative-ai` API 규격을 사용하도록 `jq` 커맨드를 업데이트했습니다. `openclaw config validate` 로 선검증 후 daemon을 restart 하십시오.

서버에서:
```bash
cd ~/.openclaw
GKEY=$(grep '^GEMINI_API_KEY=' .env | cut -d= -f2-)
UNIT=~/.config/systemd/user/openclaw-gateway.service
sed -i '/^Environment=GEMINI_API_KEY=/d' "$UNIT"; sed -i "/^\[Service\]/a Environment=GEMINI_API_KEY=$GKEY" "$UNIT"
systemctl --user daemon-reload
cp openclaw.json openclaw.json.bak-fb.$(date +%s)
jq '.agents.defaults.model.fallbacks=([ (.agents.defaults.model.fallbacks // [])[] | select(startswith("openai/")) ] + ["google/gemini-flash-lite-latest","google/gemini-flash-latest"]) | .agents.defaults.models=((.agents.defaults.models // {}) + {"google/gemini-flash-lite-latest":{},"google/gemini-flash-latest":{}}) | .models.providers.google.api="google-generative-ai" | del(.models.providers.google.baseUrl) | .models.providers.google.models=((.models.providers.google.models // []) + [{"id":"gemini-flash-lite-latest","name":"gemini-flash-lite-latest"},{"id":"gemini-flash-latest","name":"gemini-flash-latest"}] | unique_by(.id)) | .agents.list |= map(if .model then .model.fallbacks=([ (.model.fallbacks // [])[] | select(startswith("openai/")) ] + ["google/gemini-flash-lite-latest","google/gemini-flash-latest"]) else . end)' openclaw.json > /tmp/oc.json && jq empty /tmp/oc.json && mv /tmp/oc.json openclaw.json
openclaw daemon restart
openclaw config validate
jq '.agents.defaults.model' openclaw.json
```
검증: `curl -H "x-goog-api-key: $GKEY" https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent -H "Content-Type: application/json" -d '{"contents": [{"parts":[{"text": "Explain quantum computing in one sentence."}]}]}'` -> 정상 응답 확인.

### B. 텔레그램 15:30~40 "지수 브리핑"(대시보드 캡처) 끄기 — 요청됨
`stock/scheduler.py`의 `daily_job` add_job 블록을 주석 처리(파이썬 패처 준비됨). 슬랙 15:40·관심종목 알림은 유지.
```bash
cd ~/stock/stock; cp scheduler.py scheduler.py.bak-$(date +%s)
python3 - <<'PY'
import re
f="scheduler.py"; s=open(f,encoding="utf-8").read()
pat=re.compile(r"(^[ \t]*)scheduler\.add_job\(\s*\n\s*daily_job\b.*?\n[ \t]*\)[ \t]*$", re.DOTALL|re.MULTILINE)
cm=lambda m:"\n".join(("# "+l if l.strip() else l) for l in m.group(0).splitlines())
new,n=pat.subn(cm,s); open(f,"w",encoding="utf-8").write(new); print("주석 처리:",n)
PY
python3 -c "import ast; ast.parse(open('scheduler.py').read()); print('OK')"
# 반영: systemctl --user restart stock-dashboard  (없으면 수동 nohup 재시작)
```

### C. 관심종목 알림 → 슬랙에도 + 국장/미장 시간대 게이팅 — ✅ **완료·검증됨(2026-08-04)**
요구사항: **국장(숫자 코드 종목)은 KRX 정규장(평일 09:00~15:30 KST)에만, 미장(영문 티커)은 24시간** 알림. 그리고 텔레그램뿐 아니라 **슬랙에도** 전송.

**정책**(확정): **슬랙만 게이팅, 텔레그램은 그대로.** 텔레그램은 지금처럼 모든 `custom_events` 전송(코드 미변경), 슬랙은 게이팅 통과분만 추가 전송.

**완료 상태**: `patch_scheduler_slack.py` 로 서버 `~/stock/stock/scheduler.py` 에 `notify_events` 삽입(백업 `scheduler.py.bak-slack-*`), `stock_alert_slack.py` stock 폴더 복사, scheduler 단일 인스턴스로 재시작. **슬랙 전송 실채널 검증 완료**(`send_slack` 테스트 메시지 수신 확인). 채널은 `SLACK_BRIEFING_CHANNEL` 폴백 중 — 알림 전용 분리 원하면 stock `.env` 에 `SLACK_ALERT_CHANNEL=C...` 추가.

**✅ 재사용 모듈 완성**: `scripts/stock_alert_slack.py`. **엔진 이벤트 기반**(스냅샷 재스캔 X — `TriggerEngine`의 '한 번만 발동' 상태를 존중해 중복 전송 방지). 게이팅(국장=KRX 정규장/미장=24h) + 슬랙 전송 캡슐화. `event["message"]`가 텔레그램/슬랙 공용 mrkdwn이라 **포맷 그대로 재사용**. 게이팅·경계(15:30/15:31)·빈/전부게이팅 케이스 오프라인 테스트 통과.

서버 코드 위치 확인됨:
- `scheduler.py alert_job` 2번 블록: `custom_events = engine.check_custom_stocks(custom_snapshot)` → `send_telegram_message(format_custom_events(custom_events))`.
- `trigger_engine.py:322 check_custom_stocks` event 구조: `{"symbol","stage","message"}`.
- `notifier.py:19 send_telegram_message` (단순 POST).

서버 적용:
```bash
# 1) 모듈 복사 (※ main 에 머지돼야 서버 auto-pull 이 가져옴. 급하면 수동 복사)
cp ~/.openclaw/scripts/stock_alert_slack.py ~/stock/stock/
# 2) (선택) 단독 미리보기 — 지금 기준 넘고 게이팅 통과한 종목만 슬랙 전송
cd ~/stock/stock && venv/bin/python stock_alert_slack.py     # 맨 python 아님!
```
**연결(자동 패처)** — `alert_job` 의 `sent = send_telegram_message(custom_message)` 다음 줄에 슬랙 호출을 자동 삽입:
```bash
cp ~/.openclaw/scripts/stock_alert_slack.py ~/stock/stock/
cd ~/stock/stock && venv/bin/python ~/.openclaw/scripts/patch_scheduler_slack.py
#   → 백업(scheduler.py.bak-slack-*) 후 삽입 + ast 문법검증. 멱등(재실행 안전).
```
⚠️ **scheduler 재시작 = systemd 아님**(2026-08-04 확인: `stock-dashboard.service` 없음). scheduler 는 `venv/bin/python scheduler.py` (nohup) 로 돎. **다중 인스턴스가 뜨면 알림 중복 발송**되므로 전부 끄고 하나만:
```bash
cd ~/stock/stock
pkill -f "scheduler.py"; sleep 2
ps aux | grep "scheduler.py" | grep -v grep          # 없어야 정상
nohup venv/bin/python scheduler.py > ~/stock/stock/scheduler.log 2>&1 &
sleep 3; ps aux | grep "scheduler.py" | grep -v grep # 딱 1개
tail -30 ~/stock/stock/scheduler.log
```
(nohup 은 재부팅 시 꺼짐 → systemd user 유닛 `stock-scheduler` 로 상시화 권장.)
삽입되는 블록(텔레그램은 그대로, 슬랙만 추가):
```python
                try:
                    import stock_alert_slack as sas
                    sas.notify_events(custom_events)   # 게이팅 통과분만 슬랙 전송
                except Exception as _e:
                    print(f"[Warn] Slack custom alert failed: {_e}")
```
`.env`: `SLACK_BOT_TOKEN` + (선택) `SLACK_ALERT_CHANNEL`(없으면 `SLACK_BRIEFING_CHANNEL` 폴백).

> ⚠️ **주의**: alert_job 연결엔 반드시 `notify_events(custom_events)` 사용. 스냅샷 기반 `preview_moves()`/단독 `main()`은 엔진 dedup을 모르므로 **미리보기 전용**(반복 호출 시 중복 전송). 구 계획의 `notifier.py send_slack_message()` 신설은 이 모듈로 대체됨.

## 참고 상수/값
- Slack 대시보드 채널: `C0BMJENDF62` (`SLACK_BRIEFING_CHANNEL`). 알림 전용 원하면 `SLACK_ALERT_CHANNEL` 추가.
- 구글 시트 DB(신문 브리핑): Apps Script 웹앱(`SHEETS_WEBAPP_URL`).
- 노션 저장 대상(`notion_push.py`): `.env` 의 `NOTION_BRIEFING_TARGET`(하위호환 `NOTION_BRIEFING_DB`).
  - ✅ **원하는 대상 = 페이지 "⭐ AI꿀팁 모음"** `3b5d470c68bd80c1a88dfa79b4581de8` → 하위 페이지로 저장.
  - (구/오연동) DB "신문 브리핑" `3b1d470c68bd80c88009ec6e91c5da3d` → 여기로 잘못 저장되고 있었음.
  - `notion_push.py` 는 대상이 DB인지 페이지인지 **자동 감지**: DB면 행(제목/날짜/시간대), 페이지면 하위 페이지(날짜·시간대는 본문 첫 줄).
  - `notion_setup_db.py`: REST API로 브리핑용 DB 생성(인라인/신형 DB는 REST 400 → 직접 생성 필요). `--page "제목"` 주면 중간 페이지 먼저 생성 후 그 안에 DB.
  - 🔗 **웹링크 저장(+표 분류)**: `notion_save_url.py <URL> --to ai|book|article` → 링크 제목/웹주소(북마크·URL칸)/본문을 카테고리별 표에 저장. SNS(스레드 등)는 크롤러 UA로 og 확보 + 게시물 첫 줄을 제목.
    - 슬랙 키워드 라우팅(SOUL.md): `ai`/링크만→AI꿀팁, `책`→책 추천, `좋은글`→좋은글, `꿀팁`→꿀팁.
    - `.env` 대상 변수: `NOTION_BRIEFING_TARGET`(ai), `NOTION_BOOK_TARGET`(책), `NOTION_ARTICLE_TARGET`(좋은글), `NOTION_TIP_TARGET`(꿀팁).
    - 표 생성: `notion_setup_db.py <부모페이지ID> "<표이름>" --env <변수명>` (제목/날짜/URL 컬럼 자동).
- stock 감시종목: `~/stock/stock/monitored_stocks.json` (국장=숫자코드, 미장=영문). 알림 기준: `CUSTOM_ALERT_STEP`(기본 2%).
- 관심종목 데이터: `market_data.get_custom_stocks_snapshot()` → `{symbol:{name,current,change_rate,is_etf}}`.

## ⚠️ 잊지 말 것
- 노출된 키 **재발급**(텔레그램봇, Slack, Brave, Gateway, Gemini).
- stock `scheduler.py`가 상시 실행돼야 15:40 캡처/알림 동작 (systemd user `stock-dashboard` 권장; 아니면 재부팅 시 꺼짐).


---

## 📚 책읽남(bookman) — "노션에 없는 글귀" 환각 문제 (2026-09 조치)

### 증상
책읽남이 노션 독서 리스트에 **없는 문장**을 그럴듯하게 만들어 브리핑함.

### 원인 (노션 실데이터 확인 결과)
1. **원천 데이터가 거의 비어 있음** — DB "독서 리스트"(`678f2c0b-d124-4889-8571-b019ec30f971`) 총 **132권 중
   `한 문장` 칸이 채워진 건 2권**(그중 1건은 URL), `깨달은 점` 3권. 나머지 127권은 프로퍼티가 빈칸.
   → 랜덤으로 고르면 거의 항상 빈칸 → 모델이 책 제목만 보고 명언을 **창작**.
2. **정작 진짜 문장은 페이지 '본문'에 있다** — 밑줄 친 문장들이 bulleted_list 블록으로 들어가 있음.
   (예: '강원국의 글쓰기' 페이지에 수백 줄)
3. **프로퍼티 이름 함정** — 노션 실제 이름이 `"깨달은 점 "` (**뒤에 공백**). 공백 없이 조회하면 항상 빈값.
4. **폴백이 창작을 허용** — 구 스크립트는 "없으면 기본 문구" 경로가 있었고, SOUL.md 엔
   "지어내지 말 것 / 스크립트를 반드시 실행할 것" 규칙이 없었음.
5. **에이전트 라우팅 의심** — `openclaw.json` `bindings` 에 **bookman 항목이 없다.**
   현재 슬랙 catch-all 은 `{"agentId":"main","match":{"channel":"slack"}}` 이라
   bookman 봇 계정으로 온 메시지가 `main`(신문 분석가)에게 갈 가능성이 크다.
   main 의 SOUL.md 엔 독서 규칙이 전혀 없으므로 **100% 창작**이 된다. → 아래 서버 작업 필요.

### 조치 (이 커밋)
- `scripts/get_notion_book.py` **신규 작성** — 창작 경로 0개.
  - `한 문장` → `깨달은 점`(공백 무시 매칭) → **본문 블록** 순으로 노션 원문만 수집
  - 단어 나열/체크리스트/URL/페이지번호 조각 필터링
  - 쓸 문장이 없으면 `NO_QUOTE` + **exit 2** (기본 문구 만들지 않음)
  - 출처 페이지 URL 을 stderr 로 출력 → 사람이 즉시 대조 가능
  - 토큰은 `.env` 의 `NOTION_TOKEN`, DB 는 `NOTION_READING_DB`(기본값 내장)
  - 중복방지 상태: `workspace/bookman/book_sequence_state.json` (gitignored)
- `workspace/bookman/SOUL.md` **전면 재작성** — 최상단에 "지어내지 않는다 / 스크립트 실행 없이 브리핑 금지 /
  종료코드 2·3 처리법" 명시.
- `workspace/bookman/AGENTS.md`, `openclaw_system_map.md`, `.env.example`, `.gitignore`, `CLAUDE.md` 동기화.

### 서버에서 해야 할 일 (git pull 로는 안 되는 것)
1. **구 스크립트 정리** (하드코딩 토큰 제거):
   ```bash
   mv ~/.openclaw/workspace/get_notion_book.py ~/.openclaw/workspace/get_notion_book.py.old-$(date +%s)
   ```
2. **동작 확인**:
   ```bash
   python3 ~/.openclaw/scripts/get_notion_book.py --check     # 132권 중 몇 권이 채워졌나
   python3 ~/.openclaw/scripts/get_notion_book.py --list 20   # 뽑히는 문장 눈으로 확인
   python3 ~/.openclaw/scripts/get_notion_book.py             # 실제 브리핑 1건
   ```
3. **bookman 라우팅 확인/추가** (`openclaw.json` 은 gitignore 대상이라 서버에서 jq 로 직접):
   ```bash
   cd ~/.openclaw
   cp openclaw.json openclaw.json.bak-$(date +%s)
   jq '.bindings = ([{"agentId":"bookman","match":{"channel":"slack","accountId":"bookman"}},
                     {"agentId":"bookman","match":{"channel":"slack","peer":{"kind":"channel","id":"C0BMHERHA77"}}}]
                    + .bindings)' openclaw.json > /tmp/oc.json \
     && jq empty /tmp/oc.json && mv /tmp/oc.json openclaw.json
   openclaw daemon restart
   ```
   ⚠️ catch-all(`{"agentId":"main","match":{"channel":"slack"}}`) 보다 **앞에** 와야 한다.
4. `.env` 에 `NOTION_READING_DB` 추가(선택). `NOTION_TOKEN` 이 해당 페이지에 **공유(연결)** 돼 있어야 한다.

### 2차 보완 — 노션 실제 구조 반영 (스크린샷 확인 후)

형준님 노션 책 페이지는 **쪽수 줄 + 색칠한 글귀 + 일반 메모** 구조였다.

```
22p                                 ← 쪽수만 있는 줄
왜를 아는 것이 가장 심오하고 …       ← 주황색 = 진짜 글귀
인간의 책임감을 자극하는 표현으로 …   ← 색 없는 일반 메모
```

또 `좋은 글귀`, `부아 c 어록`, `김종원 작가 . 책 어록` 처럼 **어록 전용 페이지**도 DB 행으로 들어있다.
→ 프로퍼티만 보면 "비었다"고 오판하게 되므로, **본문 블록이 실제 본체**다.

보완 내용:
- **강조 인식 추가** — 노션 `rich_text[].annotations` 의 `color`(글자색+`_background` 형광펜)와
  `bold`/`underline` 비율을 계산해 등급을 매긴다.
  0=프로퍼티 직접입력 / 1=색칠·인용블록 / 2=굵게 / 3=일반본문.
  **1순위가 나오면 즉시 채택** → 색칠해둔 문장이 우선 나간다.
- **강조 문장은 까다로운 필터를 건너뛴다** — 사람이 이미 고른 문장이므로
  단어나열/체크리스트 검사로 잘못 버리지 않는다. (일반 본문에만 엄격 적용)
- **쪽수 줄 처리** — `22p` / `35p` / `12쪽` 같은 줄은 글귀 후보에서 빼고 **출처 표시**로만 쓴다.
  문장 앞에 붙은 `153p ` 접두어는 제거한다.
- **본문 캐시 추가** (`workspace/bookman/book_cache.json`, gitignored) —
  `last_edited_time` 이 바뀌면 자동 재수집. 1회 실행당 새로 읽는 책은 **최대 8권**으로 제한해
  슬랙 응답 지연을 막는다. 전체를 미리 담으려면 `--build-cache`.
- `--check` 가 캐시에 모인 문장 수를 등급별로 보여준다. `--clear-cache` 추가.
- (제거) `--no-body` — 본문이 사실상 본체라 의미 없는 옵션이었음.

서버 권장 순서:
```bash
python3 ~/.openclaw/scripts/get_notion_book.py --build-cache   # 1회 (몇 분 걸림)
python3 ~/.openclaw/scripts/get_notion_book.py --check         # 등급별 문장 수 확인
python3 ~/.openclaw/scripts/get_notion_book.py --list 30       # 눈으로 검수
python3 ~/.openclaw/scripts/get_notion_book.py                 # 실제 브리핑
```

### 3차 보완 — "빈손보다 일반 본문이 낫다" (사용자 피드백)

2차 필터가 너무 엄격해서, 애매한 줄을 전부 버리면 최악의 경우 `NO_QUOTE`(빈손)가 나올 수 있었다.
사용자 판단: **일반 본문도 좋다. 엉뚱한 공백보다 낫다.**

- 필터를 **버리기 → 뒤로 미루기**로 전환. `is_good_sentence()`(bool) 를
  `score_sentence()`(등급 or None) 로 교체하고 **4순위 `TIER_WEAK`** 를 신설했다.
  단어 나열·체크리스트 항목·라벨 나열·끝맺음 없는 줄·길이가 애매한 줄은
  이제 버려지지 않고 4순위로 내려가 다른 후보가 없을 때 쓰인다.
- **진짜로 버리는 줄은 넷뿐**: 길이 6자 미만/600자 초과 · 한글 없음 · 링크 · 쪽수만 있는 줄(`22p`).
  (길이 기준을 두 겹으로 분리: HARD_MIN/MAX = 6/600 은 버림, GOOD_MIN/MAX = 10/260 밖은 후순위)
- **빈손일 때 더 찾아본다**: 후보를 하나도 못 찾은 상태면 1회 실행당 새로 읽는 책 상한을
  10권 → 30권(`DESPERATE_MULTIPLIER=3`)까지 늘린다. 이미 쓸 만한 후보(3순위 이내)를
  잡았으면 상한에서 즉시 멈춰 응답 속도를 지킨다.
- `--check` 가 후순위 문장 수도 보여준다. 등급 의미가 바뀌어 `CACHE_VERSION` 2 → 3
  (기존 캐시는 자동 무효화되어 다시 읽는다).

환각 차단 원칙은 그대로. 노션에 정말 아무것도 없을 때만 exit 2.

### 4차 보완 — 소제목이 글귀로 섞이는 문제 (서버 실행 결과 확인 후)

서버에서 `--list 30` 을 돌려본 결과 실제로 잘 동작했으나, `[본문]` 등급에
**책의 소제목(목차)** 이 섞여 나왔다.
예: "지켜야 할 주의 사항", "압구정에서 시작되는 흐름", "100날 투자 공부해도 부자가 될 수 없는 이유".

- `heading_1/2/3` 블록은 `TIER_WEAK`(후순위)로 내린다. 단 **색칠돼 있으면 예외**(사람이 고른 것).
- 일반 본문 중에서도 **마침표·물음표·느낌표 없이 40자 미만으로 끝나는 줄**은
  소제목일 확률이 높아 후순위로 내린다. 색칠·굵게 표시된 줄은 이 규칙에서 면제.
  → "…이기 때문이다.", "…중요하다." 같은 진짜 문장은 그대로 3순위 유지됨을 테스트로 확인.
- `--list` 가 한 책에서만 30줄을 쏟아내던 문제 → 책당 5줄 상한(`LIST_PER_BOOK`)을 둬
  여러 책을 골고루 검수할 수 있게 했다.
- 등급 규칙이 바뀌어 `CACHE_VERSION` 3 → 4 (기존 캐시 자동 무효화).

**첫 실전 검증 성공 기록**:
```
"좋은 글 한문장"
아이는 지금도 무럭무럭 크고 있고, 안아줄 수 있는 시간은 점점 줄어들고 있습니다. …
66일 밥상머리 대화법 김종원
[출처] 강조 231p / https://app.notion.com/p/66-1a8d470c68bd80a1a6b0d8aebb7e33c8
```

### 5차 — 제목을 꺾쇠로 감싸기 (양식 확정)

원래 SOUL.md 양식이 `<제목> 저자` 였는데, 이를 '빈칸 표시'로 해석해 꺾쇠 없이 출력하고 있었다.
사용자 의도는 **꺾쇠를 실제로 출력**하는 것. 수정했다.

- `TITLE_WRAP = ("<", ">")` 상수 신설 → `emit()` 이 `<책 제목> 저자` 로 출력.
- 저자가 비면 제목만: `<만일 나에게 단 한 번의 아침이 남아 있다면>`
- ⚠️ 슬랙 mrkdwn 은 `<...>` 를 링크/멘션 문법으로 해석한다. 실제 발송 시 꺾쇠가
  사라지거나 이상하게 보이면 `TITLE_WRAP` 을 `("『", "』")` 등으로 **한 줄만** 바꾸면 된다.
  (스크립트는 stdout 을 그대로 내보내고 에이전트가 전달하는 구조라, 이 상수 하나가 유일한 변경점)

**브리핑은 항상 3줄** — 머리말 / 글귀 / `<제목> 저자`. 글귀가 길면 화면에서만 접혀 보인다.

### 6차 — 머리말 제거, 브리핑 2줄 확정

사용자 요청: `"좋은 글 한문장"` 머리말 줄 불필요.

```
왜를 아는 것이 가장 심오하고 강력한 형태의 지식이다. …
<퓨처셀프> 벤저민 하디
```

- `emit()` 에서 머리말 `print` 제거. 이제 stdout 은 **글귀 / `<제목> 저자` 2줄**.
- SOUL.md 에 "머리말을 붙이지 않는다 / 인사말·설명을 앞뒤에 넣지 않는다" 명시
  (모델이 친절하게 앞말을 덧붙이는 것을 막기 위함).

#### 참고 — 2줄 중 '글귀'가 뽑히는 기준 (cmd_pick 요약)
1. DB 132권을 읽어 `random.shuffle` → **매번 다른 책부터** 살펴본다.
2. 각 책의 문장 후보는 **등급 오름차순**으로 정렬돼 있다
   (0 직접입력 → 1 색칠·인용 → 2 굵게 → 3 본문 → 4 후순위).
   같은 등급 안에서는 **노션 페이지에 적힌 순서**(위→아래)를 유지한다(안정 정렬).
3. 이미 보낸 문장(`book_sequence_state.json` 의 지문)은 후보에서 제외.
4. 그 책의 남은 후보 중 **1등**을 본다.
   - 등급 0·1(직접입력/색칠)이면 → **즉시 채택하고 종료**.
   - 아니면 후보로 들고 다음 책으로 넘어가, 더 좋은 등급이 나오면 교체.
5. 3순위 이내 후보를 쥔 채 새로 읽은 책이 10권을 넘으면 멈추고 그걸 채택(응답 속도).
6. 모든 문장을 다 보냈으면 기록을 비우고 재순환. 정말 아무것도 없으면 exit 2.

즉 **"랜덤한 책 → 그 책에서 가장 잘 표시된, 아직 안 보낸 문장"** 이 뽑힌다.

### 7차 — 엔터 2번(빈 줄)을 글귀 덩어리 경계로 (사용자 요청)

기존에는 노션 블록 1개 = 글귀 1개였다. 엔터 한 번으로 줄만 바꿔 이어 쓴 글귀가
반 토막 나서 나갈 수 있었다.

- `page_blocks()` 를 두 단계로 분리했다.
  - `collect_blocks()` : 빈 블록까지 포함해 **원래 순서대로 평평하게** 수집
  - `group_blocks()`   : 빈 줄을 경계로 **덩어리 묶기** + 덩어리 전체 기준으로 등급 재계산
    (색칠 비율은 글자 수 가중평균)
- 끊는 조건 7가지: ①빈 줄 ②앞 줄이 `.!?` 로 끝남 ③쪽수 줄 ④소제목
  ⑤블록 종류 변경 ⑥색칠 여부 변경 ⑦`GROUP_MAX`(300자) 초과.
- ②를 넣은 이유: 빈 줄만 기준으로 삼으니 강원국·인생상승선처럼 **불릿이 연달아 있는 책**에서
  서로 무관한 문장 8개가 272자 덩어리로 뭉쳤다. "문장이 안 끝난 채 줄만 바뀐 경우에만
  이어 붙인다"로 바꿔 해결. 테스트로 불릿 8개 → 덩어리 8개 유지 확인.
- ⑥이 필요한 이유: 색칠한 글귀 바로 밑의 검은 메모가 섞이면 색칠 비율이 희석돼
  1순위(강조)에서 밀려난다.
- `GOOD_MAX` 260 → 300 (덩어리로 합쳐졌다는 이유만으로 후순위가 되지 않게).
- `CACHE_VERSION` 4 → 5 (덩어리 기준이 바뀌었으므로 기존 캐시 자동 무효화).
