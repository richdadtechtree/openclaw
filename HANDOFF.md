# HANDOFF — 현재 상태 & 다음 할 일

> 먼저 `CLAUDE.md`(규칙/함정)를 읽으세요. 이 문서는 진행 현황과 남은 작업입니다.
> 서버: openclaw = `/home/ubuntu/.openclaw`, stock = `/home/ubuntu/stock/stock`.

## 🗂️ 무엇이 어디서 도나 (편집 위치)
- **openclaw 폴더에서 돎(=claude.ai 편집·동기화 가능)**: 뉴스 브리핑(`cron/jobs.json` + `workspace/news_fetcher.py` + `workspace/SOUL.md`), PT 트레이너(`agents/pt-trainer/`), 날씨 브리핑(`cron/jobs.json`). 단 `openclaw.json`/`.env`(비밀)는 서버 전용.
- **주식 프로젝트**: 실행은 `~/stock/stock`(nohup `scheduler.py`). 소스를 openclaw repo `stock/` 로 **vendoring 도입**(A안) → `git-auto-pull.sh` 후 `scripts/sync-stock.sh` 가 코드만 rsync + 변경 시 scheduler 재시작. **최초 씨딩 필요**(`stock/README.md` 참고).

## ✅ 완료된 것
1. **자동 git 동기화**: 클로드에서 openclaw main에 push → 서버 cron(1분)이 pull + `openclaw daemon restart`. 런타임 파일 추적 제외.
2. **비밀 → .env 정리** + `SECRETS.md`/`.env.example`. (일부는 아직 openclaw.json 평문 — 감사 남음. 노출 키 재발급 권장.)
3. **뚜떵또(openclaw AI) 모델**: **주 = GPT(OpenAI)** 로 살림(어제 크레딧 충전 + `onboard --classic`). 정상 동작 중.
4. **온디맨드 신문 브리핑**: 정해진 시각 자동 브리핑 **OFF**. 사용자가 봇에 "신문 브리핑 해줘" 요청 시에만 → 분석 답변 + **구글 시트 저장**(`sheets_push.py`, `workspace/SOUL.md`에 규칙 있음).
   - 구글 시트: Apps Script 웹앱. `.env`에 `SHEETS_WEBAPP_URL`, `SHEETS_WEBAPP_SECRET`.
   - (노션은 폐기 — 시트로 전환. `notion_push.py`는 남겨둠, 미사용.)
5. **stock 대시보드 → 슬랙**: 평일 **15:40** openclaw cron `stock-slack-briefing`(command job) → `slack_briefing.py`. 채널 `C0BMJENDF62`. AI 미사용, 정상.
6. **stock 관심종목 급등락 알림**: `scheduler.py alert_job`(약 10분) → 텔레그램 `briefing-bot`. 2% 단위. AI 미사용, 정상.
7. **관심종목 알림 슬랙 확장(+시간대 게이팅)**: 텔레그램 그대로 두고 **슬랙에도** 전송. 국장(숫자코드)=KRX 장중만, 미장=24h. `scripts/stock_alert_slack.py`(`notify_events`) + `patch_scheduler_slack.py` 로 서버 반영·검증 완료. (상세: 아래 C)

## ⏳ 진행 중 / 다음 할 일 (우선순위 순)

### A. Gemini 백업(fallback) 적용 — ⚠️ **아래 jq 는 이 버전에서 무효(수정 필요)**
GPT 주력 유지 + Gemini 무료 백업(`gemini-flash-lite-latest` → `gemini-flash-latest`).
> ⚠️ **openclaw 2026.7.1-2 는 `google.api="openai-chat"` 를 거부**한다(2026-08-04 확인: config invalid → 게이트웨이 기동 실패). 실제로 이 값이 openclaw.json 에 남아 restart 가 깨졌고, `jq 'del(.models.providers.google)'` 로 제거해 복구함. **다음에 Gemini 붙일 땐 아래 jq 의 `.api="openai-chat"` 부분을 이 버전 허용값으로 바꿔야 함** — 네이티브 `google-generative-ai`(권장, baseUrl 우회 불필요) 또는 OpenAI-호환이면 `openai-completions`. `openclaw config validate` 로 반드시 선검증 후 restart.

서버에서(⚠️ api 값 교체 후 사용):
```bash
cd ~/.openclaw
GKEY=$(grep '^GEMINI_API_KEY=' .env | cut -d= -f2-)
UNIT=~/.config/systemd/user/openclaw-gateway.service
sed -i '/^Environment=GEMINI_API_KEY=/d' "$UNIT"; sed -i "/^\[Service\]/a Environment=GEMINI_API_KEY=$GKEY" "$UNIT"
systemctl --user daemon-reload
cp openclaw.json openclaw.json.bak-fb.$(date +%s)
jq '.agents.defaults.model.fallbacks=([ (.agents.defaults.model.fallbacks // [])[] | select(startswith("openai/")) ] + ["google/gemini-flash-lite-latest","google/gemini-flash-latest"]) | .agents.defaults.models=((.agents.defaults.models // {}) + {"google/gemini-flash-lite-latest":{},"google/gemini-flash-latest":{}}) | .models.providers.google.api="openai-chat" | .models.providers.google.baseUrl="https://generativelanguage.googleapis.com/v1beta/openai/" | .models.providers.google.models=((.models.providers.google.models // []) + [{"id":"gemini-flash-lite-latest","name":"gemini-flash-lite-latest"},{"id":"gemini-flash-latest","name":"gemini-flash-latest"}] | unique_by(.id)) | .agents.list |= map(if .model then .model.fallbacks=([ (.model.fallbacks // [])[] | select(startswith("openai/")) ] + ["google/gemini-flash-lite-latest","google/gemini-flash-latest"]) else . end)' openclaw.json > /tmp/oc.json && jq empty /tmp/oc.json && mv /tmp/oc.json openclaw.json
openclaw daemon restart
jq '.agents.defaults.model' openclaw.json
```
검증: `curl -s https://generativelanguage.googleapis.com/v1beta/openai/chat/completions -H "Authorization: Bearer $GKEY" -H "Content-Type: application/json" -d '{"model":"gemini-flash-latest","messages":[{"role":"user","content":"hi"}]}'` → `choices` 오면 정상.

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
- (폐기)노션 DB id: `3b1d470c68bd80c88009ec6e91c5da3d`.
- stock 감시종목: `~/stock/stock/monitored_stocks.json` (국장=숫자코드, 미장=영문). 알림 기준: `CUSTOM_ALERT_STEP`(기본 2%).
- 관심종목 데이터: `market_data.get_custom_stocks_snapshot()` → `{symbol:{name,current,change_rate,is_etf}}`.

## ⚠️ 잊지 말 것
- 노출된 키 **재발급**(텔레그램봇, Slack, Brave, Gateway, Gemini).
- stock `scheduler.py`가 상시 실행돼야 15:40 캡처/알림 동작 (systemd user `stock-dashboard` 권장; 아니면 재부팅 시 꺼짐).
