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

## 🗞️ 슬랙 데일리 다이제스트 (뷰어)
슬랙 접속 불가 환경에서 '그날 시스템이 슬랙에 보낸 내용'을 claude.ai 아티팩트로 읽는 기능.
- **로그 수집**: `scripts/slack_log.py`(+`stock/slack_log.py`) `log_slack()` → `~/.openclaw/slack_logs/YYYY-MM-DD.jsonl`(KST, gitignored). 훅: 신문(`slack_text`), 주식 브리핑(`slack_briefing`), 급등락/사이드카(`stock_alert_slack.send_slack` source 태깅). **시스템 발신분만**(뚜떵또 대화·사용자 메시지는 미포함 — 원하면 Slack API 읽기 권한 추가 필요).
- **뷰어**: claude.ai 아티팩트(시간축 원장 타임라인, 카테고리 필터, 라이트/다크). 현재 샘플 데이터로 게시됨.
- **실데이터 갱신 워크플로**: 서버에서 `python3 ~/.openclaw/scripts/slack_digest.py [날짜]` → 출력 JSON 한 줄을 Claude 에게 붙이면 아티팩트를 그날 실데이터로 갱신(같은 URL 유지).

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
