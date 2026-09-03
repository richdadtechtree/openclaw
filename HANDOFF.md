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

## 🗣️ AI 토론 채널(#ai-토론) — ✅ 코드 완료, 서버 수동 설정 남음 (2026-09-03)

`openclaw_multi_model_debate_plan.md` 계획서 기반으로 GPT/Gemini/Qwen(OpenRouter 무료)/Mistral(무료) 4개 모델이
독립 의견 → (선택) 1회 반론 → GPT 사회자 종합까지 하는 슬랙 토론 채널을 구축했다.
**기존 main/pt-trainer/keepgoing 에이전트·바인딩은 전혀 건드리지 않았다** (새 에이전트 `debate` + 새 바인딩만 추가).

### 구조
```
Slack #ai-토론 (새 채널, 멘션 시에만 응답)
   ↓
openclaw agent "debate" (workspace/debate/SOUL.md)
   → exec 로 scripts/debate.py "<원문>" 실행 → stdout 을 그대로 답장
        ↓
   scripts/debate.py (openclaw 모델 라우팅과 무관, 각 공급자 REST 직접 호출)
        ├─ GPT      (OpenAI Chat Completions, OPENAI_API_KEY)
        ├─ Gemini   (Google Generative AI 네이티브 API, 기존 GEMINI_API_KEY 재사용)
        ├─ Qwen     (OpenRouter, OPENROUTER_API_KEY, :free 모델)
        └─ Mistral  (Mistral API, MISTRAL_API_KEY, 무료 모드)
```
- 모드: 무키워드/`개별답변:` = 개별 답변(모델별 의견+사회자 종합, 5회 호출), `토론:` = 1차의견→반론1회→사회자 종합(9회 호출), `상태`/`도움말` = API 호출 없음.
- 사회자의 "핵심 주장 정리"는 별도 LLM 호출 없이 스크립트가 기계적으로 조합 → 계획서 §12 비용 예산(5회/9회) 그대로 지킴.
- 장애 처리(계획서 §8 그대로 구현): 429=1회 재시도 후 "한도초과" 표시, 401/403=재시도 안함, 타임아웃="응답 지연" 표시, 모델 하나 실패해도 나머지+사회자 요약 계속, 무료 모델 ID 오류(400/404)시 예비 모델로 1회 전환, 사회자(GPT) 실패시 모델 원문만이라도 게시, 전체 실패시 오류 요약+재시도 안내.
- 분당 호출 제한(기본 3회/분)과 사용량 로그는 `workspace/debate/state/`(git 추적 제외, 런타임 전용)에 자동 저장.
- 토론자에게는 함수 호출/툴을 전혀 주지 않는 순수 텍스트 API 호출이라 "명령 실행·파일쓰기·메시지 발송 금지" 원칙이 코드 구조상 자동으로 지켜짐.

### 📌 서버에서 수동으로 해야 하는 것 (코드만으로는 안 됨)
1. **Slack `#ai-토론` 채널 생성** + 기존 봇(예: `default`/뚜떵또 봇) 초대 → 채널 ID 확인(채널 세부정보 → 채널ID 복사, `C...` 형식).
2. `openclaw.json` 의 새 바인딩에 있는 **placeholder `C000000AIDEBATE` 를 실제 채널 ID로 교체**:
   ```bash
   cd ~/.openclaw
   sed -i 's/C000000AIDEBATE/<실제채널ID>/' openclaw.json
   openclaw config validate   # 문법 확인 후
   openclaw daemon restart
   ```
   (claude.ai 에서 고치고 push 해도 auto-pull 이 반영한다. 다만 채널ID는 서버에서만 알 수 있으므로 보통 서버에서 직접 고치는 편이 빠르다.)
3. **API 키 발급 후 `~/.openclaw/.env` 에 추가**(`.env.example` §11 참고):
   - `OPENAI_API_KEY` (https://platform.openai.com/api-keys — main 봇의 OAuth 로그인과는 별개의 키)
   - `OPENROUTER_API_KEY` (https://openrouter.ai/keys)
   - `MISTRAL_API_KEY` (https://console.mistral.ai/ → Studio 무료 모드 활성화 후 발급)
   - `GEMINI_API_KEY` 는 이미 있는 값 재사용(추가 발급 불필요).
4. **무료 모델 ID 확정**(자주 바뀜 — 반드시 구축 당일 확인): OpenRouter에서 `:free` 로 끝나는 Qwen 계열 모델 ID, Mistral 무료 계정에서 쓸 수 있는 모델 ID를 조회해 `.env` 의 `DEBATE_QWEN_MODEL` / `DEBATE_QWEN_MODEL_FALLBACK` / `DEBATE_MISTRAL_MODEL` / `DEBATE_MISTRAL_MODEL_FALLBACK` 에 채운다. 한국어로 짧은 시험 질문을 보내 정상 응답을 먼저 확인.
5. 위 3~4 완료 후 서버에서 검증:
   ```bash
   cd ~/.openclaw
   python3 scripts/debate.py "상태"          # 키 등록 여부/모델ID 확인 (API 호출 없음)
   python3 scripts/debate.py "테스트 질문입니다"  # 실제 4개 모델 호출 확인
   ```
6. Slack 앱 권한: 앱 멘션/채널 메시지 읽기 + 메시지·스레드 답글 쓰기만 있으면 충분(기존 봇 재사용이면 이미 충족).
7. (선택) 결제수단 등록된 공급자는 지출 한도를 0원 또는 매우 낮게 설정.

### 아직 안 된 것 / 주의
- Qwen·Mistral 정확한 모델 ID는 코드에 **placeholder**만 있다(위 4번 전에는 "모델 미설정" 오류로 실패 표시됨 — 의도된 동작).
- 계획서의 "시작 시 진행 메시지 한 번"은 `debate` 에이전트가 exec 호출 전에 먼저 텍스트로 답하도록 SOUL.md 에 지시했지만, 실제로 슬랙에 두 번째 메시지로 분리돼 나가는지는 openclaw 런타임의 중간 텍스트 스트리밍 동작에 달려있다 — **서버에서 실제로 확인 필요**.
- 이 기능은 기존 `main`/`keepgoing`/`bookman`/`pt-trainer` 와 완전히 분리돼 있어, 문제가 생기면 `openclaw.json` 에서 `debate` 바인딩 항목만 지우면 즉시 롤백된다(계획서 §15 롤백 계획).

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
