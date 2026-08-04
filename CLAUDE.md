# CLAUDE.md — 이 리포 작업 컨텍스트

이 리포(`richdadtechtree/openclaw`)는 서버의 **`/home/ubuntu/.openclaw`** (openclaw AI 에이전트 홈)이며,
Git으로 서버와 자동 동기화됩니다. 별도 프로젝트인 **stock**(`/home/ubuntu/stock/stock`)도 함께 다룹니다.

## 시스템 구성 (누가 무엇을 하나)
- 🤖 **뚜떵또 = openclaw AI 에이전트** (`~/.openclaw`): 텔레그램/슬랙 대화 + **온디맨드 신문 브리핑**. AI 모델 사용.
- 📈 **stock 프로젝트** (`~/stock/stock`, FastAPI+Playwright, `briefing-bot` 텔레그램): 주가 대시보드 캡처 + 관심종목 급등락 알림. **AI 미사용(규칙 기반)** → 모델 문제와 무관하게 동작.

## 핵심 규칙 / 함정 (필독)
- **서버 경로**: openclaw = `/home/ubuntu/.openclaw`, stock = `/home/ubuntu/stock/stock`.
- **파이썬**: 서버에 맨 `python` 없음 → `python3` 또는 venv `~/stock/stock/venv/bin/python` 사용.
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
| `notion_push.py` / `notion-briefing-*.txt` | (구) 노션 저장 — **시트로 대체됨, 미사용** |

> 상세 현황·다음 할 일은 **`HANDOFF.md`** 참고.
