# 🔐 비밀 키를 .env 로 숨기기 (쉬운 절차)

모든 API 키를 `openclaw.json` 에서 빼서 `.env` 한 곳에 모읍니다.
`.env` 는 git 에 올라가지 않고(`.gitignore`), openclaw 가 시작할 때 자동으로 읽어
`openclaw.json` 안의 `${변수명}` 을 실제 값으로 채웁니다.

> 💡 **openclaw 네이티브 방식 추천**: openclaw 에는 자체 비밀 관리자가 있습니다.
> `openclaw secrets audit --check` 로 평문 비밀을 확인하고,
> `openclaw secrets configure` 로 env 기반 SecretRef 로 옮길 수 있습니다.
> 아래 `.env` 방식(수동)과 결과는 같으며, 둘 중 편한 쪽을 쓰면 됩니다.

## .env 에 넣어야 하는 키 목록 (총 7개)

| 변수명 | 무엇 | 어디서 받나 | 형식 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN_DEFAULT` | 텔레그램 봇토큰 (신문 분석가 봇) | 텔레그램 **@BotFather** → `/mybots` → 봇 선택 → **API Token** | `숫자:영문숫자` |
| `TELEGRAM_BOT_TOKEN_PT` | 텔레그램 봇토큰 (PT 트레이너 봇) | @BotFather → `/mybots` → PT 봇 → API Token | `숫자:영문숫자` |
| `BRAVE_API_KEY` | Brave 웹검색 키 | https://api-dashboard.search.brave.com/ → **API Keys** | `BSA...` |
| `SLACK_APP_TOKEN` | Slack 앱 토큰 | https://api.slack.com/apps → 앱 → Basic Information → App-Level Tokens | `xapp-...` |
| `SLACK_BOT_TOKEN` | Slack 봇 토큰 | 같은 앱 → OAuth & Permissions → Bot User OAuth Token | `xoxb-...` |
| `GEMINI_API_KEY` | Gemini(Google) 키 | https://aistudio.google.com/apikey → **Create API key** | `AIza...` |
| `GATEWAY_TOKEN` | 게이트웨이 접속 토큰 | 아무 랜덤 문자열 (`openssl rand -hex 24`) | 임의 |

## 방법 A: 마법사로 한 번에 (제일 쉬움)

서버에서:

```bash
cd ~/.openclaw
scripts/setup-env.sh        # 키를 하나씩 물어봄. 모르면 엔터로 건너뛰기
scripts/apply-env-refs.sh   # openclaw.json 을 ${참조} 로 자동 교체
openclaw daemon restart           # 이 서버의 재시작 명령
```

끝입니다. `setup-env.sh` 가 각 키의 발급처를 안내하며 하나씩 받아 `.env`(권한 600)에 저장하고,
`apply-env-refs.sh` 가 `openclaw.json` 의 실제 값을 `${...}` 참조로 바꿔줍니다.

## 방법 B: 이미 openclaw.json 에 키가 있으면 (손입력 없이)

지금처럼 키가 `openclaw.json` 에 이미 들어있다면, 그대로 뽑아서 옮기기만:

```bash
cd ~/.openclaw
scripts/extract-secrets-to-env.sh   # openclaw.json → .env 로 값 복사
scripts/apply-env-refs.sh           # openclaw.json 을 ${참조} 로 교체
openclaw daemon restart
```

## 방법 C: 손으로 직접

```bash
cd ~/.openclaw
cp .env.example .env
nano .env            # 위 표를 보고 값 5개 채우기
chmod 600 .env
scripts/apply-env-refs.sh
openclaw daemon restart
```

## 확인

재시작 후 봇이 정상 응답하면 성공입니다. `.env` 가 잘 감춰졌는지 확인:

```bash
git status --ignored | grep .env      # .env 가 "ignored" 로 나오면 정상 (추적 안 됨)
grep -c '\${' openclaw.json            # 값이 ${...} 참조로 바뀐 개수
```

## ⚠️ 중요: 기존 키 재발급(rotate)

이 키들은 예전에 git 히스토리·백업 파일에 노출됐습니다. `.env` 로 옮겨도
**이미 노출된 값 자체는 무효화가 최선**입니다. 아래를 새로 발급받아 `.env` 에 갱신하세요:

- 텔레그램 봇토큰: @BotFather → 봇 선택 → **API Token → Revoke current token**
- Brave 키: 대시보드에서 기존 키 삭제 후 새로 생성
- Gemini 키: AI Studio 에서 기존 키 삭제 후 새로 생성
- 게이트웨이 토큰: `openssl rand -hex 24` 로 새 값

> 히스토리에 남은 노출 파일 자체를 git 에서 완전히 지우는 작업(히스토리 재작성)은
> 별도 단계입니다. 필요하면 요청하세요.
